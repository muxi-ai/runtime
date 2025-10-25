# API Endpoints - Implementation TODO

**Created:** October 25, 2025  
**Status:** 14 endpoints need implementation  
**Spec Reference:** `schemas/api/formation-api-v1-final.yaml`  

---

## Overview

All backend functionality exists and works. These endpoints just need to be wired up to expose existing functionality via the REST API.

**Implementation Pattern:**
1. Backend logic ✅ EXISTS
2. API endpoint ❌ NOT WIRED UP
3. OpenAPI spec ✅ COMPLETE

---

## 1. Job/Async Management (5 endpoints) - MEDIUM PRIORITY

### 1.1 List User Jobs
**Endpoint:** `GET /v1/jobs/{user_id}`  
**File:** `src/muxi/formation/server/routes/client/jobs.py:18`  
**Auth:** Client API Key  
**Status:** Returns empty list, needs implementation

**Backend Exists:**
```python
# Available in overlord:
overlord.request_tracker.get_all_requests(user_id)
# Returns: Dict[request_id, RequestState]
```

**What to Implement:**
```python
@router.get("/jobs/{user_id}", response_model=APIResponse)
async def list_user_jobs(request: Request, user_id: str) -> JSONResponse:
    formation = request.app.state.formation
    overlord = formation.overlord
    
    # Get all requests for this user from request tracker
    user_requests = await overlord.request_tracker.get_all_requests(user_id)
    
    # Convert RequestState objects to API response format
    jobs = []
    for request_id, state in user_requests.items():
        jobs.append({
            "id": request_id,
            "status": state.status.value,  # pending, processing, completed, failed, cancelled
            "progress": state.progress,
            "created_at": state.created_at,
            "completed_at": state.completed_at,
            "error": state.error,
        })
    
    response = job_list_response(jobs, request_id, use_generic_type=True)
    return JSONResponse(content=response.model_dump(), status_code=200)
```

**Effort:** 1 hour  
**Spec Location:** Line 1510-1553

---

### 1.2 Cancel User Job
**Endpoint:** `DELETE /v1/jobs/{user_id}/{job_id}`  
**File:** `src/muxi/formation/server/routes/client/jobs.py:44`  
**Auth:** Client API Key  
**Status:** Returns 501 Not Implemented

**Backend Exists:**
```python
# Available in overlord:
result = await overlord.cancel_request(request_id)
# Returns: {"success": bool, "message": str}
```

**What to Implement:**
```python
@router.delete("/jobs/{user_id}/{job_id}", response_model=APIResponse)
async def cancel_job(request: Request, user_id: str, job_id: str) -> JSONResponse:
    formation = request.app.state.formation
    overlord = formation.overlord
    request_id = getattr(request.state, "request_id", None)
    
    # Verify job belongs to user (security check)
    job_state = await overlord.request_tracker.get_request(job_id)
    if not job_state:
        response = create_error_response("NOT_FOUND", f"Job {job_id} not found", None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=404)
    
    if job_state.user_id != user_id:
        response = create_error_response("FORBIDDEN", "Job does not belong to this user", None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=403)
    
    # Cancel the job
    result = await overlord.cancel_request(job_id)
    
    if result["success"]:
        response = create_success_response(result, request_id)
        return JSONResponse(content=response.model_dump(), status_code=200)
    else:
        response = create_error_response("OPERATION_FAILED", result["message"], None, request_id)
        return JSONResponse(content=response.model_dump(), status_code=400)
```

**Effort:** 1 hour  
**Spec Location:** Line 1555-1607

---

### 1.3 List All Jobs (Admin)
**Endpoint:** `GET /v1/async/jobs`  
**File:** `src/muxi/formation/server/routes/admin/async_routes.py:95`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
all_requests = overlord.request_tracker._requests
# Dict[request_id, RequestState] for ALL users
```

**What to Implement:**
```python
@router.get("/async/jobs")
async def get_async_jobs(request: Request):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    # Get all active async jobs across all users
    jobs = []
    for request_id, state in overlord.request_tracker._requests.items():
        jobs.append({
            "request_id": request_id,
            "user_id": state.user_id,
            "status": state.status.value,
            "progress": state.progress,
            "created_at": state.created_at,
            "completed_at": state.completed_at,
        })
    
    return {"success": True, "data": {"jobs": jobs}}
```

**Effort:** 30 minutes  
**Spec Location:** Not in spec (admin convenience endpoint)

---

### 1.4 Get Job Details (Admin)
**Endpoint:** `GET /v1/async/jobs/{job_id}`  
**File:** `src/muxi/formation/server/routes/admin/async_routes.py:114`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
state = await overlord.request_tracker.get_request(job_id)
# Or from buffer memory:
status = await overlord.get_request_status(job_id)
```

**What to Implement:**
```python
@router.get("/async/jobs/{job_id}")
async def get_async_job(request: Request, job_id: str):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    # Get full job status including from buffer memory if completed
    status = await overlord.get_request_status(job_id)
    
    if "error" in status:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": status["error"]}}
    
    return {"success": True, "data": status}
```

**Effort:** 30 minutes  
**Spec Location:** Not in spec (admin convenience endpoint)

---

### 1.5 Cancel Job (Admin)
**Endpoint:** `DELETE /v1/async/jobs/{job_id}`  
**File:** `src/muxi/formation/server/routes/admin/async_routes.py:132`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
result = await overlord.cancel_request(job_id)
```

**What to Implement:**
```python
@router.delete("/async/jobs/{job_id}")
async def cancel_async_job(request: Request, job_id: str):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    result = await overlord.cancel_request(job_id)
    
    if result["success"]:
        return {"success": True, "data": result}
    else:
        return {"success": False, "error": {"code": "OPERATION_FAILED", "message": result["message"]}}
```

**Effort:** 30 minutes  
**Spec Location:** Not in spec (admin convenience endpoint)

---

## 2. Live Log Streaming (2 endpoints) - MEDIUM PRIORITY

### 2.1 Stream Logs (SSE)
**Endpoint:** `GET /v1/logs/stream`  
**File:** `src/muxi/formation/server/routes/admin/logs.py:112`  
**Auth:** Admin API Key  
**Status:** Returns "not implemented" error message

**Backend Exists:**
```python
# Observability system emits events throughout codebase
# Need to add subscription mechanism
```

**What to Implement:**
1. Add event subscription to observability manager
2. Wire up SSE streaming in endpoint
3. Apply filters (user_id, session_id, level, event_type)

**Implementation Steps:**

**Step 1:** Add subscription to observability manager
```python
# In src/muxi/services/observability/manager.py

class ObservabilityManager:
    def __init__(self):
        self._subscribers = []  # Add subscriber list
        
    async def subscribe(self, filters: Dict[str, Any]) -> AsyncGenerator:
        """Subscribe to filtered event stream."""
        queue = asyncio.Queue(maxsize=1000)  # Buffered event queue
        self._subscribers.append((queue, filters))
        
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Cleanup on disconnect
            self._subscribers.remove((queue, filters))
    
    def emit_event(self, event: Event):
        """Emit event to all subscribers (in addition to formatters)."""
        # Existing formatter logic...
        
        # NEW: Also send to subscribers
        for queue, filters in self._subscribers:
            if self._matches_filters(event, filters):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop events if subscriber is slow
                    pass
```

**Step 2:** Update endpoint
```python
# In src/muxi/formation/server/routes/admin/logs.py

async def event_generator():
    """Generate Server-Sent Events from observability logs."""
    formation = request.app.state.formation
    observability_manager = formation.overlord.observability_manager
    
    try:
        # Subscribe to filtered event stream
        async for event in observability_manager.subscribe(active_filters):
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            # Format as SSE
            event_data = {
                "timestamp": event.timestamp,
                "level": event.level.value if hasattr(event.level, 'value') else str(event.level),
                "event_type": event.event_type,
                "user_id": event.context.get("user_id"),
                "session_id": event.context.get("session_id"),
                "request_id": event.context.get("request_id"),
                "agent_id": event.context.get("agent_id"),
                "message": event.description,
                "data": event.data,
            }
            
            yield "event: log\n"
            yield f"data: {json.dumps(event_data)}\n\n"
            
    except asyncio.CancelledError:
        # Client disconnected
        pass
    except Exception as e:
        # Error occurred
        error_data = {"error": True, "message": str(e)}
        yield "event: error\n"
        yield f"data: {json.dumps(error_data)}\n\n"
```

**Effort:** 4-6 hours (needs observability manager changes)  
**Spec Location:** Line 3850-3940

---

### 2.2 Event Streaming for Users
**Endpoint:** `GET /v1/events/stream`  
**File:** `src/muxi/formation/server/routes/client/events.py:30`  
**Auth:** Client API Key  
**Status:** TODO comment

**Backend Exists:**
Same observability system as admin logs, just filtered to user's events

**What to Implement:**
Similar to admin log streaming but:
- Auto-filter to `user_id` from authentication context
- Only expose user-facing events (not system internals)
- Simpler event format

```python
@router.get("/events/stream")
async def stream_user_events(request: Request):
    # Extract user_id from auth context
    user_id = getattr(request.state, "user_id", None)
    
    # Same subscription mechanism as logs but filtered to user
    async def event_generator():
        formation = request.app.state.formation
        observability_manager = formation.overlord.observability_manager
        
        # Subscribe with user_id filter
        filters = {"user_id": user_id}
        
        async for event in observability_manager.subscribe(filters):
            if await request.is_disconnected():
                break
            
            # Only send user-facing events
            if event.event_type.startswith(("chat.", "agent.", "workflow.")):
                event_data = {
                    "timestamp": event.timestamp,
                    "type": event.event_type,
                    "message": event.description,
                }
                yield "event: notification\n"
                yield f"data: {json.dumps(event_data)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Effort:** 2 hours (after log streaming is done)  
**Spec Location:** Not in spec (user convenience endpoint)

---

## 3. Memory Management (5 endpoints) - LOW PRIORITY

### 3.1 List User Memories
**Endpoint:** `GET /v1/memory`  
**File:** `src/muxi/formation/server/routes/client/memory.py:58`  
**Auth:** Client API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
memories = await overlord.long_term_memory.search(
    query="",  # Empty query returns all
    user_id=user_id,
    limit=1000
)
```

**What to Implement:**
```python
@router.get("/memory")
async def get_memories(
    request: Request,
    collection: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    formation = request.app.state.formation
    overlord = formation.overlord
    user_id = getattr(request.state, "user_id", None)
    
    if not overlord.long_term_memory:
        return {"success": False, "error": {"code": "NOT_CONFIGURED", "message": "Memory not enabled"}}
    
    # Get memories with optional collection filter
    memories = await overlord.long_term_memory.get_recent_memories(
        user_id=user_id,
        collection=collection,
        limit=limit,
        offset=offset
    )
    
    # Format for API
    memory_list = [
        {
            "id": mem.get("id"),
            "collection": mem.get("collection"),
            "text": mem.get("text"),
            "created_at": mem.get("created_at"),
            "metadata": mem.get("metadata", {})
        }
        for mem in memories
    ]
    
    return {"success": True, "data": {"memories": memory_list, "count": len(memory_list)}}
```

**Effort:** 1 hour  
**Spec Location:** Line 2300-2363

---

### 3.2 Create User Memory
**Endpoint:** `POST /v1/memory`  
**File:** `src/muxi/formation/server/routes/client/memory.py:85`  
**Auth:** Client API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
await overlord.long_term_memory.add(
    text=text,
    user_id=user_id,
    collection=collection,
    metadata=metadata
)
```

**What to Implement:**
```python
@router.post("/memory")
async def create_memory(
    request: Request,
    body: Dict[str, Any]  # {"text": str, "collection": str, "metadata": dict}
):
    formation = request.app.state.formation
    overlord = formation.overlord
    user_id = getattr(request.state, "user_id", None)
    
    if not overlord.long_term_memory:
        return {"success": False, "error": {"code": "NOT_CONFIGURED", "message": "Memory not enabled"}}
    
    # Validate required fields
    text = body.get("text")
    if not text:
        return {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "text is required"}}
    
    collection = body.get("collection", "user_notes")
    metadata = body.get("metadata", {})
    
    # Add to memory
    memory_id = await overlord.long_term_memory.add(
        text=text,
        user_id=user_id,
        collection=collection,
        metadata=metadata
    )
    
    return {
        "success": True,
        "data": {
            "id": memory_id,
            "text": text,
            "collection": collection,
            "created_at": datetime.utcnow().isoformat()
        }
    }
```

**Effort:** 1 hour  
**Spec Location:** Line 2300-2363

---

### 3.3 Delete User Memory
**Endpoint:** `DELETE /v1/memory/{item}`  
**File:** `src/muxi/formation/server/routes/client/memory.py:114`  
**Auth:** Client API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
await overlord.long_term_memory.delete(
    memory_id=item,
    user_id=user_id
)
```

**What to Implement:**
```python
@router.delete("/memory/{item}")
async def delete_memory(request: Request, item: str):
    formation = request.app.state.formation
    overlord = formation.overlord
    user_id = getattr(request.state, "user_id", None)
    
    if not overlord.long_term_memory:
        return {"success": False, "error": {"code": "NOT_CONFIGURED", "message": "Memory not enabled"}}
    
    # Delete memory (with user_id check for security)
    success = await overlord.long_term_memory.delete(
        memory_id=item,
        user_id=user_id  # Ensures users can only delete their own memories
    )
    
    if success:
        return {"success": True, "data": {"deleted": item}}
    else:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Memory {item} not found"}}
```

**Effort:** 30 minutes  
**Spec Location:** Line 2365-2387

---

### 3.4 Get Buffer Memory (Admin)
**Endpoint:** `GET /v1/memory/buffer`  
**File:** `src/muxi/formation/server/routes/admin/memory.py:67`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
overlord.buffer_memory.entries  # All buffer entries
overlord.buffer_memory.kv_store  # KV store entries
```

**What to Implement:**
```python
@router.get("/memory/buffer")
async def get_buffer_memory(request: Request):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    if not overlord.buffer_memory:
        return {"success": False, "error": {"code": "NOT_CONFIGURED", "message": "Buffer memory not enabled"}}
    
    # Get buffer statistics
    buffer_stats = {
        "total_entries": len(overlord.buffer_memory.entries),
        "max_size": overlord.buffer_memory.size,
        "utilization": len(overlord.buffer_memory.entries) / overlord.buffer_memory.size,
        "kv_namespaces": {},
    }
    
    # Get KV store namespaces
    for key in overlord.buffer_memory.kv_store.keys():
        namespace = key.split(":")[0] if ":" in key else "default"
        buffer_stats["kv_namespaces"][namespace] = buffer_stats["kv_namespaces"].get(namespace, 0) + 1
    
    return {"success": True, "data": buffer_stats}
```

**Effort:** 1 hour  
**Spec Location:** Line 2389-2460

---

### 3.5 Clear Buffer Memory (Admin)
**Endpoint:** `DELETE /v1/memory/buffer/{session_id}`  
**File:** `src/muxi/formation/server/routes/admin/memory.py:90`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Available in overlord:
# Clear all entries for a session
overlord.buffer_memory.entries = [
    entry for entry in overlord.buffer_memory.entries
    if entry.get("metadata", {}).get("session_id") != session_id
]
```

**What to Implement:**
```python
@router.delete("/memory/buffer/{session_id}")
async def clear_buffer_session(request: Request, session_id: str):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    if not overlord.buffer_memory:
        return {"success": False, "error": {"code": "NOT_CONFIGURED", "message": "Buffer memory not enabled"}}
    
    # Count entries before
    before_count = len(overlord.buffer_memory.entries)
    
    # Remove entries for this session
    overlord.buffer_memory.entries = [
        entry for entry in overlord.buffer_memory.entries
        if entry.get("metadata", {}).get("session_id") != session_id
    ]
    
    # Count removed
    removed_count = before_count - len(overlord.buffer_memory.entries)
    
    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "removed_entries": removed_count
        }
    }
```

**Effort:** 30 minutes  
**Spec Location:** Line 2462-2501

---

## 4. Runtime Settings Updates (6 endpoints) - LOW PRIORITY

### 4.1 Update LLM Settings
**Endpoint:** `PUT /v1/llm/settings`  
**File:** `src/muxi/formation/server/routes/admin/llm.py:69`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
LLM configuration in formation, but runtime updates need persistence strategy

**What to Implement:**
```python
@router.put("/llm/settings")
async def update_llm_settings(request: Request, body: Dict[str, Any]):
    formation = request.app.state.formation
    
    # Update in-memory configuration
    if "temperature" in body:
        formation.llm_config["temperature"] = body["temperature"]
    if "max_tokens" in body:
        formation.llm_config["max_tokens"] = body["max_tokens"]
    # ... other settings
    
    # TODO: Decide on persistence strategy
    # Option 1: Ephemeral (lost on restart) - simplest
    # Option 2: Write back to formation YAML - complex
    # Option 3: Store in database - requires schema
    
    return {"success": True, "data": formation.llm_config}
```

**Challenge:** Need to decide persistence strategy  
**Effort:** 2 hours (if ephemeral), 6 hours (if persistent)  
**Spec Location:** Line 846-914

---

### 4.2 Reset LLM Setting
**Endpoint:** `DELETE /v1/llm/settings/{item}`  
**File:** `src/muxi/formation/server/routes/admin/llm.py:108`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Reset specific LLM setting to formation YAML default

**Effort:** 1 hour  
**Spec Location:** Line 916-971

---

### 4.3 Update MCP Settings
**Endpoint:** `PUT /v1/mcp`  
**File:** `src/muxi/formation/server/routes/admin/mcp.py:132`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Update MCP global defaults (same persistence challenge as LLM)

**Effort:** 1-2 hours  
**Spec Location:** Line 3512-3590

---

### 4.4 Add MCP Server
**Endpoint:** `POST /v1/mcp/servers`  
**File:** `src/muxi/formation/server/routes/admin/mcp.py:216`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Can dynamically add MCP servers:
await formation.add_mcp_server(server_config)
```

**What to Implement:**
```python
@router.post("/mcp/servers")
async def add_mcp_server(request: Request, body: Dict[str, Any]):
    formation = request.app.state.formation
    
    # Validate server config
    server_config = {
        "id": body["id"],
        "type": body["type"],  # stdio, http, sse
        "command": body.get("command"),
        "endpoint": body.get("endpoint"),
        # ... other config
    }
    
    # Add server dynamically
    try:
        await formation.add_mcp_server(server_config)
        return {"success": True, "data": server_config}
    except Exception as e:
        return {"success": False, "error": {"code": "OPERATION_FAILED", "message": str(e)}}
```

**Effort:** 2 hours  
**Spec Location:** Line 3592-3665

---

### 4.5 Update MCP Server
**Endpoint:** `PUT /v1/mcp/servers/{server_id}`  
**File:** `src/muxi/formation/server/routes/admin/mcp.py:270`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Update existing MCP server configuration (need remove + re-add)

**Effort:** 1 hour  
**Spec Location:** Line 3698-3750

---

### 4.6 Delete MCP Server
**Endpoint:** `DELETE /v1/mcp/servers/{server_id}`  
**File:** `src/muxi/formation/server/routes/admin/mcp.py:297`  
**Auth:** Admin API Key  
**Status:** TODO comment

**Backend Exists:**
```python
# Can remove MCP servers:
await formation.remove_mcp_server(server_id)
```

**What to Implement:**
```python
@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(request: Request, server_id: str):
    formation = request.app.state.formation
    
    try:
        await formation.remove_mcp_server(server_id)
        return {"success": True, "data": {"deleted": server_id}}
    except KeyError:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": f"Server {server_id} not found"}}
```

**Effort:** 1 hour  
**Spec Location:** Line 3698-3750

---

### 4.7 Update Scheduler Settings
**Endpoint:** `PUT /v1/scheduler`  
**File:** `src/muxi/formation/server/routes/admin/scheduler.py:82`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Update scheduler configuration (same persistence challenge)

**Effort:** 1 hour  
**Spec Location:** Line 2558-2611

---

### 4.8 Update A2A Settings
**Endpoint:** `PUT /v1/a2a/outbound`  
**File:** `src/muxi/formation/server/routes/admin/a2a.py:71`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Update A2A outbound configuration (same persistence challenge)

**Effort:** 1 hour  
**Spec Location:** Not in spec

---

### 4.9 Reset A2A Setting
**Endpoint:** `DELETE /v1/a2a/outbound/{item}`  
**File:** `src/muxi/formation/server/routes/admin/a2a.py:94`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
Reset A2A setting to default

**Effort:** 30 minutes  
**Spec Location:** Not in spec

---

### 4.10 Update Async Settings
**Endpoint:** `PUT /v1/async`  
**File:** `src/muxi/formation/server/routes/admin/async_routes.py:72`  
**Auth:** Admin API Key  
**Status:** TODO comment

**What to Implement:**
```python
@router.put("/async")
async def update_async_settings(request: Request, body: Dict[str, Any]):
    formation = request.app.state.formation
    overlord = formation.overlord
    
    # Update runtime settings (ephemeral)
    if "threshold_seconds" in body:
        overlord.async_threshold_seconds = body["threshold_seconds"]
    if "webhook_url" in body:
        overlord.async_webhook_url = body["webhook_url"]
    
    return {
        "success": True,
        "data": {
            "threshold_seconds": overlord.async_threshold_seconds,
            "webhook_url": overlord.async_webhook_url,
        }
    }
```

**Effort:** 1 hour  
**Spec Location:** Line 2503-2556

---

## Implementation Summary

### By Priority

**High Priority (Implement First):**
- None - all are medium or low priority

**Medium Priority (User-Facing Value):**
- 5 Job/Async endpoints (~3 hours total)
- 2 Log streaming endpoints (~6 hours total)

**Low Priority (Admin Convenience):**
- 5 Memory endpoints (~4 hours total)
- 10 Settings update endpoints (~10-15 hours total, depends on persistence)

### By Effort

**Quick Wins (<1 hour each):**
- Cancel user job
- List all jobs (admin)
- Get job details (admin)
- Cancel job (admin)
- Delete memory
- Clear buffer session
- Reset LLM/A2A settings

**Medium Effort (1-2 hours each):**
- List user jobs
- Get memories
- Create memory
- Get buffer memory
- Update LLM/MCP/Scheduler/A2A/Async settings

**Higher Effort (4-6 hours):**
- Live log streaming (needs observability changes)

### Total Effort Estimate

- **Minimum (ephemeral settings):** ~18-20 hours
- **Maximum (persistent settings):** ~25-30 hours

All endpoints can be implemented incrementally - each one is independent.

---

## Next Steps

1. **Decide on persistence strategy** for runtime settings updates:
   - Ephemeral (simplest, lost on restart)
   - Database (clean, requires schema)
   - Formation YAML (complex, requires atomic writes)

2. **Implement in order of priority:**
   - Phase 1: Job management (high user value, low effort)
   - Phase 2: Log streaming (high debugging value, medium effort)
   - Phase 3: Memory management (privacy/control value, low effort)
   - Phase 4: Settings updates (convenience, higher effort)

3. **Test against spec:**
   - Each endpoint has full definition in `formation-api-v1-final.yaml`
   - Request/response schemas are complete
   - Just wire up to existing backend

---

**All backend functionality exists and works correctly. These are just API wrappers around existing code.**
