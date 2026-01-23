"""Contract fixtures for CiviCRM API v4 request/response format validation.

These fixtures define the expected JSON format for CiviCRM API v4 requests
and responses. They serve as the source of truth for contract testing.
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# REQUEST CONTRACTS
# =============================================================================


class RequestContracts:
    """Expected request formats for CiviCRM API v4."""

    # -------------------------------------------------------------------------
    # Simple Query Contracts
    # -------------------------------------------------------------------------

    SIMPLE_FILTER = {
        "description": "Simple filter: Contact.objects.filter(first_name='John')",
        "queryset_call": lambda qs: qs.filter(first_name="John"),
        "expected_params": {
            "where": [["first_name", "=", "John"]],
        },
    }

    SIMPLE_SELECT = {
        "description": "Select fields: Contact.objects.select('id', 'display_name')",
        "queryset_call": lambda qs: qs.select("id", "display_name"),
        "expected_params": {
            "select": ["id", "display_name"],
        },
    }

    SIMPLE_LIMIT = {
        "description": "Limit results: Contact.objects.limit(10)",
        "queryset_call": lambda qs: qs.limit(10),
        "expected_params": {
            "limit": 10,
        },
    }

    SIMPLE_OFFSET = {
        "description": "Offset results: Contact.objects.offset(20)",
        "queryset_call": lambda qs: qs.offset(20),
        "expected_params": {
            "offset": 20,
        },
    }

    # -------------------------------------------------------------------------
    # Complex Query Contracts
    # -------------------------------------------------------------------------

    COMPLEX_FILTER = {
        "description": "Complex filter with multiple conditions",
        "queryset_call": lambda qs: qs.filter(
            is_deleted=False,
            contact_type="Individual",
        ),
        "expected_params": {
            "where": [
                ["is_deleted", "=", False],
                ["contact_type", "=", "Individual"],
            ],
        },
    }

    CHAINED_FILTERS = {
        "description": "Chained filter calls",
        "queryset_call": lambda qs: qs.filter(first_name="John").filter(last_name="Doe"),
        "expected_params": {
            "where": [
                ["first_name", "=", "John"],
                ["last_name", "=", "Doe"],
            ],
        },
    }

    FULL_QUERY = {
        "description": "Full query with select, filter, order, pagination",
        "queryset_call": lambda qs: (
            qs.filter(is_deleted=False)
            .select("id", "display_name", "email_primary.email")
            .order_by("-created_date", "last_name")
            .limit(10)
            .offset(20)
        ),
        "expected_params": {
            "select": ["id", "display_name", "email_primary.email"],
            "where": [["is_deleted", "=", False]],
            "orderBy": {"created_date": "DESC", "last_name": "ASC"},
            "limit": 10,
            "offset": 20,
        },
    }

    # -------------------------------------------------------------------------
    # Field Lookup Operator Contracts
    # -------------------------------------------------------------------------

    LOOKUP_EXACT = {
        "description": "Exact lookup (explicit)",
        "queryset_call": lambda qs: qs.filter(first_name__exact="John"),
        "expected_params": {
            "where": [["first_name", "=", "John"]],
        },
    }

    LOOKUP_CONTAINS = {
        "description": "Contains lookup",
        "queryset_call": lambda qs: qs.filter(email__contains="@example.com"),
        "expected_params": {
            "where": [["email", "CONTAINS", "@example.com"]],
        },
    }

    LOOKUP_STARTSWITH = {
        "description": "Startswith lookup",
        "queryset_call": lambda qs: qs.filter(last_name__startswith="Sm"),
        "expected_params": {
            "where": [["last_name", "LIKE", "Sm%"]],
        },
    }

    LOOKUP_ENDSWITH = {
        "description": "Endswith lookup",
        "queryset_call": lambda qs: qs.filter(last_name__endswith="th"),
        "expected_params": {
            "where": [["last_name", "LIKE", "%th"]],
        },
    }

    LOOKUP_GT = {
        "description": "Greater than lookup",
        "queryset_call": lambda qs: qs.filter(age__gt=21),
        "expected_params": {
            "where": [["age", ">", 21]],
        },
    }

    LOOKUP_GTE = {
        "description": "Greater than or equal lookup",
        "queryset_call": lambda qs: qs.filter(age__gte=21),
        "expected_params": {
            "where": [["age", ">=", 21]],
        },
    }

    LOOKUP_LT = {
        "description": "Less than lookup",
        "queryset_call": lambda qs: qs.filter(age__lt=65),
        "expected_params": {
            "where": [["age", "<", 65]],
        },
    }

    LOOKUP_LTE = {
        "description": "Less than or equal lookup",
        "queryset_call": lambda qs: qs.filter(age__lte=65),
        "expected_params": {
            "where": [["age", "<=", 65]],
        },
    }

    LOOKUP_IN = {
        "description": "IN lookup",
        "queryset_call": lambda qs: qs.filter(id__in=[1, 2, 3]),
        "expected_params": {
            "where": [["id", "IN", [1, 2, 3]]],
        },
    }

    LOOKUP_ISNULL_TRUE = {
        "description": "IS NULL lookup (true)",
        "queryset_call": lambda qs: qs.filter(email__isnull=True),
        "expected_params": {
            "where": [["email", "IS NULL"]],
        },
    }

    LOOKUP_ISNULL_FALSE = {
        "description": "IS NOT NULL lookup (false)",
        "queryset_call": lambda qs: qs.filter(email__isnull=False),
        "expected_params": {
            "where": [["email", "IS NOT NULL"]],
        },
    }

    LOOKUP_NOT = {
        "description": "Not equal lookup",
        "queryset_call": lambda qs: qs.filter(status__not="deleted"),
        "expected_params": {
            "where": [["status", "!=", "deleted"]],
        },
    }

    # -------------------------------------------------------------------------
    # Order By Contracts
    # -------------------------------------------------------------------------

    ORDER_ASC = {
        "description": "Ascending order",
        "queryset_call": lambda qs: qs.order_by("last_name"),
        "expected_params": {
            "orderBy": {"last_name": "ASC"},
        },
    }

    ORDER_DESC = {
        "description": "Descending order (with - prefix)",
        "queryset_call": lambda qs: qs.order_by("-created_date"),
        "expected_params": {
            "orderBy": {"created_date": "DESC"},
        },
    }

    ORDER_MULTIPLE = {
        "description": "Multiple order fields",
        "queryset_call": lambda qs: qs.order_by("-created_date", "last_name", "-first_name"),
        "expected_params": {
            "orderBy": {
                "created_date": "DESC",
                "last_name": "ASC",
                "first_name": "DESC",
            },
        },
    }

    # -------------------------------------------------------------------------
    # Join/Select Related Contracts
    # -------------------------------------------------------------------------

    SELECT_RELATED_FIELD = {
        "description": "Select with related field (dot notation)",
        "queryset_call": lambda qs: qs.select("id", "display_name", "email_primary.email"),
        "expected_params": {
            "select": ["id", "display_name", "email_primary.email"],
        },
    }

    SELECT_MULTIPLE_RELATED = {
        "description": "Select with multiple related fields",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "email_primary.email",
            "address_primary.city",
            "phone_primary.phone",
        ),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "email_primary.email",
                "address_primary.city",
                "phone_primary.phone",
            ],
        },
    }

    JOIN_BASIC = {
        "description": "Basic join",
        "queryset_call": lambda qs: qs.join("Email", "email_primary"),
        "expected_params": {
            "join": [["Email", "email_primary"]],
        },
    }

    JOIN_WITH_ALIAS = {
        "description": "Join with alias",
        "queryset_call": lambda qs: qs.join("Email", "email_primary", "email"),
        "expected_params": {
            "join": [["Email", "email_primary", "email"]],
        },
    }

    JOIN_MULTIPLE = {
        "description": "Multiple joins",
        "queryset_call": lambda qs: (
            qs.join("Email", "email_primary", "email")
            .join("Address", "address_primary", "addr")
            .join("Phone", "phone_primary", "phone")
        ),
        "expected_params": {
            "join": [
                ["Email", "email_primary", "email"],
                ["Address", "address_primary", "addr"],
                ["Phone", "phone_primary", "phone"],
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Group By / Having Contracts
    # -------------------------------------------------------------------------

    GROUP_BY_SINGLE = {
        "description": "Group by single field",
        "queryset_call": lambda qs: qs.group_by("contact_type"),
        "expected_params": {
            "groupBy": ["contact_type"],
        },
    }

    GROUP_BY_MULTIPLE = {
        "description": "Group by multiple fields",
        "queryset_call": lambda qs: qs.group_by("contact_type", "is_deleted"),
        "expected_params": {
            "groupBy": ["contact_type", "is_deleted"],
        },
    }

    HAVING_CLAUSE = {
        "description": "Having clause",
        "queryset_call": lambda qs: qs.group_by("contact_type").having(count__gt=5),
        "expected_params": {
            "groupBy": ["contact_type"],
            "having": [["count", ">", 5]],
        },
    }

    # -------------------------------------------------------------------------
    # Exclude Contracts
    # -------------------------------------------------------------------------

    EXCLUDE_SIMPLE = {
        "description": "Simple exclude",
        "queryset_call": lambda qs: qs.exclude(is_deleted=True),
        "expected_params": {
            "where": [["NOT", [["is_deleted", "=", True]]]],
        },
    }

    EXCLUDE_MULTIPLE = {
        "description": "Multiple excludes",
        "queryset_call": lambda qs: qs.exclude(is_deleted=True).exclude(contact_type="Organization"),
        "expected_params": {
            "where": [
                ["NOT", [["is_deleted", "=", True]]],
                ["NOT", [["contact_type", "=", "Organization"]]],
            ],
        },
    }

    FILTER_AND_EXCLUDE = {
        "description": "Combined filter and exclude",
        "queryset_call": lambda qs: (qs.filter(contact_type="Individual").exclude(is_deleted=True)),
        "expected_params": {
            "where": [
                ["contact_type", "=", "Individual"],
                ["NOT", [["is_deleted", "=", True]]],
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Pagination Contracts
    # -------------------------------------------------------------------------

    PAGINATION_FIRST_PAGE = {
        "description": "First page of results",
        "queryset_call": lambda qs: qs.limit(25).offset(0),
        "expected_params": {
            "limit": 25,
            "offset": 0,
        },
    }

    PAGINATION_SECOND_PAGE = {
        "description": "Second page of results",
        "queryset_call": lambda qs: qs.limit(25).offset(25),
        "expected_params": {
            "limit": 25,
            "offset": 25,
        },
    }

    PAGINATION_LARGE_OFFSET = {
        "description": "Large offset for deep pagination",
        "queryset_call": lambda qs: qs.limit(100).offset(1000),
        "expected_params": {
            "limit": 100,
            "offset": 1000,
        },
    }


# =============================================================================
# RESPONSE CONTRACTS
# =============================================================================


class ResponseContracts:
    """Expected response formats from CiviCRM API v4."""

    # -------------------------------------------------------------------------
    # Success Response Contracts
    # -------------------------------------------------------------------------

    SUCCESS_SINGLE: dict[str, Any] = {
        "description": "Successful response with single record",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "first_name": "John",
                    "last_name": "Doe",
                    "contact_type": "Individual",
                    "is_deleted": False,
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "values_count": 1,
            "count": 1,
            "is_error": False,
            "first_id": 1,
        },
    }

    SUCCESS_MULTIPLE: dict[str, Any] = {
        "description": "Successful response with multiple records",
        "json": {
            "values": [
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "Jane Smith"},
                {"id": 3, "display_name": "Bob Johnson"},
            ],
            "count": 3,
            "countFetched": 3,
        },
        "expected": {
            "values_count": 3,
            "count": 3,
            "is_error": False,
        },
    }

    SUCCESS_EMPTY: dict[str, Any] = {
        "description": "Successful response with no records",
        "json": {
            "values": [],
            "count": 0,
            "countFetched": 0,
        },
        "expected": {
            "values_count": 0,
            "count": 0,
            "is_error": False,
            "first": None,
        },
    }

    SUCCESS_PAGINATED: dict[str, Any] = {
        "description": "Paginated response with more results available",
        "json": {
            "values": [
                {"id": 1, "display_name": "Contact 1"},
                {"id": 2, "display_name": "Contact 2"},
            ],
            "count": 100,
            "countFetched": 2,
        },
        "expected": {
            "values_count": 2,
            "count": 100,
            "countFetched": 2,
            "is_error": False,
        },
    }

    SUCCESS_WITH_RELATED: dict[str, Any] = {
        "description": "Response with related entity data (dot notation)",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "email_primary.email": "john@example.com",
                    "email_primary.is_primary": True,
                    "address_primary.city": "New York",
                    "address_primary.country_id": 1228,
                    "phone_primary.phone": "(555) 123-4567",
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "values_count": 1,
            "has_related_email": True,
            "has_related_address": True,
            "has_related_phone": True,
        },
    }

    SUCCESS_WITH_NESTED_ARRAY: dict[str, Any] = {
        "description": "Response with nested array values",
        "json": {
            "values": [
                {
                    "id": 1,
                    "subject": "Meeting",
                    "target_contact_id": [2, 3, 4],
                    "assignee_contact_id": [1, 5],
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "values_count": 1,
            "target_contacts": [2, 3, 4],
            "assignee_contacts": [1, 5],
        },
    }

    # -------------------------------------------------------------------------
    # Error Response Contracts
    # -------------------------------------------------------------------------

    ERROR_UNAUTHORIZED: dict[str, Any] = {
        "description": "Authentication error (invalid API key)",
        "json": {
            "error_code": "unauthorized",
            "error_message": "API key is invalid or expired. Please check your credentials.",
        },
        "expected": {
            "is_error": True,
            "error_code": "unauthorized",
            "has_error_message": True,
        },
    }

    ERROR_NOT_FOUND: dict[str, Any] = {
        "description": "Entity not found error",
        "json": {
            "error_code": "not_found",
            "error_message": "Entity not found: No Contact with id = 999 exists.",
        },
        "expected": {
            "is_error": True,
            "error_code": "not_found",
            "has_error_message": True,
        },
    }

    ERROR_VALIDATION: dict[str, Any] = {
        "description": "Validation error",
        "json": {
            "error_code": "validation_error",
            "error_message": "Validation failed for field 'email': Invalid email format.",
        },
        "expected": {
            "is_error": True,
            "error_code": "validation_error",
            "has_error_message": True,
        },
    }

    ERROR_PERMISSION: dict[str, Any] = {
        "description": "Permission denied error",
        "json": {
            "error_code": "access_denied",
            "error_message": "You do not have permission to access Contact records.",
        },
        "expected": {
            "is_error": True,
            "error_code": "access_denied",
            "has_error_message": True,
        },
    }

    ERROR_INTERNAL: dict[str, Any] = {
        "description": "Internal server error (numeric code)",
        "json": {
            "error_code": 500,
            "error_message": "An unexpected error occurred while processing your request.",
        },
        "expected": {
            "is_error": True,
            "error_code": 500,
            "has_error_message": True,
        },
    }

    ERROR_REQUIRED_FIELD: dict[str, Any] = {
        "description": "Required field missing error",
        "json": {
            "error_code": "required_field",
            "error_message": "Mandatory values missing from Api4 Contact::create: contact_type",
        },
        "expected": {
            "is_error": True,
            "error_code": "required_field",
            "mentions_field": "contact_type",
        },
    }


# =============================================================================
# OPERATOR MAPPING CONTRACTS
# =============================================================================


OPERATOR_MAPPING: dict[str, str] = {
    "exact": "=",
    "contains": "CONTAINS",
    "startswith": "LIKE",  # value becomes "value%"
    "endswith": "LIKE",  # value becomes "%value"
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "in": "IN",
    "isnull": "IS NULL",  # or "IS NOT NULL" based on value
    "not": "!=",
}


# =============================================================================
# API v4 JSON FORMAT REFERENCE
# =============================================================================


class APIv4FormatReference:
    """Reference documentation for CiviCRM API v4 JSON format."""

    # Request format for 'get' action
    GET_REQUEST_FORMAT: dict[str, Any] = {
        "select": ["field1", "field2", "related.field"],
        "where": [
            ["field", "operator", "value"],
            ["AND", [["field1", "=", "value1"], ["field2", "=", "value2"]]],
            ["OR", [["field1", "=", "value1"], ["field2", "=", "value2"]]],
            ["NOT", [["field", "=", "value"]]],
        ],
        "orderBy": {"field": "ASC"},
        "limit": 25,
        "offset": 0,
        "join": [["EntityName", "join_field", "alias"]],
        "groupBy": ["field1", "field2"],
        "having": [["aggregate_field", "operator", "value"]],
    }

    # Request format for 'create' action
    CREATE_REQUEST_FORMAT: dict[str, Any] = {
        "values": {
            "field1": "value1",
            "field2": "value2",
        },
    }

    # Request format for 'update' action
    UPDATE_REQUEST_FORMAT: dict[str, Any] = {
        "values": {
            "field1": "new_value",
        },
        "where": [
            ["id", "=", 1],
        ],
    }

    # Request format for 'delete' action
    DELETE_REQUEST_FORMAT: dict[str, Any] = {
        "where": [
            ["id", "=", 1],
        ],
    }

    # Valid operators for where clauses
    VALID_OPERATORS: list[str] = [
        "=",
        "!=",
        ">",
        "<",
        ">=",
        "<=",
        "LIKE",
        "NOT LIKE",
        "IN",
        "NOT IN",
        "CONTAINS",
        "NOT CONTAINS",
        "IS NULL",
        "IS NOT NULL",
        "IS EMPTY",
        "IS NOT EMPTY",
        "BETWEEN",
        "NOT BETWEEN",
        "REGEXP",
        "NOT REGEXP",
    ]

    # Response format for success
    SUCCESS_RESPONSE_FORMAT: dict[str, Any] = {
        "values": [{"id": 1, "field": "value"}],
        "count": 1,
        "countFetched": 1,
    }

    # Response format for error
    ERROR_RESPONSE_FORMAT: dict[str, Any] = {
        "error_code": "string or int",
        "error_message": "Human readable error message",
    }
