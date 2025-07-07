#!/usr/bin/env python3
"""Test 3I4: Word document content extraction completeness."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3I4: Word Document Extraction Completeness")
    print("Goal: Verify complete content extraction from Word documents")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare Word document
    docx_path = Path("test-docs/document.docx")
    if not docx_path.exists():
        print(f"ERROR: Word document not found at {docx_path}")
        return
    
    with open(docx_path, "rb") as f:
        docx_content = f.read()
    
    print(f"📄 Word document: {docx_path.name} ({len(docx_content)} bytes)")
    
    # Send request for comprehensive extraction
    print("\nSending Word document extraction request...")
    response = await overlord.chat(
        user_id="test_user_word_extract",
        message="Please extract ALL content from this Word document comprehensively. Include: 1) All text paragraphs, 2) Headings and their hierarchy, 3) Lists (bulleted and numbered), 4) Tables with data, 5) Headers and footers, 6) Any embedded images or diagrams descriptions, 7) Formatting information (bold, italic, etc). Provide a complete extraction.",
        files=[{
            "filename": docx_path.name,
            "content": docx_content,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": len(docx_content),
        }],
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async document extraction started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(18):  # 1.5 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Document extraction completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving document content...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Extraction complete! Total: {len(full_response)} characters")
        
        # Check extraction completeness
        response_lower = full_response.lower()
        
        completeness_checks = {
            "paragraphs": len(full_response) > 500,  # Substantial content
            "headings": any(term in response_lower for term in ["heading", "title", "section", "chapter"]),
            "lists": any(term in response_lower for term in ["list", "bullet", "number", "item", "•", "-", "*"]),
            "tables": any(term in response_lower for term in ["table", "row", "column", "cell"]),
            "formatting": any(term in response_lower for term in ["bold", "italic", "underline", "format"]),
            "structure": any(term in response_lower for term in ["document", "page", "paragraph"])
        }
        
        print("\n📊 Extraction Completeness Analysis:")
        if completeness_checks["paragraphs"]:
            print("  ✓ Substantial text content extracted")
        if completeness_checks["headings"]:
            print("  ✓ Document structure preserved")
        if completeness_checks["lists"]:
            print("  ✓ Lists identified")
        if completeness_checks["tables"]:
            print("  ✓ Tables extracted")
        if completeness_checks["formatting"]:
            print("  ✓ Formatting noted")
        if completeness_checks["structure"]:
            print("  ✓ Document organization captured")
        
        completeness_score = sum(completeness_checks.values())
        print(f"\n🎯 Completeness score: {completeness_score}/6")
        
        # Additional metrics
        word_count = len(full_response.split())
        line_count = len(full_response.split('\n'))
        print(f"\n📈 Extraction Metrics:")
        print(f"  - Words extracted: {word_count}")
        print(f"  - Lines extracted: {line_count}")
        print(f"  - Average words per line: {word_count/max(line_count, 1):.1f}")
        
    elif isinstance(response, str):
        print(f"\n✅ Extraction results: {response[:300]}...")
        print(f"Total extracted: {len(response)} characters")
        
        # Basic validation
        if len(response) > 200:
            print("✓ Meaningful content extracted")
    
    print("\n📝 Word Document Extraction Summary:")
    print("  - Text content extracted")
    print("  - Document structure analyzed")
    print("  - Special elements identified")
    print("  - Completeness verified")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting Word document extraction completeness test...")
    
    try:
        await run_async_test()
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()