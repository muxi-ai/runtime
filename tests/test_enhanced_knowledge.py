#!/usr/bin/env python3

import os
import sys
import tempfile
import asyncio
from pathlib import Path

# Set up the path to import the muxi package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

# Now import the muxi modules
from runtime.muxi.runtime.knowledge.base import FileKnowledge  # noqa: E402
from runtime.muxi.runtime.knowledge.handler import KnowledgeHandler  # noqa: E402


def create_test_files():
    """Create test files and directories for testing."""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()

    # Create some test files
    test_files = {
        "doc1.txt": ("This is a sample document about Python programming. "
                     "It covers basic concepts."),
        "doc2.md": ("# Machine Learning Guide\n\n"
                    "This document covers machine learning fundamentals."),
        "subfolder/doc3.txt": "Advanced Python topics including asyncio and coroutines.",
        "subfolder/nested/doc4.md": ("# Data Science\n\n"
                                     "Comprehensive guide to data analysis."),
        "other.pdf": "This is a PDF document (simulated as text).",
        "ignore.log": "This file should be ignored due to extension filter."
    }

    # Create files
    for rel_path, content in test_files.items():
        file_path = Path(temp_dir) / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return temp_dir


async def mock_embedding_function(text):
    """Mock embedding function for testing."""
    # Return a simple vector based on text length and hash
    import hashlib
    hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    # Create a 1536-dimensional vector (matching OpenAI embeddings)
    vector = [(hash_val + i) % 1000 / 1000.0 for i in range(1536)]
    return vector


async def test_single_file():
    """Test FileKnowledge with a single file."""
    print("Testing single file...")

    temp_dir = create_test_files()

    # Test single file
    single_file_path = os.path.join(temp_dir, "doc1.txt")
    knowledge = FileKnowledge(
        path=single_file_path,
        description="Test single file"
    )

    # Verify discovered files
    files = knowledge._discover_files()
    assert len(files) == 1
    assert files[0] == single_file_path

    # Test retrieval
    results = await knowledge.retrieve("Python", limit=5)
    assert len(results) == 1
    assert "Python programming" in results[0]["content"]

    print("✅ Single file test passed")


async def test_directory_recursive():
    """Test FileKnowledge with directory (recursive)."""
    print("Testing directory recursive...")

    temp_dir = create_test_files()

    # Test directory (recursive)
    knowledge = FileKnowledge(
        path=temp_dir,
        description="Test directory recursive",
        recursive=True,
        allowed_extensions=[".txt", ".md"]
    )

    # Verify discovered files
    files = knowledge._discover_files()
    print(f"Found files: {files}")

    # Should find all .txt and .md files recursively
    assert len(files) == 4  # doc1.txt, doc2.md, doc3.txt, doc4.md
    assert any("doc1.txt" in f for f in files)
    assert any("doc2.md" in f for f in files)
    assert any("doc3.txt" in f for f in files)
    assert any("doc4.md" in f for f in files)

    # Should not include .pdf or .log files
    assert not any("other.pdf" in f for f in files)
    assert not any("ignore.log" in f for f in files)

    print("✅ Directory recursive test passed")


async def test_directory_non_recursive():
    """Test FileKnowledge with directory (non-recursive)."""
    print("Testing directory non-recursive...")

    temp_dir = create_test_files()

    # Test directory (non-recursive)
    knowledge = FileKnowledge(
        path=temp_dir,
        description="Test directory non-recursive",
        recursive=False,
        allowed_extensions=[".txt", ".md"]
    )

    # Verify discovered files
    files = knowledge._discover_files()
    print(f"Found files (non-recursive): {files}")

    # Should only find files in root directory
    assert len(files) == 2  # doc1.txt, doc2.md
    assert any("doc1.txt" in f for f in files)
    assert any("doc2.md" in f for f in files)

    # Should not include files in subdirectories
    assert not any("doc3.txt" in f for f in files)
    assert not any("doc4.md" in f for f in files)

    print("✅ Directory non-recursive test passed")


async def test_from_config():
    """Test FileKnowledge.from_config method."""
    print("Testing from_config...")

    temp_dir = create_test_files()

    # Test from_config
    config = {
        "path": temp_dir,
        "description": "Test config knowledge",
        "recursive": True,
        "allowed_extensions": [".txt"],
        "name": "test_knowledge"
    }

    knowledge = FileKnowledge.from_config(config)

    # Verify properties
    assert knowledge.path == temp_dir
    assert knowledge.description == "Test config knowledge"
    assert knowledge.recursive is True
    assert knowledge.allowed_extensions == [".txt"]
    assert knowledge.name == "test_knowledge"

    # Verify discovered files (only .txt)
    files = knowledge._discover_files()
    assert len(files) == 2  # doc1.txt, doc3.txt
    assert all(f.endswith(".txt") for f in files)

    print("✅ from_config test passed")


async def test_knowledge_handler_from_config():
    """Test KnowledgeHandler.from_agent_config method."""
    print("Testing KnowledgeHandler.from_agent_config...")

    temp_dir = create_test_files()

    # Test configuration matching the new YAML schema
    knowledge_config = {
        "enabled": True,
        "sources": [
            {
                "path": os.path.join(temp_dir, "doc1.txt"),
                "description": "Single file source"
            },
            {
                "path": temp_dir,
                "description": "Directory source",
                "recursive": True,
                "allowed_extensions": [".md"]
            }
        ]
    }

    # Create handler from config
    handler = await KnowledgeHandler.from_agent_config(
        agent_id="test_agent",
        knowledge_config=knowledge_config,
        generate_embeddings_fn=mock_embedding_function,
        embedding_dimension=1536,
        mode="local"
    )

    # Verify handler was created
    assert handler is not None
    assert handler.agent_id == "test_agent"

    # Should have processed documents from both sources
    assert len(handler.documents) >= 3  # At least 1 .txt + 2 .md files

    print("✅ KnowledgeHandler.from_agent_config test passed")


async def test_disabled_knowledge():
    """Test disabled knowledge configuration."""
    print("Testing disabled knowledge...")

    knowledge_config = {
        "enabled": False,
        "sources": [
            {
                "path": "/some/path",
                "description": "Should be ignored"
            }
        ]
    }

    # Create handler from config
    handler = await KnowledgeHandler.from_agent_config(
        agent_id="test_agent",
        knowledge_config=knowledge_config,
        generate_embeddings_fn=mock_embedding_function
    )

    # Should return None when disabled
    assert handler is None

    print("✅ Disabled knowledge test passed")


async def test_search_functionality():
    """Test search functionality with the enhanced knowledge handler."""
    print("Testing search functionality...")

    temp_dir = create_test_files()

    # Create handler with multiple sources
    knowledge_config = {
        "enabled": True,
        "sources": [
            {
                "path": temp_dir,
                "description": "All documents",
                "recursive": True,
                "allowed_extensions": [".txt", ".md"]
            }
        ]
    }

    handler = await KnowledgeHandler.from_agent_config(
        agent_id="test_agent",
        knowledge_config=knowledge_config,
        generate_embeddings_fn=mock_embedding_function,
        embedding_dimension=1536,
        mode="local"
    )

    # Test search
    results = await handler.search(
        query="Python programming",
        generate_embedding_fn=mock_embedding_function,
        top_k=3
    )

    # Should return relevant results
    assert len(results) > 0
    assert all("content" in result for result in results)
    assert all("source" in result for result in results)

    print("✅ Search functionality test passed")


async def main():
    """Run all tests."""
    print("🧪 Starting Enhanced Knowledge Handler Tests\n")

    try:
        await test_single_file()
        await test_directory_recursive()
        await test_directory_non_recursive()
        await test_from_config()
        await test_knowledge_handler_from_config()
        await test_disabled_knowledge()
        await test_search_functionality()

        print("\n🎉 All tests passed! Enhanced knowledge handler is working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    asyncio.run(main())
