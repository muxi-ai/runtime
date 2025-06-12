"""
Memory optimization and automatic cleanup for the intelligent caching system.

This module provides automatic memory management, resource cleanup, and performance
monitoring to ensure the caching system maintains optimal memory usage.
"""

import asyncio
import gc
import logging
import psutil
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .cache_types import MemoryStats


logger = logging.getLogger(__name__)


@dataclass
class CleanupRule:
    """Configuration for automatic cleanup rules."""
    name: str
    trigger_memory_percent: float  # Trigger cleanup when memory usage exceeds this %
    target_reduction_percent: float  # Try to reduce memory by this %
    min_interval_seconds: int  # Minimum time between cleanups
    priority: int  # Higher priority rules run first


class MemoryOptimizer:
    """
    Automatic memory optimization and cleanup manager.

    Monitors memory usage across all cache components and triggers intelligent
    cleanup operations to maintain optimal performance and prevent memory pressure.
    """

    def __init__(
        self,
        target_memory_percent: float = 70.0,
        max_memory_percent: float = 85.0,
        cleanup_interval_seconds: int = 60,
        aggressive_cleanup_percent: float = 90.0
    ):
        """
        Initialize memory optimizer.

        Args:
            target_memory_percent: Target memory usage as % of system RAM
            max_memory_percent: Maximum memory usage before aggressive cleanup
            cleanup_interval_seconds: Interval between cleanup checks
            aggressive_cleanup_percent: Trigger aggressive cleanup above this %
        """
        self.target_memory_percent = target_memory_percent
        self.max_memory_percent = max_memory_percent
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.aggressive_cleanup_percent = aggressive_cleanup_percent

        # Cache components to monitor and clean
        self.cache_components: Dict[str, any] = {}
        self.cleanup_rules: List[CleanupRule] = []
        self.last_cleanup_times: Dict[str, float] = {}

        # Monitoring state
        self.is_running = False
        self.cleanup_task: Optional[asyncio.Task] = None
        self.stats = MemoryStats()

        # Performance tracking
        self.cleanup_history: List[Tuple[float, str, int]] = []  # (timestamp, rule_name, bytes_freed)

        # Initialize default cleanup rules
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default cleanup rules."""
        self.cleanup_rules = [
            CleanupRule(
                name="emergency_cleanup",
                trigger_memory_percent=self.aggressive_cleanup_percent,
                target_reduction_percent=20.0,
                min_interval_seconds=10,
                priority=100
            ),
            CleanupRule(
                name="expired_cleanup",
                trigger_memory_percent=self.max_memory_percent,
                target_reduction_percent=10.0,
                min_interval_seconds=30,
                priority=80
            ),
            CleanupRule(
                name="lru_cleanup",
                trigger_memory_percent=self.target_memory_percent,
                target_reduction_percent=5.0,
                min_interval_seconds=60,
                priority=60
            ),
            CleanupRule(
                name="size_optimization",
                trigger_memory_percent=self.target_memory_percent * 0.8,
                target_reduction_percent=3.0,
                min_interval_seconds=300,  # 5 minutes
                priority=40
            )
        ]

    def register_cache_component(self, name: str, cache_component: any) -> None:
        """
        Register a cache component for monitoring and cleanup.

        Args:
            name: Unique name for the cache component
            cache_component: Cache instance with standard interface
        """
        self.cache_components[name] = cache_component
        self.last_cleanup_times[name] = 0.0
        logger.info(f"Registered cache component: {name}")

    def unregister_cache_component(self, name: str) -> None:
        """Remove a cache component from monitoring."""
        if name in self.cache_components:
            del self.cache_components[name]
            del self.last_cleanup_times[name]
            logger.info(f"Unregistered cache component: {name}")

    async def start(self) -> None:
        """Start the memory optimization background task."""
        if self.is_running:
            return

        self.is_running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Memory optimizer started")

    async def stop(self) -> None:
        """Stop the memory optimization background task."""
        if not self.is_running:
            return

        self.is_running = False
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Memory optimizer stopped")

    async def force_cleanup(self, rule_name: Optional[str] = None) -> MemoryStats:
        """
        Force immediate cleanup operation.

        Args:
            rule_name: Specific rule to apply, or None for all applicable rules

        Returns:
            Memory statistics after cleanup
        """
        logger.info(f"Force cleanup triggered: {rule_name or 'all rules'}")

        if rule_name:
            rule = next((r for r in self.cleanup_rules if r.name == rule_name), None)
            if rule:
                await self._apply_cleanup_rule(rule, force=True)
        else:
            current_stats = self.get_memory_stats()
            current_percent = current_stats.memory_utilization * 100

            # Apply all applicable rules
            applicable_rules = [
                rule for rule in sorted(self.cleanup_rules, key=lambda r: r.priority, reverse=True)
                if current_percent >= rule.trigger_memory_percent
            ]

            for rule in applicable_rules:
                await self._apply_cleanup_rule(rule, force=True)

        return self.get_memory_stats()

    def get_memory_stats(self) -> MemoryStats:
        """Get current memory statistics."""
        # System memory info
        memory = psutil.virtual_memory()

        # Cache component memory usage
        cache_usage = {}
        total_cache_bytes = 0

        for name, component in self.cache_components.items():
            if hasattr(component, 'get_memory_usage'):
                usage = component.get_memory_usage()
                cache_usage[name] = usage
                total_cache_bytes += usage
            else:
                cache_usage[name] = 0

        self.stats.update_memory_usage(
            l1_bytes=cache_usage.get('L1', 0),
            l2_bytes=cache_usage.get('L2', 0),
            l3_bytes=cache_usage.get('L3', 0),
            embeddings_bytes=cache_usage.get('embeddings', 0)
        )
        self.stats.memory_limit_bytes = memory.total

        return self.stats

    async def _cleanup_loop(self) -> None:
        """Main cleanup loop that runs in the background."""
        while self.is_running:
            try:
                await self._perform_cleanup_check()
                await asyncio.sleep(self.cleanup_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(self.cleanup_interval_seconds)

    async def _perform_cleanup_check(self) -> None:
        """Check if cleanup is needed and apply appropriate rules."""
        current_stats = self.get_memory_stats()
        current_percent = current_stats.memory_utilization * 100

        # Find applicable cleanup rules
        applicable_rules = []
        current_time = time.time()

        for rule in self.cleanup_rules:
            if (current_percent >= rule.trigger_memory_percent and
                current_time - self.last_cleanup_times.get(rule.name, 0) >= rule.min_interval_seconds):
                applicable_rules.append(rule)

        if not applicable_rules:
            return

        # Sort by priority and apply rules
        applicable_rules.sort(key=lambda r: r.priority, reverse=True)

        logger.info(
            f"Memory cleanup triggered: {current_percent:.1f}% usage, "
            f"applying {len(applicable_rules)} rules"
        )

        for rule in applicable_rules:
            await self._apply_cleanup_rule(rule)

    async def _apply_cleanup_rule(self, rule: CleanupRule, force: bool = False) -> int:
        """
        Apply a specific cleanup rule.

        Args:
            rule: Cleanup rule to apply
            force: Skip interval checks if True

        Returns:
            Bytes freed by the cleanup operation
        """
        start_stats = self.get_memory_stats()
        start_time = time.time()

        if not force:
            last_cleanup = self.last_cleanup_times.get(rule.name, 0)
            if start_time - last_cleanup < rule.min_interval_seconds:
                return 0

        bytes_freed = 0

        try:
            # Apply rule-specific cleanup logic
            if rule.name == "emergency_cleanup":
                bytes_freed = await self._emergency_cleanup(rule.target_reduction_percent)
            elif rule.name == "expired_cleanup":
                bytes_freed = await self._expired_cleanup()
            elif rule.name == "lru_cleanup":
                bytes_freed = await self._lru_cleanup(rule.target_reduction_percent)
            elif rule.name == "size_optimization":
                bytes_freed = await self._size_optimization()

            # Update cleanup history
            self.last_cleanup_times[rule.name] = start_time
            self.cleanup_history.append((start_time, rule.name, bytes_freed))

            # Keep only recent history
            cutoff_time = start_time - 3600  # 1 hour
            self.cleanup_history = [
                entry for entry in self.cleanup_history
                if entry[0] > cutoff_time
            ]

            logger.info(
                f"Cleanup rule '{rule.name}' freed {bytes_freed:,} bytes "
                f"in {(time.time() - start_time):.2f}s"
            )

        except Exception as e:
            logger.error(f"Error applying cleanup rule '{rule.name}': {e}")

        return bytes_freed

    async def _emergency_cleanup(self, target_reduction_percent: float) -> int:
        """Emergency cleanup - most aggressive memory reduction."""
        bytes_freed = 0

        # Force garbage collection
        gc.collect()

        # Clear caches aggressively, starting with largest
        cache_sizes = [
            (name, component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0)
            for name, component in self.cache_components.items()
        ]
        cache_sizes.sort(key=lambda x: x[1], reverse=True)

        target_bytes = sum(size for _, size in cache_sizes) * (target_reduction_percent / 100)

        for name, size in cache_sizes:
            if bytes_freed >= target_bytes:
                break

            component = self.cache_components[name]
            if hasattr(component, 'clear'):
                before_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                await component.clear()
                after_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                bytes_freed += before_size - after_size
                logger.warning(f"Emergency cleanup: cleared cache '{name}' ({before_size:,} bytes)")

        return bytes_freed

    async def _expired_cleanup(self) -> int:
        """Remove expired items from all caches."""
        bytes_freed = 0

        for name, component in self.cache_components.items():
            if hasattr(component, 'cleanup_expired'):
                before_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                expired_count = await component.cleanup_expired()
                after_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                component_freed = before_size - after_size
                bytes_freed += component_freed

                if expired_count > 0:
                    logger.info(f"Expired cleanup: removed {expired_count} items from '{name}' ({component_freed:,} bytes)")

        return bytes_freed

    async def _lru_cleanup(self, target_reduction_percent: float) -> int:
        """Remove least recently used items to achieve target reduction."""
        bytes_freed = 0

        for name, component in self.cache_components.items():
            if not hasattr(component, 'get_memory_usage'):
                continue

            current_size = component.get_memory_usage()
            target_reduction = current_size * (target_reduction_percent / 100)

            # For LRU caches, remove items until target is reached
            if hasattr(component, '_lru_cleanup'):
                freed = await component._lru_cleanup(target_reduction)
                bytes_freed += freed
                if freed > 0:
                    logger.info(f"LRU cleanup: freed {freed:,} bytes from '{name}'")

        return bytes_freed

    async def _size_optimization(self) -> int:
        """Optimize cache sizes and compress where possible."""
        bytes_freed = 0

        # Force garbage collection to reclaim unused memory
        collected = gc.collect()
        if collected > 0:
            logger.info(f"Garbage collection reclaimed {collected} objects")

        # Optimize individual cache components
        for name, component in self.cache_components.items():
            if hasattr(component, '_optimize_storage'):
                before_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                await component._optimize_storage()
                after_size = component.get_memory_usage() if hasattr(component, 'get_memory_usage') else 0
                component_freed = before_size - after_size
                bytes_freed += component_freed

                if component_freed > 0:
                    logger.info(f"Size optimization: optimized '{name}' ({component_freed:,} bytes)")

        return bytes_freed

    def get_cleanup_history(self, hours: int = 1) -> List[Tuple[float, str, int]]:
        """
        Get cleanup history for the specified time period.

        Args:
            hours: Number of hours of history to return

        Returns:
            List of (timestamp, rule_name, bytes_freed) tuples
        """
        cutoff_time = time.time() - (hours * 3600)
        return [
            entry for entry in self.cleanup_history
            if entry[0] > cutoff_time
        ]

    def get_performance_summary(self) -> Dict[str, any]:
        """Get a summary of memory optimization performance."""
        current_stats = self.get_memory_stats()
        recent_history = self.get_cleanup_history(24)  # 24 hours

        total_bytes_freed = sum(entry[2] for entry in recent_history)
        cleanup_count = len(recent_history)

        rule_performance = {}
        for rule_name in set(entry[1] for entry in recent_history):
            rule_entries = [entry for entry in recent_history if entry[1] == rule_name]
            rule_performance[rule_name] = {
                'count': len(rule_entries),
                'total_bytes_freed': sum(entry[2] for entry in rule_entries),
                'avg_bytes_freed': sum(entry[2] for entry in rule_entries) / len(rule_entries) if rule_entries else 0
            }

        return {
            'current_memory_usage': {
                'system_percent': current_stats.memory_utilization * 100,
                'total_bytes': current_stats.total_memory_bytes,
                'cache_bytes': current_stats.total_memory_bytes
            },
            'cleanup_performance': {
                'total_cleanups_24h': cleanup_count,
                'total_bytes_freed_24h': total_bytes_freed,
                'avg_bytes_per_cleanup': total_bytes_freed / cleanup_count if cleanup_count > 0 else 0
            },
            'rule_performance': rule_performance,
            'cache_components': {
                name: {
                    'size': getattr(component, 'get_memory_usage', lambda: 0)(),
                    'component_type': type(component).__name__
                }
                for name, component in self.cache_components.items()
            }
        }

    async def optimize_for_workload(self, workload_type: str = "balanced") -> None:
        """
        Optimize memory settings for specific workload types.

        Args:
            workload_type: Type of workload ('memory_intensive', 'balanced', 'performance')
        """
        if workload_type == "memory_intensive":
            # More aggressive cleanup for memory-constrained environments
            self.target_memory_percent = 60.0
            self.max_memory_percent = 75.0
            self.cleanup_interval_seconds = 30

        elif workload_type == "performance":
            # Less aggressive cleanup for performance-critical environments
            self.target_memory_percent = 80.0
            self.max_memory_percent = 90.0
            self.cleanup_interval_seconds = 120

        else:  # balanced
            # Default balanced settings
            self.target_memory_percent = 70.0
            self.max_memory_percent = 85.0
            self.cleanup_interval_seconds = 60

        # Update cleanup rules accordingly
        self._init_default_rules()

        logger.info(f"Memory optimizer configured for '{workload_type}' workload")


class ResourceMonitor:
    """
    System resource monitoring for the caching system.

    Provides real-time monitoring of CPU, memory, disk I/O, and network
    resources to help optimize cache performance.
    """

    def __init__(self, monitoring_interval: int = 30):
        """
        Initialize resource monitor.

        Args:
            monitoring_interval: Interval between monitoring checks in seconds
        """
        self.monitoring_interval = monitoring_interval
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None

        # Resource history
        self.cpu_history: List[Tuple[float, float]] = []  # (timestamp, cpu_percent)
        self.memory_history: List[Tuple[float, float]] = []  # (timestamp, memory_percent)
        self.disk_history: List[Tuple[float, float, float]] = []  # (timestamp, read_mbps, write_mbps)

    async def start_monitoring(self) -> None:
        """Start resource monitoring."""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Resource monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        if not self.is_monitoring:
            return

        self.is_monitoring = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Resource monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        last_disk_io = psutil.disk_io_counters()

        while self.is_monitoring:
            try:
                timestamp = time.time()

                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                self.cpu_history.append((timestamp, cpu_percent))

                # Memory usage
                memory = psutil.virtual_memory()
                self.memory_history.append((timestamp, memory.percent))

                # Disk I/O
                current_disk_io = psutil.disk_io_counters()
                if last_disk_io:
                    read_bytes = current_disk_io.read_bytes - last_disk_io.read_bytes
                    write_bytes = current_disk_io.write_bytes - last_disk_io.write_bytes
                    read_mbps = read_bytes / (1024 * 1024 * self.monitoring_interval)
                    write_mbps = write_bytes / (1024 * 1024 * self.monitoring_interval)
                    self.disk_history.append((timestamp, read_mbps, write_mbps))

                last_disk_io = current_disk_io

                # Keep only recent history (last 24 hours)
                cutoff_time = timestamp - 86400
                self.cpu_history = [(t, v) for t, v in self.cpu_history if t > cutoff_time]
                self.memory_history = [(t, v) for t, v in self.memory_history if t > cutoff_time]
                self.disk_history = [(t, r, w) for t, r, w in self.disk_history if t > cutoff_time]

                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(self.monitoring_interval)

    def get_resource_summary(self, hours: int = 1) -> Dict[str, any]:
        """
        Get resource usage summary for the specified time period.

        Args:
            hours: Number of hours of history to analyze

        Returns:
            Resource usage summary
        """
        cutoff_time = time.time() - (hours * 3600)

        # Filter recent data
        recent_cpu = [(t, v) for t, v in self.cpu_history if t > cutoff_time]
        recent_memory = [(t, v) for t, v in self.memory_history if t > cutoff_time]
        recent_disk = [(t, r, w) for t, r, w in self.disk_history if t > cutoff_time]

        summary = {
            'cpu': {
                'current': recent_cpu[-1][1] if recent_cpu else 0,
                'avg': sum(v for _, v in recent_cpu) / len(recent_cpu) if recent_cpu else 0,
                'max': max(v for _, v in recent_cpu) if recent_cpu else 0,
                'min': min(v for _, v in recent_cpu) if recent_cpu else 0
            },
            'memory': {
                'current': recent_memory[-1][1] if recent_memory else 0,
                'avg': sum(v for _, v in recent_memory) / len(recent_memory) if recent_memory else 0,
                'max': max(v for _, v in recent_memory) if recent_memory else 0,
                'min': min(v for _, v in recent_memory) if recent_memory else 0
            },
            'disk_io': {
                'read_mbps': {
                    'current': recent_disk[-1][1] if recent_disk else 0,
                    'avg': sum(r for _, r, w in recent_disk) / len(recent_disk) if recent_disk else 0,
                    'max': max(r for _, r, w in recent_disk) if recent_disk else 0
                },
                'write_mbps': {
                    'current': recent_disk[-1][2] if recent_disk else 0,
                    'avg': sum(w for _, r, w in recent_disk) / len(recent_disk) if recent_disk else 0,
                    'max': max(w for _, r, w in recent_disk) if recent_disk else 0
                }
            }
        }

        return summary
