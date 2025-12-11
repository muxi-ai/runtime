# A2A Troubleshooting Guide

This guide helps diagnose and resolve common A2A communication issues.

## Quick Diagnostics

### 1. Check A2A Status

```python
# In your agent code
status = await self.get_a2a_status()
print(f"A2A Enabled: {status['enabled']}")
print(f"Inbound Server: {status['inbound_server']}")
print(f"Registered Agents: {status['registered_agents']}")
```

### 2. Test Internal A2A

```python
# Test message to another agent in same formation
try:
    response = await self.send_a2a_message(
        agent_id="test-agent",
        message="ping"
    )
    print(f"Internal A2A working: {response}")
except Exception as e:
    print(f"Internal A2A failed: {e}")
```

### 3. Test External A2A

```bash
# Test A2A server endpoint
curl -X GET http://localhost:8181/health

# Test with authentication
curl -X GET http://localhost:8181/agents \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Common Issues and Solutions

### Issue: "Agent not found"

**Symptoms**:
```
Error: Agent 'target-agent' not found
```

**Diagnosis**:
1. Check if agent exists in formation
2. Verify agent ID is correct
3. Check if agent is registered with registry

**Solutions**:
```python
# List available agents
agents = await self.discover_agents()
print(f"Available agents: {[a['id'] for a in agents]}")

# Check specific agent
agent_info = await self.get_agent_info("target-agent")
```

### Issue: "Authentication failed"

**Symptoms**:
```
Error: 401 Unauthorized
Authentication failed: Invalid bearer token
```

**Diagnosis**:
1. Check if authentication is configured
2. Verify token/credentials are correct
3. Check token hasn't expired

**Solutions**:
```yaml
# Verify configuration
a2a:
  inbound:
    auth:
      type: "bearer"
      token: "${{ secrets.A2A_TOKEN }}"  # Check this secret exists
```

```bash
# Test token
export TOKEN="your-token-here"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8181/agents
```

### Issue: "Connection refused"

**Symptoms**:
```
Error: Connection refused to localhost:8181
```

**Diagnosis**:
1. Check if A2A server is running
2. Verify port is correct
3. Check firewall rules

**Solutions**:
```bash
# Check if port is listening
netstat -an | grep 8181
# or
lsof -i :8181

# Check formation logs
grep "A2A server started" formation.log
```

### Issue: "Registry unreachable"

**Symptoms**:
```
Warning: Failed to register with registry https://registry.example.com
Error: Connection timeout
```

**Diagnosis**:
1. Check network connectivity
2. Verify registry URL
3. Check if registry is running

**Solutions**:
```bash
# Test registry connectivity
curl https://registry.example.com/health

# Test DNS resolution
nslookup registry.example.com

# Test with different timeout
curl --connect-timeout 10 https://registry.example.com/health
```

### Issue: "Formation startup failed - strict policy"

**Symptoms**:
```
============================================================
⚠️  FORMATION STARTUP FAILED
============================================================

Policy: STRICT
Required registries are unreachable:

  ❌ https://registry.example.com

To resolve this issue, you can:
  1. Start the registry server(s) listed above
  2. Change startup_policy to 'lenient' in formation.afs
  3. Remove the unreachable registries from configuration

============================================================
```

**Diagnosis**:
1. Formation configured with `startup_policy: "strict"`
2. One or more registries are unreachable during startup
3. Health checks are failing

**Solutions**:

**Option 1: Start the Registry**
```bash
# Start local registry for development
python -m muxi.tools.a2a_registry --port 9090

# Or start the specific registry service listed in the error
```

**Option 2: Change to Lenient Policy**
```yaml
# formation.afs (or .yaml)
a2a:
  outbound:
    startup_policy: "lenient"  # Allow startup even if registry is down
    registries:
      - "https://registry.example.com"
```

**Option 3: Use Retry Policy**
```yaml
# formation.afs (or .yaml)
a2a:
  outbound:
    startup_policy: "retry"           # Retry connections
    retry_timeout_seconds: 60         # Wait up to 60 seconds
    registries:
      - "https://registry.example.com"
```

**Option 4: Per-Registry Configuration**
```yaml
# Mark registries as optional
a2a:
  outbound:
    startup_policy: "strict"
    registries:
      - url: "https://critical-registry.com"
        required: true                    # Must be available
      - url: "https://optional-registry.com"
        required: false                   # Can be down
```

**When to Use Each Policy**:
- **Lenient**: Development, optional services
- **Strict**: Production systems with critical dependencies
- **Retry**: Temporary network issues, gradual startup

### Issue: "Message timeout"

**Symptoms**:
```
Error: A2A message timeout after 30 seconds
```

**Diagnosis**:
1. Target agent taking too long
2. Network latency
3. Agent overloaded

**Solutions**:
```yaml
# Increase timeout
a2a:
  outbound:
    default_timeout_seconds: 60  # Increase from 30

# Or per-service
services:
  - service_id: "slow-service"
    timeout_seconds: 120
```

### Issue: "Duplicate agent registration"

**Symptoms**:
```
Error: Agent 'my-agent' already registered
```

**Diagnosis**:
1. Previous registration not cleaned up
2. Multiple formations with same agent ID
3. Registry persistence issue

**Solutions**:
```python
# Force deregistration
await registry_client.deregister_agent("my-agent")

# Use unique agent IDs
agent_id = f"{agent_name}-{formation_id}"
```

## Debug Logging

### Enable A2A Debug Logs

```yaml
logging:
  streams:
    - transport: "stdout"
      level: "debug"
      format: "text"
      events:
        - "a2a.*"  # All A2A events
        - "a2a.message.*"  # Message flow
        - "a2a.auth.*"  # Authentication
        - "a2a.registry.*"  # Registry operations
```

### Useful Log Patterns

```bash
# Watch A2A message flow
tail -f formation.log | grep "a2a.message"

# Monitor authentication
tail -f formation.log | grep "a2a.auth"

# Track registry operations
tail -f formation.log | grep "a2a.registry"
```

## Network Diagnostics

### Test A2A Endpoints

```bash
# Health check
curl -v http://localhost:8181/health

# List agents (no auth)
curl -v http://localhost:8181/agents

# Send test message
curl -v -X POST http://localhost:8181/agents/test-agent/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "message": {
      "parts": [{"type": "text", "text": "Test message"}]
    }
  }'
```

### Check Port Availability

```bash
# Check if port is in use
sudo lsof -i :8181

# Find process using port
sudo netstat -nlp | grep :8181

# Check firewall (Linux)
sudo iptables -L -n | grep 8181

# Check firewall (macOS)
sudo pfctl -s rules | grep 8181
```

## Configuration Validation

### Validate Formation Config

```python
# Check A2A configuration
from muxi.formation.config.validation import FormationValidator

validator = FormationValidator()
result = validator.validate_file("formation.afs")

if not result.is_valid:
    print("Configuration errors:")
    for error in result.errors:
        print(f"  - {error}")
```

### Common Configuration Errors

1. **Missing required fields**:
   ```yaml
   # Bad - missing auth type
   inbound:
     auth:
       token: "secret"

   # Good
   inbound:
     auth:
       type: "bearer"
       token: "secret"
   ```

2. **Invalid port number**:
   ```yaml
   # Bad - port too low
   inbound:
     port: 80  # Requires root

   # Good
   inbound:
     port: 8181  # User-accessible
   ```

3. **Mismatched auth types**:
   ```yaml
   # Bad - bearer auth with api_key field
   auth:
     type: "bearer"
     key: "secret"  # Should be 'token'

   # Good
   auth:
     type: "bearer"
     token: "secret"
   ```

## Performance Issues

### Slow Message Delivery

**Diagnosis**:
```python
import time

start = time.time()
response = await self.send_a2a_message(...)
duration = time.time() - start
print(f"Message took {duration:.2f} seconds")
```

**Solutions**:
1. Check network latency
2. Profile target agent processing
3. Enable connection pooling
4. Use caching for discovery

### High Memory Usage

**Diagnosis**:
```bash
# Monitor memory usage
ps aux | grep python | grep formation

# Check for memory leaks
python -m tracemalloc formation.py
```

**Solutions**:
1. Limit cache sizes
2. Close unused connections
3. Implement connection pooling
4. Regular garbage collection

## Recovery Procedures

### Reset A2A State

```python
# In emergency, reset A2A state
async def reset_a2a():
    # Stop A2A server
    if hasattr(overlord, 'a2a_server'):
        await overlord.a2a_server.stop()

    # Clear registrations
    if hasattr(overlord, 'registry_client'):
        await overlord.registry_client.deregister_all()

    # Restart A2A
    await overlord.a2a_coordinator.startup()
```

### Manual Deregistration

```python
# If automatic deregistration fails
from muxi.services.a2a.registry_client import A2ARegistryClient

client = A2ARegistryClient(["https://registry.example.com"])
await client.deregister_agent("stuck-agent")
```

### Force Registry Sync

```python
# Re-register all agents
async def force_registry_sync():
    for agent_id, agent in overlord.agents.items():
        agent_card = create_agent_card(agent)
        await registry_client.register_agent(agent_card)
```

## Monitoring and Alerts

### Health Check Script

```python
#!/usr/bin/env python3
import asyncio
import httpx

async def check_a2a_health(formation_url):
    async with httpx.AsyncClient() as client:
        try:
            # Check A2A server
            resp = await client.get(f"{formation_url}/health")
            health = resp.json()

            print(f"A2A Status: {health['status']}")
            print(f"Agents: {len(health['agents'])}")

            # Check each agent
            for agent_id in health['agents']:
                agent_resp = await client.get(
                    f"{formation_url}/agents/{agent_id}"
                )
                if agent_resp.status_code == 200:
                    print(f"  ✓ {agent_id}: OK")
                else:
                    print(f"  ✗ {agent_id}: FAILED")

        except Exception as e:
            print(f"Health check failed: {e}")

asyncio.run(check_a2a_health("http://localhost:8181"))
```

### Prometheus Metrics

```python
# Add to your formation
from prometheus_client import Counter, Histogram

a2a_messages_sent = Counter('a2a_messages_sent_total', 'Total A2A messages sent')
a2a_message_duration = Histogram('a2a_message_duration_seconds', 'A2A message duration')
a2a_errors = Counter('a2a_errors_total', 'Total A2A errors', ['error_type'])
```

## Getting Help

### Collect Diagnostic Information

When reporting issues, collect:

1. **Formation configuration** (sanitized):
   ```bash
   cat formation.afs | grep -A 20 "^a2a:"
   ```

2. **A2A logs**:
   ```bash
   grep "a2a\." formation.log > a2a_debug.log
   ```

3. **Network state**:
   ```bash
   netstat -an | grep 8181 > network_state.txt
   ```

4. **Version information**:
   ```python
   import a2a
   print(f"A2A SDK Version: {a2a.__version__}")
   ```

### Support Channels

1. **GitHub Issues**: Report bugs and feature requests
2. **Documentation**: Check latest docs
3. **Community Forum**: Ask questions
4. **Stack Overflow**: Tag with `muxi-a2a`
