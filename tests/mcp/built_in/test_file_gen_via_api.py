#!/usr/bin/env python3
"""
End-to-end test demonstrating file generation through MUXI's chat API.
"""

import json
import os
import requests
import time
from pathlib import Path


def test_file_generation_via_api():
    """Test file generation through MUXI's REST API."""
    print("=" * 60)
    print("File Generation MCP - API Test")
    print("=" * 60)
    
    # Check if MUXI is running
    api_url = "http://localhost:3000"
    
    try:
        # Health check
        response = requests.get(f"{api_url}/health", timeout=2)
        if response.status_code != 200:
            print("❌ MUXI is not running. Please start it with:")
            print("   muxi up formation.yaml")
            return
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to MUXI. Please ensure it's running on http://localhost:3000")
        return
    
    print("✅ MUXI is running")
    
    # Test cases
    test_cases = [
        {
            "name": "Bar Chart Generation",
            "message": "Create a bar chart showing quarterly sales: Q1 $250k, Q2 $300k, Q3 $280k, Q4 $350k. Use a professional color scheme and save as quarterly_sales.png",
            "expected_file": "quarterly_sales.png"
        },
        {
            "name": "JSON Data Export",
            "message": "Generate a JSON file with product inventory data: 5 products with name, SKU, quantity, and price fields",
            "expected_type": ".json"
        },
        {
            "name": "Excel Report",
            "message": "Create an Excel spreadsheet with two sheets: 'Sales' with monthly data for 2024, and 'Summary' with totals and averages",
            "expected_type": ".xlsx"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n📊 Test {i}: {test['name']}...")
        
        # Send chat request
        chat_data = {
            "message": test['message'],
            "user_id": "test-user",
            "session_id": f"test-session-{i}"
        }
        
        try:
            response = requests.post(
                f"{api_url}/v1/agents/file-creator/chat",
                json=chat_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Response: {result.get('response', '')[:100]}...")
                
                # Check if file was mentioned
                response_text = result.get('response', '').lower()
                if 'generated' in response_text or 'created' in response_text:
                    print("   File generation appears successful!")
                    
                    # Look for file reference
                    if test.get('expected_file'):
                        if test['expected_file'] in response_text:
                            print(f"   Found reference to {test['expected_file']}")
                    elif test.get('expected_type'):
                        if test['expected_type'] in response_text:
                            print(f"   Found {test['expected_type']} file reference")
            else:
                print(f"❌ Request failed: {response.status_code}")
                print(f"   Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
        
        # Small delay between tests
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print("✅ API tests completed!")
    print("\nNote: Generated files are saved in the MUXI runtime's outputs/ directory")
    print("=" * 60)


if __name__ == "__main__":
    test_file_generation_via_api()