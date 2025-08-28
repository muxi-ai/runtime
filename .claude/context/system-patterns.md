# MUXI Runtime System Patterns

This document outlines the core system architecture, design patterns, and component relationships within the MUXI Runtime - the execution engine for AI agent formations.

## System Architecture

MUXI Runtime follows a formation-based architecture where declarative YAML configurations are transformed into living AI systems with sophisticated orchestration, memory management, and tool integration.

### High-Level Component Overview

```
┌────────────────────────────────────┐
│           MUXI AI Server           │  ← User-facing API server
├────────────────────────────────────┤
│          MUXI Runtime              │  ← Core execution engine
│  ┌──────────────────────────────┐  │
│  │      Formation Engine        │  │  ← YAML loader & validator
│  ├──────────────────────────────┤  │
│  │    Overlord   │  Agent Pool  │  │  ← Orchestration layer
│  ├──────────────────────────────┤  │
│  │   Memory │ Services │ Tools  │  │  ← Core subsystems
│  ├──────────────────────────────┤  │
│  │  SOPs │ Knowledge │ Security │  │  ← Guidance systems
│  │  Workflow │ Resilience      │  │  ← Execution systems
│  └──────────────────────────────┘  │
├────────────────────────────────────┤
│       LLM Providers (OneLLM)       │  ← External integrations
└────────────────────────────────────┘
```

### Component Relationships

1. **Formation Engine**: The entry point that loads and validates YAML formations
   - Parses and validates formation.yaml against schemas
   - Initializes all runtime components (LLM, memory, agents, MCP)
   - Manages lifecycle (start, stop, reload)
   - Handles environment variable substitution
   - Provides OpenAPI-compliant REST API with standardized response envelopes

2. **Overlord Orchestrator**: Central intelligence that coordinates agents
   - Intent detection and agent routing with SOP guidance
   - SOP discovery and execution through semantic search
   - Multi-agent coordination for complex tasks
   - Memory context management across agents
   - Tool discovery and execution through MCP
   - Async/streaming response orchestration
   - Workflow decomposition with intelligent optimization
   - Unified clarification system for handling ambiguous requests

3. **Agent Pool**: Specialized agents with domain knowledge
   - Each agent has unique capabilities and specialties
   - Agents share memory through Overlord
   - Knowledge base per agent for domain expertise
   - Direct LLM access for task execution

4. **Memory Systems**: Three-tier architecture for context
   - Buffer Memory: FIFO + vector search for recent context
   - Persistent Memory: PostgreSQL/SQLite for long-term storage
   - Vector Memory: FAISSx integration for semantic search
   - Multi-user isolation with Memobase partitioning
   - Semantic deduplication: >90% similarity check before storing
   - Collection-based organization: preferences, user_identity, activities, etc.

5. **Service Layer**: Core runtime services
   - MCP Service: Tool integration via Model Context Protocol with agent isolation
   - Multimodal Service: Image/audio/video/document processing
   - A2A Service: Comprehensive internal/external agent communication with registry
   - Scheduler Service: Natural language task scheduling
   - Observability: Comprehensive event streaming

## Key Design Patterns

### Core Architectural Patterns

1. **Formation-First Architecture**
   ```yaml
   # Everything starts with a formation.yaml
   schema: "1.0.0"
   id: "my-ai-system"
   llm:
     models:
       - text: "openai/gpt-4o-mini"  # Required
   agents:
     - id: "assistant"
       name: "General Assistant"
   memory:
     buffer:
       size: 20
   ```

2. **Declarative Configuration**
   - YAML defines entire AI systems
   - Runtime handles all complexity
   - No orchestration code needed
   - Environment variable support for secrets

3. **Provider-Agnostic Design**
   - OneLLM abstracts LLM providers
   - Swap models without code changes
   - Unified interface across providers
   - Multi-model support per formation

### Orchestration Patterns

1. **SOP-Enhanced Orchestration**
   ```python
   # Simplified SOP execution flow
   user_request → SOP search (FAISS) → Pass SOP to decomposer → Execute workflow
   ```
   - SOPs discovered through semantic similarity (via workflow.sops.SOPSystem)
   - Full SOP content passed to task decomposer
   - Decomposer handles parsing, optimization, execution
   - Mode-specific instructions (template vs guide)

2. **Intent-Based Routing**
   ```python
   class Overlord:
       async def chat(self, message: str, user_id: str):
           # 1. Detect intent
           intent = await self.intent_detector.analyze(message)

           # 2. Find relevant SOPs
           sops = await self.sop_coordinator.search(message)

           # 3. Select agent(s)
           if sops:
               agents = self.select_agents_for_sop(sops[0])
           else:
               agent = self.select_agent(intent)

           # 4. Execute with context
           context = await self.memory.get_context(user_id)
           response = await agent.process(message, context)
   ```

2. **SOP-Guided Decomposition**
   - Standard Operating Procedures guide complex tasks
   - Multi-step workflows with agent coordination
   - Procedural knowledge for consistency
   - YAML-defined procedures

3. **Streaming-First Responses**
   ```python
   async def chat(self, message: str, stream: bool = True):
       if stream:
           async for chunk in agent.stream_response(message):
               yield chunk
       else:
           return await agent.get_response(message)
   ```

### Memory Patterns

1. **Centralized Memory Management**
   - All memory owned by Overlord
   - Agents access through Overlord methods
   - Consistent state across agents
   - Multi-user isolation built-in

2. **Three-Tier Memory Architecture**
   ```python
   # Buffer Memory - Recent context
   buffer = WorkingMemory(size=20, vector_search=True)

   # Persistent Memory - Long-term storage with collections
   persistent = LongTermMemory("postgresql://...")
   # Collections: preferences, user_identity, activities, goals, etc.

   # Vector Memory - Semantic search with deduplication
   vector = VectorMemory(embedding_model="openai/text-embedding-3-small")
   ```

3. **Memobase Partitioning**
   - User isolation through partitioning
   - Shared knowledge with access control
   - Efficient multi-tenant support
   - Session-based context management

4. **Semantic Deduplication** (Added August 2025)
   ```python
   # Prevent duplicate memories using embeddings
   async def store_memory(self, content, collection):
       # Check for similar existing memories
       existing = await self.search(content, limit=1, collection=collection)
       if existing and existing[0]["distance"] < 0.1:  # >90% similar
           return  # Skip duplicate
       
       # Store new memory
       await self.add(content, collection=collection)
   ```

### Service Integration Patterns

1. **MCP Protocol Implementation with Agent Isolation**
   ```python
   # Agent-aware tool access with isolation
   class MCPService:
       def __init__(self):
           self.tool_registry = {}  # Global registry (legacy)
           self.agent_tool_registry = {"_shared": {}}  # New agent-isolated registry
           
       def get_tool_registry(self, agent_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
           """Get tools available to specific agent or global registry."""
           if agent_id is None:
               return self.tool_registry
           # Combine shared tools with agent-specific tools
           result = dict(self.agent_tool_registry.get("_shared", {}))
           if agent_id in self.agent_tool_registry:
               result.update(self.agent_tool_registry[agent_id])
           return result
           
       async def execute_tool(self, server_id: str, tool: str, args: dict, agent_id: str = None):
           # Verify agent has access to this tool
           available_tools = self.get_tool_registry(agent_id)
           if server_id not in available_tools:
               raise PermissionError(f"Agent {agent_id} does not have access to server {server_id}")
           transport = self.get_transport(server_id)
           return await transport.execute(tool, args)
   ```

2. **Transport Abstraction**
   - Command transport for local tools
   - HTTP/SSE for remote services
   - Streamable transport for real-time
   - Consistent interface across types

3. **Built-in MCP Servers**
   - File Generation (Artifacts System)
   - Secure sandboxed Python execution
   - Chart/document/code generation
   - Session-based artifact tracking

### SOP System Patterns

1. **Simplified Architecture**
   ```python
   # Old approach: Manual parsing, step extraction, directive parsing
   # New approach: Direct pass to decomposer
   # Note: SOPSystem now lives in workflow module, not overlord
   class SOPSystem:
       async def execute_sop(self, sop_content: str, mode: str):
           # Add mode-specific instructions
           if mode == "template":
               prompt = "Follow this SOP EXACTLY. Do not skip steps."
           else:  # guide mode
               prompt = "Use this SOP as guidance while optimizing."
           
           # Pass directly to decomposer - it handles everything
           workflow = await self.task_decomposer.decompose(
               user_request + "\n\n" + prompt + "\n\n" + sop_content
           )
           return await self.workflow_executor.execute(workflow)
   ```

2. **Semantic Discovery**
   ```python
   # FAISS-based SOP matching
   class SOPDiscovery:
       def __init__(self):
           self.index = FAISSIndex()  # Semantic search
           self.sops = {}  # SOP storage
       
       async def find_relevant_sops(self, user_request: str):
           # Semantic similarity search
           embedding = await self.embed(user_request)
           matches = self.index.search(embedding, k=5)
           return [self.sops[id] for id, score in matches if score > 0.7]
   ```

3. **Mode-Based Execution**
   - **Template Mode**: Strict adherence, no optimization
   - **Guide Mode**: Flexible interpretation, automatic optimization
   - **Bypass Approval**: Skip workflow approval for routine SOPs
   - **Critical Marking**: Preserve essential steps even in guide mode

4. **Performance Optimization**
   ```python
   # Before: 104 seconds for 3-step SOP (each step = LLM call)
   # After: 10 seconds (1 decomposition + optimized execution)
   
   # Why it's faster:
   # 1. Single decomposition call vs N step calls
   # 2. Trivial operations combined with complex tasks
   # 3. Parallel execution in guide mode
   # 4. No parsing overhead - decomposer handles it
   ```

### Security Patterns

1. **Credential Isolation**
   ```python
   # Per-user credential management
   class UserCredentialStore:
       def get_credentials(self, user_id: str, service: str):
           # Encrypted, isolated credentials
           return self.decrypt(self.store[user_id][service])
   ```

2. **Sandboxed Execution**
   - File generation in isolated environments
   - Resource limits for safety
   - No network access in sandbox
   - Temporary file cleanup

3. **Role-Based Access Control**
   - Agent-level permissions
   - User-level data isolation
   - Service-level access control
   - Audit logging for compliance

4. **Parameter Validation** (Added August 4, 2025)
   ```python
   # Validate parameters against tool schemas before execution
   def _validate_tool_parameters(self, parameters, tool_schema, tool_name):
       # Check required parameters
       for req_param in tool_schema.get("required", []):
           if req_param not in parameters:
               return False, f"Missing required parameter: {req_param}"
       
       # Validate types, enums, min/max values
       for param_name, param_value in parameters.items():
           param_def = tool_schema["properties"].get(param_name, {})
           # Type validation, enum validation, range validation
           ...
       return True, None
   ```

## Implementation Patterns

### Async-First Design

```python
# Everything is async for performance
class Formation:
    async def load(self, path: str):
        # Async file I/O
        config = await self.read_yaml(path)

        # Parallel initialization
        await asyncio.gather(
            self.init_llm(config.llm),
            self.init_memory(config.memory),
            self.init_agents(config.agents)
        )
```

### Approval-Aware Async Execution

```python
# New pattern: Async decisions respect approval requirements
class ChatOrchestrator:
    async def _determine_async_mode(self, message, agent_name, use_async, threshold):
        # Explicit override takes precedence
        if use_async is not None:
            return use_async
            
        # Check if approval needed - force sync if so
        if await self.overlord.would_need_workflow_approval(message, agent_name):
            return False  # Stay synchronous for interactive approval
            
        # Normal async decision based on time estimation
        return await self._estimate_time(message) > threshold
```

### Error Handling Philosophy

```python
# Fail fast for critical config
if not config.llm.models.get("text"):
    raise ConfigurationValidationError("Missing required text model")

# Log and continue for optional features
try:
    await self.init_optional_feature()
except Exception as e:
    logger.warning(f"Optional feature failed: {e}")
    # Continue without feature
```

### Resource Management

```python
# Context managers for cleanup
class MCPTransport:
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.cleanup()
```

### Memory Management Patterns (Enhanced August 4, 2025)

```python
# Bounded collections for preventing memory leaks
from collections import deque

class Agent:
    def __init__(self):
        # Use deque with maxlen for automatic FIFO eviction
        self._a2a_history = deque(maxlen=20)  # Automatically maintains size
        # No manual cleanup needed - oldest entries auto-removed
```

### Caching Strategies

1. **Knowledge Base Caching**
   - MD5 hash-based content detection
   - Only regenerate embeddings on changes
   - 45% cache hit rate in production
   - Significant cost reduction

2. **LLM Response Caching**
   - Optional response caching
   - Key-based on input hash
   - TTL-based expiration
   - User-specific cache isolation

## Performance Patterns

### Optimization Strategies

1. **Lazy Loading**
   ```python
   # Only load agents when needed
   class AgentRegistry:
       def __init__(self):
           self._agents = {}  # Empty initially

       async def get_agent(self, agent_id: str):
           if agent_id not in self._agents:
               self._agents[agent_id] = await self.load_agent(agent_id)
           return self._agents[agent_id]
   ```

2. **Connection Pooling**
   - Database connection pools
   - HTTP connection reuse
   - MCP server connection caching
   - Efficient resource utilization

3. **Batch Processing**
   - Batch embedding generation
   - Bulk database operations
   - Grouped API calls
   - Reduced overhead

### Monitoring Patterns

1. **Event Streaming**
   ```python
   # Comprehensive observability
   class EventStream:
       def __init__(self, formatters: List[Formatter]):
           self.formatters = formatters

       async def emit(self, event: Event):
           for formatter in self.formatters:
               await formatter.format_and_send(event)
   ```

2. **Metrics Collection**
   - Response time tracking
   - Memory usage monitoring
   - Token consumption metrics
   - Error rate tracking

## Testing Patterns

### Real Services Only

```python
# No mocks - test against real services
async def test_openai_integration():
    formation = Formation()
    await formation.load("test-formation.yaml")

    # Real API call
    response = await overlord.chat("Hello", user_id="test")
    assert response  # Real response from OpenAI
```

### Formation-Based Testing

```python
# Test entire systems via formations
async def test_multi_agent_system():
    # Load complete formation
    formation = await Formation.from_file("multi-agent.yaml")
    overlord = await formation.start_overlord()

    # Test orchestration
    response = await overlord.chat("Complex task")
    # Verify agent coordination worked
```

---
created: 2025-08-21T17:31:00Z
last_updated: 2025-08-28T21:12:39Z
version: 1.2
author: Claude Code PM System
---

## Credential Handling Patterns (August 2025 - Issue #53)

### Early Interception Architecture

Credential requests are intercepted BEFORE clarification to prevent confusion:

```python
# In overlord._process_sync_chat()
# After formatting message with context
credential_detection = await self._detect_credential_need(message, user_id)

if credential_detection:
    # Handle based on detection type
    if credential_detection["type"] == "CREDENTIAL_REQUEST":
        return await self._handle_credential_request(...)
    elif credential_detection["type"] == "SERVICE_USE":
        if credential_detection["needs_credentials"]:
            return await self._handle_credential_request(...)

# Only then check for clarification
if await self.clarification.has_active_clarification(request_id):
    ...
```

### MCP Server Registry Pattern

Registry built during formation initialization:

```python
# In formation._register_mcp_servers()
self._mcp_servers_with_user_credentials = {}

for server_config in self._mcp_servers:
    if contains_user_credentials(auth):
        self._mcp_servers_with_user_credentials[server_id] = {
            "service": service_name,
            "server_id": server_id,
            "accept_inline": auth.get("accept_inline", False),
            "auth_type": auth.get("type", "bearer"),
            "uses_user_credentials": True
        }

# Pass to overlord via configured_services
self._configured_services["mcp_servers_with_user_credentials"] = self._mcp_servers_with_user_credentials
```

### LLM-Based Detection Pattern

Replace pattern matching with intelligent detection:

```python
async def _detect_credential_need(self, message: str, user_id: str) -> Optional[Dict]:
    # Get available services from registry
    for server_id, info in self._mcp_servers_with_user_credentials.items():
        available_services.append(info["service"])
    
    # Use LLM to detect intent
    prompt = f"""Analyze if this message relates to any credential service.
    Available services: {available_services}
    Message: {message}
    
    Respond with: SERVICE_USE:<service>, CREDENTIAL_REQUEST:<service>, or NONE
    """
    
    # Return detection with type and service info
    return {
        "type": "SERVICE_USE|CREDENTIAL_REQUEST|NONE",
        "service": service_name,
        "server_id": server_id,
        "has_credentials": bool,
        "accept_inline": bool
    }
```

### Module Organization Pattern

Dedicated credential module for separation of concerns:

```
src/muxi/formation/credentials/
├── __init__.py           # Module exports
├── resolver.py           # Base credential resolver
├── encrypted.py          # Encrypted credential resolver
└── exceptions.py         # Credential-specific exceptions
```

## Clarification System Patterns (August 2025)

### Unified Clarification Architecture

The clarification system underwent a revolutionary consolidation from 15+ separate components to a single unified class, achieving 85% code reduction while adding powerful new features:

```python
# Single unified entry point replacing 15+ legacy components
class UnifiedClarificationSystem:
    def __init__(self, overlord):
        self.overlord = overlord
        self.buffer_memory = overlord.buffer_memory  # State storage
        self.llm = overlord.default_llm_model       # LLM for all decisions
        self.active_requests = set()                # Track active clarifications
        
    async def needs_clarification(self, message: str, request_id: str, 
                                 session_id: str, context: dict) -> ClarificationResult:
        """Main entry point - determines if clarification is needed."""
        # Check for existing clarification
        if await self.has_active_clarification(request_id):
            return await self.handle_response(request_id, message)
        
        # Analyze new request via LLM (no pattern matching!)
        analysis = await self._analyze_request(message, context)
        
        if analysis["needs_clarification"]:
            await self._create_state(request_id, message, analysis["mode"], session_id)
            return ClarificationResult(action="clarify", question=analysis["question"])
        
        return ClarificationResult(action="execute", request=message)
```

### Credential Handling Integration (Issue #47 - August 2025)

The clarification system now integrates with credential management:

```python
# Enhanced clarification prompt includes credential detection
CREDENTIAL_HANDLING_RULES = '''
If user is asking to ADD NEW CREDENTIALS/API keys/accounts:
  - In redirect mode: Set action="message" with redirect message
  - In dynamic mode: Collect credentials through clarification dialog
'''

# Support for message action in clarification results
if result.action == "message":
    # Return message directly without agent processing
    return SyncChatResponse(
        content=result.question,
        metadata={"clarification": "redirect"}
    )
```

**Key Features**:
- **LLM-based detection**: No pattern matching, works in any language
- **Mode-specific behavior**: Redirect vs dynamic credential collection
- **Security-first**: No inline credential prompting in redirect mode
- **Simplified architecture**: Removed session-based request_id override

### Five Specialized Clarification Modes

Each mode has different maximum depths and specialized request enhancement:

```python
# Mode-specific configurations and behaviors
CLARIFICATION_MODES = {
    "direct": {
        "max_depth": 3,
        "purpose": "Quick clarification of simple ambiguities",
        "use_cases": ["file operations", "basic commands", "simple queries"]
    },
    "brainstorm": {
        "max_depth": 10, 
        "purpose": "Creative exploration and idea development",
        "use_cases": ["design discussions", "feature planning", "creative projects"]
    },
    "planning": {
        "max_depth": 7,
        "purpose": "Structured project planning and requirements",
        "use_cases": ["project setup", "architecture decisions", "complex implementations"]
    },
    "credential": {
        "max_depth": 1,
        "purpose": "Credential and account selection",
        "use_cases": ["API authentication", "service selection", "account disambiguation"]
    },
    "execution": {
        "max_depth": 2,
        "purpose": "Clarifying execution details and parameters", 
        "use_cases": ["command parameters", "output formats", "execution options"]
    }
}
```

### Buffer Memory State Management

Unlike the old session-based approach, the unified system uses request_id for state management:

```python
# Request ID vs Session ID usage pattern
async def _create_state(self, request_id: str, message: str, mode: str, session_id: str):
    """Create clarification state with proper ID usage."""
    state = {
        "request_id": request_id,     # PRIMARY KEY for state management
        "session_id": session_id,     # For analytics/grouping only
        "original_request": message,
        "mode": mode,
        "depth": 0,
        "max_depth": self._get_max_depth(mode),
        "collected_info": [],
        "started_at": time.time()
    }
    
    # Store using request_id as key
    key = f"clarification:{request_id}"
    await self.buffer_memory.set(key, state, ttl=300)  # 5-minute TTL
    self.active_requests.add(request_id)
```

### Multi-Turn Clarification Support (November 2025)

The system now fully supports multi-turn clarification through proper request flow:

```python
# Overlord no longer bypasses clarification for responses
async def _process_sync_chat(self, message, request_id, session_id, ...):
    # ALWAYS check clarification - no special cases for responses
    if not skip_clarification and not agent_name and self.clarification:
        result = await self.clarification.needs_clarification(
            message=message,
            request_id=request_id,  # Same ID throughout entire interaction
            session_id=session_id,
            context={"user_id": user_id}
        )
        
        if result.action == "clarify":
            # Store minimal state for request_id reuse
            self._pending_clarifications[session_id] = {
                "request_id": request_id,
                "type": result.mode
            }
            return MuxiResponse(content=result.question, ...)
            
        elif result.action == "execute":
            # Clean up and use enhanced request
            if session_id in self._pending_clarifications:
                del self._pending_clarifications[session_id]
            message = result.request  # Use enhanced request
```

**ID Hierarchy for Multi-Turn Support**:
- **request_id**: Tracks ONE complete interaction (initial request + all clarification turns)
- **session_id**: Groups multiple requests, enables request_id reuse for clarification continuity
- **user_id**: Provides user isolation in multi-user mode

### Context Switch Detection

New intelligent feature that detects when users change topics mid-clarification:

```python
async def _detect_context_switch(self, state: dict, message: str) -> bool:
    """Detect if user switched to unrelated topic using LLM."""
    prompt = f"""
    Original request: {state['original_request']}
    Current clarification mode: {state['mode']}
    User response: {message}
    
    Is this response related to the original request? Answer with:
    - "answering" if responding to clarification
    - "different" if switching to unrelated topic
    """
    
    response = await self.llm.chat([{"role": "user", "content": prompt}])
    return response.content.strip().lower() == "different"

# Usage in handle_response
if await self._detect_context_switch(state, message):
    # User switched topics - cancel clarification and process new request
    await self._cleanup_state(request_id)
    return ClarificationResult(
        action="execute",
        request=message,  # Process the new request
        context={"clarification_cancelled": True, "reason": "context_switch"}
    )
```

### LLM-First Decision Making

All decisions are made via LLM calls, no pattern matching for true multilingual support:

```python
# Old approach: Regex patterns and hardcoded logic
if re.match(r'^(help|assist)', message, re.IGNORECASE):
    # Only works in English
    
# New approach: LLM-based understanding
async def _analyze_request(self, message: str, context: dict) -> dict:
    """Use LLM to determine if clarification is needed."""
    prompt = f"""
    Analyze this request to determine if clarification is needed.
    
    Request: {message}
    Context: {context}
    
    Return JSON:
    {{
        "needs_clarification": boolean,
        "reason": "clear|ambiguous|incomplete|planning_needed|execution_details",
        "mode": "direct|brainstorm|planning|credential|execution",
        "question": "clarifying question if needed",
        "confidence": 0.0-1.0
    }}
    """
    
    response = await self.llm.chat([{"role": "user", "content": prompt}])
    return json.loads(response.content)
```

### Circuit Breaker and Safety Patterns

Multiple safety mechanisms prevent infinite loops and resource exhaustion:

```python
async def _check_circuit_breaker(self, state: dict) -> Optional[ClarificationResult]:
    """Prevent infinite clarification loops."""
    if state["depth"] >= state["max_depth"]:
        # Force completion with collected info
        enhanced_request = self._build_enhanced_request(state)
        await self._cleanup_state(state["request_id"])
        
        return ClarificationResult(
            action="execute",
            request=enhanced_request,
            context={"max_depth_reached": True}
        )
    return None

async def _check_timeout(self, state: dict) -> Optional[ClarificationResult]:
    """Handle clarification timeouts."""
    elapsed = time.time() - state["started_at"]
    if elapsed > self.timeout:  # 5 minutes default
        enhanced_request = self._build_enhanced_request(state)
        await self._cleanup_state(state["request_id"])
        
        return ClarificationResult(
            action="execute", 
            request=enhanced_request,
            context={"timeout": True}
        )
    return None
```

## Advanced Patterns (Day 7B)

### Generic Parameter Inference (Added August 4, 2025)

```python
# LLM-based parameter inference for ANY tool
async def _infer_tool_parameters(self, tool_name, required_params, 
                                 param_properties, action_description, user_request):
    # Build prompt with parameter schema
    prompt = f"""Based on the user's request and tool requirements, 
    determine the appropriate parameter values.
    
    User Request: {user_request}
    Tool Name: {tool_name}
    Required Parameters:
    """
    
    for param in required_params:
        param_def = param_properties.get(param, {})
        prompt += f"""
        - {param}:
          Type: {param_def.get('type')}
          Description: {param_def.get('description')}
          Enum values: {param_def.get('enum', [])}
        """
    
    # Use LLM to infer parameters
    response = await self.model.chat([{"role": "user", "content": prompt}])
    parameters = json.loads(response)
    
    # No hardcoded tool-specific logic!
    return parameters
```

## Advanced Patterns (Day 7B)

### Comprehensive A2A Communication System

#### Internal A2A Communication (Same Formation)
```python
# Internal agent-to-agent communication with tool isolation
class InternalA2AService:
    def __init__(self, overlord):
        self.overlord = overlord
        self.agent_tool_registry = {"_shared": {}}  # Agent-specific tool isolation
        
    async def handle_internal_request(self, message: str, requesting_agent_id: str, target_agent_id: str):
        # Verify target agent exists in same formation
        if target_agent_id not in self.overlord.agents:
            raise ValueError(f"Target agent {target_agent_id} not found in formation")
        
        # Check tool requirements and agent capabilities
        required_tools = await self.analyze_tool_requirements(message)
        target_agent_tools = self.get_agent_tools(target_agent_id)
        
        if all(tool in target_agent_tools for tool in required_tools):
            # Direct communication within formation
            return await self.route_to_internal_agent(message, target_agent_id)
        else:
            # Tool collaboration needed
            return await self.coordinate_tool_access(message, requesting_agent_id, target_agent_id)
```

#### External A2A Communication (Cross-Formation)
```python
# External agent-to-agent communication with registry
class ExternalA2AService:
    def __init__(self, registry_client, auth_config):
        self.registry = registry_client
        self.auth = auth_config
        
    async def discover_external_agent(self, service_id: str, capability: str = None):
        """Discover agents in other formations with service ID precedence."""
        # Try exact service_id match first
        agents = await self.registry.discover_agents(service_id=service_id)
        
        if not agents:
            # Fallback to formation_id matching
            agents = await self.registry.discover_agents(formation_id=service_id)
        
        # Filter by capability if specified
        if capability:
            agents = [a for a in agents if capability in a.get('capabilities', [])]
            
        return agents
        
    async def send_external_message(self, target_url: str, message: str, auth_token: str):
        """Send message to external agent with authentication."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{target_url}/a2a/message",
                json={"message": message, "sender": self.formation_id},
                headers=headers
            )
            return response.json()
```

#### Registry-Based Discovery
```python
# Agent registration and discovery system
class A2ARegistry:
    def __init__(self, registry_url: str, auth_config: dict):
        self.registry_url = registry_url
        self.auth_config = auth_config
        
    async def register_formation(self, formation_id: str, service_id: str, agents: List[dict]):
        """Register formation and its agents with the registry."""
        registration_data = {
            "formation_id": formation_id,
            "service_id": service_id,  # For service ID precedence matching
            "agents": agents,
            "auth": self.auth_config,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.registry_url}/register",
                json=registration_data,
                headers=self._get_auth_headers()
            )
            return response.json()
            
    async def discover_agents(self, service_id: str = None, formation_id: str = None, 
                            capability: str = None):
        """Discover agents with service ID precedence."""
        params = {}
        if service_id:
            params["service_id"] = service_id
        if formation_id:
            params["formation_id"] = formation_id  
        if capability:
            params["capability"] = capability
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.registry_url}/discover",
                params=params,
                headers=self._get_auth_headers()
            )
            return response.json()
```

#### Enhanced Authentication Patterns
```python
# Standardized authentication for A2A communications
class A2AAuthHandler:
    def __init__(self, formation_config: dict):
        self.auth_config = formation_config.get("a2a", {}).get("auth", {})
        
    def get_auth_headers(self) -> dict:
        """Generate authentication headers based on auth.type configuration."""
        auth_type = self.auth_config.get("type", "bearer")
        auth_token = self.auth_config.get("token")
        
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {auth_token}"}
        elif auth_type == "api_key":
            return {"X-API-Key": auth_token}
        elif auth_type == "basic":
            # For basic auth, token should be base64 encoded username:password
            return {"Authorization": f"Basic {auth_token}"}
        else:
            raise ValueError(f"Unsupported auth type: {auth_type}")
            
    def validate_incoming_auth(self, headers: dict) -> bool:
        """Validate incoming authentication based on configuration."""
        expected_headers = self.get_auth_headers()
        
        for header, expected_value in expected_headers.items():
            if headers.get(header) != expected_value:
                return False
        return True

# Migration helper for legacy configurations
class AuthConfigMigrator:
    @staticmethod
    def migrate_legacy_config(old_config: dict) -> dict:
        """Migrate from mode/shared_key to auth.type/auth.token format."""
        if "mode" in old_config and "shared_key" in old_config:
            return {
                "type": old_config["mode"],  # "bearer", "api_key", etc.
                "token": old_config["shared_key"]
            }
        return old_config
```

### Configuration Validation Patterns

```python
# Fixed pattern: Validation without modifying global config
def validate_user_credentials_requirements(config: Dict[str, Any]) -> None:
    # Get MCP servers for validation
    mcp_config = config.get("mcp", {})
    servers = list(mcp_config.get("servers", []))  # Create copy for validation
    
    # Add agent-specific servers to validation copy only
    agents = config.get("agents", [])
    for agent in agents:
        if isinstance(agent, dict) and "mcp_servers" in agent:
            agent_servers = agent["mcp_servers"]
            if isinstance(agent_servers, list):
                servers.extend(agent_servers)  # Only extend validation copy
    
    # Validate credentials without modifying global config
    validate_credentials_in_servers(servers)
```

### Error Handling Patterns (Enhanced August 4, 2025)

```python
# No more silent failures - explicit error handling
try:
    with open(template_path, "r") as f:
        planning_prompt += f.read()
except FileNotFoundError as e:
    # Log error with full context
    observability.observe(
        event_type=observability.ErrorEvents.INTERNAL_ERROR,
        level=observability.EventLevel.ERROR,
        data={"template_path": str(template_path), "error": str(e)},
        description=f"Planning template file not found: {template_path}"
    )
    # Raise with clear message
    raise FileNotFoundError(
        f"Required planning template file is missing: {template_path}. "
        "This file is essential for the planning system to function properly."
    ) from e
```

## Code Quality Patterns (December 2025)

### Dead Code Prevention
- **Regular Audits**: Systematic scans for unused classes and functions
- **AST-Based Detection**: Using Python AST parsing to identify all class definitions
- **Usage Verification**: Grep-based search to verify actual usage vs just imports
- **Clean Removal**: Complete removal of abandoned features rather than leaving dead code

### Lean Architecture Principles
- **Single Responsibility**: One class per concept (e.g., LLMCircuitBreaker not MultiLLMCircuitBreaker)
- **Minimal Dataclasses**: Only essential data structures (removed 4 unused clarification dataclasses)
- **Feature Completion**: Either fully implement or fully remove - no half-built features
- **Clear Boundaries**: Services stay focused on their core purpose

### Code Maintenance Strategy
- **Immediate Cleanup**: Remove code as soon as it becomes unused
- **No Speculative Features**: Don't build for hypothetical future needs
- **Simplicity First**: Prefer simple solutions over complex architectures
- **Documentation Accuracy**: Keep docs aligned with actual implementation

## Future Patterns

### Planned Enhancements

1. **Cross-Formation A2A Communication**
   - External agent discovery
   - Secure inter-formation protocols
   - Network-based agent collaboration
   - Distributed tool access

2. **Advanced Tool Isolation**
   - Fine-grained permission systems
   - Role-based tool access
   - Dynamic tool provisioning
   - Audit trails for tool usage

3. **Enhanced Orchestration**
   - Multi-clarification sequences
   - Thinking visibility modes
   - Large file chunking
   - Parallel agent execution

4. **Distributed Runtime**
   - Agent distribution across nodes
   - Shared memory via distributed cache
   - Load balancing for scale
   - Fault tolerance

This architecture provides a solid foundation for building production AI agent systems with true agent-to-agent communication capabilities, perfect tool isolation, and enterprise-grade security, while maintaining flexibility for future distributed enhancements.
