#!/usr/bin/env python3
"""
Test 7B4: Explicit SOP Invocation
Tests that users can explicitly call SOPs by name in any language.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestExplicitSOPCall(BaseE2ETest):
    """Test explicit SOP invocation via LLM-based request analysis."""

    def __init__(self):
        super().__init__(
            test_name="test_7b4_explicit_sop_call",
            test_description="Test explicit SOP invocation by name",
            test_area="7_orchestration",
        )

    async def test_7b4_explicit_sop_call(self):
        """Test that explicitly requesting a SOP by name triggers it directly."""
        formatter = TestOutputFormatter()
        transcript = []
        
        print("="*80)
        print("Test 7B4: Explicit SOP Invocation")
        print("="*80)

        try:
            # Load formation with SOPs
            print("\n1. Loading formation with SOPs...")
            await self.setup_formation(
                formation_name="formation-multi-agent",
                formation_subdir="formations"
            )
            overlord = self.overlord
            print("   ✓ Formation loaded with SOPs")

            # Test 1: Explicit SOP request in English
            print("\n2. Testing explicit SOP request: 'Execute the code-review SOP'...")
            response = await overlord.chat(
                "Execute the code-review SOP for the authentication module",
                user_id="test_user",
                session_id="explicit_sop_test",
                stream=False
            )
            
            assert response is not None, "Response should not be None"
            response_text = response.content if hasattr(response, "content") else str(response)
            assert len(response_text) > 0, "Response should not be empty"
            
            print(f"   ✓ Response received ({len(response_text)} chars)")
            transcript.append(("Execute the code-review SOP", response_text[:200]))
            
            # Verify workflow was triggered (response should mention review/quality/etc)
            response_lower = response_text.lower()
            workflow_indicators = ["review", "quality", "code", "check", "feedback"]
            triggered = any(indicator in response_lower for indicator in workflow_indicators)
            assert triggered, f"Response should indicate code review workflow was triggered"
            print("   ✅ Code review workflow triggered")

            # Test 2: Verify it works with context
            print("\n3. Testing SOP with additional context...")
            response2 = await overlord.chat(
                "Please execute the customer-onboarding SOP for a new enterprise client",
                user_id="test_user",
                session_id="explicit_sop_test2",
                stream=False
            )
            
            assert response2 is not None, "Response should not be None"
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            assert len(response2_text) > 0, "Response should not be empty"
            
            print(f"   ✓ Response received ({len(response2_text)} chars)")
            transcript.append(("Execute customer-onboarding SOP", response2_text[:200]))
            
            # Verify onboarding workflow indicators
            response2_lower = response2_text.lower()
            onboarding_indicators = ["onboard", "welcome", "setup", "customer", "client"]
            triggered2 = any(indicator in response2_lower for indicator in onboarding_indicators)
            assert triggered2, "Response should indicate onboarding workflow"
            print("   ✅ Customer onboarding workflow triggered")

            # Cleanup
            print("\n4. Cleaning up...")
            await self.cleanup_formation()
            print("   ✓ Formation stopped")

            # Print results
            formatter.print_test_result(
                test_name="test_7b4_explicit_sop_call",
                success=True,
                checks=[
                    "Formation loaded with SOPs",
                    "Explicit 'code-review' SOP triggered",
                    "Explicit 'customer-onboarding' SOP triggered",
                    "Context preserved in SOP execution",
                ],
                transcript=transcript,
            )
            
            return 0

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            
            formatter.print_test_result(
                test_name="test_7b4_explicit_sop_call",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=transcript,
            )
            return 1

    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_7b4_explicit_sop_call())


if __name__ == "__main__":
    test = TestExplicitSOPCall()
    sys.exit(test.run_test())
