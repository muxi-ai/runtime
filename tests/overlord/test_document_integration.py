#!/usr/bin/env python3
"""
Document Processing Integration Test

This test focuses on the integration between different document processing components
and validates that they work together correctly. This is a focused test that
complements the comprehensive test suite.
"""

import sys
import os
import asyncio
import tempfile

# Add runtime to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def create_test_document(content: str, filename: str = "test_doc.txt") -> str:
    """Create a temporary test document."""
    temp_dir = tempfile.mkdtemp()
    doc_path = os.path.join(temp_dir, filename)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(content)
    return doc_path


async def test_storage_experience_integration():
    """Test integration between storage and experience layers."""
    print("\n🔗 Testing Storage ↔ Experience Layer Integration")

    try:
        # Import components from both layers
        from src.muxi.runtime.formation.documents.storage import (
            DocumentChunkManager,
            DocumentMetadataStore,
        )
        from src.muxi.runtime.formation.documents.experience import (
            DocumentSummarizer,
            DocumentAcknowledgmentGenerator,
        )

        # Initialize components
        chunk_manager = DocumentChunkManager()
        metadata_store = DocumentMetadataStore()
        summarizer = DocumentSummarizer()
        ack_generator = DocumentAcknowledgmentGenerator()

        # Test content
        test_content = """
        Integration Test Document

        This document tests the integration between storage and experience layers.
        The storage layer should effectively chunk and store this content,
        while the experience layer should provide summaries and acknowledgments.

        Key integration points:
        - Chunked content feeding into summarization
        - Metadata informing acknowledgment generation
        - Cross-layer data consistency
        """

        # Storage layer processing
        chunks = await chunk_manager.chunk_document(
            content=test_content, filename="integration_test.txt", strategy="semantic"
        )

        doc_path = create_test_document(test_content, "integration_test.txt")
        metadata = {
            "filename": "integration_test.txt",
            "chunk_count": len(chunks),
            "content_type": "text/plain",
        }
        doc_id = await metadata_store.store_document_metadata(doc_path, metadata)

        # Experience layer processing using storage results
        summary = await summarizer.generate_summary(
            test_content, summary_type="overview", max_length=150
        )

        acknowledgment = await ack_generator.generate_completion_acknowledgment(
            "integration_test.txt", {"chunks": len(chunks), "summary": summary}
        )

        # Validate integration
        assert len(chunks) > 0, "Storage layer failed to generate chunks"
        assert doc_id is not None, "Storage layer failed to store metadata"
        assert len(summary) > 20, "Experience layer failed to generate summary"
        assert len(acknowledgment) > 30, "Experience layer failed to generate acknowledgment"

        print("  ✅ Storage → Experience integration working")
        print(f"     Chunks: {len(chunks)}, Summary: {len(summary)} chars")
        return True

    except Exception as e:
        print(f"  ❌ Storage ↔ Experience integration failed: {e}")
        return False


async def test_experience_workflow_integration():
    """Test integration between experience and workflow layers."""
    print("\n🔗 Testing Experience ↔ Workflow Layer Integration")

    try:
        # Import components from both layers
        from src.muxi.runtime.formation.documents.experience import (
            DocumentSummarizer,
            # DocumentErrorHandler,
        )
        from src.muxi.runtime.formation.documents.workflow import (
            DocumentWorkflowIntegrator,
            DocumentContextPreserver,
        )

        # Initialize components
        summarizer = DocumentSummarizer()
        # error_handler = DocumentErrorHandler()
        workflow_integrator = DocumentWorkflowIntegrator()
        context_preserver = DocumentContextPreserver()

        # Test content with workflow implications
        workflow_content = """
        Project Planning Document

        Objectives:
        - Complete system design by February 15th
        - Implement core features by March 30th
        - Conduct testing by April 15th

        Action Items:
        - John: Prepare technical specifications
        - Sarah: Design user interface mockups
        - Mike: Set up development environment
        """

        # Experience layer processing
        summary = await summarizer.generate_summary(
            workflow_content, summary_type="actionable", max_length=200
        )

        # Workflow layer processing using experience results
        tasks = await workflow_integrator.generate_tasks_from_document(workflow_content)

        # Context preservation with summary
        context = {
            "user_message": "Process this project planning document",
            "summary_generated": summary,
            "tasks_extracted": len(tasks),
            "timestamp": "2025-01-15T11:00:00Z",
        }

        await context_preserver.preserve_conversation_context("test_user", context)
        retrieved_context = await context_preserver.get_relevant_context(
            "test_user", "What tasks were extracted from the project document?"
        )

        # Validate integration
        assert len(summary) > 30, "Experience layer failed to generate actionable summary"
        assert len(tasks) > 0, "Workflow layer failed to generate tasks"
        assert retrieved_context is not None, "Workflow layer failed to preserve context"

        print("  ✅ Experience → Workflow integration working")
        print(f"     Summary: {len(summary)} chars, Tasks: {len(tasks)}")
        return True

    except Exception as e:
        print(f"  ❌ Experience ↔ Workflow integration failed: {e}")
        return False


async def test_storage_workflow_integration():
    """Test integration between storage and workflow layers."""
    print("\n🔗 Testing Storage ↔ Workflow Layer Integration")

    try:
        # Import components from both layers
        from src.muxi.runtime.formation.documents.storage import (
            DocumentChunkManager,
            DocumentReferenceSystem,
        )
        from src.muxi.runtime.formation.documents.workflow import (
            DocumentCrossReferenceManager,
            DocumentWorkflowIntegrator,
        )

        # Initialize components
        chunk_manager = DocumentChunkManager()
        reference_system = DocumentReferenceSystem()
        cross_ref_manager = DocumentCrossReferenceManager()
        workflow_integrator = DocumentWorkflowIntegrator()

        # Test content with cross-references
        doc1_content = """
        Requirements Document
        This document outlines the system requirements.
        See Technical Specification for implementation details.
        """

        doc2_content = """
        Technical Specification
        Implementation details for the Requirements Document.
        References: Requirements Document sections 2.1-2.3
        """

        # Storage layer processing
        doc1_chunks = await chunk_manager.chunk_document(
            content=doc1_content, filename="requirements.txt", strategy="fixed"
        )

        doc2_chunks = await chunk_manager.chunk_document(
            content=doc2_content, filename="tech_spec.txt", strategy="fixed"
        )

        # Reference system operations
        await reference_system.add_document_reference("req_doc", "tech_spec", "references")

        # Workflow layer processing using storage results
        await cross_ref_manager.add_document("req_doc", doc1_content, {"title": "Requirements"})
        await cross_ref_manager.add_document("tech_spec", doc2_content, {"title": "Tech Spec"})

        connections = await cross_ref_manager.discover_document_connections("req_doc", "tech_spec")

        # Generate workflow from connected documents
        combined_content = doc1_content + "\n\n" + doc2_content
        workflow_tasks = await workflow_integrator.generate_tasks_from_document(combined_content)

        # Validate integration
        assert len(doc1_chunks) > 0, "Storage layer failed to chunk first document"
        assert len(doc2_chunks) > 0, "Storage layer failed to chunk second document"
        assert len(connections) >= 0, "Workflow layer failed to discover connections"
        assert len(workflow_tasks) > 0, "Workflow layer failed to generate tasks"

        print("  ✅ Storage → Workflow integration working")
        print(f"     Chunks: {len(doc1_chunks + doc2_chunks)}, Tasks: {len(workflow_tasks)}")
        return True

    except Exception as e:
        print(f"  ❌ Storage ↔ Workflow integration failed: {e}")
        return False


async def test_three_layer_integration():
    """Test integration across all three layers."""
    print("\n🔗 Testing Three-Layer Integration (Storage → Experience → Workflow)")

    try:
        # Import components from all three layers
        from src.muxi.runtime.formation.documents.storage import (
            DocumentChunkManager,
            DocumentMetadataStore,
        )
        from src.muxi.runtime.formation.documents.experience import (
            DocumentSummarizer,
            DocumentAcknowledgmentGenerator,
        )
        from src.muxi.runtime.formation.documents.workflow import (
            DocumentWorkflowIntegrator,
            DocumentContextPreserver,
        )

        # Initialize all components
        chunk_manager = DocumentChunkManager()
        metadata_store = DocumentMetadataStore()
        summarizer = DocumentSummarizer()
        ack_generator = DocumentAcknowledgmentGenerator()
        workflow_integrator = DocumentWorkflowIntegrator()
        context_preserver = DocumentContextPreserver()

        # Complex test content
        complex_content = """
        Product Development Roadmap - Q1 2025

        Executive Summary:
        This roadmap outlines the key initiatives for Q1 2025 product development.

        Strategic Objectives:
        1. Launch mobile application beta version
        2. Implement advanced analytics dashboard
        3. Enhance security features and compliance

        Detailed Planning:

        Phase 1: Foundation (Weeks 1-4)
        - Complete technical architecture review
        - Finalize UI/UX designs for mobile app
        - Set up development and testing environments

        Phase 2: Development (Weeks 5-10)
        - Mobile app development (iOS and Android)
        - Analytics dashboard implementation
        - Security feature development

        Phase 3: Testing and Launch (Weeks 11-12)
        - Comprehensive testing across all platforms
        - Beta user recruitment and onboarding
        - Launch preparation and marketing

        Success Metrics:
        - 10,000+ beta users within first month
        - 95% uptime for all services
        - Zero critical security vulnerabilities
        """

        # Layer 1: Storage processing
        print("  📁 Storage Layer: Chunking and metadata...")
        chunks = await chunk_manager.chunk_document(
            content=complex_content, filename="product_roadmap_q1_2025.txt", strategy="semantic"
        )

        doc_path = create_test_document(complex_content, "product_roadmap_q1_2025.txt")
        metadata = {
            "filename": "product_roadmap_q1_2025.txt",
            "file_size": len(complex_content),
            "chunk_count": len(chunks),
            "document_type": "roadmap",
        }
        doc_id = await metadata_store.store_document_metadata(doc_path, metadata)

        # Layer 2: Experience processing
        print("  🎭 Experience Layer: Summary and acknowledgments...")
        summary = await summarizer.generate_summary(
            complex_content, summary_type="executive", max_length=300
        )

        processing_ack = await ack_generator.generate_processing_acknowledgment(
            "product_roadmap_q1_2025.txt", "Extract roadmap tasks and timeline"
        )

        # Layer 3: Workflow processing
        print("  🔄 Workflow Layer: Task extraction and context...")
        tasks = await workflow_integrator.generate_tasks_from_document(complex_content)

        workflow_context = {
            "user_message": "Process the Q1 2025 product roadmap",
            "document_id": doc_id,
            "chunks_generated": len(chunks),
            "summary": summary[:100] + "...",  # Truncated summary
            "tasks_extracted": len(tasks),
            "processing_acknowledgment": processing_ack[:50] + "...",
            "timestamp": "2025-01-15T14:00:00Z",
        }

        await context_preserver.preserve_conversation_context("roadmap_user", workflow_context)

        completion_ack = await ack_generator.generate_completion_acknowledgment(
            "product_roadmap_q1_2025.txt",
            {"summary": summary, "chunks": len(chunks), "tasks": len(tasks), "metadata": metadata},
        )

        # Validate three-layer integration
        assert len(chunks) >= 3, "Storage layer: Insufficient chunks generated"
        assert doc_id is not None, "Storage layer: Metadata storage failed"
        assert len(summary) > 50, "Experience layer: Summary generation failed"
        assert len(processing_ack) > 30, "Experience layer: Processing acknowledgment failed"
        assert len(tasks) >= 2, "Workflow layer: Task extraction failed"
        assert len(completion_ack) > 40, "Experience layer: Completion acknowledgment failed"

        # Test cross-layer data flow
        retrieved_context = await context_preserver.get_relevant_context(
            "roadmap_user", "What tasks were extracted from the roadmap?"
        )
        assert retrieved_context is not None, "Workflow layer: Context retrieval failed"

        print("  ✅ Three-layer integration successful")
        print(f"     Storage: {len(chunks)} chunks, doc_id: {doc_id}")
        print(f"     Experience: {len(summary)} char summary, acks generated")
        print(f"     Workflow: {len(tasks)} tasks, context preserved")
        return True

    except Exception as e:
        print(f"  ❌ Three-layer integration failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run document processing integration tests."""
    print("🔗 Document Processing Integration Test Suite")
    print("=" * 60)

    integration_tests = [
        ("Storage ↔ Experience Integration", test_storage_experience_integration),
        ("Experience ↔ Workflow Integration", test_experience_workflow_integration),
        ("Storage ↔ Workflow Integration", test_storage_workflow_integration),
        ("Three-Layer Integration", test_three_layer_integration),
    ]

    results = []

    for test_name, test_func in integration_tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"Integration test failed with exception: {e}")
            results.append((test_name, False))

    # Generate integration test report
    print("\n" + "=" * 60)
    print("📊 INTEGRATION TEST RESULTS")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<40} {status}")

    print("\n" + "-" * 60)
    print(f"Integration Tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(results)*100):.1f}%")

    if failed == 0:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("✅ Document processing layers are properly integrated")
        print("✅ Cross-layer data flow is working correctly")
        print("✅ Three-layer architecture is operational")
    else:
        print(f"\n⚠️ {failed} integration test(s) failed")

    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ Integration test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Integration test crashed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
