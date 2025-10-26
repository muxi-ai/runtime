"""
Unit tests for atomic_yaml function renaming and deprecation.
"""

import pytest
import tempfile
import warnings
from pathlib import Path

from muxi.formation.utils.atomic_yaml import (
    update_yaml,
    atomic_update_yaml,
    atomic_write_yaml,
    atomic_read_yaml,
)


@pytest.mark.asyncio
async def test_update_yaml_basic_functionality():
    """Test that update_yaml works correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.yaml"
        
        # Create initial file
        await atomic_write_yaml(file_path, {"key1": "value1", "key2": "value2"})
        
        # Update with new data
        await update_yaml(file_path, {"key2": "updated", "key3": "new"})
        
        # Read and verify
        result = await atomic_read_yaml(file_path)
        assert result["key1"] == "value1"
        assert result["key2"] == "updated"
        assert result["key3"] == "new"


@pytest.mark.asyncio
async def test_update_yaml_deep_merge():
    """Test that update_yaml performs deep merge correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.yaml"
        
        # Create initial file with nested structure
        await atomic_write_yaml(file_path, {
            "section1": {"a": 1, "b": 2},
            "section2": {"c": 3}
        })
        
        # Update with deep merge
        await update_yaml(file_path, {
            "section1": {"b": 20, "d": 4}  # Should merge, not replace
        }, deep_merge=True)
        
        # Read and verify
        result = await atomic_read_yaml(file_path)
        assert result["section1"]["a"] == 1  # Original preserved
        assert result["section1"]["b"] == 20  # Updated
        assert result["section1"]["d"] == 4  # New field added
        assert result["section2"]["c"] == 3  # Other section preserved


@pytest.mark.asyncio
async def test_update_yaml_shallow_merge():
    """Test that update_yaml with shallow merge replaces nested dicts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.yaml"
        
        # Create initial file
        await atomic_write_yaml(file_path, {
            "section1": {"a": 1, "b": 2},
            "section2": {"c": 3}
        })
        
        # Update with shallow merge
        await update_yaml(file_path, {
            "section1": {"d": 4}  # Should replace entire section1
        }, deep_merge=False)
        
        # Read and verify
        result = await atomic_read_yaml(file_path)
        assert result["section1"] == {"d": 4}  # Replaced, not merged
        assert result["section2"]["c"] == 3  # Other section preserved


@pytest.mark.asyncio
async def test_atomic_update_yaml_deprecation_warning():
    """Test that atomic_update_yaml raises deprecation warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.yaml"
        
        # Create initial file
        await atomic_write_yaml(file_path, {"key": "value"})
        
        # Use deprecated function - should warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await atomic_update_yaml(file_path, {"key": "updated"})
            
            # Verify warning
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "atomic_update_yaml is deprecated" in str(w[0].message)
            assert "update_yaml" in str(w[0].message)
            assert "NOT safe for concurrent" in str(w[0].message)
        
        # Verify it still works
        result = await atomic_read_yaml(file_path)
        assert result["key"] == "updated"


@pytest.mark.asyncio
async def test_update_yaml_file_not_found():
    """Test that update_yaml raises FileNotFoundError for missing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError):
            await update_yaml(file_path, {"key": "value"})


@pytest.mark.asyncio
async def test_update_yaml_preserves_permissions():
    """Test that update_yaml preserves file permissions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.yaml"
        
        # Create file with specific permissions
        await atomic_write_yaml(file_path, {"key": "value"})
        import os
        os.chmod(file_path, 0o600)  # Read/write for owner only
        
        original_mode = file_path.stat().st_mode
        
        # Update file
        await update_yaml(file_path, {"key": "updated"}, preserve_permissions=True)
        
        # Verify permissions preserved
        new_mode = file_path.stat().st_mode
        assert original_mode == new_mode


def test_module_docstring_has_concurrency_warning():
    """Test that module docstring contains prominent concurrency warning."""
    from muxi.formation.utils import atomic_yaml
    
    docstring = atomic_yaml.__doc__
    assert "CRITICAL" in docstring
    assert "CONCURRENCY WARNING" in docstring
    assert "NOT safe" in docstring
    assert "lost updates" in docstring
    assert "external locking" in docstring


def test_update_yaml_docstring_has_detailed_warning():
    """Test that update_yaml docstring has detailed concurrency warning."""
    docstring = update_yaml.__doc__
    
    # Check for critical warnings
    assert "CRITICAL" in docstring
    assert "CONCURRENCY WARNING" in docstring
    assert "NOT safe" in docstring
    
    # Check for race condition explanation
    assert "Process A" in docstring
    assert "Process B" in docstring
    assert "LOST" in docstring
    
    # Check for locking example
    assert "FileLock" in docstring
    assert "example" in docstring.lower()
