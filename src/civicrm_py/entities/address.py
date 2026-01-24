"""Address entity model for CiviCRM.

Addresses store physical/postal address information for contacts.

Relationships:
    - contact: Contact this address belongs to
    - master_address: Master address for shared addresses
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Address(BaseEntity, kw_only=True):
    """CiviCRM Address entity.

    Addresses store physical/postal address information associated with
    contacts. Each contact can have multiple addresses with different
    location types (Home, Work, etc.).

    Attributes:
        id: Unique address identifier.
        contact_id: Contact this address belongs to.
        location_type_id: Type of location (Home, Work, Main, etc.).
        is_primary: Whether this is the primary address.
        is_billing: Whether this is the billing address.
        street_address: Street address (number and street).
        street_number: Parsed street number.
        street_number_suffix: Street number suffix (A, B, 1/2, etc.).
        street_name: Parsed street name.
        street_type: Street type (St, Ave, Blvd, etc.).
        street_number_predirectional: Directional prefix (N, S, E, W).
        street_number_postdirectional: Directional suffix.
        street_unit: Unit/apartment type and number.
        supplemental_address_1: Additional address line 1.
        supplemental_address_2: Additional address line 2.
        supplemental_address_3: Additional address line 3.
        city: City name.
        county_id: County option value ID.
        state_province_id: State/province ID.
        postal_code: Postal/ZIP code.
        postal_code_suffix: Postal code extension (ZIP+4).
        usps_adc: USPS Area Distribution Center.
        country_id: Country ID.
        geo_code_1: Latitude coordinate.
        geo_code_2: Longitude coordinate.
        manual_geo_code: Whether geo codes were manually entered.
        timezone: Timezone name (e.g., 'America/New_York').
        name: Address name/label.
        master_id: ID of master address for shared addresses.
        created_date: When the address was created.
        modified_date: When the address was last modified.
    """

    __entity_name__: ClassVar[str] = "Address"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    location_type_id: int | None = None

    # Primary/billing flags
    is_primary: bool = False
    is_billing: bool = False

    # Street address components
    street_address: str | None = None
    street_number: int | None = None
    street_number_suffix: str | None = None
    street_name: str | None = None
    street_type: str | None = None
    street_number_predirectional: str | None = None
    street_number_postdirectional: str | None = None
    street_unit: str | None = None

    # Supplemental address lines
    supplemental_address_1: str | None = None
    supplemental_address_2: str | None = None
    supplemental_address_3: str | None = None

    # City, state, country
    city: str | None = None
    county_id: int | None = None
    state_province_id: int | None = None
    country_id: int | None = None

    # Postal code
    postal_code: str | None = None
    postal_code_suffix: str | None = None
    usps_adc: str | None = None

    # Geocoding
    geo_code_1: float | None = None
    geo_code_2: float | None = None
    manual_geo_code: bool = False

    # Additional
    timezone: str | None = None
    name: str | None = None
    master_id: int | None = None

    # Timestamps
    created_date: str | None = None
    modified_date: str | None = None

    # Foreign key relationships
    # Access contact: await address.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")
    # Access master address: await address.master_address
    master_address: ClassVar[ForeignKey[Address]] = ForeignKey("Address", "master_id")


__all__ = ["Address"]
