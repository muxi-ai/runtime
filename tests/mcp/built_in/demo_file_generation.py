#!/usr/bin/env python3
"""
Simple demonstration of the File Generation MCP capability.
Shows how the implementation generates actual files.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add runtime source to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.services.mcp.built_in import file_generation


def main():
    """Demonstrate file generation capability."""
    print("🎨 File Generation MCP Demo")
    print("=" * 40)
    
    # Example: Generate a visualization
    demo_code = '''
import matplotlib.pyplot as plt
import numpy as np

# Create sample data
categories = ['Product A', 'Product B', 'Product C', 'Product D']
values = [23, 45, 56, 78]
colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']

# Create figure
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Bar chart
ax1.bar(categories, values, color=colors)
ax1.set_title('Sales by Product', fontsize=14, fontweight='bold')
ax1.set_ylabel('Sales (thousands)', fontsize=12)
ax1.grid(axis='y', alpha=0.3)

# Pie chart
ax2.pie(values, labels=categories, colors=colors, autopct='%1.1f%%', startangle=90)
ax2.set_title('Sales Distribution', fontsize=14, fontweight='bold')

plt.tight_layout()
plt.savefig('sales_visualization.png', dpi=150, bbox_inches='tight')
print("Visualization saved as sales_visualization.png")
'''

    print("\n📝 Code to execute:")
    print("-" * 40)
    print(demo_code)
    print("-" * 40)
    
    # Create temporary directory for output
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        
        # Validate the code
        is_valid, error = file_generation.validate_code(demo_code)
        print(f"\n🔍 Code validation: {'✅ Valid' if is_valid else f'❌ Invalid: {error}'}")
        
        if is_valid:
            # Generate the file
            print("\n🚀 Generating file...")
            result = file_generation.generate_file(demo_code)
            
            if "error" in result:
                print(f"❌ Generation failed: {result['error']}")
            else:
                print(f"✅ Success! Generated: {result['filename']}")
                print(f"📁 File location: {result['file_path']}")
                print(f"📏 File size: {Path(result['file_path']).stat().st_size:,} bytes")
                
                if result.get('stdout'):
                    print(f"\n📋 Output from code execution:")
                    print(result['stdout'])
    
    print("\n✨ Demo completed!")


if __name__ == "__main__":
    main()