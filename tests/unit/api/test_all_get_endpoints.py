#!/usr/bin/env python3
"""
Comprehensive test suite for all GET endpoints.

Tests authentication and functionality of all admin and client GET endpoints
discovered from the OpenAPI specification.
"""

import asyncio
import httpx
import json
from typing import Dict, Any
from datetime import datetime


# Server configuration
BASE_URL = "http://localhost:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"


class EndpointTester:
    """Test runner for API endpoints."""

    def __init__(self):
        self.results = []
        self.success_count = 0
        self.total_count = 0

    async def test_endpoint(
        self,
        client: httpx.AsyncClient,
        method: str,
        endpoint: str,
        headers: Dict[str, str],
        description: str,
        expect_success: bool = True
    ) -> Dict[str, Any]:
        """Test a single endpoint."""
        url = f"{BASE_URL}{endpoint}"
        self.total_count += 1

        try:
            response = await client.request(method, url, headers=headers)

            # Determine if test passed
            is_success = (200 <= response.status_code < 300)
            test_passed = is_success if expect_success else not is_success

            if test_passed:
                self.success_count += 1

            result = {
                "endpoint": endpoint,
                "method": method,
                "description": description,
                "status_code": response.status_code,
                "success": is_success,
                "test_passed": test_passed,
                "expected_success": expect_success,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
            }

            # Parse response body
            try:
                body = response.json()
                result["response_body"] = body
                result["response_type"] = "json"

                # Extract useful info from successful responses
                if is_success and isinstance(body, dict):
                    result["object_type"] = body.get("object", "unknown")
                    result["data_count"] = len(body.get("data", []))

            except Exception:
                result["response_body"] = response.text
                result["response_type"] = "text"

            self.results.append(result)
            return result

        except Exception as e:
            result = {
                "endpoint": endpoint,
                "method": method,
                "description": description,
                "status_code": "ERROR",
                "success": False,
                "test_passed": False,
                "expected_success": expect_success,
                "error": str(e)
            }
            self.results.append(result)
            return result

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*80)
        print("📊 TEST SUMMARY")
        print("="*80)
        print(f"Total tests: {self.total_count}")
        print(f"Passed: {self.success_count}")
        print(f"Failed: {self.total_count - self.success_count}")
        print(f"Success rate: {(self.success_count/self.total_count)*100:.1f}%")

        # Group results by status
        successful = [r for r in self.results if r["success"]]
        failed = [r for r in self.results if not r["success"] and r["status_code"] != "ERROR"]
        errors = [r for r in self.results if r["status_code"] == "ERROR"]

        if successful:
            print(f"\n✅ SUCCESSFUL ENDPOINTS ({len(successful)}):")
            for result in successful:
                data_info = f" ({result.get('data_count', '?')} items)" if result.get('data_count') is not None else ""
                print(f"   {result['method']} {result['endpoint']} - {result['description']}{data_info}")

        if failed:
            print(f"\n❌ FAILED ENDPOINTS ({len(failed)}):")
            for result in failed:
                print(f"   {result['method']} {result['endpoint']} - {result['status_code']} - {result['description']}")

        if errors:
            print(f"\n💥 ERROR ENDPOINTS ({len(errors)}):")
            for result in errors:
                print(f"   {result['method']} {result['endpoint']} - {result['error']}")


async def test_admin_endpoints(tester: EndpointTester):
    """Test all admin GET endpoints."""
    print("\n" + "="*60)
    print("🔐 TESTING ADMIN GET ENDPOINTS")
    print("="*60)

    admin_endpoints = [
        # Core endpoints
        ("GET", "/v1/agents", "List all agents"),
        ("GET", "/v1/config", "Get formation configuration"),
        ("GET", "/v1/formation", "Get formation info"),
        ("GET", "/v1/status", "Get formation status"),
        ("GET", "/v1/overlord", "Get overlord info"),

        # Agent management
        ("GET", "/v1/agents/coder", "Get specific agent (coder)"),
        ("GET", "/v1/agents/researcher", "Get specific agent (researcher)"),
        ("GET", "/v1/agents/writer", "Get specific agent (writer)"),
        ("GET", "/v1/agents/project-manager", "Get specific agent (project-manager)"),
        ("GET", "/v1/agents/nonexistent", "Get nonexistent agent (should fail)"),

        # Secrets management
        ("GET", "/v1/secrets", "List secrets"),

        # MCP endpoints
        ("GET", "/v1/mcp", "Get MCP configuration"),
        ("GET", "/v1/mcp/servers", "List MCP servers"),
        ("GET", "/v1/mcp/tools", "List MCP tools"),

        # Service configuration endpoints
        ("GET", "/v1/llm/settings", "Get LLM settings"),
        ("GET", "/v1/logging", "Get logging configuration"),
        ("GET", "/v1/memory", "Get memory configuration"),
        ("GET", "/v1/memory/buffers", "Get memory buffers"),
        ("GET", "/v1/async", "Get async configuration"),
        ("GET", "/v1/async/jobs", "List async jobs"),
        ("GET", "/v1/scheduler", "Get scheduler configuration"),
        ("GET", "/v1/a2a", "Get A2A configuration"),
    ]

    headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, endpoint, description in admin_endpoints:
            print(f"Testing {method} {endpoint}...", end=" ")

            # Determine if we expect this to succeed
            expect_success = "nonexistent" not in endpoint.lower()

            result = await tester.test_endpoint(
                client, method, endpoint, headers, description, expect_success
            )

            status_icon = "✅" if result["test_passed"] else "❌"
            print(f"{status_icon} {result['status_code']}")


async def test_client_endpoints(tester: EndpointTester):
    """Test all client GET endpoints."""
    print("\n" + "="*60)
    print("👤 TESTING CLIENT GET ENDPOINTS")
    print("="*60)

    # Use a test user ID for endpoints that require it
    test_user = "test_user_123"

    client_endpoints = [
        # User-specific endpoints
        ("GET", f"/v1/events/{test_user}", "Get user events stream"),
        ("GET", f"/v1/jobs/{test_user}", "List user jobs"),
        ("GET", f"/v1/memories/{test_user}", "List user memories"),
    ]

    headers = {"X-Muxi-Client-Key": CLIENT_KEY}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, endpoint, description in client_endpoints:
            print(f"Testing {method} {endpoint}...", end=" ")

            result = await tester.test_endpoint(
                client, method, endpoint, headers, description, True
            )

            status_icon = "✅" if result["test_passed"] else "❌"
            print(f"{status_icon} {result['status_code']}")


async def test_public_endpoints(tester: EndpointTester):
    """Test public endpoints (no auth required)."""
    print("\n" + "="*60)
    print("🌐 TESTING PUBLIC GET ENDPOINTS")
    print("="*60)

    public_endpoints = [
        ("GET", "/v1/health", "Health check"),
    ]

    headers = {}  # No authentication needed

    async with httpx.AsyncClient(timeout=10.0) as client:
        for method, endpoint, description in public_endpoints:
            print(f"Testing {method} {endpoint}...", end=" ")

            result = await tester.test_endpoint(
                client, method, endpoint, headers, description, True
            )

            status_icon = "✅" if result["test_passed"] else "❌"
            print(f"{status_icon} {result['status_code']}")


async def test_auth_failures(tester: EndpointTester):
    """Test that authentication failures work as expected."""
    print("\n" + "="*60)
    print("🚫 TESTING AUTHENTICATION FAILURES")
    print("="*60)

    # Test admin endpoint with wrong/missing auth
    test_cases = [
        ("GET", "/v1/agents", {}, "Admin endpoint with no auth (should fail)", False),
        ("GET", "/v1/agents", {"X-Muxi-Admin-Key": "wrong_key"}, "Admin endpoint with wrong key (should fail)", False),  # noqa: E501
        ("GET", "/v1/jobs/test_user", {"X-Muxi-Client-Key": "wrong_key"}, "Client endpoint with wrong key (should fail)", False),  # noqa: E501
        ("GET", "/v1/jobs/test_user", {"X-Muxi-Admin-Key": ADMIN_KEY}, "Client endpoint with admin key (should fail)", False),  # noqa: E501
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for method, endpoint, headers, description, expect_success in test_cases:
            print(f"Testing {description}...", end=" ")

            result = await tester.test_endpoint(
                client, method, endpoint, headers, description, expect_success
            )

            status_icon = "✅" if result["test_passed"] else "❌"
            print(f"{status_icon} {result['status_code']}")


async def main():
    """Run comprehensive GET endpoint tests."""
    print("\n🚀 COMPREHENSIVE GET ENDPOINT TESTING")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Server: {BASE_URL}")

    # Check server health first
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            if response.status_code == 200:
                print("✅ Server is healthy and reachable")
            else:
                print(f"⚠️  Server returned {response.status_code} for health check")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Make sure the server is running on http://localhost:8271")
        return

    # Initialize tester
    tester = EndpointTester()

    # Run all test suites
    await test_public_endpoints(tester)
    await test_admin_endpoints(tester)
    await test_client_endpoints(tester)
    await test_auth_failures(tester)

    # Print summary
    tester.print_summary()

    # Save detailed results to file
    results_file = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "server_url": BASE_URL,
            "total_tests": tester.total_count,
            "passed": tester.success_count,
            "failed": tester.total_count - tester.success_count,
            "results": tester.results
        }, f, indent=2)

    print(f"\n📄 Detailed results saved to: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
