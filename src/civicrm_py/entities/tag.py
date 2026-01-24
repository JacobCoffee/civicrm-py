"""Tag entity models for CiviCRM.

Tags provide flexible categorization and labeling of contacts and other
entities through a hierarchical tagging system.
"""

from __future__ import annotations

from typing import ClassVar

from civicrm_py.entities.base import BaseEntity


class Tag(BaseEntity, kw_only=True):
    """CiviCRM Tag entity.

    Tags provide a flexible way to categorize contacts and other entities.
    Tags can be hierarchical with parent-child relationships.

    Attributes:
        id: Unique tag identifier.
        name: Tag name.
        description: Tag description.
        parent_id: Parent tag ID for hierarchical tags.
        is_selectable: Whether tag can be selected by users.
        is_reserved: Whether tag is system-reserved.
        is_tagset: Whether this is a tag set (container for tags).
        used_for: Entity types this tag can be applied to.
        color: Hex color code for visual display.
        created_id: Contact ID who created the tag.
        created_date: When the tag was created.
        modified_date: When the tag was last modified.
    """

    __entity_name__: ClassVar[str] = "Tag"

    # Core identification
    id: int | None = None
    name: str | None = None
    description: str | None = None

    # Hierarchy
    parent_id: int | None = None

    # Status
    is_selectable: bool = True
    is_reserved: bool = False
    is_tagset: bool = False

    # Usage
    used_for: list[str] | None = None

    # Display
    color: str | None = None

    # Audit
    created_id: int | None = None
    created_date: str | None = None
    modified_date: str | None = None


class EntityTag(BaseEntity, kw_only=True):
    """CiviCRM EntityTag entity.

    EntityTag represents the application of a tag to an entity (contact,
    activity, case, etc.).

    Attributes:
        id: Unique entity tag identifier.
        entity_table: Table name of the tagged entity (e.g., 'civicrm_contact').
        entity_id: ID of the tagged entity.
        tag_id: ID of the applied tag.
    """

    __entity_name__: ClassVar[str] = "EntityTag"

    # Core identification
    id: int | None = None
    entity_table: str | None = None
    entity_id: int | None = None
    tag_id: int | None = None


__all__ = ["EntityTag", "Tag"]
