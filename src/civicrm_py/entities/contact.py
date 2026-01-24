"""Contact entity models for CiviCRM.

Defines the Contact entity and its specialized subtypes: Individual, Organization,
and Household. Contacts are the core entity in CiviCRM representing people and
organizations.

Relationships:
    - activities: Activities where this contact is the source
    - contributions: Financial contributions from this contact
    - memberships: Membership records for this contact
    - addresses: Physical/postal addresses for this contact
    - emails: Email addresses for this contact
    - phones: Phone numbers for this contact
    - participants: Event registrations for this contact
    - employer: Organization that employs this contact (Individual only)
"""

from __future__ import annotations

from typing import ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey, RelatedField


class Contact(BaseEntity, kw_only=True):
    """CiviCRM Contact entity.

    Represents any contact in CiviCRM. Contacts can be of three types:
    Individual (people), Organization (companies/nonprofits), or Household
    (family units).

    Attributes:
        id: Unique contact identifier.
        contact_type: Type of contact - 'Individual', 'Organization', or 'Household'.
        contact_sub_type: Optional sub-types for further categorization.
        display_name: Formatted display name for the contact.
        sort_name: Name used for sorting (typically "Last, First" or org name).
        first_name: First name (Individual contacts only).
        middle_name: Middle name (Individual contacts only).
        last_name: Last name (Individual contacts only).
        prefix_id: Name prefix ID (Mr., Ms., Dr., etc.).
        suffix_id: Name suffix ID (Jr., Sr., III, etc.).
        formal_title: Formal title (e.g., "President", "CEO").
        nick_name: Nickname or preferred name.
        legal_identifier: Legal identifier (SSN, EIN, etc.).
        external_identifier: External system identifier.
        organization_name: Organization name (Organization contacts only).
        legal_name: Legal organization name.
        sic_code: Standard Industrial Classification code.
        household_name: Household name (Household contacts only).
        job_title: Job title for individuals.
        employer_id: Contact ID of employer organization.
        gender_id: Gender option value ID.
        birth_date: Date of birth (YYYY-MM-DD format).
        is_deleted: Whether contact is in trash.
        is_deceased: Whether individual is deceased.
        deceased_date: Date of death (YYYY-MM-DD format).
        do_not_email: Do not send email to this contact.
        do_not_phone: Do not call this contact.
        do_not_mail: Do not send postal mail to this contact.
        do_not_sms: Do not send SMS to this contact.
        do_not_trade: Do not trade/share this contact's info.
        is_opt_out: Contact has opted out of bulk mailings.
        preferred_communication_method: List of preferred communication methods.
        preferred_language: ISO language code (e.g., "en_US").
        preferred_mail_format: Preferred email format ('Text', 'HTML', 'Both').
        email_primary: Primary email address (joined field: email_primary.email).
        phone_primary: Primary phone number (joined field: phone_primary.phone).
        address_primary_street_address: Primary street address.
        address_primary_city: Primary city.
        address_primary_postal_code: Primary postal code.
        address_primary_country_id: Primary country ID.
        source: How the contact was acquired.
        image_URL: URL to contact's image.
        created_date: When the contact was created.
        modified_date: When the contact was last modified.
        hash: Contact hash for checksum URLs.
    """

    __entity_name__: ClassVar[str] = "Contact"

    # Core identification fields
    id: int | None = None
    contact_type: str | None = None
    contact_sub_type: list[str] | None = None
    display_name: str | None = None
    sort_name: str | None = None

    # Individual name fields
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    prefix_id: int | None = None
    suffix_id: int | None = None
    formal_title: str | None = None
    nick_name: str | None = None

    # Legal/external identifiers
    legal_identifier: str | None = None
    external_identifier: str | None = None

    # Organization fields
    organization_name: str | None = None
    legal_name: str | None = None
    sic_code: str | None = None

    # Household fields
    household_name: str | None = None

    # Employment fields
    job_title: str | None = None
    employer_id: int | None = None

    # Demographics
    gender_id: int | None = None
    birth_date: str | None = None

    # Status fields
    is_deleted: bool = False
    is_deceased: bool = False
    deceased_date: str | None = None

    # Communication preferences
    do_not_email: bool = False
    do_not_phone: bool = False
    do_not_mail: bool = False
    do_not_sms: bool = False
    do_not_trade: bool = False
    is_opt_out: bool = False
    preferred_communication_method: list[str] | None = None
    preferred_language: str | None = None
    preferred_mail_format: str | None = None

    # Primary contact info (joined fields from related entities)
    email_primary: str | None = None
    phone_primary: str | None = None
    address_primary_street_address: str | None = None
    address_primary_city: str | None = None
    address_primary_postal_code: str | None = None
    address_primary_country_id: int | None = None

    # Metadata
    source: str | None = None
    image_URL: str | None = None  # noqa: N815 - CiviCRM API naming convention
    created_date: str | None = None
    modified_date: str | None = None
    hash: str | None = None

    # Reverse relationships (one-to-many)
    # These provide access to related entities via RelatedManager
    activities: ClassVar[RelatedField] = RelatedField("Activity", "source_contact_id")
    contributions: ClassVar[RelatedField] = RelatedField("Contribution", "contact_id")
    memberships: ClassVar[RelatedField] = RelatedField("Membership", "contact_id")
    addresses: ClassVar[RelatedField] = RelatedField("Address", "contact_id")
    emails: ClassVar[RelatedField] = RelatedField("Email", "contact_id")
    phones: ClassVar[RelatedField] = RelatedField("Phone", "contact_id")
    participants: ClassVar[RelatedField] = RelatedField("Participant", "contact_id")

    # Foreign key relationship
    # Access employer organization: await contact.employer
    employer: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "employer_id")


class Individual(Contact, kw_only=True):
    """Individual contact representing a person.

    Inherits all fields from Contact with contact_type defaulting to "Individual".
    Use this class when specifically working with person contacts.

    Example:
        >>> person = Individual(
        ...     first_name="John", last_name="Doe", email_primary="john.doe@example.com"
        ... )
    """

    __entity_name__: ClassVar[str] = "Contact"
    contact_type: str = "Individual"


class Organization(Contact, kw_only=True):
    """Organization contact representing a company, nonprofit, or other entity.

    Inherits all fields from Contact with contact_type defaulting to "Organization".
    Use this class when specifically working with organizational contacts.

    Example:
        >>> org = Organization(organization_name="Acme Corporation", legal_name="Acme Corp Inc.")
    """

    __entity_name__: ClassVar[str] = "Contact"
    contact_type: str = "Organization"


class Household(Contact, kw_only=True):
    """Household contact representing a family unit.

    Inherits all fields from Contact with contact_type defaulting to "Household".
    Use this class when specifically working with household/family contacts.

    Example:
        >>> family = Household(household_name="The Smith Family")
    """

    __entity_name__: ClassVar[str] = "Contact"
    contact_type: str = "Household"


__all__ = ["Contact", "Household", "Individual", "Organization"]
