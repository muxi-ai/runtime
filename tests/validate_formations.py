#!/usr/bin/env python3
"""
Validate that test formations can be loaded by the Formation class.
"""

import sys
import asyncio
from pathlib import Path
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from muxi.runtime.formation import Formation


async def validate_formation(formation_dir: Path) -> bool:
    """Validate a single formation can be loaded."""
    print(f"\n🔍 Validating formation: {formation_dir.name}")
    
    try:
        # Check formation.yaml exists
        formation_yaml = formation_dir / "formation.yaml"
        if not formation_yaml.exists():
            print(f"  ❌ Missing formation.yaml")
            return False
            
        # Load and validate YAML structure
        with open(formation_yaml) as f:
            config = yaml.safe_load(f)
            
        # Check required fields
        required_fields = ["schema", "id", "description"]
        for field in required_fields:
            if field not in config:
                print(f"  ❌ Missing required field: {field}")
                return False
                
        print(f"  ✅ Schema version: {config['schema']}")
        print(f"  ✅ Formation ID: {config['id']}")
        
        # Check for agents
        agent_dir = formation_dir / "agents"
        if agent_dir.exists():
            agents = list(agent_dir.glob("*.yaml"))
            print(f"  ✅ Found {len(agents)} agent(s)")
            
        # Check for MCP servers
        mcp_dir = formation_dir / "mcp"
        if mcp_dir.exists():
            mcps = list(mcp_dir.glob("*.yaml"))
            print(f"  ✅ Found {len(mcps)} MCP server(s)")
            
        # Check for A2A services
        a2a_dir = formation_dir / "a2a"
        if a2a_dir.exists():
            a2as = list(a2a_dir.glob("*.yaml"))
            print(f"  ✅ Found {len(a2as)} A2A service(s)")
            
        # Try to create Formation instance
        formation = Formation(formation_dir)
        print(f"  ✅ Formation instance created successfully")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


async def main():
    """Validate all test formations."""
    print("🚀 Validating test formations...")
    
    test_formations_dir = Path(__file__).parent.parent / "test-formations"
    if not test_formations_dir.exists():
        print(f"❌ Test formations directory not found: {test_formations_dir}")
        return 1
        
    # Find all formation directories
    formations = [d for d in test_formations_dir.iterdir() 
                 if d.is_dir() and d.name.startswith("formation-")]
    
    if not formations:
        print("❌ No test formations found")
        return 1
        
    print(f"📂 Found {len(formations)} test formation(s)")
    
    # Validate each formation
    results = []
    for formation_dir in sorted(formations):
        result = await validate_formation(formation_dir)
        results.append((formation_dir.name, result))
        
    # Summary
    print("\n📊 Validation Summary:")
    print("-" * 40)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:30} {status}")
        if result:
            passed += 1
            
    print("-" * 40)
    print(f"Total: {passed}/{len(results)} passed")
    
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)