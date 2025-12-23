# Session Management

## Overview

Sessions group related messages into conversations, enabling context continuity, repeated question detection, and follow-up inference.

## Recommended Flow

### 1. First Request

Send your first message without a `session_id` (or with `null`):

```bash
curl -X POST 'http://localhost:8002/v1/chat' \
  -H 'Content-Type: application/json' \
  -H 'X-MUXI-CLIENT-KEY: your-key' \
  -d '{"message": "whats the capital of france?", "stream": false}'
```

### 2. Capture Generated Session ID

The response includes a generated `session_id`:

```json
{
  "data": {
    "session_id": "sess_VcL57KzvPPLkaxO70jzF4",
    "message": {
      "role": "assistant",
      "content": "The capital of France is Paris."
    }
  }
}
```

### 3. Use Session ID for Continuity

Include the `session_id` in subsequent requests to maintain conversation context:

```bash
curl -X POST 'http://localhost:8002/v1/chat' \
  -H 'Content-Type: application/json' \
  -H 'X-MUXI-CLIENT-KEY: your-key' \
  -d '{
    "message": "what about israel?",
    "session_id": "sess_VcL57KzvPPLkaxO70jzF4",
    "stream": false
  }'
```

The system will infer context from the conversation history:

```json
{
  "data": {
    "session_id": "sess_VcL57KzvPPLkaxO70jzF4",
    "message": {
      "role": "assistant", 
      "content": "The capital of Israel is Jerusalem."
    }
  }
}
```

## Benefits of Session Continuity

| Feature | Description |
|---------|-------------|
| **Context Inference** | Follow-up questions like "what about X?" are understood in context |
| **Repeated Question Detection** | System acknowledges when the same question is asked again |
| **Conversation History** | Messages are stored and retrievable via `/v1/sessions/{id}/messages` |

## Design Principles

1. **Explicit over implicit**: No session_id = no continuity. We don't guess or group by timing.
2. **Client control**: The client decides whether to maintain context by choosing to send session_id.
3. **Stateless requests**: Each request is self-contained; session_id is the only state reference.
4. **Predictable behavior**: No magic time-based grouping that's hard to debug.

## SDK Implementation Guidelines

When building SDKs, implement a session manager that:

1. Stores the `session_id` from the first response
2. Automatically includes it in subsequent requests
3. Provides methods to explicitly start a new session (clear stored session_id)
4. Exposes the current session_id for debugging/logging

Example SDK pattern:

```python
class MuxiClient:
    def __init__(self):
        self._session_id = None
    
    def chat(self, message: str, new_session: bool = False) -> Response:
        if new_session:
            self._session_id = None
        
        response = self._send_request(message, self._session_id)
        self._session_id = response.session_id
        return response
    
    @property
    def session_id(self) -> str | None:
        return self._session_id
```

## Related Endpoints

- `GET /v1/sessions` - List sessions for a user
- `GET /v1/sessions/{session_id}` - Get session details
- `GET /v1/sessions/{session_id}/messages` - Get messages in a session
- `DELETE /v1/sessions/{session_id}` - Delete a session and its history
