"""
Document Processing Performance Benchmarks

This module provides comprehensive performance testing and benchmarking
for document processing capabilities, including memory usage, processing
speed metrics, and scalability limits.
"""

import asyncio
import time
import psutil
import os
import tempfile
import pytest
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import json
import sys

# Add runtime path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'runtime'))

# Mock only spacy since it may not be available in test environment
# NLTK is available, so we don't need to mock it
sys.modules['spacy'] = type('MockSpacy', (), {
    'load': lambda self, model: type('MockModel', (), {
        'process': lambda text: type('Doc', (), {'text': text})()
    }),
    '__version__': '3.7.0'
})()

from muxi.runtime.overlord.document_storage import (
    DocumentChunkManager,
    DocumentAwareBufferMemory,
    DocumentSemanticIndex
)
from muxi.runtime.overlord.document_experience import (
    DocumentSummarizer,
    DocumentAcknowledgmentGenerator
)
from muxi.runtime.overlord.document_workflow import (
    DocumentWorkflowIntegrator
)


@dataclass
class PerformanceMetrics:
    """Performance metrics for document processing operations"""
    operation: str
    file_size_mb: float
    processing_time_ms: float
    memory_usage_mb: float
    memory_peak_mb: float
    cpu_usage_percent: float
    success: bool
    throughput_mbps: float = 0.0
    items_per_second: float = 0.0


@dataclass
class ScalabilityResult:
    """Results from scalability testing"""
    concurrent_operations: int
    total_files: int
    avg_processing_time_ms: float
    avg_memory_usage_mb: float
    peak_memory_usage_mb: float
    success_rate: float
    errors: List[str]


class DocumentProcessingBenchmark:
    """Comprehensive performance benchmarking for document processing"""

    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.scalability_results: List[ScalabilityResult] = []
        self.baseline_memory = self._get_current_memory_usage()

    def _get_current_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024

    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=0.1)

    async def _monitor_resource_usage(self, operation_func, *args, **kwargs) -> Tuple[Any, PerformanceMetrics]:
        """Monitor resource usage during operation execution"""
        start_time = time.time()
        start_memory = self._get_current_memory_usage()
        peak_memory = start_memory

        # Create monitoring task
        monitoring = True
        memory_samples = []

        async def memory_monitor():
            nonlocal peak_memory, monitoring
            while monitoring:
                current_memory = self._get_current_memory_usage()
                memory_samples.append(current_memory)
                peak_memory = max(peak_memory, current_memory)
                await asyncio.sleep(0.1)

        # Start monitoring
        monitor_task = asyncio.create_task(memory_monitor())

        try:
            # Execute operation
            result = await operation_func(*args, **kwargs)
            success = True
        except Exception as e:
            result = None
            success = False
            print(f"Operation failed: {e}")
        finally:
            monitoring = False
            monitor_task.cancel()

        end_time = time.time()
        processing_time_ms = (end_time - start_time) * 1000
        memory_usage_mb = max(memory_samples) - self.baseline_memory if memory_samples else 0
        cpu_usage = self._get_cpu_usage()

        metrics = PerformanceMetrics(
            operation="unknown",
            file_size_mb=0.0,
            processing_time_ms=processing_time_ms,
            memory_usage_mb=memory_usage_mb,
            memory_peak_mb=peak_memory - self.baseline_memory,
            cpu_usage_percent=cpu_usage,
            success=success
        )

        return result, metrics

    def create_test_files(self, sizes_mb: List[float]) -> List[str]:
        """Create test files of various sizes"""
        test_files = []
        for size_mb in sizes_mb:
            # Create temporary file
            fd, filepath = tempfile.mkstemp(suffix='.txt')
            try:
                # Generate content
                content_size = int(size_mb * 1024 * 1024)
                content = "A" * min(content_size, 1000) + "\n" * (content_size // 1000)

                with os.fdopen(fd, 'w') as f:
                    f.write(content[:content_size])

                test_files.append(filepath)
            except Exception:
                os.close(fd)
                raise

        return test_files

    async def benchmark_chunk_manager(self, file_sizes: List[float] = None) -> Dict[str, Any]:
        """Benchmark document chunking performance"""
        if file_sizes is None:
            file_sizes = [0.1, 0.5, 1.0, 5.0, 10.0]  # MB

        print(f"🔬 Benchmarking DocumentChunkManager with files: {file_sizes} MB")

        chunk_manager = DocumentChunkManager()
        results = []

        test_files = self.create_test_files(file_sizes)

        try:
            for file_path, size_mb in zip(test_files, file_sizes):
                # Read file content
                with open(file_path, 'r') as f:
                    content = f.read()

                # Benchmark chunking operation
                async def chunk_operation():
                    return await chunk_manager.chunk_document(content, file_path)

                result, metrics = await self._monitor_resource_usage(chunk_operation)

                # Update metrics
                metrics.operation = "chunking"
                metrics.file_size_mb = size_mb
                if metrics.success and metrics.processing_time_ms > 0:
                    metrics.throughput_mbps = size_mb / (metrics.processing_time_ms / 1000)

                results.append(metrics)
                self.metrics.append(metrics)

                print(f"  📄 {size_mb}MB: {metrics.processing_time_ms:.1f}ms, "
                      f"{metrics.memory_usage_mb:.1f}MB memory, "
                      f"{metrics.throughput_mbps:.2f} MB/s")

        finally:
            # Cleanup test files
            for file_path in test_files:
                try:
                    os.unlink(file_path)
                except:
                    pass

        return {
            "operation": "chunking",
            "file_sizes_mb": file_sizes,
            "metrics": [
                {
                    "file_size_mb": m.file_size_mb,
                    "processing_time_ms": m.processing_time_ms,
                    "memory_usage_mb": m.memory_usage_mb,
                    "throughput_mbps": m.throughput_mbps,
                    "success": m.success
                } for m in results
            ],
            "avg_throughput_mbps": sum(m.throughput_mbps for m in results if m.success) / len([m for m in results if m.success]),
            "avg_memory_per_mb": sum(m.memory_usage_mb / m.file_size_mb for m in results if m.success and m.file_size_mb > 0) / len([m for m in results if m.success])
        }

    async def benchmark_buffer_memory(self, document_counts: List[int] = None) -> Dict[str, Any]:
        """Benchmark document-aware buffer memory performance"""
        if document_counts is None:
            document_counts = [10, 50, 100, 500, 1000]

        print(f"🧠 Benchmarking DocumentAwareBufferMemory with document counts: {document_counts}")

        buffer_memory = DocumentAwareBufferMemory({})
        results = []

        for doc_count in document_counts:
            # Create test documents
            test_docs = [f"Document {i} content with meaningful text for testing." * 10 for i in range(doc_count)]

            # Benchmark storage operation
            async def storage_operation():
                for i, content in enumerate(test_docs):
                    await buffer_memory.store_document(
                        content=content,
                        filename=f"test_doc_{i}.txt",
                        metadata={"index": i}
                    )

            result, metrics = await self._monitor_resource_usage(storage_operation)

            # Update metrics
            metrics.operation = "buffer_storage"
            metrics.file_size_mb = len(test_docs) * 0.001  # Approximate size
            if metrics.success and metrics.processing_time_ms > 0:
                metrics.items_per_second = doc_count / (metrics.processing_time_ms / 1000)

            results.append(metrics)
            self.metrics.append(metrics)

            print(f"  📚 {doc_count} docs: {metrics.processing_time_ms:.1f}ms, "
                  f"{metrics.memory_usage_mb:.1f}MB memory, "
                  f"{metrics.items_per_second:.1f} docs/s")

        return {
            "operation": "buffer_storage",
            "document_counts": document_counts,
            "metrics": [
                {
                    "document_count": count,
                    "processing_time_ms": m.processing_time_ms,
                    "memory_usage_mb": m.memory_usage_mb,
                    "items_per_second": m.items_per_second,
                    "success": m.success
                } for count, m in zip(document_counts, results)
            ],
            "avg_docs_per_second": sum(m.items_per_second for m in results if m.success) / len([m for m in results if m.success]),
            "memory_per_doc": sum(m.memory_usage_mb / (count if count > 0 else 1) for count, m in zip(document_counts, results) if m.success) / len([m for m in results if m.success])
        }

    async def benchmark_semantic_search(self, index_sizes: List[int] = None) -> Dict[str, Any]:
        """Benchmark semantic index search performance"""
        if index_sizes is None:
            index_sizes = [100, 500, 1000, 5000]

        print(f"🔍 Benchmarking DocumentSemanticIndex with index sizes: {index_sizes}")

        semantic_index = DocumentSemanticIndex({})
        results = []

        for index_size in index_sizes:
            # Create test index
            test_chunks = [f"Test document chunk {i} with search content." for i in range(index_size)]

            # Mock embeddings (1536 dimensions like OpenAI)
            import numpy as np
            test_embeddings = [np.random.rand(1536).astype(np.float32) for _ in test_chunks]

            # Benchmark search operation
            async def search_operation():
                # First index the chunks
                await semantic_index.index_document_chunks(test_chunks, test_embeddings)

                # Then search
                query_embedding = np.random.rand(1536).astype(np.float32)
                return await semantic_index.search_documents(query_embedding, k=10)

            result, metrics = await self._monitor_resource_usage(search_operation)

            # Update metrics
            metrics.operation = "semantic_search"
            metrics.file_size_mb = index_size * 0.001  # Approximate
            if metrics.success and metrics.processing_time_ms > 0:
                metrics.items_per_second = index_size / (metrics.processing_time_ms / 1000)

            results.append(metrics)
            self.metrics.append(metrics)

            print(f"  🔎 {index_size} items: {metrics.processing_time_ms:.1f}ms, "
                  f"{metrics.memory_usage_mb:.1f}MB memory, "
                  f"{metrics.items_per_second:.1f} items/s")

        return {
            "operation": "semantic_search",
            "index_sizes": index_sizes,
            "metrics": [
                {
                    "index_size": size,
                    "processing_time_ms": m.processing_time_ms,
                    "memory_usage_mb": m.memory_usage_mb,
                    "items_per_second": m.items_per_second,
                    "success": m.success
                } for size, m in zip(index_sizes, results)
            ],
            "avg_search_time_ms": sum(m.processing_time_ms for m in results if m.success) / len([m for m in results if m.success]),
            "memory_per_item": sum(m.memory_usage_mb / size for size, m in zip(index_sizes, results) if m.success and size > 0) / len([m for m in results if m.success])
        }

    async def benchmark_scalability(self, max_concurrent: int = 10) -> Dict[str, Any]:
        """Benchmark concurrent document processing scalability"""
        print(f"⚡ Benchmarking scalability with up to {max_concurrent} concurrent operations")

        chunk_manager = DocumentChunkManager()
        concurrent_levels = [1, 2, 5, max_concurrent]
        results = []

        for concurrent_ops in concurrent_levels:
            print(f"  Testing {concurrent_ops} concurrent operations...")

            # Create test content
            test_content = "Test document content for scalability testing. " * 100
            errors = []
            successful_ops = 0

            async def single_operation():
                nonlocal successful_ops
                try:
                    await chunk_manager.chunk_document(test_content, "scalability_test.txt")
                    successful_ops += 1
                except Exception as e:
                    errors.append(str(e))

            # Benchmark concurrent operations
            start_time = time.time()
            start_memory = self._get_current_memory_usage()

            # Run concurrent operations
            tasks = [single_operation() for _ in range(concurrent_ops)]
            await asyncio.gather(*tasks, return_exceptions=True)

            end_time = time.time()
            end_memory = self._get_current_memory_usage()

            processing_time_ms = (end_time - start_time) * 1000
            memory_usage_mb = end_memory - start_memory
            success_rate = successful_ops / concurrent_ops if concurrent_ops > 0 else 0

            result = ScalabilityResult(
                concurrent_operations=concurrent_ops,
                total_files=concurrent_ops,
                avg_processing_time_ms=processing_time_ms,
                avg_memory_usage_mb=memory_usage_mb,
                peak_memory_usage_mb=memory_usage_mb,  # Simplified
                success_rate=success_rate,
                errors=errors
            )

            results.append(result)
            self.scalability_results.append(result)

            print(f"    ✅ Success rate: {success_rate:.1%}, "
                  f"Time: {processing_time_ms:.1f}ms, "
                  f"Memory: {memory_usage_mb:.1f}MB")

        return {
            "operation": "scalability",
            "results": [
                {
                    "concurrent_operations": r.concurrent_operations,
                    "success_rate": r.success_rate,
                    "avg_processing_time_ms": r.avg_processing_time_ms,
                    "avg_memory_usage_mb": r.avg_memory_usage_mb,
                    "error_count": len(r.errors)
                } for r in results
            ],
            "max_concurrent_tested": max_concurrent,
            "scalability_score": min(r.success_rate for r in results) if results else 0.0
        }

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        if not self.metrics:
            return {"error": "No performance data collected"}

        # Calculate overall statistics
        total_operations = len(self.metrics)
        successful_operations = sum(1 for m in self.metrics if m.success)
        success_rate = successful_operations / total_operations if total_operations > 0 else 0

        # Memory statistics
        memory_usage = [m.memory_usage_mb for m in self.metrics if m.success]
        avg_memory = sum(memory_usage) / len(memory_usage) if memory_usage else 0
        max_memory = max(memory_usage) if memory_usage else 0

        # Processing time statistics
        processing_times = [m.processing_time_ms for m in self.metrics if m.success]
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        max_processing_time = max(processing_times) if processing_times else 0

        # Throughput statistics
        throughputs = [m.throughput_mbps for m in self.metrics if m.success and m.throughput_mbps > 0]
        avg_throughput = sum(throughputs) / len(throughputs) if throughputs else 0

        report = {
            "summary": {
                "total_operations": total_operations,
                "successful_operations": successful_operations,
                "success_rate": success_rate,
                "avg_memory_usage_mb": avg_memory,
                "max_memory_usage_mb": max_memory,
                "avg_processing_time_ms": avg_processing_time,
                "max_processing_time_ms": max_processing_time,
                "avg_throughput_mbps": avg_throughput
            },
            "performance_targets": {
                "memory_efficiency": "GOOD" if avg_memory < 100 else "NEEDS_IMPROVEMENT",
                "processing_speed": "GOOD" if avg_processing_time < 1000 else "NEEDS_IMPROVEMENT",
                "scalability": "GOOD" if success_rate > 0.95 else "NEEDS_IMPROVEMENT",
                "throughput": "GOOD" if avg_throughput > 1.0 else "NEEDS_IMPROVEMENT"
            },
            "recommendations": self._generate_recommendations(avg_memory, avg_processing_time, success_rate, avg_throughput),
            "detailed_metrics": [
                {
                    "operation": m.operation,
                    "file_size_mb": m.file_size_mb,
                    "processing_time_ms": m.processing_time_ms,
                    "memory_usage_mb": m.memory_usage_mb,
                    "throughput_mbps": m.throughput_mbps,
                    "success": m.success
                } for m in self.metrics
            ]
        }

        return report

    def _generate_recommendations(self, avg_memory: float, avg_time: float, success_rate: float, throughput: float) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []

        if avg_memory > 100:
            recommendations.append("Consider implementing streaming processing for large files to reduce memory usage")

        if avg_time > 1000:
            recommendations.append("Optimize processing algorithms or consider parallel processing for speed improvement")

        if success_rate < 0.95:
            recommendations.append("Improve error handling and fallback mechanisms to increase reliability")

        if throughput < 1.0:
            recommendations.append("Consider caching, preprocessing, or async processing to improve throughput")

        if not recommendations:
            recommendations.append("Performance is within acceptable limits. Consider monitoring in production.")

        return recommendations

    def save_report(self, filepath: str) -> None:
        """Save performance report to file"""
        report = self.generate_performance_report()
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"📊 Performance report saved to {filepath}")


# Test classes for pytest
class TestDocumentProcessingPerformance:
    """Test class for document processing performance"""

    @pytest.mark.asyncio
    async def test_chunking_performance(self):
        """Test document chunking performance"""
        benchmark = DocumentProcessingBenchmark()
        result = await benchmark.benchmark_chunk_manager([0.1, 0.5, 1.0])

        assert result["avg_throughput_mbps"] > 0
        assert len(result["metrics"]) == 3
        print(f"✅ Chunking benchmark completed: {result['avg_throughput_mbps']:.2f} MB/s average")

    @pytest.mark.asyncio
    async def test_buffer_memory_performance(self):
        """Test buffer memory performance"""
        benchmark = DocumentProcessingBenchmark()
        result = await benchmark.benchmark_buffer_memory([10, 50, 100])

        assert result["avg_docs_per_second"] > 0
        assert len(result["metrics"]) == 3
        print(f"✅ Buffer memory benchmark completed: {result['avg_docs_per_second']:.1f} docs/s average")

    @pytest.mark.asyncio
    async def test_semantic_search_performance(self):
        """Test semantic search performance"""
        benchmark = DocumentProcessingBenchmark()
        result = await benchmark.benchmark_semantic_search([100, 500])

        assert result["avg_search_time_ms"] > 0
        assert len(result["metrics"]) == 2
        print(f"✅ Semantic search benchmark completed: {result['avg_search_time_ms']:.1f}ms average")

    @pytest.mark.asyncio
    async def test_scalability_performance(self):
        """Test scalability performance"""
        benchmark = DocumentProcessingBenchmark()
        result = await benchmark.benchmark_scalability(max_concurrent=5)

        assert result["scalability_score"] >= 0
        assert len(result["results"]) > 0
        print(f"✅ Scalability benchmark completed: {result['scalability_score']:.1%} success rate")

    @pytest.mark.asyncio
    async def test_comprehensive_performance_suite(self):
        """Run comprehensive performance test suite"""
        benchmark = DocumentProcessingBenchmark()

        # Run all benchmarks
        print("\n🚀 Running comprehensive performance benchmark suite...")

        chunking_result = await benchmark.benchmark_chunk_manager([0.1, 0.5, 1.0])
        buffer_result = await benchmark.benchmark_buffer_memory([10, 50, 100])
        search_result = await benchmark.benchmark_semantic_search([100, 500])
        scalability_result = await benchmark.benchmark_scalability(max_concurrent=3)

        # Generate and save report
        report = benchmark.generate_performance_report()
        benchmark.save_report("/tmp/document_processing_performance_report.json")

        # Assertions
        assert report["summary"]["success_rate"] > 0.8, "Success rate should be above 80%"
        assert report["summary"]["avg_memory_usage_mb"] < 500, "Average memory usage should be under 500MB"

        print("\n📊 PERFORMANCE BENCHMARK RESULTS:")
        print(f"  📈 Success Rate: {report['summary']['success_rate']:.1%}")
        print(f"  🧠 Avg Memory: {report['summary']['avg_memory_usage_mb']:.1f}MB")
        print(f"  ⏱️  Avg Time: {report['summary']['avg_processing_time_ms']:.1f}ms")
        print(f"  🚀 Avg Throughput: {report['summary']['avg_throughput_mbps']:.2f}MB/s")

        print("\n🎯 PERFORMANCE TARGETS:")
        for target, status in report["performance_targets"].items():
            print(f"  {target}: {status}")

        print("\n💡 RECOMMENDATIONS:")
        for rec in report["recommendations"]:
            print(f"  • {rec}")


if __name__ == "__main__":
    async def main():
        benchmark = DocumentProcessingBenchmark()

        print("🚀 Starting Document Processing Performance Benchmarks")
        print("=" * 60)

        # Run comprehensive benchmarks
        await benchmark.benchmark_chunk_manager()
        await benchmark.benchmark_buffer_memory()
        await benchmark.benchmark_semantic_search()
        await benchmark.benchmark_scalability()

        # Generate and display report
        report = benchmark.generate_performance_report()
        benchmark.save_report("document_processing_performance_report.json")

        print("\n" + "=" * 60)
        print("📊 FINAL PERFORMANCE REPORT")
        print("=" * 60)
        print(f"Success Rate: {report['summary']['success_rate']:.1%}")
        print(f"Average Memory Usage: {report['summary']['avg_memory_usage_mb']:.1f}MB")
        print(f"Average Processing Time: {report['summary']['avg_processing_time_ms']:.1f}ms")
        print(f"Average Throughput: {report['summary']['avg_throughput_mbps']:.2f}MB/s")
        print("\nRecommendations:")
        for rec in report["recommendations"]:
            print(f"  • {rec}")

    asyncio.run(main())
