"""
Minimal test to check configuration loading without starting overlord.
"""
import yaml
from pathlib import Path


def test_minimal_yaml_loading():
    """Test that we can at least load the YAML file"""
    formation_path = Path(str(Path(__file__).parent / "formations" / "formation-basic" / "formation.yaml"))

    print(f"\nChecking if formation file exists: {formation_path}")
    assert formation_path.exists(), f"Formation file not found: {formation_path}"

    print("Loading YAML content...")
    with open(formation_path, 'r') as f:
        config = yaml.safe_load(f)

    print("✓ YAML loaded successfully!")
    print(f"Config keys: {list(config.keys())}")
    print(f"Schema: {config.get('schema')}")
    print(f"ID: {config.get('id')}")

    # Check required fields
    assert config.get('schema') == "1.0.0"
    assert config.get('id') == "basic-test-formation"
    assert 'llm' in config
    assert 'memory' in config

    print("\n✓ All basic checks passed!")


if __name__ == "__main__":
    test_minimal_yaml_loading()
