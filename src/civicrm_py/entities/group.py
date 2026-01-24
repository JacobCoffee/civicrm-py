"""Group entity models for CiviCRM.

Groups organize contacts into collections for mailing lists, permissions,
and other organizational purposes.
"""

from __future__ import annotations

from typing import ClassVar

from civicrm_py.entities.base import BaseEntity


class Group(BaseEntity, kw_only=True):
    """CiviCRM Group entity.

    Groups organize contacts into collections. They can be static (manually
    managed membership) or smart (dynamic membership based on search criteria).

    Attributes:
        id: Unique group identifier.
        name: Internal group name (machine name).
        title: Human-readable group title.
        description: Group description.
        source: How the group was created.
        saved_search_id: Saved search ID for smart groups.
        is_active: Whether group is active.
        visibility: Group visibility ('User and User Admin', 'Public Pages').
        where_clause: SQL WHERE clause for smart groups.
        select_tables: Tables to select from for smart groups.
        where_tables: Tables to use in WHERE clause.
        group_type: Types of group (Mailing List, Access Control).
        cache_date: When smart group cache was last updated.
        refresh_date: When smart group should be refreshed.
        parents: Parent group IDs.
        children: Child group IDs.
        is_hidden: Whether group is hidden from UI.
        is_reserved: Whether group is reserved/system-managed.
        created_id: Contact ID who created the group.
        frontend_title: Title shown on public pages.
        frontend_description: Description shown on public pages.
        created_date: When the group was created.
        modified_date: When the group was last modified.
    """

    __entity_name__: ClassVar[str] = "Group"

    # Core identification
    id: int | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None

    # Source
    source: str | None = None

    # Smart group settings
    saved_search_id: int | None = None
    where_clause: str | None = None
    select_tables: str | None = None
    where_tables: str | None = None

    # Status and visibility
    is_active: bool = True
    visibility: str | None = None
    is_hidden: bool = False
    is_reserved: bool = False

    # Group type (list of option values)
    group_type: list[str] | None = None

    # Cache settings for smart groups
    cache_date: str | None = None
    refresh_date: str | None = None

    # Hierarchy
    parents: str | None = None
    children: str | None = None

    # Frontend display
    frontend_title: str | None = None
    frontend_description: str | None = None

    # Audit
    created_id: int | None = None
    created_date: str | None = None
    modified_date: str | None = None


class GroupContact(BaseEntity, kw_only=True):
    """CiviCRM GroupContact entity.

    GroupContact represents the relationship between a contact and a group,
    tracking membership status and history.

    Attributes:
        id: Unique group contact identifier.
        group_id: Group the contact belongs to.
        contact_id: Contact who is a member.
        status: Membership status ('Added', 'Removed', 'Pending').
        location_id: Location ID (deprecated).
        email_id: Email ID (deprecated).
        in_method: How contact was added to group.
        out_method: How contact was removed from group.
        date: Date of last status change.
    """

    __entity_name__: ClassVar[str] = "GroupContact"

    # Core identification
    id: int | None = None
    group_id: int | None = None
    contact_id: int | None = None

    # Status
    status: str | None = None

    # Legacy fields
    location_id: int | None = None
    email_id: int | None = None

    # History tracking
    in_method: str | None = None
    out_method: str | None = None
    date: str | None = None


__all__ = ["Group", "GroupContact"]
