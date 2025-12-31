#!/usr/bin/env python3
"""Test 4D2: User Credential Missing - Trigger Clarification Flow"""

import asyncio
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the test for existing user credentials."""

    print("\n" + "="*80)
    print("I am testing: User Credential Missing - Trigger Clarification Flow")
    print("This test verifies that when user2 (who does NOT have GitHub credentials in the database)")
    print("makes a request to list GitHub repositories, the system:")
    print("1. Uses formation secrets to initialize and discover GitHub MCP tools")
    print("2. Detects that user credentials are missing during the API call attempt")
    print("3. Triggers a clarification flow asking the user to provide their GitHub token")
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
        prompt = "List my GitHub repositories. Do not include forks"

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
            user_id="user2",
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

        # Check if we asked for credentials (this is what we WANT to happen)
        asked_for_credentials = any(phrase in response_str for phrase in [
            "please provide", "need your", "don't have", "missing credential",
            "github token", "github credentials", "authentication", "personal access token",
            "i need", "provide me", "enter your", "what is your", "what's your"
        ])

        # Check if we found repositories
        found_repos = any(word in response_str for word in ["repository", "repositories", "repo", "repos"])

        # Check for clarification request
        has_clarification = "clarification" in response_str or "missing_credential" in response_str

        if asked_for_credentials or has_clarification:
            success = True
            summary = "SUCCESS: System correctly asked for credentials when they were missing!"
        elif found_repos:
            success = False
            summary = "FAILED: System somehow listed repositories without credentials"
        elif "error" in response_str and ("401" in response_str or "unauthorized" in response_str):
            success = False
            summary = "FAILED: Got authentication error instead of asking for credentials"
        else:
            success = False
            summary = "FAILED: System did not ask for credentials when they were missing"

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
    print("Starting Test 4D2: User Credential Missing - Trigger Clarification")

    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4D2 PASSED")
        else:
            print("\n❌ Test 4D2 FAILED")

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
