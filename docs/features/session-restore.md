# Session Restore - PRD

**Status:** Planned  
**Created:** 2025-12-12  
**Endpoint:** `POST /sessions/{session_id}/restore`

## Problem

MUXI's session buffer is ephemeral:
- Lost on runtime restart
- Old messages roll off (FIFO with size limits)
- No built-in persistence

Developers building chat applications (like ChatGPT's sidebar) need persistent conversation history. Currently they must:
1. Store messages in their own database
2. Have no way to restore context when user returns

## Solution

Add `POST /sessions/{session_id}/restore` endpoint that allows developers to hydrate a session's buffer with messages from their external storage.

## User Flow

```
1. User chats with formation
2. Developer persists messages to their DB (via webhook, polling GET /sessions/{id}/messages, or inline)
3. User leaves, runtime may restart, buffer clears
4. User returns to continue conversation
5. Developer fetches messages from their DB
6. Developer calls POST /sessions/{session_id}/restore with messages
7. Buffer is hydrated with conversation history
8. User continues chatting with full context
```

## API Design

### Request

```http
POST /sessions/{session_id}/restore
X-Muxi-User-ID: alice
Content-Type: application/json

{
  "messages": [
    {
      "role": "user",
      "content": "What's the weather like?",
      "timestamp": "2025-10-23T10:00:00Z"
    },
    {
      "role": "assistant", 
      "content": "The weather today is sunny with a high of 72F.",
      "timestamp": "2025-10-23T10:00:15Z",
      "agent_id": "weather-assistant"
    },
    {
      "role": "user",
      "content": "Thanks! What about tomorrow?",
      "timestamp": "2025-10-23T10:01:00Z"
    }
  ]
}
```

### Response

```json
{
  "object": "session",
  "type": "session.restored",
  "success": true,
  "data": {
    "session_id": "sess_abc123",
    "messages_loaded": 3,
    "messages_dropped": 0,
    "message": "Session restored successfully"
  }
}
```

## Message Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| role | string | Yes | `user`, `assistant`, or `system` |
| content | string | Yes | Message content |
| timestamp | ISO 8601 | Yes | Original message timestamp |
| agent_id | string | No | Agent that generated response |
| metadata | object | No | Additional metadata to preserve |

## Implementation Requirements

### Buffer Memory Changes

1. Add `restore_session(user_id, session_id, messages)` method to buffer memory
2. Method should:
   - Clear existing messages for this user+session
   - Insert messages in timestamp order
   - Respect buffer size limits (drop oldest if overflow)
   - Return count of loaded and dropped messages

### Endpoint Implementation

```python
@router.post("/sessions/{session_id}/restore")
async def restore_session(
    request: Request,
    session_id: str,
    payload: SessionRestoreRequest,
    x_user_id: str = Header(..., alias="X-Muxi-User-ID"),
) -> JSONResponse:
    # 1. Validate user_id
    # 2. Get buffer memory from overlord
    # 3. Call buffer.restore_session(user_id, session_id, payload.messages)
    # 4. Return success with counts
```

### Validation

- Timestamps must be valid ISO 8601
- Messages should be sorted by timestamp (or we sort them)
- Role must be one of: user, assistant, system
- Content cannot be empty

### Edge Cases

| Case | Behavior |
|------|----------|
| Empty messages array | Clear session, return 0 loaded |
| More messages than buffer size | Load newest N, drop oldest, return counts |
| Session already has messages | Clear first, then load new |
| Invalid timestamp format | Return 400 |
| Missing required fields | Return 400 |

## Security Considerations

- Requires valid client API key
- X-Muxi-User-ID header required (user isolation)
- Messages are only loaded for the specified user+session
- No cross-user access possible

## Testing

1. **Basic restore**: Load 3 messages, verify buffer contains them
2. **Overflow handling**: Load 1000 messages into buffer with limit 100, verify oldest dropped
3. **Idempotent**: Restore same messages twice, verify correct state
4. **Clear and restore**: Session has messages, restore clears and replaces
5. **Validation**: Invalid timestamps, missing fields return 400
6. **User isolation**: Restore for user A doesn't affect user B

## Future Enhancements

1. **Streaming restore**: For very large histories, accept chunked uploads
2. **Selective restore**: Only restore messages after certain timestamp
3. **Compression**: Accept gzipped payloads for large histories
4. **Webhook on buffer clear**: Notify developer when buffer is about to clear

## Documentation

Update developer docs to explain:
1. Sessions are ephemeral by design
2. How to implement persistent chat history
3. Recommended patterns for storing/restoring messages
4. Buffer size limits and overflow behavior
