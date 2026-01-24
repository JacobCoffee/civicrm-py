"""Note entity model for CiviCRM.

Notes provide a way to attach free-form text annotations to contacts
and other entities.
"""

from __future__ import annotations

from typing import ClassVar

from civicrm_py.entities.base import BaseEntity


class Note(BaseEntity, kw_only=True):
    """CiviCRM Note entity.

    Notes are free-form text annotations that can be attached to contacts
    and other entities to record additional information.

    Attributes:
        id: Unique note identifier.
        entity_table: Table name of the entity (e.g., 'civicrm_contact').
        entity_id: ID of the entity the note is attached to.
        note: Note content/body.
        subject: Note subject/title.
        contact_id: Contact who created the note.
        privacy: Privacy level ('0' = public, '1' = private).
        modified_date: When the note was last modified.
    """

    __entity_name__: ClassVar[str] = "Note"

    # Core identification
    id: int | None = None
    entity_table: str | None = None
    entity_id: int | None = None

    # Content
    note: str | None = None
    subject: str | None = None

    # Metadata
    contact_id: int | None = None
    privacy: str | None = None

    # Timestamp
    modified_date: str | None = None


__all__ = ["Note"]
