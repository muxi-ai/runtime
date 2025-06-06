#!/usr/bin/env python3
"""
Simple test to verify FAISSx remote connection and see server logs.
"""

import sys
import traceback

import numpy as np

# Set up import path before importing muxi modules
sys.path.insert(0, "runtime")


def test_faissx_remote():
    """Test FAISSx remote operations with detailed logging"""
    print("=== Testing FAISSx Remote Mode ===")

    try:
        # Import FAISSx client
        from faissx import client as faiss  # noqa: E402
        print("✓ Successfully imported faissx.client")

        # Configure for remote mode
        print("Configuring FAISSx for remote server...")
        faiss.configure(
            server="tcp://localhost:45678",
            api_key="test_key_123",
            tenant_id="test_tenant_456"
        )
        print("✓ FAISSx configured for remote mode")

        # Create index
        print("Creating remote index...")
        index = faiss.IndexFlatL2(128)  # Smaller dimension for faster test
        print("✓ Remote index created (dimension: 128)")

        # Add vectors
        print("Adding vectors to remote index...")
        vectors = np.random.rand(5, 128).astype(np.float32)
        index.add(vectors)
        print(f"✓ Added {index.ntotal} vectors to remote index")

        # Search
        print("Performing search on remote index...")
        query = np.random.rand(1, 128).astype(np.float32)
        distances, indices = index.search(query, 2)
        print(f"✓ Search completed, found {len(indices[0])} results")
        print(f"  Distances: {distances[0]}")
        print(f"  Indices: {indices[0]}")

        # Try multiple operations to generate more logs
        print("Performing additional operations...")
        for i in range(3):
            more_vectors = np.random.rand(2, 128).astype(np.float32)
            index.add(more_vectors)
            print(f"  Batch {i+1}: Added 2 more vectors (total: {index.ntotal})")

        print("\n✅ All remote operations completed successfully!")
        print("Check the FAISSx server logs for connection activity.")

        return True

    except Exception as e:
        print(f"❌ Remote test failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_faissx_remote()
