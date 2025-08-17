"""Test 8B E-commerce Check: Direct Test of Context Statement

Tests exactly what happens when user provides context about working on an e-commerce platform.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_ecommerce_statement():
    """Test the exact e-commerce statement from 8b1."""
    try:
        print("\n=== Test 8B E-commerce Statement Check ===\n")
        
        # Load formation with clarification capabilities
        formation_path = Path(__file__).parent / "formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path / "formation.yaml"))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        # Create unique test context
        ctx = TestContext("test_8b_ecommerce")
        print(f"Using unique IDs - User: {ctx.user_id}, Session: {ctx.session_id}")
        
        # Test 1: The exact statement from 8b1
        print("\n1. Testing e-commerce platform statement...")
        response1 = await overlord.chat(
            message="I'm working on an e-commerce platform using React and Node.js",
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
        
        print(f"\nUser: I'm working on an e-commerce platform using React and Node.js")
        print(f"System: {content1}\n")
        
        # Analysis
        print("=" * 40)
        print("Analysis:")
        
        response_lower = content1.lower()
        
        # Check for error messages
        has_error = "error" in response_lower or "access" in response_lower or "denied" in response_lower
        
        # Check for actual clarification requests (not just conversational uses of these words)
        asks_clarification = any(phrase in response_lower for phrase in [
            "what specific",
            "what particular",
            "which specific",
            "could you clarify",
            "can you clarify",
            "could you provide more",
            "can you provide more",
            "what are you looking for",
            "what do you need help with",
            "what would you like"
        ])
        
        # Check for acknowledgment
        has_acknowledgment = any(word in response_lower for word in ["great", "help", "assist", "nice", "cool", "awesome", "good"])
        
        if has_error:
            print("❌ PROBLEM: Response contains error messages")
            print("   This is inappropriate for a simple context statement")
        
        if asks_clarification:
            print("⚠️ ISSUE: System asks for clarification")
            print("   No clarification needed - user is just providing context")
        
        if has_acknowledgment:
            print("✅ GOOD: System acknowledges the context")
        else:
            print("⚠️ MISSING: No acknowledgment of the provided context")
        
        # Test 2: Follow-up question
        print("\n" + "=" * 40)
        print("\n2. Testing follow-up question...")
        response2 = await overlord.chat(
            message="What database should I use?",
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
        
        print(f"\nUser: What database should I use?")
        print(f"System: {content2}\n")
        
        response_lower = content2.lower()
        
        # Check if context was maintained
        mentions_ecommerce = any(term in response_lower for term in ["e-commerce", "ecommerce", "shop", "store", "product", "order"])
        mentions_tech = any(term in response_lower for term in ["react", "node", "javascript"])
        # More specific check - only flag if actually asking what project they're working on
        asks_what_project = any(phrase in response_lower for phrase in [
            "what project are you",
            "what application are you", 
            "what are you working on",
            "what kind of project",
            "what type of application",
            "tell me about your project",
            "describe your project"
        ])
        
        print("Analysis:")
        if asks_what_project:
            print("❌ FAILURE: System asks what project - context was lost!")
            print("   User already said they're working on an e-commerce platform")
        
        if mentions_ecommerce:
            print("✅ GOOD: Response mentions e-commerce context")
        else:
            print("⚠️ MISSING: No reference to e-commerce")
        
        if mentions_tech:
            print("✅ GOOD: Response mentions React/Node.js stack")
        else:
            print("⚠️ MISSING: No reference to the tech stack")
        
        # Provide database recommendations check
        has_db_recommendation = any(db in response_lower for db in ["postgres", "mysql", "mongodb", "redis", "dynamodb"])
        if has_db_recommendation:
            print("✅ GOOD: Database recommendations provided")
        else:
            print("⚠️ MISSING: No specific database recommendations")
        
        print("\n" + "=" * 40)
        print("\n### Summary:")
        print("The system should:")
        print("1. Acknowledge context statements without asking for clarification")
        print("2. Maintain context for follow-up questions")
        print("3. Provide relevant recommendations based on the established context")
        print("\nCurrent behavior:")
        if has_error:
            print("- ❌ Returns errors for simple context statements")
        if asks_clarification and not has_acknowledgment:
            print("- ❌ Asks for unnecessary clarification")
        if asks_what_project:
            print("- ❌ Loses context between messages")
        if not has_db_recommendation:
            print("- ❌ Fails to provide contextual recommendations")
        
        print("\n" + "=" * 40)
        
        # Final Summary with Chat Transcript
        print("\n" + "=" * 40)
        print("\n### Test Result:")
        
        # Determine success/failure based on all criteria
        test_passed = (
            not has_error and 
            not asks_clarification and 
            not asks_what_project and 
            has_db_recommendation and
            (mentions_ecommerce or mentions_tech)
        )
        
        if test_passed:
            print("  🎉 SUCCESS: System handles context statements properly")
            print("  ✓ Acknowledges context without unnecessary clarification")
            print("  ✓ Maintains e-commerce/tech stack context")
            print("  ✓ Provides relevant database recommendations")
        else:
            print("  ❌ FAILURE: Context handling issues detected")
            if has_error:
                print("  ✗ Returns errors for context statements")
            if asks_clarification:
                print("  ✗ Asks for unnecessary clarification")
            if asks_what_project:
                print("  ✗ Loses context between messages")
            if not has_db_recommendation:
                print("  ✗ No database recommendations provided")
            if not mentions_ecommerce and not mentions_tech:
                print("  ✗ Does not maintain tech context")
        
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f"\nUser: I'm working on an e-commerce platform using React and Node.js")
        print(f"System: {content1}")
        print(f"\nUser: What database should I use?")
        print(f"System: {content2}")
        
        print("\n" + "=" * 40)
        
        # Properly shut down to prevent timeout
        await formation.stop_overlord()
        formation.shutdown()
        
        return test_passed
        
    except Exception as e:
        print(f"\n❌ Test E-commerce Check FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to shut down even on failure
        if 'formation' in locals():
            try:
                await formation.stop_overlord()
                formation.shutdown()
            except Exception:
                pass
        
        return False


if __name__ == "__main__":
    asyncio.run(test_ecommerce_statement())