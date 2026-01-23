"""Showcase services for civi-py examples.

Provides high-level operations for demonstrating civi-py capabilities.
These services wrap the CiviClient with common patterns used in demo applications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from civi_py.core.exceptions import CiviConnectionError, CiviError

if TYPE_CHECKING:
    from civi_py.core.client import CiviClient, SyncCiviClient


@dataclass
class PaginatedResult:
    """Result container for paginated queries."""

    items: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 25
    has_next: bool = False
    has_prev: bool = False
    error: str | None = None

    @property
    def pages(self) -> int:
        """Total number of pages."""
        if self.per_page <= 0:
            return 0
        return (self.total + self.per_page - 1) // self.per_page


@dataclass
class DashboardStats:
    """Statistics for the dashboard overview."""

    total_contacts: int = 0
    total_individuals: int = 0
    total_organizations: int = 0
    total_households: int = 0
    total_activities: int = 0
    total_contributions: int = 0
    total_events: int = 0
    recent_contacts: list[dict[str, Any]] = field(default_factory=list)
    recent_activities: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class CiviShowcase:
    """Async showcase service for demonstrating civi-py capabilities.

    Provides high-level methods for common CiviCRM operations used in demos.

    Usage:
        async with CiviClient() as client:
            showcase = CiviShowcase(client)
            result = await showcase.list_contacts(page=1, per_page=25)
    """

    def __init__(self, client: CiviClient) -> None:
        """Initialize the showcase service.

        Args:
            client: Async CiviCRM client instance.
        """
        self.client = client

    # -------------------------------------------------------------------------
    # Dashboard
    # -------------------------------------------------------------------------

    async def get_dashboard_stats(self) -> DashboardStats:
        """Get statistics for the dashboard overview.

        Returns:
            Dashboard statistics including counts and recent items.
        """
        stats = DashboardStats()

        try:
            # Get contact counts by type
            contacts_response = await self.client.get(
                "Contact",
                select=["id", "contact_type"],
                where=[["is_deleted", "=", False]],
                limit=0,  # Just get count
            )
            stats.total_contacts = contacts_response.count or 0

            # Count by type
            for contact_type in ["Individual", "Organization", "Household"]:
                response = await self.client.get(
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["contact_type", "=", contact_type],
                    ],
                    limit=0,
                )
                count = response.count or 0
                if contact_type == "Individual":
                    stats.total_individuals = count
                elif contact_type == "Organization":
                    stats.total_organizations = count
                else:
                    stats.total_households = count

            # Get activity count
            activities_response = await self.client.get(
                "Activity",
                select=["id"],
                where=[["is_deleted", "=", False]],
                limit=0,
            )
            stats.total_activities = activities_response.count or 0

            # Get contribution count
            contributions_response = await self.client.get(
                "Contribution",
                select=["id"],
                limit=0,
            )
            stats.total_contributions = contributions_response.count or 0

            # Get event count
            events_response = await self.client.get(
                "Event",
                select=["id"],
                where=[["is_active", "=", True]],
                limit=0,
            )
            stats.total_events = events_response.count or 0

            # Get recent contacts
            recent_contacts_response = await self.client.get(
                "Contact",
                select=["id", "display_name", "contact_type", "created_date"],
                where=[["is_deleted", "=", False]],
                order_by={"created_date": "DESC"},
                limit=5,
            )
            stats.recent_contacts = recent_contacts_response.values or []

            # Get recent activities
            recent_activities_response = await self.client.get(
                "Activity",
                select=["id", "subject", "activity_type_id:label", "activity_date_time", "status_id:label"],
                where=[["is_deleted", "=", False]],
                order_by={"activity_date_time": "DESC"},
                limit=5,
            )
            stats.recent_activities = recent_activities_response.values or []

        except CiviConnectionError:
            stats.error = "Cannot connect to CiviCRM. Make sure the infrastructure is running."
        except CiviError as e:
            stats.error = f"CiviCRM error: {e}"

        return stats

    # -------------------------------------------------------------------------
    # Contacts
    # -------------------------------------------------------------------------

    async def list_contacts(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_type: str | None = None,
    ) -> PaginatedResult:
        """List contacts with pagination and optional filtering.

        Args:
            page: Page number (1-indexed).
            per_page: Items per page.
            search: Search term for display_name.
            contact_type: Filter by contact type (Individual, Organization, Household).

        Returns:
            Paginated result with contacts.
        """
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            # Build where clause
            where: list[list[Any]] = [["is_deleted", "=", False]]
            if search:
                where.append(["display_name", "CONTAINS", search])
            if contact_type:
                where.append(["contact_type", "=", contact_type])

            # Get total count first
            count_response = await self.client.get(
                "Contact",
                select=["id"],
                where=where,
                limit=0,
            )
            result.total = count_response.count or 0

            # Get paginated results
            offset = (page - 1) * per_page
            response = await self.client.get(
                "Contact",
                select=[
                    "id",
                    "display_name",
                    "first_name",
                    "last_name",
                    "contact_type",
                    "email_primary.email",
                    "phone_primary.phone",
                    "created_date",
                ],
                where=where,
                order_by={"display_name": "ASC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM. Make sure the infrastructure is running."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    async def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        """Get a single contact by ID.

        Args:
            contact_id: The contact ID.

        Returns:
            Contact data or None if not found.
        """
        try:
            response = await self.client.get(
                "Contact",
                select=[
                    "id",
                    "display_name",
                    "first_name",
                    "last_name",
                    "middle_name",
                    "contact_type",
                    "email_primary.email",
                    "phone_primary.phone",
                    "address_primary.street_address",
                    "address_primary.city",
                    "address_primary.state_province_id:label",
                    "address_primary.postal_code",
                    "address_primary.country_id:label",
                    "created_date",
                    "modified_date",
                    "job_title",
                    "employer_id.display_name",
                ],
                where=[["id", "=", contact_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def create_contact(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contact.

        Args:
            data: Contact field values.

        Returns:
            Created contact data or None on error.
        """
        try:
            response = await self.client.create("Contact", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def update_contact(self, contact_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing contact.

        Args:
            contact_id: The contact ID.
            data: Field values to update.

        Returns:
            Updated contact data or None on error.
        """
        try:
            response = await self.client.update(
                "Contact",
                values=data,
                where=[["id", "=", contact_id]],
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact (soft delete by setting is_deleted).

        Args:
            contact_id: The contact ID.

        Returns:
            True if deleted successfully.
        """
        try:
            await self.client.update(
                "Contact",
                values={"is_deleted": True},
                where=[["id", "=", contact_id]],
            )
            return True
        except CiviError:
            return False

    # -------------------------------------------------------------------------
    # Activities
    # -------------------------------------------------------------------------

    async def list_activities(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_id: int | None = None,
    ) -> PaginatedResult:
        """List activities with pagination.

        Args:
            page: Page number.
            per_page: Items per page.
            search: Search in subject.
            contact_id: Filter by contact.

        Returns:
            Paginated result with activities.
        """
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = [["is_deleted", "=", False]]
            if search:
                where.append(["subject", "CONTAINS", search])
            if contact_id:
                where.append(["source_contact_id", "=", contact_id])

            count_response = await self.client.get(
                "Activity",
                select=["id"],
                where=where,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = await self.client.get(
                "Activity",
                select=[
                    "id",
                    "subject",
                    "activity_type_id:label",
                    "status_id:label",
                    "activity_date_time",
                    "source_contact_id.display_name",
                    "details",
                ],
                where=where,
                order_by={"activity_date_time": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    async def get_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Get a single activity by ID."""
        try:
            response = await self.client.get(
                "Activity",
                select=[
                    "id",
                    "subject",
                    "activity_type_id:label",
                    "status_id:label",
                    "priority_id:label",
                    "activity_date_time",
                    "duration",
                    "location",
                    "details",
                    "source_contact_id",
                    "source_contact_id.display_name",
                    "created_date",
                    "modified_date",
                ],
                where=[["id", "=", activity_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def create_activity(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new activity."""
        try:
            response = await self.client.create("Activity", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def delete_activity(self, activity_id: int) -> bool:
        """Delete an activity."""
        try:
            await self.client.update(
                "Activity",
                values={"is_deleted": True},
                where=[["id", "=", activity_id]],
            )
            return True
        except CiviError:
            return False

    # -------------------------------------------------------------------------
    # Contributions
    # -------------------------------------------------------------------------

    async def list_contributions(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        contact_id: int | None = None,
    ) -> PaginatedResult:
        """List contributions with pagination."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = []
            if contact_id:
                where.append(["contact_id", "=", contact_id])

            count_response = await self.client.get(
                "Contribution",
                select=["id"],
                where=where if where else None,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = await self.client.get(
                "Contribution",
                select=[
                    "id",
                    "contact_id",
                    "contact_id.display_name",
                    "total_amount",
                    "currency",
                    "financial_type_id:label",
                    "contribution_status_id:label",
                    "receive_date",
                    "source",
                ],
                where=where if where else None,
                order_by={"receive_date": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    async def get_contribution(self, contribution_id: int) -> dict[str, Any] | None:
        """Get a single contribution by ID."""
        try:
            response = await self.client.get(
                "Contribution",
                select=[
                    "id",
                    "contact_id",
                    "contact_id.display_name",
                    "total_amount",
                    "net_amount",
                    "fee_amount",
                    "currency",
                    "financial_type_id:label",
                    "contribution_status_id:label",
                    "payment_instrument_id:label",
                    "receive_date",
                    "receipt_date",
                    "source",
                    "trxn_id",
                    "invoice_id",
                    "created_date",
                ],
                where=[["id", "=", contribution_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def create_contribution(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contribution."""
        try:
            response = await self.client.create("Contribution", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    async def list_events(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        active_only: bool = True,
    ) -> PaginatedResult:
        """List events with pagination."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = []
            if active_only:
                where.append(["is_active", "=", True])
            if search:
                where.append(["title", "CONTAINS", search])

            count_response = await self.client.get(
                "Event",
                select=["id"],
                where=where if where else None,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = await self.client.get(
                "Event",
                select=[
                    "id",
                    "title",
                    "event_type_id:label",
                    "start_date",
                    "end_date",
                    "is_active",
                    "is_public",
                    "max_participants",
                    "loc_block_id.address_id.city",
                ],
                where=where if where else None,
                order_by={"start_date": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    async def get_event(self, event_id: int) -> dict[str, Any] | None:
        """Get a single event by ID."""
        try:
            response = await self.client.get(
                "Event",
                select=[
                    "id",
                    "title",
                    "summary",
                    "description",
                    "event_type_id:label",
                    "start_date",
                    "end_date",
                    "is_active",
                    "is_public",
                    "max_participants",
                    "event_full_text",
                    "is_online_registration",
                    "registration_link_text",
                    "created_date",
                ],
                where=[["id", "=", event_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    async def create_event(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new event."""
        try:
            response = await self.client.create("Event", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None


class SyncCiviShowcase:
    """Sync showcase service for WSGI frameworks.

    Provides the same functionality as CiviShowcase but with synchronous methods.

    Usage:
        with SyncCiviClient() as client:
            showcase = SyncCiviShowcase(client)
            result = showcase.list_contacts(page=1, per_page=25)
    """

    def __init__(self, client: SyncCiviClient) -> None:
        """Initialize the sync showcase service.

        Args:
            client: Sync CiviCRM client instance.
        """
        self.client = client

    # -------------------------------------------------------------------------
    # Dashboard
    # -------------------------------------------------------------------------

    def get_dashboard_stats(self) -> DashboardStats:
        """Get statistics for the dashboard overview."""
        stats = DashboardStats()

        try:
            # Get contact counts
            contacts_response = self.client.get(
                "Contact",
                select=["id"],
                where=[["is_deleted", "=", False]],
                limit=0,
            )
            stats.total_contacts = contacts_response.count or 0

            for contact_type in ["Individual", "Organization", "Household"]:
                response = self.client.get(
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["contact_type", "=", contact_type],
                    ],
                    limit=0,
                )
                count = response.count or 0
                if contact_type == "Individual":
                    stats.total_individuals = count
                elif contact_type == "Organization":
                    stats.total_organizations = count
                else:
                    stats.total_households = count

            activities_response = self.client.get(
                "Activity",
                select=["id"],
                where=[["is_deleted", "=", False]],
                limit=0,
            )
            stats.total_activities = activities_response.count or 0

            contributions_response = self.client.get(
                "Contribution",
                select=["id"],
                limit=0,
            )
            stats.total_contributions = contributions_response.count or 0

            events_response = self.client.get(
                "Event",
                select=["id"],
                where=[["is_active", "=", True]],
                limit=0,
            )
            stats.total_events = events_response.count or 0

            recent_contacts_response = self.client.get(
                "Contact",
                select=["id", "display_name", "contact_type", "created_date"],
                where=[["is_deleted", "=", False]],
                order_by={"created_date": "DESC"},
                limit=5,
            )
            stats.recent_contacts = recent_contacts_response.values or []

            recent_activities_response = self.client.get(
                "Activity",
                select=["id", "subject", "activity_type_id:label", "activity_date_time", "status_id:label"],
                where=[["is_deleted", "=", False]],
                order_by={"activity_date_time": "DESC"},
                limit=5,
            )
            stats.recent_activities = recent_activities_response.values or []

        except CiviConnectionError:
            stats.error = "Cannot connect to CiviCRM. Make sure the infrastructure is running."
        except CiviError as e:
            stats.error = f"CiviCRM error: {e}"

        return stats

    # -------------------------------------------------------------------------
    # Contacts
    # -------------------------------------------------------------------------

    def list_contacts(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_type: str | None = None,
    ) -> PaginatedResult:
        """List contacts with pagination and optional filtering."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = [["is_deleted", "=", False]]
            if search:
                where.append(["display_name", "CONTAINS", search])
            if contact_type:
                where.append(["contact_type", "=", contact_type])

            count_response = self.client.get(
                "Contact",
                select=["id"],
                where=where,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = self.client.get(
                "Contact",
                select=[
                    "id",
                    "display_name",
                    "first_name",
                    "last_name",
                    "contact_type",
                    "email_primary.email",
                    "phone_primary.phone",
                    "created_date",
                ],
                where=where,
                order_by={"display_name": "ASC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM. Make sure the infrastructure is running."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        """Get a single contact by ID."""
        try:
            response = self.client.get(
                "Contact",
                select=[
                    "id",
                    "display_name",
                    "first_name",
                    "last_name",
                    "middle_name",
                    "contact_type",
                    "email_primary.email",
                    "phone_primary.phone",
                    "address_primary.street_address",
                    "address_primary.city",
                    "address_primary.state_province_id:label",
                    "address_primary.postal_code",
                    "address_primary.country_id:label",
                    "created_date",
                    "modified_date",
                    "job_title",
                    "employer_id.display_name",
                ],
                where=[["id", "=", contact_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def create_contact(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contact."""
        try:
            response = self.client.create("Contact", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def update_contact(self, contact_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing contact."""
        try:
            response = self.client.update(
                "Contact",
                values=data,
                where=[["id", "=", contact_id]],
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def delete_contact(self, contact_id: int) -> bool:
        """Delete a contact."""
        try:
            self.client.update(
                "Contact",
                values={"is_deleted": True},
                where=[["id", "=", contact_id]],
            )
            return True
        except CiviError:
            return False

    # -------------------------------------------------------------------------
    # Activities
    # -------------------------------------------------------------------------

    def list_activities(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_id: int | None = None,
    ) -> PaginatedResult:
        """List activities with pagination."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = [["is_deleted", "=", False]]
            if search:
                where.append(["subject", "CONTAINS", search])
            if contact_id:
                where.append(["source_contact_id", "=", contact_id])

            count_response = self.client.get(
                "Activity",
                select=["id"],
                where=where,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = self.client.get(
                "Activity",
                select=[
                    "id",
                    "subject",
                    "activity_type_id:label",
                    "status_id:label",
                    "activity_date_time",
                    "source_contact_id.display_name",
                    "details",
                ],
                where=where,
                order_by={"activity_date_time": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    def get_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Get a single activity by ID."""
        try:
            response = self.client.get(
                "Activity",
                select=[
                    "id",
                    "subject",
                    "activity_type_id:label",
                    "status_id:label",
                    "priority_id:label",
                    "activity_date_time",
                    "duration",
                    "location",
                    "details",
                    "source_contact_id",
                    "source_contact_id.display_name",
                    "created_date",
                    "modified_date",
                ],
                where=[["id", "=", activity_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def create_activity(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new activity."""
        try:
            response = self.client.create("Activity", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def delete_activity(self, activity_id: int) -> bool:
        """Delete an activity."""
        try:
            self.client.update(
                "Activity",
                values={"is_deleted": True},
                where=[["id", "=", activity_id]],
            )
            return True
        except CiviError:
            return False

    # -------------------------------------------------------------------------
    # Contributions
    # -------------------------------------------------------------------------

    def list_contributions(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        contact_id: int | None = None,
    ) -> PaginatedResult:
        """List contributions with pagination."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = []
            if contact_id:
                where.append(["contact_id", "=", contact_id])

            count_response = self.client.get(
                "Contribution",
                select=["id"],
                where=where if where else None,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = self.client.get(
                "Contribution",
                select=[
                    "id",
                    "contact_id",
                    "contact_id.display_name",
                    "total_amount",
                    "currency",
                    "financial_type_id:label",
                    "contribution_status_id:label",
                    "receive_date",
                    "source",
                ],
                where=where if where else None,
                order_by={"receive_date": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    def get_contribution(self, contribution_id: int) -> dict[str, Any] | None:
        """Get a single contribution by ID."""
        try:
            response = self.client.get(
                "Contribution",
                select=[
                    "id",
                    "contact_id",
                    "contact_id.display_name",
                    "total_amount",
                    "net_amount",
                    "fee_amount",
                    "currency",
                    "financial_type_id:label",
                    "contribution_status_id:label",
                    "payment_instrument_id:label",
                    "receive_date",
                    "receipt_date",
                    "source",
                    "trxn_id",
                    "invoice_id",
                    "created_date",
                ],
                where=[["id", "=", contribution_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def create_contribution(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contribution."""
        try:
            response = self.client.create("Contribution", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def list_events(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        active_only: bool = True,
    ) -> PaginatedResult:
        """List events with pagination."""
        result = PaginatedResult(page=page, per_page=per_page)

        try:
            where: list[list[Any]] = []
            if active_only:
                where.append(["is_active", "=", True])
            if search:
                where.append(["title", "CONTAINS", search])

            count_response = self.client.get(
                "Event",
                select=["id"],
                where=where if where else None,
                limit=0,
            )
            result.total = count_response.count or 0

            offset = (page - 1) * per_page
            response = self.client.get(
                "Event",
                select=[
                    "id",
                    "title",
                    "event_type_id:label",
                    "start_date",
                    "end_date",
                    "is_active",
                    "is_public",
                    "max_participants",
                    "loc_block_id.address_id.city",
                ],
                where=where if where else None,
                order_by={"start_date": "DESC"},
                limit=per_page,
                offset=offset,
            )
            result.items = response.values or []
            result.has_next = offset + len(result.items) < result.total
            result.has_prev = page > 1

        except CiviConnectionError:
            result.error = "Cannot connect to CiviCRM."
        except CiviError as e:
            result.error = f"CiviCRM error: {e}"

        return result

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        """Get a single event by ID."""
        try:
            response = self.client.get(
                "Event",
                select=[
                    "id",
                    "title",
                    "summary",
                    "description",
                    "event_type_id:label",
                    "start_date",
                    "end_date",
                    "is_active",
                    "is_public",
                    "max_participants",
                    "event_full_text",
                    "is_online_registration",
                    "registration_link_text",
                    "created_date",
                ],
                where=[["id", "=", event_id]],
                limit=1,
            )
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None

    def create_event(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new event."""
        try:
            response = self.client.create("Event", data)
            if response.values:
                return response.values[0]
        except CiviError:
            pass
        return None
