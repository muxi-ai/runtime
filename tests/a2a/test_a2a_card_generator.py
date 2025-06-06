#!/usr/bin/env python3
"""
Test script for A2A Agent Card Generator

This script tests the functionality of generating A2A agent cards from existing
MUXI agent configurations.
"""

import sys
from pathlib import Path

# Add the runtime to the path from tests directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.a2a.card_generator import AgentCardGenerator  # noqa: E402
from muxi.runtime.a2a.cache_manager import A2ACacheManager  # noqa: E402


def test_basic_card_generation():
    """Test basic agent card generation from existing configs"""

    # Initialize generator with cache
    cache_manager = A2ACacheManager()
    generator = AgentCardGenerator(cache_manager)

    # Test with existing agent configs (relative to runtime root)
    config_dir = Path("../examples/configs")
    if not config_dir.exists():
        print(f"Config directory {config_dir} not found")
        return False

    # Test with assistant.yaml
    assistant_config = config_dir / "assistant.yaml"
    if assistant_config.exists():
        print(f"Testing card generation with {assistant_config}")

        try:
            # Generate agent card
            card = generator.generate_agent_card(
                config_path=assistant_config,
                base_url="http://localhost:8000",
                formation_name="test_formation"
            )

            print(f"✅ Generated card for agent: {card.name}")
            print(f"   ID: {card.muxi_agent_id}")
            print(f"   Description: {card.description}")
            print(f"   URL: {card.url}")
            print(f"   Capabilities: {len(card.capabilities)}")
            print(f"   Endpoints: {len(card.endpoints)}")

            # Print capabilities
            print("\n   Capabilities:")
            for cap in card.capabilities:
                if hasattr(cap, 'name') and hasattr(cap, 'description'):
                    print(f"     - {cap.name}: {cap.description}")
                else:
                    print(f"     - {cap}")  # Handle string capabilities

            # Print endpoints
            print("\n   Endpoints:")
            for name, endpoint in card.endpoints.items():
                print(f"     - {name}: {endpoint.url}")

            # Test JSON serialization
            card_json = card.to_json(indent=2)
            print(f"\n   JSON serialization: {len(card_json)} characters")

            # Test caching
            print("\n   Testing cache...")
            generator.generate_agent_card(
                config_path=assistant_config,
                base_url="http://localhost:8000",
                formation_name="test_formation"
            )
            print("   Second generation successful (should use cache)")

            return True

        except Exception as e:
            print(f"❌ Error generating card: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"Assistant config {assistant_config} not found")
        return False


def test_formation_card_generation():
    """Test generating cards for all agents in a formation"""

    generator = AgentCardGenerator()
    config_dir = Path("../examples/configs")

    if not config_dir.exists():
        print(f"Config directory {config_dir} not found")
        return False

    try:
        print(f"\nTesting formation card generation from {config_dir}")

        # Generate cards for all agents
        cards = generator.generate_cards_for_formation(
            config_dir=config_dir,
            base_url="http://localhost:8000",
            formation_name="test_formation"
        )

        print(f"✅ Generated {len(cards)} agent cards:")
        for agent_id, card in cards.items():
            print(f"   - {agent_id}: {card.name}")

        # Test export
        output_dir = Path("../.cache/test_cards")
        generator.export_cards_to_directory(cards, output_dir)
        print(f"✅ Exported cards to {output_dir}")

        # List exported files
        exported_files = list(output_dir.glob("*.json"))
        print(f"   Exported files: {[f.name for f in exported_files]}")

        return True

    except Exception as e:
        print(f"❌ Error in formation card generation: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_functionality():
    """Test the caching functionality"""

    print("\nTesting cache functionality...")

    cache_manager = A2ACacheManager()

    # Test config hash computation
    test_config = {
        "name": "test_agent",
        "description": "Test agent description"
    }

    hash1 = cache_manager._compute_config_hash(test_config)
    hash2 = cache_manager._compute_config_hash(test_config)

    if hash1 == hash2:
        print(f"✅ Config hash is consistent: {hash1[:8]}...")
    else:
        print(f"❌ Config hash inconsistent: {hash1[:8]} != {hash2[:8]}")
        return False

    # Test with different config
    test_config2 = {
        "name": "test_agent",
        "description": "Different description"
    }

    hash3 = cache_manager._compute_config_hash(test_config2)

    if hash1 != hash3:
        print("✅ Different configs produce different hashes")
    else:
        print("❌ Different configs produced same hash")
        return False

    print("✅ Cache functionality working correctly")
    return True


def main():
    """Run all tests"""

    print("🚀 Testing A2A Agent Card Generator")
    print("=" * 50)

    # Run tests
    tests = [
        ("Basic Card Generation", test_basic_card_generation),
        ("Formation Card Generation", test_formation_card_generation),
        ("Cache Functionality", test_cache_functionality)
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n📝 {test_name}")
        print("-" * 30)
        results[test_name] = test_func()

    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Agent Card Generator is working correctly.")
        return 0
    else:
        print("🚨 Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
