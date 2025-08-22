#!/usr/bin/env python3
"""
Script to encrypt existing plaintext credentials in the database.
Run this AFTER the schema migration but BEFORE using the system.
"""

import asyncio
import base64
import json
import os
import sys
from datetime import datetime

import asyncpg
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_user_key(formation_id: str, user_id: str) -> Fernet:
    """
    Derive a per-user encryption key using PBKDF2.
    Matches the approach in EncryptedCredentialResolver.
    """
    # Combine formation_id with user_id for per-user isolation
    combined = f"{formation_id}:{user_id}".encode('utf-8')

    # Derive key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'muxi-user-credentials-v1',  # Static salt for deterministic key derivation
        iterations=100000,
        backend=default_backend()
    )

    # Generate Fernet-compatible key
    key = base64.urlsafe_b64encode(kdf.derive(combined))
    return Fernet(key)


async def encrypt_credentials():
    """Encrypt all existing credentials in the database."""
    print(f"[{datetime.now()}] Starting credential encryption...")

    # Get database URL from environment or use default
    db_url = os.getenv("DATABASE_URL", "postgresql://ran@127.0.0.1/muxi_framework")

    # Connect to database
    conn = await asyncpg.connect(db_url)

    try:
        # Check if credentials are already encrypted
        test_row = await conn.fetchrow("""
            SELECT credentials FROM credentials LIMIT 1
        """)

        if test_row and test_row['credentials']:
            try:
                # Try to parse as JSON to check if encrypted
                data = json.loads(test_row['credentials'])
                if isinstance(data, dict) and data.get('encrypted'):
                    print("Credentials appear to already be encrypted. Skipping.")
                    return
            except (json.JSONDecodeError, TypeError):
                pass  # Not JSON or not encrypted, proceed

        # Get all credentials with user info
        print("Fetching existing credentials...")
        rows = await conn.fetch("""
            SELECT c.id, c.user_id, c.credentials, u.external_user_id, u.formation_id
            FROM credentials c
            JOIN users u ON c.user_id = u.id
            WHERE c.credentials IS NOT NULL
        """)

        print(f"Found {len(rows)} credentials to encrypt")

        # Encrypt each credential
        for row in rows:
            cred_id = row['id']
            external_user_id = row['external_user_id']
            user_formation_id = row['formation_id']
            cred_data = row['credentials']

            # Skip if already encrypted
            try:
                parsed = json.loads(cred_data)
                if isinstance(parsed, dict) and parsed.get('encrypted'):
                    print(f"  Credential ID {cred_id} already encrypted, skipping")
                    continue
            except (json.JSONDecodeError, TypeError):
                pass

            # Use the user's formation_id for encryption
            fernet = derive_user_key(user_formation_id, external_user_id)

            # Handle different data types
            if cred_data.startswith('"') and cred_data.endswith('"'):
                # It's a JSON string, extract the actual value
                try:
                    actual_value = json.loads(cred_data)
                    credential_str = json.dumps({"token": actual_value})
                except json.JSONDecodeError:
                    credential_str = json.dumps({"token": cred_data})
            else:
                # Try to parse as JSON
                try:
                    parsed = json.loads(cred_data)
                    if isinstance(parsed, dict):
                        credential_str = cred_data
                    else:
                        credential_str = json.dumps({"token": parsed})
                except (json.JSONDecodeError, TypeError):
                    # Plain string, wrap it
                    credential_str = json.dumps({"token": cred_data})

            # Encrypt the credential
            encrypted_data = {
                "encrypted": True,
                "version": "1.0",
                "data": fernet.encrypt(credential_str.encode()).decode('utf-8')
            }
            encrypted_json = json.dumps(encrypted_data)

            # Update the row
            await conn.execute("""
                UPDATE credentials
                SET credentials = $1
                WHERE id = $2
            """, encrypted_json, cred_id)

            print(f"  Encrypted credential ID {cred_id} for user {external_user_id}")

        print(f"[{datetime.now()}] Credential encryption completed successfully")

    finally:
        await conn.close()


async def decrypt_credentials():
    """Decrypt all credentials back to plaintext (for rollback)."""
    print(f"[{datetime.now()}] Starting credential decryption...")

    # Get database URL from environment or use default
    db_url = os.getenv("DATABASE_URL", "postgresql://ran@127.0.0.1/muxi_framework")

    # Connect to database
    conn = await asyncpg.connect(db_url)

    try:
        # Get all encrypted credentials with user info
        rows = await conn.fetch("""
            SELECT c.id, c.user_id, c.credentials, u.external_user_id, u.formation_id
            FROM credentials c
            JOIN users u ON c.user_id = u.id
            WHERE c.credentials IS NOT NULL
        """)

        print(f"Found {len(rows)} credentials to decrypt")

        # Decrypt each credential
        for row in rows:
            cred_id = row['id']
            external_user_id = row['external_user_id']
            user_formation_id = row['formation_id']
            encrypted_str = row['credentials']

            try:
                # Parse the encrypted data structure
                encrypted_data = json.loads(encrypted_str)

                if not encrypted_data.get("encrypted"):
                    print(f"  Credential ID {cred_id} not encrypted, skipping")
                    continue

                if "data" not in encrypted_data:
                    print(f"  Credential ID {cred_id} missing encrypted data, skipping")
                    continue

                # Decrypt it
                fernet = derive_user_key(user_formation_id, external_user_id)
                decrypted_bytes = fernet.decrypt(encrypted_data["data"].encode())
                decrypted = decrypted_bytes.decode('utf-8')

                # Parse as JSON
                cred_json = json.loads(decrypted)

                # If it's wrapped in a token field with only that field, unwrap it
                if isinstance(cred_json, dict) and 'token' in cred_json and len(cred_json) == 1:
                    # This was a plain string token, store as JSON string
                    plaintext = json.dumps(cred_json['token'])
                else:
                    # Store as JSON object
                    plaintext = json.dumps(cred_json)

                # Update the row
                await conn.execute("""
                    UPDATE credentials
                    SET credentials = $1::jsonb
                    WHERE id = $2
                """, plaintext, cred_id)

                print(f"  Decrypted credential ID {cred_id} for user {external_user_id}")

            except Exception as e:
                print(f"  Error decrypting credential ID {cred_id}: {e}")
                continue

        print(f"[{datetime.now()}] Credential decryption completed successfully")

    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "decrypt":
        asyncio.run(decrypt_credentials())
    else:
        asyncio.run(encrypt_credentials())
