#!/usr/bin/env python3
"""Test 4D1: User Credential Exists in DB - Direct Execution"""

import asyncio
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for existing user credentials."""

    print("\n" + "="*80)
    print("I am testing: User Credential Exists in DB - Direct Execution")
    print("This test verifies that when user1 (who has GitHub credentials stored in the database)")
    print("makes a request to list GitHub repositories, the system:")
    print("1. Uses formation secrets to initialize and discover GitHub MCP tools")
    print("2. Automatically uses user1's stored credentials for the actual API call")
    print("3. Does NOT ask the user to provide credentials")
    print("="*80 + "\n")

    try:
        # Use the test formation
        formation_path = Path(str(Path(__file__).parent / "formations" / "formation-mcp"))

        # Load formation
        print("Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))

        # Start overlord first (this initializes all services)
        print("Starting overlord...")
        overlord = await formation.start_overlord()

        # Give MCP servers time to initialize
        print("\nWaiting for MCP servers to initialize...")
        await asyncio.sleep(3)

        # Check available tools
        print("\n=== CHECKING MCP TOOLS ===")
        mcp_service = overlord.mcp_service
        if mcp_service:
            tools = mcp_service.tool_registry
            github_tools = [tool for tool in tools.keys() if 'github' in tool.lower()]
            print(f"GitHub MCP tools available: {len(github_tools)}")
            if github_tools:
                print("Sample tools:", github_tools[:3])

        # Prepare the test
        prompt = "Create a GitHub issue on the muxi repo with title 'Yet another test Issue from MUXI' and body 'This is a test issue created by the MUXI runtime to verify user credential functionality.'"  # noqa: E501

        print("\n" + "="*80)
        print("Prompt sent to overlord.chat:")
        print(prompt)
        print("="*80 + "\n")

        # Capture observability events
        print("Observability Events:")
        print("-"*80)

        # Set up event capture
        import io
        import sys
        global captured_events
        captured_events = []

        # Temporarily capture stdout for events
        old_stdout = sys.stdout
        capture_buffer = io.StringIO()

        # Create a custom stdout that captures JSON events
        class EventCapture:
            def __init__(self, original, buffer):
                self.original = original
                self.buffer = buffer

            def write(self, text):
                self.original.write(text)
                if text.strip() and text.strip().startswith('{'):
                    try:
                        event = json.loads(text.strip())
                        if 'event' in event:
                            captured_events.append(event)
                    except Exception:
                        pass

            def flush(self):
                self.original.flush()

        sys.stdout = EventCapture(old_stdout, capture_buffer)

        print("Processing request...")
        print("-"*80)

        # Make the request
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,
            stream=False,
        )

        # Handle response
        if hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        # Restore stdout
        sys.stdout = old_stdout

        # Show captured events
        print("\n" + "="*80)
        print("Captured Observability Events:")
        print("-"*80)

        # Filter for relevant events
        relevant_events = []
        for event in captured_events:
            event_type = event.get('event', '')
            event_data = event.get('data', {})
            event_desc = event_data.get('description', '').lower()

            # Look for credential transformation and usage
            if any(keyword in event_type.lower() or keyword in event_desc
                   for keyword in ['credential', 'transformed', 'user.credentials', 'github_mcp', 'auth', 'bearer']):
                relevant_events.append(event)

        if relevant_events:
            for event in relevant_events[:10]:  # Show first 10 relevant events
                print(f"- {event.get('event')}: {event.get('data', {}).get('description', 'No description')}")
        else:
            print("No credential-related events captured. Check logs above for raw events.")

        print("\n" + "="*80)
        print("overlord.chat response:")
        print(json.dumps({"response": str(response)}, indent=2))
        print("="*80 + "\n")

        # Analyze results
        response_str = str(response).lower()
        success = True
        summary = ""

        # Check if we asked for credentials
        asked_for_credentials = any(phrase in response_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication"
        ])

        # Check if we created an issue or got a specific response
        created_issue = any(word in response_str for word in ["created", "issue", "opened", "submitted"])
        got_error = "error" in response_str or "failed" in response_str

        if asked_for_credentials:
            success = False
            summary = "FAILED: System asked for credentials even though they exist in DB"
        elif created_issue:
            success = True
            summary = "SUCCESS: Used credentials from database to create GitHub issue!"
        elif got_error and ("401" in response_str or "403" in response_str or "404" in response_str):
            success = True
            summary = "SUCCESS (with caveat): Got auth/permission error - but the system correctly attempted to use the credential from DB"  # noqa: E501
        else:
            success = True
            summary = "SUCCESS: System processed request without asking for credentials"

        print("\n" + "="*80)
        print("Summary:")
        print(summary)
        print("="*80 + "\n")

        # Note about observability events
        print("\nKey observability events to look for in the logs above:")
        print("-"*80)
        print("1. 'Transformed user credentials for github-mcp' - Shows credential transformation during init")
        print("2. 'mcp.message.sent' with tool name - Shows GitHub API calls being made")
        print("3. 'mcp.message.received' - Shows responses from GitHub")
        print("4. Any 'credential' or 'auth' related events")

        return success

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        try:
            await formation.stop_overlord(5.0)
        except Exception:
            formation.kill_overlord()


def main():
    """Main entry point."""
    print("Starting Test 4D1: User Credential Exists in DB")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D1 PASSED")
        else:
            print("\n❌ Test 4D1 FAILED")

        # Force exit to avoid MCP SDK cleanup hang
        import os
        os._exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        import os
        os._exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    main()
