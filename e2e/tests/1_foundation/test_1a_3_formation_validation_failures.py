#!/usr/bin/env python3
"""Test 1a3: Formation Validation Failures using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402
from muxi.formation import Formation  # noqa: E402


class TestFormationValidationFailures(BaseE2ETest):
    """Test formation validation and error handling."""

    def __init__(self):
        super().__init__(
            test_name="test_1a3_formation_validation_failures",
            test_description="Test formation validation failures",
            test_area="1_foundation",
        )

    async def test_1a3_formation_validation_failures(self):
        """Test various formation validation failure scenarios."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False
        tests_passed = []
        tests_failed = []

        # Print header
        formatter.print_test_header(
            test_name="test_1a3_formation_validation_failures",
            description="Test formation validation failures",
        )

        try:
            # Test 1: Non-existent path
            print("\n1. Testing non-existent path...")
            formation = Formation()
            try:
                asyncio.run(formation.load("/nonexistent/path/formation.afs"))
                tests_failed.append("Non-existent path should fail")
            except Exception as e:
                print(f"   ✅ Correctly failed with: {type(e).__name__}")
                tests_passed.append("Non-existent path validation")

            # Test 2: Invalid YAML syntax
            print("\n2. Testing invalid YAML syntax...")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write("invalid: yaml: syntax: {{")
                invalid_yaml_path = f.name

            formation = Formation()
            try:
                asyncio.run(formation.load(invalid_yaml_path))
                tests_failed.append("Invalid YAML should fail")
            except Exception as e:
                print(f"   ✅ Correctly failed with: {type(e).__name__}")
                tests_passed.append("Invalid YAML validation")
            finally:
                Path(invalid_yaml_path).unlink()

            # Test 3: Missing required fields
            print("\n3. Testing missing required fields...")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                # Minimal YAML without required fields
                f.write("id: test\ndescription: test")
                missing_fields_path = f.name

            formation = Formation()
            try:
                asyncio.run(formation.load(missing_fields_path))
                tests_failed.append("Missing required fields should fail")
            except Exception as e:
                print(f"   ✅ Correctly failed with: {type(e).__name__}")
                tests_passed.append("Missing fields validation")
            finally:
                Path(missing_fields_path).unlink()

            # Test 4: Empty YAML file
            print("\n4. Testing empty YAML file...")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write("")
                empty_yaml_path = f.name

            formation = Formation()
            try:
                asyncio.run(formation.load(empty_yaml_path))
                tests_failed.append("Empty YAML should fail")
            except Exception as e:
                print(f"   ✅ Correctly failed with: {type(e).__name__}")
                tests_passed.append("Empty YAML validation")
            finally:
                Path(empty_yaml_path).unlink()

            # Test 5: Not a YAML file
            print("\n5. Testing non-YAML file...")
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write("This is not a YAML file")
                not_yaml_path = f.name

            formation = Formation()
            try:
                asyncio.run(formation.load(not_yaml_path))
                tests_failed.append("Non-YAML file should fail")
            except Exception as e:
                print(f"   ✅ Correctly failed with: {type(e).__name__}")
                tests_passed.append("Non-YAML file validation")
            finally:
                Path(not_yaml_path).unlink()

            # Check if all tests passed
            if tests_failed:
                raise AssertionError(f"Some validations didn't fail as expected: {tests_failed}")

            print("\n✅ All validation tests passed correctly")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a3_formation_validation_failures",
                success=True,
                checks=tests_passed,
                transcript=[],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a3_formation_validation_failures",
                success=False,
                checks=[f"Failed: {str(e)}"] + tests_failed,
                transcript=[],
                duration=duration,
            )
            raise
        finally:
            return 0 if success else 1

    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_1a3_formation_validation_failures())


if __name__ == "__main__":
    test = TestFormationValidationFailures()
    sys.exit(test.run_test())
