"""Activity entity model for CiviCRM.

Activities represent interactions and tasks associated with contacts, such as
meetings, phone calls, emails, and other trackable events.

Relationships:
    - source_contact: Contact who created/performed the activity
    - parent_activity: Parent activity for threaded activities
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from civicrm_py.entities.base import BaseEntity
from civicrm_py.entities.relationships import ForeignKey

if TYPE_CHECKING:
    from civicrm_py.entities.contact import Contact


class Activity(BaseEntity, kw_only=True):
    """CiviCRM Activity entity.

    Activities track interactions and tasks associated with contacts. They can
    represent meetings, phone calls, emails sent, tasks completed, and other
    events that should be recorded in the contact's history.

    Attributes:
        id: Unique activity identifier.
        activity_type_id: Type of activity (references option value).
        subject: Subject/title of the activity.
        details: Full description/details of the activity.
        activity_date_time: When the activity occurred or is scheduled.
        duration: Duration in minutes.
        location: Location where activity took place.
        status_id: Activity status (Scheduled, Completed, Cancelled, etc.).
        priority_id: Priority level (Low, Normal, High, Urgent).
        source_contact_id: Contact who created/performed the activity.
        target_contact_id: Target contacts for this activity.
        assignee_contact_id: Contacts assigned to this activity.
        source_record_id: ID of related record (e.g., contribution, case).
        is_current_revision: Whether this is the current revision.
        is_deleted: Whether activity is deleted.
        is_test: Whether this is test data.
        medium_id: Communication medium (Phone, Email, In Person, etc.).
        result: Outcome/result of the activity.
        is_auto: Whether activity was automatically generated.
        parent_id: Parent activity ID for threaded activities.
        original_id: Original activity ID if this is a copy.
        campaign_id: Associated campaign ID.
        engagement_level: Engagement level for fundraising activities.
        weight: Sorting weight.
        created_date: When the activity was created.
        modified_date: When the activity was last modified.
    """

    __entity_name__: ClassVar[str] = "Activity"

    # Core identification
    id: int | None = None
    activity_type_id: int | None = None
    subject: str | None = None
    details: str | None = None

    # Timing
    activity_date_time: str | None = None
    duration: int | None = None

    # Location
    location: str | None = None

    # Status and priority
    status_id: int | None = None
    priority_id: int | None = None

    # Related contacts
    source_contact_id: int | None = None
    target_contact_id: list[int] | None = None
    assignee_contact_id: list[int] | None = None

    # Related records
    source_record_id: int | None = None
    parent_id: int | None = None
    original_id: int | None = None
    campaign_id: int | None = None

    # Flags
    is_current_revision: bool = True
    is_deleted: bool = False
    is_test: bool = False
    is_auto: bool = False

    # Additional details
    medium_id: int | None = None
    result: str | None = None
    engagement_level: int | None = None
    weight: int | None = None

    # Timestamps
    created_date: str | None = None
    modified_date: str | None = None

    # Foreign key relationships
    # Access source contact: await activity.source_contact
    source_contact: ClassVar[ForeignKey[Contact]] = ForeignKey("Contact", "source_contact_id")
    # Access parent activity: await activity.parent_activity
    parent_activity: ClassVar[ForeignKey[Activity]] = ForeignKey("Activity", "parent_id")


__all__ = ["Activity"]
