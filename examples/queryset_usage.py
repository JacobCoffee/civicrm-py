"""Example usage of QuerySet with CiviClient.

This demonstrates the Django-ORM-like query interface for CiviCRM API v4.
"""

# ruff: noqa: BLE001, ERA001

from __future__ import annotations

import asyncio

from civicrm_py.core.client import CiviClient
from civicrm_py.query.queryset import QuerySet


async def main() -> None:
    """Demonstrate QuerySet usage patterns."""
    # Initialize client
    async with CiviClient.from_env() as client:
        # Create a QuerySet for Contact entity
        contacts = QuerySet(client, "Contact")

        # Example 1: Basic filtering
        print("Example 1: Basic filtering")
        active_contacts = await (
            contacts.filter(is_deleted=False).select("id", "display_name", "email_primary.email").limit(5).all()
        )
        print(f"Found {len(active_contacts)} active contacts")
        for contact in active_contacts:
            print(f"  - {contact['display_name']}")

        # Example 2: Field lookups
        print("\nExample 2: Field lookups")
        smiths = await (
            contacts.filter(last_name__contains="Smith", is_deleted=False).select("id", "first_name", "last_name").all()
        )
        print(f"Found {len(smiths)} contacts with 'Smith' in last name")

        # Example 3: Ordering
        print("\nExample 3: Ordering")
        recent_contacts = await (
            contacts.filter(is_deleted=False)
            .order_by("-created_date")
            .select("id", "display_name", "created_date")
            .limit(3)
            .all()
        )
        print("Most recently created contacts:")
        for contact in recent_contacts:
            print(f"  - {contact['display_name']} ({contact.get('created_date')})")

        # Example 4: Count and exists
        print("\nExample 4: Count and exists")
        total_count = await contacts.filter(is_deleted=False).count()
        print(f"Total active contacts: {total_count}")

        has_admins = await contacts.filter(contact_type="Individual").exists()
        print(f"Has individual contacts: {has_admins}")

        # Example 5: Get single entity
        print("\nExample 5: Get single entity")
        try:
            contact = await contacts.get(id=1)
            print(f"Found contact: {contact.get('display_name')}")
        except Exception as e:
            print(f"Error: {e}")

        # Example 6: values() for dictionaries
        print("\nExample 6: values() for specific fields")
        names = await contacts.filter(is_deleted=False).values("id", "display_name").limit(3).all()
        print("Contact names as dicts:")
        for name in names:
            print(f"  - {name}")

        # Example 7: values_list() for tuples
        print("\nExample 7: values_list() for tuples")
        id_names = await contacts.filter(is_deleted=False).values_list("id", "display_name").limit(3).all()
        print("Contact IDs and names as tuples:")
        for id_name in id_names:
            print(f"  - {id_name}")

        # Example 8: values_list() flat
        print("\nExample 8: values_list() flat for single field")
        ids = await contacts.filter(is_deleted=False).values_list("id", flat=True).limit(5).all()
        print(f"Contact IDs: {ids}")

        # Example 9: Complex filtering with multiple conditions
        print("\nExample 9: Complex filtering")
        filtered = await (
            contacts.filter(
                contact_type="Individual",
                is_deleted=False,
            )
            .exclude(last_name__isnull=True)
            .select("id", "first_name", "last_name")
            .order_by("last_name", "first_name")
            .limit(5)
            .all()
        )
        print(f"Found {len(filtered)} filtered contacts")

        # Example 10: first() method
        print("\nExample 10: first() method")
        first_contact = await contacts.filter(is_deleted=False).order_by("-id").first()
        if first_contact:
            print(f"First contact: {first_contact.get('display_name')}")
        else:
            print("No contacts found")

        # Example 11: Update
        print("\nExample 11: Update entities")
        # Uncomment to actually update:
        # updated = await contacts.filter(id=123).update(nick_name="Test")
        # print(f"Updated {updated} contacts")

        # Example 12: Delete
        print("\nExample 12: Delete entities")
        # Uncomment to actually delete:
        # deleted = await contacts.filter(id__in=[456, 789]).delete()
        # print(f"Deleted {deleted} contacts")


if __name__ == "__main__":
    asyncio.run(main())
