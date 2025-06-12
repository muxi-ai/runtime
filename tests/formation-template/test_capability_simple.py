#!/usr/bin/env python3
"""Simple test for capability-based model resolution"""

import sys
import asyncio
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.muxi.runtime.overlord import Overlord  # noqa: E402
from src.muxi.runtime.secrets import SecretsManager  # noqa: E402


async def test_capability_resolution():
    """Test the capability-based model resolution system."""
    print("🧪 Testing LLM Capability-Based Model Resolution")
    formation_path = Path("formation1")
    print(f"📁 Testing formation: {formation_path.absolute()}")

    # Initialize SecretsManager
    secrets_manager = SecretsManager(formation_path)
    await secrets_manager.initialize_encryption()

    # Create overlord with formation config
    overlord = Overlord(secrets_manager=secrets_manager)
    await overlord.load_formation_from_path(formation_path / "formation.yaml")

    # Test capability resolution
    print("\\n🔍 Testing capability-based model resolution:")
    capabilities = ["text", "vision", "embedding", "transcription", "documents"]

    for capability in capabilities:
        try:
            model = overlord.get_model_for_capability(capability)
            print(f"  ✅ {capability}: {model}")
        except Exception as e:
            print(f"  ❌ {capability}: {e}")

    # Test that models config was loaded correctly
    print(f"\\n📊 Formation config loaded: {bool(overlord.formation_config)}")
    if overlord.formation_config:
        llm_config = overlord.formation_config.get("llm", {})
        models = llm_config.get("models", [])
        print(f"📋 Configured models: {len(models)} models found")
        for model in models:
            print(f"   - {model}")

    print("\\n✅ Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_capability_resolution())
