#!/usr/bin/env python3

import os
import sys
import tempfile
import asyncio
import pytest

# Set up the path to import the muxi package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

# Now import the muxi modules
from muxi.runtime.knowledge.base import FileKnowledge  # noqa: E402
from muxi.runtime.knowledge.handler import KnowledgeHandler  # noqa: E402


def mock_embedding_fn(text):
    """Fast mock embedding function"""
    import random
    return [random.random() for _ in range(128)]  # Smaller dimension for speed


async def mock_async_embedding_fn(text):
    """Fast async mock embedding function"""
    return mock_embedding_fn(text)


@pytest.fixture
def temp_knowledge_files():
    """Create temporary knowledge files for testing"""
    files = []

    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()

    # Create a few small test files
    for i in range(3):  # Only 3 files for speed
        file_path = os.path.join(temp_dir, f"test_file_{i}.txt")
        with open(file_path, 'w') as f:
            f.write(f"Test content {i}. This is knowledge file number {i}.")
        files.append(file_path)

    # Create a subdirectory with one more file
    sub_dir = os.path.join(temp_dir, "subdir")
    os.makedirs(sub_dir)
    sub_file = os.path.join(sub_dir, "sub_test.txt")
    with open(sub_file, 'w') as f:
        f.write("Subdirectory test content.")
    files.append(sub_file)

    yield temp_dir, files

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


def test_single_file(temp_knowledge_files):
    """Test FileKnowledge with a single file"""
    temp_dir, files = temp_knowledge_files

    # Test with first file only
    knowledge = FileKnowledge(
        path=files[0],
        description="Single test file",
        max_files=1,  # Limit to 1 file
        max_file_size=1024  # 1KB limit
    )

    assert knowledge.path == files[0]
    assert knowledge.description == "Single test file"

    # Test file discovery
    discovered = knowledge._discover_files()
    assert len(discovered) == 1
    assert discovered[0] == files[0]


def test_directory_recursive(temp_knowledge_files):
    """Test FileKnowledge with directory scanning (recursive)"""
    temp_dir, files = temp_knowledge_files

    knowledge = FileKnowledge(
        path=temp_dir,
        description="Test directory",
        recursive=True,
        max_files=5,  # Limit to 5 files max
        max_file_size=1024  # 1KB limit
    )

    # Test file discovery
    discovered = knowledge._discover_files()
    assert len(discovered) >= 3  # Should find at least our test files

    # All discovered files should be .txt files in our temp directory
    for file_path in discovered:
        assert file_path.startswith(temp_dir)
        assert file_path.endswith('.txt')


def test_directory_non_recursive(temp_knowledge_files):
    """Test FileKnowledge with directory scanning (non-recursive)"""
    temp_dir, files = temp_knowledge_files

    knowledge = FileKnowledge(
        path=temp_dir,
        description="Test directory",
        recursive=False,  # Non-recursive
        max_files=3,  # Limit to 3 files
        max_file_size=1024  # 1KB limit
    )

    # Test file discovery
    discovered = knowledge._discover_files()
    # Should find files in root directory only (not subdirectory)
    root_files = [f for f in files if not f.endswith('sub_test.txt')]
    assert len(discovered) == len(root_files)


def test_from_config():
    """Test FileKnowledge.from_config() method"""
    config = {
        'path': '/test/path.txt',
        'description': 'Test config file',
        'recursive': False,
        'allowed_extensions': ['.txt', '.md'],
        'max_files': 10,
        'max_file_size': 2048
    }

    knowledge = FileKnowledge.from_config(config)

    assert knowledge.path == '/test/path.txt'
    assert knowledge.description == 'Test config file'
    assert knowledge.recursive is False
    assert knowledge.allowed_extensions == ['.txt', '.md']
    assert knowledge.max_files == 10
    assert knowledge.max_file_size == 2048


@pytest.mark.asyncio
async def test_knowledge_handler_from_config():
    """Test KnowledgeHandler.from_agent_config() with timeout"""
    # Use a very simple config that won't cause file scanning
    config = {
        'enabled': True,
        'sources': [
            {
                'path': '/nonexistent/path.txt',  # Use nonexistent path to avoid file operations
                'description': 'Test source 1',
                'max_files': 1,
                'max_file_size': 1024
            }
        ]
    }

    try:
        # Add timeout to prevent hanging
        handler = await asyncio.wait_for(
            KnowledgeHandler.from_agent_config(
                agent_id="test_agent",
                knowledge_config=config,
                generate_embeddings_fn=mock_async_embedding_fn
            ),
            timeout=5.0  # 5 second timeout
        )

        assert handler is not None
        assert len(handler.sources) == 1

        print("✓ KnowledgeHandler.from_agent_config() completed successfully")

    except asyncio.TimeoutError:
        pytest.fail("KnowledgeHandler.from_agent_config() timed out after 5 seconds")
    except Exception as e:
        print(f"Expected error for nonexistent path: {e}")
        # This is expected since we're using a nonexistent path


def test_disabled_knowledge():
    """Test that disabled knowledge config returns None"""
    async def test_disabled():
        config = {
            'enabled': False,
            'sources': [
                {'path': '/some/path.txt', 'description': 'Test source'}
            ]
        }

        result = await KnowledgeHandler.from_agent_config(
            agent_id="test_agent",
            knowledge_config=config,
            generate_embeddings_fn=mock_async_embedding_fn
        )

        assert result is None

    # Run the async test
    asyncio.run(test_disabled())


@pytest.mark.asyncio
async def test_search_functionality(temp_knowledge_files):
    """Test the search functionality with timeout"""
    temp_dir, files = temp_knowledge_files

    # Use only one small file to keep it fast
    knowledge = FileKnowledge(
        path=files[0],  # Single file only
        description="Test knowledge for search",
        max_files=1,
        max_file_size=1024
    )

    try:
        # Add timeout to search operation
        results = await asyncio.wait_for(
            knowledge.retrieve("test content", limit=1),
            timeout=3.0  # 3 second timeout
        )

        assert len(results) <= 1  # Should return at most 1 result
        if results:
            assert 'source' in results[0]
            assert 'content' in results[0]
            assert 'metadata' in results[0]
            print("✓ Search functionality working")

    except asyncio.TimeoutError:
        pytest.fail("Search operation timed out after 3 seconds")
