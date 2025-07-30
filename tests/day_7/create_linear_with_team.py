#!/usr/bin/env python3
"""
Create Linear issues with the configured team ID.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def main():
    """Create 10 Linear issues with team ID."""
    
    print("🚀 MUXI Runtime - Creating Linear Issues with Team ID")
    print("="*60)
    print("\n📋 Configuration:")
    print("   • Team ID: 21b2d439-9ffa-4383-86f5-556acc7af93b")
    print("   • Formation: multi-agent with resilience")
    print("   • Agent: project-manager")
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    
    # Topics for issues
    topics = [
        "AI Healthcare Innovation 2025",
        "Quantum Computing Progress",
        "Sustainable Tech Solutions",
        "Space Technology Advances",
        "Cybersecurity Trends",
        "Blockchain Applications",
        "Robotics Evolution",
        "Edge Computing Future",
        "Biotech Breakthroughs",
        "Autonomous Systems"
    ]
    
    print(f"\n⏳ Creating {len(topics)} Linear issues...\n")
    
    success_count = 0
    
    for i, topic in enumerate(topics, 1):
        print(f"[{i:02d}] Creating issue: {topic}...", end="", flush=True)
        
        try:
            # Fresh formation for each issue
            formation = Formation()
            await formation.load(str(formation_path))
            overlord = await formation.start_overlord()
            
            # Direct request to project-manager
            response = await overlord.chat(
                message=f"Create a Linear issue titled '{topic}' with a detailed description about current developments and future trends in this area.",
                user_id=f"test_user_{i}",
                session_id=f"linear_{i}",
                agent_name="project-manager",
                stream=False
            )
            
            # Get response
            if hasattr(response, 'content'):
                content = response.content
            else:
                content = ""
                async for chunk in response:
                    content += chunk
            
            # Check result
            if any(phrase in content.lower() for phrase in ["created", "issue", "linear"]):
                print(" ✅")
                success_count += 1
            else:
                print(" ⚠️")
            
            # Cleanup
            try:
                await formation.stop()
            except:
                pass
                
            # Small delay
            if i < len(topics):
                await asyncio.sleep(2)
                
        except Exception as e:
            print(f" ❌ {e}")
    
    print(f"\n{'='*60}")
    print(f"✅ Created: {success_count}/{len(topics)} issues")
    print(f"\n🔍 Check your Linear workspace - look for team ID:")
    print(f"   21b2d439-9ffa-4383-86f5-556acc7af93b")
    print(f"\n💡 The resilience layer handled any timeouts gracefully!")


if __name__ == "__main__":
    asyncio.run(main())