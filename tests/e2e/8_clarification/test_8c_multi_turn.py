"""
Test runner for Day 8C: Multiple Clarification Sequences

This script tests the new multi-turn clarification functionality
implemented according to the simplified PRD.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi.formation.overlord import Overlord
from muxi.formation.clarification import ClarificationContext


async def test_simple_rejection_flow():
    """Test a simple rejection and recovery flow."""
    print("\n" + "="*60)
    print("TEST: Simple Rejection Flow")
    print("="*60)
    
    # Test ClarificationContext directly without overlord
    # since we can't easily initialize overlord without a formation
    context = ClarificationContext(
        original_intent="List my GitHub repositories",
        session_id="test_123"
    )
    
    # Simulate rejection scenario
    context.add_qa_pair(
        question="Which account? 1) personal 2) work",
        answer="None of these, I want to add a new account",
        intent_type="REJECT"
    )
    
    print(f"Chain after rejection: {len(context.clarification_chain)} items")
    assert len(context.clarification_chain) == 1
    assert context.clarification_chain[0]["intent_type"] == "REJECT"
    print("✅ Rejection recorded correctly")
    
    # Simulate providing token after rejection
    context.depth = 1  # Sub-clarification
    context.add_param("token", "ghp_abc123def456")
    
    print(f"Params after token: {context.collected_params}")
    assert "token" in context.collected_params
    print("✅ Token parameter collected correctly")
    
    # Test depth tracking
    context.add_qa_pair(
        question="Please provide your GitHub token",
        answer="ghp_abc123def456",
        intent_type="ANSWER"
    )
    
    last_qa = context.clarification_chain[-1]
    print(f"Depth of sub-clarification: {last_qa['depth']}")
    assert last_qa["depth"] == 1
    print("✅ Depth tracking works correctly")
    

async def test_context_management():
    """Test ClarificationContext functionality."""
    print("\n" + "="*60)
    print("TEST: ClarificationContext Management")
    print("="*60)
    
    context = ClarificationContext(
        original_intent="Build a web scraper",
        session_id="test_456"
    )
    
    # Test adding parameters
    context.add_param("url", "example.com")
    context.add_param("data_type", "prices")
    
    print(f"Collected params: {context.collected_params}")
    assert len(context.collected_params) == 2
    print("✅ Parameters collected correctly")
    
    # Test Q&A chain
    context.add_qa_pair(
        question="What website do you want to scrape?",
        answer="example.com",
        intent_type="ANSWER"
    )
    
    print(f"Chain length: {len(context.clarification_chain)}")
    assert len(context.clarification_chain) == 3  # 2 params + 1 Q&A
    print("✅ Q&A chain managed correctly")
    
    # Test depth tracking
    context.depth = 1
    context.add_qa_pair(
        question="What specific data?",
        answer="Product prices",
        intent_type="ANSWER"
    )
    
    last_item = context.clarification_chain[-1]
    print(f"Depth in chain: {last_item.get('depth', 0)}")
    assert last_item["depth"] == 1
    print("✅ Depth tracking works correctly")
    
    # Test can_fulfill
    can_fulfill = context.can_fulfill()
    print(f"Can fulfill: {can_fulfill}")
    assert can_fulfill is True  # We have params
    print("✅ Fulfillment check works correctly")


async def test_conversion_compatibility():
    """Test backward compatibility with old format."""
    print("\n" + "="*60)
    print("TEST: Backward Compatibility")
    print("="*60)
    
    # Test to_dict conversion
    context = ClarificationContext(
        original_intent="Test request",
        session_id="test_789"
    )
    context.add_param("test_param", "test_value")
    
    dict_format = context.to_dict()
    print(f"Dict format keys: {dict_format.keys()}")
    
    assert "original_message" in dict_format
    assert dict_format["type"] == "multi_turn"
    print("✅ Conversion to dict works")
    
    # Test from_dict conversion
    restored = ClarificationContext.from_dict(dict_format, "test_789")
    
    assert restored is not None
    assert restored.original_intent == "Test request"
    assert restored.collected_params == {"test_param": "test_value"}
    print("✅ Restoration from dict works")
    
    # Test with old format (should return None)
    old_format = {
        "type": "credential",
        "original_message": "Old format"
    }
    
    not_restored = ClarificationContext.from_dict(old_format, "test_old")
    assert not_restored is None
    print("✅ Old format correctly returns None")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Day 8C: Multiple Clarification Sequences Tests")
    print("="*60)
    
    try:
        await test_simple_rejection_flow()
        await test_context_management()
        await test_conversion_compatibility()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED! ✅")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)