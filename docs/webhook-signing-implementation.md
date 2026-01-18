# Webhook Signing Implementation

## Overview

Implement HMAC-SHA256 signing for all outbound webhooks from the runtime. This allows SDK users to verify that webhooks genuinely originated from MUXI and haven't been tampered with.

## Why This Matters

### Security Risks Without Signing

1. **Spoofing**: Attackers can send fake webhook payloads to customer endpoints, triggering unauthorized actions
2. **Tampering**: Man-in-the-middle attacks can modify webhook content in transit
3. **Replay Attacks**: Captured webhooks can be re-sent to trigger duplicate processing

### Industry Standard

Webhook signing is standard practice:
- Stripe uses `Stripe-Signature` header with HMAC-SHA256
- GitHub uses `X-Hub-Signature-256`
- Twilio uses `X-Twilio-Signature`

Our SDKs already implement verification - the runtime just needs to sign.

## Specification

### Signature Header Format

```
X-Muxi-Signature: t=1704067200,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd
```

Components:
- `t` = Unix timestamp (seconds) when signature was generated
- `v1` = HMAC-SHA256 hex digest (version 1 scheme)

### Signing Algorithm

```python
import hmac
import hashlib
import time
import json

def sign_webhook(payload: dict, secret: str) -> tuple[str, int]:
    """
    Sign a webhook payload.
    
    Args:
        payload: The webhook payload dict
        secret: Signing secret (admin_key or dedicated webhook_secret)
    
    Returns:
        Tuple of (signature_header_value, timestamp)
    """
    timestamp = int(time.time())
    
    # Canonical JSON: compact, sorted keys for deterministic output
    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    
    # Message format: "{timestamp}.{payload}"
    message = f"{timestamp}.".encode('utf-8') + payload_bytes
    
    # HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()
    
    # Header value
    header_value = f"t={timestamp},v1={signature}"
    
    return header_value, timestamp
```

### Signing Secret

Use the formation's `admin_key` as the signing secret. This is already known to SDK users who configure webhooks.

Future enhancement: Add optional `webhook_secret` in formation config for dedicated signing key.

## Implementation Location

### File: `src/muxi/runtime/formation/background/webhook_manager.py`

### Changes Required

1. **Add signing function** (as shown above)

2. **Modify `_deliver_webhook` method** to include signature header:

```python
async def _deliver_webhook(
    self, webhook_url: str, payload: MuxiUnifiedResponse, timeout: int
) -> bool:
    try:
        session = await self._get_session()
        payload_dict = self._clean_payload_for_serialization(payload)
        
        # NEW: Sign the payload
        signature_header, timestamp = sign_webhook(payload_dict, self._signing_secret)
        
        headers = {
            "Content-Type": "application/json",
            "X-Muxi-Signature": signature_header,
            "X-Muxi-Timestamp": str(timestamp),  # Optional convenience header
        }
        
        async with session.post(
            webhook_url, 
            json=payload_dict, 
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            return 200 <= response.status < 300
    except Exception:
        return False
```

3. **Pass signing secret to WebhookManager**:

```python
class WebhookManager:
    def __init__(
        self, 
        default_retries: int = 3, 
        default_timeout: int = 10,
        signing_secret: str = ""  # NEW
    ):
        self.default_retries = default_retries
        self.default_timeout = default_timeout
        self._signing_secret = signing_secret  # NEW
```

4. **Update WebhookManager instantiation** in formation initialization to pass `admin_key`:

```python
# In formation/initialization.py or wherever WebhookManager is created
webhook_manager = WebhookManager(
    default_retries=async_config.webhook_retries,
    default_timeout=async_config.webhook_timeout,
    signing_secret=formation_config.admin_key,  # NEW
)
```

5. **Also sign clarification webhooks** in `_deliver_clarification_webhook`:

```python
async def _deliver_clarification_webhook(
    self, webhook_url: str, payload: ClarificationWebhookPayload, timeout: int
) -> bool:
    try:
        session = await self._get_session()
        payload_dict = payload.to_dict()
        
        # NEW: Sign the payload
        signature_header, timestamp = sign_webhook(payload_dict, self._signing_secret)
        
        headers = {
            "Content-Type": "application/json",
            "X-Muxi-Signature": signature_header,
            "X-Muxi-Timestamp": str(timestamp),
        }
        
        async with session.post(
            webhook_url, 
            json=payload_dict,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            return 200 <= response.status < 300
    except Exception:
        return False
```

## SDK Verification (Already Implemented)

The SDKs already have verification implemented. Example usage:

```python
from muxi import webhook

@app.post("/webhooks/muxi")
async def handle(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Muxi-Signature")
    
    # Verifies signature AND checks timestamp within 5 minutes
    if not webhook.verify_signature(payload, signature, ADMIN_KEY):
        raise HTTPException(401, "Invalid signature")
    
    event = webhook.parse(payload)
    # Process event...
```

## Testing

### Unit Test

```python
import pytest
from muxi.runtime.formation.background.webhook_manager import sign_webhook

def test_sign_webhook():
    payload = {"id": "req_123", "status": "completed"}
    secret = "test_secret_key"
    
    header, timestamp = sign_webhook(payload, secret)
    
    assert header.startswith("t=")
    assert ",v1=" in header
    assert len(header.split(",v1=")[1]) == 64  # SHA256 hex = 64 chars

def test_signature_deterministic():
    """Same payload + secret + timestamp = same signature"""
    payload = {"id": "req_123", "status": "completed"}
    secret = "test_secret"
    
    # Mock time.time() to return consistent value
    with patch('time.time', return_value=1704067200):
        header1, _ = sign_webhook(payload, secret)
        header2, _ = sign_webhook(payload, secret)
    
    assert header1 == header2
```

### Integration Test

```python
@pytest.mark.asyncio
async def test_webhook_signature_verification():
    """Verify SDK can validate runtime signatures"""
    from muxi import webhook
    
    # Simulate runtime signing
    payload = {"id": "req_123", "status": "completed", "response": []}
    secret = "test_admin_key"
    signature_header, _ = sign_webhook(payload, secret)
    
    # Verify with SDK
    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    assert webhook.verify_signature(payload_bytes, signature_header, secret)
```

### E2E Test

Update `e2e/tests/9_async/` tests to verify signature header is present and valid.

## Rollout

1. **Backward Compatible**: Webhooks will include signature header, but receivers aren't required to verify
2. **Documentation**: Update async-operations.md to document the signature format
3. **SDK Users**: Can opt-in to verification using `webhook.verify_signature()`

## Summary

| Component | Change |
|-----------|--------|
| `webhook_manager.py` | Add `sign_webhook()` function |
| `webhook_manager.py` | Add `_signing_secret` to `__init__` |
| `webhook_manager.py` | Add signature headers in `_deliver_webhook` |
| `webhook_manager.py` | Add signature headers in `_deliver_clarification_webhook` |
| Formation init | Pass `admin_key` to `WebhookManager` |
| Tests | Add unit + integration tests |
| Docs | Update async-operations.md |

## References

- SDK implementations: `muxi-python/muxi/webhook.py`, `muxi-go/src/webhook/`, `muxi-typescript/src/webhook.ts`
- Stripe signature docs: https://stripe.com/docs/webhooks/signatures
- Current webhook code: `src/muxi/runtime/formation/background/webhook_manager.py`
