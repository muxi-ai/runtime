#!/usr/bin/env python3
"""
Day 7a: PDF Artifact Test - Workflow Integration

This test verifies PDF generation through the workflow system:
- Complex document generation triggers workflow
- Workflow metadata is included in response
- Artifacts are properly generated and attached
"""

import asyncio
import sys
import base64
from pathlib import Path
from datetime import datetime

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def test_pdf_artifact_generation():
    """Test PDF generation through workflow system."""
    print("\n" + "="*80)
    print("Day 7a: PDF Artifact Generation Test - Workflow Integration")
    print("Testing artifact generation with workflow orchestration")
    print("="*80 + "\n")
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    
    # Create output directory
    output_dir = Path(__file__).parent / "test_outputs"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Load formation
        print("1. Loading formation-multi-agent...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded and overlord started")
        
        # Request PDF generation
        prompt = """Generate a PDF document with the following content:

Title: Day 7a Test Report
Subtitle: Task Decomposition and Multi-Agent Coordination

Content:
1. Introduction
   This report demonstrates the successful implementation of task decomposition in MUXI Runtime.

2. Test Results
   - Multi-agent coordination: PASSED
   - MCP tool integration: PASSED
   - Linear issue creation: PASSED
   - PDF generation: IN PROGRESS

3. Conclusion
   The MUXI Runtime successfully handles complex multi-step tasks through intelligent agent routing.

Please generate this as a PDF artifact with proper formatting."""

        print("\n2. Requesting PDF generation...")
        print(f"   Prompt length: {len(prompt)} characters")
        
        start_time = asyncio.get_event_loop().time()
        response = await overlord.chat(
            prompt,
            user_id="test_user",
            session_id="test_pdf_session",
            stream=False,
            use_async=False
        )
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        # Extract response content
        response_content = response.content if hasattr(response, 'content') else str(response)
        
        print(f"\n   ✓ Response received in {duration:.1f} seconds")
        print(f"   Response type: {type(response)}")
        print(f"   Response attributes: {[attr for attr in dir(response) if not attr.startswith('_')][:20]}")
        print(f"   Response content length: {len(response_content)} characters")
        
        # Check for workflow metadata
        has_metadata = hasattr(response, 'metadata') and response.metadata is not None
        workflow_id = None
        if has_metadata:
            workflow_id = response.metadata.get('workflow_id')
            print(f"   Workflow ID: {workflow_id or 'Not found'}")
            print(f"   Workflow used: {'✓' if workflow_id else '✗'}")
        
        # Check for artifacts attribute
        artifacts = None
        if hasattr(response, 'artifacts'):
            artifacts = response.artifacts
            print(f"   Response has artifacts: {len(artifacts) if artifacts else 0}")
        
        # Save FULL response without truncation
        response_file = output_dir / f"pdf_artifact_full_{timestamp}.txt"
        with open(response_file, 'w') as f:
            f.write(f"PDF Artifact Generation Test\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Duration: {duration:.1f} seconds\n")
            f.write(f"Response type: {type(response)}\n")
            f.write(f"Response content length: {len(response_content)} characters\n")
            f.write(f"Has metadata: {has_metadata}\n")
            f.write(f"Workflow ID: {workflow_id or 'None'}\n")
            f.write(f"Has artifacts attribute: {hasattr(response, 'artifacts')}\n")
            if artifacts:
                f.write(f"Number of artifacts: {len(artifacts)}\n")
            f.write(f"\n{'='*80}\n\n")
            f.write("RESPONSE CONTENT:\n\n")
            f.write(response_content)
            
            # Save artifacts separately
            if artifacts:
                f.write(f"\n\n{'='*80}\n\n")
                f.write("ARTIFACTS:\n\n")
                for i, artifact in enumerate(artifacts):
                    f.write(f"\nArtifact {i+1}:\n")
                    f.write(f"Type: {type(artifact)}\n")
                    if hasattr(artifact, 'name'):
                        f.write(f"Name: {artifact.name}\n")
                    if hasattr(artifact, 'data'):
                        f.write(f"Data length: {len(artifact.data) if artifact.data else 0}\n")
                        f.write(f"Data preview: {str(artifact.data)[:100]}...\n")
                    if hasattr(artifact, 'content'):
                        f.write(f"Content length: {len(artifact.content) if artifact.content else 0}\n")
                        f.write(f"Content preview: {str(artifact.content)[:100]}...\n")
                    if hasattr(artifact, 'data_url'):
                        f.write(f"Data URL: {artifact.data_url[:100] if artifact.data_url else 'None'}...\n")
                        if artifact.data_url:
                            f.write(f"Full Data URL Length: {len(artifact.data_url)}\n")
                    if hasattr(artifact, 'filename'):
                        f.write(f"Filename: {artifact.filename}\n")
                    if hasattr(artifact, 'format'):
                        f.write(f"Format: {artifact.format}\n")
                    if hasattr(artifact, 'type'):
                        f.write(f"Type: {artifact.type}\n")
        
        print(f"   Full response saved to: {response_file}")
        
        # Look for base64 PDF data
        print("\n3. Analyzing response for PDF artifact...")
        
        # Check for artifact indicators
        has_artifact = "artifact" in response_content.lower()
        has_pdf = "pdf" in response_content.lower()
        has_base64 = "base64" in response_content.lower() or "data:application/pdf" in response_content
        
        print(f"   Contains 'artifact': {'✓' if has_artifact else '✗'}")
        print(f"   Contains 'pdf': {'✓' if has_pdf else '✗'}")
        print(f"   Contains base64 data in content: {'✓' if has_base64 else '✗'}")
        
        # Check artifacts
        if artifacts and len(artifacts) > 0:
            print(f"\n   Found {len(artifacts)} artifact(s) in response.artifacts")
        
        # Try to extract base64 PDF data
        if "data:application/pdf;base64," in response_content:
            print("\n4. Found PDF artifact!")
            
            # Extract base64 data
            start_marker = "data:application/pdf;base64,"
            start_idx = response_content.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                # Find the end of base64 data (usually ends with quotes or whitespace)
                end_idx = response_content.find('"', start_idx)
                if end_idx == -1:
                    end_idx = response_content.find("'", start_idx)
                if end_idx == -1:
                    end_idx = response_content.find(" ", start_idx)
                if end_idx == -1:
                    end_idx = response_content.find("\n", start_idx)
                
                if end_idx != -1:
                    base64_data = response_content[start_idx:end_idx]
                    print(f"   Base64 data length: {len(base64_data)} characters")
                    
                    # Decode and save PDF
                    try:
                        pdf_data = base64.b64decode(base64_data)
                        pdf_file = output_dir / f"generated_artifact_{timestamp}.pdf"
                        with open(pdf_file, 'wb') as f:
                            f.write(pdf_data)
                        print(f"   ✓ PDF decoded and saved to: {pdf_file}")
                        print(f"   PDF file size: {len(pdf_data)} bytes")
                    except Exception as e:
                        print(f"   ✗ Failed to decode base64: {e}")
                else:
                    print("   ✗ Could not find end of base64 data")
            else:
                print("   ✗ Could not find start of base64 data")
        else:
            print("\n4. Checking artifacts attribute...")
            if artifacts and len(artifacts) > 0:
                for i, artifact in enumerate(artifacts):
                    print(f"\n   Artifact {i+1}:")
                    if hasattr(artifact, 'filename'):
                        print(f"   Filename: {artifact.filename}")
                    if hasattr(artifact, 'format'):
                        print(f"   Format: {artifact.format}")
                    if hasattr(artifact, 'type'):
                        print(f"   Type: {artifact.type}")
                    if hasattr(artifact, 'data_url') and artifact.data_url:
                        print(f"   Has data_url: ✓ (length: {len(artifact.data_url)})")
                        
                        # Try to decode and save PDF
                        if artifact.data_url.startswith("data:application/pdf;base64,"):
                            try:
                                base64_data = artifact.data_url.split(",", 1)[1]
                                pdf_data = base64.b64decode(base64_data)
                                pdf_file = output_dir / f"artifact_{artifact.filename}"
                                with open(pdf_file, 'wb') as f:
                                    f.write(pdf_data)
                                print(f"   ✓ PDF decoded and saved to: {pdf_file}")
                                print(f"   PDF file size: {len(pdf_data)} bytes")
                            except Exception as e:
                                print(f"   ✗ Failed to decode PDF: {e}")
            else:
                print("   No artifacts found in response")
            
            # Check for error messages
            if "error" in response_content.lower() or "failed" in response_content.lower():
                print("   Response may contain error messages")
        
        # Clean up
        print("\n5. Cleaning up...")
        await formation.stop_overlord()
        print("   ✓ Overlord stopped")
        
        print("\n" + "="*80)
        print("✓ PDF Artifact Test Complete!")
        print(f"\nResults:")
        print(f"  - Workflow engaged: {'✓' if workflow_id else '✗'}")
        print(f"  - PDF artifact generated: {'✓' if (has_artifact and has_pdf) else '✗'}")
        print(f"  - Base64 data present: {'✓' if has_base64 else '✗'}")
        print(f"\nCheck {response_file} for the full response")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_pdf_artifact_generation())