"""Sample data generator for civi-py examples.

Provides utilities to generate sample CiviCRM data for demonstration purposes.
Sample data is idempotent - running multiple times updates existing records.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from civicrm_py.core.exceptions import CiviError

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient, SyncCiviClient


# Prefix for external identifiers to track sample data
SAMPLE_DATA_PREFIX = "civi-py-sample-"

# Sample data pools
FIRST_NAMES = [
    "James",
    "Mary",
    "John",
    "Patricia",
    "Robert",
    "Jennifer",
    "Michael",
    "Linda",
    "William",
    "Elizabeth",
    "David",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Charles",
    "Karen",
    "Christopher",
    "Nancy",
    "Daniel",
    "Lisa",
    "Matthew",
    "Betty",
    "Anthony",
    "Margaret",
    "Mark",
    "Sandra",
    "Donald",
    "Ashley",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Ramirez",
    "Lewis",
    "Robinson",
    "Walker",
]

ORGANIZATION_NAMES = [
    "Acme Corporation",
    "Global Tech Industries",
    "Pacific Northwest Foundation",
    "Green Earth Initiative",
    "Community Health Alliance",
    "Urban Development Group",
    "Sunrise Medical Center",
    "Mountain View Associates",
    "River Valley Bank",
    "Coastal Engineering Solutions",
    "Metro Transit Authority",
    "Heritage Arts Council",
    "Innovation Labs Inc.",
    "Sustainable Energy Partners",
    "Youth Education Network",
]

ACTIVITY_SUBJECTS = [
    "Follow-up call",
    "Meeting scheduled",
    "Email sent",
    "Newsletter subscription",
    "Donation acknowledgment",
    "Event registration",
    "Volunteer orientation",
    "Membership renewal",
    "Grant application",
    "Board meeting",
    "Annual review",
    "Training session",
    "Site visit",
    "Phone inquiry",
    "Document request",
]

EVENT_TITLES = [
    "Annual Fundraising Gala",
    "Community Volunteer Day",
    "Board of Directors Meeting",
    "Member Appreciation Event",
    "Educational Workshop",
    "Networking Mixer",
    "Charity Golf Tournament",
    "Youth Leadership Conference",
    "Arts and Culture Festival",
    "Health and Wellness Fair",
    "Environmental Cleanup Day",
    "Holiday Celebration",
]


@dataclass
class GenerationResult:
    """Result of sample data generation."""

    contacts_created: int = 0
    contacts_updated: int = 0
    activities_created: int = 0
    activities_updated: int = 0
    contributions_created: int = 0
    contributions_updated: int = 0
    events_created: int = 0
    events_updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        """Total number of records created."""
        return self.contacts_created + self.activities_created + self.contributions_created + self.events_created

    @property
    def total_updated(self) -> int:
        """Total number of records updated."""
        return self.contacts_updated + self.activities_updated + self.contributions_updated + self.events_updated

    @property
    def total(self) -> int:
        """Total number of records created or updated."""
        return self.total_created + self.total_updated

    @property
    def has_errors(self) -> bool:
        """Check if there were any errors during generation."""
        return len(self.errors) > 0


class SampleDataGenerator:
    """Generates sample CiviCRM data for demonstrations.

    Supports both async and sync clients.

    Usage (async):
        async with CiviClient() as client:
            generator = SampleDataGenerator(client)
            result = await generator.generate_all(
                contacts=10,
                activities=20,
                contributions=15,
                events=5,
            )

    Usage (sync):
        with SyncCiviClient() as client:
            generator = SampleDataGenerator(client)
            result = generator.generate_all_sync(
                contacts=10,
                activities=20,
                contributions=15,
                events=5,
            )
    """

    def __init__(self, client: CiviClient | SyncCiviClient) -> None:
        """Initialize the generator.

        Args:
            client: CiviCRM client (async or sync).
        """
        self.client = client
        self._contact_ids: list[int] = []

    def _random_email(self, first_name: str, last_name: str) -> str:
        """Generate a random email address."""
        domains = ["example.com", "test.org", "demo.net", "sample.io"]
        return f"{first_name.lower()}.{last_name.lower()}@{random.choice(domains)}"

    def _random_phone(self) -> str:
        """Generate a random phone number."""
        return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"

    def _random_date(self, days_back: int = 365) -> str:
        """Generate a random date within the past N days."""
        days = random.randint(0, days_back)
        date = datetime.now() - timedelta(days=days)
        return date.strftime("%Y-%m-%d %H:%M:%S")

    def _random_future_date(self, days_ahead: int = 90) -> str:
        """Generate a random date in the future."""
        days = random.randint(1, days_ahead)
        date = datetime.now() + timedelta(days=days)
        return date.strftime("%Y-%m-%d %H:%M:%S")

    def _generate_individual_data(self, index: int) -> dict[str, Any]:
        """Generate data for an individual contact.

        Args:
            index: Unique index for this contact (used for external_identifier).
        """
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        return {
            "contact_type": "Individual",
            "first_name": first_name,
            "last_name": last_name,
            "nick_name": f"{first_name[0]}{last_name}",
            "external_identifier": f"{SAMPLE_DATA_PREFIX}ind-{index}",
        }

    def _generate_organization_data(self, index: int) -> dict[str, Any]:
        """Generate data for an organization contact.

        Args:
            index: Unique index for this contact (used for external_identifier).
        """
        org_name = random.choice(ORGANIZATION_NAMES)
        return {
            "contact_type": "Organization",
            "organization_name": org_name,
            "external_identifier": f"{SAMPLE_DATA_PREFIX}org-{index}",
        }

    def _generate_household_data(self, index: int) -> dict[str, Any]:
        """Generate data for a household contact.

        Args:
            index: Unique index for this contact (used for external_identifier).
        """
        last_name = random.choice(LAST_NAMES)
        return {
            "contact_type": "Household",
            "household_name": f"The {last_name} Family",
            "external_identifier": f"{SAMPLE_DATA_PREFIX}hh-{index}",
        }

    def _generate_activity_data(self, contact_id: int, index: int) -> dict[str, Any]:
        """Generate data for an activity.

        Args:
            contact_id: Contact ID to link the activity to.
            index: Unique index for this activity.
        """
        subject = random.choice(ACTIVITY_SUBJECTS)
        return {
            "activity_type_id": random.randint(1, 5),  # Common activity types
            "subject": f"{subject} (Sample #{index})",
            "source_contact_id": contact_id,
            "activity_date_time": self._random_date(30),
            "status_id": random.choice([1, 2]),  # Scheduled or Completed
            "details": f"Auto-generated sample activity for testing civi-py. Index: {index}",
        }

    def _generate_contribution_data(self, contact_id: int, index: int) -> dict[str, Any]:
        """Generate data for a contribution.

        Args:
            contact_id: Contact ID to link the contribution to.
            index: Unique index for this contribution.
        """
        return {
            "contact_id": contact_id,
            "financial_type_id": 1,  # Donation
            "total_amount": round(random.uniform(25.0, 500.0), 2),
            "receive_date": self._random_date(180),
            "contribution_status_id": 1,  # Completed
            "source": f"civi-py sample data (#{index})",
            "trxn_id": f"{SAMPLE_DATA_PREFIX}contrib-{index}",
        }

    def _generate_event_data(self, index: int) -> dict[str, Any]:
        """Generate data for an event.

        Args:
            index: Unique index for this event.
        """
        title = random.choice(EVENT_TITLES)
        start_date = self._random_future_date(60)
        return {
            "title": f"{title} (Sample #{index})",
            "event_type_id": random.randint(1, 5),
            "start_date": start_date,
            "is_active": True,
            "is_public": True,
            "max_participants": random.randint(50, 200),
            "description": f"Auto-generated sample event for testing civi-py. Index: {index}",
        }

    # -------------------------------------------------------------------------
    # Async methods
    # -------------------------------------------------------------------------

    async def _save_contact(
        self,
        data: dict[str, Any],
    ) -> tuple[bool, bool, int | None]:
        """Save a contact (create or update).

        Args:
            data: Contact data with external_identifier.

        Returns:
            Tuple of (success, was_created, contact_id).
        """
        ext_id = data.get("external_identifier")
        if not ext_id:
            return False, False, None

        try:
            # Check if contact exists
            existing = await self.client.get(  # type: ignore[union-attr]
                "Contact",
                select=["id"],
                where=[["external_identifier", "=", ext_id]],
                limit=1,
            )

            if existing.values:
                # Update existing contact
                contact_id = existing.values[0]["id"]
                await self.client.update(  # type: ignore[union-attr]
                    "Contact",
                    values=data,
                    where=[["id", "=", contact_id]],
                )
                return True, False, contact_id
            # Create new contact
            response = await self.client.create("Contact", data)  # type: ignore[union-attr]
            if response.values:
                return True, True, response.values[0]["id"]
            return False, False, None
        except CiviError:
            return False, False, None

    async def generate_contacts(
        self,
        count: int = 10,
        *,
        individuals: float = 0.7,
        organizations: float = 0.2,
        households: float = 0.1,
    ) -> tuple[int, int]:
        """Generate sample contacts asynchronously (idempotent).

        Args:
            count: Number of contacts to create/update.
            individuals: Proportion of individual contacts.
            organizations: Proportion of organization contacts.
            households: Proportion of household contacts.

        Returns:
            Tuple of (contacts_created, contacts_updated).
        """
        created = 0
        updated = 0
        self._contact_ids = []

        for i in range(count):
            rand = random.random()
            if rand < individuals:
                data = self._generate_individual_data(i)
            elif rand < individuals + organizations:
                data = self._generate_organization_data(i)
            else:
                data = self._generate_household_data(i)

            success, was_created, contact_id = await self._save_contact(data)
            if success and contact_id:
                if was_created:
                    created += 1
                else:
                    updated += 1
                self._contact_ids.append(contact_id)

        return created, updated

    async def generate_activities(self, count: int = 20) -> tuple[int, int]:
        """Generate sample activities asynchronously (idempotent).

        Args:
            count: Number of activities to create/update.

        Returns:
            Tuple of (activities_created, activities_updated).
        """
        if not self._contact_ids:
            # Fetch existing sample contacts to link activities
            try:
                response = await self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["external_identifier", "LIKE", f"{SAMPLE_DATA_PREFIX}%"],
                    ],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                pass

        # If no sample contacts, use any contacts
        if not self._contact_ids:
            try:
                response = await self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[["is_deleted", "=", False]],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                return 0, 0

        if not self._contact_ids:
            return 0, 0

        created = 0
        updated = 0
        for i in range(count):
            contact_id = random.choice(self._contact_ids)
            data = self._generate_activity_data(contact_id, i)
            subject_pattern = f"(Sample #{i})"

            try:
                # Check if activity with this sample index exists
                existing = await self.client.get(  # type: ignore[union-attr]
                    "Activity",
                    select=["id"],
                    where=[["subject", "LIKE", f"%{subject_pattern}"]],
                    limit=1,
                )

                if existing.values:
                    # Update existing activity
                    activity_id = existing.values[0]["id"]
                    await self.client.update(  # type: ignore[union-attr]
                        "Activity",
                        values=data,
                        where=[["id", "=", activity_id]],
                    )
                    updated += 1
                else:
                    # Create new activity
                    response = await self.client.create("Activity", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    async def generate_contributions(self, count: int = 15) -> tuple[int, int]:
        """Generate sample contributions asynchronously (idempotent).

        Args:
            count: Number of contributions to create/update.

        Returns:
            Tuple of (contributions_created, contributions_updated).
        """
        if not self._contact_ids:
            try:
                response = await self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["external_identifier", "LIKE", f"{SAMPLE_DATA_PREFIX}%"],
                    ],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                pass

        if not self._contact_ids:
            try:
                response = await self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[["is_deleted", "=", False]],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                return 0, 0

        if not self._contact_ids:
            return 0, 0

        created = 0
        updated = 0
        for i in range(count):
            contact_id = random.choice(self._contact_ids)
            data = self._generate_contribution_data(contact_id, i)
            trxn_id = data.get("trxn_id")

            try:
                # Check if contribution with this trxn_id exists
                existing = await self.client.get(  # type: ignore[union-attr]
                    "Contribution",
                    select=["id"],
                    where=[["trxn_id", "=", trxn_id]],
                    limit=1,
                )

                if existing.values:
                    # Update existing contribution
                    contrib_id = existing.values[0]["id"]
                    await self.client.update(  # type: ignore[union-attr]
                        "Contribution",
                        values=data,
                        where=[["id", "=", contrib_id]],
                    )
                    updated += 1
                else:
                    # Create new contribution
                    response = await self.client.create("Contribution", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    async def generate_events(self, count: int = 5) -> tuple[int, int]:
        """Generate sample events asynchronously (idempotent).

        Args:
            count: Number of events to create/update.

        Returns:
            Tuple of (events_created, events_updated).
        """
        created = 0
        updated = 0
        for i in range(count):
            data = self._generate_event_data(i)
            title_pattern = f"(Sample #{i})"

            try:
                # Check if event with this sample index exists
                existing = await self.client.get(  # type: ignore[union-attr]
                    "Event",
                    select=["id"],
                    where=[["title", "LIKE", f"%{title_pattern}"]],
                    limit=1,
                )

                if existing.values:
                    # Update existing event
                    event_id = existing.values[0]["id"]
                    await self.client.update(  # type: ignore[union-attr]
                        "Event",
                        values=data,
                        where=[["id", "=", event_id]],
                    )
                    updated += 1
                else:
                    # Create new event
                    response = await self.client.create("Event", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    async def generate_all(
        self,
        *,
        contacts: int = 10,
        activities: int = 20,
        contributions: int = 15,
        events: int = 5,
    ) -> GenerationResult:
        """Generate all types of sample data asynchronously (idempotent).

        Args:
            contacts: Number of contacts to create/update.
            activities: Number of activities to create/update.
            contributions: Number of contributions to create/update.
            events: Number of events to create/update.

        Returns:
            GenerationResult with counts and any errors.
        """
        result = GenerationResult()

        try:
            created, updated = await self.generate_contacts(contacts)
            result.contacts_created = created
            result.contacts_updated = updated
        except Exception as e:
            result.errors.append(f"Contacts: {e}")

        try:
            created, updated = await self.generate_activities(activities)
            result.activities_created = created
            result.activities_updated = updated
        except Exception as e:
            result.errors.append(f"Activities: {e}")

        try:
            created, updated = await self.generate_contributions(contributions)
            result.contributions_created = created
            result.contributions_updated = updated
        except Exception as e:
            result.errors.append(f"Contributions: {e}")

        try:
            created, updated = await self.generate_events(events)
            result.events_created = created
            result.events_updated = updated
        except Exception as e:
            result.errors.append(f"Events: {e}")

        return result

    # -------------------------------------------------------------------------
    # Sync methods
    # -------------------------------------------------------------------------

    def _save_contact_sync(
        self,
        data: dict[str, Any],
    ) -> tuple[bool, bool, int | None]:
        """Save a contact synchronously (create or update).

        Args:
            data: Contact data with external_identifier.

        Returns:
            Tuple of (success, was_created, contact_id).
        """
        ext_id = data.get("external_identifier")
        if not ext_id:
            return False, False, None

        try:
            # Check if contact exists
            existing = self.client.get(  # type: ignore[union-attr]
                "Contact",
                select=["id"],
                where=[["external_identifier", "=", ext_id]],
                limit=1,
            )

            if existing.values:
                # Update existing contact
                contact_id = existing.values[0]["id"]
                self.client.update(  # type: ignore[union-attr]
                    "Contact",
                    values=data,
                    where=[["id", "=", contact_id]],
                )
                return True, False, contact_id
            # Create new contact
            response = self.client.create("Contact", data)  # type: ignore[union-attr]
            if response.values:
                return True, True, response.values[0]["id"]
            return False, False, None
        except CiviError:
            return False, False, None

    def generate_contacts_sync(
        self,
        count: int = 10,
        *,
        individuals: float = 0.7,
        organizations: float = 0.2,
        households: float = 0.1,
    ) -> tuple[int, int]:
        """Generate sample contacts synchronously (idempotent)."""
        created = 0
        updated = 0
        self._contact_ids = []

        for i in range(count):
            rand = random.random()
            if rand < individuals:
                data = self._generate_individual_data(i)
            elif rand < individuals + organizations:
                data = self._generate_organization_data(i)
            else:
                data = self._generate_household_data(i)

            success, was_created, contact_id = self._save_contact_sync(data)
            if success and contact_id:
                if was_created:
                    created += 1
                else:
                    updated += 1
                self._contact_ids.append(contact_id)

        return created, updated

    def generate_activities_sync(self, count: int = 20) -> tuple[int, int]:
        """Generate sample activities synchronously (idempotent)."""
        if not self._contact_ids:
            try:
                response = self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["external_identifier", "LIKE", f"{SAMPLE_DATA_PREFIX}%"],
                    ],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                pass

        if not self._contact_ids:
            try:
                response = self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[["is_deleted", "=", False]],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                return 0, 0

        if not self._contact_ids:
            return 0, 0

        created = 0
        updated = 0
        for i in range(count):
            contact_id = random.choice(self._contact_ids)
            data = self._generate_activity_data(contact_id, i)
            subject_pattern = f"(Sample #{i})"

            try:
                # Check if activity with this sample index exists
                existing = self.client.get(  # type: ignore[union-attr]
                    "Activity",
                    select=["id"],
                    where=[["subject", "LIKE", f"%{subject_pattern}"]],
                    limit=1,
                )

                if existing.values:
                    # Update existing activity
                    activity_id = existing.values[0]["id"]
                    self.client.update(  # type: ignore[union-attr]
                        "Activity",
                        values=data,
                        where=[["id", "=", activity_id]],
                    )
                    updated += 1
                else:
                    # Create new activity
                    response = self.client.create("Activity", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    def generate_contributions_sync(self, count: int = 15) -> tuple[int, int]:
        """Generate sample contributions synchronously (idempotent)."""
        if not self._contact_ids:
            try:
                response = self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[
                        ["is_deleted", "=", False],
                        ["external_identifier", "LIKE", f"{SAMPLE_DATA_PREFIX}%"],
                    ],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                pass

        if not self._contact_ids:
            try:
                response = self.client.get(  # type: ignore[union-attr]
                    "Contact",
                    select=["id"],
                    where=[["is_deleted", "=", False]],
                    limit=50,
                )
                self._contact_ids = [c["id"] for c in (response.values or [])]
            except CiviError:
                return 0, 0

        if not self._contact_ids:
            return 0, 0

        created = 0
        updated = 0
        for i in range(count):
            contact_id = random.choice(self._contact_ids)
            data = self._generate_contribution_data(contact_id, i)
            trxn_id = data.get("trxn_id")

            try:
                # Check if contribution with this trxn_id exists
                existing = self.client.get(  # type: ignore[union-attr]
                    "Contribution",
                    select=["id"],
                    where=[["trxn_id", "=", trxn_id]],
                    limit=1,
                )

                if existing.values:
                    # Update existing contribution
                    contrib_id = existing.values[0]["id"]
                    self.client.update(  # type: ignore[union-attr]
                        "Contribution",
                        values=data,
                        where=[["id", "=", contrib_id]],
                    )
                    updated += 1
                else:
                    # Create new contribution
                    response = self.client.create("Contribution", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    def generate_events_sync(self, count: int = 5) -> tuple[int, int]:
        """Generate sample events synchronously (idempotent)."""
        created = 0
        updated = 0
        for i in range(count):
            data = self._generate_event_data(i)
            title_pattern = f"(Sample #{i})"

            try:
                # Check if event with this sample index exists
                existing = self.client.get(  # type: ignore[union-attr]
                    "Event",
                    select=["id"],
                    where=[["title", "LIKE", f"%{title_pattern}"]],
                    limit=1,
                )

                if existing.values:
                    # Update existing event
                    event_id = existing.values[0]["id"]
                    self.client.update(  # type: ignore[union-attr]
                        "Event",
                        values=data,
                        where=[["id", "=", event_id]],
                    )
                    updated += 1
                else:
                    # Create new event
                    response = self.client.create("Event", data)  # type: ignore[union-attr]
                    if response.values:
                        created += 1
            except CiviError:
                pass

        return created, updated

    def generate_all_sync(
        self,
        *,
        contacts: int = 10,
        activities: int = 20,
        contributions: int = 15,
        events: int = 5,
    ) -> GenerationResult:
        """Generate all types of sample data synchronously (idempotent).

        Args:
            contacts: Number of contacts to create/update.
            activities: Number of activities to create/update.
            contributions: Number of contributions to create/update.
            events: Number of events to create/update.

        Returns:
            GenerationResult with counts and any errors.
        """
        result = GenerationResult()

        try:
            created, updated = self.generate_contacts_sync(contacts)
            result.contacts_created = created
            result.contacts_updated = updated
        except Exception as e:
            result.errors.append(f"Contacts: {e}")

        try:
            created, updated = self.generate_activities_sync(activities)
            result.activities_created = created
            result.activities_updated = updated
        except Exception as e:
            result.errors.append(f"Activities: {e}")

        try:
            created, updated = self.generate_contributions_sync(contributions)
            result.contributions_created = created
            result.contributions_updated = updated
        except Exception as e:
            result.errors.append(f"Contributions: {e}")

        try:
            created, updated = self.generate_events_sync(events)
            result.events_created = created
            result.events_updated = updated
        except Exception as e:
            result.errors.append(f"Events: {e}")

        return result
