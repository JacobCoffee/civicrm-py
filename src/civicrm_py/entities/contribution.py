"""Contribution entity model for CiviCRM.

Contributions represent financial transactions including donations, payments,
and other monetary exchanges with contacts.

Relationships:
    - contact: Contact who made the contribution
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Contribution(BaseEntity, kw_only=True):
    """CiviCRM Contribution entity.

    Contributions track financial transactions with contacts. This includes
    donations, membership dues, event fees, and other payments.

    Attributes:
        id: Unique contribution identifier.
        contact_id: Contact who made the contribution.
        financial_type_id: Type of contribution (Donation, Event Fee, etc.).
        contribution_page_id: Contribution page ID if made online.
        payment_instrument_id: Payment method (Credit Card, Check, Cash, etc.).
        receive_date: When the contribution was received.
        non_deductible_amount: Non tax-deductible portion of the amount.
        total_amount: Total contribution amount.
        fee_amount: Processing/transaction fees.
        net_amount: Net amount after fees.
        trxn_id: Transaction ID from payment processor.
        invoice_id: Invoice identifier.
        invoice_number: Human-readable invoice number.
        currency: ISO 4217 currency code (USD, EUR, etc.).
        cancel_date: Date contribution was cancelled.
        cancel_reason: Reason for cancellation.
        receipt_date: Date receipt was sent.
        thankyou_date: Date thank you was sent.
        source: Source/origin of the contribution.
        amount_level: Amount level for price sets.
        contribution_recur_id: Recurring contribution ID.
        is_test: Whether this is test data.
        is_pay_later: Whether payment is deferred.
        contribution_status_id: Status (Pending, Completed, Cancelled, etc.).
        address_id: Associated address ID.
        check_number: Check number if paid by check.
        campaign_id: Associated campaign ID.
        creditnote_id: Credit note ID if refunded.
        tax_amount: Tax amount.
        revenue_recognition_date: Date for revenue recognition.
        is_template: Whether this is a template contribution.
        created_date: When the contribution was created.
        modified_date: When the contribution was last modified.
    """

    __entity_name__: ClassVar[str] = "Contribution"

    # Core identification
    id: int | None = None
    contact_id: int | None = None
    financial_type_id: int | None = None
    contribution_page_id: int | None = None
    payment_instrument_id: int | None = None

    # Dates
    receive_date: str | None = None
    cancel_date: str | None = None
    receipt_date: str | None = None
    thankyou_date: str | None = None
    revenue_recognition_date: str | None = None

    # Amounts
    non_deductible_amount: float | None = None
    total_amount: float | None = None
    fee_amount: float | None = None
    net_amount: float | None = None
    tax_amount: float | None = None
    currency: str | None = None

    # Transaction details
    trxn_id: str | None = None
    invoice_id: str | None = None
    invoice_number: str | None = None
    check_number: str | None = None

    # Cancellation
    cancel_reason: str | None = None

    # Source and context
    source: str | None = None
    amount_level: str | None = None

    # Related records
    contribution_recur_id: int | None = None
    address_id: int | None = None
    campaign_id: int | None = None
    creditnote_id: str | None = None

    # Status and flags
    contribution_status_id: int | None = None
    is_test: bool = False
    is_pay_later: bool = False
    is_template: bool = False

    # Timestamps
    created_date: str | None = None
    modified_date: str | None = None

    # Foreign key relationships
    # Access contact: await contribution.contact
    contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "contact_id")


__all__ = ["Contribution"]
