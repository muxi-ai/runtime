#!/usr/bin/env python3
"""
Test script to verify URL encoding/decoding matches between client and server
"""

import urllib.parse

# The agent URL we're trying to deregister
agent_url = "http://localhost:8080/debug-agent"

print("🔍 URL Encoding/Decoding Test")
print("=" * 50)

# Test encoding (what client does)
encoded_url = urllib.parse.quote(agent_url, safe='')
print(f"Original URL: {agent_url}")
print(f"Client encodes to: {encoded_url}")

# Test decoding (what server should do)
decoded_url = urllib.parse.unquote(encoded_url)
print(f"Server decodes to: {decoded_url}")

# Check if they match
print(f"URLs match: {agent_url == decoded_url}")

print()

# Test the exact URL from the curl command
curl_encoded = "http%3A%2F%2Flocalhost%3A8080%2Fdebug-agent"
curl_decoded = urllib.parse.unquote(curl_encoded)
print(f"Curl encoded URL: {curl_encoded}")
print(f"Curl decoded URL: {curl_decoded}")
print(f"Curl matches original: {agent_url == curl_decoded}")

print()

# Show what we expect to find in the registry storage
print("Expected storage entries:")
print(f"Storage key should be: '{agent_url}'")
print(f"DELETE should look for: '{decoded_url}'")

# Test different encoding variations
print()
print("Testing encoding variations:")
test_urls = [
    "http://localhost:8080/debug-agent",
    "https://example.com/agent-123",
    "http://127.0.0.1:8080/test"
]

for url in test_urls:
    encoded = urllib.parse.quote(url, safe='')
    redecoded = urllib.parse.unquote(encoded)
    print(f"  {url} -> {encoded} -> {redecoded} ({'✅' if url == redecoded else '❌'})")
