"""Contract tests for CiviCRM API v4 request/response serialization.

These tests verify that:
1. QuerySet.build() output matches expected API request format
2. Response parsing matches expected format exactly
3. Where clause operators map correctly to API v4 syntax
4. Join/select/orderBy translation to API format
5. Error response parsing and exception mapping

Contract tests ensure our library produces valid CiviCRM API v4 requests
and correctly parses API responses.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from civicrm_py.core.serialization import (
    APIRequest,
    APIResponse,
    decode_response,
    encode,
    to_dict,
)
from civicrm_py.http.transport import BaseTransport
from civicrm_py.query.queryset import LOOKUP_OPERATORS, QuerySet

from .contracts.fixtures import (
    APIv4FormatReference,
    RequestContracts,
    ResponseContracts,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock CiviClient for QuerySet testing."""
    client = Mock()
    client.request = AsyncMock()
    return client


@pytest.fixture
def queryset(mock_client: Mock) -> QuerySet:
    """Create a QuerySet for Contact entity."""
    return QuerySet(mock_client, "Contact")


@pytest.fixture
def activity_queryset(mock_client: Mock) -> QuerySet:
    """Create a QuerySet for Activity entity."""
    return QuerySet(mock_client, "Activity")


# =============================================================================
# REQUEST CONTRACT TESTS
# =============================================================================


class TestRequestSerializationContracts:
    """Test QuerySet builds correct API v4 request format."""

    def test_simple_filter_contract(self, queryset: QuerySet) -> None:
        """Test simple filter produces correct where clause format."""
        contract = RequestContracts.SIMPLE_FILTER
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_simple_select_contract(self, queryset: QuerySet) -> None:
        """Test select produces correct select clause format."""
        contract = RequestContracts.SIMPLE_SELECT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_simple_limit_contract(self, queryset: QuerySet) -> None:
        """Test limit produces correct limit parameter."""
        contract = RequestContracts.SIMPLE_LIMIT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("limit") == contract["expected_params"]["limit"]

    def test_simple_offset_contract(self, queryset: QuerySet) -> None:
        """Test offset produces correct offset parameter."""
        contract = RequestContracts.SIMPLE_OFFSET
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("offset") == contract["expected_params"]["offset"]

    def test_complex_filter_contract(self, queryset: QuerySet) -> None:
        """Test complex filter with multiple conditions."""
        contract = RequestContracts.COMPLEX_FILTER
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        # Check all conditions are present (order may vary)
        where = result.get("where", [])
        expected_where = contract["expected_params"]["where"]

        assert len(where) == len(expected_where)
        for expected in expected_where:
            assert expected in where

    def test_chained_filters_contract(self, queryset: QuerySet) -> None:
        """Test chained filter calls produce correct where clauses."""
        contract = RequestContracts.CHAINED_FILTERS
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_full_query_contract(self, queryset: QuerySet) -> None:
        """Test full query with all options produces correct format."""
        contract = RequestContracts.FULL_QUERY
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        expected = contract["expected_params"]
        assert result.get("select") == expected["select"]
        assert result.get("where") == expected["where"]
        assert result.get("orderBy") == expected["orderBy"]
        assert result.get("limit") == expected["limit"]
        assert result.get("offset") == expected["offset"]


class TestOperatorMappingContracts:
    """Test field lookup operators map correctly to API v4 syntax."""

    def test_exact_lookup_contract(self, queryset: QuerySet) -> None:
        """Test exact lookup produces = operator."""
        contract = RequestContracts.LOOKUP_EXACT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_contains_lookup_contract(self, queryset: QuerySet) -> None:
        """Test contains lookup produces CONTAINS operator."""
        contract = RequestContracts.LOOKUP_CONTAINS
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_startswith_lookup_contract(self, queryset: QuerySet) -> None:
        """Test startswith lookup produces LIKE operator with % suffix."""
        contract = RequestContracts.LOOKUP_STARTSWITH
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        where = result.get("where", [[]])[0]
        assert where[0] == "last_name"
        assert where[1] == "LIKE"
        assert where[2].endswith("%")
        assert not where[2].startswith("%")

    def test_endswith_lookup_contract(self, queryset: QuerySet) -> None:
        """Test endswith lookup produces LIKE operator with % prefix."""
        contract = RequestContracts.LOOKUP_ENDSWITH
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        where = result.get("where", [[]])[0]
        assert where[0] == "last_name"
        assert where[1] == "LIKE"
        assert where[2].startswith("%")
        assert not where[2].endswith("%")

    def test_gt_lookup_contract(self, queryset: QuerySet) -> None:
        """Test gt lookup produces > operator."""
        contract = RequestContracts.LOOKUP_GT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_gte_lookup_contract(self, queryset: QuerySet) -> None:
        """Test gte lookup produces >= operator."""
        contract = RequestContracts.LOOKUP_GTE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_lt_lookup_contract(self, queryset: QuerySet) -> None:
        """Test lt lookup produces < operator."""
        contract = RequestContracts.LOOKUP_LT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_lte_lookup_contract(self, queryset: QuerySet) -> None:
        """Test lte lookup produces <= operator."""
        contract = RequestContracts.LOOKUP_LTE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_in_lookup_contract(self, queryset: QuerySet) -> None:
        """Test in lookup produces IN operator with list value."""
        contract = RequestContracts.LOOKUP_IN
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_isnull_true_lookup_contract(self, queryset: QuerySet) -> None:
        """Test isnull=True lookup produces IS NULL operator."""
        contract = RequestContracts.LOOKUP_ISNULL_TRUE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_isnull_false_lookup_contract(self, queryset: QuerySet) -> None:
        """Test isnull=False lookup produces IS NOT NULL operator."""
        contract = RequestContracts.LOOKUP_ISNULL_FALSE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_not_lookup_contract(self, queryset: QuerySet) -> None:
        """Test not lookup produces != operator."""
        contract = RequestContracts.LOOKUP_NOT
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_all_operators_are_valid_api_operators(self) -> None:
        """Verify all mapped operators are valid CiviCRM API v4 operators."""
        valid_operators = APIv4FormatReference.VALID_OPERATORS

        for lookup, api_operator in LOOKUP_OPERATORS.items():
            assert api_operator in valid_operators, (
                f"Operator '{api_operator}' for lookup '{lookup}' is not a valid API v4 operator"
            )


class TestOrderByContracts:
    """Test order_by translation to API format."""

    def test_order_asc_contract(self, queryset: QuerySet) -> None:
        """Test ascending order produces ASC in orderBy."""
        contract = RequestContracts.ORDER_ASC
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("orderBy") == contract["expected_params"]["orderBy"]

    def test_order_desc_contract(self, queryset: QuerySet) -> None:
        """Test descending order (- prefix) produces DESC in orderBy."""
        contract = RequestContracts.ORDER_DESC
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("orderBy") == contract["expected_params"]["orderBy"]

    def test_order_multiple_contract(self, queryset: QuerySet) -> None:
        """Test multiple order fields produce correct orderBy dict."""
        contract = RequestContracts.ORDER_MULTIPLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("orderBy") == contract["expected_params"]["orderBy"]


class TestJoinSelectContracts:
    """Test join and select related field translation."""

    def test_select_related_field_contract(self, queryset: QuerySet) -> None:
        """Test select with dot notation for related fields."""
        contract = RequestContracts.SELECT_RELATED_FIELD
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_select_multiple_related_contract(self, queryset: QuerySet) -> None:
        """Test select with multiple related fields."""
        contract = RequestContracts.SELECT_MULTIPLE_RELATED
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_join_basic_contract(self, queryset: QuerySet) -> None:
        """Test basic join produces correct join clause."""
        contract = RequestContracts.JOIN_BASIC
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]

    def test_join_with_alias_contract(self, queryset: QuerySet) -> None:
        """Test join with alias produces correct join clause."""
        contract = RequestContracts.JOIN_WITH_ALIAS
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]

    def test_join_multiple_contract(self, queryset: QuerySet) -> None:
        """Test multiple joins produce correct join clauses."""
        contract = RequestContracts.JOIN_MULTIPLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]


class TestGroupByHavingContracts:
    """Test group_by and having translation."""

    def test_group_by_single_contract(self, queryset: QuerySet) -> None:
        """Test single field group by."""
        contract = RequestContracts.GROUP_BY_SINGLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("groupBy") == contract["expected_params"]["groupBy"]

    def test_group_by_multiple_contract(self, queryset: QuerySet) -> None:
        """Test multiple field group by."""
        contract = RequestContracts.GROUP_BY_MULTIPLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("groupBy") == contract["expected_params"]["groupBy"]

    def test_having_clause_contract(self, queryset: QuerySet) -> None:
        """Test having clause with aggregate condition."""
        contract = RequestContracts.HAVING_CLAUSE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("groupBy") == contract["expected_params"]["groupBy"]
        assert result.get("having") == contract["expected_params"]["having"]


class TestExcludeContracts:
    """Test exclude (NOT) clause translation."""

    def test_exclude_simple_contract(self, queryset: QuerySet) -> None:
        """Test simple exclude produces NOT wrapper."""
        contract = RequestContracts.EXCLUDE_SIMPLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_exclude_multiple_contract(self, queryset: QuerySet) -> None:
        """Test multiple excludes produce multiple NOT wrappers."""
        contract = RequestContracts.EXCLUDE_MULTIPLE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]

    def test_filter_and_exclude_contract(self, queryset: QuerySet) -> None:
        """Test combined filter and exclude."""
        contract = RequestContracts.FILTER_AND_EXCLUDE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("where") == contract["expected_params"]["where"]


class TestPaginationContracts:
    """Test pagination parameter translation."""

    def test_pagination_first_page_contract(self, queryset: QuerySet) -> None:
        """Test first page pagination parameters."""
        contract = RequestContracts.PAGINATION_FIRST_PAGE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("limit") == contract["expected_params"]["limit"]
        assert result.get("offset") == contract["expected_params"]["offset"]

    def test_pagination_second_page_contract(self, queryset: QuerySet) -> None:
        """Test second page pagination parameters."""
        contract = RequestContracts.PAGINATION_SECOND_PAGE
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("limit") == contract["expected_params"]["limit"]
        assert result.get("offset") == contract["expected_params"]["offset"]

    def test_pagination_large_offset_contract(self, queryset: QuerySet) -> None:
        """Test large offset for deep pagination."""
        contract = RequestContracts.PAGINATION_LARGE_OFFSET
        qs = contract["queryset_call"](queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("limit") == contract["expected_params"]["limit"]
        assert result.get("offset") == contract["expected_params"]["offset"]


# =============================================================================
# RESPONSE CONTRACT TESTS
# =============================================================================


class TestResponseParsingContracts:
    """Test response parsing matches expected format exactly."""

    def test_success_single_record_contract(self) -> None:
        """Test parsing single record success response."""
        contract = ResponseContracts.SUCCESS_SINGLE
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert len(response.values) == contract["expected"]["values_count"]
        assert response.count == contract["expected"]["count"]
        assert response.first["id"] == contract["expected"]["first_id"]

    def test_success_multiple_records_contract(self) -> None:
        """Test parsing multiple records success response."""
        contract = ResponseContracts.SUCCESS_MULTIPLE
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert len(response.values) == contract["expected"]["values_count"]
        assert response.count == contract["expected"]["count"]

    def test_success_empty_response_contract(self) -> None:
        """Test parsing empty success response."""
        contract = ResponseContracts.SUCCESS_EMPTY
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert len(response.values) == contract["expected"]["values_count"]
        assert response.count == contract["expected"]["count"]
        assert response.first is contract["expected"]["first"]

    def test_success_paginated_response_contract(self) -> None:
        """Test parsing paginated response with count > countFetched."""
        contract = ResponseContracts.SUCCESS_PAGINATED
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert len(response.values) == contract["expected"]["values_count"]
        assert response.count == contract["expected"]["count"]
        assert response.countFetched == contract["expected"]["countFetched"]
        # Key assertion: count > countFetched indicates more results available
        assert response.count > response.countFetched

    def test_success_with_related_fields_contract(self) -> None:
        """Test parsing response with related entity fields (dot notation)."""
        contract = ResponseContracts.SUCCESS_WITH_RELATED
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None

        # Verify related email fields present
        assert "email_primary.email" in first
        assert contract["expected"]["has_related_email"] is True

        # Verify related address fields present
        assert "address_primary.city" in first
        assert contract["expected"]["has_related_address"] is True

        # Verify related phone fields present
        assert "phone_primary.phone" in first
        assert contract["expected"]["has_related_phone"] is True

    def test_success_with_nested_array_contract(self) -> None:
        """Test parsing response with nested array values."""
        contract = ResponseContracts.SUCCESS_WITH_NESTED_ARRAY
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None
        assert first["target_contact_id"] == contract["expected"]["target_contacts"]
        assert first["assignee_contact_id"] == contract["expected"]["assignee_contacts"]


class TestErrorResponseParsingContracts:
    """Test error response parsing and exception mapping."""

    def test_error_unauthorized_contract(self) -> None:
        """Test parsing unauthorized error response."""
        contract = ResponseContracts.ERROR_UNAUTHORIZED
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert response.error_message is not None

    def test_error_not_found_contract(self) -> None:
        """Test parsing not found error response."""
        contract = ResponseContracts.ERROR_NOT_FOUND
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert response.error_message is not None

    def test_error_validation_contract(self) -> None:
        """Test parsing validation error response."""
        contract = ResponseContracts.ERROR_VALIDATION
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert response.error_message is not None

    def test_error_permission_contract(self) -> None:
        """Test parsing permission denied error response."""
        contract = ResponseContracts.ERROR_PERMISSION
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert response.error_message is not None

    def test_error_internal_with_numeric_code_contract(self) -> None:
        """Test parsing internal error with numeric code."""
        contract = ResponseContracts.ERROR_INTERNAL
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert isinstance(response.error_code, int)
        assert response.error_message is not None

    def test_error_required_field_contract(self) -> None:
        """Test parsing required field error includes field name."""
        contract = ResponseContracts.ERROR_REQUIRED_FIELD
        response = decode_response(json.dumps(contract["json"]).encode())

        assert response.is_error is contract["expected"]["is_error"]
        assert response.error_code == contract["expected"]["error_code"]
        assert contract["expected"]["mentions_field"] in response.error_message


# =============================================================================
# API REQUEST ENCODING TESTS
# =============================================================================


class TestAPIRequestEncoding:
    """Test APIRequest to JSON encoding for API v4 format."""

    def test_empty_request_encoding(self) -> None:
        """Test encoding empty request produces minimal JSON."""
        request = APIRequest()
        result = to_dict(request)

        # Empty request should produce empty dict (no None values)
        assert result == {}

    def test_select_encoding(self) -> None:
        """Test select array encoding."""
        request = APIRequest(select=["id", "display_name"])
        result = to_dict(request)

        assert result["select"] == ["id", "display_name"]

    def test_where_encoding(self) -> None:
        """Test where clause array encoding."""
        request = APIRequest(
            where=[
                ["is_deleted", "=", False],
                ["contact_type", "=", "Individual"],
            ]
        )
        result = to_dict(request)

        assert result["where"] == [
            ["is_deleted", "=", False],
            ["contact_type", "=", "Individual"],
        ]

    def test_order_by_encoding(self) -> None:
        """Test orderBy dict encoding."""
        request = APIRequest(orderBy={"created_date": "DESC", "last_name": "ASC"})
        result = to_dict(request)

        assert result["orderBy"] == {"created_date": "DESC", "last_name": "ASC"}

    def test_full_request_encoding(self) -> None:
        """Test full request encoding preserves all fields."""
        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            orderBy={"id": "ASC"},
            limit=10,
            offset=5,
            groupBy=["contact_type"],
            having=[["COUNT(id)", ">", 1]],
        )
        result = to_dict(request)

        assert result["select"] == ["id", "display_name"]
        assert result["where"] == [["is_deleted", "=", False]]
        assert result["orderBy"] == {"id": "ASC"}
        assert result["limit"] == 10
        assert result["offset"] == 5
        assert result["groupBy"] == ["contact_type"]
        assert result["having"] == [["COUNT(id)", ">", 1]]

    def test_values_encoding_for_create(self) -> None:
        """Test values dict encoding for create/update requests."""
        request = APIRequest(
            values={
                "first_name": "John",
                "last_name": "Doe",
                "contact_type": "Individual",
            }
        )
        result = to_dict(request)

        assert result["values"] == {
            "first_name": "John",
            "last_name": "Doe",
            "contact_type": "Individual",
        }

    def test_json_serialization_produces_valid_json(self) -> None:
        """Test encoded request produces valid JSON."""
        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=10,
        )
        encoded = encode(request)

        # Should be valid JSON
        parsed = json.loads(encoded)
        assert "select" in parsed
        assert "limit" in parsed


# =============================================================================
# TRANSPORT REQUEST DATA FORMAT TESTS
# =============================================================================


class TestTransportRequestDataFormat:
    """Test transport layer builds correct request data for CiviCRM API v4."""

    def test_build_request_data_format(self) -> None:
        """Test request data is form-encoded with JSON params."""
        # Create mock settings and auth
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.base_url = "https://example.org/civicrm/ajax/api4"
        auth = MagicMock()

        transport = BaseTransport(settings, auth)

        params = {"select": ["id"], "limit": 10}
        request_data = transport._build_request_data(params)

        # Should have 'params' key with JSON string value
        assert "params" in request_data
        assert isinstance(request_data["params"], str)

        # JSON should be valid and contain original params
        parsed = json.loads(request_data["params"])
        assert parsed["select"] == ["id"]
        assert parsed["limit"] == 10

    def test_build_url_format(self) -> None:
        """Test URL format for API endpoints."""
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.base_url = "https://example.org/civicrm/ajax/api4"
        auth = MagicMock()

        transport = BaseTransport(settings, auth)

        url = transport._build_url("Contact", "get")
        assert url == "https://example.org/civicrm/ajax/api4/Contact/get"

        url = transport._build_url("Activity", "create")
        assert url == "https://example.org/civicrm/ajax/api4/Activity/create"

    def test_build_url_strips_trailing_slash(self) -> None:
        """Test URL builder handles trailing slash in base URL."""
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.base_url = "https://example.org/civicrm/ajax/api4/"  # Trailing slash
        auth = MagicMock()

        transport = BaseTransport(settings, auth)

        url = transport._build_url("Contact", "get")
        # Should not have double slash
        assert "//Contact" not in url
        assert url == "https://example.org/civicrm/ajax/api4/Contact/get"


# =============================================================================
# API RESPONSE STRUCTURE VALIDATION
# =============================================================================


class TestAPIResponseStructure:
    """Test APIResponse matches expected CiviCRM API v4 response structure."""

    def test_response_has_values_field(self) -> None:
        """Test response has values field for entity data."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}],
            count=1,
        )
        assert hasattr(response, "values")
        assert response.values == [{"id": 1}]

    def test_response_has_count_field(self) -> None:
        """Test response has count field for total matches."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[],
            count=100,
        )
        assert hasattr(response, "count")
        assert response.count == 100

    def test_response_has_count_fetched_field(self) -> None:
        """Test response has countFetched field for returned count."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}],
            count=100,
            countFetched=1,
        )
        assert hasattr(response, "countFetched")
        assert response.countFetched == 1

    def test_response_has_error_code_field(self) -> None:
        """Test response has error_code field for errors."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_code="not_found",
        )
        assert hasattr(response, "error_code")
        assert response.error_code == "not_found"

    def test_response_has_error_message_field(self) -> None:
        """Test response has error_message field for errors."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_message="Entity not found",
        )
        assert hasattr(response, "error_message")
        assert response.error_message == "Entity not found"

    def test_response_is_error_property(self) -> None:
        """Test is_error property correctly identifies error responses."""
        success: APIResponse[dict[str, Any]] = APIResponse(values=[], count=0)
        assert success.is_error is False

        error: APIResponse[dict[str, Any]] = APIResponse(error_code="error")
        assert error.is_error is True

    def test_response_first_property(self) -> None:
        """Test first property returns first value or None."""
        with_values: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}, {"id": 2}],
        )
        assert with_values.first == {"id": 1}

        empty: APIResponse[dict[str, Any]] = APIResponse(values=[])
        assert empty.first is None

        none_values: APIResponse[dict[str, Any]] = APIResponse()
        assert none_values.first is None


# =============================================================================
# EDGE CASE AND BOUNDARY TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_queryset_produces_minimal_request(
        self,
        mock_client: Mock,
    ) -> None:
        """Test unmodified QuerySet produces minimal request."""
        qs = QuerySet(mock_client, "Contact")
        params = qs._build_params()
        result = to_dict(params)

        # Should be empty (no None values)
        assert result == {}

    def test_boolean_false_preserved_in_where(self, queryset: QuerySet) -> None:
        """Test boolean False is preserved in where clause."""
        qs = queryset.filter(is_deleted=False)
        params = qs._build_params()
        result = to_dict(params)

        assert result["where"] == [["is_deleted", "=", False]]

    def test_zero_limit_preserved(self, queryset: QuerySet) -> None:
        """Test zero limit is preserved (edge case)."""
        qs = queryset.limit(0)
        params = qs._build_params()
        result = to_dict(params)

        assert result["limit"] == 0

    def test_zero_offset_preserved(self, queryset: QuerySet) -> None:
        """Test zero offset is preserved."""
        qs = queryset.offset(0)
        params = qs._build_params()
        result = to_dict(params)

        assert result["offset"] == 0

    def test_empty_list_for_in_operator(self, queryset: QuerySet) -> None:
        """Test empty list with IN operator."""
        qs = queryset.filter(id__in=[])
        params = qs._build_params()
        result = to_dict(params)

        assert result["where"] == [["id", "IN", []]]

    def test_special_characters_in_values(self, queryset: QuerySet) -> None:
        """Test special characters are preserved in filter values."""
        qs = queryset.filter(name__contains="O'Brien")
        params = qs._build_params()
        result = to_dict(params)

        assert result["where"] == [["name", "CONTAINS", "O'Brien"]]

    def test_unicode_in_values(self, queryset: QuerySet) -> None:
        """Test unicode characters are preserved in filter values."""
        qs = queryset.filter(name="Muller")
        params = qs._build_params()
        result = to_dict(params)

        assert result["where"] == [["name", "=", "Muller"]]

    def test_null_value_in_response(self) -> None:
        """Test null values in response are handled."""
        response_json = {
            "values": [
                {"id": 1, "email": None, "phone": None},
            ],
            "count": 1,
            "countFetched": 1,
        }
        response = decode_response(json.dumps(response_json).encode())

        assert response.first["email"] is None
        assert response.first["phone"] is None

    def test_nested_null_in_response(self) -> None:
        """Test nested null values in response."""
        response_json = {
            "values": [
                {
                    "id": 1,
                    "address_primary.street": None,
                    "address_primary.city": "New York",
                },
            ],
            "count": 1,
            "countFetched": 1,
        }
        response = decode_response(json.dumps(response_json).encode())

        first = response.first
        assert first["address_primary.street"] is None
        assert first["address_primary.city"] == "New York"


# =============================================================================
# PARAMETRIZED CONTRACT TESTS
# =============================================================================


class TestParametrizedContracts:
    """Parametrized tests for comprehensive contract coverage."""

    @pytest.mark.parametrize(
        ("lookup", "operator", "value", "expected_value"),
        [
            ("exact", "=", "John", "John"),
            ("contains", "CONTAINS", "@example", "@example"),
            ("gt", ">", 21, 21),
            ("gte", ">=", 21, 21),
            ("lt", "<", 65, 65),
            ("lte", "<=", 65, 65),
            ("not", "!=", "deleted", "deleted"),
        ],
    )
    def test_lookup_operator_mapping(
        self,
        queryset: QuerySet,
        lookup: str,
        operator: str,
        value: Any,
        expected_value: Any,
    ) -> None:
        """Test each lookup produces correct operator and value."""
        qs = queryset.filter(**{f"field__{lookup}": value})
        params = qs._build_params()
        result = to_dict(params)

        where = result["where"][0]
        assert where[0] == "field"
        assert where[1] == operator
        assert where[2] == expected_value

    @pytest.mark.parametrize(
        ("order_prefix", "expected_direction"),
        [
            ("", "ASC"),
            ("-", "DESC"),
        ],
    )
    def test_order_direction_mapping(
        self,
        queryset: QuerySet,
        order_prefix: str,
        expected_direction: str,
    ) -> None:
        """Test order prefix produces correct direction."""
        qs = queryset.order_by(f"{order_prefix}field_name")
        params = qs._build_params()
        result = to_dict(params)

        assert result["orderBy"]["field_name"] == expected_direction

    @pytest.mark.parametrize(
        ("error_code", "expected_type"),
        [
            ("unauthorized", str),
            ("not_found", str),
            ("validation_error", str),
            (500, int),
            (404, int),
        ],
    )
    def test_error_code_types(
        self,
        error_code: str | int,
        expected_type: type,
    ) -> None:
        """Test error codes can be string or int."""
        response_json = {
            "error_code": error_code,
            "error_message": "Error occurred",
        }
        response = decode_response(json.dumps(response_json).encode())

        assert isinstance(response.error_code, expected_type)
        assert response.is_error is True


# =============================================================================
# COMPREHENSIVE INTEGRATION CONTRACT TESTS
# =============================================================================


class TestIntegrationContracts:
    """Integration tests combining multiple contract aspects."""

    def test_complex_real_world_query_contract(self, queryset: QuerySet) -> None:
        """Test complex real-world query produces valid API request."""
        qs = (
            queryset.filter(is_deleted=False, contact_type="Individual")
            .filter(email__isnull=False)
            .exclude(status="inactive")
            .select(
                "id",
                "display_name",
                "email_primary.email",
                "phone_primary.phone",
            )
            .order_by("-created_date", "last_name")
            .limit(50)
            .offset(0)
        )

        params = qs._build_params()
        result = to_dict(params)

        # Verify all parts are present
        assert "select" in result
        assert "where" in result
        assert "orderBy" in result
        assert "limit" in result
        assert "offset" in result

        # Verify select includes related fields
        assert "email_primary.email" in result["select"]
        assert "phone_primary.phone" in result["select"]

        # Verify where has multiple conditions including NOT
        where = result["where"]
        assert len(where) == 4  # 2 filters + 1 isnull + 1 exclude

        # Verify order has multiple fields
        assert result["orderBy"]["created_date"] == "DESC"
        assert result["orderBy"]["last_name"] == "ASC"

    def test_full_response_round_trip(self) -> None:
        """Test full response can be decoded and fields accessed."""
        response_json = {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "first_name": "John",
                    "last_name": "Doe",
                    "contact_type": "Individual",
                    "email_primary.email": "john@example.com",
                    "phone_primary.phone": "(555) 123-4567",
                    "address_primary.city": "New York",
                    "is_deleted": False,
                    "created_date": "2024-01-15 10:30:00",
                },
                {
                    "id": 2,
                    "display_name": "Jane Smith",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "contact_type": "Individual",
                    "email_primary.email": "jane@example.com",
                    "phone_primary.phone": "(555) 987-6543",
                    "address_primary.city": "Los Angeles",
                    "is_deleted": False,
                    "created_date": "2024-01-16 14:00:00",
                },
            ],
            "count": 150,
            "countFetched": 2,
        }

        response = decode_response(json.dumps(response_json).encode())

        # Basic structure
        assert response.is_error is False
        assert len(response.values) == 2
        assert response.count == 150
        assert response.countFetched == 2

        # First record access
        first = response.first
        assert first["id"] == 1
        assert first["display_name"] == "John Doe"
        assert first["email_primary.email"] == "john@example.com"
        assert first["is_deleted"] is False

        # Second record access
        second = response.values[1]
        assert second["id"] == 2
        assert second["display_name"] == "Jane Smith"

    def test_request_matches_api_v4_reference_format(self) -> None:
        """Test request format matches CiviCRM API v4 reference."""
        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            orderBy={"display_name": "ASC"},
            limit=25,
            offset=0,
        )

        result = to_dict(request)

        # Compare structure to reference
        ref = APIv4FormatReference.GET_REQUEST_FORMAT

        # Should have same keys where values are set
        assert "select" in result
        assert "where" in result
        assert "orderBy" in result
        assert "limit" in result
        assert "offset" in result

        # Types should match reference
        assert isinstance(result["select"], list)
        assert isinstance(result["where"], list)
        assert isinstance(result["orderBy"], dict)
        assert isinstance(result["limit"], int)
        assert isinstance(result["offset"], int)
