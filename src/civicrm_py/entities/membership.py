"""Membership entity model for CiviCRM.

Memberships represent the relationship between contacts and membership organizations,
tracking membership status, terms, and associated benefits.

Relationships:
    - contact: Contact who holds the membership
    - owner_membership: Primary membership for inherited memberships
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Membership(BaseEntity, kw_only=True):
    """CiviCRM Membership entity.

    Memberships track organizational membership relationships with contacts.
    This includes membership type, status, dates, and associated contributions.

    Attributes:
        id: Unique membership identifier.
        contact_id: Contact who holds the membership.
        membership_type_id: Type of membership.
        join_date: Date contact first joined.
        start_date: Current membership period start date.
        end_date: Current membership period end date.
        source: How the membership was acquired.
        status_id: Current membership status (New, Current, Grace, Expired, etc.).
        is_override: Whether status is manually overridden.
        status_override_end_date: When status override expires.
        owner_membership_id: Primary membership ID for inherited memberships.
        max_related: Maximum related memberships allowed.
        is_test: Whether this is test data.
        is_pay_later: Whether payment is deferred.
        contribution_recur_id: Recurring contribution ID.
        campaign_id: Associated campaign ID.
        created_date: When the membership was created.
        modified_date: When the membership was last modified.
    """

    __entity_name__: ClassVar[str] = "Membership"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    membership_type_id: int | None = None

    # Dates
    join_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    # Source
    source: str | None = None

    # Status
    status_id: int | None = None
    is_override: bool = False
    status_override_end_date: str | None = None

    # Related memberships
    owner_membership_id: int | None = None
    max_related: int | None = None

    # Flags
    is_test: bool = False
    is_pay_later: bool = False

    # Related records
    contribution_recur_id: int | None = None
    campaign_id: int | None = None

    # Timestamps
    created_date: str | None = None
    modified_date: str | None = None

    # Foreign key relationships
    # Access contact: await membership.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")
    # Access owner membership: await membership.owner_membership
    owner_membership: ClassVar[ForeignKey[Membership]] = ForeignKey("Membership", "owner_membership_id")


__all__ = ["Membership"]
