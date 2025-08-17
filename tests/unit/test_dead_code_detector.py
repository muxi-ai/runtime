#!/usr/bin/env python3
"""Unit tests for Dead Code Detector"""

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'dead-code'))

from dead_code_detector import (
    DeadCodeDetector, ClassInfo, MethodInfo, UsageRef, ClassUsageReport
)


class TestDeadCodeDetector(unittest.TestCase):
    """Test cases for DeadCodeDetector"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir) / "src" / "muxi"
        self.test_path.mkdir(parents=True)
        self.detector = DeadCodeDetector(str(self.test_path))
        
    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_class_info_creation(self):
        """Test ClassInfo dataclass creation"""
        method = MethodInfo(name="test_method", line=10, is_dunder=False)
        class_info = ClassInfo(
            class_name="TestClass",
            module="test.module",
            file="test.py",
            line=5,
            methods=[method]
        )
        
        self.assertEqual(class_info.class_name, "TestClass")
        self.assertEqual(class_info.module, "test.module")
        self.assertEqual(len(class_info.methods), 1)
        self.assertEqual(class_info.methods[0].name, "test_method")
    
    def test_extract_classes_from_simple_file(self):
        """Test extracting classes from a simple Python file"""
        # Create a test Python file
        test_file = self.test_path / "test_module.py"
        test_file.write_text("""
class SimpleClass:
    def __init__(self):
        pass
    
    def method1(self):
        return "hello"
    
    @property
    def prop1(self):
        return self._value

class InheritedClass(SimpleClass):
    def method2(self):
        pass
""")
        
        # Extract classes
        classes = self.detector.extract_classes()
        
        # Verify extraction
        self.assertEqual(len(classes), 2)
        
        # Check SimpleClass
        simple_key = "src.muxi.test_module.SimpleClass"
        self.assertIn(simple_key, classes)
        simple_class = classes[simple_key]
        self.assertEqual(simple_class.class_name, "SimpleClass")
        self.assertEqual(len(simple_class.methods), 3)  # __init__, method1, prop1
        
        # Check InheritedClass
        inherited_key = "src.muxi.test_module.InheritedClass"
        self.assertIn(inherited_key, classes)
        inherited_class = classes[inherited_key]
        self.assertEqual(inherited_class.class_name, "InheritedClass")
        self.assertEqual(inherited_class.inherits, ["SimpleClass"])
    
    def test_method_info_dunder_detection(self):
        """Test detection of dunder methods"""
        dunder_method = MethodInfo(name="__str__", line=10)
        self.assertTrue(dunder_method.is_dunder)
        
        private_method = MethodInfo(name="_private", line=20)
        self.assertTrue(private_method.is_private)
        self.assertFalse(private_method.is_dunder)
        
        normal_method = MethodInfo(name="normal", line=30)
        self.assertFalse(normal_method.is_dunder)
        self.assertFalse(normal_method.is_private)
    
    @patch('subprocess.run')
    def test_search_pattern(self, mock_run):
        """Test pattern searching with ripgrep"""
        # Mock ripgrep output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="test.py:10:    obj = TestClass()\nother.py:20:    x = TestClass()"
        )
        
        refs = self.detector._search_pattern(
            "TestClass\\(",
            "original.py",
            "instantiation"
        )
        
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].file, "test.py")
        self.assertEqual(refs[0].line, 10)
        self.assertEqual(refs[0].pattern_type, "instantiation")
    
    def test_calculate_confidence_dead_class(self):
        """Test confidence calculation for dead class"""
        class_info = ClassInfo(
            class_name="DeadClass",
            module="test",
            file="test.py",
            line=1
        )
        
        # No usage refs
        confidence, status = self.detector.calculate_confidence([], class_info)
        
        self.assertEqual(confidence, 100.0)
        self.assertEqual(status, "DEAD")
    
    def test_calculate_confidence_used_class(self):
        """Test confidence calculation for used class"""
        class_info = ClassInfo(
            class_name="UsedClass",
            module="test",
            file="test.py",
            line=1
        )
        
        # Has instantiation usage
        usage_refs = [
            UsageRef("other.py", 10, "UsedClass()", "instantiation")
        ]
        
        confidence, status = self.detector.calculate_confidence(usage_refs, class_info)
        
        self.assertEqual(confidence, 0.0)
        self.assertEqual(status, "USED")
    
    def test_calculate_confidence_type_hints_only(self):
        """Test confidence calculation for class used only in type hints"""
        class_info = ClassInfo(
            class_name="TypeHintClass",
            module="test",
            file="test.py",
            line=1
        )
        
        # Only type hint usage
        usage_refs = [
            UsageRef("other.py", 10, "def func() -> TypeHintClass:", "type_hints")
        ]
        
        confidence, status = self.detector.calculate_confidence(usage_refs, class_info)
        
        self.assertEqual(confidence, 70.0)
        self.assertEqual(status, "POSSIBLY_DEAD")
    
    def test_determine_risk_level(self):
        """Test risk level determination"""
        # Core class - CRITICAL
        core_class = ClassInfo(
            class_name="CoreClass",
            module="core",
            file="src/muxi/core/base.py",
            line=1
        )
        self.assertEqual(self.detector.determine_risk_level(core_class), "CRITICAL")
        
        # Service class - HIGH
        service_class = ClassInfo(
            class_name="ServiceClass",
            module="services",
            file="src/muxi/services/api.py",
            line=1
        )
        self.assertEqual(self.detector.determine_risk_level(service_class), "HIGH")
        
        # Utils class - LOW
        utils_class = ClassInfo(
            class_name="UtilClass",
            module="utils",
            file="src/muxi/utils/helper.py",
            line=1
        )
        self.assertEqual(self.detector.determine_risk_level(utils_class), "LOW")
        
        # Other class - MEDIUM
        other_class = ClassInfo(
            class_name="OtherClass",
            module="other",
            file="src/muxi/other/module.py",
            line=1
        )
        self.assertEqual(self.detector.determine_risk_level(other_class), "MEDIUM")
    
    def test_analyze_methods_dead_class(self):
        """Test method analysis for dead class"""
        class_info = ClassInfo(
            class_name="DeadClass",
            module="test",
            file="test.py",
            line=1,
            methods=[
                MethodInfo("__init__", 5),
                MethodInfo("method1", 10),
                MethodInfo("method2", 15)
            ]
        )
        
        method_status = self.detector.analyze_methods(class_info, is_used=False)
        
        # All methods should be dead
        self.assertEqual(method_status["__init__"], "DEAD")
        self.assertEqual(method_status["method1"], "DEAD")
        self.assertEqual(method_status["method2"], "DEAD")
    
    @patch.object(DeadCodeDetector, '_search_method_usage')
    def test_analyze_methods_used_class(self, mock_search):
        """Test method analysis for used class"""
        class_info = ClassInfo(
            class_name="UsedClass",
            module="test",
            file="test.py",
            line=1,
            methods=[
                MethodInfo("__init__", 5),
                MethodInfo("used_method", 10),
                MethodInfo("unused_method", 15)
            ]
        )
        
        # Mock method usage search
        def mock_search_side_effect(method_name, class_info):
            if method_name == "used_method":
                return [UsageRef("other.py", 20, "obj.used_method()", "method_call")]
            return []
        
        mock_search.side_effect = mock_search_side_effect
        
        method_status = self.detector.analyze_methods(class_info, is_used=True)
        
        self.assertEqual(method_status["__init__"], "USED")
        self.assertEqual(method_status["used_method"], "USED")
        self.assertEqual(method_status["unused_method"], "DEAD")
    
    def test_check_dunder_method(self):
        """Test special handling of dunder methods"""
        # Implicit dunder with no refs
        status = self.detector._check_dunder_method("__str__", [])
        self.assertEqual(status, "POSSIBLY_DEAD")
        
        # Dunder with refs
        refs = [UsageRef("test.py", 10, "str(obj)", "method_call")]
        status = self.detector._check_dunder_method("__str__", refs)
        self.assertEqual(status, "USED")
        
        # Non-implicit dunder with no refs
        status = self.detector._check_dunder_method("__custom__", [])
        self.assertEqual(status, "DEAD")
    
    def test_generate_metadata(self):
        """Test metadata generation"""
        # Add some test classes
        self.detector.classes = {
            "test.Class1": ClassInfo(
                "Class1", "test", "test1.py", 1,
                methods=[MethodInfo("method1", 5)]
            ),
            "test.Class2": ClassInfo(
                "Class2", "test", "test2.py", 1,
                methods=[MethodInfo("method1", 5), MethodInfo("method2", 10)]
            )
        }
        
        self.detector.generate_metadata()
        
        metadata_file = self.detector.output_dir / "metadata.json"
        self.assertTrue(metadata_file.exists())
        
        with open(metadata_file) as f:
            metadata = json.load(f)
        
        self.assertEqual(metadata["total_classes"], 2)
        self.assertEqual(metadata["total_methods"], 3)
        self.assertEqual(metadata["scanner_version"], "1.0.0")
        self.assertIn("scan_date", metadata)
    
    def test_class_usage_report_creation(self):
        """Test ClassUsageReport dataclass"""
        class_info = ClassInfo("TestClass", "test", "test.py", 1)
        report = ClassUsageReport(
            class_info=class_info,
            status="DEAD",
            confidence=100.0,
            risk_level="LOW"
        )
        
        self.assertEqual(report.status, "DEAD")
        self.assertEqual(report.confidence, 100.0)
        self.assertEqual(report.risk_level, "LOW")
        self.assertEqual(len(report.usage_refs), 0)
    
    def test_generate_class_report(self):
        """Test individual class report generation"""
        class_info = ClassInfo(
            class_name="TestClass",
            module="test.module",
            file="test.py",
            line=10,
            methods=[
                MethodInfo("__init__", 15),
                MethodInfo("method1", 20)
            ]
        )
        
        report = ClassUsageReport(
            class_info=class_info,
            status="DEAD",
            confidence=95.0,
            risk_level="LOW",
            method_status={
                "__init__": "DEAD",
                "method1": "DEAD"
            }
        )
        
        self.detector.generate_class_report("test.module.TestClass", report)
        
        report_file = self.detector.output_dir / "classes" / "TestClass.md"
        self.assertTrue(report_file.exists())
        
        content = report_file.read_text()
        self.assertIn("# TestClass", content)
        self.assertIn("Status: DEAD", content)
        self.assertIn("Confidence: 95.0%", content)
        self.assertIn("Risk Level: LOW", content)
    
    def test_generate_summary_report(self):
        """Test summary report generation"""
        # Create test usage reports
        class1 = ClassInfo("DeadClass", "test", "test1.py", 1)
        class2 = ClassInfo("UsedClass", "test", "test2.py", 1)
        
        self.detector.usage_reports = {
            "test.DeadClass": ClassUsageReport(
                class_info=class1,
                status="DEAD",
                confidence=100.0,
                risk_level="LOW",
                method_status={"method1": "DEAD"}
            ),
            "test.UsedClass": ClassUsageReport(
                class_info=class2,
                status="USED",
                confidence=0.0,
                risk_level="MEDIUM",
                method_status={"method1": "USED", "method2": "DEAD"}
            )
        }
        
        self.detector.generate_summary_report()
        
        summary_file = self.detector.output_dir / "reports" / "summary.md"
        self.assertTrue(summary_file.exists())
        
        content = summary_file.read_text()
        self.assertIn("# Dead Code Analysis Summary", content)
        self.assertIn("Total classes analyzed: 2", content)
        self.assertIn("Definitely dead: 1", content)


class TestParallelDeadCodeDetector(unittest.TestCase):
    """Test cases for ParallelDeadCodeDetector"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_path = Path(self.temp_dir) / "src" / "muxi"
        self.test_path.mkdir(parents=True)
        
        # Import here to avoid import errors
        from parallel_dead_code_detector import ParallelDeadCodeDetector
        self.detector = ParallelDeadCodeDetector(str(self.test_path), max_workers=2)
    
    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_get_directory_segments(self):
        """Test directory segmentation for parallel processing"""
        # Create test directories
        (self.test_path / "formation").mkdir()
        (self.test_path / "services").mkdir()
        (self.test_path / "utils").mkdir()
        (self.test_path / "other").mkdir()
        
        segments = self.detector.get_directory_segments()
        
        # Should have at least the created directories
        self.assertGreaterEqual(len(segments), 4)
        
        # Check that primary directories are included
        segment_names = [s.name for s in segments]
        self.assertIn("formation", segment_names)
        self.assertIn("services", segment_names)
        self.assertIn("utils", segment_names)
    
    def test_create_batches(self):
        """Test batch creation for parallel processing"""
        items = list(range(100))
        batches = self.detector.create_batches(items, batch_size=15)
        
        # Should have 7 batches (6 of 15, 1 of 10)
        self.assertEqual(len(batches), 7)
        
        # First 6 batches should have 15 items
        for i in range(6):
            self.assertEqual(len(batches[i]), 15)
        
        # Last batch should have 10 items
        self.assertEqual(len(batches[6]), 10)
    
    def test_progress_monitor(self):
        """Test progress monitoring"""
        from parallel_dead_code_detector import ProgressMonitor
        
        monitor = ProgressMonitor()
        
        # Initial progress should be 0
        for phase in monitor.phase_progress:
            self.assertEqual(monitor.phase_progress[phase], 0.0)
        
        # Update progress
        monitor.update_progress('discovery', 50.0)
        self.assertEqual(monitor.phase_progress['discovery'], 50.0)
        
        # Progress shouldn't exceed 100
        monitor.update_progress('discovery', 60.0)
        self.assertEqual(monitor.phase_progress['discovery'], 100.0)


if __name__ == "__main__":
    unittest.main()