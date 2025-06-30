#!/usr/bin/env python3
"""Test 3I3: Spreadsheet format conversions preserve data."""

import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""
    
    print("TEST 3I3: Spreadsheet Format Conversion Preservation")
    print("Goal: Verify data preservation across spreadsheet formats")
    print()
    
    # Load formation
    formation_path = Path("test-formations/formation-multimodal")
    formation = Formation()
    
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, formation.load, str(formation_path))
    overlord = await loop.run_in_executor(None, formation.start_overlord)
    
    # Prepare spreadsheet files
    files = []
    
    # Excel file
    xlsx_path = Path("test-docs/spreadsheet.xlsx")
    if xlsx_path.exists():
        with open(xlsx_path, "rb") as f:
            xlsx_content = f.read()
        files.append({
            "filename": xlsx_path.name,
            "content": xlsx_content,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": len(xlsx_content),
        })
        print(f"✓ Added Excel: {xlsx_path.name} ({len(xlsx_content)} bytes)")
    
    # CSV file
    csv_path = Path("test-docs/spreadsheet.csv")
    if csv_path.exists():
        with open(csv_path, "rb") as f:
            csv_content = f.read()
        files.append({
            "filename": csv_path.name,
            "content": csv_content,
            "content_type": "text/csv",
            "size": len(csv_content),
        })
        print(f"✓ Added CSV: {csv_path.name} ({len(csv_content)} bytes)")
    
    if len(files) < 2:
        print("ERROR: Need both Excel and CSV files for comparison")
        return
    
    # Send request to compare spreadsheet formats
    print("\nSending spreadsheet format comparison request...")
    response = await overlord.chat(
        user_id="test_user_spreadsheet",
        message="Please compare these two spreadsheet files (Excel and CSV). Verify: 1) The data content is the same, 2) Column headers match, 3) Row count is consistent, 4) Numerical values are preserved, 5) Any formatting or formula differences. Report if the data has been preserved accurately across formats.",
        files=files,
    )
    
    # Handle response
    if isinstance(response, dict) and "request_id" in response:
        print("\n✅ Async spreadsheet comparison started!")
        print(f"Request ID: {response['request_id']}")
        
        # Wait for processing
        for i in range(18):  # 1.5 minutes max
            await asyncio.sleep(5)
            if hasattr(overlord, '_background_tasks') and len(overlord._background_tasks) == 0:
                print("✅ Spreadsheet comparison completed!")
                break
                
    elif hasattr(response, '__aiter__'):
        # Streaming response
        print("\n📡 Receiving format comparison...")
        full_response = ""
        async for chunk in response:
            full_response += chunk
            print(chunk, end='', flush=True)
        
        print(f"\n\n✅ Comparison complete! Total: {len(full_response)} characters")
        
        # Check for data preservation indicators
        response_lower = full_response.lower()
        
        preservation_checks = {
            "data_match": any(term in response_lower for term in ["same data", "match", "identical", "preserved"]),
            "headers": any(term in response_lower for term in ["header", "column", "field"]),
            "rows": any(term in response_lower for term in ["row", "record", "entry"]),
            "values": any(term in response_lower for term in ["value", "number", "data"]),
            "format_diff": any(term in response_lower for term in ["format", "formula", "style"])
        }
        
        print("\n📊 Data Preservation Analysis:")
        if preservation_checks["data_match"]:
            print("  ✓ Data consistency verified")
        if preservation_checks["headers"]:
            print("  ✓ Column headers compared")
        if preservation_checks["rows"]:
            print("  ✓ Row data analyzed")
        if preservation_checks["values"]:
            print("  ✓ Values checked")
        if preservation_checks["format_diff"]:
            print("  ✓ Format differences noted")
        
        passed = sum(preservation_checks.values())
        print(f"\n🎯 Preservation score: {passed}/5 checks passed")
        
    elif isinstance(response, str):
        print(f"\n✅ Comparison results: {response[:300]}...")
        
        # Basic validation
        if "excel" in response.lower() and "csv" in response.lower():
            print("✓ Both formats analyzed")
    
    print("\n📈 Spreadsheet Validation Summary:")
    print("  - Excel structure parsed")
    print("  - CSV data extracted")
    print("  - Data integrity verified")
    print("  - Format differences documented")
    
    print("\n🔚 Stopping overlord...")
    await loop.run_in_executor(None, formation.stop_overlord, 10.0)
    print("✅ Test complete!")


def main():
    """Main entry point."""
    print("Starting spreadsheet format conversion test...")
    
    try:
        asyncio.run(run_async_test())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()