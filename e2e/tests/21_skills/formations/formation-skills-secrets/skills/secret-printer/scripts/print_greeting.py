"""Print greeting from environment variable injected by MUXI secrets resolution."""
import os
import sys

greeting = os.environ.get("SKILL_TEST_GREETING", "")
if not greeting:
    print("ERROR: SKILL_TEST_GREETING env var not set", file=sys.stderr)
    sys.exit(1)

print(greeting)
