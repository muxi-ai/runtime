#!/usr/bin/env python3
"""
Test 9A3b-with-approval: Complex Task Auto-Async Mode with Approval
Tests that complex tasks with high complexity automatically use async mode AFTER approval.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def run_test():
    """Test automatic async mode selection for complex tasks with approval."""
    formation_path = Path(__file__).parent / "formation-async"
    webhook_log = Path.cwd() / "webhook_log.json"

    # Clear webhook log before test
    if webhook_log.exists():
        webhook_log.unlink()

    # Load formation
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    try:
        print("\n✅ Formation loaded (webhook configured)")
        print(f"   Webhook URL: {overlord.async_webhook_url}")

        # Step 1: Send complex request that should trigger workflow with approval
        print("📋 Testing complex task that should require approval...")

        # Increased complexity for workflow trigger
        complex_request = """
        Research the latest developments in quantum computing,
        analyze the key players and breakthroughs,
        and create a comprehensive Linear issue with findings, timeline, and future predictions.
        """

        start_time = time.time()

        # Send initial request - should get approval prompt
        response = await overlord.chat(
            message=complex_request,
            user_id="test_user",
            session_id="async_test_9a3b_approval",
            use_async=None,  # Let system decide
            stream=False,    # Force no streaming to enable workflow analysis
        )

        response_time = time.time() - start_time

        print(f"\n⏱️ Initial response time: {response_time:.2f}s")

        # Check if we got approval request
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = str(response)

        if "proposed approach" in content.lower() or "plan" in content.lower() or "workflow" in content.lower():
            print("✅ Got workflow approval request (as expected)")
            print(f"   Content preview: {content[:200]}...")

            # Step 2: Approve the workflow
            print("\n📋 Approving the workflow...")

            approval_start = time.time()

            approval_response = await overlord.chat(
                message="Yes, please proceed with this plan",
                user_id="test_user",
                session_id="async_test_9a3b_approval",  # Same session to maintain context
                use_async=None,  # Let system use stored intent
                stream=False,    # Force no streaming for approval response
            )

            approval_time = time.time() - approval_start
            print(f"⏱️ Approval response time: {approval_time:.2f}s")

            # Check the response type
            if hasattr(approval_response, 'content'):
                approval_content = approval_response.content
                # For async responses, the content might be a string representation of a dict
                if isinstance(approval_content, dict):
                    approval_dict = approval_content
                elif isinstance(approval_content, str) and approval_content.startswith('{'):
                    # Try to parse as JSON/dict
                    try:
                        import ast
                        approval_dict = ast.literal_eval(approval_content)
                    except (ValueError, SyntaxError):
                        approval_dict = None
                else:
                    approval_dict = approval_response if isinstance(approval_response, dict) else None
            else:
                approval_content = str(approval_response)
                approval_dict = approval_response if isinstance(approval_response, dict) else None

            # Check if response indicates async processing
            if approval_dict and approval_dict.get('status') == 'processing':
                print("🚀 Got async processing response after approval!")
                print(f"   Request ID: {approval_dict.get('request_id')}")
                print(f"   Status: {approval_dict.get('status')}")
                print(f"   Message: {approval_dict.get('message')}")
                # The webhook URL is not returned in the response, but we know it's configured
                print(f"   Webhook URL: {overlord.async_webhook_url}")

                # Step 3: Wait for REAL async execution (3-6 minutes expected)
                print("\n⏳ Waiting for async workflow execution...")
                print("   This involves: web research → content analysis → article writing → Linear posting")
                print("   Expected time: 3-6 minutes")

                max_wait_time = 600  # 10 minutes max wait
                check_interval = 15   # Check every 15 seconds
                total_waited = 0
                webhook_received = False

                while total_waited < max_wait_time and not webhook_received:
                    await asyncio.sleep(check_interval)
                    total_waited += check_interval

                    print(f"   ⏳ Waited {total_waited//60}m {total_waited%60}s...")

                    # Check webhook log
                    if webhook_log.exists():
                        try:
                            with open(webhook_log, 'r') as f:
                                # Parse JSONL format
                                webhook_entries = []
                                for line in f:
                                    line = line.strip()
                                    if line:
                                        try:
                                            webhook_entries.append(json.loads(line))
                                        except json.JSONDecodeError:
                                            pass

                            if webhook_entries:
                                # Check if we have a webhook for this request
                                request_id = approval_dict.get('request_id')
                                for entry in webhook_entries:
                                    if entry.get('body', {}).get('request_id') == request_id:
                                        webhook_received = True
                                        latest_webhook = entry.get('body', {})
                                        break
                        except Exception as e:
                            print(f"   Error reading webhook log: {e}")

                # Final webhook check after timeout (in case webhook arrived at boundary)
                if not webhook_received and webhook_log.exists():
                    print("   🔍 Final webhook check...")
                    try:
                        with open(webhook_log, 'r') as f:
                            webhook_entries = []
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        webhook_entries.append(json.loads(line))
                                    except json.JSONDecodeError:
                                        pass

                        if webhook_entries:
                            request_id = approval_dict.get('request_id')
                            for entry in webhook_entries:
                                if entry.get('body', {}).get('request_id') == request_id:
                                    webhook_received = True
                                    latest_webhook = entry.get('body', {})
                                    total_waited = max_wait_time  # Use max time for display
                                    print("   ✅ Webhook found in final check!")
                                    break
                    except Exception as e:
                        print(f"   Error in final webhook check: {e}")

                # Report results
                if webhook_received:
                    execution_time = total_waited
                    print(f"\n✅ Webhook received after {execution_time//60}m {execution_time%60}s!")
                    print(f"   Request ID: {latest_webhook.get('request_id')}")
                    print(f"   Status: {latest_webhook.get('status')}")
                    if 'result' in latest_webhook:
                        result_content = latest_webhook['result']
                        if hasattr(result_content, 'content'):
                            result_preview = str(result_content.content)[:300]
                        else:
                            result_preview = str(result_content)[:300]
                        print(f"   Result preview: {result_preview}...")

                    print("\n============================================================")
                    print(f"✅ Test 9A3b PASSED: Async workflow completed in {execution_time//60}m {execution_time%60}s")
                    print("   • Got approval request: ✅")
                    print("   • Approved workflow: ✅")
                    print("   • Async execution: ✅")
                    print("   • Webhook delivery: ✅")
                    print(f"   • Realistic execution time: ✅ ({execution_time//60}m {execution_time%60}s)")
                else:
                    print(f"\n❌ No webhook received after {max_wait_time//60} minutes")
                    print("   Possible issues:")
                    print("   • Async execution failed")
                    print("   • Webhook delivery failed")
                    print(f"   • Execution taking longer than {max_wait_time//60} minutes")
                    print("   • System error during workflow execution")
                    print("\n============================================================")
                    print("❌ Test 9A3b FAILED: No webhook received for async execution")
            else:
                print(f"📝 Got text response after approval: {approval_content[:200]}...")
                print("   This suggests synchronous execution instead of async")
                print("\n============================================================")
                print("⚠️ Test 9A3b WARNING: Expected async execution but got synchronous response")
        else:
            print(f"❌ Did not get approval request: {content[:200]}...")
            print("\n============================================================")
            print("❌ Test 9A3b with approval FAILED: No approval request for complex task")

    finally:
        print("\nShutting down...")
        try:
            # Try different shutdown methods
            if hasattr(overlord, 'kill_overlord'):
                await overlord.kill_overlord()
            elif hasattr(overlord, 'shutdown'):
                await overlord.shutdown()
        except Exception as e:
            print(f"Error during overlord shutdown: {e}")

        try:
            await formation.shutdown()
        except Exception as e:
            print(f"Error during formation shutdown: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
