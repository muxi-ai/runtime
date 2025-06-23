#!/usr/bin/env python3
"""
List Secrets - MUXI Runtime Utility (Fixed for direct execution)
"""

import sys
import asyncio
import warnings
from pathlib import Path
import os
import io
from contextlib import redirect_stdout

# Fix the import path
sys.path.insert(0, "/Users/ran/Projects/muxi/code/runtime/src")
from muxi.runtime.services.secrets import SecretsManager  # noqa: E402

# Suppress all output except our clean display
warnings.filterwarnings("ignore")
os.environ["LOGURU_LEVEL"] = "ERROR"


async def list_secrets_in_formation():
    """List all secrets in the formation in current directory."""
    formation_dir = Path(".")

    try:
        # Capture all stdout output to suppress JSON logs
        captured_output = io.StringIO()

        with redirect_stdout(captured_output):
            # Initialize SecretsManager
            secrets_manager = SecretsManager(formation_dir)
            await secrets_manager.initialize_encryption()

            # List secrets
            secrets = await secrets_manager.list_secrets()

        # Clean output after capturing is done
        if secrets:
            for secret in sorted(secrets):
                print(secret)

        print(f"\nTotal: {len(secrets)} secret(s)\n\n")

        return secrets

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    try:
        asyncio.run(list_secrets_in_formation())
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
