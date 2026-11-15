#!/usr/bin/env python3
"""Trigger auth check for Stripe webhooks (Python standard library only).

Reads the trigger-auth JSON on stdin and exits 0 only for a valid, fresh
Stripe-Signature. The signing secret comes from STRIPE_WEBHOOK_SECRET in
the runtime's environment.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time

TOLERANCE_SECONDS = 300  # Stripe's default replay window

request = json.load(sys.stdin)
body = base64.b64decode(request["body"])
header = request["headers"].get("stripe-signature", "")
pairs = [item.split("=", 1) for item in header.split(",") if "=" in item]
timestamp = next((value for key, value in pairs if key == "t"), "")
signatures = [value for key, value in pairs if key == "v1"]
if not timestamp.isdigit() or abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
    sys.exit(1)
secret = os.environ["STRIPE_WEBHOOK_SECRET"].encode()
expected = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
sys.exit(0 if any(hmac.compare_digest(expected, s) for s in signatures) else 1)
