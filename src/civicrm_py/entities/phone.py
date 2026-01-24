"""Phone entity model for CiviCRM.

Phones store phone numbers associated with contacts.

Relationships:
    - contact: Contact this phone belongs to
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Phone(BaseEntity, kw_only=True):
    """CiviCRM Phone entity.

    Phones store phone numbers associated with contacts. Each contact
    can have multiple phone numbers with different location types and
    phone types (Phone, Mobile, Fax, etc.).

    Attributes:
        id: Unique phone identifier.
        contact_id: Contact this phone belongs to.
        location_type_id: Type of location (Home, Work, Main, etc.).
        is_primary: Whether this is the primary phone.
        is_billing: Whether this is the billing phone.
        mobile_provider_id: Mobile carrier provider ID.
        phone: Phone number.
        phone_ext: Phone extension.
        phone_numeric: Numeric-only phone number (for searching).
        phone_type_id: Type of phone (Phone, Mobile, Fax, Pager, etc.).
    """

    __entity_name__: ClassVar[str] = "Phone"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    location_type_id: int | None = None

    # Phone number
    phone: str | None = None
    phone_ext: str | None = None
    phone_numeric: str | None = None
    phone_type_id: int | None = None

    # Flags
    is_primary: bool = False
    is_billing: bool = False

    # Mobile provider
    mobile_provider_id: int | None = None

    # Foreign key relationships
    # Access contact: await phone.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")


__all__ = ["Phone"]
