"""
Tests for Protobuf Code Generation System
"""

import pytest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.muxi.runtime.services.observability.build_protobuf import (
    ProtobufCodeGenerator,
    generate_protobuf_code
)


class TestProtobufCodeGenerator:
    """Test the ProtobufCodeGenerator class"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            schema_dir = temp_path / "schemas"
            output_dir = temp_path / "output"
            schema_dir.mkdir()
            output_dir.mkdir()

            # Create a minimal test proto file
            test_proto = schema_dir / "test.proto"
            test_proto.write_text('''
syntax = "proto3";

package test.v1;

message TestMessage {
  string id = 1;
  int64 timestamp = 2;
}
''')

            yield {
                "schema_dir": schema_dir,
                "output_dir": output_dir,
                "test_proto": test_proto
            }

    def test_generator_initialization(self, temp_dirs):
        """Test generator initializes correctly with custom paths"""
        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        assert generator.schema_dir == temp_dirs["schema_dir"]
        assert generator.output_dir == temp_dirs["output_dir"]

    def test_generator_initialization_defaults(self):
        """Test generator uses default paths when none provided"""
        # Use the real schema directory that exists
        generator = ProtobufCodeGenerator()

        assert generator.schema_dir.name == "protobuf"
        assert generator.output_dir.name == "proto"

    def test_generator_initialization_invalid_schema_dir(self):
        """Test generator raises error for nonexistent schema directory"""
        with pytest.raises(FileNotFoundError, match="Schema directory does not exist"):
            ProtobufCodeGenerator(schema_dir="/nonexistent/path")

    def test_find_proto_files(self, temp_dirs):
        """Test finding proto files in schema directory"""
        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        proto_files = generator._find_proto_files()
        assert len(proto_files) == 1
        assert proto_files[0].name == "test.proto"

    def test_find_proto_files_empty_directory(self, temp_dirs):
        """Test finding proto files in empty directory"""
        # Remove the test proto file
        temp_dirs["test_proto"].unlink()

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        proto_files = generator._find_proto_files()
        assert len(proto_files) == 0

    def test_prepare_output_directory(self, temp_dirs):
        """Test output directory preparation"""
        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        # Remove output directory to test creation
        generator.output_dir.rmdir()

        generator._prepare_output_directory()

        assert generator.output_dir.exists()
        assert (generator.output_dir / "__init__.py").exists()

        # Check __init__.py content
        init_content = (generator.output_dir / "__init__.py").read_text()
        assert "Generated protobuf modules" in init_content

    @patch('subprocess.run')
    def test_ensure_protoc_available_success(self, mock_run, temp_dirs):
        """Test protoc availability check when available"""
        mock_run.return_value = MagicMock(returncode=0)

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        assert generator._ensure_protoc_available() is True
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_ensure_protoc_available_failure(self, mock_run, temp_dirs):
        """Test protoc availability check when not available"""
        mock_run.return_value = MagicMock(returncode=1)

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        assert generator._ensure_protoc_available() is False

    @patch('subprocess.run')
    def test_ensure_protoc_available_timeout(self, mock_run, temp_dirs):
        """Test protoc availability check with timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired("protoc", 10)

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        assert generator._ensure_protoc_available() is False

    @patch('subprocess.run')
    def test_compile_single_proto_success(self, mock_run, temp_dirs):
        """Test successful compilation of a single proto file"""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator._compile_single_proto(temp_dirs["test_proto"])
        assert result is True
        mock_run.assert_called_once()

        # Check command structure
        call_args = mock_run.call_args[0][0]  # First positional arg is the command list
        assert "grpc_tools.protoc" in " ".join(call_args)
        assert str(temp_dirs["test_proto"]) in call_args

    @patch('subprocess.run')
    def test_compile_single_proto_failure(self, mock_run, temp_dirs):
        """Test failed compilation of a single proto file"""
        mock_run.return_value = MagicMock(returncode=1, stderr="Compilation error")

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator._compile_single_proto(temp_dirs["test_proto"])
        assert result is False

    @patch('subprocess.run')
    def test_compile_single_proto_timeout(self, mock_run, temp_dirs):
        """Test compilation timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired("protoc", 30)

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator._compile_single_proto(temp_dirs["test_proto"])
        assert result is False

    @patch.object(ProtobufCodeGenerator, '_ensure_protoc_available')
    @patch.object(ProtobufCodeGenerator, '_compile_single_proto')
    def test_generate_python_code_success(self, mock_compile, mock_ensure, temp_dirs):
        """Test successful generation of Python code"""
        mock_ensure.return_value = True
        mock_compile.return_value = True

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator.generate_python_code()
        assert result is True
        mock_ensure.assert_called_once()
        mock_compile.assert_called_once()

    @patch.object(ProtobufCodeGenerator, '_ensure_protoc_available')
    def test_generate_python_code_protoc_unavailable(self, mock_ensure, temp_dirs):
        """Test generation when protoc is unavailable"""
        mock_ensure.return_value = False

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator.generate_python_code()
        assert result is False

    def test_generate_python_code_no_proto_files(self, temp_dirs):
        """Test generation when no proto files exist"""
        # Remove the test proto file
        temp_dirs["test_proto"].unlink()

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator.generate_python_code()
        assert result is False

    @patch.object(ProtobufCodeGenerator, '_ensure_protoc_available')
    @patch.object(ProtobufCodeGenerator, '_compile_single_proto')
    def test_generate_python_code_specific_files(self, mock_compile, mock_ensure, temp_dirs):
        """Test generation with specific proto files"""
        mock_ensure.return_value = True
        mock_compile.return_value = True

        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        result = generator.generate_python_code(proto_files=["test.proto"])
        assert result is True
        mock_compile.assert_called_once()

    def test_get_generated_modules_empty(self, temp_dirs):
        """Test getting generated modules when none exist"""
        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        modules = generator.get_generated_modules()
        assert modules == []

    def test_get_generated_modules_with_files(self, temp_dirs):
        """Test getting generated modules when files exist"""
        generator = ProtobufCodeGenerator(
            schema_dir=str(temp_dirs["schema_dir"]),
            output_dir=str(temp_dirs["output_dir"])
        )

        # Create mock generated files
        (generator.output_dir / "test_pb2.py").touch()
        (generator.output_dir / "example_pb2.py").touch()

        modules = generator.get_generated_modules()
        assert "test_pb2" in modules
        assert "example_pb2" in modules
        assert len(modules) == 2


class TestGenerateProtobufCodeFunction:
    """Test the standalone generate_protobuf_code function"""

    def test_generate_protobuf_code_success(self):
        """Test successful code generation using real schema"""
        # Use the actual schema directory
        result = generate_protobuf_code()
        assert result is True

    @patch.object(ProtobufCodeGenerator, '__init__')
    def test_generate_protobuf_code_initialization_error(self, mock_init):
        """Test handling of initialization errors"""
        mock_init.side_effect = FileNotFoundError("Schema directory not found")

        result = generate_protobuf_code(schema_dir="/nonexistent")
        assert result is False

    @patch.object(ProtobufCodeGenerator, 'generate_python_code')
    def test_generate_protobuf_code_generation_error(self, mock_generate):
        """Test handling of generation errors"""
        mock_generate.side_effect = Exception("Generation failed")

        result = generate_protobuf_code()
        assert result is False


class TestIntegrationWithRealSchema:
    """Integration tests using the real observability schema"""

    def test_real_schema_generation(self):
        """Test that the real observability schema can be compiled"""
        generator = ProtobufCodeGenerator()

        # Should find the observability.proto file
        proto_files = generator._find_proto_files()
        assert len(proto_files) > 0
        assert any(f.name == "observability.proto" for f in proto_files)

        # Should be able to generate code
        result = generator.generate_python_code()
        assert result is True

        # Should create the expected files
        generated_files = list(generator.output_dir.glob("*_pb2.py"))
        assert len(generated_files) > 0
        assert generator.output_dir.joinpath("observability_pb2.py").exists()

    def test_generated_modules_accessible(self):
        """Test that generated modules can be imported"""
        generator = ProtobufCodeGenerator()
        generator.generate_python_code()

        # Try to import the generated module
        try:
            from src.muxi.runtime.services.observability.proto import observability_pb2

            # Check that expected classes exist
            assert hasattr(observability_pb2, 'ObservabilityEvent')
            assert hasattr(observability_pb2, 'EventLevel')
            assert hasattr(observability_pb2, 'EventType')

        except ImportError:
            pytest.fail("Generated protobuf module could not be imported")
