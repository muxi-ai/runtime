#!/usr/bin/env python3
"""
Test the actual triggering of the clarification flow.
Simulates the complete flow from Agent to Overlord.
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass


# Mock classes
class MissingCredentialError(Exception):
    def __init__(self, service: str, user_id: str):
        self.service = service
        self.user_id = user_id
        super().__init__(f"Missing credentials for service '{service}' and user '{user_id}'")


@dataclass
class ClarificationRequest:
    request_type: str
    questions: list
    context: dict


class MockCredentialResolver:
    """Mock credential resolver that simulates missing/existing credentials."""
    
    def __init__(self):
        self.credentials = {}
    
    async def resolve(self, service: str, user_id: str) -> Dict[str, Any]:
        key = f"{user_id}:{service.lower()}"
        if key not in self.credentials:
            raise MissingCredentialError(service, user_id)
        return self.credentials[key]
    
    async def store(self, service: str, user_id: str, credentials: Dict[str, Any]):
        key = f"{user_id}:{service.lower()}"
        self.credentials[key] = credentials


class MockMCPService:
    """Mock MCP service that simulates tool invocation."""
    
    def __init__(self, credential_resolver):
        self.credential_resolver = credential_resolver
        self.invocation_count = 0
    
    async def invoke_tool(self, server_id: str, tool_name: str, arguments: dict,
                         user_id: Optional[str] = None, 
                         credential_resolver: Optional[Any] = None):
        """Simulate tool invocation with credential resolution."""
        self.invocation_count += 1
        
        # Simulate credential resolution for GitHub tool
        if server_id == "github-api" and credential_resolver:
            # This would normally be in MCPCoordinator
            credentials = await credential_resolver.resolve("github", user_id)
            print(f"   └─> Resolved credentials: {credentials}")
            return {"status": "success", "pr_url": "https://github.com/repo/pull/123"}
        
        return {"status": "error", "message": "No credentials"}


class MockOverlord:
    """Mock Overlord that handles clarification."""
    
    def __init__(self, credential_resolver):
        self._credential_resolver = credential_resolver
        self._pending_clarifications = {}
    
    async def handle_missing_credential(self, service: str, user_id: str, context: dict) -> ClarificationRequest:
        """Generate clarification request for missing credentials."""
        print(f"\n📋 OVERLORD: Handling missing credential for {service}")
        
        # Format service name
        display_name = service.replace("_", " ").title()
        if service.lower() == "github":
            display_name = "GitHub"
        
        # Generate request
        message = (
            f"I need your {display_name} credentials to continue. "
            f"This is required to use the '{context.get('tool_name')}' tool. "
            f"Please provide your {display_name} credentials (API key, token, or authentication details)."
        )
        
        request = ClarificationRequest(
            request_type="credential_required",
            questions=[{
                "id": f"credential_{service}",
                "question": message,
                "type": "credential"
            }],
            context={"service": service, "user_id": user_id, **context}
        )
        
        # Track pending clarification
        request_id = f"req_{len(self._pending_clarifications)}"
        self._pending_clarifications[request_id] = {
            "service": service,
            "user_id": user_id,
            "context": context
        }
        
        return request
    
    async def process_credential_clarification_response(self, response: dict, service: str, user_id: str):
        """Process user's credential response."""
        print(f"\n💾 OVERLORD: Storing credential for {service}")
        
        # Parse response (simplified)
        credential_value = response.get("answer", "")
        
        # Determine field name
        field_name = "token" if service.lower() in ["github", "gitlab"] else "api_key"
        
        # Store credential
        await self._credential_resolver.store(
            service=service,
            user_id=user_id,
            credentials={field_name: credential_value}
        )
        
        print(f"   └─> Stored: {{{field_name}: '{credential_value[:10]}...'}}")


class MockAgent:
    """Mock Agent that uses MCP tools and handles clarification."""
    
    def __init__(self, overlord, mcp_service):
        self._overlord = overlord
        self._mcp_service = mcp_service
        self._current_user_id = None
        self.agent_id = "test-agent"
    
    async def process_message(self, message: str, user_id: str):
        """Process user message."""
        self._current_user_id = user_id
        print(f"\n🤖 AGENT: Processing '{message}' for user '{user_id}'")
        
        # Simulate determining we need GitHub tool
        if "create" in message.lower() and "pr" in message.lower():
            return await self.invoke_tool("github-api", "create_pull_request", {"title": "Test PR"})
        
        return "I don't understand that request."
    
    async def invoke_tool(self, server_id: str, tool_name: str, arguments: dict):
        """Invoke MCP tool with error handling."""
        print(f"\n🔧 AGENT: Invoking tool {tool_name} on {server_id}")
        
        try:
            # Try to invoke tool
            result = await self._mcp_service.invoke_tool(
                server_id=server_id,
                tool_name=tool_name,
                arguments=arguments,
                user_id=self._current_user_id,
                credential_resolver=self._overlord._credential_resolver
            )
            print(f"   └─> Success: {result}")
            return result
            
        except MissingCredentialError as e:
            print(f"\n⚠️  AGENT: Caught MissingCredentialError!")
            print(f"   └─> Service: {e.service}, User: {e.user_id}")
            
            # Trigger clarification flow
            clarification_request = await self._overlord.handle_missing_credential(
                service=e.service,
                user_id=e.user_id,
                context={
                    "tool_name": tool_name,
                    "agent_id": self.agent_id,
                    "server_id": server_id
                }
            )
            
            print(f"\n❓ AGENT: Returning clarification request to user")
            return clarification_request


async def test_clarification_flow_trigger():
    """Test the complete clarification flow triggering."""
    
    print("TEST: CLARIFICATION FLOW TRIGGERING")
    print("=" * 60)
    print()
    
    # Setup components
    credential_resolver = MockCredentialResolver()
    mcp_service = MockMCPService(credential_resolver)
    overlord = MockOverlord(credential_resolver)
    agent = MockAgent(overlord, mcp_service)
    
    # Test 1: First attempt - no credentials
    print("SCENARIO 1: User requests PR creation without stored credentials")
    print("-" * 60)
    
    result1 = await agent.process_message("Create a PR with my changes", "user-123")
    
    assert isinstance(result1, ClarificationRequest)
    assert result1.request_type == "credential_required"
    assert "GitHub" in result1.questions[0]["question"]
    assert "create_pull_request" in result1.questions[0]["question"]
    
    print(f"\n✅ Clarification request generated:")
    print(f"   {result1.questions[0]['question']}")
    print()
    
    # Test 2: User provides credential
    print("SCENARIO 2: User provides credential")
    print("-" * 60)
    
    user_response = {"answer": "ghp_mytoken123456789"}
    await overlord.process_credential_clarification_response(
        response=user_response,
        service="github",
        user_id="user-123"
    )
    
    print("✅ Credential stored")
    print()
    
    # Test 3: Second attempt - credentials exist
    print("SCENARIO 3: User requests PR creation again (credentials now exist)")
    print("-" * 60)
    
    result2 = await agent.process_message("Create another PR", "user-123")
    
    assert isinstance(result2, dict)
    assert result2["status"] == "success"
    assert "pr_url" in result2
    
    print("✅ Tool executed successfully with stored credentials")
    print()
    
    # Test 4: Different user - no credentials
    print("SCENARIO 4: Different user requests PR (no credentials)")
    print("-" * 60)
    
    result3 = await agent.process_message("Create a PR please", "user-456")
    
    assert isinstance(result3, ClarificationRequest)
    assert "GitHub" in result3.questions[0]["question"]
    
    print("✅ Clarification triggered for different user")
    print()
    
    # Test 5: Case insensitivity
    print("SCENARIO 5: Test case-insensitive service resolution")
    print("-" * 60)
    
    # Store credential with lowercase
    await credential_resolver.store("github", "user-789", {"token": "ghp_test"})
    
    # Mock service that uses uppercase
    class MockMCPServiceUppercase(MockMCPService):
        async def invoke_tool(self, server_id, tool_name, arguments, user_id=None, credential_resolver=None):
            if server_id == "github-api":
                # Simulate uppercase service name
                credentials = await credential_resolver.resolve("GITHUB", user_id)
                return {"status": "success", "data": credentials}
    
    mcp_upper = MockMCPServiceUppercase(credential_resolver)
    agent_upper = MockAgent(overlord, mcp_upper)
    
    result4 = await agent_upper.process_message("Create a PR", "user-789")
    assert result4["status"] == "success"
    assert result4["data"] == {"token": "ghp_test"}
    
    print("✅ Case-insensitive resolution works")
    print()
    
    print("=" * 60)
    print("✅ ALL CLARIFICATION FLOW TESTS PASSED!")
    print()
    print("Verified:")
    print("- Agent catches MissingCredentialError")
    print("- Overlord.handle_missing_credential() is called")
    print("- Clarification request is returned to user")
    print("- User response is processed and stored")
    print("- Subsequent requests use stored credentials")
    print("- User isolation works correctly")
    print("- Case-insensitive service names work")


async def test_mcp_coordinator_integration():
    """Test MCP Coordinator placeholder resolution."""
    
    print("\nTEST: MCP COORDINATOR INTEGRATION")
    print("=" * 60)
    print()
    
    class MockMCPCoordinator:
        """Mock MCP Coordinator with placeholder resolution."""
        
        def __init__(self, credential_resolver):
            self.credential_resolver = credential_resolver
        
        async def resolve_mcp_auth_for_execution(self, auth_config: dict, user_id: str) -> dict:
            """Resolve auth placeholders at execution time."""
            import re
            
            resolved_auth = {}
            pattern = re.compile(r'\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}')
            
            for key, value in auth_config.items():
                if isinstance(value, str):
                    match = pattern.match(value)
                    if match:
                        service = match.group(1)
                        print(f"   Resolving placeholder: {value}")
                        
                        # Resolve credential
                        credentials = await self.credential_resolver.resolve(service, user_id)
                        
                        # Use the first credential value
                        if credentials:
                            resolved_value = list(credentials.values())[0]
                            resolved_auth[key] = resolved_value
                            print(f"   └─> Resolved to: {resolved_value[:10]}...")
                    else:
                        resolved_auth[key] = value
                else:
                    resolved_auth[key] = value
            
            return resolved_auth
    
    # Setup
    resolver = MockCredentialResolver()
    coordinator = MockMCPCoordinator(resolver)
    
    # Test placeholder resolution
    print("1. Test placeholder resolution without credentials")
    auth_config = {"token": "${{ user.credentials.github }}"}
    
    try:
        await coordinator.resolve_mcp_auth_for_execution(auth_config, "user-999")
        print("   ❌ Should have raised error")
    except MissingCredentialError as e:
        print(f"   ✅ MissingCredentialError raised: {e}")
    
    # Store credential and retry
    print("\n2. Store credential and retry")
    await resolver.store("github", "user-999", {"token": "ghp_secret123"})
    
    resolved = await coordinator.resolve_mcp_auth_for_execution(auth_config, "user-999")
    assert resolved == {"token": "ghp_secret123"}
    print(f"   ✅ Resolved auth: {resolved}")
    
    # Test multiple placeholders
    print("\n3. Test multiple placeholders")
    multi_auth = {
        "github_token": "${{ user.credentials.github }}",
        "api_key": "${{ user.credentials.openai }}",
        "static_key": "static-value-123"
    }
    
    await resolver.store("openai", "user-999", {"api_key": "sk-openai-key"})
    
    resolved_multi = await coordinator.resolve_mcp_auth_for_execution(multi_auth, "user-999")
    assert resolved_multi == {
        "github_token": "ghp_secret123",
        "api_key": "sk-openai-key",
        "static_key": "static-value-123"
    }
    print(f"   ✅ Multiple placeholders resolved: {resolved_multi}")
    
    print("\n✅ MCP Coordinator integration works correctly!")


if __name__ == "__main__":
    asyncio.run(test_clarification_flow_trigger())
    asyncio.run(test_mcp_coordinator_integration())