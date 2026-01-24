"""Msgspec DTOs for Litestar CiviCRM integration.

Provides request/response Data Transfer Objects using msgspec.Struct
for native Litestar integration with automatic validation and serialization.

Example:
    >>> from civicrm_py.contrib.litestar.dto import ContactCreateDTO, ContactResponseDTO
    >>>
    >>> # Create a contact
    >>> create_data = ContactCreateDTO(
    ...     first_name="John",
    ...     last_name="Doe",
    ...     email_primary="john@example.com",
    ... )
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Required at runtime for msgspec
from typing import Any

import msgspec

# =============================================================================
# Base DTOs
# =============================================================================


class BaseDTO(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Base DTO with common configuration.

    All DTOs inherit from this base class which configures msgspec
    to omit default values during serialization.
    """


class PaginationDTO(BaseDTO):
    """Pagination parameters for list endpoints.

    Attributes:
        limit: Maximum number of records to return.
        offset: Number of records to skip.
    """

    limit: int = 25
    offset: int = 0


class APIResponseDTO(BaseDTO, kw_only=True):
    """Standard API response wrapper.

    Attributes:
        values: List of returned records.
        count: Total number of records matching the query.
        count_fetched: Number of records actually returned.
    """

    values: list[dict[str, Any]]
    count: int
    count_fetched: int


# =============================================================================
# Contact DTOs
# =============================================================================


class ContactBaseDTO(BaseDTO):
    """Base fields shared by Contact create/update/response DTOs."""

    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    display_name: str | None = None
    sort_name: str | None = None
    nick_name: str | None = None
    contact_type: str = "Individual"
    contact_sub_type: list[str] | None = None
    prefix_id: int | None = None
    suffix_id: int | None = None
    email_primary: str | None = None
    phone_primary: str | None = None
    do_not_email: bool = False
    do_not_phone: bool = False
    do_not_mail: bool = False
    do_not_sms: bool = False
    do_not_trade: bool = False
    is_opt_out: bool = False
    preferred_communication_method: list[str] | None = None
    preferred_language: str | None = None
    source: str | None = None
    external_identifier: str | None = None


class ContactCreateDTO(ContactBaseDTO):
    """DTO for creating a new Contact.

    Example:
        >>> dto = ContactCreateDTO(
        ...     first_name="Jane",
        ...     last_name="Smith",
        ...     email_primary="jane@example.com",
        ...     contact_type="Individual",
        ... )
    """


class ContactUpdateDTO(ContactBaseDTO):
    """DTO for updating an existing Contact.

    All fields are optional - only provided fields will be updated.
    """


class ContactResponseDTO(ContactBaseDTO, kw_only=True):
    """DTO for Contact response data.

    Includes read-only fields like id, created_date, and modified_date.
    """

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


class ContactFilterDTO(PaginationDTO):
    """DTO for Contact list filtering.

    Attributes:
        contact_type: Filter by contact type (Individual, Organization, Household).
        is_deleted: Include deleted contacts.
        search: Search string for display_name, email, etc.
    """

    contact_type: str | None = None
    is_deleted: bool = False
    search: str | None = None


# =============================================================================
# Activity DTOs
# =============================================================================


class ActivityBaseDTO(BaseDTO):
    """Base fields shared by Activity create/update/response DTOs."""

    activity_type_id: int | None = None
    subject: str | None = None
    details: str | None = None
    activity_date_time: datetime | None = None
    duration: int | None = None
    location: str | None = None
    status_id: int | None = None
    priority_id: int | None = None
    source_contact_id: int | None = None
    target_contact_id: list[int] | None = None
    assignee_contact_id: list[int] | None = None


class ActivityCreateDTO(ActivityBaseDTO, kw_only=True):
    """DTO for creating a new Activity.

    Example:
        >>> dto = ActivityCreateDTO(
        ...     activity_type_id=1,
        ...     subject="Follow-up call",
        ...     source_contact_id=123,
        ... )
    """

    activity_type_id: int  # Required for creation


class ActivityUpdateDTO(ActivityBaseDTO):
    """DTO for updating an existing Activity."""


class ActivityResponseDTO(ActivityBaseDTO, kw_only=True):
    """DTO for Activity response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


class ActivityFilterDTO(PaginationDTO):
    """DTO for Activity list filtering."""

    activity_type_id: int | None = None
    status_id: int | None = None
    source_contact_id: int | None = None
    is_deleted: bool = False


# =============================================================================
# Contribution DTOs
# =============================================================================


class ContributionBaseDTO(BaseDTO):
    """Base fields shared by Contribution create/update/response DTOs."""

    contact_id: int | None = None
    financial_type_id: int | None = None
    total_amount: float | None = None
    currency: str = "USD"
    contribution_status_id: int | None = None
    receive_date: datetime | None = None
    receipt_date: datetime | None = None
    thankyou_date: datetime | None = None
    source: str | None = None
    trxn_id: str | None = None
    invoice_id: str | None = None
    check_number: str | None = None
    note: str | None = None


class ContributionCreateDTO(ContributionBaseDTO, kw_only=True):
    """DTO for creating a new Contribution.

    Example:
        >>> dto = ContributionCreateDTO(
        ...     contact_id=123,
        ...     financial_type_id=1,
        ...     total_amount=100.00,
        ... )
    """

    contact_id: int  # Required
    financial_type_id: int  # Required
    total_amount: float  # Required


class ContributionUpdateDTO(ContributionBaseDTO):
    """DTO for updating an existing Contribution."""


class ContributionResponseDTO(ContributionBaseDTO, kw_only=True):
    """DTO for Contribution response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


class ContributionFilterDTO(PaginationDTO):
    """DTO for Contribution list filtering."""

    contact_id: int | None = None
    financial_type_id: int | None = None
    contribution_status_id: int | None = None
    is_deleted: bool = False


# =============================================================================
# Event DTOs
# =============================================================================


class EventBaseDTO(BaseDTO):
    """Base fields shared by Event create/update/response DTOs."""

    title: str | None = None
    summary: str | None = None
    description: str | None = None
    event_type_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_active: bool = True
    is_public: bool = True
    is_online_registration: bool = False
    max_participants: int | None = None
    event_full_text: str | None = None
    waitlist_text: str | None = None


class EventCreateDTO(EventBaseDTO, kw_only=True):
    """DTO for creating a new Event."""

    title: str  # Required
    event_type_id: int  # Required
    start_date: datetime  # Required


class EventUpdateDTO(EventBaseDTO):
    """DTO for updating an existing Event."""


class EventResponseDTO(EventBaseDTO, kw_only=True):
    """DTO for Event response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


class EventFilterDTO(PaginationDTO):
    """DTO for Event list filtering."""

    event_type_id: int | None = None
    is_active: bool | None = None
    is_public: bool | None = None
    is_deleted: bool = False


# =============================================================================
# Membership DTOs
# =============================================================================


class MembershipBaseDTO(BaseDTO):
    """Base fields shared by Membership create/update/response DTOs."""

    contact_id: int | None = None
    membership_type_id: int | None = None
    status_id: int | None = None
    join_date: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    source: str | None = None
    owner_membership_id: int | None = None


class MembershipCreateDTO(MembershipBaseDTO, kw_only=True):
    """DTO for creating a new Membership."""

    contact_id: int  # Required
    membership_type_id: int  # Required


class MembershipUpdateDTO(MembershipBaseDTO):
    """DTO for updating an existing Membership."""


class MembershipResponseDTO(MembershipBaseDTO, kw_only=True):
    """DTO for Membership response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


class MembershipFilterDTO(PaginationDTO):
    """DTO for Membership list filtering."""

    contact_id: int | None = None
    membership_type_id: int | None = None
    status_id: int | None = None
    is_deleted: bool = False


# =============================================================================
# Generic Entity DTO
# =============================================================================


class EntityCreateDTO(BaseDTO):
    """Generic DTO for creating any entity.

    Use this for entities without specific DTOs defined.
    """

    values: dict[str, Any]


class EntityUpdateDTO(BaseDTO):
    """Generic DTO for updating any entity."""

    values: dict[str, Any]


__all__ = [
    "APIResponseDTO",
    "ActivityCreateDTO",
    "ActivityFilterDTO",
    "ActivityResponseDTO",
    "ActivityUpdateDTO",
    "BaseDTO",
    "ContactCreateDTO",
    "ContactFilterDTO",
    "ContactResponseDTO",
    "ContactUpdateDTO",
    "ContributionCreateDTO",
    "ContributionFilterDTO",
    "ContributionResponseDTO",
    "ContributionUpdateDTO",
    "EntityCreateDTO",
    "EntityUpdateDTO",
    "EventCreateDTO",
    "EventFilterDTO",
    "EventResponseDTO",
    "EventUpdateDTO",
    "MembershipCreateDTO",
    "MembershipFilterDTO",
    "MembershipResponseDTO",
    "MembershipUpdateDTO",
    "PaginationDTO",
]
