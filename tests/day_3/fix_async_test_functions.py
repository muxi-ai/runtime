#!/usr/bin/env python3
"""Fix async/await issues in test functions."""

import re
import os

# Files that have the issue
files_with_issue = [
    "test_3c1_video_frame_analysis.py",
    "test_3c2_video_audio_combined_analysis.py", 
    "test_3c3_video_summarization.py",
    "test_3c4_long_video_async_processing.py",
    "test_3d1_document_image_cross_analysis.py",
    "test_3d2_audio_image_fusion_analysis.py",
    "test_3d3_full_multimodal_processing.py",
    "test_3e1_sync_multimodal_processing.py",
    "test_3e2_async_multimodal_processing.py"
]

for filename in files_with_issue:
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filename} - file not found")
        continue
        
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Pattern 1: Convert test functions to async
    # Match: def test_functionname(overlord):
    content = re.sub(
        r'^(def test_\w+\(overlord\):)$',
        r'async \1',
        content,
        flags=re.MULTILINE
    )
    
    # Pattern 2: Replace get_response() calls with await
    # Match: response = get_response(\n        overlord.chat(
    content = re.sub(
        r'response = get_response\(\s*\n\s*overlord\.chat\(',
        'response = await overlord.chat(',
        content
    )
    
    # Pattern 3: Remove the closing parenthesis from get_response
    # Match lines that have just )\n    ) pattern
    content = re.sub(
        r'\)\s*\n\s*\)(\s*\n)',
        r')\1',
        content
    )
    
    # Pattern 4: Fix function calls in try block to use await
    # Match: test_functionname(overlord)
    content = re.sub(
        r'^(\s+)(test_\w+)\(overlord\)$',
        r'\1await \2(overlord)',
        content,
        flags=re.MULTILINE
    )
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"Fixed {filename}")

print("\nDone!")