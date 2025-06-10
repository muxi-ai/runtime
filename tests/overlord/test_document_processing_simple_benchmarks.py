"""
Simplified Document Processing Performance Benchmarks

This module provides basic performance testing without complex monitoring
that can cause hanging issues.
"""

import asyncio
import time
import psutil
import os
import pytest
from typing import Dict, List, Any
import sys

# Add runtime path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'runtime'))

# Only mock spacy since NLTK is available
sys.modules['spacy'] = type('MockSpacy', (), {
    'load': lambda self, model: type('MockModel', (), {
        'process': lambda text: type('Doc', (), {'text': text})()
    }),
    '__version__': '3.7.0'
})()

from muxi.runtime.overlord.document_storage import DocumentChunkManager


class SimpleDocumentBenchmark:
    """Simplified performance benchmarking for document processing"""

    def __init__(self):
        self.results = []

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024

    def create_test_content(self, size_mb: float) -> str:
        """Create test content of specified size"""
        # Create content that's approximately the specified size
        base_text = ("This is a test document with meaningful content "
                    "for performance testing. ") * 20
        target_size = int(size_mb * 1024 * 1024)
        content = ""
        while len(content) < target_size:
            content += base_text + "\n"
        return content[:target_size]

    async def simple_chunking_benchmark(self, file_sizes: List[float] = None) -> Dict[str, Any]:
        """Simple chunking benchmark without complex monitoring"""
        if file_sizes is None:
            file_sizes = [0.1, 0.5, 1.0]  # MB

        print(f"\n🔬 Simple Chunking Benchmark - Files: {file_sizes} MB")

        chunk_manager = DocumentChunkManager()
        results = []

        for size_mb in file_sizes:
            print(f"  📄 Processing {size_mb}MB file...")

            # Create test content
            content = self.create_test_content(size_mb)

            # Simple timing
            start_memory = self.get_memory_usage()
            start_time = time.time()

            try:
                # Perform chunking
                chunks = await chunk_manager.chunk_document(
                    content=content,
                    filename=f"test_{size_mb}mb.txt",
                    strategy="fixed"
                )

                end_time = time.time()
                end_memory = self.get_memory_usage()

                processing_time_ms = (end_time - start_time) * 1000
                memory_used_mb = end_memory - start_memory
                throughput_mbps = size_mb / (processing_time_ms / 1000) if processing_time_ms > 0 else 0

                result = {
                    "file_size_mb": size_mb,
                    "processing_time_ms": processing_time_ms,
                    "memory_used_mb": memory_used_mb,
                    "throughput_mbps": throughput_mbps,
                    "chunk_count": len(chunks),
                    "success": True
                }

                print(f"    ✅ {processing_time_ms:.1f}ms, {memory_used_mb:.1f}MB, "
                      f"{throughput_mbps:.2f}MB/s, {len(chunks)} chunks")

            except Exception as e:
                print(f"    ❌ Failed: {e}")
                result = {
                    "file_size_mb": size_mb,
                    "processing_time_ms": 0,
                    "memory_used_mb": 0,
                    "throughput_mbps": 0,
                    "chunk_count": 0,
                    "success": False,
                    "error": str(e)
                }

            results.append(result)
            self.results.append(result)

        return {
            "operation": "simple_chunking",
            "file_sizes_mb": file_sizes,
            "results": results,
            "avg_throughput_mbps": sum(r["throughput_mbps"] for r in results if r["success"]) / max(1, len([r for r in results if r["success"]])),
            "total_success": len([r for r in results if r["success"]]),
            "total_tests": len(results)
        }

    async def simple_scalability_test(self, concurrent_levels: List[int] = None) -> Dict[str, Any]:
        """Simple concurrent processing test"""
        if concurrent_levels is None:
            concurrent_levels = [1, 2, 3]

        print(f"\n⚡ Simple Scalability Test - Concurrent levels: {concurrent_levels}")

        chunk_manager = DocumentChunkManager()
        test_content = self.create_test_content(0.1)  # 0.1MB test content
        results = []

        for concurrent_ops in concurrent_levels:
            print(f"  🔄 Testing {concurrent_ops} concurrent operations...")

            async def single_operation():
                return await chunk_manager.chunk_document(
                    content=test_content,
                    filename="concurrent_test.txt",
                    strategy="fixed"
                )

            start_time = time.time()
            start_memory = self.get_memory_usage()

            try:
                # Run concurrent operations
                tasks = [single_operation() for _ in range(concurrent_ops)]
                results_list = await asyncio.gather(*tasks, return_exceptions=True)

                end_time = time.time()
                end_memory = self.get_memory_usage()

                # Count successes
                successful = sum(1 for r in results_list if not isinstance(r, Exception))
                failed = len(results_list) - successful

                processing_time_ms = (end_time - start_time) * 1000
                memory_used_mb = end_memory - start_memory
                success_rate = successful / len(results_list) if results_list else 0

                result = {
                    "concurrent_operations": concurrent_ops,
                    "processing_time_ms": processing_time_ms,
                    "memory_used_mb": memory_used_mb,
                    "success_rate": success_rate,
                    "successful_ops": successful,
                    "failed_ops": failed
                }

                print(f"    ✅ {processing_time_ms:.1f}ms, {memory_used_mb:.1f}MB, "
                      f"{success_rate:.1%} success rate")

            except Exception as e:
                print(f"    ❌ Failed: {e}")
                result = {
                    "concurrent_operations": concurrent_ops,
                    "processing_time_ms": 0,
                    "memory_used_mb": 0,
                    "success_rate": 0.0,
                    "successful_ops": 0,
                    "failed_ops": concurrent_ops,
                    "error": str(e)
                }

            results.append(result)

        return {
            "operation": "simple_scalability",
            "concurrent_levels": concurrent_levels,
            "results": results,
            "avg_success_rate": sum(r["success_rate"] for r in results) / len(results) if results else 0
        }

    def generate_simple_report(self) -> Dict[str, Any]:
        """Generate a simple performance report"""
        if not self.results:
            return {"error": "No performance data collected"}

        successful_results = [r for r in self.results if r["success"]]

        if not successful_results:
            return {"error": "No successful operations"}

        total_operations = len(self.results)
        successful_operations = len(successful_results)

        avg_time = sum(r["processing_time_ms"] for r in successful_results) / len(successful_results)
        avg_memory = sum(r["memory_used_mb"] for r in successful_results) / len(successful_results)
        avg_throughput = sum(r.get("throughput_mbps", 0) for r in successful_results) / len(successful_results)

        return {
            "summary": {
                "total_operations": total_operations,
                "successful_operations": successful_operations,
                "success_rate": successful_operations / total_operations,
                "avg_processing_time_ms": avg_time,
                "avg_memory_usage_mb": avg_memory,
                "avg_throughput_mbps": avg_throughput
            },
            "performance_assessment": {
                "speed": "GOOD" if avg_time < 1000 else "NEEDS_IMPROVEMENT",
                "memory": "GOOD" if avg_memory < 50 else "NEEDS_IMPROVEMENT",
                "throughput": "GOOD" if avg_throughput > 0.5 else "NEEDS_IMPROVEMENT"
            },
            "detailed_results": self.results
        }


class TestSimpleDocumentPerformance:
    """Simple test class for document processing performance"""

    @pytest.mark.asyncio
    async def test_simple_chunking_performance(self):
        """Test simple document chunking performance"""
        benchmark = SimpleDocumentBenchmark()
        result = await benchmark.simple_chunking_benchmark([0.1, 0.2])

        assert result["total_success"] > 0, "At least one test should succeed"
        assert result["avg_throughput_mbps"] > 0, "Should have positive throughput"

        print(f"\n✅ Simple chunking test completed:")
        print(f"   Success: {result['total_success']}/{result['total_tests']}")
        print(f"   Avg Throughput: {result['avg_throughput_mbps']:.2f} MB/s")

    @pytest.mark.asyncio
    async def test_simple_scalability(self):
        """Test simple scalability performance"""
        benchmark = SimpleDocumentBenchmark()
        result = await benchmark.simple_scalability_test([1, 2])

        assert result["avg_success_rate"] > 0.5, "Should have >50% success rate"

        print(f"\n✅ Simple scalability test completed:")
        print(f"   Avg Success Rate: {result['avg_success_rate']:.1%}")

    @pytest.mark.asyncio
    async def test_comprehensive_simple_benchmark(self):
        """Run comprehensive simple performance benchmark"""
        benchmark = SimpleDocumentBenchmark()

        print("\n🚀 Running Simple Performance Benchmark Suite...")

        # Run tests
        chunking_result = await benchmark.simple_chunking_benchmark([0.1, 0.5, 1.0])
        scalability_result = await benchmark.simple_scalability_test([1, 2, 3])

        # Generate report
        report = benchmark.generate_simple_report()

        # Assertions
        assert report["summary"]["success_rate"] > 0.5, "Should have >50% success rate"

        print("\n📊 SIMPLE PERFORMANCE REPORT:")
        print(f"  📈 Success Rate: {report['summary']['success_rate']:.1%}")
        print(f"  🧠 Avg Memory: {report['summary']['avg_memory_usage_mb']:.1f}MB")
        print(f"  ⏱️  Avg Time: {report['summary']['avg_processing_time_ms']:.1f}ms")
        print(f"  🚀 Avg Throughput: {report['summary']['avg_throughput_mbps']:.2f}MB/s")

        print("\n🎯 PERFORMANCE ASSESSMENT:")
        for metric, status in report["performance_assessment"].items():
            print(f"  {metric}: {status}")

        return report


if __name__ == "__main__":
    async def main():
        benchmark = SimpleDocumentBenchmark()

        print("🚀 Starting Simple Document Processing Benchmarks")
        print("=" * 50)

        # Run benchmarks
        chunking_result = await benchmark.simple_chunking_benchmark()
        scalability_result = await benchmark.simple_scalability_test()

        # Generate report
        report = benchmark.generate_simple_report()

        print("\n" + "=" * 50)
        print("📊 FINAL SIMPLE PERFORMANCE REPORT")
        print("=" * 50)
        print(f"Success Rate: {report['summary']['success_rate']:.1%}")
        print(f"Average Processing Time: {report['summary']['avg_processing_time_ms']:.1f}ms")
        print(f"Average Memory Usage: {report['summary']['avg_memory_usage_mb']:.1f}MB")
        print(f"Average Throughput: {report['summary']['avg_throughput_mbps']:.2f}MB/s")

    asyncio.run(main())
