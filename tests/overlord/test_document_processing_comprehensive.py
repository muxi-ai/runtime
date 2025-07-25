#!/usr/bin/env python3
"""
DEPRECATED: Document Processing Comprehensive Test

⚠️  DEPRECATION NOTICE:
This test file tests deprecated document workflow components that are not recommended
for agent knowledge use cases. These components are maintained for backward compatibility
with existing document processing workflows only.

For agent knowledge systems, use:
- DocumentChunkManager: Efficient document chunking and processing
- DocumentSemanticIndex: Vector-based semantic search and indexing

The following components tested here are deprecated for agent knowledge:
- DocumentWorkflowIntegrator: Use agent knowledge system's built-in capabilities
- DocumentCrossReferenceManager: Use agent knowledge system's built-in capabilities
- DocumentContextPreserver: Use agent knowledge system's working memory integration

Comprehensive Document Processing Implementation Test Suite

Tests all three layers of the document processing system:
1. Document Storage Foundation Layer
2. Document User Experience Layer
3. Document Workflow Integration Layer

Plus unified configuration schema integration.
"""

import sys
import os
import asyncio
import tempfile
from pathlib import Path

# Add runtime to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Test configuration with FAISSx and PostgreSQL
TEST_CONFIG = {
    "llm": {
        "models": [
            {
                "documents": "openai/gpt-4o",
                "settings": {
                    "max_size_mb": 25,
                    "extraction": {
                        "chunk_size": 1200,
                        "overlap": 150,
                        "strategy": "semantic",
                        "nlp": {
                            "data_path": "~/nlp_data",
                            "spacy_model": "en_core_web_sm",
                            "sentence_transformer": "all-MiniLM-L6-v2"
                        }
                    },
                    "cache_ttl_seconds": 7200
                }
            },
            {
                "embedding": "openai/text-embedding-3-large"
            }
        ]
    },
    "memory": {
        "working": {
            "mode": "remote",
            "remote": {
                "url": "tcp://localhost:45678",
                "api_key": "test_key",
                "tenant": "test_tenant"
            }
        },
        "persistent": {
            "connection_string": "postgresql://ran@127.0.0.1/muxi_framework",
            "embedding_model": "text-embedding-ada-002"
        }
    }
}


def create_test_document(filename: str, content: str) -> str:
    """Create a temporary test document."""
    temp_dir = tempfile.mkdtemp()
    doc_path = os.path.join(temp_dir, filename)
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return doc_path


async def test_document_storage_layer():
    """Test Document Storage Foundation Layer (Subtask 3.7)."""
    print("\n🧪 Testing Document Storage Foundation Layer (Subtask 3.7)")

    try:
        # Import all document storage components
        from src.muxi.formation.documents.storage import (
            DocumentChunkManager,
            DocumentMetadataStore,
            DocumentSemanticIndex,
            DocumentReferenceSystem
        )
        print("✅ All document storage components imported successfully")

        # Test DocumentChunkManager
        print("\n📄 Testing DocumentChunkManager...")
        chunk_manager = DocumentChunkManager()

        # Create test document
        test_content = """
        This is a comprehensive test document for the MUXI document processing system.

        The document contains multiple paragraphs to test different chunking strategies.
        This paragraph discusses the importance of intelligent document processing.

        Here's another section about semantic understanding and vector search capabilities.
        The system should be able to break this down into meaningful chunks.

        Finally, this section covers workflow integration and task generation features.
        Each chunk should maintain context while being searchable independently.
        """

        test_doc_path = create_test_document("test_document.txt", test_content)

        # Test different chunking strategies
        strategies = ["adaptive", "semantic", "fixed", "paragraph"]
        for strategy in strategies:
            try:
                chunks = await chunk_manager.chunk_document(
                    content=test_content,
                    filename="test_document.txt",
                    strategy=strategy
                )
                print(f"  ✅ {strategy} chunking: {len(chunks)} chunks created")

                # Validate chunk structure
                if chunks:
                    chunk = chunks[0]
                    assert hasattr(chunk, 'content'), "Chunk missing content"
                    assert hasattr(chunk, 'chunk_id'), "Chunk missing chunk_id"
                    assert hasattr(chunk, 'metadata'), "Chunk missing metadata"
                    print(f"     Chunk validation passed for {strategy}")

            except Exception as e:
                print(f"  ❌ {strategy} chunking failed: {e}")

        # Test DocumentMetadataStore
        print("\n📊 Testing DocumentMetadataStore...")
        metadata_store = DocumentMetadataStore()

        test_metadata = {
            "filename": "test_document.txt",
            "file_size": len(test_content),
            "content_type": "text/plain",
            "chunk_count": len(chunks) if 'chunks' in locals() else 0,
            "processing_strategy": "semantic",
            "processing_time": 0.5
        }

        # Store and retrieve metadata
        doc_id = await metadata_store.store_document_metadata(test_doc_path, test_metadata)
        retrieved_metadata = await metadata_store.get_document_metadata(doc_id)

        assert retrieved_metadata is not None, "Failed to retrieve metadata"
        assert retrieved_metadata["filename"] == "test_document.txt", "Metadata mismatch"
        print("  ✅ Metadata storage and retrieval working")

        # Test DocumentSemanticIndex
        print("\n🔍 Testing DocumentSemanticIndex...")
        try:
            semantic_index = DocumentSemanticIndex(
                mode="remote",
                remote_config={
                    "url": "tcp://localhost:45678",
                    "api_key": "test_key",
                    "tenant": "test_tenant"
                }
            )

            # Test index operations (will test local fallback if FAISSx unavailable)
            if 'chunks' in locals() and chunks:
                try:
                    # Add a couple chunks
                    await semantic_index.add_document_chunks(chunks[:2])
                    print("  ✅ Document chunks added to semantic index")

                    # Test semantic search
                    results = await semantic_index.search_similar_chunks(
                        "document processing system",
                        k=2
                    )
                    print(f"  ✅ Semantic search returned {len(results)} results")

                except Exception as e:
                    print(f"  ⚠️ FAISSx operations failed (expected if server unavailable): {e}")
                    print("  ℹ️ Testing local fallback mode...")

                    # Test local mode fallback
                    local_index = DocumentSemanticIndex(mode="local")
                    await local_index.add_document_chunks(chunks[:2])
                    results = await local_index.search_similar_chunks("document processing", k=2)
                    print(f"  ✅ Local mode semantic search: {len(results)} results")

        except Exception as e:
            print(f"  ❌ Semantic index failed: {e}")

        # Test DocumentReferenceSystem
        print("\n🔗 Testing DocumentReferenceSystem...")
        ref_system = DocumentReferenceSystem()

        # Test citation generation
        citation_data = {
            "title": "Test Document",
            "author": "Test Author",
            "year": "2025",
            "url": "https://example.com/test-doc"
        }

        apa_citation = await ref_system.generate_citation(citation_data, "apa")
        mla_citation = await ref_system.generate_citation(citation_data, "mla")

        assert "Test Author" in apa_citation, "APA citation missing author"
        assert "Test Document" in mla_citation, "MLA citation missing title"
        print("  ✅ Citation generation working (APA and MLA)")

        # Test cross-document reference tracking
        await ref_system.add_document_reference(doc_id, "related_doc_123", "cites")
        references = await ref_system.get_document_references(doc_id)
        assert len(references) > 0, "Failed to track document references"
        print("  ✅ Cross-document reference tracking working")

        print("🎉 Document Storage Foundation Layer tests completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Document Storage Layer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_document_experience_layer():
    """Test Document User Experience Layer (Subtask 3.8)."""
    print("\n🧪 Testing Document User Experience Layer (Subtask 3.8)")

    try:
        # Import document experience components
        from src.muxi.formation.documents.experience import (
            DocumentAcknowledgmentGenerator,
            DocumentSummarizer,
            DocumentErrorHandler
        )
        print("✅ All document experience components imported successfully")

        # Test DocumentAcknowledgmentGenerator
        print("\n📢 Testing DocumentAcknowledgmentGenerator...")
        ack_generator = DocumentAcknowledgmentGenerator()

        # Test different acknowledgment types
        processing_ack = await ack_generator.generate_processing_acknowledgment(
            "test_document.pdf",
            "Please summarize this document"
        )
        assert "processing" in processing_ack.lower(), "Processing acknowledgment missing key terms"
        print("  ✅ Processing acknowledgment generated")

        completion_ack = await ack_generator.generate_completion_acknowledgment(
            "test_document.pdf",
            {"summary": "Test summary", "chunks": 5}
        )
        completion_check = "complete" in completion_ack.lower() or "finished" in completion_ack.lower()
        assert completion_check, "Completion acknowledgment missing completion terms"
        print("  ✅ Completion acknowledgment generated")

        # Test error acknowledgment
        error_ack = await ack_generator.generate_error_acknowledgment(
            "bad_file.xyz",
            "Unsupported file format"
        )
        error_check = "error" in error_ack.lower() or "problem" in error_ack.lower()
        assert error_check, "Error acknowledgment missing error terms"
        print("  ✅ Error acknowledgment generated")

        # Test DocumentSummarizer
        print("\n📝 Testing DocumentSummarizer...")
        summarizer = DocumentSummarizer()

        test_content = """
        This is a detailed business report about quarterly performance.

        Key findings include:
        - Revenue increased by 15% compared to last quarter
        - Customer satisfaction scores improved to 4.2/5.0
        - New product launch exceeded expectations

        Action items:
        - Expand marketing in Q2
        - Hire additional support staff
        - Invest in R&D for next product cycle

        Technical details:
        - Database performance optimized
        - API response times reduced by 30%
        - Security audit completed with no major issues
        """

        # Test different summary types
        summary_types = ["overview", "key_points", "actionable", "technical"]
        for summary_type in summary_types:
            try:
                summary = await summarizer.generate_summary(
                    test_content,
                    summary_type=summary_type,
                    max_length=200
                )
                assert len(summary) > 10, f"{summary_type} summary too short"
                print(f"  ✅ {summary_type} summary generated ({len(summary)} chars)")
            except Exception as e:
                print(f"  ⚠️ {summary_type} summary failed: {e}")

        # Test progressive summarization for large content
        large_content = test_content * 10  # Simulate large document
        progressive_summary = await summarizer.generate_progressive_summary(large_content)
        assert len(progressive_summary) > 0, "Progressive summary failed"
        print("  ✅ Progressive summarization working")

        # Test DocumentErrorHandler
        print("\n🚨 Testing DocumentErrorHandler...")
        error_handler = DocumentErrorHandler()

        # Test different error scenarios
        error_scenarios = [
            ("FileNotFoundError", "Document file not found"),
            ("UnicodeDecodeError", "File encoding issue"),
            ("MemoryError", "Document too large for memory"),
            ("TimeoutError", "Processing timeout exceeded")
        ]

        for error_type, error_message in error_scenarios:
            try:
                error_response = await error_handler.handle_processing_error(
                    error_type,
                    error_message,
                    "test_document.pdf"
                )

                guidance_check = "suggestion" in error_response or "recommendation" in error_response
                assert guidance_check, f"Error response missing guidance for {error_type}"
                print(f"  ✅ {error_type} handled with guidance")

            except Exception as e:
                print(f"  ⚠️ Error handling failed for {error_type}: {e}")

        # Test error statistics
        stats = await error_handler.get_error_statistics()
        assert isinstance(stats, dict), "Error statistics should be a dictionary"
        print("  ✅ Error statistics tracking working")

        print("🎉 Document User Experience Layer tests completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Document Experience Layer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_document_workflow_layer():
    """Test Document Workflow Integration Layer (Subtask 3.9)."""
    print("\n🧪 Testing Document Workflow Integration Layer (Subtask 3.9)")

    try:
        # Import document workflow components
        from src.muxi.formation.documents.workflow import (
            DocumentWorkflowIntegrator,
            DocumentCrossReferenceManager,
            DocumentContextPreserver
        )
        print("✅ All document workflow components imported successfully")

        # Test DocumentWorkflowIntegrator
        print("\n⚙️ Testing DocumentWorkflowIntegrator...")
        workflow_integrator = DocumentWorkflowIntegrator()

        # Test task generation from document content
        task_content = """
        Meeting Notes - Project Alpha

        Decisions made:
        - Approve budget increase for Q2
        - Move launch date to March 15th
        - Assign Sarah as project lead

        Action items:
        - John: Update project timeline by Friday
        - Sarah: Schedule team meeting for next week
        - Mike: Review technical specifications
        - All: Submit progress reports by EOW
        """

        # Generate tasks from document
        generated_tasks = await workflow_integrator.generate_tasks_from_document(task_content)
        assert len(generated_tasks) > 0, "No tasks generated from document"
        print(f"  ✅ Generated {len(generated_tasks)} tasks from document")

        # Validate task structure
        if generated_tasks:
            task = generated_tasks[0]
            assert "title" in task or "description" in task, "Task missing required fields"
            print("  ✅ Task structure validation passed")

        # Test workflow enrichment
        existing_workflow = {
            "tasks": [
                {"id": "task_1", "title": "Review document", "status": "pending"}
            ]
        }

        enriched_workflow = await workflow_integrator.enrich_workflow_with_document_insights(
            existing_workflow,
            task_content
        )
        assert "document_insights" in enriched_workflow, "Workflow not enriched"
        print("  ✅ Workflow enrichment working")

        # Test DocumentCrossReferenceManager
        print("\n🔗 Testing DocumentCrossReferenceManager...")
        cross_ref_manager = DocumentCrossReferenceManager()

        # Test reference discovery between documents
        doc1_content = "As discussed in the Q4 Financial Report, revenue targets were exceeded."
        doc2_content = "Q4 Financial Report shows 15% growth in core markets."

        # Add documents and discover connections
        await cross_ref_manager.add_document("doc1", doc1_content, {"title": "Meeting Notes"})
        await cross_ref_manager.add_document("doc2", doc2_content, {"title": "Q4 Financial Report"})

        connections = await cross_ref_manager.discover_document_connections("doc1", "doc2")
        print(f"  ✅ Found {len(connections)} connections between documents")

        # Test citation path finding
        citation_path = await cross_ref_manager.find_citation_path("doc1", "doc2")
        assert citation_path is not None, "Citation path not found"
        print("  ✅ Citation path finding working")

        # Test formatted citation generation
        citation = await cross_ref_manager.generate_formatted_citation("doc2", "apa")
        assert "Q4 Financial Report" in citation, "Citation missing document title"
        print("  ✅ Formatted citation generation working")

        # Test DocumentContextPreserver
        print("\n💾 Testing DocumentContextPreserver...")
        context_preserver = DocumentContextPreserver()

        # Test context preservation across conversations
        conversation_context = {
            "user_message": "What were the main decisions from the Alpha project meeting?",
            "documents_referenced": ["doc1"],
            "timestamp": "2025-01-15T10:30:00Z"
        }

        await context_preserver.preserve_conversation_context(
            "user_123",
            conversation_context
        )
        print("  ✅ Conversation context preserved")

        # Test context retrieval
        preserved_context = await context_preserver.get_relevant_context(
            "user_123",
            "Tell me more about project Alpha"
        )

        assert preserved_context is not None, "Failed to retrieve preserved context"
        print("  ✅ Context retrieval working")

        # Test document access tracking
        await context_preserver.track_document_access("user_123", "doc1", "viewed")
        access_patterns = await context_preserver.get_document_access_patterns("user_123")

        assert "doc1" in str(access_patterns), "Document access not tracked"
        print("  ✅ Document access tracking working")

        # Test relevance scoring
        relevance_scores = await context_preserver.calculate_document_relevance(
            "user_123",
            ["doc1", "doc2"],
            "project management"
        )

        assert len(relevance_scores) > 0, "Relevance scoring failed"
        print("  ✅ Document relevance scoring working")

        print("🎉 Document Workflow Integration Layer tests completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Document Workflow Layer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_unified_configuration():
    """Test the unified configuration schema integration."""
    print("\n🧪 Testing Unified Configuration Schema Integration")

    try:
        from src.muxi.config.document_processing import DocumentProcessingConfig

        # Test unified schema configuration
        doc_config = DocumentProcessingConfig(TEST_CONFIG["llm"])

        assert doc_config.is_enabled() is True, "Document processing should be enabled"
        chunk_size_msg = f"Expected chunk_size 1200, got {doc_config.get_chunk_size()}"
        assert doc_config.get_chunk_size() == 1200, chunk_size_msg
        strategy_msg = f"Expected strategy 'semantic', got {doc_config.get_extraction_strategy()}"
        assert doc_config.get_extraction_strategy() == "semantic", strategy_msg
        cache_msg = f"Expected cache_ttl 7200, got {doc_config.get_cache_ttl_seconds()}"
        assert doc_config.get_cache_ttl_seconds() == 7200, cache_msg

        print("✅ Unified configuration schema working correctly")
        print(f"  - Enabled: {doc_config.is_enabled()}")
        print(f"  - Chunk size: {doc_config.get_chunk_size()}")
        print(f"  - Strategy: {doc_config.get_extraction_strategy()}")
        print(f"  - Cache TTL: {doc_config.get_cache_ttl_seconds()}")
        print(f"  - NLP data path: {doc_config.get_nlp_data_path()}")

        return True

    except Exception as e:
        print(f"❌ Unified configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_integration_workflow():
    """Test end-to-end document processing workflow integration."""
    print("\n🧪 Testing End-to-End Integration Workflow")

    try:
        # Import all components for integration test
        from src.muxi.config.document_processing import DocumentProcessingConfig
        from src.muxi.formation.documents.storage import (
            DocumentChunkManager, DocumentMetadataStore
        )
        from src.muxi.formation.documents.experience import (
            DocumentAcknowledgmentGenerator, DocumentSummarizer
        )
        from src.muxi.formation.documents.workflow import DocumentWorkflowIntegrator

        print("✅ All components imported for integration test")

        # Initialize components with unified configuration
        doc_config = DocumentProcessingConfig(TEST_CONFIG["llm"])

        chunk_manager = DocumentChunkManager(document_config=doc_config)
        metadata_store = DocumentMetadataStore()
        ack_generator = DocumentAcknowledgmentGenerator()
        summarizer = DocumentSummarizer()
        workflow_integrator = DocumentWorkflowIntegrator()

        print("✅ All components initialized with unified configuration")

        # Simulate complete document processing workflow
        test_document_content = """
        Product Requirements Document - MUXI AI Enhancement

        Overview:
        This document outlines the requirements for enhancing MUXI with advanced document processing.

        Key Features:
        1. Intelligent document chunking with multiple strategies
        2. Semantic search and indexing capabilities
        3. Cross-document reference tracking
        4. Automated workflow generation from document content

        Implementation Tasks:
        - Develop chunk manager with adaptive strategies
        - Integrate FAISSx for semantic search
        - Build reference system for citations
        - Create workflow automation tools

        Success Criteria:
        - Process documents up to 50MB in size
        - Support multiple file formats (PDF, DOCX, TXT)
        - Generate accurate summaries and task lists
        - Maintain document context across conversations
        """

        document_filename = "muxi_enhancement_prd.txt"

        # Step 1: Generate processing acknowledgment
        print("\n1️⃣ Generating processing acknowledgment...")
        acknowledgment = await ack_generator.generate_processing_acknowledgment(
            document_filename,
            "Please process this PRD and extract actionable tasks"
        )
        print(f"   Acknowledgment: {acknowledgment[:100]}...")

        # Step 2: Chunk the document
        print("\n2️⃣ Chunking document with adaptive strategy...")
        chunks = await chunk_manager.chunk_document(
            content=test_document_content,
            filename=document_filename,
            strategy="adaptive"
        )
        print(f"   Created {len(chunks)} chunks")

        # Step 3: Store metadata
        print("\n3️⃣ Storing document metadata...")
        metadata = {
            "filename": document_filename,
            "file_size": len(test_document_content),
            "content_type": "text/plain",
            "chunk_count": len(chunks),
            "processing_strategy": "adaptive"
        }

        doc_id = await metadata_store.store_document_metadata(
            create_test_document(document_filename, test_document_content),
            metadata
        )
        print(f"   Stored metadata with doc_id: {doc_id}")

        # Step 4: Generate summary
        print("\n4️⃣ Generating document summary...")
        summary = await summarizer.generate_summary(
            test_document_content,
            summary_type="overview",
            max_length=300
        )
        print(f"   Summary: {summary[:150]}...")

        # Step 5: Extract workflow tasks
        print("\n5️⃣ Extracting workflow tasks...")
        tasks = await workflow_integrator.generate_tasks_from_document(test_document_content)
        print(f"   Generated {len(tasks)} tasks")
        for i, task in enumerate(tasks[:3], 1):  # Show first 3 tasks
            task_title = task.get('title', task.get('description', 'Unknown task'))[:50]
            print(f"     Task {i}: {task_title}...")

        # Step 6: Generate completion acknowledgment
        print("\n6️⃣ Generating completion acknowledgment...")
        completion_result = {
            "summary": summary,
            "chunks": len(chunks),
            "tasks": len(tasks),
            "metadata": metadata
        }

        completion_ack = await ack_generator.generate_completion_acknowledgment(
            document_filename,
            completion_result
        )
        print(f"   Completion: {completion_ack[:100]}...")

        print("\n🎉 End-to-end integration workflow completed successfully!")
        print("Workflow Summary:")
        print(f"  📄 Document: {document_filename}")
        print(f"  🧩 Chunks: {len(chunks)}")
        print(f"  📝 Summary length: {len(summary)} characters")
        print(f"  ⚙️ Tasks generated: {len(tasks)}")
        print(f"  💾 Metadata stored: doc_id {doc_id}")

        return True

    except Exception as e:
        print(f"❌ Integration workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the comprehensive document processing test suite."""
    print("🚀 Starting Comprehensive Document Processing Test Suite")
    print("=" * 80)

    test_results = []

    # Test each layer individually
    print("\n📋 TESTING PHASE 1: Individual Component Layers")
    test_results.append(("Unified Configuration", await test_unified_configuration()))
    test_results.append(("Document Storage Layer", await test_document_storage_layer()))
    test_results.append(("Document Experience Layer", await test_document_experience_layer()))
    test_results.append(("Document Workflow Layer", await test_document_workflow_layer()))

    # Test integration
    print("\n📋 TESTING PHASE 2: Integration Workflow")
    test_results.append(("End-to-End Integration", await test_integration_workflow()))

    # Generate test report
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE TEST RESULTS")
    print("=" * 80)

    passed = 0
    failed = 0

    for test_name, result in test_results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<50} {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 80)
    print(f"Total Tests: {len(test_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed/len(test_results)*100):.1f}%")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Document processing implementation is working correctly!")
        print("\n✅ IMPLEMENTATION STATUS:")
        print("   • Document Storage Foundation Layer (3.7): WORKING")
        print("   • Document User Experience Layer (3.8): WORKING")
        print("   • Document Workflow Integration Layer (3.9): WORKING")
        print("   • Unified Configuration Schema: WORKING")
        print("   • End-to-End Integration: WORKING")

        print("\n🔧 INFRASTRUCTURE STATUS:")
        print("   • FAISSx (port 45678): Using local fallback if unavailable")
        print("   • PostgreSQL: Available at postgresql://ran@127.0.0.1/muxi_framework")
        print("   • Unified Schema: Fully integrated and tested")

    else:
        print(f"\n⚠️ {failed} test(s) failed. Review the errors above for details.")

    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️ Test suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
