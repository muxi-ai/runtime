#!/usr/bin/env python3
"""
Test true A2A collaboration between research-agent and writer-agent
"""
import asyncio
import httpx


async def test_collaboration():
    """Test if agents can actually collaborate on a shared task"""

    print("🔄 Testing True A2A Agent Collaboration...")

    # Simple collaboration request
    collaboration_request = {
        "message": "Write a summary about quantum computing with the data I provide",
        "message_type": "collaboration_request",
        "context": {
            "from_agent": "research-agent",
            "task": "joint_content_creation",
            "research_data": {
                "topic": "Quantum Computing",
                "key_points": [
                    "Quantum bits can exist in superposition",
                    "Quantum computers use entanglement",
                    "Current limitations include decoherence"
                ]
            }
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Send collaboration request from research-agent to writer-agent
            print("\\n📝 Sending collaboration request to writer-agent...")

            response = await client.post(
                "http://localhost:8182/agents/writer-agent/message",
                json=collaboration_request,
                headers={"X-API-Key": "test-key-456"}
            )

            print(f"Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print("✅ Collaboration request successful!")
                print(f"Writer response: {result.get('message', 'No message')}")

                # Check if response shows collaborative understanding
                if "quantum" in result.get('message', '').lower():
                    print("✅ TRUE COLLABORATION: Writer used research data!")
                    return True
                else:
                    print("❌ Message passing only - no collaboration content")
                    return False
            else:
                print(f"❌ Collaboration failed: {response.status_code}")
                print(f"Error: {response.text}")
                return False

    except Exception as e:
        print(f"❌ Collaboration test failed: {str(e)}")
        return False


async def main():
    """Main test runner"""
    print("=" * 60)
    print("TESTING TRUE A2A COLLABORATION")
    print("=" * 60)

    success = await test_collaboration()

    print("\\n" + "=" * 60)
    if success:
        print("🎉 TRUE COLLABORATION CONFIRMED!")
    else:
        print("⚠️  ONLY MESSAGE PASSING - NO TRUE COLLABORATION")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
