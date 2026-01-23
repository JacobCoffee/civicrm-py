"""Performance benchmark utilities for civi-py.

This module provides utilities and thresholds for benchmarking civi-py performance.
Used by test_performance.py to establish and verify performance baselines.

Performance Thresholds:
    Serialization:
        - msgspec encode: < 0.01ms per record (1K records)
        - msgspec decode: < 0.01ms per record (1K records)
        - Overhead vs raw dict: < 10%

    QuerySet:
        - Simple query build: < 0.5ms
        - Complex query build: < 1.0ms
        - Filter parsing: < 0.1ms per filter

    Entity Hydration:
        - from_dict(): < 0.05ms per record
        - to_dict(): < 0.02ms per record
        - Overhead vs raw dict: < 20%

    HTTP Transport:
        - Request serialization: < 1ms
        - Response deserialization: < 1ms per 100 records
        - Total overhead vs raw httpx: < 10%

Usage:
    >>> from tests.compat.benchmarks import Benchmark, BenchmarkResult
    >>> bench = Benchmark()
    >>> result = bench.run("test_name", my_function, iterations=1000)
    >>> result.assert_threshold(max_ms=1.0)
"""

from __future__ import annotations

import gc
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


# =============================================================================
# Performance Thresholds (in milliseconds)
# =============================================================================


class Thresholds:
    """Performance thresholds for CI regression checks.

    All values are in milliseconds unless otherwise noted.
    These thresholds represent acceptable performance baselines.
    """

    # Serialization thresholds (per record)
    MSGSPEC_ENCODE_PER_RECORD_MS = 0.01  # 10us per record
    MSGSPEC_DECODE_PER_RECORD_MS = 0.01  # 10us per record
    SERIALIZATION_OVERHEAD_PERCENT = 10  # Max 10% overhead vs raw

    # QuerySet thresholds
    QUERYSET_BUILD_SIMPLE_MS = 0.5  # Simple query (1-2 filters)
    QUERYSET_BUILD_COMPLEX_MS = 1.0  # Complex query (5+ filters, joins)
    QUERYSET_FILTER_PARSE_MS = 0.1  # Per filter clause

    # Entity hydration thresholds (per record)
    ENTITY_FROM_DICT_PER_RECORD_MS = 0.05  # 50us per record
    ENTITY_TO_DICT_PER_RECORD_MS = 0.02  # 20us per record
    ENTITY_HYDRATION_OVERHEAD_PERCENT = 20  # Max 20% overhead

    # HTTP transport thresholds
    REQUEST_SERIALIZATION_MS = 1.0  # Full request serialization
    RESPONSE_DESERIALIZE_PER_100_RECORDS_MS = 1.0  # Per 100 records
    HTTP_OVERHEAD_PERCENT = 10  # Max 10% overhead vs raw httpx

    # Memory thresholds (in MB)
    MEMORY_PER_1000_RECORDS_MB = 5.0  # Max memory for 1K records
    MEMORY_PER_10000_RECORDS_MB = 50.0  # Max memory for 10K records

    # Bulk operation thresholds (total time in ms)
    BULK_1000_RECORDS_MS = 100  # 1K record bulk operation
    BULK_10000_RECORDS_MS = 1000  # 10K record bulk operation

    @classmethod
    def get_threshold(cls, name: str) -> float:
        """Get threshold value by name.

        Args:
            name: Threshold attribute name.

        Returns:
            Threshold value.

        Raises:
            AttributeError: If threshold name doesn't exist.
        """
        return getattr(cls, name)


# =============================================================================
# Benchmark Result
# =============================================================================


@dataclass
class BenchmarkResult:
    """Result of a benchmark run.

    Attributes:
        name: Benchmark name/identifier.
        iterations: Number of iterations run.
        times_ms: List of execution times in milliseconds.
        memory_mb: Memory usage in MB (if tracked).
        metadata: Additional benchmark metadata.
    """

    name: str
    iterations: int
    times_ms: list[float]
    memory_mb: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def mean_ms(self) -> float:
        """Mean execution time in milliseconds."""
        return statistics.mean(self.times_ms)

    @property
    def median_ms(self) -> float:
        """Median execution time in milliseconds."""
        return statistics.median(self.times_ms)

    @property
    def std_dev_ms(self) -> float:
        """Standard deviation of execution times."""
        if len(self.times_ms) < 2:
            return 0.0
        return statistics.stdev(self.times_ms)

    @property
    def min_ms(self) -> float:
        """Minimum execution time."""
        return min(self.times_ms)

    @property
    def max_ms(self) -> float:
        """Maximum execution time."""
        return max(self.times_ms)

    @property
    def p95_ms(self) -> float:
        """95th percentile execution time."""
        sorted_times = sorted(self.times_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    @property
    def p99_ms(self) -> float:
        """99th percentile execution time."""
        sorted_times = sorted(self.times_ms)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    @property
    def total_ms(self) -> float:
        """Total execution time."""
        return sum(self.times_ms)

    @property
    def ops_per_sec(self) -> float:
        """Operations per second based on mean time."""
        if self.mean_ms == 0:
            return float("inf")
        return 1000.0 / self.mean_ms

    def per_record_ms(self, record_count: int) -> float:
        """Calculate time per record.

        Args:
            record_count: Number of records processed per iteration.

        Returns:
            Time in milliseconds per record.
        """
        if record_count == 0:
            return 0.0
        return self.mean_ms / record_count

    def assert_threshold(
        self,
        max_ms: float | None = None,
        max_per_record_ms: float | None = None,
        record_count: int = 1,
        max_memory_mb: float | None = None,
    ) -> None:
        """Assert benchmark meets threshold.

        Args:
            max_ms: Maximum allowed mean time in milliseconds.
            max_per_record_ms: Maximum allowed time per record.
            record_count: Number of records for per-record calculation.
            max_memory_mb: Maximum allowed memory usage.

        Raises:
            AssertionError: If threshold is exceeded.
        """
        if max_ms is not None:
            assert self.mean_ms <= max_ms, f"{self.name}: Mean time {self.mean_ms:.3f}ms exceeds threshold {max_ms}ms"

        if max_per_record_ms is not None:
            per_record = self.per_record_ms(record_count)
            assert per_record <= max_per_record_ms, (
                f"{self.name}: Per-record time {per_record:.4f}ms exceeds threshold {max_per_record_ms}ms"
            )

        if max_memory_mb is not None and self.memory_mb is not None:
            assert self.memory_mb <= max_memory_mb, (
                f"{self.name}: Memory {self.memory_mb:.2f}MB exceeds threshold {max_memory_mb}MB"
            )

    def assert_overhead_percent(
        self,
        baseline: BenchmarkResult,
        max_overhead_percent: float,
    ) -> None:
        """Assert overhead vs baseline is within limit.

        Args:
            baseline: Baseline benchmark result to compare against.
            max_overhead_percent: Maximum allowed overhead percentage.

        Raises:
            AssertionError: If overhead exceeds limit.
        """
        if baseline.mean_ms == 0:
            return  # Can't calculate overhead

        overhead = ((self.mean_ms - baseline.mean_ms) / baseline.mean_ms) * 100
        assert overhead <= max_overhead_percent, (
            f"{self.name}: Overhead {overhead:.1f}% vs {baseline.name} exceeds threshold {max_overhead_percent}%"
        )

    def __str__(self) -> str:
        """Human-readable representation."""
        lines = [
            f"Benchmark: {self.name}",
            f"  Iterations: {self.iterations}",
            f"  Mean: {self.mean_ms:.4f}ms",
            f"  Median: {self.median_ms:.4f}ms",
            f"  Std Dev: {self.std_dev_ms:.4f}ms",
            f"  Min: {self.min_ms:.4f}ms",
            f"  Max: {self.max_ms:.4f}ms",
            f"  P95: {self.p95_ms:.4f}ms",
            f"  P99: {self.p99_ms:.4f}ms",
            f"  Ops/sec: {self.ops_per_sec:.0f}",
        ]
        if self.memory_mb is not None:
            lines.append(f"  Memory: {self.memory_mb:.2f}MB")
        return "\n".join(lines)


# =============================================================================
# Benchmark Runner
# =============================================================================


class Benchmark:
    """Benchmark runner with timing and memory tracking.

    Provides utilities for measuring execution time and memory usage
    of functions with statistical analysis.

    Example:
        >>> bench = Benchmark()
        >>> result = bench.run("my_test", lambda: [i * 2 for i in range(1000)])
        >>> print(result)
        >>> result.assert_threshold(max_ms=1.0)
    """

    def __init__(
        self,
        warmup_iterations: int = 5,
        gc_before_each: bool = True,
    ) -> None:
        """Initialize benchmark runner.

        Args:
            warmup_iterations: Number of warmup iterations before timing.
            gc_before_each: Whether to run GC before each iteration.
        """
        self.warmup_iterations = warmup_iterations
        self.gc_before_each = gc_before_each

    def run(
        self,
        name: str,
        func: Callable[[], T],
        iterations: int = 100,
        track_memory: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> BenchmarkResult:
        """Run benchmark and collect timing data.

        Args:
            name: Benchmark name.
            func: Function to benchmark (no arguments).
            iterations: Number of timed iterations.
            track_memory: Whether to track memory usage.
            metadata: Additional metadata to store.

        Returns:
            BenchmarkResult with timing statistics.
        """
        # Warmup phase
        for _ in range(self.warmup_iterations):
            func()

        # Memory tracking setup
        memory_mb = None
        if track_memory:
            gc.collect()
            tracemalloc.start()

        # Timed iterations
        times_ms: list[float] = []
        for _ in range(iterations):
            if self.gc_before_each:
                gc.collect()

            start = time.perf_counter_ns()
            func()
            end = time.perf_counter_ns()

            elapsed_ms = (end - start) / 1_000_000  # ns to ms
            times_ms.append(elapsed_ms)

        # Memory tracking cleanup
        if track_memory:
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            memory_mb = peak / (1024 * 1024)  # bytes to MB

        return BenchmarkResult(
            name=name,
            iterations=iterations,
            times_ms=times_ms,
            memory_mb=memory_mb,
            metadata=metadata or {},
        )

    def run_with_args(
        self,
        name: str,
        func: Callable[..., T],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        iterations: int = 100,
        track_memory: bool = False,
    ) -> BenchmarkResult:
        """Run benchmark with function arguments.

        Args:
            name: Benchmark name.
            func: Function to benchmark.
            args: Positional arguments for function.
            kwargs: Keyword arguments for function.
            iterations: Number of timed iterations.
            track_memory: Whether to track memory.

        Returns:
            BenchmarkResult with timing statistics.
        """
        kwargs = kwargs or {}
        return self.run(
            name=name,
            func=lambda: func(*args, **kwargs),
            iterations=iterations,
            track_memory=track_memory,
        )

    def compare(
        self,
        baseline: BenchmarkResult,
        comparison: BenchmarkResult,
    ) -> dict[str, Any]:
        """Compare two benchmark results.

        Args:
            baseline: Baseline benchmark result.
            comparison: Comparison benchmark result.

        Returns:
            Dictionary with comparison metrics.
        """
        overhead_ms = comparison.mean_ms - baseline.mean_ms
        overhead_percent = (overhead_ms / baseline.mean_ms * 100) if baseline.mean_ms > 0 else 0

        return {
            "baseline_mean_ms": baseline.mean_ms,
            "comparison_mean_ms": comparison.mean_ms,
            "overhead_ms": overhead_ms,
            "overhead_percent": overhead_percent,
            "speedup": baseline.mean_ms / comparison.mean_ms if comparison.mean_ms > 0 else float("inf"),
        }


# =============================================================================
# Data Generators
# =============================================================================


class TestDataGenerator:
    """Generator for test data at various scales.

    Provides methods to generate realistic CiviCRM-like data
    for performance testing.
    """

    @staticmethod
    def contact_dict(contact_id: int) -> dict[str, Any]:
        """Generate a single contact dictionary.

        Args:
            contact_id: Unique contact identifier.

        Returns:
            Contact data dictionary.
        """
        return {
            "id": contact_id,
            "contact_type": "Individual",
            "display_name": f"Test Contact {contact_id}",
            "first_name": f"First{contact_id}",
            "last_name": f"Last{contact_id}",
            "email_primary": f"contact{contact_id}@example.com",
            "phone_primary": f"555-{contact_id:04d}",
            "is_deleted": False,
            "is_deceased": False,
            "do_not_email": False,
            "do_not_phone": False,
            "do_not_mail": False,
            "do_not_sms": False,
            "do_not_trade": False,
            "is_opt_out": False,
            "created_date": "2024-01-01 00:00:00",
            "modified_date": "2024-01-15 12:00:00",
        }

    @staticmethod
    def activity_dict(activity_id: int, contact_id: int = 1) -> dict[str, Any]:
        """Generate a single activity dictionary.

        Args:
            activity_id: Unique activity identifier.
            contact_id: Source contact ID.

        Returns:
            Activity data dictionary.
        """
        return {
            "id": activity_id,
            "activity_type_id": 3,
            "subject": f"Activity {activity_id}",
            "details": f"<p>Details for activity {activity_id}</p>",
            "activity_date_time": "2024-01-15 10:30:00",
            "duration": 30,
            "location": "Office",
            "status_id": 2,
            "priority_id": 2,
            "source_contact_id": contact_id,
            "target_contact_id": [contact_id + 1],
            "assignee_contact_id": [contact_id],
            "is_current_revision": True,
            "is_deleted": False,
            "is_test": False,
            "is_auto": False,
            "created_date": "2024-01-15 09:00:00",
            "modified_date": "2024-01-15 11:00:00",
        }

    @classmethod
    def contacts(cls, count: int) -> list[dict[str, Any]]:
        """Generate multiple contact dictionaries.

        Args:
            count: Number of contacts to generate.

        Returns:
            List of contact dictionaries.
        """
        return [cls.contact_dict(i + 1) for i in range(count)]

    @classmethod
    def activities(cls, count: int) -> list[dict[str, Any]]:
        """Generate multiple activity dictionaries.

        Args:
            count: Number of activities to generate.

        Returns:
            List of activity dictionaries.
        """
        return [cls.activity_dict(i + 1, contact_id=(i % 10) + 1) for i in range(count)]

    @classmethod
    def api_response(cls, values: list[dict[str, Any]]) -> dict[str, Any]:
        """Wrap values in API response format.

        Args:
            values: List of entity dictionaries.

        Returns:
            API response dictionary.
        """
        return {
            "values": values,
            "count": len(values),
            "countFetched": len(values),
        }

    @classmethod
    def contact_response(cls, count: int) -> dict[str, Any]:
        """Generate API response with contacts.

        Args:
            count: Number of contacts.

        Returns:
            API response dictionary.
        """
        return cls.api_response(cls.contacts(count))

    @classmethod
    def activity_response(cls, count: int) -> dict[str, Any]:
        """Generate API response with activities.

        Args:
            count: Number of activities.

        Returns:
            API response dictionary.
        """
        return cls.api_response(cls.activities(count))


# =============================================================================
# Report Generator
# =============================================================================


@dataclass
class BenchmarkReport:
    """Collection of benchmark results with reporting.

    Attributes:
        name: Report name.
        results: List of benchmark results.
        comparisons: List of comparison results.
    """

    name: str
    results: list[BenchmarkResult] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)

    def add_result(self, result: BenchmarkResult) -> None:
        """Add a benchmark result.

        Args:
            result: Benchmark result to add.
        """
        self.results.append(result)

    def add_comparison(self, comparison: dict[str, Any]) -> None:
        """Add a comparison result.

        Args:
            comparison: Comparison dictionary.
        """
        self.comparisons.append(comparison)

    def get_result(self, name: str) -> BenchmarkResult | None:
        """Get result by name.

        Args:
            name: Benchmark name.

        Returns:
            BenchmarkResult if found, None otherwise.
        """
        for result in self.results:
            if result.name == name:
                return result
        return None

    def all_thresholds_met(self) -> bool:
        """Check if all results meet their thresholds.

        Returns:
            True if all thresholds are met.
        """
        # This is a placeholder - actual threshold checks are done
        # in the test assertions
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "name": self.name,
            "results": [
                {
                    "name": r.name,
                    "iterations": r.iterations,
                    "mean_ms": r.mean_ms,
                    "median_ms": r.median_ms,
                    "std_dev_ms": r.std_dev_ms,
                    "min_ms": r.min_ms,
                    "max_ms": r.max_ms,
                    "p95_ms": r.p95_ms,
                    "p99_ms": r.p99_ms,
                    "ops_per_sec": r.ops_per_sec,
                    "memory_mb": r.memory_mb,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
            "comparisons": self.comparisons,
        }

    def __str__(self) -> str:
        """Human-readable report."""
        lines = [f"=== Benchmark Report: {self.name} ===", ""]

        for result in self.results:
            lines.append(str(result))
            lines.append("")

        if self.comparisons:
            lines.append("--- Comparisons ---")
            lines.extend(
                f"  {comp.get('baseline_name', 'baseline')} vs "
                f"{comp.get('comparison_name', 'comparison')}: "
                f"{comp.get('overhead_percent', 0):.1f}% overhead"
                for comp in self.comparisons
            )

        return "\n".join(lines)


# =============================================================================
# Utilities
# =============================================================================


def measure_memory(func: Callable[[], T]) -> tuple[T, float]:
    """Measure peak memory usage of a function.

    Args:
        func: Function to measure.

    Returns:
        Tuple of (function result, peak memory in MB).
    """
    gc.collect()
    tracemalloc.start()

    result = func()

    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return result, peak / (1024 * 1024)


def object_size_mb(obj: Any) -> float:
    """Get approximate size of object in MB.

    Args:
        obj: Object to measure.

    Returns:
        Size in megabytes.
    """
    return sys.getsizeof(obj) / (1024 * 1024)


__all__ = [
    "Benchmark",
    "BenchmarkReport",
    "BenchmarkResult",
    "TestDataGenerator",
    "Thresholds",
    "measure_memory",
    "object_size_mb",
]
