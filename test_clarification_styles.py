"""Test clarification with different styles."""

import asyncio
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test_style(style_name):
    """Test with a specific style."""
    try:
        # Create a temporary formation config with the specified style
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        config_path = formation_path / "formation.yaml"
        
        # Read existing config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Update clarification style
        if 'overlord' not in config:
            config['overlord'] = {}
        if 'clarification' not in config['overlord']:
            config['overlord']['clarification'] = {}
        config['overlord']['clarification']['style'] = style_name
        
        # Write temporary config
        temp_config = formation_path / f"formation_{style_name}.yaml"
        with open(temp_config, 'w') as f:
            yaml.dump(config, f)
        
        print(f"\n=== Testing {style_name.upper()} style ===")
        
        # Load formation with updated config
        formation = Formation()
        # The load method doesn't support config_file parameter, so we need to use the temp file path
        await formation.load(str(formation_path))
        
        overlord = await formation.start_overlord()
        
        # Test with vague scraper request
        response = await overlord.chat(
            message="I need help with a scraper",
            user_id=f"test_user_{style_name}",
            session_id=f"test_session_{style_name}",
            stream=False
        )
        
        print(f"Response: {response.content}")
        
        # Clean up temp config
        temp_config.unlink()
        
    except Exception as e:
        print(f"Error testing {style_name}: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Test all three styles."""
    for style in ["conversational", "formal", "brief"]:
        await test_style(style)
    
    print("\n=== Style Comparison Complete ===")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())