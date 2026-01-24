"""Event entity model for CiviCRM.

Events represent gatherings, meetings, conferences, and other scheduled
occurrences that contacts can participate in.

Relationships:
    - participants: Contacts participating in this event
    - parent_event: Parent event for recurring events
    - created_by: Contact who created the event
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey, RelatedField

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Event(BaseEntity, kw_only=True):
    """CiviCRM Event entity.

    Events represent scheduled gatherings such as conferences, meetings,
    workshops, fundraisers, and other occasions where contacts participate.

    Attributes:
        id: Unique event identifier.
        title: Event title/name.
        summary: Brief summary of the event.
        description: Full event description.
        event_type_id: Type of event (Conference, Meeting, Workshop, etc.).
        participant_listing_id: How participants are listed.
        is_public: Whether event is publicly visible.
        start_date: Event start date and time.
        end_date: Event end date and time.
        is_online_registration: Whether online registration is enabled.
        registration_link_text: Text for registration link.
        registration_start_date: When registration opens.
        registration_end_date: When registration closes.
        max_participants: Maximum number of participants.
        event_full_text: Message shown when event is full.
        is_monetary: Whether event has a fee.
        financial_type_id: Financial type for paid events.
        payment_processor: Payment processor ID.
        is_map: Whether to show map.
        is_active: Whether event is active.
        fee_label: Label for the fee field.
        is_show_location: Whether to show location.
        loc_block_id: Location block ID.
        default_role_id: Default participant role.
        intro_text: Introduction text.
        footer_text: Footer text.
        confirm_title: Confirmation page title.
        confirm_text: Confirmation page text.
        confirm_footer_text: Confirmation footer text.
        is_email_confirm: Whether to send confirmation emails.
        confirm_email_text: Confirmation email text.
        confirm_from_name: Confirmation email from name.
        confirm_from_email: Confirmation email from address.
        cc_confirm: CC address for confirmations.
        bcc_confirm: BCC address for confirmations.
        default_fee_id: Default fee ID.
        default_discount_fee_id: Default discounted fee ID.
        thankyou_title: Thank you page title.
        thankyou_text: Thank you page text.
        thankyou_footer_text: Thank you page footer.
        is_pay_later: Whether pay later is enabled.
        pay_later_text: Pay later option text.
        pay_later_receipt: Pay later receipt text.
        is_partial_payment: Whether partial payments allowed.
        initial_amount_label: Label for initial payment amount.
        initial_amount_help_text: Help text for initial amount.
        min_initial_amount: Minimum initial payment.
        is_multiple_registrations: Whether multiple registrations allowed.
        max_additional_participants: Max additional participants per registration.
        allow_same_participant_emails: Allow same email for multiple participants.
        has_waitlist: Whether waitlist is enabled.
        requires_approval: Whether registration requires approval.
        expiration_time: Registration expiration time in hours.
        allow_selfcancelxfer: Allow self-service cancellation/transfer.
        selfcancelxfer_time: Hours before event for self-service.
        waitlist_text: Waitlist message text.
        approval_req_text: Approval required message.
        is_template: Whether this is a template event.
        template_title: Template title.
        currency: ISO 4217 currency code.
        campaign_id: Associated campaign ID.
        is_share: Whether social sharing is enabled.
        is_confirm_enabled: Whether confirmation page is enabled.
        parent_event_id: Parent event ID for recurring events.
        slot_label_id: Slot label option value.
        dedupe_rule_group_id: Dedupe rule group ID.
        is_billing_required: Whether billing info required.
        created_id: Contact ID who created the event.
        created_date: When the event was created.
        modified_date: When the event was last modified.
    """

    __entity_name__: ClassVar[str] = "Event"

    # Core identification
    id: int | None = None
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    event_type_id: int | None = None

    # Visibility and status
    is_public: bool = True
    is_active: bool = True
    is_template: bool = False
    template_title: str | None = None

    # Dates
    start_date: str | None = None
    end_date: str | None = None

    # Registration settings
    is_online_registration: bool = False
    registration_link_text: str | None = None
    registration_start_date: str | None = None
    registration_end_date: str | None = None
    max_participants: int | None = None
    event_full_text: str | None = None
    is_multiple_registrations: bool = False
    max_additional_participants: int | None = None
    allow_same_participant_emails: bool = False

    # Waitlist and approval
    has_waitlist: bool = False
    requires_approval: bool = False
    waitlist_text: str | None = None
    approval_req_text: str | None = None
    expiration_time: int | None = None

    # Self-service
    allow_selfcancelxfer: bool = False
    selfcancelxfer_time: int | None = None

    # Financial settings
    is_monetary: bool = False
    financial_type_id: int | None = None
    payment_processor: int | None = None
    fee_label: str | None = None
    default_fee_id: int | None = None
    default_discount_fee_id: int | None = None
    currency: str | None = None
    is_pay_later: bool = False
    pay_later_text: str | None = None
    pay_later_receipt: str | None = None
    is_partial_payment: bool = False
    initial_amount_label: str | None = None
    initial_amount_help_text: str | None = None
    min_initial_amount: float | None = None
    is_billing_required: bool = False

    # Location settings
    is_map: bool = False
    is_show_location: bool = True
    loc_block_id: int | None = None

    # Participant settings
    participant_listing_id: int | None = None
    default_role_id: int | None = None

    # Page content
    intro_text: str | None = None
    footer_text: str | None = None

    # Confirmation page
    is_confirm_enabled: bool = True
    confirm_title: str | None = None
    confirm_text: str | None = None
    confirm_footer_text: str | None = None

    # Confirmation email
    is_email_confirm: bool = False
    confirm_email_text: str | None = None
    confirm_from_name: str | None = None
    confirm_from_email: str | None = None
    cc_confirm: str | None = None
    bcc_confirm: str | None = None

    # Thank you page
    thankyou_title: str | None = None
    thankyou_text: str | None = None
    thankyou_footer_text: str | None = None

    # Related records
    campaign_id: int | None = None
    parent_event_id: int | None = None
    dedupe_rule_group_id: int | None = None
    slot_label_id: int | None = None

    # Social sharing
    is_share: bool = False

    # Audit fields
    created_id: int | None = None
    created_date: str | None = None
    modified_date: str | None = None

    # Reverse relationships (one-to-many)
    # Access participants: await event.participants.all()
    participants: ClassVar[RelatedField] = RelatedField("Participant", "event_id")

    # Foreign key relationships
    # Access parent event: await event.parent_event
    parent_event: ClassVar[ForeignKey[Event]] = ForeignKey("Event", "parent_event_id")
    # Access created by contact: await event.created_by
    created_by: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "created_id")


__all__ = ["Event"]
