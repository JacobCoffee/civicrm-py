"""Integration tests for entity operations against Docker CiviCRM.

Tests multiple entity types and their relationships.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from civicrm_py import CiviClient

from .conftest import docker_available

# -----------------------------------------------------------------------------
# Contact Entity Tests
# -----------------------------------------------------------------------------


@docker_available
class TestContactEntity:
    """Integration tests for Contact entity operations."""

    async def test_create_individual_contact(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating an Individual contact type."""
        contact_data = {
            "contact_type": "Individual",
            "first_name": f"John_{unique_id}",
            "last_name": "Doe",
            "job_title": "Software Engineer",
            "source": "Integration Test",
        }

        response = await integration_client.create("Contact", contact_data)
        cleanup_contacts.append(response.values[0]["id"])

        assert response.values[0]["contact_type"] == "Individual"
        assert response.values[0]["first_name"] == f"John_{unique_id}"

    async def test_create_organization_contact(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating an Organization contact type."""
        contact_data = {
            "contact_type": "Organization",
            "organization_name": f"Acme Corp {unique_id}",
            "legal_name": f"Acme Corporation {unique_id}",
            "source": "Integration Test",
        }

        response = await integration_client.create("Contact", contact_data)
        cleanup_contacts.append(response.values[0]["id"])

        assert response.values[0]["contact_type"] == "Organization"
        assert response.values[0]["organization_name"] == f"Acme Corp {unique_id}"

    async def test_create_household_contact(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating a Household contact type."""
        contact_data = {
            "contact_type": "Household",
            "household_name": f"The Smith Family {unique_id}",
            "source": "Integration Test",
        }

        response = await integration_client.create("Contact", contact_data)
        cleanup_contacts.append(response.values[0]["id"])

        assert response.values[0]["contact_type"] == "Household"
        assert response.values[0]["household_name"] == f"The Smith Family {unique_id}"

    async def test_filter_contacts_by_type(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test filtering contacts by contact_type."""
        response = await integration_client.get(
            "Contact",
            where=[["contact_type", "=", "Individual"]],
            limit=10,
        )

        assert response.values is not None
        assert all(c["contact_type"] == "Individual" for c in response.values)

    async def test_update_contact_communication_preferences(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
    ) -> None:
        """Test updating contact communication preferences."""
        response = await integration_client.update(
            "Contact",
            values={
                "do_not_email": True,
                "do_not_phone": False,
                "preferred_language": "en_US",
            },
            where=[["id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        updated = response.values[0]
        assert updated["do_not_email"] is True
        assert updated["do_not_phone"] is False


# -----------------------------------------------------------------------------
# Activity Entity Tests
# -----------------------------------------------------------------------------


@docker_available
class TestActivityEntity:
    """Integration tests for Activity entity operations."""

    async def test_create_activity(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        cleanup_activities: list[int],
        unique_id: str,
    ) -> None:
        """Test creating an activity."""
        activity_data = {
            "activity_type_id": 1,  # Meeting
            "subject": f"Test Meeting {unique_id}",
            "activity_date_time": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "source_contact_id": test_contact["id"],
            "status_id": 1,  # Scheduled
            "priority_id": 2,  # Normal
            "duration": 60,
            "location": "Conference Room A",
        }

        response = await integration_client.create("Activity", activity_data)
        cleanup_activities.append(response.values[0]["id"])

        created = response.values[0]
        assert created["subject"] == f"Test Meeting {unique_id}"
        assert created["source_contact_id"] == test_contact["id"]
        assert created["duration"] == 60

    async def test_get_activities_by_contact(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        test_activity: dict[str, Any],
    ) -> None:
        """Test retrieving activities for a specific contact."""
        response = await integration_client.get(
            "Activity",
            where=[["source_contact_id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        assert len(response.values) >= 1
        assert any(a["id"] == test_activity["id"] for a in response.values)

    async def test_update_activity_status(
        self,
        integration_client: CiviClient,
        test_activity: dict[str, Any],
    ) -> None:
        """Test updating activity status."""
        response = await integration_client.update(
            "Activity",
            values={"status_id": 2},  # Completed
            where=[["id", "=", test_activity["id"]]],
        )

        assert response.values is not None
        assert response.values[0]["status_id"] == 2

    async def test_filter_activities_by_type(
        self,
        integration_client: CiviClient,
        test_activity: dict[str, Any],
    ) -> None:
        """Test filtering activities by type."""
        response = await integration_client.get(
            "Activity",
            where=[["activity_type_id", "=", test_activity["activity_type_id"]]],
            limit=10,
        )

        assert response.values is not None
        assert all(a["activity_type_id"] == test_activity["activity_type_id"] for a in response.values)

    async def test_filter_activities_by_date_range(
        self,
        integration_client: CiviClient,
        test_activity: dict[str, Any],
    ) -> None:
        """Test filtering activities by date range."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        response = await integration_client.get(
            "Activity",
            where=[
                ["activity_date_time", ">=", f"{today} 00:00:00"],
                ["activity_date_time", "<=", f"{today} 23:59:59"],
            ],
        )

        assert response.values is not None
        # Should include our test activity from today
        activity_ids = {a["id"] for a in response.values}
        assert test_activity["id"] in activity_ids


# -----------------------------------------------------------------------------
# Email Entity Tests
# -----------------------------------------------------------------------------


@docker_available
class TestEmailEntity:
    """Integration tests for Email entity operations."""

    async def test_create_email_for_contact(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Test creating an email for a contact."""
        email_data = {
            "contact_id": test_contact["id"],
            "email": f"test_{unique_id}@example.com",
            "location_type_id": 1,  # Home
            "is_primary": True,
        }

        response = await integration_client.create("Email", email_data)

        assert response.values is not None
        created = response.values[0]
        assert created["email"] == f"test_{unique_id}@example.com"
        assert created["contact_id"] == test_contact["id"]

        # Cleanup
        await integration_client.delete("Email", [["id", "=", created["id"]]])

    async def test_get_emails_by_contact(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Test retrieving emails for a contact."""
        # Create an email first
        email_data = {
            "contact_id": test_contact["id"],
            "email": f"gettest_{unique_id}@example.com",
            "location_type_id": 1,
        }
        create_response = await integration_client.create("Email", email_data)
        email_id = create_response.values[0]["id"]

        try:
            # Get emails for contact
            response = await integration_client.get(
                "Email",
                where=[["contact_id", "=", test_contact["id"]]],
            )

            assert response.values is not None
            assert len(response.values) >= 1
            assert any(e["id"] == email_id for e in response.values)
        finally:
            # Cleanup
            await integration_client.delete("Email", [["id", "=", email_id]])

    async def test_update_email_primary_status(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Test updating email primary status."""
        # Create email
        email_data = {
            "contact_id": test_contact["id"],
            "email": f"primary_{unique_id}@example.com",
            "location_type_id": 1,
            "is_primary": False,
        }
        create_response = await integration_client.create("Email", email_data)
        email_id = create_response.values[0]["id"]

        try:
            # Update to primary
            response = await integration_client.update(
                "Email",
                values={"is_primary": True},
                where=[["id", "=", email_id]],
            )

            assert response.values is not None
            assert response.values[0]["is_primary"] is True
        finally:
            await integration_client.delete("Email", [["id", "=", email_id]])


# -----------------------------------------------------------------------------
# Entity Relationship Tests
# -----------------------------------------------------------------------------


@docker_available
class TestEntityRelationships:
    """Test relationships between entities."""

    async def test_contact_with_activities(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        cleanup_activities: list[int],
        unique_id: str,
    ) -> None:
        """Test creating multiple activities for a contact."""
        # Create multiple activities
        for i in range(3):
            activity_data = {
                "activity_type_id": 1,
                "subject": f"Activity {i} for {unique_id}",
                "activity_date_time": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
                "source_contact_id": test_contact["id"],
                "status_id": 1,
            }
            response = await integration_client.create("Activity", activity_data)
            cleanup_activities.append(response.values[0]["id"])

        # Query activities for this contact
        response = await integration_client.get(
            "Activity",
            where=[["source_contact_id", "=", test_contact["id"]]],
        )

        assert response.values is not None
        assert len(response.values) >= 3

    async def test_contact_with_multiple_emails(
        self,
        integration_client: CiviClient,
        test_contact: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Test creating multiple emails for a contact."""
        email_ids = []

        try:
            # Create work and home emails
            locations = [("work", 2), ("home", 1)]
            for label, location_id in locations:
                email_data = {
                    "contact_id": test_contact["id"],
                    "email": f"{label}_{unique_id}@example.com",
                    "location_type_id": location_id,
                }
                response = await integration_client.create("Email", email_data)
                email_ids.append(response.values[0]["id"])

            # Query all emails for contact
            response = await integration_client.get(
                "Email",
                where=[["contact_id", "=", test_contact["id"]]],
            )

            assert response.values is not None
            assert len(response.values) >= 2

        finally:
            # Cleanup
            for email_id in email_ids:
                await integration_client.delete("Email", [["id", "=", email_id]])

    async def test_organization_with_employees(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating organization with employee contacts."""
        # Create organization
        org_data = {
            "contact_type": "Organization",
            "organization_name": f"Test Org {unique_id}",
        }
        org_response = await integration_client.create("Contact", org_data)
        org_id = org_response.values[0]["id"]
        cleanup_contacts.append(org_id)

        # Create employees linked to organization
        employee_ids = []
        for i in range(2):
            emp_data = {
                "contact_type": "Individual",
                "first_name": f"Employee{i}",
                "last_name": unique_id,
                "employer_id": org_id,
            }
            response = await integration_client.create("Contact", emp_data)
            employee_ids.append(response.values[0]["id"])
            cleanup_contacts.append(response.values[0]["id"])

        # Query employees of this organization
        response = await integration_client.get(
            "Contact",
            where=[["employer_id", "=", org_id]],
        )

        assert response.values is not None
        assert len(response.values) == 2
        assert all(e["employer_id"] == org_id for e in response.values)


# -----------------------------------------------------------------------------
# Bulk Operations Tests
# -----------------------------------------------------------------------------


@docker_available
class TestBulkOperations:
    """Test bulk create, update, and delete operations."""

    async def test_bulk_create_contacts(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test creating multiple contacts in sequence."""
        created_ids = []

        for i in range(5):
            contact_data = {
                "contact_type": "Individual",
                "first_name": f"Bulk{i}",
                "last_name": f"Test_{unique_id}",
            }
            response = await integration_client.create("Contact", contact_data)
            created_ids.append(response.values[0]["id"])
            cleanup_contacts.append(response.values[0]["id"])

        # Verify all were created
        response = await integration_client.get(
            "Contact",
            where=[["id", "IN", created_ids]],
        )

        assert response.values is not None
        assert len(response.values) == 5

    async def test_bulk_update_contacts(
        self,
        integration_client: CiviClient,
        cleanup_contacts: list[int],
        unique_id: str,
    ) -> None:
        """Test updating multiple contacts at once."""
        # Create contacts to update
        created_ids = []
        for i in range(3):
            contact_data = {
                "contact_type": "Individual",
                "first_name": f"BulkUpdate{i}",
                "last_name": f"Test_{unique_id}",
                "source": "Before Update",
            }
            response = await integration_client.create("Contact", contact_data)
            created_ids.append(response.values[0]["id"])
            cleanup_contacts.append(response.values[0]["id"])

        # Update all at once
        response = await integration_client.update(
            "Contact",
            values={"source": "After Update"},
            where=[["id", "IN", created_ids]],
        )

        assert response.values is not None
        assert len(response.values) == 3
        assert all(c["source"] == "After Update" for c in response.values)

    async def test_bulk_delete_contacts(
        self,
        integration_client: CiviClient,
        unique_id: str,
    ) -> None:
        """Test deleting multiple contacts at once."""
        # Create contacts to delete
        created_ids = []
        for i in range(3):
            contact_data = {
                "contact_type": "Individual",
                "first_name": f"BulkDelete{i}",
                "last_name": f"Test_{unique_id}",
            }
            response = await integration_client.create("Contact", contact_data)
            created_ids.append(response.values[0]["id"])

        # Delete all at once
        await integration_client.delete(
            "Contact",
            [["id", "IN", created_ids]],
        )

        # Verify deletion
        response = await integration_client.get(
            "Contact",
            where=[["id", "IN", created_ids], ["is_deleted", "=", False]],
        )

        assert response.values is not None
        assert len(response.values) == 0


# -----------------------------------------------------------------------------
# Additional Entity Type Tests
# -----------------------------------------------------------------------------


@docker_available
class TestAdditionalEntities:
    """Test other entity types available in CiviCRM."""

    async def test_get_option_values(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving option values (lookup tables)."""
        # Get activity types
        response = await integration_client.get(
            "OptionValue",
            where=[["option_group_id:name", "=", "activity_type"]],
            limit=10,
        )

        assert response.values is not None
        assert len(response.values) > 0

    async def test_get_location_types(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving location types."""
        response = await integration_client.get(
            "LocationType",
            limit=10,
        )

        assert response.values is not None
        assert len(response.values) > 0
        # Should have common types like Home, Work
        names = {lt.get("name") for lt in response.values}
        assert "Home" in names or "Work" in names or len(names) > 0

    async def test_get_country_list(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving country list."""
        response = await integration_client.get(
            "Country",
            select=["id", "name", "iso_code"],
            limit=10,
        )

        assert response.values is not None
        assert len(response.values) > 0
        # Each country should have iso_code
        assert all("iso_code" in c for c in response.values)

    async def test_get_state_province_for_country(
        self,
        integration_client: CiviClient,
    ) -> None:
        """Test retrieving states/provinces for a country."""
        # Get US country ID first
        country_response = await integration_client.get(
            "Country",
            where=[["iso_code", "=", "US"]],
            select=["id"],
        )

        if country_response.values:
            us_id = country_response.values[0]["id"]

            # Get states for US
            response = await integration_client.get(
                "StateProvince",
                where=[["country_id", "=", us_id]],
                limit=10,
            )

            assert response.values is not None
            assert len(response.values) > 0
