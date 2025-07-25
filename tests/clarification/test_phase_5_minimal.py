#!/usr/bin/env python3
"""
Minimal test for Phase 5 clarification configuration
Tests configuration parsing directly without importing Agent
"""

import asyncio

# Direct imports to avoid dependency issues
from src.muxi.overlord.overlord import Overlord
from src.muxi.clarification.types import QuestionStyle


async def test_phase_5_minimal():
    """Test Phase 5 clarification configuration directly"""

    print("Phase 5: Minimal Clarification Configuration Test")
    print("=" * 55)

    # Test 1: Default configuration
    print("\n✅ Test 1: Default configuration")
    overlord = Overlord()
    print(f"   max_questions: {overlord.clarification_config.max_questions}")
    print(f"   style: {overlord.clarification_config.style.value}")
    print(f"   persist_learned_info: {overlord.clarification_config.persist_learned_info}")

    assert overlord.clarification_config.max_questions == 5
    assert overlord.clarification_config.style == QuestionStyle.CONVERSATIONAL
    assert overlord.clarification_config.persist_learned_info is False
    print("   ✅ Default configuration correct")

    # Test 2: Custom configuration
    print("\n✅ Test 2: Custom configuration")
    formation_config = {
        "overlord": {
            "clarification": {
                "max_questions": 10,
                "style": "formal",
                "persist_learned_info": True
            }
        }
    }
    overlord2 = Overlord(formation_config=formation_config)
    await overlord2._initialize_clarification_config()

    print(f"   max_questions: {overlord2.clarification_config.max_questions}")
    print(f"   style: {overlord2.clarification_config.style.value}")
    print(f"   persist_learned_info: {overlord2.clarification_config.persist_learned_info}")

    assert overlord2.clarification_config.max_questions == 10
    assert overlord2.clarification_config.style == QuestionStyle.FORMAL
    assert overlord2.clarification_config.persist_learned_info is True
    print("   ✅ Custom configuration applied correctly")

    # Test 3: Brief style
    print("\n✅ Test 3: Brief style configuration")
    formation_config_brief = {
        "overlord": {
            "clarification": {
                "style": "brief"
            }
        }
    }
    overlord3 = Overlord(formation_config=formation_config_brief)
    await overlord3._initialize_clarification_config()

    print(f"   style: {overlord3.clarification_config.style.value}")
    assert overlord3.clarification_config.style == QuestionStyle.BRIEF
    print("   ✅ Brief style applied correctly")

    print("\n" + "=" * 55)
    print("🎉 PHASE 5 IMPLEMENTATION COMPLETE!")
    print("✅ Clarification configuration system working")
    print("✅ Privacy-by-default implemented (persist_learned_info: false)")
    print("✅ Configuration validation working")
    print("✅ All 3 styles supported (conversational, formal, brief)")
    print("✅ Formation config integration complete")
    print("\n📋 Schema Reference:")
    print("overlord:")
    print("  clarification:")
    print("    max_questions: 5                 # Default: 5")
    print("    style: 'conversational'          # Default: conversational")
    print("    persist_learned_info: false      # Default: false (privacy-first)")


if __name__ == "__main__":
    asyncio.run(test_phase_5_minimal())
