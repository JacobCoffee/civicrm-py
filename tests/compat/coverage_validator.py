"""Coverage validation for CiviCRM API entity and action implementation.

This module provides comprehensive tools for validating the coverage of
civi-py's implementation against the CiviCRM API v4. It fetches available
entities and actions from the API and compares them against the implemented
entity classes and manager methods.

Key Components:
    - EntityCoverageValidator: Validates entity class coverage
    - ActionCoverageValidator: Validates action method coverage per entity
    - CoverageReport: Structured coverage report with metrics
    - generate_coverage_report: CLI-friendly report generator
    - DetailedActionReport: Per-entity action coverage with priority analysis

Phase 8.5.8 Enhancements:
    - 100% action coverage validation per entity
    - Detailed action mapping with priority classification
    - Custom action identification and tracking
    - Per-entity and overall coverage metrics

Example:
    >>> async with CiviClient() as client:
    ...     validator = EntityCoverageValidator(client)
    ...     report = await validator.generate_report()
    ...     report.save_json("coverage_report.json")
    ...     print(report.to_console())

    >>> async with CiviClient() as client:
    ...     validator = ActionCoverageValidator(client)
    ...     detailed = await validator.generate_detailed_report("Contact")
    ...     print(f"Coverage: {detailed.coverage_percentage:.1f}%")
    ...     print(f"Missing critical: {len(detailed.missing_critical_actions)}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from civi_py.entities import (
    Activity,
    Address,
    Contact,
    Contribution,
    Email,
    EntityTag,
    Event,
    Group,
    GroupContact,
    Household,
    Individual,
    Membership,
    Note,
    Organization,
    Participant,
    Phone,
    Tag,
)
from civi_py.entities.base import EntityMeta
from civi_py.entities.discovery import EntityDiscovery, EntityInfo
from tests.compat.action_mapping import (
    ActionInfo,
    ActionMapping,
    ActionPriority,
)

if TYPE_CHECKING:
    from civi_py.core.client import CiviClient

__all__ = [
    "ActionCoverageReport",
    "ActionCoverageValidator",
    "CoverageReport",
    "DetailedActionReport",
    "EntityCoverageReport",
    "EntityCoverageValidator",
    "EntityPriority",
    "MissingAction",
    "MissingEntity",
    "OverallActionCoverageReport",
    "generate_coverage_reports",
    "generate_detailed_coverage_report",
]

logger = logging.getLogger(__name__)


class EntityPriority(Enum):
    """Priority levels for entity implementation.

    Based on CiviCRM entity type and common usage patterns.
    """

    CRITICAL = 1  # Core entities (Contact, Activity, Contribution)
    HIGH = 2  # Important entities (Event, Membership, Participant)
    MEDIUM = 3  # Supporting entities (Address, Email, Phone, etc.)
    LOW = 4  # Utility entities (OptionValue, Domain, etc.)
    INTERNAL = 5  # Internal/system entities


# Known CiviCRM core entities and their priorities
ENTITY_PRIORITIES: dict[str, EntityPriority] = {
    # Critical - Core CRM entities
    "Contact": EntityPriority.CRITICAL,
    "Activity": EntityPriority.CRITICAL,
    "Contribution": EntityPriority.CRITICAL,
    "Relationship": EntityPriority.CRITICAL,
    # High - Important business entities
    "Event": EntityPriority.HIGH,
    "Membership": EntityPriority.HIGH,
    "Participant": EntityPriority.HIGH,
    "MembershipType": EntityPriority.HIGH,
    "ContributionRecur": EntityPriority.HIGH,
    "Case": EntityPriority.HIGH,
    "Campaign": EntityPriority.HIGH,
    "Pledge": EntityPriority.HIGH,
    "Grant": EntityPriority.HIGH,
    # Medium - Supporting entities
    "Address": EntityPriority.MEDIUM,
    "Email": EntityPriority.MEDIUM,
    "Phone": EntityPriority.MEDIUM,
    "Website": EntityPriority.MEDIUM,
    "IM": EntityPriority.MEDIUM,
    "Group": EntityPriority.MEDIUM,
    "GroupContact": EntityPriority.MEDIUM,
    "Tag": EntityPriority.MEDIUM,
    "EntityTag": EntityPriority.MEDIUM,
    "Note": EntityPriority.MEDIUM,
    "Attachment": EntityPriority.MEDIUM,
    "RelationshipType": EntityPriority.MEDIUM,
    "ActivityContact": EntityPriority.MEDIUM,
    "FinancialType": EntityPriority.MEDIUM,
    "PaymentProcessor": EntityPriority.MEDIUM,
    "ContributionPage": EntityPriority.MEDIUM,
    "EventType": EntityPriority.MEDIUM,
    "CustomGroup": EntityPriority.MEDIUM,
    "CustomField": EntityPriority.MEDIUM,
    # Low - Utility/config entities
    "OptionValue": EntityPriority.LOW,
    "OptionGroup": EntityPriority.LOW,
    "LocationType": EntityPriority.LOW,
    "StateProvince": EntityPriority.LOW,
    "Country": EntityPriority.LOW,
    "County": EntityPriority.LOW,
    "MessageTemplate": EntityPriority.LOW,
    "UFGroup": EntityPriority.LOW,
    "UFField": EntityPriority.LOW,
    "Setting": EntityPriority.LOW,
    "Job": EntityPriority.LOW,
    "SavedSearch": EntityPriority.LOW,
    "ReportInstance": EntityPriority.LOW,
    "Navigation": EntityPriority.LOW,
    # Internal - System entities
    "Entity": EntityPriority.INTERNAL,
    "Domain": EntityPriority.INTERNAL,
    "ACL": EntityPriority.INTERNAL,
    "ACLCache": EntityPriority.INTERNAL,
    "ACLContactCache": EntityPriority.INTERNAL,
    "ACLEntityRole": EntityPriority.INTERNAL,
    "Cache": EntityPriority.INTERNAL,
    "Log": EntityPriority.INTERNAL,
    "Queue": EntityPriority.INTERNAL,
    "Managed": EntityPriority.INTERNAL,
    "Extension": EntityPriority.INTERNAL,
    "System": EntityPriority.INTERNAL,
    "Cxn": EntityPriority.INTERNAL,
    "Afform": EntityPriority.INTERNAL,
    "SearchDisplay": EntityPriority.INTERNAL,
    "SKEntity": EntityPriority.INTERNAL,
}

# Standard CiviCRM API actions
STANDARD_ACTIONS: set[str] = {
    "get",
    "create",
    "update",
    "delete",
    "save",
    "getFields",
    "getActions",
    "getLinks",
    "checkAccess",
    "replace",
    "refresh",
    "getChecksum",
    "validateChecksum",
}

# Actions that EntityManager supports
MANAGER_ACTIONS: set[str] = {
    "get",
    "create",
    "update",
    "delete",
    "get_fields",  # Maps to getFields
    "count",  # Via get with limit=0
    "exists",  # Via get with limit=1
    "get_or_create",  # Via get + create
    "update_or_create",  # Via get + update/create
    "bulk_create",  # Via multiple create calls
}


@dataclass
class MissingEntity:
    """Represents a CiviCRM entity not yet implemented in civi-py.

    Attributes:
        name: Entity name from CiviCRM API.
        title: Human-readable title.
        description: Entity description.
        priority: Implementation priority.
        entity_type: CiviCRM entity type (primary, secondary, bridge, etc.).
        fields_count: Number of fields on this entity.
        dependencies: Other entities this entity depends on.
        notes: Additional implementation notes.
    """

    name: str
    title: str | None = None
    description: str | None = None
    priority: EntityPriority = EntityPriority.LOW
    entity_type: str | None = None
    fields_count: int = 0
    dependencies: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.name,
            "priority_value": self.priority.value,
            "entity_type": self.entity_type,
            "fields_count": self.fields_count,
            "dependencies": self.dependencies,
            "notes": self.notes,
        }


@dataclass
class MissingAction:
    """Represents a CiviCRM action not yet supported for an entity.

    Attributes:
        entity_name: The entity this action belongs to.
        action_name: Action name from CiviCRM API.
        description: Action description if available.
        is_standard: Whether this is a standard CRUD action.
        is_custom: Whether this is a custom action specific to the entity.
        notes: Additional implementation notes.
    """

    entity_name: str
    action_name: str
    description: str | None = None
    is_standard: bool = True
    is_custom: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_name": self.entity_name,
            "action_name": self.action_name,
            "description": self.description,
            "is_standard": self.is_standard,
            "is_custom": self.is_custom,
            "notes": self.notes,
        }


@dataclass
class EntityCoverageReport:
    """Coverage report for entity implementations.

    Attributes:
        total_entities: Total number of entities in CiviCRM.
        implemented_entities: Number of implemented entities.
        missing_entities: List of missing entities with details.
        implemented_names: Set of implemented entity names.
        api_entities: List of all EntityInfo from API.
        generated_at: Report generation timestamp.
    """

    total_entities: int = 0
    implemented_entities: int = 0
    missing_entities: list[MissingEntity] = field(default_factory=list)
    implemented_names: set[str] = field(default_factory=set)
    api_entities: list[EntityInfo] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def coverage_percentage(self) -> float:
        """Calculate entity coverage percentage."""
        if self.total_entities == 0:
            return 0.0
        return (self.implemented_entities / self.total_entities) * 100

    @property
    def missing_count(self) -> int:
        """Number of missing entities."""
        return len(self.missing_entities)

    def missing_by_priority(self) -> dict[EntityPriority, list[MissingEntity]]:
        """Group missing entities by priority."""
        result: dict[EntityPriority, list[MissingEntity]] = {priority: [] for priority in EntityPriority}
        for entity in self.missing_entities:
            result[entity.priority].append(entity)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": {
                "total_entities": self.total_entities,
                "implemented_entities": self.implemented_entities,
                "missing_entities": self.missing_count,
                "coverage_percentage": round(self.coverage_percentage, 2),
                "generated_at": self.generated_at.isoformat(),
            },
            "implemented": sorted(self.implemented_names),
            "missing": [e.to_dict() for e in self.missing_entities],
            "missing_by_priority": {
                priority.name: [e.to_dict() for e in entities]
                for priority, entities in self.missing_by_priority().items()
                if entities
            },
        }

    def to_console(self) -> str:
        """Generate console-friendly report output."""
        lines = [
            "=" * 60,
            "ENTITY COVERAGE REPORT",
            "=" * 60,
            "",
            f"Total CiviCRM Entities: {self.total_entities}",
            f"Implemented Entities:   {self.implemented_entities}",
            f"Missing Entities:       {self.missing_count}",
            f"Coverage:               {self.coverage_percentage:.1f}%",
            f"Generated:              {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "-" * 60,
            "IMPLEMENTED ENTITIES",
            "-" * 60,
        ]

        lines.extend(f"  [x] {name}" for name in sorted(self.implemented_names))

        lines.extend(
            [
                "",
                "-" * 60,
                "MISSING ENTITIES (by priority)",
                "-" * 60,
            ],
        )

        for priority in EntityPriority:
            entities = [e for e in self.missing_entities if e.priority == priority]
            if entities:
                lines.append(f"\n  {priority.name} ({len(entities)}):")
                for entity in sorted(entities, key=lambda x: x.name):
                    lines.append(f"    [ ] {entity.name}")
                    if entity.title and entity.title != entity.name:
                        lines.append(f"        Title: {entity.title}")
                    if entity.notes:
                        lines.append(f"        Note: {entity.notes}")

        lines.extend(["", "=" * 60])
        return "\n".join(lines)

    def save_json(self, path: str | Path) -> None:
        """Save report to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Entity coverage report saved to %s", path)

    def save_console(self, path: str | Path) -> None:
        """Save console report to text file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_console())
        logger.info("Entity coverage console report saved to %s", path)


@dataclass
class ActionCoverageReport:
    """Coverage report for action implementations per entity.

    Attributes:
        entity_name: Name of the entity.
        available_actions: Actions available in CiviCRM API.
        implemented_actions: Actions implemented in EntityManager.
        missing_actions: List of missing actions.
        custom_actions: Entity-specific custom actions.
        generated_at: Report generation timestamp.
    """

    entity_name: str
    available_actions: set[str] = field(default_factory=set)
    implemented_actions: set[str] = field(default_factory=set)
    missing_actions: list[MissingAction] = field(default_factory=list)
    custom_actions: list[MissingAction] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def coverage_percentage(self) -> float:
        """Calculate action coverage percentage."""
        if not self.available_actions:
            return 0.0
        # Count actions that are either implemented or mappable
        covered = len(self.available_actions & self._mapped_actions())
        return (covered / len(self.available_actions)) * 100

    def _mapped_actions(self) -> set[str]:
        """Get the set of CiviCRM actions that map to implemented methods."""
        # Map CiviCRM actions to our manager methods
        action_map = {
            "get": {"get", "count", "exists", "filter", "all"},
            "create": {"create", "bulk_create", "get_or_create", "update_or_create"},
            "update": {"update", "update_or_create"},
            "delete": {"delete"},
            "getFields": {"get_fields"},
            "save": {"save"},
        }
        result: set[str] = set()
        for action, methods in action_map.items():
            if methods & self.implemented_actions:
                result.add(action)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_name": self.entity_name,
            "summary": {
                "available_actions": len(self.available_actions),
                "implemented_actions": len(self.implemented_actions),
                "coverage_percentage": round(self.coverage_percentage, 2),
                "generated_at": self.generated_at.isoformat(),
            },
            "available": sorted(self.available_actions),
            "implemented": sorted(self.implemented_actions),
            "missing": [a.to_dict() for a in self.missing_actions],
            "custom_actions": [a.to_dict() for a in self.custom_actions],
        }


@dataclass
class CoverageReport:
    """Combined coverage report for entities and actions.

    Attributes:
        entity_report: Entity coverage report.
        action_reports: Per-entity action coverage reports.
        generated_at: Report generation timestamp.
    """

    entity_report: EntityCoverageReport
    action_reports: dict[str, ActionCoverageReport] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def overall_entity_coverage(self) -> float:
        """Overall entity coverage percentage."""
        return self.entity_report.coverage_percentage

    @property
    def overall_action_coverage(self) -> float:
        """Average action coverage across all entities."""
        if not self.action_reports:
            return 0.0
        total = sum(r.coverage_percentage for r in self.action_reports.values())
        return total / len(self.action_reports)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": {
                "entity_coverage": round(self.overall_entity_coverage, 2),
                "action_coverage": round(self.overall_action_coverage, 2),
                "generated_at": self.generated_at.isoformat(),
            },
            "entities": self.entity_report.to_dict(),
            "actions": {name: report.to_dict() for name, report in self.action_reports.items()},
        }

    def save_json(self, path: str | Path) -> None:
        """Save complete report to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Coverage report saved to %s", path)


class EntityCoverageValidator:
    """Validates entity implementation coverage against CiviCRM API.

    This validator fetches all available entities from a CiviCRM instance
    and compares them against the entities implemented in civi-py.

    Attributes:
        client: CiviClient for API access.
        discovery: EntityDiscovery instance for API introspection.

    Example:
        >>> async with CiviClient() as client:
        ...     validator = EntityCoverageValidator(client)
        ...     report = await validator.generate_report()
        ...     print(f"Coverage: {report.coverage_percentage:.1f}%")
    """

    # Static mapping of implemented entity classes
    IMPLEMENTED_ENTITIES: ClassVar[dict[str, type[Any]]] = {
        "Contact": Contact,
        "Individual": Individual,
        "Organization": Organization,
        "Household": Household,
        "Activity": Activity,
        "Address": Address,
        "Contribution": Contribution,
        "Email": Email,
        "Event": Event,
        "Group": Group,
        "GroupContact": GroupContact,
        "Membership": Membership,
        "Note": Note,
        "Participant": Participant,
        "Phone": Phone,
        "Tag": Tag,
        "EntityTag": EntityTag,
    }

    def __init__(self, client: CiviClient) -> None:
        """Initialize entity coverage validator.

        Args:
            client: CiviClient for API access.
        """
        self.client = client
        self.discovery = EntityDiscovery(client)

    def get_implemented_entities(self) -> set[str]:
        """Get set of implemented entity names.

        Returns:
            Set of entity names that have implementations.
        """
        # Combine static implementations with dynamically registered ones
        implemented = set(self.IMPLEMENTED_ENTITIES.keys())

        # Also check the entity registry
        for name in EntityMeta._registry:
            implemented.add(name)

        return implemented

    async def get_api_entities(self) -> list[EntityInfo]:
        """Fetch all available entities from CiviCRM API.

        Returns:
            List of EntityInfo objects for all available entities.
        """
        return await self.discovery.get_entities()

    def _get_entity_priority(  # noqa: PLR0911
        self,
        entity: EntityInfo,
    ) -> EntityPriority:
        """Determine implementation priority for an entity.

        Args:
            entity: EntityInfo from CiviCRM API.

        Returns:
            Appropriate priority level.
        """
        # Check known priorities first
        if entity.name in ENTITY_PRIORITIES:
            return ENTITY_PRIORITIES[entity.name]

        # Use heuristics based on entity type and name
        if entity.name.startswith("Custom_"):
            return EntityPriority.LOW
        if entity.name.startswith("CiviCase") or entity.name.startswith("Civi"):
            return EntityPriority.MEDIUM
        if entity.name.endswith("Type") or entity.name.endswith("Status"):
            return EntityPriority.LOW
        if entity.type == "primary":
            return EntityPriority.HIGH
        if entity.type == "secondary":
            return EntityPriority.MEDIUM
        if entity.type == "bridge":
            return EntityPriority.LOW

        return EntityPriority.LOW

    async def _get_entity_fields_count(self, entity_name: str) -> int:
        """Get the number of fields for an entity.

        Args:
            entity_name: Name of the entity.

        Returns:
            Number of fields, or 0 if unavailable.
        """
        try:
            fields = await self.discovery.get_fields(entity_name)
            return len(fields)
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch fields for %s", entity_name)
            return 0

    async def generate_report(
        self,
        *,
        include_field_counts: bool = False,
    ) -> EntityCoverageReport:
        """Generate entity coverage report.

        Args:
            include_field_counts: Whether to fetch field counts for missing
                entities (slower but more informative).

        Returns:
            EntityCoverageReport with coverage details.
        """
        implemented = self.get_implemented_entities()
        api_entities = await self.get_api_entities()

        missing: list[MissingEntity] = []

        for entity in api_entities:
            if entity.name not in implemented:
                # Determine fields count if requested
                fields_count = 0
                if include_field_counts:
                    fields_count = await self._get_entity_fields_count(entity.name)

                missing_entity = MissingEntity(
                    name=entity.name,
                    title=entity.title,
                    description=entity.description,
                    priority=self._get_entity_priority(entity),
                    entity_type=entity.type,
                    fields_count=fields_count,
                )
                missing.append(missing_entity)

        # Sort missing by priority
        missing.sort(key=lambda x: (x.priority.value, x.name))

        return EntityCoverageReport(
            total_entities=len(api_entities),
            implemented_entities=len(implemented),
            missing_entities=missing,
            implemented_names=implemented,
            api_entities=api_entities,
        )


@dataclass
class DetailedActionReport:
    """Detailed action coverage report for a single entity.

    This report provides comprehensive information about action coverage
    for a specific entity, including:
    - All available actions from API
    - Standard actions with implementation status
    - Custom/entity-specific actions
    - Priority-based classification of missing actions
    - Methods available in EntityManager

    Attributes:
        entity_name: Name of the CiviCRM entity.
        api_actions: Actions available from CiviCRM API getActions().
        action_mapping: Complete ActionMapping with status.
        fetched_at: When API actions were fetched.
        api_action_details: Detailed info for each API action.
    """

    entity_name: str
    api_actions: set[str] = field(default_factory=set)
    action_mapping: ActionMapping | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    api_action_details: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize action mapping if not provided."""
        if self.action_mapping is None:
            self.action_mapping = ActionMapping(
                entity_name=self.entity_name,
                api_actions=self.api_actions,
            )
        elif self.api_actions:
            self.action_mapping.api_actions = self.api_actions

    @property
    def coverage_percentage(self) -> float:
        """Calculate overall action coverage percentage."""
        if self.action_mapping is None:
            return 0.0
        return self.action_mapping.coverage_percentage()

    @property
    def api_coverage_percentage(self) -> float:
        """Calculate coverage against actual API actions."""
        if self.action_mapping is None or not self.api_actions:
            return 0.0
        return self.action_mapping.api_coverage_percentage()

    @property
    def standard_actions_covered(self) -> list[str]:
        """Get list of standard actions that are implemented."""
        if self.action_mapping is None:
            return []
        return [name for name, info in self.action_mapping.standard_actions.items() if info.is_implemented]

    @property
    def standard_actions_missing(self) -> list[str]:
        """Get list of standard actions that are NOT implemented."""
        if self.action_mapping is None:
            return []
        return [name for name, info in self.action_mapping.standard_actions.items() if not info.is_implemented]

    @property
    def custom_actions_available(self) -> list[str]:
        """Get list of known custom actions for this entity."""
        if self.action_mapping is None:
            return []
        return [a.name for a in self.action_mapping.custom_actions]

    @property
    def unknown_actions(self) -> set[str]:
        """Get API actions not in our mapping (potentially new or undocumented)."""
        if self.action_mapping is None:
            return self.api_actions

        known_actions = set(self.action_mapping.standard_actions.keys())
        known_actions.update(a.name for a in self.action_mapping.custom_actions)
        return self.api_actions - known_actions

    @property
    def missing_critical_actions(self) -> list[ActionInfo]:
        """Get critical priority actions that are missing."""
        if self.action_mapping is None:
            return []
        return [a for a in self.action_mapping.unimplemented_actions if a.priority == ActionPriority.CRITICAL]

    @property
    def missing_high_priority_actions(self) -> list[ActionInfo]:
        """Get high priority actions that are missing."""
        if self.action_mapping is None:
            return []
        return [a for a in self.action_mapping.unimplemented_actions if a.priority == ActionPriority.HIGH]

    def get_action_status(self, action_name: str) -> dict[str, Any]:
        """Get detailed status for a specific action.

        Args:
            action_name: Name of the action.

        Returns:
            Dict with action status details.
        """
        if self.action_mapping is None:
            return {"action": action_name, "status": "unknown"}
        return self.action_mapping.get_action_status(action_name)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_name": self.entity_name,
            "summary": {
                "total_standard_actions": len(self.action_mapping.standard_actions) if self.action_mapping else 0,
                "covered_standard_actions": len(self.standard_actions_covered),
                "missing_standard_actions": len(self.standard_actions_missing),
                "custom_actions_known": len(self.custom_actions_available),
                "api_actions_count": len(self.api_actions),
                "unknown_api_actions": len(self.unknown_actions),
                "coverage_percentage": round(self.coverage_percentage, 2),
                "api_coverage_percentage": round(self.api_coverage_percentage, 2),
                "missing_critical": len(self.missing_critical_actions),
                "missing_high_priority": len(self.missing_high_priority_actions),
                "fetched_at": self.fetched_at.isoformat(),
            },
            "standard_actions": {
                "covered": self.standard_actions_covered,
                "missing": self.standard_actions_missing,
            },
            "custom_actions": self.custom_actions_available,
            "api_actions": sorted(self.api_actions),
            "unknown_actions": sorted(self.unknown_actions),
            "missing_by_priority": {
                "critical": [a.to_dict() for a in self.missing_critical_actions],
                "high": [a.to_dict() for a in self.missing_high_priority_actions],
            },
            "action_details": self.action_mapping.to_dict() if self.action_mapping else None,
        }

    def to_console(self) -> str:
        """Generate console-friendly report output."""
        lines = [
            "=" * 70,
            f"ACTION COVERAGE REPORT: {self.entity_name}",
            "=" * 70,
            "",
            f"  API Actions Available:    {len(self.api_actions)}",
            f"  Standard Actions Total:   {len(self.action_mapping.standard_actions) if self.action_mapping else 0}",
            f"  Standard Actions Covered: {len(self.standard_actions_covered)}",
            f"  Standard Actions Missing: {len(self.standard_actions_missing)}",
            f"  Custom Actions Known:     {len(self.custom_actions_available)}",
            f"  Unknown API Actions:      {len(self.unknown_actions)}",
            "",
            f"  Overall Coverage:         {self.coverage_percentage:.1f}%",
            f"  API Coverage:             {self.api_coverage_percentage:.1f}%",
            "",
        ]

        # Covered actions
        if self.standard_actions_covered:
            lines.extend(
                [
                    "-" * 70,
                    "IMPLEMENTED STANDARD ACTIONS",
                    "-" * 70,
                ],
            )
            lines.extend(f"  [x] {action}" for action in sorted(self.standard_actions_covered))

        # Missing actions
        if self.standard_actions_missing:
            lines.extend(
                [
                    "",
                    "-" * 70,
                    "MISSING STANDARD ACTIONS",
                    "-" * 70,
                ],
            )
            for action in sorted(self.standard_actions_missing):
                status = self.get_action_status(action)
                priority = status.get("priority", "UNKNOWN")
                lines.append(f"  [ ] {action} (priority: {priority})")

        # Custom actions
        if self.custom_actions_available:
            lines.extend(
                [
                    "",
                    "-" * 70,
                    "KNOWN CUSTOM ACTIONS",
                    "-" * 70,
                ],
            )
            for action in sorted(self.custom_actions_available):
                status = self.get_action_status(action)
                implemented = "x" if status.get("status") == "implemented" else " "
                lines.append(f"  [{implemented}] {action}")

        # Unknown actions from API
        if self.unknown_actions:
            lines.extend(
                [
                    "",
                    "-" * 70,
                    "UNKNOWN API ACTIONS (needs mapping)",
                    "-" * 70,
                ],
            )
            lines.extend(f"  [?] {action}" for action in sorted(self.unknown_actions))

        # Priority issues
        if self.missing_critical_actions:
            lines.extend(
                [
                    "",
                    "-" * 70,
                    "CRITICAL PRIORITY MISSING (must implement)",
                    "-" * 70,
                ],
            )
            lines.extend(f"  [!] {action.name}: {action.description}" for action in self.missing_critical_actions)

        lines.extend(["", "=" * 70])
        return "\n".join(lines)

    def save_json(self, path: str | Path) -> None:
        """Save report to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Detailed action report saved to %s", path)

    def save_console(self, path: str | Path) -> None:
        """Save console report to text file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_console())
        logger.info("Detailed action console report saved to %s", path)


@dataclass
class OverallActionCoverageReport:
    """Overall action coverage report across all entities.

    Aggregates action coverage data from multiple entities to provide
    an overall view of API action implementation status.

    Attributes:
        entity_reports: Dict of entity names to their DetailedActionReports.
        generated_at: Report generation timestamp.
    """

    entity_reports: dict[str, DetailedActionReport] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_entities(self) -> int:
        """Number of entities in report."""
        return len(self.entity_reports)

    @property
    def average_coverage(self) -> float:
        """Average coverage percentage across all entities."""
        if not self.entity_reports:
            return 0.0
        total = sum(r.coverage_percentage for r in self.entity_reports.values())
        return total / len(self.entity_reports)

    @property
    def average_api_coverage(self) -> float:
        """Average API coverage percentage across all entities."""
        if not self.entity_reports:
            return 0.0
        total = sum(r.api_coverage_percentage for r in self.entity_reports.values())
        return total / len(self.entity_reports)

    @property
    def entities_with_full_coverage(self) -> list[str]:
        """Entities with 100% standard action coverage."""
        return [name for name, report in self.entity_reports.items() if report.coverage_percentage >= 100.0]

    @property
    def entities_with_missing_critical(self) -> list[str]:
        """Entities with missing critical actions."""
        return [name for name, report in self.entity_reports.items() if report.missing_critical_actions]

    @property
    def all_missing_critical_actions(self) -> list[tuple[str, ActionInfo]]:
        """All critical actions missing across all entities."""
        return [
            (name, action) for name, report in self.entity_reports.items() for action in report.missing_critical_actions
        ]

    @property
    def all_unknown_actions(self) -> dict[str, set[str]]:
        """Unknown API actions across all entities."""
        return {name: report.unknown_actions for name, report in self.entity_reports.items() if report.unknown_actions}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": {
                "total_entities": self.total_entities,
                "average_coverage": round(self.average_coverage, 2),
                "average_api_coverage": round(self.average_api_coverage, 2),
                "entities_with_full_coverage": len(self.entities_with_full_coverage),
                "entities_with_missing_critical": len(self.entities_with_missing_critical),
                "total_unknown_actions": sum(len(u) for u in self.all_unknown_actions.values()),
                "generated_at": self.generated_at.isoformat(),
            },
            "entity_coverage": {
                name: {
                    "coverage_percentage": round(report.coverage_percentage, 2),
                    "api_coverage_percentage": round(report.api_coverage_percentage, 2),
                    "missing_critical": len(report.missing_critical_actions),
                    "unknown_actions": len(report.unknown_actions),
                }
                for name, report in self.entity_reports.items()
            },
            "full_coverage_entities": sorted(self.entities_with_full_coverage),
            "missing_critical": [
                {"entity": name, "action": action.name, "description": action.description}
                for name, action in self.all_missing_critical_actions
            ],
            "unknown_actions": {name: sorted(actions) for name, actions in self.all_unknown_actions.items()},
            "detailed_reports": {name: report.to_dict() for name, report in self.entity_reports.items()},
        }

    def to_console(self) -> str:
        """Generate console-friendly summary report."""
        lines = [
            "=" * 70,
            "OVERALL ACTION COVERAGE REPORT",
            "=" * 70,
            "",
            f"  Total Entities Analyzed:      {self.total_entities}",
            f"  Average Coverage:             {self.average_coverage:.1f}%",
            f"  Average API Coverage:         {self.average_api_coverage:.1f}%",
            f"  Full Coverage Entities:       {len(self.entities_with_full_coverage)}",
            f"  Entities with Missing Critical: {len(self.entities_with_missing_critical)}",
            f"  Generated:                    {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "-" * 70,
            "PER-ENTITY COVERAGE",
            "-" * 70,
        ]

        # Sort entities by coverage (ascending, so lowest first)
        sorted_entities = sorted(
            self.entity_reports.items(),
            key=lambda x: x[1].coverage_percentage,
        )

        for name, report in sorted_entities:
            status = "CRITICAL" if report.missing_critical_actions else ""
            status = f" [{status}]" if status else ""
            lines.append(
                f"  {name:25} {report.coverage_percentage:5.1f}% (API: {report.api_coverage_percentage:5.1f}%){status}",
            )

        # Missing critical actions
        if self.all_missing_critical_actions:
            lines.extend(
                [
                    "",
                    "-" * 70,
                    "CRITICAL MISSING ACTIONS",
                    "-" * 70,
                ],
            )
            for entity_name, action in self.all_missing_critical_actions:
                lines.append(f"  {entity_name}.{action.name}: {action.description}")

        lines.extend(["", "=" * 70])
        return "\n".join(lines)

    def save_json(self, path: str | Path) -> None:
        """Save report to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Overall action coverage report saved to %s", path)

    def save_console(self, path: str | Path) -> None:
        """Save console report to text file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_console())
        logger.info("Overall action coverage console report saved to %s", path)


class ActionCoverageValidator:
    """Validates action implementation coverage for entities.

    This validator fetches available actions for each entity and compares
    them against the methods implemented in EntityManager. Provides both
    basic reports (for backward compatibility) and detailed reports with
    priority classification.

    Attributes:
        client: CiviClient for API access.
        discovery: EntityDiscovery instance for API introspection.

    Example:
        >>> async with CiviClient() as client:
        ...     validator = ActionCoverageValidator(client)
        ...     report = await validator.generate_report("Contact")
        ...     print(f"Actions: {report.available_actions}")

        >>> async with CiviClient() as client:
        ...     validator = ActionCoverageValidator(client)
        ...     detailed = await validator.generate_detailed_report("Contact")
        ...     print(f"Coverage: {detailed.coverage_percentage:.1f}%")
        ...     for action in detailed.missing_critical_actions:
        ...         print(f"  Missing critical: {action.name}")
    """

    # Methods implemented in EntityManager
    MANAGER_METHODS: ClassVar[set[str]] = {
        "get",
        "create",
        "update",
        "delete",
        "get_fields",
        "count",
        "exists",
        "get_or_create",
        "update_or_create",
        "bulk_create",
        "all",
        "filter",
        "exclude",
        "select",
        "order_by",
        "limit",
        "offset",
    }

    # Mapping from CiviCRM actions to manager methods
    ACTION_TO_METHOD_MAP: ClassVar[dict[str, set[str]]] = {
        "get": {"get", "filter", "all", "count", "exists"},
        "create": {"create", "bulk_create", "get_or_create", "update_or_create"},
        "update": {"update", "update_or_create"},
        "delete": {"delete"},
        "save": {"save", "update_or_create"},
        "getFields": {"get_fields"},
        "getActions": set(),  # Not implemented as method
        "getLinks": set(),  # Not implemented
        "checkAccess": set(),  # Not implemented
        "replace": set(),  # Not implemented
        "refresh": set(),  # Not implemented
    }

    def __init__(self, client: CiviClient) -> None:
        """Initialize action coverage validator.

        Args:
            client: CiviClient for API access.
        """
        self.client = client
        self.discovery = EntityDiscovery(client)

    async def get_entity_actions(self, entity_name: str) -> set[str]:
        """Fetch available actions for an entity from CiviCRM API.

        Args:
            entity_name: Name of the entity.

        Returns:
            Set of action names available for this entity.
        """
        try:
            response = await self.client.request(entity_name, "getActions", {})
            if response.values:
                return {action.get("name", "") for action in response.values if action.get("name")}
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch actions for %s", entity_name)
        return set()

    async def get_entity_actions_detailed(self, entity_name: str) -> list[dict[str, Any]]:
        """Fetch detailed action info for an entity from CiviCRM API.

        Args:
            entity_name: Name of the entity.

        Returns:
            List of action detail dicts from API.
        """
        try:
            response = await self.client.request(entity_name, "getActions", {})
            if response.values:
                return list(response.values)
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch actions for %s", entity_name)
        return []

    def _is_action_implemented(self, action: str) -> bool:
        """Check if an action is implemented in EntityManager.

        Args:
            action: CiviCRM action name.

        Returns:
            True if the action is covered by EntityManager methods.
        """
        methods = self.ACTION_TO_METHOD_MAP.get(action, set())
        return bool(methods & self.MANAGER_METHODS)

    def _is_standard_action(self, action: str) -> bool:
        """Check if an action is a standard CiviCRM action.

        Args:
            action: Action name.

        Returns:
            True if this is a standard action.
        """
        return action in STANDARD_ACTIONS

    async def generate_report(
        self,
        entity_name: str,
    ) -> ActionCoverageReport:
        """Generate action coverage report for a specific entity.

        This is the basic report for backward compatibility.

        Args:
            entity_name: Name of the entity to check.

        Returns:
            ActionCoverageReport with coverage details.
        """
        available = await self.get_entity_actions(entity_name)

        missing: list[MissingAction] = []
        custom: list[MissingAction] = []

        for action in available:
            is_standard = self._is_standard_action(action)
            is_implemented = self._is_action_implemented(action)

            if not is_implemented:
                action_info = MissingAction(
                    entity_name=entity_name,
                    action_name=action,
                    is_standard=is_standard,
                    is_custom=not is_standard,
                )
                if is_standard:
                    missing.append(action_info)
                else:
                    custom.append(action_info)

        return ActionCoverageReport(
            entity_name=entity_name,
            available_actions=available,
            implemented_actions=self.MANAGER_METHODS,
            missing_actions=missing,
            custom_actions=custom,
        )

    async def generate_detailed_report(
        self,
        entity_name: str,
    ) -> DetailedActionReport:
        """Generate detailed action coverage report for a specific entity.

        This enhanced report includes priority classification, custom action
        tracking, and per-action implementation status.

        Args:
            entity_name: Name of the entity to check.

        Returns:
            DetailedActionReport with comprehensive coverage details.
        """
        # Fetch actions from API
        api_actions = await self.get_entity_actions(entity_name)
        api_details = await self.get_entity_actions_detailed(entity_name)

        # Create action mapping
        mapping = ActionMapping(
            entity_name=entity_name,
            api_actions=api_actions,
        )

        return DetailedActionReport(
            entity_name=entity_name,
            api_actions=api_actions,
            action_mapping=mapping,
            api_action_details=api_details,
        )

    async def generate_all_reports(
        self,
        entity_names: list[str] | None = None,
    ) -> dict[str, ActionCoverageReport]:
        """Generate action coverage reports for multiple entities.

        Args:
            entity_names: List of entity names to check. If None, checks
                all implemented entities.

        Returns:
            Dict mapping entity names to their action reports.
        """
        if entity_names is None:
            # Use implemented entities
            entity_validator = EntityCoverageValidator(self.client)
            entity_names = list(entity_validator.get_implemented_entities())

        reports: dict[str, ActionCoverageReport] = {}
        for name in entity_names:
            try:
                reports[name] = await self.generate_report(name)
            except Exception:  # noqa: BLE001
                logger.warning("Could not generate action report for %s", name)

        return reports

    async def generate_all_detailed_reports(
        self,
        entity_names: list[str] | None = None,
    ) -> OverallActionCoverageReport:
        """Generate detailed action coverage reports for all entities.

        Args:
            entity_names: List of entity names to check. If None, checks
                all implemented entities.

        Returns:
            OverallActionCoverageReport with per-entity detailed reports.
        """
        if entity_names is None:
            # Use implemented entities
            entity_validator = EntityCoverageValidator(self.client)
            entity_names = list(entity_validator.get_implemented_entities())

        entity_reports: dict[str, DetailedActionReport] = {}
        for name in entity_names:
            try:
                entity_reports[name] = await self.generate_detailed_report(name)
            except Exception:  # noqa: BLE001
                logger.warning("Could not generate detailed action report for %s", name)

        return OverallActionCoverageReport(entity_reports=entity_reports)

    async def validate_100_percent_coverage(
        self,
        entity_name: str,
    ) -> tuple[bool, list[str]]:
        """Validate if an entity has 100% standard action coverage.

        Args:
            entity_name: Name of the entity to validate.

        Returns:
            Tuple of (has_full_coverage, list_of_missing_actions).
        """
        report = await self.generate_detailed_report(entity_name)
        missing = report.standard_actions_missing
        return len(missing) == 0, missing

    async def get_high_priority_missing(
        self,
        entity_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Get high-priority missing actions across entities.

        Args:
            entity_names: List of entity names to check.

        Returns:
            Dict mapping entity names to their high-priority missing actions.
        """
        overall = await self.generate_all_detailed_reports(entity_names)
        result: dict[str, list[str]] = {}

        for name, report in overall.entity_reports.items():
            critical = [a.name for a in report.missing_critical_actions]
            high = [a.name for a in report.missing_high_priority_actions]
            if critical or high:
                result[name] = critical + high

        return result


async def generate_coverage_reports(
    client: CiviClient,
    *,
    output_dir: str | Path | None = None,
    include_field_counts: bool = False,
    entity_names: list[str] | None = None,
) -> CoverageReport:
    """Generate comprehensive coverage reports.

    This is the main entry point for coverage validation. It generates
    both entity and action coverage reports and optionally saves them.

    Args:
        client: CiviClient for API access.
        output_dir: Directory to save reports. If None, reports are not saved.
        include_field_counts: Whether to fetch field counts (slower).
        entity_names: Specific entities to check actions for.

    Returns:
        CoverageReport with complete coverage information.

    Example:
        >>> async with CiviClient() as client:
        ...     report = await generate_coverage_reports(
        ...         client,
        ...         output_dir="./coverage_reports",
        ...     )
        ...     print(f"Entity coverage: {report.overall_entity_coverage:.1f}%")
        ...     print(f"Action coverage: {report.overall_action_coverage:.1f}%")
    """
    # Generate entity coverage report
    entity_validator = EntityCoverageValidator(client)
    entity_report = await entity_validator.generate_report(
        include_field_counts=include_field_counts,
    )

    # Generate action coverage reports
    action_validator = ActionCoverageValidator(client)
    action_reports = await action_validator.generate_all_reports(entity_names)

    # Create combined report
    report = CoverageReport(
        entity_report=entity_report,
        action_reports=action_reports,
    )

    # Save reports if output directory specified
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save complete report
        report.save_json(output_path / "coverage_report.json")

        # Save entity report
        entity_report.save_json(output_path / "entity_coverage.json")
        entity_report.save_console(output_path / "entity_coverage.txt")

        # Save individual action reports
        actions_dir = output_path / "actions"
        actions_dir.mkdir(exist_ok=True)
        for name, action_report in action_reports.items():
            action_path = actions_dir / f"{name.lower()}_actions.json"
            with action_path.open("w") as f:
                json.dump(action_report.to_dict(), f, indent=2)

        logger.info("Coverage reports saved to %s", output_path)

    return report


async def generate_detailed_coverage_report(
    client: CiviClient,
    *,
    output_dir: str | Path | None = None,
    include_field_counts: bool = False,
    entity_names: list[str] | None = None,
) -> tuple[CoverageReport, OverallActionCoverageReport]:
    """Generate comprehensive coverage reports with detailed action analysis.

    Enhanced version of generate_coverage_reports that includes per-entity
    detailed action coverage with priority classification.

    Args:
        client: CiviClient for API access.
        output_dir: Directory to save reports. If None, reports are not saved.
        include_field_counts: Whether to fetch field counts (slower).
        entity_names: Specific entities to check actions for.

    Returns:
        Tuple of (CoverageReport, OverallActionCoverageReport).

    Example:
        >>> async with CiviClient() as client:
        ...     report, detailed = await generate_detailed_coverage_report(
        ...         client,
        ...         output_dir="./coverage_reports",
        ...     )
        ...     print(f"Entity coverage: {report.overall_entity_coverage:.1f}%")
        ...     print(f"Average action coverage: {detailed.average_coverage:.1f}%")
        ...     for entity, action in detailed.all_missing_critical_actions:
        ...         print(f"  Missing: {entity}.{action.name}")
    """
    # Generate entity coverage report
    entity_validator = EntityCoverageValidator(client)
    entity_report = await entity_validator.generate_report(
        include_field_counts=include_field_counts,
    )

    # Generate action coverage reports (basic for CoverageReport)
    action_validator = ActionCoverageValidator(client)
    action_reports = await action_validator.generate_all_reports(entity_names)

    # Generate detailed action coverage reports
    detailed_report = await action_validator.generate_all_detailed_reports(entity_names)

    # Create combined basic report
    report = CoverageReport(
        entity_report=entity_report,
        action_reports=action_reports,
    )

    # Save reports if output directory specified
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save complete report
        report.save_json(output_path / "coverage_report.json")

        # Save entity report
        entity_report.save_json(output_path / "entity_coverage.json")
        entity_report.save_console(output_path / "entity_coverage.txt")

        # Save overall detailed action report
        detailed_report.save_json(output_path / "action_coverage_detailed.json")
        detailed_report.save_console(output_path / "action_coverage_detailed.txt")

        # Save individual action reports
        actions_dir = output_path / "actions"
        actions_dir.mkdir(exist_ok=True)

        # Save basic reports
        for name, action_report in action_reports.items():
            action_path = actions_dir / f"{name.lower()}_actions.json"
            with action_path.open("w") as f:
                json.dump(action_report.to_dict(), f, indent=2)

        # Save detailed reports
        detailed_dir = output_path / "actions_detailed"
        detailed_dir.mkdir(exist_ok=True)
        for name, detail_report in detailed_report.entity_reports.items():
            detail_path = detailed_dir / f"{name.lower()}_detailed.json"
            detail_report.save_json(detail_path)
            console_path = detailed_dir / f"{name.lower()}_detailed.txt"
            detail_report.save_console(console_path)

        logger.info("Detailed coverage reports saved to %s", output_path)

    return report, detailed_report


async def validate_entity_action_coverage(
    client: CiviClient,
    entity_name: str,
    *,
    require_100_percent: bool = False,
) -> dict[str, Any]:
    """Validate action coverage for a specific entity.

    Convenience function to check action coverage for a single entity.

    Args:
        client: CiviClient for API access.
        entity_name: Name of the entity to validate.
        require_100_percent: If True, returns failure status if coverage < 100%.

    Returns:
        Dict with validation results.

    Example:
        >>> async with CiviClient() as client:
        ...     result = await validate_entity_action_coverage(
        ...         client, "Contact", require_100_percent=True
        ...     )
        ...     print(f"Valid: {result['valid']}")
        ...     print(f"Coverage: {result['coverage_percentage']:.1f}%")
    """
    validator = ActionCoverageValidator(client)
    report = await validator.generate_detailed_report(entity_name)

    valid = True
    if require_100_percent and report.coverage_percentage < 100.0:
        valid = False

    return {
        "entity": entity_name,
        "valid": valid,
        "coverage_percentage": report.coverage_percentage,
        "api_coverage_percentage": report.api_coverage_percentage,
        "standard_covered": report.standard_actions_covered,
        "standard_missing": report.standard_actions_missing,
        "custom_actions": report.custom_actions_available,
        "unknown_api_actions": list(report.unknown_actions),
        "critical_missing": [a.name for a in report.missing_critical_actions],
        "high_priority_missing": [a.name for a in report.missing_high_priority_actions],
    }
