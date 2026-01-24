"""Email entity model for CiviCRM.

Emails store email addresses associated with contacts.

Relationships:
    - contact: Contact this email belongs to
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Email(BaseEntity, kw_only=True):
    """CiviCRM Email entity.

    Emails store email addresses associated with contacts. Each contact
    can have multiple email addresses with different location types
    (Home, Work, etc.).

    Attributes:
        id: Unique email identifier.
        contact_id: Contact this email belongs to.
        location_type_id: Type of location (Home, Work, Main, etc.).
        email: Email address.
        is_primary: Whether this is the primary email.
        is_billing: Whether this is the billing email.
        on_hold: Hold status (0=no hold, 1=bounce, 2=manual).
        is_bulkmail: Whether to use for bulk mailings.
        hold_date: When email was put on hold.
        reset_date: When hold was reset.
        signature_text: Plain text email signature.
        signature_html: HTML email signature.
    """

    __entity_name__: ClassVar[str] = "Email"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    location_type_id: int | None = None

    # Email address
    email: str | None = None

    # Flags
    is_primary: bool = False
    is_billing: bool = False
    is_bulkmail: bool = False

    # Hold status
    on_hold: int = 0
    hold_date: str | None = None
    reset_date: str | None = None

    # Signatures
    signature_text: str | None = None
    signature_html: str | None = None

    # Foreign key relationships
    # Access contact: await email.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")


__all__ = ["Email"]
