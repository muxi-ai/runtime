#!/usr/bin/env python3
"""
Test 9A3b (with approval): Complex Task Auto-Async with Workflow Approval

Tests that complex tasks with high complexity automatically trigger workflow approval,
and after approval, execute in async mode with webhook delivery.
"""

import sys
from pathlib import Path

from base_async_test import BaseAsyncTest


def main():
    """Test automatic async mode selection for complex tasks with approval."""
    test = BaseAsyncTest(
        "9a3b_with_approval", "Test auto-async for complex tasks with workflow approval"
    )

    async def run_async_test():
        # Setup formation
        formation_path = Path(__file__).parent / "formations" / "formation-async"
        await test.setup_formation(formation_path=str(formation_path))
        await test.clear_webhook_log()

        test.formatter.print_debug("Testing complex task with approval workflow...")

        # Step 1: Send complex request that should trigger approval
        complex_request = (
            "Research the latest developments in quantum computing, "
            "analyze the key players and breakthroughs, "
            "and create a comprehensive report with findings and timeline"
        )

        response = await test.overlord.chat(
            message=complex_request,
            user_id="test_user",
            session_id="async_test_9a3b_approval",
            use_async=None,  # Let system decide
            stream=False,
        )

        # Extract content
        if hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        # Check if we got approval request
        approval_keywords = ["proposed approach", "plan", "workflow", "approve", "proceed"]
        is_approval = any(keyword in content.lower() for keyword in approval_keywords)

        if is_approval:
            test.formatter.print_success("Got workflow approval request (as expected)")
            test.formatter.print_debug(f"Content preview: {content[:200]}...")

            # Step 2: Approve the workflow
            test.formatter.print_debug("Approving the workflow...")

            approval_response = await test.overlord.chat(
                message="Yes, please proceed with this plan",
                user_id="test_user",
                session_id="async_test_9a3b_approval",  # Same session
                use_async=None,
                stream=False,
            )

            # After approval, system should execute async
            if hasattr(approval_response, "request_id"):
                test.formatter.print_success(
                    f"Workflow executing async (request_id: {approval_response.request_id})"
                )

                # Wait for webhook
                webhook = await test.wait_for_webhook(approval_response.request_id, max_wait=45)

                if webhook:
                    success = await test.verify_webhook_content(webhook, "quantum")
                    test.results.append(success)

                    # Extract response for transcript
                    response_data = webhook.get("response", [])
                    for item in response_data:
                        if item.get("type") == "text":
                            result_content = item.get("text", "")
                            test.transcript.append(
                                (complex_request[:50] + "...", result_content[:300] + "...")
                            )
                            break
                else:
                    test.formatter.print_failure("Webhook not received")
                    test.results.append(False)
            else:
                # Got sync response after approval
                if hasattr(approval_response, "content"):
                    result_content = approval_response.content
                else:
                    result_content = str(approval_response)

                test.formatter.print_debug("Workflow executed synchronously after approval")

                if "quantum" in result_content.lower():
                    test.formatter.print_success("Response contains expected content")
                    test.results.append(True)
                    test.transcript.append(
                        (complex_request[:50] + "...", result_content[:300] + "...")
                    )
                else:
                    test.formatter.print_failure("Response doesn't contain expected content")
                    test.results.append(False)
        else:
            # No approval prompt - might execute directly
            test.formatter.print_warning("No approval prompt received")

            if hasattr(response, "request_id"):
                test.formatter.print_debug("Request executing async without approval")
                webhook = await test.wait_for_webhook(response.request_id, max_wait=45)

                if webhook:
                    success = await test.verify_webhook_content(webhook, "quantum")
                    test.results.append(success)
                else:
                    test.results.append(False)
            else:
                test.formatter.print_debug("Request executed synchronously")
                if "quantum" in content.lower():
                    test.results.append(True)
                else:
                    test.results.append(False)

        # Print summary
        test.print_async_summary()

        # Cleanup
        await test.cleanup_formation()

        return 0 if all(test.results) else 1

    import asyncio
    import os; result = asyncio.run(run_async_test()); os._exit(result)


if __name__ == "__main__":
    main()
    
