# Testing Utilities

This directory contains testing utilities that are not part of the MUXI Runtime distribution but are used for testing and development.

## Contents

### webhook_server.py
A simple webhook server for testing async processing responses.
- Listens on port 8765 by default
- Logs all webhook requests to `webhook_log.json` in the current directory
- Provides HTTP endpoints for health checks and log viewing

**Usage:**
```bash
python utils/webhook_server.py
```

### webhook_log_reader.py
Utility for reading webhook logs in tests.
- Provides methods to find webhooks by request ID
- Can wait for webhooks with timeout
- Helps tests verify async processing results

**Usage in tests:**
```python
from utils.webhook_log_reader import WebhookLogReader

reader = WebhookLogReader()
webhook = reader.wait_for_webhook(request_id, timeout=30.0)
```

### a2a_registry.py
Mock A2A (Agent-to-Agent) registry server for testing cross-formation communication.
- Provides agent discovery and registration
- Used for testing multi-formation scenarios
- Runs on port 9090 by default

**Usage:**
```bash
python utils/a2a_registry.py
```

## Note
These utilities are for testing purposes only and should not be included in production deployments.