"""
Build system integration for generating Python protobuf code from schema files.
Implements automated protobuf code generation for observability events.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .protobuf_schema import find_project_root, ValidationError


class ProtobufCodeGenerator:
    """
    Generates Python protobuf code from .proto schema files.

    Handles the compilation process and ensures proper output directory structure.
    """

    def __init__(self, schema_dir: Optional[str] = None, output_dir: Optional[str] = None):
        self.schema_dir = Path(schema_dir) if schema_dir else self._get_default_schema_dir()
        self.output_dir = Path(output_dir) if output_dir else self._get_default_output_dir()

        # Validate paths
        if not self.schema_dir.exists():
            raise FileNotFoundError(f"Schema directory does not exist: {self.schema_dir}")

    def _get_default_schema_dir(self) -> Path:
        """
        Get default path to protobuf schemas using robust project root detection.

        Returns:
            Path to the schemas/protobuf directory
        """
        try:
            project_root = find_project_root()
            return project_root / "schemas" / "protobuf"
        except ValidationError as e:
            # Provide a more specific error message for build system
            raise FileNotFoundError(
                f"Cannot locate protobuf schemas for build: {e}. "
                f"Ensure you're running from the project directory or set MUXI_PROJECT_ROOT."
            )

    def _get_default_output_dir(self) -> Path:
        """Get default output directory for generated code"""
        return Path(__file__).parent / "proto"

    def _ensure_protoc_available(self) -> bool:
        """Check if protoc compiler is available"""
        try:
            result = subprocess.run(["python", "-m", "grpc_tools.protoc", "--version"],
                                    capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _find_proto_files(self) -> List[Path]:
        """Find all .proto files in the schema directory"""
        return list(self.schema_dir.glob("*.proto"))

    def _prepare_output_directory(self):
        """Ensure output directory exists and is ready"""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create __init__.py file for Python package
        init_file = self.output_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Generated protobuf modules for MUXI observability events"""\n')

    def get_generated_modules(self) -> List[str]:
        """Get list of generated Python module names"""
        modules = []
        for pb2_file in self.output_dir.glob("*_pb2.py"):
            module_name = pb2_file.stem
            modules.append(module_name)
        return modules

    def generate_python_code(self, proto_files: Optional[List[str]] = None) -> bool:
        """Generate Python protobuf code from schema files."""
        # Ensure protoc is available
        if not self._ensure_protoc_available():
            print("grpc_tools.protoc not available")
            return False

        # Find proto files to compile
        if proto_files:
            files_to_compile = [self.schema_dir / f for f in proto_files]
        else:
            files_to_compile = self._find_proto_files()

        if not files_to_compile:
            print(f"No .proto files found in {self.schema_dir}")
            return False

        # Prepare output directory
        self._prepare_output_directory()

        # Compile each proto file
        success = True
        for proto_file in files_to_compile:
            if not self._compile_single_proto(proto_file):
                success = False

        if success:
            print(f"Successfully generated protobuf code in {self.output_dir}")

        return success

    def _compile_single_proto(self, proto_file: Path) -> bool:
        """Compile a single .proto file to Python code"""
        try:
            cmd = [
                "python", "-m", "grpc_tools.protoc",
                f"--proto_path={self.schema_dir}",
                f"--python_out={self.output_dir}",
                f"--grpc_python_out={self.output_dir}",
                str(proto_file)
            ]

            print(f"Compiling {proto_file.name}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                print(f"Failed to compile {proto_file.name}:")
                print(f"Error: {result.stderr}")
                return False

            return True

        except Exception as e:
            print(f"Exception compiling {proto_file.name}: {e}")
            return False


def generate_protobuf_code(schema_dir: Optional[str] = None, output_dir: Optional[str] = None) -> bool:
    """Main function to generate protobuf code."""
    try:
        generator = ProtobufCodeGenerator(schema_dir, output_dir)
        return generator.generate_python_code()
    except Exception as e:
        print(f"Error generating protobuf code: {e}")
        return False


if __name__ == "__main__":
    success = generate_protobuf_code()
    sys.exit(0 if success else 1)
