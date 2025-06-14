"""
Cache analytics and performance monitoring for the intelligent caching system.

This module provides detailed analytics on cache performance, hit rates,
and optimization opportunities for the multi-layer caching system.
"""

import asyncio
import json

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import statistics

from .cache_types import CacheType, CacheStatistics





@dataclass
class HitRateMetric:
    """Metrics for cache hit rates over time."""
    timestamp: float
    cache_layer: str  # L1, L2, L3, or overall
    hit_count: int
    miss_count: int
    hit_rate: float
    avg_response_time_ms: float

    @property
    def total_requests(self) -> int:
        """Total number of requests."""
        return self.hit_count + self.miss_count


@dataclass
class PerformanceMetric:
    """Performance metrics for cache operations."""
    timestamp: float
    operation: str  # get, put, remove, clear
    cache_component: str
    duration_ms: float
    success: bool
    cache_size_before: int
    cache_size_after: int
    memory_usage_bytes: int


@dataclass
class CacheLayerStats:
    """Statistics for a specific cache layer."""
    layer_name: str
    total_hits: int = 0
    total_misses: int = 0
    total_requests: int = 0
    avg_hit_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    memory_usage_bytes: int = 0
    cache_size: int = 0
    last_cleanup_time: float = 0.0
    cleanup_count: int = 0

    @property
    def hit_rate(self) -> float:
        """Current hit rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_hits / self.total_requests) * 100


class CacheHitAnalyzer:
    """
    Cache hit rate analyzer and performance monitor.

    Tracks cache performance across all layers and provides analytics
    for optimization and tuning decisions.
    """

    def __init__(self,
                 history_retention_hours: int = 24,
                 metric_collection_interval: int = 60):
        """
        Initialize cache hit analyzer.

        Args:
            history_retention_hours: How long to keep performance history
            metric_collection_interval: Interval for collecting metrics (seconds)
        """
        self.history_retention_hours = history_retention_hours
        self.metric_collection_interval = metric_collection_interval

        # Performance tracking
        self.hit_rate_history: List[HitRateMetric] = []
        self.performance_history: List[PerformanceMetric] = []
        self.layer_stats: Dict[str, CacheLayerStats] = {}

        # Real-time tracking
        self.recent_requests: deque = deque(maxlen=1000)  # Last 1000 requests
        self.cache_components: Dict[str, any] = {}

        # Analytics state
        self.is_collecting = False
        self.collection_task: Optional[asyncio.Task] = None

        # Performance buckets for percentile calculations
        self.response_time_buckets: Dict[str, List[float]] = defaultdict(list)

        # Anomaly detection
        self.baseline_hit_rates: Dict[str, float] = {}
        self.performance_alerts: List[Dict[str, Any]] = []

    def register_cache_component(self, name: str, cache_component: any) -> None:
        """
        Register a cache component for monitoring.

        Args:
            name: Unique name for the cache component
            cache_component: Cache instance to monitor
        """
        self.cache_components[name] = cache_component
        if name not in self.layer_stats:
            self.layer_stats[name] = CacheLayerStats(layer_name=name)
        #  Info - add observability event

    def unregister_cache_component(self, name: str) -> None:
        """Remove a cache component from monitoring."""
        if name in self.cache_components:
            del self.cache_components[name]
        #  Info - add observability event

    async def start_collection(self) -> None:
        """Start automatic metrics collection."""
        if self.is_collecting:
            return

        self.is_collecting = True
        self.collection_task = asyncio.create_task(self._collection_loop())
        #  Info - add observability event

    async def stop_collection(self) -> None:
        """Stop automatic metrics collection."""
        if not self.is_collecting:
            return

        self.is_collecting = False
        if self.collection_task and not self.collection_task.done():
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass

        #  Info - add observability event

    def record_cache_hit(self,
                        cache_layer: str,
                        cache_type: CacheType,
                        response_time_ms: float,
                        cache_key: str = "",
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record a cache hit event.

        Args:
            cache_layer: Name of the cache layer (L1, L2, L3, etc.)
            cache_type: Type of cache hit
            response_time_ms: Response time in milliseconds
            cache_key: Cache key (for debugging)
            metadata: Additional metadata
        """
        timestamp = time.time()

        # Update layer stats
        if cache_layer not in self.layer_stats:
            self.layer_stats[cache_layer] = CacheLayerStats(layer_name=cache_layer)

        stats = self.layer_stats[cache_layer]
        stats.total_hits += 1
        stats.total_requests += 1

        # Update response time tracking
        self.response_time_buckets[cache_layer].append(response_time_ms)
        if len(self.response_time_buckets[cache_layer]) > 1000:
            self.response_time_buckets[cache_layer] = self.response_time_buckets[cache_layer][-500:]

        # Record recent request
        self.recent_requests.append({
            'timestamp': timestamp,
            'cache_layer': cache_layer,
            'cache_type': cache_type.value,
            'hit': True,
            'response_time_ms': response_time_ms,
            'cache_key': cache_key,
            'metadata': metadata or {}
        })

        # Check for anomalies
        self._check_performance_anomalies(cache_layer, response_time_ms, True)

        #  Debug - add observability event

    def record_cache_miss(self,
                         cache_layer: str,
                         response_time_ms: float,
                         cache_key: str = "",
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record a cache miss event.

        Args:
            cache_layer: Name of the cache layer
            response_time_ms: Response time in milliseconds
            cache_key: Cache key (for debugging)
            metadata: Additional metadata
        """
        timestamp = time.time()

        # Update layer stats
        if cache_layer not in self.layer_stats:
            self.layer_stats[cache_layer] = CacheLayerStats(layer_name=cache_layer)

        stats = self.layer_stats[cache_layer]
        stats.total_misses += 1
        stats.total_requests += 1

        # Update response time tracking
        self.response_time_buckets[cache_layer].append(response_time_ms)
        if len(self.response_time_buckets[cache_layer]) > 1000:
            self.response_time_buckets[cache_layer] = self.response_time_buckets[cache_layer][-500:]

        # Record recent request
        self.recent_requests.append({
            'timestamp': timestamp,
            'cache_layer': cache_layer,
            'cache_type': CacheType.MISS.value,
            'hit': False,
            'response_time_ms': response_time_ms,
            'cache_key': cache_key,
            'metadata': metadata or {}
        })

        # Check for anomalies
        self._check_performance_anomalies(cache_layer, response_time_ms, False)

        #  Debug - add observability event

    def record_cache_operation(self,
                              operation: str,
                              cache_component: str,
                              duration_ms: float,
                              success: bool,
                              cache_size_before: int = 0,
                              cache_size_after: int = 0,
                              memory_usage_bytes: int = 0) -> None:
        """
        Record a cache operation (put, remove, clear, etc.).

        Args:
            operation: Type of operation
            cache_component: Name of cache component
            duration_ms: Operation duration in milliseconds
            success: Whether operation succeeded
            cache_size_before: Cache size before operation
            cache_size_after: Cache size after operation
            memory_usage_bytes: Current memory usage
        """
        metric = PerformanceMetric(
            timestamp=time.time(),
            operation=operation,
            cache_component=cache_component,
            duration_ms=duration_ms,
            success=success,
            cache_size_before=cache_size_before,
            cache_size_after=cache_size_after,
            memory_usage_bytes=memory_usage_bytes
        )

        self.performance_history.append(metric)

        # Cleanup old history
        self._cleanup_old_history()

        #  Debug - add observability event

    def get_hit_rate_summary(self, hours: int = 1) -> Dict[str, Any]:
        """
        Get hit rate summary for the specified time period.

        Args:
            hours: Number of hours to analyze

        Returns:
            Hit rate summary with statistics
        """
        cutoff_time = time.time() - (hours * 3600)

        # Filter recent requests
        recent_requests = [
            req for req in self.recent_requests
            if req['timestamp'] > cutoff_time
        ]

        if not recent_requests:
            return {'total_requests': 0, 'overall_hit_rate': 0.0, 'layers': {}}

        # Overall statistics
        total_requests = len(recent_requests)
        total_hits = sum(1 for req in recent_requests if req['hit'])
        overall_hit_rate = (total_hits / total_requests) * 100 if total_requests > 0 else 0.0

        # Per-layer statistics
        layer_summary = {}
        for layer_name in set(req['cache_layer'] for req in recent_requests):
            layer_requests = [req for req in recent_requests if req['cache_layer'] == layer_name]
            layer_hits = sum(1 for req in layer_requests if req['hit'])
            layer_hit_rate = (layer_hits / len(layer_requests)) * 100 if layer_requests else 0.0

            response_times = [req['response_time_ms'] for req in layer_requests]
            avg_response_time = statistics.mean(response_times) if response_times else 0.0

            layer_summary[layer_name] = {
                'requests': len(layer_requests),
                'hits': layer_hits,
                'misses': len(layer_requests) - layer_hits,
                'hit_rate': layer_hit_rate,
                'avg_response_time_ms': avg_response_time,
                'p95_response_time_ms': statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 5 else avg_response_time,
                'p99_response_time_ms': statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 10 else avg_response_time
            }

        return {
            'time_period_hours': hours,
            'total_requests': total_requests,
            'total_hits': total_hits,
            'total_misses': total_requests - total_hits,
            'overall_hit_rate': overall_hit_rate,
            'layers': layer_summary
        }

    def get_performance_summary(self, hours: int = 1) -> Dict[str, Any]:
        """
        Get performance summary for cache operations.

        Args:
            hours: Number of hours to analyze

        Returns:
            Performance summary with statistics
        """
        cutoff_time = time.time() - (hours * 3600)

        recent_operations = [
            op for op in self.performance_history
            if op.timestamp > cutoff_time
        ]

        if not recent_operations:
            return {'total_operations': 0, 'operations': {}}

        # Group by operation type
        operation_summary = {}
        for op_type in set(op.operation for op in recent_operations):
            ops = [op for op in recent_operations if op.operation == op_type]
            durations = [op.duration_ms for op in ops]
            successes = sum(1 for op in ops if op.success)

            operation_summary[op_type] = {
                'count': len(ops),
                'success_count': successes,
                'success_rate': (successes / len(ops)) * 100 if ops else 0.0,
                'avg_duration_ms': statistics.mean(durations) if durations else 0.0,
                'p95_duration_ms': statistics.quantiles(durations, n=20)[18] if len(durations) >= 5 else 0.0,
                'p99_duration_ms': statistics.quantiles(durations, n=100)[98] if len(durations) >= 10 else 0.0
            }

        return {
            'time_period_hours': hours,
            'total_operations': len(recent_operations),
            'operations': operation_summary
        }

    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate optimization recommendations based on analytics.

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Analyze hit rates
        hit_rate_summary = self.get_hit_rate_summary(24)  # Last 24 hours

        for layer_name, layer_data in hit_rate_summary.get('layers', {}).items():
            hit_rate = layer_data['hit_rate']
            avg_response_time = layer_data['avg_response_time_ms']

            # Low hit rate recommendations
            if hit_rate < 50:
                recommendations.append({
                    'type': 'hit_rate_optimization',
                    'priority': 'high',
                    'layer': layer_name,
                    'issue': f'Low hit rate ({hit_rate:.1f}%)',
                    'recommendation': 'Consider increasing cache size or adjusting TTL settings',
                    'impact': 'high'
                })

            # High response time recommendations
            if avg_response_time > 100:  # > 100ms
                recommendations.append({
                    'type': 'performance_optimization',
                    'priority': 'medium',
                    'layer': layer_name,
                    'issue': f'High response time ({avg_response_time:.1f}ms)',
                    'recommendation': 'Consider optimizing cache storage or using faster storage backend',
                    'impact': 'medium'
                })

        # Analyze memory usage
        for layer_name, stats in self.layer_stats.items():
            if stats.memory_usage_bytes > 100 * 1024 * 1024:  # > 100MB
                recommendations.append({
                    'type': 'memory_optimization',
                    'priority': 'medium',
                    'layer': layer_name,
                    'issue': f'High memory usage ({stats.memory_usage_bytes / (1024*1024):.1f}MB)',
                    'recommendation': 'Consider implementing compression or reducing cache size',
                    'impact': 'medium'
                })

        # Check for performance anomalies
        if self.performance_alerts:
            for alert in self.performance_alerts[-5:]:  # Last 5 alerts
                recommendations.append({
                    'type': 'anomaly_detection',
                    'priority': 'high',
                    'layer': alert.get('layer', 'unknown'),
                    'issue': alert.get('issue', 'Performance anomaly detected'),
                    'recommendation': 'Investigate recent changes or system resource constraints',
                    'impact': 'high'
                })

        return recommendations

    def export_analytics_data(self, format: str = 'json') -> str:
        """
        Export analytics data for external analysis.

        Args:
            format: Export format ('json', 'csv')

        Returns:
            Exported data as string
        """
        data = {
            'timestamp': time.time(),
            'hit_rate_summary': self.get_hit_rate_summary(24),
            'performance_summary': self.get_performance_summary(24),
            'layer_stats': {
                name: {
                    'layer_name': stats.layer_name,
                    'total_hits': stats.total_hits,
                    'total_misses': stats.total_misses,
                    'hit_rate': stats.hit_rate,
                    'memory_usage_bytes': stats.memory_usage_bytes,
                    'cache_size': stats.cache_size
                }
                for name, stats in self.layer_stats.items()
            },
            'recommendations': self.get_optimization_recommendations()
        }

        if format == 'json':
            return json.dumps(data, indent=2)
        else:
            # CSV export would require additional formatting
            return json.dumps(data, indent=2)  # Fallback to JSON

    async def _collection_loop(self) -> None:
        """Main metrics collection loop."""
        while self.is_collecting:
            try:
                await self._collect_current_metrics()
                await asyncio.sleep(self.metric_collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                #  Error - add observability event
                await asyncio.sleep(self.metric_collection_interval)

    async def _collect_current_metrics(self) -> None:
        """Collect current metrics from all cache components."""
        timestamp = time.time()

        for name, component in self.cache_components.items():
            if name not in self.layer_stats:
                self.layer_stats[name] = CacheLayerStats(layer_name=name)

            stats = self.layer_stats[name]

            # Update memory usage and cache size
            if hasattr(component, 'get_memory_usage'):
                stats.memory_usage_bytes = component.get_memory_usage()

            if hasattr(component, 'size'):
                stats.cache_size = component.size()

            # Calculate average hit rate
            if stats.total_requests > 0:
                stats.avg_hit_rate = (stats.total_hits / stats.total_requests) * 100

            # Calculate average response time
            if name in self.response_time_buckets and self.response_time_buckets[name]:
                stats.avg_response_time_ms = statistics.mean(self.response_time_buckets[name])

        # Create hit rate metric for history
        for name, stats in self.layer_stats.items():
            metric = HitRateMetric(
                timestamp=timestamp,
                cache_layer=name,
                hit_count=stats.total_hits,
                miss_count=stats.total_misses,
                hit_rate=stats.hit_rate,
                avg_response_time_ms=stats.avg_response_time_ms
            )
            self.hit_rate_history.append(metric)

        # Cleanup old history
        self._cleanup_old_history()

    def _cleanup_old_history(self) -> None:
        """Remove old history entries to manage memory usage."""
        cutoff_time = time.time() - (self.history_retention_hours * 3600)

        # Clean hit rate history
        self.hit_rate_history = [
            metric for metric in self.hit_rate_history
            if metric.timestamp > cutoff_time
        ]

        # Clean performance history
        self.performance_history = [
            metric for metric in self.performance_history
            if metric.timestamp > cutoff_time
        ]

        # Clean performance alerts
        self.performance_alerts = [
            alert for alert in self.performance_alerts
            if alert.get('timestamp', 0) > cutoff_time
        ]

    def _check_performance_anomalies(self, cache_layer: str, response_time_ms: float, hit: bool) -> None:
        """Check for performance anomalies and alert if found."""
        # Establish baseline if not exists
        if cache_layer not in self.baseline_hit_rates:
            if cache_layer in self.layer_stats:
                self.baseline_hit_rates[cache_layer] = self.layer_stats[cache_layer].hit_rate
            return

        # Check for sudden hit rate drop
        current_hit_rate = self.layer_stats[cache_layer].hit_rate
        baseline_hit_rate = self.baseline_hit_rates[cache_layer]

        if baseline_hit_rate > 50 and current_hit_rate < baseline_hit_rate * 0.7:  # 30% drop
            alert = {
                'timestamp': time.time(),
                'type': 'hit_rate_drop',
                'layer': cache_layer,
                'issue': f'Hit rate dropped from {baseline_hit_rate:.1f}% to {current_hit_rate:.1f}%',
                'severity': 'high'
            }
            self.performance_alerts.append(alert)
            #  Warning - add observability event

        # Check for extremely high response times
        if response_time_ms > 1000:  # > 1 second
            alert = {
                'timestamp': time.time(),
                'type': 'high_response_time',
                'layer': cache_layer,
                'issue': f'Very high response time: {response_time_ms:.1f}ms',
                'severity': 'medium'
            }
            self.performance_alerts.append(alert)
            #  Warning - add observability event

        # Update baseline periodically
        if time.time() % 3600 < 60:  # Every hour
            self.baseline_hit_rates[cache_layer] = current_hit_rate
