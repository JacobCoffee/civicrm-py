"""Relationship and join compatibility tests for CiviCRM API v4.

These tests verify that:
1. FK relationships produce correct API request format
2. Implicit joins (dot notation) work correctly
3. Explicit joins produce correct API format
4. Related entity prefetching works
5. Many-to-many relationships via bridge tables work

The tests ensure our library correctly handles entity relationships
as expected by CiviCRM API v4.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from civicrm_py.core.serialization import (
    APIResponse,
    decode_response,
    to_dict,
)
from civicrm_py.entities.relationships import (
    ForeignKey,
    ForeignKeyAccessor,
    ManyToManyField,
    ManyToManyManager,
    RelatedField,
    RelatedManager,
    get_relationships,
    get_reverse_relationships,
    register_relationship,
)
from civicrm_py.query.queryset import QuerySet

# =============================================================================
# RELATIONSHIP CONTRACT FIXTURES
# =============================================================================


class RelationshipContracts:
    """Expected formats for relationship-related API operations."""

    # -------------------------------------------------------------------------
    # FK Field Selection Contracts
    # -------------------------------------------------------------------------

    FK_FIELD_SELECT = {
        "description": "Select FK field with related data",
        "queryset_call": lambda qs: qs.select("id", "display_name", "employer_id"),
        "expected_params": {
            "select": ["id", "display_name", "employer_id"],
        },
    }

    FK_WITH_RELATED_DATA = {
        "description": "Select FK field and access related entity fields",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "employer_id",
            "employer_id.organization_name",
            "employer_id.display_name",
        ),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "employer_id",
                "employer_id.organization_name",
                "employer_id.display_name",
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Implicit Join Contracts (dot notation)
    # -------------------------------------------------------------------------

    IMPLICIT_JOIN_EMAIL = {
        "description": "Implicit join via email_primary.email",
        "queryset_call": lambda qs: qs.select("id", "display_name", "email_primary.email"),
        "expected_params": {
            "select": ["id", "display_name", "email_primary.email"],
        },
    }

    IMPLICIT_JOIN_ADDRESS = {
        "description": "Implicit join via address_primary fields",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "address_primary.street_address",
            "address_primary.city",
            "address_primary.postal_code",
            "address_primary.country_id",
        ),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "address_primary.street_address",
                "address_primary.city",
                "address_primary.postal_code",
                "address_primary.country_id",
            ],
        },
    }

    IMPLICIT_JOIN_PHONE = {
        "description": "Implicit join via phone_primary.phone",
        "queryset_call": lambda qs: qs.select("id", "display_name", "phone_primary.phone"),
        "expected_params": {
            "select": ["id", "display_name", "phone_primary.phone"],
        },
    }

    IMPLICIT_JOIN_MULTIPLE = {
        "description": "Multiple implicit joins in single query",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "email_primary.email",
            "phone_primary.phone",
            "address_primary.city",
            "employer_id.organization_name",
        ),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "email_primary.email",
                "phone_primary.phone",
                "address_primary.city",
                "employer_id.organization_name",
            ],
        },
    }

    IMPLICIT_JOIN_NESTED = {
        "description": "Deeply nested implicit join",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "address_primary.country_id.name",
            "address_primary.state_province_id.name",
        ),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "address_primary.country_id.name",
                "address_primary.state_province_id.name",
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Explicit Join Contracts
    # -------------------------------------------------------------------------

    EXPLICIT_JOIN_EMAIL = {
        "description": "Explicit join to Email entity",
        "queryset_call": lambda qs: qs.join("Email", "email_primary", "email"),
        "expected_params": {
            "join": [["Email", "email_primary", "email"]],
        },
    }

    EXPLICIT_JOIN_ACTIVITY = {
        "description": "Explicit join to Activity entity",
        "queryset_call": lambda qs: qs.join("Activity", "id", "activity"),
        "expected_params": {
            "join": [["Activity", "id", "activity"]],
        },
    }

    EXPLICIT_JOIN_MULTIPLE = {
        "description": "Multiple explicit joins",
        "queryset_call": lambda qs: (
            qs.join("Email", "email_primary", "email")
            .join("Phone", "phone_primary", "phone")
            .join("Address", "address_primary", "addr")
        ),
        "expected_params": {
            "join": [
                ["Email", "email_primary", "email"],
                ["Phone", "phone_primary", "phone"],
                ["Address", "address_primary", "addr"],
            ],
        },
    }

    EXPLICIT_JOIN_WITH_SELECT = {
        "description": "Explicit join with aliased field selection",
        "queryset_call": lambda qs: (
            qs.join("Email", "email_primary", "email").select(
                "id",
                "display_name",
                "email.email",
                "email.is_primary",
            )
        ),
        "expected_params": {
            "join": [["Email", "email_primary", "email"]],
            "select": ["id", "display_name", "email.email", "email.is_primary"],
        },
    }

    EXPLICIT_JOIN_WITH_FILTER = {
        "description": "Explicit join with filter on joined entity",
        "queryset_call": lambda qs: (
            qs.join("Email", "email_primary", "email")
            .select("id", "display_name", "email.email")
            .filter(**{"email.is_primary": True})
        ),
        "expected_params": {
            "join": [["Email", "email_primary", "email"]],
            "select": ["id", "display_name", "email.email"],
            "where": [["email.is_primary", "=", True]],
        },
    }

    # -------------------------------------------------------------------------
    # Nested/Chained Join Contracts
    # -------------------------------------------------------------------------

    NESTED_JOIN_ACTIVITY_CONTACT = {
        "description": "Nested join: Activity -> ActivityContact -> Contact",
        "queryset_call": lambda qs: (
            qs.join("ActivityContact", "id", "ac")
            .join("Contact", "ac.contact_id", "target")
            .select(
                "id",
                "subject",
                "ac.record_type_id",
                "target.display_name",
            )
        ),
        "expected_params": {
            "join": [
                ["ActivityContact", "id", "ac"],
                ["Contact", "ac.contact_id", "target"],
            ],
            "select": [
                "id",
                "subject",
                "ac.record_type_id",
                "target.display_name",
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Self-referential Join Contracts
    # -------------------------------------------------------------------------

    SELF_REF_EMPLOYER = {
        "description": "Self-referential join: Contact.employer_id -> Contact (Organization)",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "employer_id",
            "employer_id.organization_name",
            "employer_id.display_name",
        ).filter(employer_id__isnull=False),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "employer_id",
                "employer_id.organization_name",
                "employer_id.display_name",
            ],
            "where": [["employer_id", "IS NOT NULL"]],
        },
    }

    SELF_REF_PARENT_ACTIVITY = {
        "description": "Self-referential join: Activity.parent_id -> Activity",
        "queryset_call": lambda qs: qs.select(
            "id",
            "subject",
            "parent_id",
            "parent_id.subject",
            "parent_id.activity_type_id",
        ).filter(parent_id__isnull=False),
        "expected_params": {
            "select": [
                "id",
                "subject",
                "parent_id",
                "parent_id.subject",
                "parent_id.activity_type_id",
            ],
            "where": [["parent_id", "IS NOT NULL"]],
        },
    }

    # -------------------------------------------------------------------------
    # Many-to-Many via Bridge Contracts
    # -------------------------------------------------------------------------

    M2M_CONTACT_GROUP_VIA_BRIDGE = {
        "description": "Contact -> GroupContact -> Group via bridge table",
        "queryset_call": lambda qs: (
            qs.join("GroupContact", "id", "gc")
            .join("Group", "gc.group_id", "grp")
            .select(
                "id",
                "display_name",
                "gc.status",
                "grp.title",
                "grp.is_active",
            )
        ),
        "expected_params": {
            "join": [
                ["GroupContact", "id", "gc"],
                ["Group", "gc.group_id", "grp"],
            ],
            "select": [
                "id",
                "display_name",
                "gc.status",
                "grp.title",
                "grp.is_active",
            ],
        },
    }

    M2M_FILTER_ON_BRIDGE = {
        "description": "Many-to-many with filter on bridge table",
        "queryset_call": lambda qs: (
            qs.join("GroupContact", "id", "gc")
            .join("Group", "gc.group_id", "grp")
            .select("id", "display_name", "grp.title")
            .filter(**{"gc.status": "Added", "grp.is_active": True})
        ),
        "expected_params": {
            "join": [
                ["GroupContact", "id", "gc"],
                ["Group", "gc.group_id", "grp"],
            ],
            "select": ["id", "display_name", "grp.title"],
            "where": [
                ["gc.status", "=", "Added"],
                ["grp.is_active", "=", True],
            ],
        },
    }

    # -------------------------------------------------------------------------
    # Prefetch Related Contracts
    # -------------------------------------------------------------------------

    PREFETCH_EMAILS = {
        "description": "Prefetch all emails for contacts (via API pattern)",
        "queryset_call": lambda qs: qs.select(
            "id",
            "display_name",
            "email.email",
            "email.is_primary",
            "email.location_type_id",
        ).join("Email", "id", "email"),
        "expected_params": {
            "select": [
                "id",
                "display_name",
                "email.email",
                "email.is_primary",
                "email.location_type_id",
            ],
            "join": [["Email", "id", "email"]],
        },
    }


# =============================================================================
# RESPONSE CONTRACTS FOR RELATIONSHIPS
# =============================================================================


class RelationshipResponseContracts:
    """Expected response formats for relationship queries."""

    RESPONSE_WITH_FK_DATA: dict[str, Any] = {
        "description": "Response with FK field and related data",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "employer_id": 10,
                    "employer_id.organization_name": "Acme Corp",
                    "employer_id.display_name": "Acme Corporation",
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "has_employer_id": True,
            "has_employer_name": True,
            "employer_id": 10,
            "employer_name": "Acme Corp",
        },
    }

    RESPONSE_WITH_IMPLICIT_JOINS: dict[str, Any] = {
        "description": "Response with implicit join data (dot notation)",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "email_primary.email": "john@example.com",
                    "email_primary.is_primary": True,
                    "phone_primary.phone": "(555) 123-4567",
                    "address_primary.city": "New York",
                    "address_primary.country_id": 1228,
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "has_email": True,
            "has_phone": True,
            "has_address": True,
            "email": "john@example.com",
            "city": "New York",
        },
    }

    RESPONSE_WITH_EXPLICIT_JOIN: dict[str, Any] = {
        "description": "Response with explicit join data",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "email.email": "john@example.com",
                    "email.is_primary": True,
                    "email.location_type_id": 1,
                },
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "email.email": "john.work@example.com",
                    "email.is_primary": False,
                    "email.location_type_id": 2,
                },
            ],
            "count": 2,
            "countFetched": 2,
        },
        "expected": {
            "values_count": 2,
            "same_contact": True,
            "different_emails": True,
        },
    }

    RESPONSE_WITH_NESTED_JOIN: dict[str, Any] = {
        "description": "Response with nested/chained join data",
        "json": {
            "values": [
                {
                    "id": 1,
                    "subject": "Follow-up call",
                    "ac.record_type_id": 3,
                    "target.display_name": "Jane Smith",
                },
                {
                    "id": 1,
                    "subject": "Follow-up call",
                    "ac.record_type_id": 3,
                    "target.display_name": "Bob Johnson",
                },
            ],
            "count": 2,
            "countFetched": 2,
        },
        "expected": {
            "values_count": 2,
            "same_activity": True,
            "different_targets": True,
        },
    }

    RESPONSE_WITH_M2M: dict[str, Any] = {
        "description": "Response with many-to-many via bridge table",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "gc.status": "Added",
                    "grp.title": "Newsletter Subscribers",
                    "grp.is_active": True,
                },
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "gc.status": "Added",
                    "grp.title": "Board Members",
                    "grp.is_active": True,
                },
            ],
            "count": 2,
            "countFetched": 2,
        },
        "expected": {
            "values_count": 2,
            "same_contact": True,
            "different_groups": True,
        },
    }

    RESPONSE_WITH_NULL_FK: dict[str, Any] = {
        "description": "Response with null FK field",
        "json": {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "employer_id": None,
                    "employer_id.organization_name": None,
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "employer_id_is_null": True,
            "employer_name_is_null": True,
        },
    }

    RESPONSE_SELF_REF: dict[str, Any] = {
        "description": "Response with self-referential relationship",
        "json": {
            "values": [
                {
                    "id": 5,
                    "subject": "Reply: Initial meeting",
                    "parent_id": 1,
                    "parent_id.subject": "Initial meeting",
                    "parent_id.activity_type_id": 2,
                },
            ],
            "count": 1,
            "countFetched": 1,
        },
        "expected": {
            "has_parent": True,
            "parent_subject": "Initial meeting",
        },
    }


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
def contact_queryset(mock_client: Mock) -> QuerySet:
    """Create a QuerySet for Contact entity."""
    return QuerySet(mock_client, "Contact")


@pytest.fixture
def activity_queryset(mock_client: Mock) -> QuerySet:
    """Create a QuerySet for Activity entity."""
    return QuerySet(mock_client, "Activity")


@pytest.fixture
def mock_entity() -> Mock:
    """Create a mock entity with client for relationship testing."""
    entity = Mock()
    entity.id = 1
    entity._client = Mock()
    entity._client.request = AsyncMock()
    return entity


# =============================================================================
# FK FIELD SELECTION TESTS
# =============================================================================


class TestFKFieldSelection:
    """Test FK field selection produces correct API format."""

    def test_fk_field_select_contract(self, contact_queryset: QuerySet) -> None:
        """Test selecting FK field produces correct select clause."""
        contract = RelationshipContracts.FK_FIELD_SELECT
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_fk_with_related_data_contract(self, contact_queryset: QuerySet) -> None:
        """Test selecting FK field with related entity fields."""
        contract = RelationshipContracts.FK_WITH_RELATED_DATA
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_fk_response_parsing(self) -> None:
        """Test parsing response with FK data."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_FK_DATA
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None
        assert first["employer_id"] == contract["expected"]["employer_id"]
        assert first["employer_id.organization_name"] == contract["expected"]["employer_name"]

    def test_null_fk_response_parsing(self) -> None:
        """Test parsing response with null FK field."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_NULL_FK
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None
        assert first["employer_id"] is None
        assert first["employer_id.organization_name"] is None


# =============================================================================
# IMPLICIT JOIN TESTS (DOT NOTATION)
# =============================================================================


class TestImplicitJoins:
    """Test implicit joins via dot notation."""

    def test_implicit_join_email_contract(self, contact_queryset: QuerySet) -> None:
        """Test implicit join via email_primary.email."""
        contract = RelationshipContracts.IMPLICIT_JOIN_EMAIL
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        # Verify dot notation is preserved
        assert "email_primary.email" in result["select"]

    def test_implicit_join_address_contract(self, contact_queryset: QuerySet) -> None:
        """Test implicit join via address_primary fields."""
        contract = RelationshipContracts.IMPLICIT_JOIN_ADDRESS
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        # Verify all address fields with dot notation
        assert "address_primary.street_address" in result["select"]
        assert "address_primary.city" in result["select"]
        assert "address_primary.postal_code" in result["select"]
        assert "address_primary.country_id" in result["select"]

    def test_implicit_join_phone_contract(self, contact_queryset: QuerySet) -> None:
        """Test implicit join via phone_primary.phone."""
        contract = RelationshipContracts.IMPLICIT_JOIN_PHONE
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]

    def test_implicit_join_multiple_contract(self, contact_queryset: QuerySet) -> None:
        """Test multiple implicit joins in single query."""
        contract = RelationshipContracts.IMPLICIT_JOIN_MULTIPLE
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        # Verify all different related entities
        select = result["select"]
        assert any("email_primary" in f for f in select)
        assert any("phone_primary" in f for f in select)
        assert any("address_primary" in f for f in select)
        assert any("employer_id" in f for f in select)

    def test_implicit_join_nested_contract(self, contact_queryset: QuerySet) -> None:
        """Test deeply nested implicit joins."""
        contract = RelationshipContracts.IMPLICIT_JOIN_NESTED
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        # Verify deeply nested fields
        assert "address_primary.country_id.name" in result["select"]
        assert "address_primary.state_province_id.name" in result["select"]

    def test_implicit_join_response_parsing(self) -> None:
        """Test parsing response with implicit join data."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_IMPLICIT_JOINS
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None
        assert first["email_primary.email"] == contract["expected"]["email"]
        assert first["address_primary.city"] == contract["expected"]["city"]
        assert "phone_primary.phone" in first
        assert "address_primary.country_id" in first


# =============================================================================
# EXPLICIT JOIN TESTS
# =============================================================================


class TestExplicitJoins:
    """Test explicit join clause generation."""

    def test_explicit_join_email_contract(self, contact_queryset: QuerySet) -> None:
        """Test explicit join to Email entity."""
        contract = RelationshipContracts.EXPLICIT_JOIN_EMAIL
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]

    def test_explicit_join_activity_contract(self, contact_queryset: QuerySet) -> None:
        """Test explicit join to Activity entity."""
        contract = RelationshipContracts.EXPLICIT_JOIN_ACTIVITY
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]

    def test_explicit_join_multiple_contract(self, contact_queryset: QuerySet) -> None:
        """Test multiple explicit joins."""
        contract = RelationshipContracts.EXPLICIT_JOIN_MULTIPLE
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert len(result["join"]) == 3

    def test_explicit_join_with_select_contract(self, contact_queryset: QuerySet) -> None:
        """Test explicit join with aliased field selection."""
        contract = RelationshipContracts.EXPLICIT_JOIN_WITH_SELECT
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert result.get("select") == contract["expected_params"]["select"]
        # Verify alias is used in select
        assert "email.email" in result["select"]

    def test_explicit_join_with_filter_contract(self, contact_queryset: QuerySet) -> None:
        """Test explicit join with filter on joined entity."""
        contract = RelationshipContracts.EXPLICIT_JOIN_WITH_FILTER
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert result.get("select") == contract["expected_params"]["select"]
        assert result.get("where") == contract["expected_params"]["where"]

    def test_explicit_join_response_parsing(self) -> None:
        """Test parsing response with explicit join data."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_EXPLICIT_JOIN
        response = decode_response(json.dumps(contract["json"]).encode())

        assert len(response.values) == contract["expected"]["values_count"]
        # Same contact, different emails (one-to-many via join)
        assert response.values[0]["id"] == response.values[1]["id"]
        assert response.values[0]["email.email"] != response.values[1]["email.email"]


# =============================================================================
# NESTED JOIN TESTS
# =============================================================================


class TestNestedJoins:
    """Test nested/chained joins."""

    def test_nested_join_activity_contact_contract(self, activity_queryset: QuerySet) -> None:
        """Test nested join: Activity -> ActivityContact -> Contact."""
        contract = RelationshipContracts.NESTED_JOIN_ACTIVITY_CONTACT
        qs = contract["queryset_call"](activity_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert result.get("select") == contract["expected_params"]["select"]
        # Verify chain of joins
        assert len(result["join"]) == 2
        assert result["join"][0][2] == "ac"  # First alias
        assert result["join"][1][2] == "target"  # Second alias

    def test_nested_join_response_parsing(self) -> None:
        """Test parsing response with nested join data."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_NESTED_JOIN
        response = decode_response(json.dumps(contract["json"]).encode())

        assert len(response.values) == contract["expected"]["values_count"]
        # Same activity, different targets
        assert response.values[0]["id"] == response.values[1]["id"]
        assert response.values[0]["target.display_name"] != response.values[1]["target.display_name"]


# =============================================================================
# SELF-REFERENTIAL JOIN TESTS
# =============================================================================


class TestSelfReferentialJoins:
    """Test self-referential relationships."""

    def test_self_ref_employer_contract(self, contact_queryset: QuerySet) -> None:
        """Test self-referential: Contact.employer_id -> Contact."""
        contract = RelationshipContracts.SELF_REF_EMPLOYER
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        assert result.get("where") == contract["expected_params"]["where"]
        # Verify employer_id references same entity
        assert "employer_id.organization_name" in result["select"]
        assert "employer_id.display_name" in result["select"]

    def test_self_ref_parent_activity_contract(self, activity_queryset: QuerySet) -> None:
        """Test self-referential: Activity.parent_id -> Activity."""
        contract = RelationshipContracts.SELF_REF_PARENT_ACTIVITY
        qs = contract["queryset_call"](activity_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        assert result.get("where") == contract["expected_params"]["where"]
        # Verify parent_id references same entity
        assert "parent_id.subject" in result["select"]
        assert "parent_id.activity_type_id" in result["select"]

    def test_self_ref_response_parsing(self) -> None:
        """Test parsing response with self-referential data."""
        contract = RelationshipResponseContracts.RESPONSE_SELF_REF
        response = decode_response(json.dumps(contract["json"]).encode())

        first = response.first
        assert first is not None
        assert first["parent_id"] == 1
        assert first["parent_id.subject"] == contract["expected"]["parent_subject"]


# =============================================================================
# MANY-TO-MANY VIA BRIDGE TESTS
# =============================================================================


class TestManyToManyViaBridge:
    """Test many-to-many relationships via bridge tables."""

    def test_m2m_contact_group_contract(self, contact_queryset: QuerySet) -> None:
        """Test Contact -> GroupContact -> Group via bridge table."""
        contract = RelationshipContracts.M2M_CONTACT_GROUP_VIA_BRIDGE
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert result.get("select") == contract["expected_params"]["select"]
        # Verify bridge table join
        assert ["GroupContact", "id", "gc"] in result["join"]
        assert ["Group", "gc.group_id", "grp"] in result["join"]

    def test_m2m_filter_on_bridge_contract(self, contact_queryset: QuerySet) -> None:
        """Test many-to-many with filter on bridge table."""
        contract = RelationshipContracts.M2M_FILTER_ON_BRIDGE
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("join") == contract["expected_params"]["join"]
        assert result.get("select") == contract["expected_params"]["select"]
        # Verify where clauses on both bridge and target
        where = result["where"]
        assert len(where) == 2
        assert any("gc.status" in str(w) for w in where)
        assert any("grp.is_active" in str(w) for w in where)

    def test_m2m_response_parsing(self) -> None:
        """Test parsing response with many-to-many data."""
        contract = RelationshipResponseContracts.RESPONSE_WITH_M2M
        response = decode_response(json.dumps(contract["json"]).encode())

        assert len(response.values) == contract["expected"]["values_count"]
        # Same contact, different groups
        assert response.values[0]["id"] == response.values[1]["id"]
        assert response.values[0]["grp.title"] != response.values[1]["grp.title"]


# =============================================================================
# PREFETCH RELATED TESTS
# =============================================================================


class TestPrefetchRelated:
    """Test prefetching related entities."""

    def test_prefetch_emails_contract(self, contact_queryset: QuerySet) -> None:
        """Test prefetch all emails for contacts."""
        contract = RelationshipContracts.PREFETCH_EMAILS
        qs = contract["queryset_call"](contact_queryset)
        params = qs._build_params()
        result = to_dict(params)

        assert result.get("select") == contract["expected_params"]["select"]
        assert result.get("join") == contract["expected_params"]["join"]


# =============================================================================
# RELATIONSHIP DESCRIPTOR TESTS
# =============================================================================


class TestForeignKeyDescriptor:
    """Test ForeignKey descriptor behavior."""

    def test_foreignkey_class_access(self) -> None:
        """Test ForeignKey returns descriptor when accessed on class."""
        fk = ForeignKey("Contact", "employer_id")
        fk.__set_name__(Mock, "employer")

        # Class access returns the descriptor itself
        result = fk.__get__(None, Mock)
        assert isinstance(result, ForeignKey)

    def test_foreignkey_instance_access(self, mock_entity: Mock) -> None:
        """Test ForeignKey returns accessor when accessed on instance."""
        fk = ForeignKey("Contact", "employer_id")
        fk.__set_name__(Mock, "employer")

        # Instance access returns accessor
        result = fk.__get__(mock_entity, type(mock_entity))
        assert isinstance(result, ForeignKeyAccessor)

    @pytest.mark.asyncio
    async def test_foreignkey_accessor_loads_related(self, mock_entity: Mock) -> None:
        """Test ForeignKeyAccessor loads related entity."""
        mock_entity.employer_id = 10
        mock_entity._client.request.return_value = APIResponse(
            values=[{"id": 10, "organization_name": "Acme Corp"}],
            count=1,
        )

        accessor = ForeignKeyAccessor(mock_entity, "Contact", "employer_id", "employer")
        result = await accessor

        assert result is not None
        assert result["id"] == 10
        assert result["organization_name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_foreignkey_accessor_returns_none_for_null_fk(self, mock_entity: Mock) -> None:
        """Test ForeignKeyAccessor returns None for null FK."""
        mock_entity.employer_id = None

        accessor = ForeignKeyAccessor(mock_entity, "Contact", "employer_id", "employer")
        result = await accessor

        assert result is None
        # No API call should be made
        mock_entity._client.request.assert_not_called()


class TestRelatedFieldDescriptor:
    """Test RelatedField descriptor behavior."""

    def test_relatedfield_class_access(self) -> None:
        """Test RelatedField returns descriptor when accessed on class."""
        rf = RelatedField("Activity", "source_contact_id")

        # Class access returns the descriptor itself
        result = rf.__get__(None, Mock)
        assert isinstance(result, RelatedField)

    def test_relatedfield_instance_access(self, mock_entity: Mock) -> None:
        """Test RelatedField returns manager when accessed on instance."""
        rf = RelatedField("Activity", "source_contact_id")

        # Instance access returns manager
        result = rf.__get__(mock_entity, type(mock_entity))
        assert isinstance(result, RelatedManager)


class TestRelatedManager:
    """Test RelatedManager behavior."""

    def test_related_manager_creates_filtered_queryset(self, mock_entity: Mock) -> None:
        """Test RelatedManager creates QuerySet filtered by FK."""
        manager = RelatedManager(mock_entity, "Activity", "source_contact_id")

        # Get the underlying queryset
        qs = manager._get_queryset()

        assert isinstance(qs, QuerySet)
        assert qs._entity == "Activity"
        # Should have filter for source_contact_id = parent.id
        assert len(qs._where) == 1
        assert qs._where[0] == ["source_contact_id", "=", mock_entity.id]

    def test_related_manager_filter_chains(self, mock_entity: Mock) -> None:
        """Test RelatedManager filter chains correctly."""
        manager = RelatedManager(mock_entity, "Activity", "source_contact_id")

        qs = manager.filter(status_id=2, activity_type_id=1)

        # Should have FK filter + additional filters
        assert len(qs._where) == 3
        assert ["source_contact_id", "=", mock_entity.id] in qs._where
        assert ["status_id", "=", 2] in qs._where
        assert ["activity_type_id", "=", 1] in qs._where

    def test_related_manager_select(self, mock_entity: Mock) -> None:
        """Test RelatedManager select method."""
        manager = RelatedManager(mock_entity, "Activity", "source_contact_id")

        qs = manager.select("id", "subject", "activity_date_time")

        assert qs._select == ["id", "subject", "activity_date_time"]

    def test_related_manager_order_by(self, mock_entity: Mock) -> None:
        """Test RelatedManager order_by method."""
        manager = RelatedManager(mock_entity, "Activity", "source_contact_id")

        qs = manager.order_by("-activity_date_time")

        assert qs._order_by == {"activity_date_time": "DESC"}

    def test_related_manager_limit(self, mock_entity: Mock) -> None:
        """Test RelatedManager limit method."""
        manager = RelatedManager(mock_entity, "Activity", "source_contact_id")

        qs = manager.limit(10)

        assert qs._limit == 10


class TestManyToManyField:
    """Test ManyToManyField descriptor behavior."""

    def test_m2m_field_class_access(self) -> None:
        """Test ManyToManyField returns descriptor when accessed on class."""
        m2m = ManyToManyField(
            "Group",
            through="GroupContact",
            through_fk="contact_id",
            target_fk="group_id",
        )

        result = m2m.__get__(None, Mock)
        assert isinstance(result, ManyToManyField)

    def test_m2m_field_instance_access(self, mock_entity: Mock) -> None:
        """Test ManyToManyField returns manager when accessed on instance."""
        m2m = ManyToManyField(
            "Group",
            through="GroupContact",
            through_fk="contact_id",
            target_fk="group_id",
        )

        result = m2m.__get__(mock_entity, type(mock_entity))
        assert isinstance(result, ManyToManyManager)


class TestManyToManyManager:
    """Test ManyToManyManager behavior."""

    @pytest.mark.asyncio
    async def test_m2m_manager_all_queries_bridge_then_target(self, mock_entity: Mock) -> None:
        """Test ManyToManyManager.all() queries bridge then target."""
        mock_entity._client.request = AsyncMock()

        # First call returns junction records
        # Second call returns target entities
        mock_entity._client.request.side_effect = [
            APIResponse(
                values=[{"group_id": 1}, {"group_id": 2}],
                count=2,
            ),
            APIResponse(
                values=[
                    {"id": 1, "title": "Group A"},
                    {"id": 2, "title": "Group B"},
                ],
                count=2,
            ),
        ]

        manager = ManyToManyManager(
            mock_entity,
            "Group",
            "GroupContact",
            "contact_id",
            "group_id",
        )

        result = await manager.all()

        # Should have made 2 requests
        assert mock_entity._client.request.call_count == 2

        # Should return target entities
        assert len(result) == 2
        assert result[0]["title"] == "Group A"
        assert result[1]["title"] == "Group B"

    @pytest.mark.asyncio
    async def test_m2m_manager_returns_empty_for_no_junctions(self, mock_entity: Mock) -> None:
        """Test ManyToManyManager returns empty list when no junctions exist."""
        mock_entity._client.request = AsyncMock()
        mock_entity._client.request.return_value = APIResponse(values=[], count=0)

        manager = ManyToManyManager(
            mock_entity,
            "Group",
            "GroupContact",
            "contact_id",
            "group_id",
        )

        result = await manager.all()

        assert result == []
        # Should only make 1 request (junction query)
        assert mock_entity._client.request.call_count == 1


# =============================================================================
# RELATIONSHIP REGISTRY TESTS
# =============================================================================


class TestRelationshipRegistry:
    """Test relationship registration and introspection."""

    def test_register_relationship(self) -> None:
        """Test registering a relationship."""
        register_relationship(
            entity_name="TestContact",
            field_name="test_activities",
            relationship_type="related",
            related_entity="Activity",
            foreign_key="source_contact_id",
        )

        relationships = get_relationships("TestContact")
        assert "test_activities" in relationships
        assert relationships["test_activities"]["type"] == "related"
        assert relationships["test_activities"]["related_entity"] == "Activity"

    def test_get_reverse_relationships(self) -> None:
        """Test getting reverse relationships."""
        register_relationship(
            entity_name="TestActivity",
            field_name="source_contact",
            relationship_type="foreign_key",
            related_entity="TestContact2",
            foreign_key="source_contact_id",
        )

        reverse = get_reverse_relationships("TestContact2")
        assert len(reverse) >= 1
        matching = [r for r in reverse if r["source_entity"] == "TestActivity"]
        assert len(matching) == 1
        assert matching[0]["field_name"] == "source_contact"


# =============================================================================
# EDGE CASES
# =============================================================================


class TestRelationshipEdgeCases:
    """Test edge cases in relationship handling."""

    def test_dot_notation_preserved_in_filter(self, contact_queryset: QuerySet) -> None:
        """Test dot notation is preserved in filter conditions."""
        qs = contact_queryset.filter(**{"email_primary.email__contains": "@example.com"})
        params = qs._build_params()
        result = to_dict(params)

        # The field name should preserve dot notation
        where = result["where"][0]
        assert where[0] == "email_primary.email"
        assert where[1] == "CONTAINS"
        assert where[2] == "@example.com"

    def test_dot_notation_preserved_in_order_by(self, contact_queryset: QuerySet) -> None:
        """Test dot notation is preserved in order_by."""
        qs = contact_queryset.order_by("-address_primary.city", "email_primary.email")
        params = qs._build_params()
        result = to_dict(params)

        assert result["orderBy"]["address_primary.city"] == "DESC"
        assert result["orderBy"]["email_primary.email"] == "ASC"

    def test_multiple_joins_preserve_order(self, contact_queryset: QuerySet) -> None:
        """Test multiple joins preserve declaration order."""
        qs = (
            contact_queryset.join("Email", "email_primary", "e1")
            .join("Phone", "phone_primary", "p1")
            .join("Address", "address_primary", "a1")
        )
        params = qs._build_params()
        result = to_dict(params)

        # Order should be preserved
        assert result["join"][0] == ["Email", "email_primary", "e1"]
        assert result["join"][1] == ["Phone", "phone_primary", "p1"]
        assert result["join"][2] == ["Address", "address_primary", "a1"]

    def test_join_without_alias(self, contact_queryset: QuerySet) -> None:
        """Test join without alias."""
        qs = contact_queryset.join("Email", "email_primary")
        params = qs._build_params()
        result = to_dict(params)

        # Should have join without alias
        assert result["join"] == [["Email", "email_primary"]]

    def test_combined_implicit_and_explicit_joins(self, contact_queryset: QuerySet) -> None:
        """Test combining implicit (dot notation) and explicit joins."""
        qs = contact_queryset.join("Email", "email_primary", "email").select(
            "id",
            "display_name",
            "email.email",  # From explicit join
            "phone_primary.phone",  # Implicit join
            "address_primary.city",  # Implicit join
        )
        params = qs._build_params()
        result = to_dict(params)

        assert result["join"] == [["Email", "email_primary", "email"]]
        assert "email.email" in result["select"]
        assert "phone_primary.phone" in result["select"]
        assert "address_primary.city" in result["select"]


# =============================================================================
# PARAMETRIZED CONTRACT TESTS
# =============================================================================


class TestParametrizedRelationshipContracts:
    """Parametrized tests for comprehensive relationship coverage."""

    @pytest.mark.parametrize(
        ("field", "expected_in_select"),
        [
            ("email_primary.email", True),
            ("email_primary.is_primary", True),
            ("phone_primary.phone", True),
            ("phone_primary.phone_type_id", True),
            ("address_primary.street_address", True),
            ("address_primary.city", True),
            ("address_primary.postal_code", True),
            ("address_primary.country_id", True),
            ("employer_id.organization_name", True),
            ("employer_id.display_name", True),
        ],
    )
    def test_implicit_join_field_selection(
        self,
        contact_queryset: QuerySet,
        field: str,
        expected_in_select: bool,
    ) -> None:
        """Test various implicit join fields are correctly selected."""
        qs = contact_queryset.select("id", field)
        params = qs._build_params()
        result = to_dict(params)

        if expected_in_select:
            assert field in result["select"]

    @pytest.mark.parametrize(
        ("entity", "on_field", "alias", "expected"),
        [
            ("Email", "email_primary", "e", ["Email", "email_primary", "e"]),
            ("Phone", "phone_primary", "p", ["Phone", "phone_primary", "p"]),
            ("Address", "address_primary", "a", ["Address", "address_primary", "a"]),
            ("Activity", "id", "act", ["Activity", "id", "act"]),
            ("GroupContact", "id", "gc", ["GroupContact", "id", "gc"]),
        ],
    )
    def test_explicit_join_variations(
        self,
        contact_queryset: QuerySet,
        entity: str,
        on_field: str,
        alias: str,
        expected: list[str],
    ) -> None:
        """Test various explicit join configurations."""
        qs = contact_queryset.join(entity, on_field, alias)
        params = qs._build_params()
        result = to_dict(params)

        assert result["join"] == [expected]


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestRelationshipIntegration:
    """Integration tests combining multiple relationship features."""

    def test_complex_relationship_query(self, contact_queryset: QuerySet) -> None:
        """Test complex query with multiple relationship features."""
        qs = (
            contact_queryset.filter(is_deleted=False, contact_type="Individual")
            .filter(employer_id__isnull=False)
            .join("GroupContact", "id", "gc")
            .join("Group", "gc.group_id", "grp")
            .select(
                "id",
                "display_name",
                "email_primary.email",
                "employer_id.organization_name",
                "gc.status",
                "grp.title",
            )
            .order_by("-created_date", "display_name")
            .limit(50)
        )

        params = qs._build_params()
        result = to_dict(params)

        # Verify all components present
        assert "select" in result
        assert "where" in result
        assert "join" in result
        assert "orderBy" in result
        assert "limit" in result

        # Verify implicit join fields
        assert "email_primary.email" in result["select"]
        assert "employer_id.organization_name" in result["select"]

        # Verify explicit joins
        assert ["GroupContact", "id", "gc"] in result["join"]
        assert ["Group", "gc.group_id", "grp"] in result["join"]

        # Verify joined entity fields
        assert "gc.status" in result["select"]
        assert "grp.title" in result["select"]

    def test_full_relationship_response_handling(self) -> None:
        """Test handling complete response with multiple relationship types."""
        response_json = {
            "values": [
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "email_primary.email": "john@example.com",
                    "email_primary.is_primary": True,
                    "phone_primary.phone": "(555) 123-4567",
                    "address_primary.city": "New York",
                    "address_primary.country_id": 1228,
                    "employer_id": 10,
                    "employer_id.organization_name": "Acme Corp",
                    "employer_id.display_name": "Acme Corporation",
                    "gc.status": "Added",
                    "gc.group_id": 5,
                    "grp.title": "Newsletter Subscribers",
                    "grp.is_active": True,
                },
            ],
            "count": 1,
            "countFetched": 1,
        }

        response = decode_response(json.dumps(response_json).encode())

        first = response.first
        assert first is not None

        # Verify all relationship data present
        assert first["email_primary.email"] == "john@example.com"
        assert first["phone_primary.phone"] == "(555) 123-4567"
        assert first["address_primary.city"] == "New York"
        assert first["employer_id"] == 10
        assert first["employer_id.organization_name"] == "Acme Corp"
        assert first["gc.status"] == "Added"
        assert first["grp.title"] == "Newsletter Subscribers"
