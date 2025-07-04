#!/usr/bin/env python3
"""
Test nested dictionary resolution in MCP coordinator.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from typing import Dict, Any, Optional


class MissingCredentialError(Exception):
    def __init__(self, service: str, user_id: str):
        self.service = service
        self.user_id = user_id
        super().__init__(f"Missing credential for service '{service}' and user '{user_id}'")


class MockCredentialResolver:
    def __init__(self):
        self.credentials = {}
    
    async def resolve(self, user_id: str, service: str) -> Optional[Dict[str, Any]]:
        key = f"{user_id}:{service}"
        return self.credentials.get(key)
    
    def store(self, user_id: str, service: str, creds: Dict[str, Any]):
        key = f"{user_id}:{service}"
        self.credentials[key] = creds


class MockOverlord:
    def __init__(self):
        self.credential_resolver = MockCredentialResolver()


class MockMCPCoordinator:
    def __init__(self, overlord):
        self.overlord = overlord
    
    async def resolve_mcp_auth_for_execution(
        self, server_id: str, auth: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """
        Resolve authentication for MCP tool execution.
        
        This method handles user credential placeholders in auth configurations
        by replacing them with actual user credentials from the database.
        """
        if not auth or not user_id or not self.overlord.credential_resolver:
            return auth

        # Pattern to match user credential placeholders
        import re
        USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")

        async def resolve_auth_recursive(data: Any) -> Any:
            """Recursively resolve credential placeholders in nested data structures."""
            if isinstance(data, dict):
                # Process dictionary recursively
                resolved_dict = {}
                for key, value in data.items():
                    resolved_dict[key] = await resolve_auth_recursive(value)
                return resolved_dict
            elif isinstance(data, list):
                # Process list recursively
                return [await resolve_auth_recursive(item) for item in data]
            elif isinstance(data, str):
                # Check if this is a user credential placeholder
                match = USER_CREDENTIAL_PATTERN.match(data)
                if match:
                    service = match.group(1).lower()  # Normalize to lowercase

                    # Resolve credential from database
                    credentials = await self.overlord.credential_resolver.resolve(user_id, service)

                    if credentials is None:
                        # Trigger clarification flow by raising error
                        raise MissingCredentialError(service, user_id)

                    # Replace placeholder with actual credential
                    # If credentials is a dict, extract the appropriate field
                    if isinstance(credentials, dict):
                        # Common patterns: token, api_key, access_token, key
                        for field in ["token", "api_key", "access_token", "key", "password"]:
                            if field in credentials:
                                return credentials[field]
                        # If no standard field found, use the whole dict
                        return credentials
                    else:
                        # If it's a string or other type, use directly
                        return credentials
                else:
                    # Not a user credential, keep as-is
                    return data
            else:
                # Non-string, non-dict, non-list values pass through
                return data

        return await resolve_auth_recursive(auth)


async def test_nested_resolution():
    """Test recursive nested dictionary resolution."""
    print("TESTING NESTED DICTIONARY CREDENTIAL RESOLUTION")
    print("=" * 60)
    print()
    
    # Setup
    overlord = MockOverlord()
    coordinator = MockMCPCoordinator(overlord)
    
    # Store test credentials
    overlord.credential_resolver.store("user-123", "github", {"token": "ghp_nested_test"})
    overlord.credential_resolver.store("user-123", "openai", {"api_key": "sk-nested-key"})
    overlord.credential_resolver.store("user-123", "database", {"password": "db_pass", "username": "db_user"})
    
    # Test 1: Flat dictionary (existing functionality)
    print("1. Flat Dictionary Resolution")
    print("-" * 40)
    
    flat_auth = {
        "token": "${{ user.credentials.github }}",
        "api_key": "${{ user.credentials.openai }}",
        "static_value": "unchanged"
    }
    
    resolved_flat = await coordinator.resolve_mcp_auth_for_execution(
        server_id="test-server",
        auth=flat_auth,
        user_id="user-123"
    )
    
    expected_flat = {
        "token": "ghp_nested_test",
        "api_key": "sk-nested-key", 
        "static_value": "unchanged"
    }
    
    assert resolved_flat == expected_flat
    print("✅ Flat dictionary resolution works")
    print(f"   Input:  {flat_auth}")
    print(f"   Output: {resolved_flat}")
    print()
    
    # Test 2: Nested dictionary resolution
    print("2. Nested Dictionary Resolution")
    print("-" * 40)
    
    nested_auth = {
        "primary": {
            "github": {
                "token": "${{ user.credentials.github }}",
                "scope": "repo"
            },
            "openai": {
                "api_key": "${{ user.credentials.openai }}",
                "model": "gpt-4"
            }
        },
        "secondary": {
            "database": {
                "user": "${{ user.credentials.database }}",
                "timeout": 30
            }
        },
        "static": "unchanged_value"
    }
    
    resolved_nested = await coordinator.resolve_mcp_auth_for_execution(
        server_id="test-server",
        auth=nested_auth,
        user_id="user-123"
    )
    
    expected_nested = {
        "primary": {
            "github": {
                "token": "ghp_nested_test",
                "scope": "repo"
            },
            "openai": {
                "api_key": "sk-nested-key", 
                "model": "gpt-4"
            }
        },
        "secondary": {
            "database": {
                "user": "db_pass",  # First field from priority list found in database credentials  
                "timeout": 30
            }
        },
        "static": "unchanged_value"
    }
    
    assert resolved_nested == expected_nested
    print("✅ Nested dictionary resolution works")
    print(f"   Input structure preserved with credentials resolved")
    print(f"   GitHub token: {resolved_nested['primary']['github']['token']}")
    print(f"   OpenAI key: {resolved_nested['primary']['openai']['api_key']}")
    print(f"   Database user: {resolved_nested['secondary']['database']['user']}")
    print()
    
    # Test 3: Array handling
    print("3. Array Resolution")
    print("-" * 40)
    
    array_auth = {
        "servers": [
            {
                "name": "primary",
                "token": "${{ user.credentials.github }}"
            },
            {
                "name": "backup", 
                "key": "${{ user.credentials.openai }}"
            }
        ],
        "static_list": ["unchanged", "values"]
    }
    
    resolved_array = await coordinator.resolve_mcp_auth_for_execution(
        server_id="test-server",
        auth=array_auth,
        user_id="user-123"
    )
    
    expected_array = {
        "servers": [
            {
                "name": "primary",
                "token": "ghp_nested_test"
            },
            {
                "name": "backup",
                "key": "sk-nested-key"
            }
        ],
        "static_list": ["unchanged", "values"]
    }
    
    assert resolved_array == expected_array
    print("✅ Array resolution works")
    print(f"   Resolved server configs in array")
    print()
    
    # Test 4: Missing credential in nested structure
    print("4. Missing Credential Error Handling")
    print("-" * 40)
    
    missing_auth = {
        "config": {
            "missing": "${{ user.credentials.nonexistent }}"
        }
    }
    
    try:
        await coordinator.resolve_mcp_auth_for_execution(
            server_id="test-server",
            auth=missing_auth,
            user_id="user-123"
        )
        assert False, "Should have raised MissingCredentialError"
    except MissingCredentialError as e:
        assert e.service == "nonexistent"
        assert e.user_id == "user-123"
        print("✅ Missing credential error properly raised from nested structure")
        print(f"   Error: {e}")
    print()
    
    # Test 5: Deep nesting
    print("5. Deep Nesting Resolution")
    print("-" * 40)
    
    deep_auth = {
        "level1": {
            "level2": {
                "level3": {
                    "level4": {
                        "credential": "${{ user.credentials.github }}"
                    }
                }
            }
        }
    }
    
    resolved_deep = await coordinator.resolve_mcp_auth_for_execution(
        server_id="test-server",
        auth=deep_auth,
        user_id="user-123"
    )
    
    assert resolved_deep["level1"]["level2"]["level3"]["level4"]["credential"] == "ghp_nested_test"
    print("✅ Deep nesting resolution works")
    print(f"   Resolved at depth 4: {resolved_deep['level1']['level2']['level3']['level4']['credential']}")
    print()
    
    print("=" * 60)
    print("✅ ALL NESTED RESOLUTION TESTS PASSED!")
    print()
    print("Benefits of recursive resolution:")
    print("- Handles arbitrarily nested authentication configurations")
    print("- Preserves structure while resolving credentials")
    print("- Works with arrays and complex data structures")
    print("- Maintains proper error handling for missing credentials")
    print("- Enables more flexible MCP server configurations")


if __name__ == "__main__":
    asyncio.run(test_nested_resolution())