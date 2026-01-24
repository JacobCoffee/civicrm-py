"""Participant entity model for CiviCRM.

Participants represent contacts who have registered for or attended events.

Relationships:
    - contact: Contact who is participating
    - event: Event being attended
    - registered_by: Contact who registered this participant
    - transferred_to: Contact the registration was transferred to
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact
    from civicrm_py.entities.event import Event


class Participant(BaseEntity, kw_only=True):
    """CiviCRM Participant entity.

    Participants track contact registration and attendance at events. They
    connect contacts to events with associated status, role, and fees.

    Attributes:
        id: Unique participant identifier.
        contact_id: Contact who is participating.
        event_id: Event being attended.
        status_id: Participant status (Registered, Attended, Cancelled, etc.).
        role_id: Participant role (Attendee, Volunteer, Speaker, etc.).
        register_date: When the participant registered.
        source: How the registration was made.
        fee_level: Description of fee level selected.
        is_test: Whether this is test data.
        is_pay_later: Whether payment is deferred.
        fee_amount: Amount paid/owed for participation.
        registered_by_id: Contact ID who registered this participant.
        discount_id: Discount applied to registration.
        fee_currency: ISO 4217 currency code for the fee.
        campaign_id: Associated campaign ID.
        discount_amount: Amount of discount applied.
        cart_id: Shopping cart ID for online registrations.
        must_wait: Whether participant is on waitlist.
        transferred_to_contact_id: Contact ID if registration was transferred.
        created_date: When the participant record was created.
        modified_date: When the participant was last modified.
    """

    __entity_name__: ClassVar[str] = "Participant"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    event_id: int | None = None

    # Status and role
    status_id: int | None = None
    role_id: int | None = None

    # Registration details
    register_date: str | None = None
    source: str | None = None
    registered_by_id: int | None = None

    # Fees
    fee_level: str | None = None
    fee_amount: float | None = None
    fee_currency: str | None = None
    discount_id: int | None = None
    discount_amount: float | None = None

    # Flags
    is_test: bool = False
    is_pay_later: bool = False
    must_wait: bool = False

    # Related records
    campaign_id: int | None = None
    cart_id: int | None = None
    transferred_to_contact_id: int | None = None

    # Timestamps
    created_date: str | None = None
    modified_date: str | None = None

    # Foreign key relationships
    # Access contact: await participant.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")
    # Access event: await participant.event
    event: ClassVar[ForeignKey[Event]] = ForeignKey("Event", "event_id")
    # Access registered by contact: await participant.registered_by
    registered_by: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "registered_by_id")
    # Access transferred to contact: await participant.transferred_to
    transferred_to: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "transferred_to_contact_id")


__all__ = ["Participant"]
