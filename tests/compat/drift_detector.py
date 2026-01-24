"""API drift detection for CiviCRM schema changes.

This module provides tools to detect when the CiviCRM API schema has changed
from stored snapshots. It enables:

- Versioned schema snapshot storage
- Schema diffing with detailed change reports
- Pytest fixtures and markers for automatic drift detection
- Changelog generation for schema updates

Usage:
    >>> differ = SchemaDiffer()
    >>> report = differ.compare_schemas(old_schema, new_schema)
    >>> if report.has_changes:
    ...     print(report.format_changelog())

Pytest integration:
    >>> @pytest.mark.detect_drift
    ... async def test_contact_schema(drift_detector):
    ...     report = await drift_detector.check_entity("Contact")
    ...     assert not report.has_breaking_changes
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient
    from tests.compat.schema_validator import SchemaCache

__all__ = [
    "ChangeType",
    "DriftDetector",
    "DriftMode",
    "DriftReport",
    "FieldChange",
    "SchemaChange",
    "SchemaDiffer",
    "SchemaSnapshot",
]

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Types of schema changes."""

    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_MODIFIED = "field_modified"
    TYPE_CHANGED = "type_changed"
    REQUIRED_CHANGED = "required_changed"
    DEFAULT_CHANGED = "default_changed"
    OPTIONS_CHANGED = "options_changed"
    DESCRIPTION_CHANGED = "description_changed"
    FK_CHANGED = "fk_entity_changed"


class DriftMode(Enum):
    """Drift detection modes."""

    STRICT = "strict"  # Fail on any change
    REPORT = "report"  # Log changes but don't fail
    BREAKING = "breaking"  # Fail only on breaking changes


@dataclass
class FieldChange:
    """Represents a change to a single field."""

    field_name: str
    change_type: ChangeType
    old_value: Any = None
    new_value: Any = None
    is_breaking: bool = False

    def __str__(self) -> str:
        """Human-readable representation."""
        return self._format_change()

    def _format_change(self) -> str:
        """Format the change as a human-readable string."""
        formatters = {
            ChangeType.FIELD_ADDED: lambda: f"  + {self.field_name}: added (type: {self.new_value})",
            ChangeType.FIELD_REMOVED: lambda: f"  - {self.field_name}: removed (was: {self.old_value})",
            ChangeType.TYPE_CHANGED: lambda: f"  ~ {self.field_name}: type changed ({self.old_value} -> {self.new_value})",
            ChangeType.REQUIRED_CHANGED: lambda: f"  ~ {self.field_name}: {'now required' if self.new_value else 'now optional'}",
            ChangeType.DEFAULT_CHANGED: lambda: f"  ~ {self.field_name}: default changed ({self.old_value!r} -> {self.new_value!r})",
            ChangeType.OPTIONS_CHANGED: lambda: f"  ~ {self.field_name}: options changed",
            ChangeType.DESCRIPTION_CHANGED: lambda: f"  ~ {self.field_name}: description updated",
            ChangeType.FK_CHANGED: lambda: f"  ~ {self.field_name}: FK entity changed ({self.old_value} -> {self.new_value})",
        }
        formatter = formatters.get(self.change_type)
        return formatter() if formatter else f"  ~ {self.field_name}: {self.change_type.value}"

    @property
    def severity(self) -> str:
        """Get severity level for this change."""
        if self.is_breaking:
            return "breaking"
        if self.change_type in (ChangeType.FIELD_REMOVED, ChangeType.TYPE_CHANGED):
            return "major"
        if self.change_type in (ChangeType.REQUIRED_CHANGED, ChangeType.FK_CHANGED):
            return "minor"
        return "patch"


@dataclass
class SchemaChange:
    """Represents changes to a single entity schema."""

    entity_name: str
    changes: list[FieldChange] = field(default_factory=list)
    old_version: str | None = None
    new_version: str | None = None
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self.changes) > 0

    @property
    def has_breaking_changes(self) -> bool:
        """Check if there are any breaking changes."""
        return any(c.is_breaking for c in self.changes)

    @property
    def added_fields(self) -> list[FieldChange]:
        """Get all added fields."""
        return [c for c in self.changes if c.change_type == ChangeType.FIELD_ADDED]

    @property
    def removed_fields(self) -> list[FieldChange]:
        """Get all removed fields."""
        return [c for c in self.changes if c.change_type == ChangeType.FIELD_REMOVED]

    @property
    def modified_fields(self) -> list[FieldChange]:
        """Get all modified fields."""
        return [c for c in self.changes if c.change_type not in (ChangeType.FIELD_ADDED, ChangeType.FIELD_REMOVED)]

    @property
    def breaking_changes(self) -> list[FieldChange]:
        """Get all breaking changes."""
        return [c for c in self.changes if c.is_breaking]

    def format_summary(self) -> str:
        """Format a brief summary of changes."""
        parts = []
        if self.added_fields:
            parts.append(f"+{len(self.added_fields)} added")
        if self.removed_fields:
            parts.append(f"-{len(self.removed_fields)} removed")
        if self.modified_fields:
            parts.append(f"~{len(self.modified_fields)} modified")

        if not parts:
            return f"{self.entity_name}: no changes"

        summary = f"{self.entity_name}: {', '.join(parts)}"
        if self.has_breaking_changes:
            summary += f" ({len(self.breaking_changes)} BREAKING)"
        return summary

    def format_changelog(self, include_minor: bool = True) -> str:
        """Format detailed changelog for this entity.

        Args:
            include_minor: Include non-breaking changes like description updates.

        Returns:
            Formatted changelog string.
        """
        if not self.has_changes:
            return f"## {self.entity_name}\n\nNo changes detected.\n"

        lines = [f"## {self.entity_name}"]

        if self.old_version and self.new_version:
            lines.append(f"Version: {self.old_version} -> {self.new_version}")
        lines.append("")

        # Group changes by type
        if self.added_fields:
            lines.append("### Added Fields")
            lines.extend(str(change) for change in self.added_fields)
            lines.append("")

        if self.removed_fields:
            lines.append("### Removed Fields")
            lines.extend(f"{change}{' [BREAKING]' if change.is_breaking else ''}" for change in self.removed_fields)
            lines.append("")

        modified = self.modified_fields
        if not include_minor:
            modified = [c for c in modified if c.change_type != ChangeType.DESCRIPTION_CHANGED]

        if modified:
            lines.append("### Modified Fields")
            lines.extend(f"{change}{' [BREAKING]' if change.is_breaking else ''}" for change in modified)
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_name": self.entity_name,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "detected_at": self.detected_at,
            "summary": {
                "total_changes": len(self.changes),
                "added": len(self.added_fields),
                "removed": len(self.removed_fields),
                "modified": len(self.modified_fields),
                "breaking": len(self.breaking_changes),
            },
            "changes": [
                {
                    "field": c.field_name,
                    "type": c.change_type.value,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "is_breaking": c.is_breaking,
                    "severity": c.severity,
                }
                for c in self.changes
            ],
        }


@dataclass
class DriftReport:
    """Aggregate report for multiple entity schema changes."""

    entity_changes: list[SchemaChange] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    mode: DriftMode = DriftMode.REPORT
    base_version: str | None = None
    target_version: str | None = None

    @property
    def has_changes(self) -> bool:
        """Check if any entity has changes."""
        return any(e.has_changes for e in self.entity_changes)

    @property
    def has_breaking_changes(self) -> bool:
        """Check if any entity has breaking changes."""
        return any(e.has_breaking_changes for e in self.entity_changes)

    @property
    def total_changes(self) -> int:
        """Total number of field changes across all entities."""
        return sum(len(e.changes) for e in self.entity_changes)

    @property
    def total_breaking(self) -> int:
        """Total number of breaking changes."""
        return sum(len(e.breaking_changes) for e in self.entity_changes)

    @property
    def entities_with_changes(self) -> list[SchemaChange]:
        """Get entities that have changes."""
        return [e for e in self.entity_changes if e.has_changes]

    @property
    def entities_with_breaking_changes(self) -> list[SchemaChange]:
        """Get entities with breaking changes."""
        return [e for e in self.entity_changes if e.has_breaking_changes]

    def add_entity_change(self, change: SchemaChange) -> None:
        """Add an entity change to the report."""
        self.entity_changes.append(change)

    def get_entity(self, entity_name: str) -> SchemaChange | None:
        """Get changes for a specific entity."""
        for change in self.entity_changes:
            if change.entity_name == entity_name:
                return change
        return None

    def should_fail(self) -> bool:
        """Determine if tests should fail based on mode.

        Returns:
            True if the drift report should cause test failure.
        """
        if self.mode == DriftMode.STRICT:
            return self.has_changes
        if self.mode == DriftMode.BREAKING:
            return self.has_breaking_changes
        # REPORT mode
        return False

    def format_summary(self) -> str:
        """Format a brief summary of all changes."""
        if not self.has_changes:
            return "No schema drift detected."

        lines = [
            "Schema Drift Detected",
            "=" * 40,
            f"Entities checked: {len(self.entity_changes)}",
            f"Entities with changes: {len(self.entities_with_changes)}",
            f"Total field changes: {self.total_changes}",
        ]

        if self.has_breaking_changes:
            lines.append(f"Breaking changes: {self.total_breaking}")

        lines.append("")
        lines.extend(entity.format_summary() for entity in self.entities_with_changes)

        return "\n".join(lines)

    def format_changelog(self, include_minor: bool = True) -> str:
        """Format complete changelog for all entities.

        Args:
            include_minor: Include minor changes like description updates.

        Returns:
            Formatted changelog string.
        """
        lines = [
            "# Schema Drift Changelog",
            f"Generated: {self.generated_at}",
        ]

        if self.base_version and self.target_version:
            lines.append(f"Version: {self.base_version} -> {self.target_version}")

        lines.append("")
        lines.append("## Summary")
        lines.append(f"- Entities with changes: {len(self.entities_with_changes)}")
        lines.append(f"- Total field changes: {self.total_changes}")
        if self.has_breaking_changes:
            lines.append(f"- Breaking changes: {self.total_breaking}")
        lines.append("")
        lines.extend(entity.format_changelog(include_minor=include_minor) for entity in self.entities_with_changes)

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "generated_at": self.generated_at,
            "mode": self.mode.value,
            "base_version": self.base_version,
            "target_version": self.target_version,
            "summary": {
                "entities_checked": len(self.entity_changes),
                "entities_with_changes": len(self.entities_with_changes),
                "total_changes": self.total_changes,
                "breaking_changes": self.total_breaking,
                "has_breaking": self.has_breaking_changes,
            },
            "entities": [e.to_dict() for e in self.entity_changes],
        }


@dataclass
class SchemaSnapshot:
    """Versioned schema snapshot for drift detection.

    Extends the basic schema storage with version tracking and
    comparison capabilities.
    """

    entity_name: str
    fields: list[dict[str, Any]]
    version: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    civicrm_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Default snapshot directory
    DEFAULT_SNAPSHOT_DIR: ClassVar[Path] = Path(__file__).parent / "schemas" / "snapshots"

    @classmethod
    def from_schema_file(cls, path: Path) -> SchemaSnapshot | None:
        """Load snapshot from a schema file.

        Args:
            path: Path to schema JSON file.

        Returns:
            SchemaSnapshot if file exists and is valid, None otherwise.
        """
        if not path.exists():
            return None

        try:
            with path.open() as f:
                data = json.load(f)

            return cls(
                entity_name=data.get("entity_name", path.stem),
                fields=data.get("fields", []),
                version=data.get("metadata", {}).get("civicrm_version", "unknown"),
                created_at=data.get("cached_at", datetime.now(UTC).isoformat()),
                civicrm_version=data.get("metadata", {}).get("civicrm_version"),
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning("Failed to load snapshot from %s: %s", path, e)
            return None

    @classmethod
    def from_api_fields(
        cls,
        entity_name: str,
        fields: list[dict[str, Any]],
        version: str = "current",
        civicrm_version: str | None = None,
    ) -> SchemaSnapshot:
        """Create snapshot from API getFields response.

        Args:
            entity_name: Entity name.
            fields: Field definitions from getFields.
            version: Version identifier for this snapshot.
            civicrm_version: CiviCRM version string.

        Returns:
            SchemaSnapshot instance.
        """
        return cls(
            entity_name=entity_name,
            fields=fields,
            version=version,
            civicrm_version=civicrm_version,
            metadata={
                "source": "api",
                "civicrm_version": civicrm_version,
            },
        )

    def save(self, directory: Path | None = None, version_suffix: bool = True) -> Path:
        """Save snapshot to file.

        Args:
            directory: Directory to save to. Uses DEFAULT_SNAPSHOT_DIR if None.
            version_suffix: Include version in filename.

        Returns:
            Path to saved file.
        """
        save_dir = directory or self.DEFAULT_SNAPSHOT_DIR
        save_dir.mkdir(parents=True, exist_ok=True)

        if version_suffix and self.version != "current":
            filename = f"{self.entity_name}_{self.version}.json"
        else:
            filename = f"{self.entity_name}.json"

        path = save_dir / filename

        # Build metadata, ensuring version is always set
        save_metadata = dict(self.metadata)
        save_metadata["civicrm_version"] = self.civicrm_version or self.version
        save_metadata.setdefault("source", "snapshot")

        data = {
            "entity_name": self.entity_name,
            "fields": self.fields,
            "cached_at": self.created_at,
            "metadata": save_metadata,
        }

        with path.open("w") as f:
            json.dump(data, f, indent=2, default=str)

        return path

    def get_field(self, field_name: str) -> dict[str, Any] | None:
        """Get a field by name.

        Args:
            field_name: Name of the field.

        Returns:
            Field definition dict or None.
        """
        for field_def in self.fields:
            if field_def.get("name") == field_name:
                return field_def
        return None

    def get_field_names(self) -> set[str]:
        """Get set of all field names."""
        return {f["name"] for f in self.fields if "name" in f}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_name": self.entity_name,
            "fields": self.fields,
            "version": self.version,
            "created_at": self.created_at,
            "civicrm_version": self.civicrm_version,
            "metadata": self.metadata,
        }


class SchemaDiffer:
    """Compares schemas and generates detailed diff reports.

    The differ identifies changes between two schema snapshots and
    categorizes them as added, removed, or modified fields. It also
    determines which changes are breaking (backwards-incompatible).
    """

    # Field attributes to compare for modifications
    COMPARABLE_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "data_type",
        "required",
        "default_value",
        "fk_entity",
        "options",
        "readonly",
        "serialize",
    )

    # Changes that are considered breaking
    BREAKING_CHANGES: ClassVar[frozenset[ChangeType]] = frozenset(
        {
            ChangeType.FIELD_REMOVED,  # Existing code may reference it
            ChangeType.TYPE_CHANGED,  # Type coercion may fail
        },
    )

    def __init__(self, *, detect_description_changes: bool = False) -> None:
        """Initialize the schema differ.

        Args:
            detect_description_changes: Include description changes in diff.
        """
        self.detect_description_changes = detect_description_changes

    def compare_fields(
        self,
        old_field: dict[str, Any],
        new_field: dict[str, Any],
    ) -> list[FieldChange]:
        """Compare two field definitions.

        Args:
            old_field: Previous field definition.
            new_field: Current field definition.

        Returns:
            List of changes detected.
        """
        changes: list[FieldChange] = []
        field_name = old_field.get("name", new_field.get("name", "unknown"))

        # Check each comparable attribute
        for attr in self.COMPARABLE_ATTRIBUTES:
            old_val = old_field.get(attr)
            new_val = new_field.get(attr)

            if old_val != new_val:
                change_type = self._get_change_type(attr)
                is_breaking = self._is_breaking_field_change(attr, old_val, new_val)

                changes.append(
                    FieldChange(
                        field_name=field_name,
                        change_type=change_type,
                        old_value=old_val,
                        new_value=new_val,
                        is_breaking=is_breaking,
                    ),
                )

        # Check description if enabled
        if self.detect_description_changes:
            old_desc = old_field.get("description", "")
            new_desc = new_field.get("description", "")
            if old_desc != new_desc:
                changes.append(
                    FieldChange(
                        field_name=field_name,
                        change_type=ChangeType.DESCRIPTION_CHANGED,
                        old_value=old_desc,
                        new_value=new_desc,
                        is_breaking=False,
                    ),
                )

        return changes

    def compare_schemas(
        self,
        old_snapshot: SchemaSnapshot,
        new_snapshot: SchemaSnapshot,
    ) -> SchemaChange:
        """Compare two schema snapshots.

        Args:
            old_snapshot: Previous schema snapshot.
            new_snapshot: Current schema snapshot.

        Returns:
            SchemaChange with all detected differences.
        """
        if old_snapshot.entity_name != new_snapshot.entity_name:
            logger.warning(
                "Comparing different entities: %s vs %s",
                old_snapshot.entity_name,
                new_snapshot.entity_name,
            )

        changes: list[FieldChange] = []

        old_fields = {f["name"]: f for f in old_snapshot.fields if "name" in f}
        new_fields = {f["name"]: f for f in new_snapshot.fields if "name" in f}

        old_names = set(old_fields.keys())
        new_names = set(new_fields.keys())

        # Detect added fields
        for name in new_names - old_names:
            field = new_fields[name]
            changes.append(
                FieldChange(
                    field_name=name,
                    change_type=ChangeType.FIELD_ADDED,
                    new_value=field.get("data_type", "unknown"),
                    is_breaking=False,  # Added fields are not breaking
                ),
            )

        # Detect removed fields
        for name in old_names - new_names:
            field = old_fields[name]
            changes.append(
                FieldChange(
                    field_name=name,
                    change_type=ChangeType.FIELD_REMOVED,
                    old_value=field.get("data_type", "unknown"),
                    is_breaking=True,  # Removed fields are breaking
                ),
            )

        # Detect modified fields
        for name in old_names & new_names:
            field_changes = self.compare_fields(old_fields[name], new_fields[name])
            changes.extend(field_changes)

        return SchemaChange(
            entity_name=new_snapshot.entity_name,
            changes=changes,
            old_version=old_snapshot.version,
            new_version=new_snapshot.version,
        )

    def _get_change_type(self, attribute: str) -> ChangeType:
        """Map attribute name to change type."""
        mapping = {
            "data_type": ChangeType.TYPE_CHANGED,
            "required": ChangeType.REQUIRED_CHANGED,
            "default_value": ChangeType.DEFAULT_CHANGED,
            "fk_entity": ChangeType.FK_CHANGED,
            "options": ChangeType.OPTIONS_CHANGED,
        }
        return mapping.get(attribute, ChangeType.FIELD_MODIFIED)

    def _is_breaking_field_change(
        self,
        attribute: str,
        old_value: Any,
        new_value: Any,
    ) -> bool:
        """Determine if a field change is breaking.

        Args:
            attribute: Name of the changed attribute.
            old_value: Previous value.
            new_value: New value.

        Returns:
            True if the change is breaking.
        """
        # Type changes are usually breaking
        if attribute == "data_type":
            return True

        # Required becoming True is breaking (existing data may not have it)
        if attribute == "required" and new_value is True and old_value is False:
            return True

        # FK entity changes could break joins
        return attribute == "fk_entity" and old_value is not None


class DriftDetector:
    """High-level drift detection for CiviCRM schemas.

    Coordinates schema loading, comparison, and reporting. Designed
    for use in pytest fixtures and CI workflows.
    """

    def __init__(
        self,
        cache: SchemaCache,
        *,
        mode: DriftMode = DriftMode.REPORT,
        snapshot_dir: Path | None = None,
    ) -> None:
        """Initialize drift detector.

        Args:
            cache: Schema cache for loading stored schemas.
            mode: Drift detection mode.
            snapshot_dir: Directory for version snapshots.
        """
        self.cache = cache
        self.mode = mode
        self.snapshot_dir = snapshot_dir or SchemaSnapshot.DEFAULT_SNAPSHOT_DIR
        self.differ = SchemaDiffer()

    def get_stored_snapshot(self, entity_name: str) -> SchemaSnapshot | None:
        """Get stored schema snapshot for an entity.

        Args:
            entity_name: Entity name.

        Returns:
            SchemaSnapshot if found, None otherwise.
        """
        # Try versioned snapshot first
        snapshot_path = self.snapshot_dir / f"{entity_name}.json"
        if snapshot_path.exists():
            return SchemaSnapshot.from_schema_file(snapshot_path)

        # Fall back to main cache
        schema_path = self.cache.get_schema_path(entity_name)
        if schema_path.exists():
            return SchemaSnapshot.from_schema_file(schema_path)

        return None

    def check_entity(
        self,
        entity_name: str,
        current_fields: list[dict[str, Any]],
        current_version: str = "current",
    ) -> SchemaChange:
        """Check an entity for schema drift.

        Args:
            entity_name: Entity name.
            current_fields: Current field definitions from API.
            current_version: Version identifier for current schema.

        Returns:
            SchemaChange with any detected drift.
        """
        stored = self.get_stored_snapshot(entity_name)

        if stored is None:
            # No stored snapshot - this is a new entity
            logger.info("No stored snapshot for %s, treating as new entity", entity_name)
            return SchemaChange(
                entity_name=entity_name,
                changes=[
                    FieldChange(
                        field_name=f["name"],
                        change_type=ChangeType.FIELD_ADDED,
                        new_value=f.get("data_type", "unknown"),
                        is_breaking=False,
                    )
                    for f in current_fields
                    if "name" in f
                ],
                new_version=current_version,
            )

        current = SchemaSnapshot.from_api_fields(
            entity_name=entity_name,
            fields=current_fields,
            version=current_version,
        )

        return self.differ.compare_schemas(stored, current)

    async def check_entity_from_api(
        self,
        client: CiviClient,
        entity_name: str,
    ) -> SchemaChange:
        """Check entity drift by fetching current schema from API.

        Args:
            client: Active CiviClient.
            entity_name: Entity name to check.

        Returns:
            SchemaChange with detected drift.
        """
        response = await client.get_fields(entity_name)
        current_fields = response.values or []

        return self.check_entity(entity_name, current_fields)

    def check_all_cached(self) -> DriftReport:
        """Check all cached entities for drift.

        This compares stored snapshots against the main cache.

        Returns:
            DriftReport for all cached entities.
        """
        report = DriftReport(mode=self.mode)

        cached_entities = self.cache.list_cached_entities()

        for entity_name in cached_entities:
            # Load from main cache as "current"
            fields = self.cache.load_schema(entity_name)
            if fields is None:
                continue

            change = self.check_entity(entity_name, fields)
            report.add_entity_change(change)

        return report

    async def check_all_from_api(
        self,
        client: CiviClient,
        entity_names: list[str] | None = None,
    ) -> DriftReport:
        """Check entities for drift by fetching from API.

        Args:
            client: Active CiviClient.
            entity_names: Entities to check. If None, uses cached entities.

        Returns:
            DriftReport for all checked entities.
        """
        report = DriftReport(mode=self.mode)

        if entity_names is None:
            entity_names = self.cache.list_cached_entities()

        for entity_name in entity_names:
            try:
                change = await self.check_entity_from_api(client, entity_name)
                report.add_entity_change(change)
            except Exception as e:
                logger.warning("Failed to check %s: %s", entity_name, e)

        return report

    def update_snapshots(
        self,
        entities: dict[str, list[dict[str, Any]]],
        version: str,
    ) -> dict[str, Path]:
        """Update stored snapshots with new schemas.

        Args:
            entities: Dict mapping entity names to field lists.
            version: Version identifier for new snapshots.

        Returns:
            Dict mapping entity names to saved file paths.
        """
        paths: dict[str, Path] = {}

        for entity_name, fields in entities.items():
            snapshot = SchemaSnapshot.from_api_fields(
                entity_name=entity_name,
                fields=fields,
                version=version,
            )
            path = snapshot.save(self.snapshot_dir, version_suffix=False)
            paths[entity_name] = path
            logger.info("Updated snapshot for %s at %s", entity_name, path)

        return paths

    def generate_changelog(
        self,
        report: DriftReport,
        output_path: Path | None = None,
    ) -> str:
        """Generate changelog from drift report.

        Args:
            report: DriftReport to generate changelog from.
            output_path: Optional path to save changelog.

        Returns:
            Changelog content string.
        """
        content = report.format_changelog()

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w") as f:
                f.write(content)
            logger.info("Saved changelog to %s", output_path)

        return content
