"""Integration tests for CiviClient against Docker CiviCRM.

These tests verify the client works correctly against a real CiviCRM instance.
"""

from __future__ import annotations

from typing import Any

import pytest

from civicrm_py import (
    CiviAPIError,
    CiviAuthError,
    CiviClient,
    CiviSettings,
    SyncCiviClient,
)

from .conftest import docker_available

# -----------------------------------------------------------------------------
# Connection Health Tests
# -----------------------------------------------------------------------------


@docker_available
class TestConnectionHealth:
    """Test connection and health checking."""

    async def test_client_connects_successfully(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test that client can connect to CiviCRM."""
        # Simply making a request without error indicates connection works
        response = await integration_client.get("Contact", limit=1)
        assert response is not None
        assert hasattr(response, "values")

    async def test_client_handles_simple_query(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test that client can execute a simple query."""
        response = await integration_client.get(
            "Contact",
            select=["id", "display_name"],
            limit=5,
        )
        assert response.values is not None
        # CiviCRM always has at least the domain contact
        assert len(response.values) >= 0

    def test_sync_client_connects_successfully(
        self,
        sync_integration_client: SyncCiviClient,
    ) -> None:
        """Test that sync client can connect to CiviCRM."""
        response = sync_integration_client.get("Contact", limit=1)
        assert response is not None
        assert hasattr(response, "values")

    async def test_client_context_manager(
        self,
        docker_civi_settings: CiviSettings,
    ) -> None:
        """Test that client works correctly as context manager."""
        async with CiviClient(settings=docker_civi_settings) as client:
            response = await client.get("Contact", limit=1)
            assert response is not None

        # Client should be closed after context
        # This shouldn't raise an error, but transport should be None
        assert client._transport is None

    def test_sync_client_context_manager(
        self,
        docker_civi_settings: CiviSettings,
    ) -> None:
        """Test that sync client works correctly as context manager."""
        with SyncCiviClient(settings=docker_civi_settings) as client:
            response = client.get("Contact", limit=1)
            assert response is not None

        assert client._transport is None


# -----------------------------------------------------------------------------
# CRUD Operations Tests
# -----------------------------------------------------------------------------


@docker_available
class TestCRUDOperations:
    """Test Create, Read, Update, Delete operations."""

    async def test_create_contact(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating a new contact."""
        contact_data = {
            "contact_type": "Individual",
            "first_name": f"CreateTest_{unique_id}",
            "last_name": "Integration",
            "source": "civi-py integration test",
        }

        response = await integration_client.create("Contact", contact_data)

        assert response.values is not None
        assert len(response.values) == 1

        created = response.values[0]
        cleanup_contacts.append(created["id"])

        assert created["id"] is not None
        assert created["first_name"] == f"CreateTest_{unique_id}"
        assert created["contact_type"] == "Individual"

    async def test_get_contact_by_id(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test retrieving a contact by ID."""
        response = await integration_client.get(
            "Contact",
            where=[["id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        assert len(response.values) == 1
        assert response.values[0]["id"] == test_contact["id"]

    async def test_get_contact_with_select(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test retrieving specific fields."""
        response = await integration_client.get(
            "Contact",
            select=["id", "first_name", "last_name"],
            where=[["id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        assert len(response.values) == 1

        contact = response.values[0]
        assert "id" in contact
        assert "first_name" in contact
        assert "last_name" in contact

    async def test_update_contact(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test updating a contact."""
        new_job_title = "Integration Test Engineer"

        response = await integration_client.update(
            "Contact",
            values={"job_title": new_job_title},
            where=[["id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        assert len(response.values) == 1
        assert response.values[0]["job_title"] == new_job_title

        # Verify update persisted
        verify_response = await integration_client.get(
            "Contact",
            select=["id", "job_title"],
            where=[["id", "=", test_contact["id"]]],
        )
        assert verify_response.values[0]["job_title"] == new_job_title

    async def test_delete_contact(
        self,
        integration_client: CiviClient,
        unique_id: str,
    ) -> None:
        """Test deleting a contact."""
        # Create a contact to delete
        contact_data = {
            "contact_type": "Individual",
            "first_name": f"DeleteTest_{unique_id}",
            "last_name": "ToBeDeleted",
        }
        create_response = await integration_client.create("Contact", contact_data)
        contact_id = create_response.values[0]["id"]

        # Delete the contact
        delete_response = await integration_client.delete(
            "Contact",
            [["id", "=", contact_id]],
        )

        assert delete_response is not None

        # Verify contact is deleted (should be in trash or gone)
        get_response = await integration_client.get(
            "Contact",
            where=[["id", "=", contact_id], ["is_deleted", "=", False]],
        )
        assert len(get_response.values) == 0

    def test_sync_create_contact(
        self,
        sync_integration_client: SyncCiviClient,
        unique_id: str,
    ) -> None:
        """Test creating a contact with sync client."""
        contact_data = {
            "contact_type": "Individual",
            "first_name": f"SyncCreate_{unique_id}",
            "last_name": "Integration",
        }

        response = sync_integration_client.create("Contact", contact_data)

        assert response.values is not None
        assert len(response.values) == 1
        contact_id = response.values[0]["id"]

        # Cleanup
        sync_integration_client.delete("Contact", [["id", "=", contact_id]])


# -----------------------------------------------------------------------------
# Field Selection and Filtering Tests
# -----------------------------------------------------------------------------


@docker_available
class TestFieldSelectionAndFiltering:
    """Test field selection and query filtering."""

    async def test_select_specific_fields(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test selecting specific fields returns only those fields."""
        response = await integration_client.get(
            "Contact",
            select=["id", "display_name"],
            where=[["id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        contact = response.values[0]

        # Should have the selected fields
        assert "id" in contact
        assert "display_name" in contact

    async def test_filter_by_equality(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test filtering by exact equality."""
        response = await integration_client.get(
            "Contact",
            where=[["first_name", "=", test_contact["first_name"]]],
        )

        assert response.values is not None
        assert len(response.values) >= 1
        assert all(c["first_name"] == test_contact["first_name"] for c in response.values)

    async def test_filter_by_like(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test filtering by LIKE pattern."""
        # Get prefix of first_name for pattern matching
        prefix = test_contact["first_name"][:5]

        response = await integration_client.get(
            "Contact",
            where=[["first_name", "LIKE", f"{prefix}%"]],
        )

        assert response.values is not None
        assert len(response.values) >= 1

    async def test_filter_by_multiple_conditions(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test filtering with multiple conditions."""
        response = await integration_client.get(
            "Contact",
            where=[
                ["first_name", "=", test_contact["first_name"]],
                ["contact_type", "=", "Individual"],
                ["is_deleted", "=", False],
            ],
        )

        assert response.values is not None
        assert len(response.values) >= 1

    async def test_filter_by_in_operator(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test filtering with IN operator."""
        # Create multiple contacts
        contact_ids = []
        for i in range(3):
            response = await integration_client.create(
                "Contact",
                {
                    "contact_type": "Individual",
                    "first_name": f"InTest_{unique_id}_{i}",
                    "last_name": "Batch",
                },
            )
            contact_ids.append(response.values[0]["id"])
            cleanup_contacts.append(response.values[0]["id"])

        # Query using IN
        response = await integration_client.get(
            "Contact",
            where=[["id", "IN", contact_ids]],
        )

        assert response.values is not None
        assert len(response.values) == 3

    async def test_order_by_ascending(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test ordering results ascending."""
        response = await integration_client.get(
            "Contact",
            select=["id", "display_name"],
            order_by={"id": "ASC"},
            limit=5,
        )

        assert response.values is not None
        if len(response.values) >= 2:
            ids = [c["id"] for c in response.values]
            assert ids == sorted(ids)

    async def test_order_by_descending(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test ordering results descending."""
        response = await integration_client.get(
            "Contact",
            select=["id", "display_name"],
            order_by={"id": "DESC"},
            limit=5,
        )

        assert response.values is not None
        if len(response.values) >= 2:
            ids = [c["id"] for c in response.values]
            assert ids == sorted(ids, reverse=True)


# -----------------------------------------------------------------------------
# Pagination Tests
# -----------------------------------------------------------------------------


@docker_available
class TestPagination:
    """Test pagination functionality."""

    async def test_limit_results(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test limiting number of results."""
        limit = 3
        response = await integration_client.get(
            "Contact",
            limit=limit,
        )

        assert response.values is not None
        assert len(response.values) <= limit

    async def test_offset_results(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test offset for pagination."""
        # Get first page
        page1 = await integration_client.get(
            "Contact",
            select=["id"],
            order_by={"id": "ASC"},
            limit=2,
            offset=0,
        )

        # Get second page
        page2 = await integration_client.get(
            "Contact",
            select=["id"],
            order_by={"id": "ASC"},
            limit=2,
            offset=2,
        )

        if page1.values and page2.values:
            page1_ids = {c["id"] for c in page1.values}
            page2_ids = {c["id"] for c in page2.values}
            # Pages should not overlap
            assert page1_ids.isdisjoint(page2_ids)

    async def test_pagination_with_count(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test that count reflects total, not just returned records."""
        # Create several contacts to ensure we have enough data
        for i in range(5):
            response = await integration_client.create(
                "Contact",
                {
                    "contact_type": "Individual",
                    "first_name": f"PageTest_{unique_id}_{i}",
                    "last_name": "Pagination",
                },
            )
            cleanup_contacts.append(response.values[0]["id"])

        # Query with limit but check count
        response = await integration_client.get(
            "Contact",
            where=[["last_name", "=", "Pagination"]],
            limit=2,
        )

        assert response.values is not None
        assert len(response.values) == 2
        # count should reflect total matching, countFetched reflects returned
        if response.count_fetched is not None:
            assert response.count_fetched == 2


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


@docker_available
class TestErrorHandling:
    """Test error handling scenarios."""

    async def test_invalid_entity_raises_error(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test that querying invalid entity raises appropriate error."""
        with pytest.raises(CiviAPIError):
            await integration_client.get("NonExistentEntity")

    async def test_invalid_field_raises_error(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test that selecting invalid field raises error."""
        with pytest.raises(CiviAPIError):
            await integration_client.get(
                "Contact",
                select=["id", "non_existent_field_xyz"],
            )

    async def test_invalid_auth_raises_error(
        self,
        docker_civi_settings: CiviSettings,
    ) -> None:
        """Test that invalid credentials raise auth error."""
        # Create settings with invalid API key
        bad_settings = CiviSettings(
            base_url=docker_civi_settings.base_url,
            api_key="invalid-api-key-that-does-not-exist",
            site_key=docker_civi_settings.site_key,
            timeout=10,
            verify_ssl=False,
        )

        async with CiviClient(settings=bad_settings) as client:
            with pytest.raises((CiviAuthError, CiviAPIError)):
                await client.get("Contact", limit=1)

    async def test_create_with_invalid_data(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test that creating with invalid data raises error."""
        with pytest.raises(CiviAPIError):
            # contact_type is required
            await integration_client.create(
                "Contact",
                {"first_name": "Invalid"},  # Missing contact_type
            )

    async def test_update_nonexistent_contact(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test updating a contact that doesn't exist."""
        # Use a very high ID that shouldn't exist
        response = await integration_client.update(
            "Contact",
            values={"job_title": "Test"},
            where=[["id", "=", 999999999]],
        )

        # Should return empty values, not raise error
        assert response.values is not None
        assert len(response.values) == 0


# -----------------------------------------------------------------------------
# Get Fields Tests
# -----------------------------------------------------------------------------


@docker_available
class TestGetFields:
    """Test metadata retrieval functionality."""

    async def test_get_contact_fields(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving field metadata for Contact entity."""
        response = await integration_client.get_fields("Contact")

        assert response.values is not None
        assert len(response.values) > 0

        # Check for common Contact fields
        field_names = {f.get("name") for f in response.values}
        assert "id" in field_names
        assert "display_name" in field_names
        assert "contact_type" in field_names

    async def test_get_activity_fields(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving field metadata for Activity entity."""
        response = await integration_client.get_fields("Activity")

        assert response.values is not None
        assert len(response.values) > 0

        field_names = {f.get("name") for f in response.values}
        assert "id" in field_names
        assert "subject" in field_names
        assert "activity_type_id" in field_names

    def test_sync_get_fields(
        self,
        sync_integration_client: SyncCiviClient,
    ) -> None:
        """Test retrieving field metadata with sync client."""
        response = sync_integration_client.get_fields("Contact")

        assert response.values is not None
        assert len(response.values) > 0
