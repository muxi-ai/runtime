# A2A Message Flow

This document details how messages flow through the A2A system in various scenarios.

## Message Flow Scenarios

### 1. Internal A2A (Same Formation)

When agents in the same formation communicate:

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Agent A   │         │ A2A Service  │         │   Agent B   │
│             │         │  (Singleton) │         │             │
└──────┬──────┘         └──────┬───────┘         └──────┬──────┘
       │                       │                         │
       │ send_a2a_message()    │                         │
       ├──────────────────────▶│                         │
       │                       │                         │
       │                       │ Route: Internal         │
       │                       ├────────────────────────▶│
       │                       │                         │
       │                       │                         │ handle_a2a_message()
       │                       │                         ├─┐
       │                       │                         │ │ process_message()
       │                       │                         │◀┘
       │                       │◀────────────────────────┤
       │                       │       Response          │
       │◀──────────────────────┤                         │
       │     Response          │                         │
       │                       │                         │
```

**Key Points**:
- No network calls
- Direct in-memory routing
- Synchronous execution
- Minimal latency

### 2. External A2A (Different Formations)

When agents communicate across formations:

```
Formation A                                                Formation B
┌─────────────┐      ┌──────────────┐                    ┌──────────────┐      ┌─────────────┐
│   Agent A   │      │ A2A Service  │                    │ A2A Server   │      │   Agent B   │
└──────┬──────┘      └──────┬───────┘                    └──────┬───────┘      └──────┬──────┘
       │                    │                                    │                     │
       │ send_a2a_message() │                                    │                     │
       ├───────────────────▶│                                    │                     │
       │                    │                                    │                     │
       │                    │ Route: External                    │                     │
       │                    ├────────────────────────────────────┤                     │
       │                    │    POST /agents/{id}/message       │                     │
       │                    │    (via A2A SDK Client)           │                     │
       │                    │                                    │                     │
       │                    │                                    │ Authenticate        │
       │                    │                                    ├─┐                   │
       │                    │                                    │ │                   │
       │                    │                                    │◀┘                   │
       │                    │                                    │                     │
       │                    │                                    │ Route to Agent      │
       │                    │                                    ├────────────────────▶│
       │                    │                                    │                     │
       │                    │                                    │                     │ handle_a2a_message()
       │                    │                                    │                     ├─┐
       │                    │                                    │                     │ │ process_message()
       │                    │                                    │                     │◀┘
       │                    │                                    │◀────────────────────┤
       │                    │                                    │     Response        │
       │                    │◀────────────────────────────────────┤                     │
       │                    │         HTTP Response              │                     │
       │◀───────────────────┤                                    │                     │
       │    Response        │                                    │                     │
```

**Key Points**:
- HTTP/HTTPS transport
- Authentication required
- Async execution
- Network latency

### 3. Agent Discovery Flow

How agents discover other agents:

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Agent A   │      │  Discovery   │      │   Registry   │      │  External    │
│             │      │   Service    │      │   Client     │      │  Registry    │
└──────┬──────┘      └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                    │                      │                      │
       │ Discover agents    │                      │                      │
       ├───────────────────▶│                      │                      │
       │ with capability X  │                      │                      │
       │                    │                      │                      │
       │                    │ Check local agents   │                      │
       │                    ├─┐                    │                      │
       │                    │ │                    │                      │
       │                    │◀┘                    │                      │
       │                    │                      │                      │
       │                    │ Check cache          │                      │
       │                    ├─┐                    │                      │
       │                    │ │                    │                      │
       │                    │◀┘                    │                      │
       │                    │                      │                      │
       │                    │ Query registries     │                      │
       │                    ├─────────────────────▶│                      │
       │                    │                      │                      │
       │                    │                      │ GET /discover        │
       │                    │                      ├─────────────────────▶│
       │                    │                      │   ?capability=X      │
       │                    │                      │                      │
       │                    │                      │◀─────────────────────┤
       │                    │                      │   Agent list        │
       │                    │◀─────────────────────┤                      │
       │                    │                      │                      │
       │                    │ Merge results        │                      │
       │                    ├─┐                    │                      │
       │                    │ │ Update cache       │                      │
       │                    │◀┘                    │                      │
       │                    │                      │                      │
       │◀───────────────────┤                      │                      │
       │  Combined results  │                      │                      │
```

**Discovery Priority**:
1. Local agents (same formation)
2. Cached results (recent discoveries)
3. External registries (live lookup)

### 4. Registration/Deregistration Flow

How agents register with external registries:

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Overlord   │      │     A2A      │      │   Registry   │      │  External    │
│             │      │ Coordinator  │      │   Client     │      │  Registry    │
└──────┬──────┘      └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                    │                      │                      │
       │ Formation startup  │                      │                      │
       ├───────────────────▶│                      │                      │
       │                    │                      │                      │
       │                    │ For each agent:      │                      │
       │                    ├─┐                    │                      │
       │                    │ │ Create AgentCard   │                      │
       │                    │◀┘                    │                      │
       │                    │                      │                      │
       │                    │ Register agent       │                      │
       │                    ├─────────────────────▶│                      │
       │                    │                      │                      │
       │                    │                      │ POST /register       │
       │                    │                      ├─────────────────────▶│
       │                    │                      │  {agent_card}       │
       │                    │                      │                      │
       │                    │                      │◀─────────────────────┤
       │                    │                      │   Success           │
       │                    │◀─────────────────────┤                      │
       │                    │                      │                      │
       │◀───────────────────┤                      │                      │
       │  Registration done │                      │                      │
       
       ... (Formation running) ...
       
       │ Formation shutdown │                      │                      │
       ├───────────────────▶│                      │                      │
       │                    │                      │                      │
       │                    │ Deregister all       │                      │
       │                    ├─────────────────────▶│                      │
       │                    │                      │                      │
       │                    │                      │ DELETE /agents/{id}  │
       │                    │                      ├─────────────────────▶│
       │                    │                      │                      │
       │                    │                      │◀─────────────────────┤
       │                    │                      │   Success           │
       │                    │◀─────────────────────┤                      │
       │◀───────────────────┤                      │                      │
```

## Message Format Details

### A2A Message Structure

```json
{
  "message_id": "msg_abc123",
  "from_agent": "research-agent",
  "to_agent": "writer-agent",
  "timestamp": "2024-01-01T12:00:00Z",
  "message": {
    "parts": [
      {
        "type": "text",
        "text": "Please write a summary of this research"
      },
      {
        "type": "data",
        "data": {
          "research_results": [...],
          "max_length": 500
        }
      }
    ]
  },
  "context": {
    "session_id": "session_123",
    "priority": "high"
  }
}
```

### Response Format

```json
{
  "message_id": "msg_resp_xyz",
  "status": "success",
  "response": {
    "parts": [
      {
        "type": "text",
        "text": "Here is the summary..."
      }
    ]
  },
  "metadata": {
    "processing_time": 1.23,
    "tokens_used": 450
  }
}
```

## Error Handling

### Error Flow

```
Agent A ──────▶ A2A Service ──────▶ External Service
                    │                      │
                    │                      ├─ Network Error
                    │                      ├─ Auth Error  
                    │                      ├─ Agent Not Found
                    │                      └─ Processing Error
                    │                      
                    ▼
              Error Handler
                    │
                    ├─ Retry Logic
                    ├─ Fallback
                    └─ Error Response
```

### Common Error Scenarios

1. **Agent Not Found**
   - Local lookup fails
   - Registry has no record
   - Returns 404 error

2. **Authentication Failed**
   - Invalid token/key
   - Expired credentials
   - Returns 401/403 error

3. **Network Timeout**
   - Registry unreachable
   - Slow response
   - Automatic retry with backoff

4. **Processing Error**
   - Agent throws exception
   - Invalid message format
   - Returns 500 error with details

## Performance Optimization

### Caching Strategy

```
First Request:
Agent ──▶ Discovery ──▶ Registry ──▶ Response
                │
                └──▶ Update Cache

Subsequent Requests (within TTL):
Agent ──▶ Discovery ──▶ Cache ──▶ Response
```

### Connection Pooling

```
A2A Service
    │
    ├─ HTTP Client Pool
    │   ├─ Registry 1 Connection
    │   ├─ Registry 2 Connection
    │   └─ Formation B Connection
    │
    └─ Reuse connections for efficiency
```

### Parallel Operations

```
Discovery Request
    │
    ├─── Local Lookup ────┐
    ├─── Cache Lookup ────┤
    └─── Registry Query ──┘
              │
              ▼
         Merge Results
```

## Security Considerations

### Authentication Flow

```
Incoming Request
    │
    ▼
Extract Auth Headers
    │
    ├─ Authorization: Bearer <token>
    ├─ X-API-Key: <key>
    └─ Other custom headers
    │
    ▼
Validate Credentials
    │
    ├─ Check token/key
    ├─ Verify permissions
    └─ Check rate limits
    │
    ▼
Allow/Deny Request
```

### Trust Boundaries

```
┌─────────────────────────────────┐
│        Formation A              │
│  ┌─────────┐    ┌─────────┐   │
│  │ Agent 1 │◀──▶│ Agent 2 │   │ ◀─── Trusted Zone
│  └─────────┘    └─────────┘   │      (No auth required)
└────────────┬────────────────────┘
             │
             │ HTTPS + Auth
             │
┌────────────▼────────────────────┐
│        Formation B              │ ◀─── External Zone
│  ┌─────────┐    ┌─────────┐   │      (Auth required)
│  │ Agent 3 │    │ Agent 4 │   │
│  └─────────┘    └─────────┘   │
└─────────────────────────────────┘
```