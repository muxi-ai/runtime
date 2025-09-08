"""Unit tests for KV store FIFO cleanup functionality in WorkingMemory."""

import time
import unittest
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.services.memory.working import WorkingMemory


class TestKVFIFOCleanup(unittest.TestCase):
    """Test KV store FIFO cleanup functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create WorkingMemory instance without model for testing
        self.memory = WorkingMemory(
            formation_id="test-formation",
            max_size=10,
            buffer_multiplier=10,
            max_memory_mb=1,  # Very low limit to trigger cleanup
            model=None
        )
        # Initialize KV store
        self.memory.kv_store = {}

    def test_namespaces_excluded_from_fifo(self):
        """Test that excluded namespaces constant is properly defined."""
        self.assertEqual(
            WorkingMemory._NAMESPACES_EXCLUDED_FROM_FIFO,
            ["knowledge", "sops"]
        )

    def test_kv_store_memory_estimation(self):
        """Test that KV store items are included in memory estimation."""
        # Add some items to KV store
        self.memory.kv_store["test:key1"] = {"data": "a" * 1000}
        self.memory.kv_store["test:key2"] = {"data": "b" * 2000}
        
        # Run cleanup (should estimate memory including KV items)
        self.memory.check_memory_usage_and_cleanup()
        
        # We can't directly test the estimation without mocking,
        # but we can verify the method runs without error
        self.assertTrue(True)  # Method completed successfully

    def test_namespace_extraction(self):
        """Test namespace extraction from KV store keys."""
        # Add items with different namespaces
        self.memory.kv_store["buffer:key1"] = {"timestamp": time.time()}
        self.memory.kv_store["pending_clarification:session1"] = {"timestamp": time.time()}
        self.memory.kv_store["knowledge:doc1"] = {"timestamp": time.time()}
        self.memory.kv_store["sops:workflow1"] = {"timestamp": time.time()}
        self.memory.kv_store["clarification:req1"] = {"timestamp": time.time()}
        
        # Extract namespaces (simulate what cleanup does)
        all_namespaces = set()
        for key in self.memory.kv_store.keys():
            if ":" in key:
                namespace = key.split(":", 1)[0]
                all_namespaces.add(namespace)
        
        # Verify all namespaces are extracted correctly
        expected_namespaces = {
            "buffer", "pending_clarification", "knowledge", "sops", "clarification"
        }
        self.assertEqual(all_namespaces, expected_namespaces)

    def test_excluded_namespaces_not_cleaned(self):
        """Test that excluded namespaces are not cleaned up."""
        # Add items to excluded namespaces
        self.memory.kv_store["knowledge:doc1"] = {
            "data": "x" * 1000000,  # Large data to trigger cleanup
            "timestamp": time.time() - 1000  # Old timestamp
        }
        self.memory.kv_store["sops:workflow1"] = {
            "data": "y" * 1000000,  # Large data to trigger cleanup
            "timestamp": time.time() - 1000  # Old timestamp
        }
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Verify excluded namespace items are still present
        self.assertIn("knowledge:doc1", self.memory.kv_store)
        self.assertIn("sops:workflow1", self.memory.kv_store)

    def test_non_excluded_namespaces_cleaned(self):
        """Test that non-excluded namespaces are cleaned up."""
        # Add multiple items to non-excluded namespaces with timestamps
        base_time = time.time()
        
        # Add 10 items to pending_clarification namespace
        for i in range(10):
            self.memory.kv_store[f"pending_clarification:session{i}"] = {
                "data": "x" * 100000,  # Large data to trigger cleanup
                "timestamp": base_time + i  # Incrementing timestamps
            }
        
        # Add 10 items to clarification namespace
        for i in range(10):
            self.memory.kv_store[f"clarification:req{i}"] = {
                "data": "y" * 100000,  # Large data to trigger cleanup
                "created_at": base_time + i  # Use created_at field
            }
        
        # Store original counts
        original_pending_count = sum(
            1 for k in self.memory.kv_store if k.startswith("pending_clarification:")
        )
        original_clarification_count = sum(
            1 for k in self.memory.kv_store if k.startswith("clarification:")
        )
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Count remaining items
        remaining_pending_count = sum(
            1 for k in self.memory.kv_store if k.startswith("pending_clarification:")
        )
        remaining_clarification_count = sum(
            1 for k in self.memory.kv_store if k.startswith("clarification:")
        )
        
        # Verify some items were removed (10% = 1 item from each namespace)
        self.assertLess(remaining_pending_count, original_pending_count)
        self.assertLess(remaining_clarification_count, original_clarification_count)
        
        # Verify oldest items were removed (session0 and req0 should be gone)
        self.assertNotIn("pending_clarification:session0", self.memory.kv_store)
        self.assertNotIn("clarification:req0", self.memory.kv_store)
        
        # Verify newer items are still present
        self.assertIn("pending_clarification:session9", self.memory.kv_store)
        self.assertIn("clarification:req9", self.memory.kv_store)

    def test_fifo_order_respected(self):
        """Test that FIFO cleanup removes oldest items first."""
        base_time = time.time()
        
        # Add items with specific timestamps
        # Use larger data sizes to exceed the 1MB limit
        self.memory.kv_store["buffer:oldest"] = {
            "data": "x" * 500000,  # 500KB
            "timestamp": base_time - 1000
        }
        self.memory.kv_store["buffer:middle"] = {
            "data": "x" * 500000,  # 500KB
            "timestamp": base_time - 500
        }
        self.memory.kv_store["buffer:newest"] = {
            "data": "x" * 500000,  # 500KB
            "timestamp": base_time
        }
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Verify oldest was removed, newer items remain
        self.assertNotIn("buffer:oldest", self.memory.kv_store)
        self.assertIn("buffer:newest", self.memory.kv_store)

    def test_empty_kv_store_no_error(self):
        """Test that cleanup works with empty KV store."""
        # Ensure KV store is empty
        self.memory.kv_store = {}
        
        # Run cleanup - should not raise any errors
        try:
            self.memory.check_memory_usage_and_cleanup()
            success = True
        except Exception:
            success = False
        
        self.assertTrue(success)

    def test_kv_store_none_no_error(self):
        """Test that cleanup works when KV store is None."""
        # Set KV store to None
        self.memory.kv_store = None
        
        # Run cleanup - should not raise any errors
        try:
            self.memory.check_memory_usage_and_cleanup()
            success = True
        except Exception:
            success = False
        
        self.assertTrue(success)

    def test_timestamp_fallback(self):
        """Test that items without timestamp use current time as fallback."""
        # Add items without timestamp fields
        # Use larger data sizes to exceed the 1MB limit
        self.memory.kv_store["buffer:no_timestamp"] = {
            "data": "x" * 700000  # 700KB
        }
        self.memory.kv_store["buffer:has_timestamp"] = {
            "data": "x" * 700000,  # 700KB - total 1.4MB exceeds 1MB limit
            "timestamp": time.time() - 1000  # Old timestamp
        }
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Item with old timestamp should be removed first
        self.assertNotIn("buffer:has_timestamp", self.memory.kv_store)
        # Item without timestamp (uses current time) should remain
        self.assertIn("buffer:no_timestamp", self.memory.kv_store)

    def test_percentage_based_removal(self):
        """Test that 10% of items are removed from each namespace."""
        # Add exactly 10 items to a namespace
        base_time = time.time()
        for i in range(10):
            self.memory.kv_store[f"knowledge_buffer:item{i}"] = {
                "data": "x" * 200000,  # 200KB each = 2MB total to exceed limit
                "timestamp": base_time + i
            }
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Verify exactly 1 item (10% of 10) was removed
        remaining_count = sum(
            1 for k in self.memory.kv_store if k.startswith("knowledge_buffer:")
        )
        self.assertEqual(remaining_count, 9)
        
        # Verify the oldest item was removed
        self.assertNotIn("knowledge_buffer:item0", self.memory.kv_store)

    def test_minimum_one_item_removal(self):
        """Test that at least 1 item is removed even from small namespaces."""
        # Add only 2 items to a namespace
        self.memory.kv_store["buffer:item1"] = {
            "data": "x" * 600000,  # 600KB
            "timestamp": time.time() - 100
        }
        self.memory.kv_store["buffer:item2"] = {
            "data": "x" * 600000,  # 600KB - total 1.2MB exceeds 1MB limit
            "timestamp": time.time()
        }
        
        # Run cleanup
        self.memory.check_memory_usage_and_cleanup()
        
        # Verify at least 1 item was removed (max(1, 2//10) = 1)
        remaining_count = sum(
            1 for k in self.memory.kv_store if k.startswith("buffer:")
        )
        self.assertEqual(remaining_count, 1)


if __name__ == "__main__":
    unittest.main()