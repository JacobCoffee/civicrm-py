"""Entity models for CiviCRM.

This module provides Pydantic-style entity models for all core CiviCRM entities.
Each entity inherits from BaseEntity and provides type-safe access to CiviCRM
data with dirty field tracking and serialization support.

Core Entities:
    - Contact: Base contact entity (Individual, Organization, Household)
    - Activity: Interactions and tasks
    - Contribution: Financial transactions
    - Event: Scheduled gatherings
    - Membership: Organization memberships
    - Participant: Event registrations

Supporting Entities:
    - Address: Physical/postal addresses
    - Email: Email addresses
    - Phone: Phone numbers
    - Group: Contact groupings
    - Tag: Categorization labels
    - Note: Text annotations

Discovery:
    - EntityDiscovery: Dynamic entity class generation from API introspection
    - EntityInfo: Metadata about CiviCRM entities
    - FieldInfo: Metadata about entity fields
    - discover_entities: Convenience function for bulk discovery

Example:
    >>> from civicrm_py.entities import Contact, Individual, Activity
    >>> contact = Individual(first_name="John", last_name="Doe")
    >>> contact.to_dict()
    {'contact_type': 'Individual', 'first_name': 'John', 'last_name': 'Doe'}

Dynamic Discovery Example:
    >>> from civicrm_py.entities import EntityDiscovery
    >>> async with CiviClient() as client:
    ...     discovery = EntityDiscovery(client)
    ...     CustomEntity = await discovery.get_entity_class("Custom_MyEntity")
"""

from __future__ import annotations

from civicrm_py.entities.activity import Activity
from civicrm_py.entities.address import Address
from civicrm_py.entities.base import (
    BaseEntity,
    EntityMeta,
    EntityState,
    EntityT,
    FieldDescriptor,
    entity_from_dict,
    get_entity_name,
)
from civicrm_py.entities.contact import Contact, Household, Individual, Organization
from civicrm_py.entities.contribution import Contribution
from civicrm_py.entities.discovery import (
    EntityDiscovery,
    EntityInfo,
    FieldInfo,
    discover_entities,
)
from civicrm_py.entities.email import Email
from civicrm_py.entities.event import Event
from civicrm_py.entities.group import Group, GroupContact
from civicrm_py.entities.membership import Membership
from civicrm_py.entities.note import Note
from civicrm_py.entities.participant import Participant
from civicrm_py.entities.phone import Phone
from civicrm_py.entities.relationships import (
    ForeignKey,
    ForeignKeyAccessor,
    ManyToManyField,
    ManyToManyManager,
    RelatedField,
    RelatedManager,
    get_relationships,
    get_reverse_relationships,
    register_relationship,
)
from civicrm_py.entities.tag import EntityTag, Tag

__all__ = [
    "Activity",
    "Address",
    "BaseEntity",
    "Contact",
    "Contribution",
    "Email",
    "EntityDiscovery",
    "EntityInfo",
    "EntityMeta",
    "EntityState",
    "EntityT",
    "EntityTag",
    "Event",
    "FieldDescriptor",
    "FieldInfo",
    "ForeignKey",
    "ForeignKeyAccessor",
    "Group",
    "GroupContact",
    "Household",
    "Individual",
    "ManyToManyField",
    "ManyToManyManager",
    "Membership",
    "Note",
    "Organization",
    "Participant",
    "Phone",
    "RelatedField",
    "RelatedManager",
    "Tag",
    "discover_entities",
    "entity_from_dict",
    "get_entity_name",
    "get_relationships",
    "get_reverse_relationships",
    "register_relationship",
]
