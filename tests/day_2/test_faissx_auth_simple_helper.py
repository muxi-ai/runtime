#!/usr/bin/env python3
"""Simple test to verify FAISSx authentication is working."""

import asyncio
import os
from muxi.services.memory.short_term import ShortTermMemory
from muxi.datatypes.memory import BufferMemoryConfig, RemoteBufferConfig

async def test_faissx_auth_connection():
    """Test connecting to FAISSx with authentication."""

    # Load secrets from environment
    api_key = os.getenv("FAISSX_API_KEY", "test-api-key")
    tenant_id = os.getenv("FAISSX_TENANT_ID", "test-tenant")

    print(f"Testing FAISSx connection with auth...")
    print(f"API Key: {'*' * len(api_key) if api_key else 'None'}")
    print(f"Tenant ID: {tenant_id}")

    # Create buffer config with authentication
    buffer_config = BufferMemoryConfig(
        enabled=True,
        size=10,
        multiplier=5,
        vector_search=True,
        vector_dimension=1536,
        mode="remote",
        remote=RemoteBufferConfig(
            url="tcp://localhost:65432",
            api_key=api_key,
            tenant=tenant_id
        )
    )

    try:
        # Create short-term memory with auth config
        memory = ShortTermMemory(
            formation_id="test_formation",
            max_size=buffer_config.size,
            buffer_multiplier=buffer_config.multiplier,
            mode=buffer_config.mode,
            vector_search=buffer_config.vector_search,
            vector_dimension=buffer_config.vector_dimension,
            remote_config=buffer_config.remote.model_dump() if buffer_config.remote else None,
            embedding_model=None  # Will use mock embeddings
        )

        print("\n✅ ShortTermMemory created successfully with auth config")
        print(f"Mode: {memory.mode}")
        print(f"Remote URL: {memory.remote_config.get('url') if memory.remote_config else 'N/A'}")
        print(f"Has API Key: {'Yes' if memory.remote_config and memory.remote_config.get('api_key') else 'No'}")
        print(f"Tenant: {memory.remote_config.get('tenant') if memory.remote_config else 'N/A'}")

        # Test adding a memory
        await memory.add("test-user", "Test message with authentication", {})
        print("\n✅ Successfully added memory with auth")

        # Test searching
        results = await memory.search("test-user", "test", k=5)
        print(f"\n✅ Search completed, found {len(results)} results")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Set the secrets as environment variables for this test
    os.environ["FAISSX_API_KEY"] = "test-auth-key-123"
    os.environ["FAISSX_TENANT_ID"] = "test-tenant-456"

    asyncio.run(test_faissx_auth_connection())
