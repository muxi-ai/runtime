#!/usr/bin/env python3
"""
Simple test to demonstrate file generation capability.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add runtime source to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.services.mcp.built_in import file_generation


def test_direct_file_generation():
    """Test file generation directly through the MCP."""
    print("=" * 60)
    print("File Generation MCP - Direct Test")
    print("=" * 60)
    
    # Test 1: Generate a bar chart
    print("\n📊 Test 1: Generating a bar chart...")
    chart_code = '''
import matplotlib.pyplot as plt

# Monthly revenue data
months = ['January', 'February', 'March']
revenue = [50, 65, 80]

# Create bar chart
plt.figure(figsize=(10, 6))
plt.bar(months, revenue, color=['#4CAF50', '#2196F3', '#FF9800'])
plt.title('Q1 2024 Revenue', fontsize=16)
plt.ylabel('Revenue ($k)', fontsize=12)
plt.xlabel('Month', fontsize=12)

# Add value labels on bars
for i, v in enumerate(revenue):
    plt.text(i, v + 1, f'${v}k', ha='center', fontsize=10)

plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig('revenue_chart.png', dpi=150)
'''
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        
        # Validate code
        is_valid, error = file_generation.validate_code(chart_code)
        print(f"Code validation: {'✅ Valid' if is_valid else f'❌ Invalid: {error}'}")
        
        if is_valid:
            # Generate file
            result = file_generation.generate_file(chart_code)
            if "error" in result:
                print(f"Generation failed: {result['error']}")
            else:
                print(f"✅ Generated: {result['filename']} at {result['file_path']}")
                print(f"   File size: {Path(result['file_path']).stat().st_size} bytes")
        
        # Test 2: Generate JSON data
        print("\n📄 Test 2: Generating JSON data file...")
        json_code = '''
import json

# Sample user data
users = [
    {"name": "Alice Johnson", "email": "alice@example.com", "age": 28},
    {"name": "Bob Smith", "email": "bob@example.com", "age": 34},
    {"name": "Charlie Brown", "email": "charlie@example.com", "age": 45}
]

with open('users.json', 'w') as f:
    json.dump(users, f, indent=2)
'''
        
        is_valid, error = file_generation.validate_code(json_code)
        print(f"Code validation: {'✅ Valid' if is_valid else f'❌ Invalid: {error}'}")
        
        if is_valid:
            result = file_generation.generate_file(json_code)
            if "error" in result:
                print(f"Generation failed: {result['error']}")
            else:
                print(f"✅ Generated: {result['filename']} at {result['file_path']}")
                # Read and display content
                with open(result['file_path'], 'r') as f:
                    content = json.load(f)
                    print(f"   Content: {len(content)} users")
                    for user in content:
                        print(f"   - {user['name']} ({user['email']})")
        
        # Test 3: Generate CSV
        print("\n📊 Test 3: Generating CSV file...")
        csv_code = '''
import csv

# Sales data
sales_data = [
    ['Product', 'Quantity', 'Price'],
    ['Laptop', 25, 899.99],
    ['Mouse', 150, 29.99],
    ['Keyboard', 75, 79.99],
    ['Monitor', 40, 299.99],
    ['Webcam', 60, 59.99]
]

with open('sales_report.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(sales_data)
'''
        
        is_valid, error = file_generation.validate_code(csv_code)
        print(f"Code validation: {'✅ Valid' if is_valid else f'❌ Invalid: {error}'}")
        
        if is_valid:
            result = file_generation.generate_file(csv_code)
            if "error" in result:
                print(f"Generation failed: {result['error']}")
            else:
                print(f"✅ Generated: {result['filename']} at {result['file_path']}")
                with open(result['file_path'], 'r') as f:
                    print(f"   First 3 lines:")
                    for i, line in enumerate(f):
                        if i < 3:
                            print(f"   {line.strip()}")
        
        # Test 4: Test security - should fail
        print("\n🔒 Test 4: Security validation (should fail)...")
        unsafe_code = '''
import os
os.system('ls')
'''
        
        is_valid, error = file_generation.validate_code(unsafe_code)
        print(f"Code validation: {'✅ Valid' if is_valid else f'❌ Invalid: {error}'}")
        
        # Show generated files
        print("\n📁 Generated files in output directory:")
        outputs_dir = Path(tmpdir) / "outputs"
        if outputs_dir.exists():
            files = list(outputs_dir.iterdir())
            for file in files:
                print(f"  - {file.name} ({file.stat().st_size} bytes)")
        else:
            print("  No outputs directory found")
        
        print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_direct_file_generation()