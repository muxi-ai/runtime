#!/usr/bin/env python3
"""Test formation capability-based model resolution"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, '../..')  # noqa: E402

from src.muxi.overlord import Overlord  # noqa: E402


async def test_formation_capabilities():
    """Test that formation configurations work with capability-based model resolution"""
    print("🧪 Testing Formation Capability-Based Model Resolution")

    # Test both formations
    formations = ["formation1", "formation2"]

    for formation_name in formations:
        print(f"\n📁 Testing {formation_name}...")
        formation_path = Path(formation_name)

        try:
            # Create overlord with formation path
            overlord = Overlord(formation_path=str(formation_path))
            await overlord.load_formation_from_path(formation_path / "formation.yaml")

            # Check that formation config was loaded
            if overlord.formation_config:
                print("  ✅ Formation config loaded successfully")

                # Check LLM configuration
                llm_config = overlord.formation_config.get("llm", {})
                if llm_config:
                    print("  ✅ LLM config found")

                    # Check models configuration
                    models = llm_config.get("models", [])
                    print(f"  📋 Found {len(models)} configured models:")
                    for model in models:
                        print(f"     - {model}")

                    # Test capability resolution
                    print("  🔍 Testing capability resolution:")
                    capabilities = ["text", "vision", "embedding", "transcription", "documents"]

                    for capability in capabilities:
                        try:
                            model = await overlord.get_model_for_capability(capability)
                            print(f"    ✅ {capability}: {model}")
                        except Exception as e:
                            print(f"    ❌ {capability}: {e}")

                else:
                    print("  ❌ No LLM config found in formation")
            else:
                print("  ❌ Failed to load formation config")

        except Exception as e:
            print(f"  ❌ Error testing {formation_name}: {e}")

    print("\n✅ Formation capability testing completed!")


if __name__ == "__main__":
    asyncio.run(test_formation_capabilities())
