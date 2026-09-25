#!/usr/bin/env python3
"""The shipped stdio middleware template, recording each user_id it receives.

Test fixture for the identity hand-off tests in test_request_middleware.py.
It runs ``contributing/templates/middleware.py`` unchanged (same MCP stdio
server, same tool contract, same embedded groups map) and wraps its
``transform`` to:

- append the ``user_id`` it received, JSON-encoded, one per line, to
  RECORD_FILE (so a test can see exactly what the runtime sent), and
- optionally return REWRITE_USER_ID as the identity (an identity rewrite).

Usage: recording_middleware.py RECORD_FILE [REWRITE_USER_ID]
"""

import importlib.util
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[3] / "contributing" / "templates" / "middleware.py"

spec = importlib.util.spec_from_file_location("middleware_template", TEMPLATE)
template = importlib.util.module_from_spec(spec)
spec.loader.exec_module(template)

record_path = sys.argv[1]
rewrite_user_id = sys.argv[2] if len(sys.argv) > 2 else None
template_transform = template.transform


def transform(arguments, groups_map):
    with open(record_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(arguments.get("user_id")) + "\n")
    payload = template_transform(arguments, groups_map)
    if rewrite_user_id is not None:
        payload["user_id"] = rewrite_user_id
    return payload


template.transform = transform
sys.argv = sys.argv[:1]
template.main()
