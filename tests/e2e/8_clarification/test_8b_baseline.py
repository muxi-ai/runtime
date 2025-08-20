"""Test 8B Baseline: Simple Greetings and Statements

Tests how the system responds to basic greetings and informational statements
that don't require clarification.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_baseline_responses():
    """Test responses to simple greetings and statements."""
    try:
        print("\n=== Test 8B Baseline: Simple Greetings and Statements ===\n")
        
        # Load formation with clarification capabilities
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8b_baseline")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Test 1: Simple greeting
        print("\n1. Testing simple greeting...")
        response1 = await overlord.chat(
            message="Hi",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        # Handle different response types
        if isinstance(response1, str):
            content1 = response1
        elif hasattr(response1, 'content'):
            content1 = response1.content
        else:
            content1 = str(response1)
        print(f"   User: Hi")
        print(f"   System: {content1}")
        
        # Test 2: Another greeting
        print("\n2. Testing hello...")
        response2 = await overlord.chat(
            message="Hello there!",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        if isinstance(response2, str):
            content2 = response2
        elif hasattr(response2, 'content'):
            content2 = response2.content
        else:
            content2 = str(response2)
        print(f"   User: Hello there!")
        print(f"   System: {content2}")
        
        # Test 3: Informational statement (no question)
        print("\n3. Testing informational statement...")
        response3 = await overlord.chat(
            message="I'm a software developer",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        if isinstance(response3, str):
            content3 = response3
        elif hasattr(response3, 'content'):
            content3 = response3.content
        else:
            content3 = str(response3)
        print(f"   User: I'm a software developer")
        print(f"   System: {content3}")
        
        # Test 4: Another informational statement
        print("\n4. Testing context-setting statement...")
        response4 = await overlord.chat(
            message="I'm working on a Python project",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            stream=False
        )
        
        if isinstance(response4, str):
            content4 = response4
        elif hasattr(response4, 'content'):
            content4 = response4.content
        else:
            content4 = str(response4)
        print(f"   User: I'm working on a Python project")
        print(f"   System: {content4}")
        
        # Test 5: Now ask a question that should use context
        print("\n5. Testing question that should use context...")
        # Add timeout to prevent hanging
        response5 = await asyncio.wait_for(
            overlord.chat(
                message="What testing framework would you recommend?",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=10.0  # 10 second timeout for this specific call
        )
        
        if isinstance(response5, str):
            content5 = response5
        elif hasattr(response5, 'content'):
            content5 = response5.content
        else:
            content5 = str(response5)
        print(f"   User: What testing framework would you recommend?")
        print(f"   System: {content5}")
        
        # Check if Python context was used
        response_lower = content5.lower()
        mentions_python = any(term in response_lower for term in ["pytest", "unittest", "python", "nose"])
        
        print("\n" + "="*40)
        print("\n### Analysis:")
        print(f"✓ Greeting responses captured")
        print(f"✓ Informational statements processed")
        if mentions_python:
            print(f"✓ Python context was remembered (mentions Python testing frameworks)")
        else:
            print(f"✗ Python context was NOT used (no Python-specific recommendations)")
        
        print("\n### Key Observations:")
        print("1. How does the system respond to simple greetings?")
        print(f"   - 'Hi' → {content1[:100]}...")
        print(f"   - 'Hello there!' → {content2[:100]}...")
        
        print("\n2. How does it handle informational statements?")
        print(f"   - 'I'm a software developer' → {content3[:100]}...")
        print(f"   - 'I'm working on a Python project' → {content4[:100]}...")
        
        print("\n3. Does it maintain context for follow-up questions?")
        print(f"   - Context used: {'Yes' if mentions_python else 'No'}")
        
        print("\n" + "="*40)
        
        # Final Summary with Chat Transcript
        print("\n" + "="*40)
        print("\n### Test Result:")
        
        # Determine success/failure
        test_passed = mentions_python  # Main success criteria
        
        if test_passed:
            print("  🎉 SUCCESS: System maintains context across messages")
            print("  ✓ Responds to greetings appropriately")
            print("  ✓ Processes informational statements")
            print("  ✓ Remembers Python context for recommendations")
        else:
            print("  ❌ FAILURE: Context not maintained properly")
            print("  ✓ Responds to greetings")
            print("  ✓ Processes statements")
            print("  ✗ Does not use Python context for recommendations")
        
        print("\n" + "="*40)
        print("\n### Chat transcript:")
        print(f"\nUser: Hi")
        print(f"System: {content1}")
        print(f"\nUser: Hello there!")
        print(f"System: {content2}")
        print(f"\nUser: I'm a software developer")
        print(f"System: {content3}")
        print(f"\nUser: I'm working on a Python project")
        print(f"System: {content4}")
        print(f"\nUser: What testing framework would you recommend?")
        print(f"System: {content5}")
        
        print("\n" + "="*40)
        
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        
        return test_passed
        
    except Exception as e:
        print(f"\n❌ Test Baseline FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.kill_overlord()
                formation.shutdown()
            except Exception:
                pass
        
        return False
    finally:
        # Ensure test terminates properly
        if 'test_passed' in locals():
            sys.exit(0 if test_passed else 1)
        else:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_baseline_responses())