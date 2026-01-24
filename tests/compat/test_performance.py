"""Performance benchmark tests for civi-py.

This module contains comprehensive performance benchmarks to establish
and verify performance baselines for civi-py operations.

Benchmarks:
    1. Serialization: msgspec encode/decode performance
    2. QuerySet: Query building overhead
    3. Entity Hydration: from_dict()/to_dict() performance
    4. HTTP Transport: Request/response serialization overhead
    5. Bulk Operations: Large dataset handling
    6. Memory Usage: Memory consumption for large result sets

Usage:
    # Run all performance tests
    pytest tests/compat/test_performance.py -v

    # Run only benchmark tests
    pytest tests/compat/test_performance.py -m benchmark

    # Run with timing output
    pytest tests/compat/test_performance.py -v --tb=short

    # Run excluding slow tests
    pytest tests/compat/test_performance.py -m "benchmark and not slow"

Environment Variables:
    CIVI_BENCHMARK_ITERATIONS: Override default iteration count
    CIVI_BENCHMARK_VERBOSE: Print detailed benchmark output
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import httpx
import msgspec
import pytest

from tests.compat.benchmarks import (
    Benchmark,
    BenchmarkReport,
    TestDataGenerator,
    Thresholds,
    measure_memory,
)

if TYPE_CHECKING:
    from civicrm_py import CiviClient, CiviSettings

# Skip all tests if running in minimal CI mode
pytestmark = [
    pytest.mark.benchmark,
]

# Configuration from environment
ITERATIONS = int(os.environ.get("CIVI_BENCHMARK_ITERATIONS", "100"))
VERBOSE = os.environ.get("CIVI_BENCHMARK_VERBOSE", "").lower() in ("1", "true", "yes")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bench() -> Benchmark:
    """Benchmark runner fixture."""
    return Benchmark(warmup_iterations=5, gc_before_each=True)


@pytest.fixture
def report() -> BenchmarkReport:
    """Benchmark report fixture."""
    return BenchmarkReport(name="civi-py Performance")


@pytest.fixture
def small_contacts() -> list[dict[str, Any]]:
    """Small set of contacts (10 records)."""
    return TestDataGenerator.contacts(10)


@pytest.fixture
def medium_contacts() -> list[dict[str, Any]]:
    """Medium set of contacts (100 records)."""
    return TestDataGenerator.contacts(100)


@pytest.fixture
def large_contacts() -> list[dict[str, Any]]:
    """Large set of contacts (1000 records)."""
    return TestDataGenerator.contacts(1000)


@pytest.fixture
def xlarge_contacts() -> list[dict[str, Any]]:
    """Extra large set of contacts (10000 records)."""
    return TestDataGenerator.contacts(10000)


# =============================================================================
# Serialization Benchmarks
# =============================================================================


class TestSerializationPerformance:
    """Benchmarks for msgspec serialization performance."""

    def test_msgspec_encode_single_record(self, bench: Benchmark) -> None:
        """Benchmark msgspec encoding of single record."""
        from civicrm_py.core.serialization import APIRequest

        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=25,
        )

        result = bench.run(
            "msgspec_encode_single",
            lambda: msgspec.json.encode(msgspec.structs.asdict(request)),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        # Single record encode should be very fast
        result.assert_threshold(max_ms=0.1)

    def test_msgspec_encode_small_response(
        self,
        bench: Benchmark,
        small_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec encoding of small response (10 records)."""
        response = TestDataGenerator.api_response(small_contacts)

        result = bench.run(
            "msgspec_encode_10_records",
            lambda: msgspec.json.encode(response),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        # 10 records should encode quickly
        result.assert_threshold(max_ms=0.5)

    def test_msgspec_encode_medium_response(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec encoding of medium response (100 records)."""
        response = TestDataGenerator.api_response(medium_contacts)

        result = bench.run(
            "msgspec_encode_100_records",
            lambda: msgspec.json.encode(response),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_ENCODE_PER_RECORD_MS,
            record_count=100,
        )

    def test_msgspec_encode_large_response(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec encoding of large response (1000 records)."""
        response = TestDataGenerator.api_response(large_contacts)

        result = bench.run(
            "msgspec_encode_1000_records",
            lambda: msgspec.json.encode(response),
            iterations=ITERATIONS // 2,  # Fewer iterations for large data
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_ENCODE_PER_RECORD_MS,
            record_count=1000,
        )

    @pytest.mark.slow
    def test_msgspec_encode_xlarge_response(
        self,
        bench: Benchmark,
        xlarge_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec encoding of extra large response (10000 records)."""
        response = TestDataGenerator.api_response(xlarge_contacts)

        result = bench.run(
            "msgspec_encode_10000_records",
            lambda: msgspec.json.encode(response),
            iterations=10,  # Minimal iterations for very large data
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_ENCODE_PER_RECORD_MS,
            record_count=10000,
        )

    def test_msgspec_decode_single_response(self, bench: Benchmark) -> None:
        """Benchmark msgspec decoding of single record response."""
        response = TestDataGenerator.contact_response(1)
        encoded = msgspec.json.encode(response)

        result = bench.run(
            "msgspec_decode_single",
            lambda: msgspec.json.decode(encoded),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=0.1)

    def test_msgspec_decode_medium_response(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec decoding of medium response (100 records)."""
        response = TestDataGenerator.api_response(medium_contacts)
        encoded = msgspec.json.encode(response)

        result = bench.run(
            "msgspec_decode_100_records",
            lambda: msgspec.json.decode(encoded),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_DECODE_PER_RECORD_MS,
            record_count=100,
        )

    def test_msgspec_decode_large_response(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark msgspec decoding of large response (1000 records)."""
        response = TestDataGenerator.api_response(large_contacts)
        encoded = msgspec.json.encode(response)

        result = bench.run(
            "msgspec_decode_1000_records",
            lambda: msgspec.json.decode(encoded),
            iterations=ITERATIONS // 2,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_DECODE_PER_RECORD_MS,
            record_count=1000,
        )

    def test_msgspec_vs_json_comparison(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Compare msgspec performance vs stdlib json."""
        response = TestDataGenerator.api_response(medium_contacts)
        encoded_bytes = msgspec.json.encode(response)
        encoded_str = encoded_bytes.decode()

        # Benchmark msgspec
        msgspec_result = bench.run(
            "msgspec_decode",
            lambda: msgspec.json.decode(encoded_bytes),
            iterations=ITERATIONS,
        )

        # Benchmark stdlib json
        json_result = bench.run(
            "json_decode",
            lambda: json.loads(encoded_str),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(f"\nmsgspec: {msgspec_result.mean_ms:.4f}ms")
            print(f"json: {json_result.mean_ms:.4f}ms")
            print(f"Speedup: {json_result.mean_ms / msgspec_result.mean_ms:.2f}x")

        # msgspec should be faster than stdlib json
        assert msgspec_result.mean_ms < json_result.mean_ms, "msgspec should be faster than stdlib json"


# =============================================================================
# QuerySet Building Benchmarks
# =============================================================================


class TestQuerySetPerformance:
    """Benchmarks for QuerySet building operations."""

    def test_queryset_simple_filter(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Benchmark simple QuerySet filter building."""
        from civicrm_py.query.queryset import QuerySet

        qs = QuerySet(civi_client, "Contact")

        result = bench.run(
            "queryset_simple_filter",
            lambda: qs.filter(is_deleted=False).select("id", "display_name"),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.QUERYSET_BUILD_SIMPLE_MS)

    def test_queryset_multiple_filters(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Benchmark QuerySet with multiple filters."""
        from civicrm_py.query.queryset import QuerySet

        qs = QuerySet(civi_client, "Contact")

        def build_query() -> Any:
            return (
                qs.filter(is_deleted=False)
                .filter(contact_type="Individual")
                .filter(first_name__contains="John")
                .select("id", "display_name", "email_primary")
                .order_by("-created_date")
                .limit(25)
            )

        result = bench.run(
            "queryset_multiple_filters",
            build_query,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.QUERYSET_BUILD_SIMPLE_MS)

    def test_queryset_complex_query(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Benchmark complex QuerySet with joins and grouping."""
        from civicrm_py.query.queryset import QuerySet

        qs = QuerySet(civi_client, "Contact")

        def build_complex_query() -> Any:
            return (
                qs.filter(is_deleted=False)
                .filter(contact_type="Individual")
                .filter(first_name__contains="John")
                .filter(email_primary__isnull=False)
                .filter(created_date__gte="2024-01-01")
                .exclude(is_deceased=True)
                .select("id", "display_name", "email_primary", "phone_primary")
                .order_by("-created_date", "last_name")
                .limit(100)
                .offset(0)
            )

        result = bench.run(
            "queryset_complex_query",
            build_complex_query,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.QUERYSET_BUILD_COMPLEX_MS)

    def test_queryset_build_params(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Benchmark QuerySet._build_params() method."""
        from civicrm_py.query.queryset import QuerySet

        qs = (
            QuerySet(civi_client, "Contact")
            .filter(is_deleted=False, contact_type="Individual")
            .select("id", "display_name")
            .order_by("-created_date")
            .limit(25)
        )

        result = bench.run(
            "queryset_build_params",
            lambda: qs._build_params(),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        # Building params should be very fast
        result.assert_threshold(max_ms=0.5)

    def test_queryset_filter_parsing(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Benchmark QuerySet filter lookup parsing."""
        from civicrm_py.query.queryset import QuerySet

        qs = QuerySet(civi_client, "Contact")

        # Test various lookup types
        lookups = [
            ("name", "John"),
            ("name__contains", "John"),
            ("age__gt", 21),
            ("age__gte", 18),
            ("age__lt", 65),
            ("age__lte", 100),
            ("status__in", [1, 2, 3]),
            ("email__isnull", False),
            ("title__startswith", "Mr"),
            ("title__endswith", "PhD"),
        ]

        def parse_all_lookups() -> list[Any]:
            results = []
            for key, value in lookups:
                results.append(qs._parse_lookup(key, value))
            return results

        result = bench.run(
            "queryset_filter_parsing",
            parse_all_lookups,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        # Parsing 10 filters should be quick
        per_filter = result.per_record_ms(len(lookups))
        assert per_filter < Thresholds.QUERYSET_FILTER_PARSE_MS, (
            f"Filter parsing {per_filter:.4f}ms exceeds threshold {Thresholds.QUERYSET_FILTER_PARSE_MS}ms"
        )


# =============================================================================
# Entity Hydration Benchmarks
# =============================================================================


class TestEntityHydrationPerformance:
    """Benchmarks for entity hydration (from_dict/to_dict)."""

    def test_contact_from_dict_single(self, bench: Benchmark) -> None:
        """Benchmark Contact.from_dict() for single record."""
        from civicrm_py.entities import Contact

        contact_data = TestDataGenerator.contact_dict(1)

        result = bench.run(
            "contact_from_dict_single",
            lambda: Contact.from_dict(contact_data),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.ENTITY_FROM_DICT_PER_RECORD_MS)

    def test_contact_from_dict_medium(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark Contact.from_dict() for 100 records."""
        from civicrm_py.entities import Contact

        def hydrate_all() -> list[Contact]:
            return [Contact.from_dict(c) for c in medium_contacts]

        result = bench.run(
            "contact_from_dict_100",
            hydrate_all,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_FROM_DICT_PER_RECORD_MS,
            record_count=100,
        )

    def test_contact_from_dict_large(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark Contact.from_dict() for 1000 records."""
        from civicrm_py.entities import Contact

        def hydrate_all() -> list[Contact]:
            return [Contact.from_dict(c) for c in large_contacts]

        result = bench.run(
            "contact_from_dict_1000",
            hydrate_all,
            iterations=ITERATIONS // 2,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_FROM_DICT_PER_RECORD_MS,
            record_count=1000,
        )

    def test_contact_to_dict_single(self, bench: Benchmark) -> None:
        """Benchmark Contact.to_dict() for single record."""
        from civicrm_py.entities import Contact

        contact_data = TestDataGenerator.contact_dict(1)
        contact = Contact.from_dict(contact_data)

        result = bench.run(
            "contact_to_dict_single",
            lambda: contact.to_dict(),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.ENTITY_TO_DICT_PER_RECORD_MS)

    def test_contact_to_dict_large(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark Contact.to_dict() for 1000 records."""
        from civicrm_py.entities import Contact

        contacts = [Contact.from_dict(c) for c in large_contacts]

        def serialize_all() -> list[dict[str, Any]]:
            return [c.to_dict() for c in contacts]

        result = bench.run(
            "contact_to_dict_1000",
            serialize_all,
            iterations=ITERATIONS // 2,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_TO_DICT_PER_RECORD_MS,
            record_count=1000,
        )

    def test_dirty_tracking_overhead(self, bench: Benchmark) -> None:
        """Measure overhead of dirty field tracking."""
        from civicrm_py.entities import Contact

        contact_data = TestDataGenerator.contact_dict(1)

        # Baseline: create without modifications
        baseline_result = bench.run(
            "dirty_tracking_baseline",
            lambda: Contact.from_dict(contact_data),
            iterations=ITERATIONS,
        )

        # With modifications
        def create_and_modify() -> Contact:
            contact = Contact.from_dict(contact_data)
            contact.first_name = "Modified"
            contact.last_name = "Name"
            return contact

        modified_result = bench.run(
            "dirty_tracking_modified",
            create_and_modify,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(f"\nBaseline: {baseline_result.mean_ms:.4f}ms")
            print(f"With modifications: {modified_result.mean_ms:.4f}ms")

        # Dirty tracking overhead should be minimal
        modified_result.assert_overhead_percent(
            baseline_result,
            max_overhead_percent=50,  # Allow up to 50% overhead for modifications
        )

    def test_entity_vs_raw_dict_comparison(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Compare entity hydration vs raw dict operations."""
        from civicrm_py.entities import Contact

        # Baseline: just iterate dicts
        baseline_result = bench.run(
            "raw_dict_iterate",
            lambda: [c["id"] for c in medium_contacts],
            iterations=ITERATIONS,
        )

        # Entity hydration
        hydration_result = bench.run(
            "entity_hydration",
            lambda: [Contact.from_dict(c) for c in medium_contacts],
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(f"\nRaw dict: {baseline_result.mean_ms:.4f}ms")
            print(f"Entity hydration: {hydration_result.mean_ms:.4f}ms")

        # Entity hydration will always have some overhead, but should be reasonable
        # We just ensure it's within the per-record threshold
        hydration_result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_FROM_DICT_PER_RECORD_MS,
            record_count=100,
        )


# =============================================================================
# HTTP Transport Benchmarks
# =============================================================================


class TestHTTPTransportPerformance:
    """Benchmarks for HTTP transport layer overhead."""

    def test_request_serialization(
        self,
        bench: Benchmark,
        civi_settings: CiviSettings,
    ) -> None:
        """Benchmark API request serialization."""
        from civicrm_py.core.auth import AuthProvider
        from civicrm_py.core.serialization import APIRequest
        from civicrm_py.http.transport import BaseTransport

        auth = AuthProvider.from_settings(civi_settings)
        transport = BaseTransport(civi_settings, auth)

        params = APIRequest(
            select=["id", "display_name", "email_primary"],
            where=[["is_deleted", "=", False], ["contact_type", "=", "Individual"]],
            orderBy={"created_date": "DESC"},
            limit=25,
        )

        def serialize_request() -> tuple[str, dict[str, str], dict[str, str]]:
            url = transport._build_url("Contact", "get")
            headers = transport._build_headers()
            data = transport._build_request_data(
                {k: v for k, v in msgspec.structs.asdict(params).items() if v is not None},
            )
            return url, headers, data

        result = bench.run(
            "request_serialization",
            serialize_request,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(max_ms=Thresholds.REQUEST_SERIALIZATION_MS)

    def test_response_deserialization(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark API response deserialization."""
        from civicrm_py.core.serialization import decode_response

        response = TestDataGenerator.api_response(medium_contacts)
        encoded = msgspec.json.encode(response)

        result = bench.run(
            "response_deserialization_100",
            lambda: decode_response(encoded),
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_ms=Thresholds.RESPONSE_DESERIALIZE_PER_100_RECORDS_MS,
        )

    def test_response_deserialization_large(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark large API response deserialization (1000 records)."""
        from civicrm_py.core.serialization import decode_response

        response = TestDataGenerator.api_response(large_contacts)
        encoded = msgspec.json.encode(response)

        result = bench.run(
            "response_deserialization_1000",
            lambda: decode_response(encoded),
            iterations=ITERATIONS // 2,
        )

        if VERBOSE:
            print(result)

        # Scale threshold for 1000 records
        max_ms = Thresholds.RESPONSE_DESERIALIZE_PER_100_RECORDS_MS * 10
        result.assert_threshold(max_ms=max_ms)

    async def test_transport_vs_raw_httpx(
        self,
        bench: Benchmark,
        civi_settings: CiviSettings,
    ) -> None:
        """Compare CiviClient transport vs raw httpx (mocked)."""
        from civicrm_py.core.auth import AuthProvider
        from civicrm_py.core.serialization import APIRequest, to_dict
        from civicrm_py.http.transport import AsyncTransport

        # Create test response
        response_data = TestDataGenerator.contact_response(10)
        response_bytes = msgspec.json.encode(response_data)

        # Mock httpx response
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = response_bytes

        auth = AuthProvider.from_settings(civi_settings)
        transport = AsyncTransport(civi_settings, auth)

        params = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=10,
        )

        # We can't easily benchmark async without running event loop,
        # so benchmark the serialization components synchronously

        def transport_overhead() -> tuple[str, dict[str, str], dict[str, str]]:
            url = transport._build_url("Contact", "get")
            headers = transport._build_headers()
            body = to_dict(params)
            data = transport._build_request_data(body)
            return url, headers, data

        def raw_httpx_prep() -> tuple[str, dict[str, str], dict[str, str]]:
            url = f"{civi_settings.base_url}/Contact/get"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = {"params": json.dumps({"select": ["id"], "limit": 10})}
            return url, headers, data

        transport_result = bench.run(
            "transport_serialization",
            transport_overhead,
            iterations=ITERATIONS,
        )

        raw_result = bench.run(
            "raw_httpx_prep",
            raw_httpx_prep,
            iterations=ITERATIONS,
        )

        if VERBOSE:
            print(f"\nTransport: {transport_result.mean_ms:.4f}ms")
            print(f"Raw httpx: {raw_result.mean_ms:.4f}ms")

        # Transport overhead includes auth headers and msgspec serialization
        # This is expected to have more overhead than raw httpx prep
        # We just verify both operations complete in reasonable time
        transport_result.assert_threshold(max_ms=Thresholds.REQUEST_SERIALIZATION_MS)
        raw_result.assert_threshold(max_ms=Thresholds.REQUEST_SERIALIZATION_MS)


# =============================================================================
# Bulk Operation Benchmarks
# =============================================================================


class TestBulkOperationsPerformance:
    """Benchmarks for bulk operations with large datasets."""

    @pytest.mark.slow
    def test_bulk_entity_creation_1000(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark creating 1000 entity instances."""
        from civicrm_py.entities import Contact

        result = bench.run(
            "bulk_entity_creation_1000",
            lambda: [Contact.from_dict(c) for c in large_contacts],
            iterations=20,
            track_memory=True,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_ms=Thresholds.BULK_1000_RECORDS_MS,
            max_memory_mb=Thresholds.MEMORY_PER_1000_RECORDS_MB,
        )

    @pytest.mark.slow
    def test_bulk_entity_creation_10000(
        self,
        bench: Benchmark,
        xlarge_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark creating 10000 entity instances."""
        from civicrm_py.entities import Contact

        result = bench.run(
            "bulk_entity_creation_10000",
            lambda: [Contact.from_dict(c) for c in xlarge_contacts],
            iterations=5,
            track_memory=True,
        )

        if VERBOSE:
            print(result)

        result.assert_threshold(
            max_ms=Thresholds.BULK_10000_RECORDS_MS,
            max_memory_mb=Thresholds.MEMORY_PER_10000_RECORDS_MB,
        )

    @pytest.mark.slow
    def test_bulk_serialization_1000(
        self,
        bench: Benchmark,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Benchmark serializing 1000 entities to dict."""
        from civicrm_py.entities import Contact

        contacts = [Contact.from_dict(c) for c in large_contacts]

        result = bench.run(
            "bulk_serialization_1000",
            lambda: [c.to_dict() for c in contacts],
            iterations=20,
        )

        if VERBOSE:
            print(result)

        # Serialization should be faster than hydration
        result.assert_threshold(max_ms=Thresholds.BULK_1000_RECORDS_MS // 2)


# =============================================================================
# Memory Usage Benchmarks
# =============================================================================


class TestMemoryPerformance:
    """Benchmarks for memory usage."""

    def test_memory_contact_list_100(
        self,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Measure memory for 100 Contact instances."""
        from civicrm_py.entities import Contact

        contacts, memory_mb = measure_memory(
            lambda: [Contact.from_dict(c) for c in medium_contacts],
        )

        if VERBOSE:
            print(f"\n100 contacts memory: {memory_mb:.2f}MB")

        assert len(contacts) == 100
        # Memory for 100 contacts should be reasonable
        assert memory_mb < Thresholds.MEMORY_PER_1000_RECORDS_MB

    @pytest.mark.slow
    def test_memory_contact_list_1000(
        self,
        large_contacts: list[dict[str, Any]],
    ) -> None:
        """Measure memory for 1000 Contact instances."""
        from civicrm_py.entities import Contact

        contacts, memory_mb = measure_memory(
            lambda: [Contact.from_dict(c) for c in large_contacts],
        )

        if VERBOSE:
            print(f"\n1000 contacts memory: {memory_mb:.2f}MB")

        assert len(contacts) == 1000
        assert memory_mb < Thresholds.MEMORY_PER_1000_RECORDS_MB

    @pytest.mark.slow
    def test_memory_contact_list_10000(
        self,
        xlarge_contacts: list[dict[str, Any]],
    ) -> None:
        """Measure memory for 10000 Contact instances."""
        from civicrm_py.entities import Contact

        contacts, memory_mb = measure_memory(
            lambda: [Contact.from_dict(c) for c in xlarge_contacts],
        )

        if VERBOSE:
            print(f"\n10000 contacts memory: {memory_mb:.2f}MB")

        assert len(contacts) == 10000
        assert memory_mb < Thresholds.MEMORY_PER_10000_RECORDS_MB

    def test_memory_queryset_chain(self, civi_client: CiviClient) -> None:
        """Measure memory for QuerySet chain operations."""
        from civicrm_py.query.queryset import QuerySet

        def build_chain() -> list[QuerySet]:
            qs = QuerySet(civi_client, "Contact")
            chain = []
            for i in range(100):
                qs = qs.filter(**{f"field_{i}": i})
                chain.append(qs)
            return chain

        chain, memory_mb = measure_memory(build_chain)

        if VERBOSE:
            print(f"\n100 QuerySet chain memory: {memory_mb:.2f}MB")

        assert len(chain) == 100
        # QuerySet chains should have minimal memory overhead
        assert memory_mb < 1.0  # Less than 1MB for 100 chained querysets


# =============================================================================
# Comprehensive Benchmark Report
# =============================================================================


class TestBenchmarkReport:
    """Generate comprehensive benchmark report."""

    @pytest.mark.slow
    def test_generate_full_report(
        self,
        bench: Benchmark,
        report: BenchmarkReport,
        medium_contacts: list[dict[str, Any]],
        large_contacts: list[dict[str, Any]],
        civi_client: CiviClient,
    ) -> None:
        """Generate full benchmark report with all measurements."""
        from civicrm_py.core.serialization import decode_response
        from civicrm_py.entities import Contact
        from civicrm_py.query.queryset import QuerySet

        # Serialization benchmarks
        response = TestDataGenerator.api_response(medium_contacts)
        encoded = msgspec.json.encode(response)

        report.add_result(
            bench.run("encode_100", lambda: msgspec.json.encode(response), iterations=50),
        )
        report.add_result(
            bench.run("decode_100", lambda: msgspec.json.decode(encoded), iterations=50),
        )
        report.add_result(
            bench.run("decode_response_100", lambda: decode_response(encoded), iterations=50),
        )

        # Entity hydration benchmarks
        report.add_result(
            bench.run(
                "hydrate_100",
                lambda: [Contact.from_dict(c) for c in medium_contacts],
                iterations=50,
            ),
        )

        contacts = [Contact.from_dict(c) for c in medium_contacts]
        report.add_result(
            bench.run(
                "serialize_100",
                lambda: [c.to_dict() for c in contacts],
                iterations=50,
            ),
        )

        # QuerySet benchmarks
        qs = QuerySet(civi_client, "Contact")
        report.add_result(
            bench.run(
                "queryset_simple",
                lambda: qs.filter(is_deleted=False).select("id"),
                iterations=50,
            ),
        )
        report.add_result(
            bench.run(
                "queryset_complex",
                lambda: (
                    qs.filter(is_deleted=False, contact_type="Individual")
                    .filter(first_name__contains="John")
                    .select("id", "display_name", "email_primary")
                    .order_by("-created_date")
                    .limit(25)
                ),
                iterations=50,
            ),
        )

        # Memory benchmarks
        _, _memory = measure_memory(
            lambda: [Contact.from_dict(c) for c in large_contacts],
        )
        report.results.append(
            bench.run(
                "memory_1000_contacts",
                lambda: [Contact.from_dict(c) for c in large_contacts],
                iterations=5,
                track_memory=True,
            ),
        )

        if VERBOSE:
            print("\n" + str(report))

        # Verify report is complete
        assert len(report.results) >= 7
        assert all(r.mean_ms > 0 for r in report.results)


# =============================================================================
# CI Threshold Validation
# =============================================================================


class TestCIThresholds:
    """Tests that CI can use for performance regression detection."""

    def test_serialization_thresholds(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Validate serialization meets CI thresholds."""
        response = TestDataGenerator.api_response(medium_contacts)
        encoded = msgspec.json.encode(response)

        # Encode
        encode_result = bench.run(
            "ci_encode",
            lambda: msgspec.json.encode(response),
            iterations=50,
        )
        encode_result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_ENCODE_PER_RECORD_MS * 2,  # 2x margin
            record_count=100,
        )

        # Decode
        decode_result = bench.run(
            "ci_decode",
            lambda: msgspec.json.decode(encoded),
            iterations=50,
        )
        decode_result.assert_threshold(
            max_per_record_ms=Thresholds.MSGSPEC_DECODE_PER_RECORD_MS * 2,
            record_count=100,
        )

    def test_queryset_thresholds(
        self,
        bench: Benchmark,
        civi_client: CiviClient,
    ) -> None:
        """Validate QuerySet building meets CI thresholds."""
        from civicrm_py.query.queryset import QuerySet

        qs = QuerySet(civi_client, "Contact")

        # Simple query
        simple_result = bench.run(
            "ci_queryset_simple",
            lambda: qs.filter(is_deleted=False).select("id"),
            iterations=50,
        )
        simple_result.assert_threshold(
            max_ms=Thresholds.QUERYSET_BUILD_SIMPLE_MS * 2,  # 2x margin for CI variance
        )

        # Complex query
        complex_result = bench.run(
            "ci_queryset_complex",
            lambda: (
                qs.filter(is_deleted=False, contact_type="Individual")
                .filter(first_name__contains="John")
                .exclude(is_deceased=True)
                .select("id", "display_name", "email_primary")
                .order_by("-created_date")
                .limit(25)
            ),
            iterations=50,
        )
        complex_result.assert_threshold(
            max_ms=Thresholds.QUERYSET_BUILD_COMPLEX_MS * 2,
        )

    def test_entity_hydration_thresholds(
        self,
        bench: Benchmark,
        medium_contacts: list[dict[str, Any]],
    ) -> None:
        """Validate entity hydration meets CI thresholds."""
        from civicrm_py.entities import Contact

        # from_dict
        hydrate_result = bench.run(
            "ci_hydrate",
            lambda: [Contact.from_dict(c) for c in medium_contacts],
            iterations=50,
        )
        hydrate_result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_FROM_DICT_PER_RECORD_MS * 2,
            record_count=100,
        )

        # to_dict
        contacts = [Contact.from_dict(c) for c in medium_contacts]
        serialize_result = bench.run(
            "ci_serialize",
            lambda: [c.to_dict() for c in contacts],
            iterations=50,
        )
        serialize_result.assert_threshold(
            max_per_record_ms=Thresholds.ENTITY_TO_DICT_PER_RECORD_MS * 2,
            record_count=100,
        )


__all__ = [
    "TestBenchmarkReport",
    "TestBulkOperationsPerformance",
    "TestCIThresholds",
    "TestEntityHydrationPerformance",
    "TestHTTPTransportPerformance",
    "TestMemoryPerformance",
    "TestQuerySetPerformance",
    "TestSerializationPerformance",
]
