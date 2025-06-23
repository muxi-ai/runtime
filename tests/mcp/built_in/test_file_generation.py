"""
Tests for the File Generation MCP server.

This module tests the file generation MCP server including:
- Code validation
- File generation
- Security constraints
- MCP protocol handling
"""

import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.services.mcp.built_in import file_generation


class TestCodeValidation:
    """Test the code validation functionality."""
    
    def test_valid_imports(self):
        """Test that allowed imports pass validation."""
        test_cases = [
            "import matplotlib.pyplot as plt",
            "import pandas as pd",
            "from docx import Document",
            "import numpy as np\nimport seaborn as sns",
            "from PIL import Image",
            "import json\nimport csv",
        ]
        
        for code in test_cases:
            is_valid, error = file_generation.validate_code(code)
            assert is_valid is True, f"Code should be valid: {code}"
            assert error is None
    
    def test_invalid_imports(self):
        """Test that disallowed imports are rejected."""
        test_cases = [
            ("import os", "Import not allowed: os"),
            ("import subprocess", "Import not allowed: subprocess"),
            ("from socket import *", "Import not allowed: socket"),
            ("import requests", "Import not allowed: requests"),
            ("import sys", "Import not allowed: sys"),
        ]
        
        for code, expected_error in test_cases:
            is_valid, error = file_generation.validate_code(code)
            assert is_valid is False, f"Code should be invalid: {code}"
            assert expected_error in error
    
    def test_dangerous_operations(self):
        """Test that dangerous operations are rejected."""
        test_cases = [
            ("exec('print(1)')", "Function not allowed: exec"),
            ("eval('2+2')", "Function not allowed: eval"),
            ("compile('x=1', 'test', 'exec')", "Function not allowed: compile"),
            ("__import__('os')", "Function not allowed: __import__"),
            ("getattr(os, 'system')", "Function not allowed: getattr"),
            ("builtins.exec('print(1)')", "Access to module not allowed: builtins.exec"),
            ("sys.modules['os']", "Access to sys.modules not allowed"),
            ("x.__class__", "Attribute access not allowed: __class__"),
            ("obj.__globals__", "Attribute access not allowed: __globals__"),
        ]
        
        for code, expected_error in test_cases:
            is_valid, error = file_generation.validate_code(code)
            assert is_valid is False, f"Code should be invalid: {code}"
            assert expected_error in error
    
    def test_syntax_errors(self):
        """Test that syntax errors are caught."""
        test_cases = [
            "import matplotlib as",
            "def broken(:\n    pass",
            "print('unclosed string",
        ]
        
        for code in test_cases:
            is_valid, error = file_generation.validate_code(code)
            assert is_valid is False, f"Code should have syntax error: {code}"
            assert "Syntax error" in error


class TestFileGeneration:
    """Test the file generation functionality."""
    
    def test_successful_file_generation(self):
        """Test successful file generation."""
        code = """
import json
data = {"test": "value", "number": 42}
with open("test_output.json", "w") as f:
    json.dump(data, f)
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the output directory
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                result = file_generation.generate_file(code)
                
                assert "error" not in result
                assert "file_path" in result
                assert "filename" in result
                assert result["filename"] == "test_output.json"
                
                # Verify file was created
                file_path = Path(result["file_path"])
                assert file_path.exists()
                
                # Verify file contents
                with open(file_path, "r") as f:
                    data = json.load(f)
                    assert data == {"test": "value", "number": 42}
    
    def test_file_generation_with_error(self):
        """Test file generation with execution error."""
        code = """
import pandas as pd
# This will cause an error
df = pd.DataFrame(undefined_variable)
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                result = file_generation.generate_file(code)
                
                assert "error" in result
                assert "NameError" in result["error"] or "undefined_variable" in result["error"]
    
    def test_file_generation_timeout(self):
        """Test file generation with timeout."""
        code = """
import time
time.sleep(35)  # Longer than MAX_EXECUTION_TIME
"""
        
        # Temporarily reduce timeout for faster testing
        original_timeout = file_generation.MAX_EXECUTION_TIME
        file_generation.MAX_EXECUTION_TIME = 1
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                    result = file_generation.generate_file(code)
                    
                    assert "error" in result
                    assert "timed out" in result["error"]
        finally:
            file_generation.MAX_EXECUTION_TIME = original_timeout
    
    def test_no_file_generated(self):
        """Test when code doesn't generate any file."""
        code = """
# This code doesn't create any files
x = 1 + 1
print(x)
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                result = file_generation.generate_file(code)
                
                assert "error" in result
                assert "No file was generated" in result["error"]


class TestMCPProtocol:
    """Test MCP protocol handling."""
    
    def test_tools_list_request(self):
        """Test handling of tools/list request."""
        request = {"method": "tools/list"}
        response = file_generation.handle_request(request)
        
        assert "tools" in response
        assert len(response["tools"]) == 1
        
        tool = response["tools"][0]
        assert tool["name"] == "generate_file"
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["required"] == ["code"]
    
    def test_tools_call_success(self):
        """Test successful tool call."""
        code = """
import json
with open("test.json", "w") as f:
    json.dump({"success": True}, f)
"""
        
        request = {
            "method": "tools/call",
            "params": {
                "name": "generate_file",
                "arguments": {
                    "code": code
                }
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                response = file_generation.handle_request(request)
                
                assert "error" not in response
                assert "content" in response
                assert len(response["content"]) == 2
                assert response["content"][0]["type"] == "text"
                assert response["content"][1]["type"] == "resource"
    
    def test_tools_call_error(self):
        """Test tool call with error."""
        request = {
            "method": "tools/call",
            "params": {
                "name": "generate_file",
                "arguments": {
                    "code": "import os"  # Disallowed import
                }
            }
        }
        
        response = file_generation.handle_request(request)
        
        assert "error" in response
        assert response["error"]["code"] == -32603
        assert "Import not allowed" in response["error"]["message"]
    
    def test_unknown_method(self):
        """Test handling of unknown method."""
        request = {"method": "unknown/method"}
        response = file_generation.handle_request(request)
        
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Unknown method" in response["error"]["message"]
    
    def test_unknown_tool(self):
        """Test handling of unknown tool."""
        request = {
            "method": "tools/call",
            "params": {
                "name": "unknown_tool",
                "arguments": {}
            }
        }
        
        response = file_generation.handle_request(request)
        
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Unknown tool" in response["error"]["message"]


class TestDirectoryManagement:
    """Test output directory management."""
    
    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "outputs"
            assert not output_path.exists()
            
            with patch('pathlib.Path.cwd', return_value=Path(tmpdir)):
                output_dir = file_generation.get_output_directory()
                assert output_dir == output_path
                assert output_path.exists()
    
    def test_cleanup_old_files(self):
        """Test cleanup of old files when directory is too large."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            
            # Create some test files
            for i in range(5):
                file_path = output_dir / f"test_{i}.txt"
                file_path.write_text("x" * 1024 * 1024)  # 1MB each
                # Set modification times in the past
                os.utime(file_path, (1000000 + i, 1000000 + i))
            
            # Set max size to 3MB (should keep only 2 newest files)
            file_generation.cleanup_old_files(output_dir, max_size_mb=3)
            
            # Check that old files were removed
            remaining_files = list(output_dir.glob("*.txt"))
            assert len(remaining_files) <= 3  # Should have removed some files


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_code(self):
        """Test handling of empty code."""
        result = file_generation.generate_file("")
        assert "error" not in result or "No file was generated" in result["error"]
    
    def test_code_with_only_comments(self):
        """Test code with only comments."""
        code = """
# This is a comment
# Another comment
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                result = file_generation.generate_file(code)
                assert "No file was generated" in result["error"]
    
    def test_filename_hint(self):
        """Test using filename hint parameter."""
        code = """
import json
with open("output.json", "w") as f:
    json.dump({"test": "data"}, f)
"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(file_generation, 'get_output_directory', return_value=Path(tmpdir)):
                # Note: Current implementation doesn't use filename hint
                # This test documents current behavior
                result = file_generation.generate_file(code, filename="suggested.json")
                
                assert "error" not in result
                assert result["filename"] == "output.json"  # Uses actual created filename


if __name__ == "__main__":
    pytest.main([__file__, "-v"])