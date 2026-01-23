"""Tests for the API drift detection module.

This module contains comprehensive tests for:
- SchemaSnapshot class (versioned schema storage)
- SchemaDiffer class (schema comparison)
- FieldChange and SchemaChange (change representations)
- DriftReport (aggregate reporting)
- DriftDetector (high-level detection)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.compat.drift_detector import (
    ChangeType,
    DriftDetector,
    DriftMode,
    DriftReport,
    FieldChange,
    SchemaChange,
    SchemaDiffer,
    SchemaSnapshot,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_old_fields() -> list[dict[str, Any]]:
    """Sample field definitions representing old schema."""
    return [
        {
            "name": "id",
            "data_type": "Integer",
            "required": False,
            "readonly": True,
            "default_value": None,
        },
        {
            "name": "display_name",
            "data_type": "String",
            "required": False,
            "readonly": True,
            "default_value": None,
        },
        {
            "name": "first_name",
            "data_type": "String",
            "required": False,
            "readonly": False,
            "default_value": None,
        },
        {
            "name": "is_deleted",
            "data_type": "Boolean",
            "required": False,
            "readonly": False,
            "default_value": "0",
        },
        {
            "name": "old_field",
            "data_type": "String",
            "required": False,
            "readonly": False,
            "default_value": None,
            "description": "This field will be removed",
        },
    ]


@pytest.fixture
def sample_new_fields() -> list[dict[str, Any]]:
    """Sample field definitions representing new schema with changes."""
    return [
        {
            "name": "id",
            "data_type": "Integer",
            "required": False,
            "readonly": True,
            "default_value": None,
        },
        {
            "name": "display_name",
            "data_type": "String",
            "required": False,
            "readonly": True,
            "default_value": None,
        },
        {
            "name": "first_name",
            "data_type": "String",
            "required": True,  # Changed: now required
            "readonly": False,
            "default_value": None,
        },
        {
            "name": "is_deleted",
            "data_type": "Boolean",
            "required": False,
            "readonly": False,
            "default_value": "false",  # Changed: default value
        },
        # old_field removed
        {
            "name": "new_field",  # Added
            "data_type": "Text",
            "required": False,
            "readonly": False,
            "default_value": None,
        },
    ]


@pytest.fixture
def old_snapshot(sample_old_fields: list[dict[str, Any]]) -> SchemaSnapshot:
    """Create old schema snapshot."""
    return SchemaSnapshot(
        entity_name="Contact",
        fields=sample_old_fields,
        version="5.73",
        civicrm_version="5.73",
    )


@pytest.fixture
def new_snapshot(sample_new_fields: list[dict[str, Any]]) -> SchemaSnapshot:
    """Create new schema snapshot."""
    return SchemaSnapshot(
        entity_name="Contact",
        fields=sample_new_fields,
        version="5.74",
        civicrm_version="5.74",
    )


@pytest.fixture
def schema_differ() -> SchemaDiffer:
    """Create SchemaDiffer instance."""
    return SchemaDiffer()


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    """Create temporary snapshot directory."""
    snapshot_path = tmp_path / "snapshots"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    return snapshot_path


# =============================================================================
# FieldChange Tests
# =============================================================================


class TestFieldChange:
    """Tests for FieldChange dataclass."""

    def test_create_added_field_change(self) -> None:
        """Test creating a field added change."""
        change = FieldChange(
            field_name="new_field",
            change_type=ChangeType.FIELD_ADDED,
            new_value="String",
            is_breaking=False,
        )

        assert change.field_name == "new_field"
        assert change.change_type == ChangeType.FIELD_ADDED
        assert change.is_breaking is False
        assert change.severity == "patch"
        assert "+" in str(change)
        assert "new_field" in str(change)

    def test_create_removed_field_change(self) -> None:
        """Test creating a field removed change."""
        change = FieldChange(
            field_name="old_field",
            change_type=ChangeType.FIELD_REMOVED,
            old_value="String",
            is_breaking=True,
        )

        assert change.is_breaking is True
        assert change.severity == "breaking"
        assert "-" in str(change)
        assert "old_field" in str(change)

    def test_create_type_change(self) -> None:
        """Test creating a type changed change."""
        change = FieldChange(
            field_name="converted_field",
            change_type=ChangeType.TYPE_CHANGED,
            old_value="String",
            new_value="Integer",
            is_breaking=True,
        )

        assert change.change_type == ChangeType.TYPE_CHANGED
        assert "~" in str(change)
        assert "String" in str(change)
        assert "Integer" in str(change)

    def test_create_required_change(self) -> None:
        """Test creating a required status change."""
        change = FieldChange(
            field_name="required_field",
            change_type=ChangeType.REQUIRED_CHANGED,
            old_value=False,
            new_value=True,
            is_breaking=True,
        )

        assert "now required" in str(change)
        assert change.severity == "breaking"

    def test_create_default_change(self) -> None:
        """Test creating a default value change."""
        change = FieldChange(
            field_name="default_field",
            change_type=ChangeType.DEFAULT_CHANGED,
            old_value="0",
            new_value="false",
            is_breaking=False,
        )

        assert "default changed" in str(change)
        assert "'0'" in str(change)
        assert "'false'" in str(change)

    def test_severity_levels(self) -> None:
        """Test severity level determination."""
        # Breaking changes
        breaking = FieldChange(
            field_name="f",
            change_type=ChangeType.FIELD_REMOVED,
            is_breaking=True,
        )
        assert breaking.severity == "breaking"

        # Major (type changed, not marked breaking)
        major = FieldChange(
            field_name="f",
            change_type=ChangeType.TYPE_CHANGED,
            is_breaking=False,
        )
        assert major.severity == "major"

        # Minor
        minor = FieldChange(
            field_name="f",
            change_type=ChangeType.REQUIRED_CHANGED,
            is_breaking=False,
        )
        assert minor.severity == "minor"

        # Patch
        patch = FieldChange(
            field_name="f",
            change_type=ChangeType.FIELD_ADDED,
            is_breaking=False,
        )
        assert patch.severity == "patch"


# =============================================================================
# SchemaChange Tests
# =============================================================================


class TestSchemaChange:
    """Tests for SchemaChange dataclass."""

    def test_empty_schema_change(self) -> None:
        """Test schema change with no changes."""
        change = SchemaChange(entity_name="Contact")

        assert change.entity_name == "Contact"
        assert change.has_changes is False
        assert change.has_breaking_changes is False
        assert len(change.changes) == 0
        assert len(change.added_fields) == 0
        assert len(change.removed_fields) == 0
        assert len(change.modified_fields) == 0

    def test_schema_change_with_additions(self) -> None:
        """Test schema change with added fields."""
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="field1",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="String",
                ),
                FieldChange(
                    field_name="field2",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="Integer",
                ),
            ],
        )

        assert change.has_changes is True
        assert change.has_breaking_changes is False
        assert len(change.added_fields) == 2
        assert len(change.removed_fields) == 0

    def test_schema_change_with_breaking(self) -> None:
        """Test schema change with breaking changes."""
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="removed",
                    change_type=ChangeType.FIELD_REMOVED,
                    old_value="String",
                    is_breaking=True,
                ),
                FieldChange(
                    field_name="typed",
                    change_type=ChangeType.TYPE_CHANGED,
                    old_value="String",
                    new_value="Integer",
                    is_breaking=True,
                ),
            ],
        )

        assert change.has_breaking_changes is True
        assert len(change.breaking_changes) == 2

    def test_format_summary(self) -> None:
        """Test summary formatting."""
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="new",
                    change_type=ChangeType.FIELD_ADDED,
                ),
                FieldChange(
                    field_name="old",
                    change_type=ChangeType.FIELD_REMOVED,
                    is_breaking=True,
                ),
                FieldChange(
                    field_name="mod",
                    change_type=ChangeType.DEFAULT_CHANGED,
                ),
            ],
        )

        summary = change.format_summary()

        assert "Contact" in summary
        assert "+1 added" in summary
        assert "-1 removed" in summary
        assert "~1 modified" in summary
        assert "BREAKING" in summary

    def test_format_changelog(self) -> None:
        """Test changelog formatting."""
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="new_field",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="String",
                ),
                FieldChange(
                    field_name="old_field",
                    change_type=ChangeType.FIELD_REMOVED,
                    old_value="Integer",
                    is_breaking=True,
                ),
            ],
            old_version="5.73",
            new_version="5.74",
        )

        changelog = change.format_changelog()

        assert "## Contact" in changelog
        assert "5.73 -> 5.74" in changelog
        assert "### Added Fields" in changelog
        assert "### Removed Fields" in changelog
        assert "new_field" in changelog
        assert "old_field" in changelog
        assert "[BREAKING]" in changelog

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="test",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="String",
                ),
            ],
            old_version="5.73",
            new_version="5.74",
        )

        data = change.to_dict()

        assert data["entity_name"] == "Contact"
        assert data["old_version"] == "5.73"
        assert data["new_version"] == "5.74"
        assert data["summary"]["total_changes"] == 1
        assert data["summary"]["added"] == 1
        assert len(data["changes"]) == 1
        assert data["changes"][0]["field"] == "test"


# =============================================================================
# DriftReport Tests
# =============================================================================


class TestDriftReport:
    """Tests for DriftReport dataclass."""

    def test_empty_report(self) -> None:
        """Test empty drift report."""
        report = DriftReport()

        assert report.has_changes is False
        assert report.has_breaking_changes is False
        assert report.total_changes == 0
        assert report.total_breaking == 0
        assert len(report.entities_with_changes) == 0

    def test_report_with_changes(self) -> None:
        """Test report with entity changes."""
        report = DriftReport()

        change1 = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="f1",
                    change_type=ChangeType.FIELD_ADDED,
                ),
            ],
        )
        change2 = SchemaChange(
            entity_name="Activity",
            changes=[
                FieldChange(
                    field_name="f2",
                    change_type=ChangeType.FIELD_REMOVED,
                    is_breaking=True,
                ),
            ],
        )

        report.add_entity_change(change1)
        report.add_entity_change(change2)

        assert report.has_changes is True
        assert report.has_breaking_changes is True
        assert report.total_changes == 2
        assert report.total_breaking == 1
        assert len(report.entities_with_changes) == 2
        assert len(report.entities_with_breaking_changes) == 1

    def test_get_entity(self) -> None:
        """Test getting specific entity changes."""
        report = DriftReport()
        change = SchemaChange(entity_name="Contact")
        report.add_entity_change(change)

        found = report.get_entity("Contact")
        assert found is not None
        assert found.entity_name == "Contact"

        not_found = report.get_entity("NonExistent")
        assert not_found is None

    @pytest.mark.parametrize(
        ("mode", "has_changes", "has_breaking", "should_fail"),
        [
            (DriftMode.STRICT, True, False, True),
            (DriftMode.STRICT, False, False, False),
            (DriftMode.BREAKING, True, False, False),
            (DriftMode.BREAKING, True, True, True),
            (DriftMode.REPORT, True, True, False),
        ],
    )
    def test_should_fail(
        self,
        mode: DriftMode,
        has_changes: bool,
        has_breaking: bool,
        should_fail: bool,
    ) -> None:
        """Test failure determination based on mode."""
        report = DriftReport(mode=mode)

        if has_changes:
            change = SchemaChange(
                entity_name="Test",
                changes=[
                    FieldChange(
                        field_name="f",
                        change_type=(ChangeType.FIELD_REMOVED if has_breaking else ChangeType.FIELD_ADDED),
                        is_breaking=has_breaking,
                    ),
                ],
            )
            report.add_entity_change(change)

        assert report.should_fail() is should_fail

    def test_format_summary(self) -> None:
        """Test summary formatting."""
        report = DriftReport()
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="f1",
                    change_type=ChangeType.FIELD_ADDED,
                ),
                FieldChange(
                    field_name="f2",
                    change_type=ChangeType.FIELD_REMOVED,
                    is_breaking=True,
                ),
            ],
        )
        report.add_entity_change(change)

        summary = report.format_summary()

        assert "Schema Drift Detected" in summary
        assert "Entities checked: 1" in summary
        assert "Total field changes: 2" in summary
        assert "Breaking changes: 1" in summary
        assert "Contact" in summary

    def test_format_changelog(self) -> None:
        """Test complete changelog formatting."""
        report = DriftReport(base_version="5.73", target_version="5.74")
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="new_field",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="String",
                ),
            ],
        )
        report.add_entity_change(change)

        changelog = report.format_changelog()

        assert "# Schema Drift Changelog" in changelog
        assert "5.73 -> 5.74" in changelog
        assert "## Summary" in changelog
        assert "## Contact" in changelog

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        report = DriftReport(mode=DriftMode.STRICT)
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="f",
                    change_type=ChangeType.FIELD_ADDED,
                ),
            ],
        )
        report.add_entity_change(change)

        data = report.to_dict()

        assert data["mode"] == "strict"
        assert data["summary"]["entities_checked"] == 1
        assert data["summary"]["total_changes"] == 1
        assert len(data["entities"]) == 1


# =============================================================================
# SchemaSnapshot Tests
# =============================================================================


class TestSchemaSnapshot:
    """Tests for SchemaSnapshot class."""

    def test_create_snapshot(self, sample_old_fields: list[dict[str, Any]]) -> None:
        """Test creating a snapshot."""
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.74",
            civicrm_version="5.74",
        )

        assert snapshot.entity_name == "Contact"
        assert len(snapshot.fields) == len(sample_old_fields)
        assert snapshot.version == "5.74"

    def test_from_api_fields(self, sample_old_fields: list[dict[str, Any]]) -> None:
        """Test creating snapshot from API response."""
        snapshot = SchemaSnapshot.from_api_fields(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.74",
            civicrm_version="5.74",
        )

        assert snapshot.entity_name == "Contact"
        assert snapshot.metadata["source"] == "api"

    def test_from_schema_file(
        self,
        snapshot_dir: Path,
        sample_old_fields: list[dict[str, Any]],
    ) -> None:
        """Test loading snapshot from file."""
        # Create a schema file
        schema_path = snapshot_dir / "Contact.json"
        schema_data = {
            "entity_name": "Contact",
            "fields": sample_old_fields,
            "cached_at": "2025-01-22T00:00:00",
            "metadata": {
                "civicrm_version": "5.74",
                "source": "test",
            },
        }
        with schema_path.open("w") as f:
            json.dump(schema_data, f)

        snapshot = SchemaSnapshot.from_schema_file(schema_path)

        assert snapshot is not None
        assert snapshot.entity_name == "Contact"
        assert len(snapshot.fields) == len(sample_old_fields)
        assert snapshot.version == "5.74"

    def test_from_schema_file_not_found(self, snapshot_dir: Path) -> None:
        """Test loading from non-existent file."""
        snapshot = SchemaSnapshot.from_schema_file(snapshot_dir / "NonExistent.json")
        assert snapshot is None

    def test_save_snapshot(
        self,
        snapshot_dir: Path,
        sample_old_fields: list[dict[str, Any]],
    ) -> None:
        """Test saving snapshot to file."""
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.74",
        )

        path = snapshot.save(snapshot_dir, version_suffix=False)

        assert path.exists()
        assert path.name == "Contact.json"

        # Verify content
        with path.open() as f:
            data = json.load(f)

        assert data["entity_name"] == "Contact"
        assert len(data["fields"]) == len(sample_old_fields)

    def test_save_with_version_suffix(
        self,
        snapshot_dir: Path,
        sample_old_fields: list[dict[str, Any]],
    ) -> None:
        """Test saving with version in filename."""
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.74",
        )

        path = snapshot.save(snapshot_dir, version_suffix=True)

        assert path.name == "Contact_5.74.json"

    def test_get_field(self, old_snapshot: SchemaSnapshot) -> None:
        """Test getting field by name."""
        field = old_snapshot.get_field("id")
        assert field is not None
        assert field["name"] == "id"
        assert field["data_type"] == "Integer"

        missing = old_snapshot.get_field("nonexistent")
        assert missing is None

    def test_get_field_names(self, old_snapshot: SchemaSnapshot) -> None:
        """Test getting all field names."""
        names = old_snapshot.get_field_names()

        assert "id" in names
        assert "display_name" in names
        assert "first_name" in names

    def test_to_dict(self, old_snapshot: SchemaSnapshot) -> None:
        """Test serialization to dictionary."""
        data = old_snapshot.to_dict()

        assert data["entity_name"] == "Contact"
        assert data["version"] == "5.73"
        assert "fields" in data
        assert "created_at" in data


# =============================================================================
# SchemaDiffer Tests
# =============================================================================


class TestSchemaDiffer:
    """Tests for SchemaDiffer class."""

    def test_compare_identical_schemas(
        self,
        schema_differ: SchemaDiffer,
        old_snapshot: SchemaSnapshot,
    ) -> None:
        """Test comparing identical schemas."""
        result = schema_differ.compare_schemas(old_snapshot, old_snapshot)

        assert result.entity_name == "Contact"
        assert result.has_changes is False
        assert len(result.changes) == 0

    def test_detect_added_field(
        self,
        schema_differ: SchemaDiffer,
        old_snapshot: SchemaSnapshot,
        new_snapshot: SchemaSnapshot,
    ) -> None:
        """Test detecting added fields."""
        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        added = [c for c in result.changes if c.change_type == ChangeType.FIELD_ADDED]
        assert len(added) == 1
        assert added[0].field_name == "new_field"
        assert added[0].is_breaking is False

    def test_detect_removed_field(
        self,
        schema_differ: SchemaDiffer,
        old_snapshot: SchemaSnapshot,
        new_snapshot: SchemaSnapshot,
    ) -> None:
        """Test detecting removed fields."""
        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        removed = [c for c in result.changes if c.change_type == ChangeType.FIELD_REMOVED]
        assert len(removed) == 1
        assert removed[0].field_name == "old_field"
        assert removed[0].is_breaking is True

    def test_detect_required_change(
        self,
        schema_differ: SchemaDiffer,
        old_snapshot: SchemaSnapshot,
        new_snapshot: SchemaSnapshot,
    ) -> None:
        """Test detecting required status changes."""
        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        required = [c for c in result.changes if c.change_type == ChangeType.REQUIRED_CHANGED]
        assert len(required) == 1
        assert required[0].field_name == "first_name"
        assert required[0].is_breaking is True  # Required becoming True is breaking

    def test_detect_default_change(
        self,
        schema_differ: SchemaDiffer,
        old_snapshot: SchemaSnapshot,
        new_snapshot: SchemaSnapshot,
    ) -> None:
        """Test detecting default value changes."""
        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        defaults = [c for c in result.changes if c.change_type == ChangeType.DEFAULT_CHANGED]
        assert len(defaults) == 1
        assert defaults[0].field_name == "is_deleted"
        assert defaults[0].old_value == "0"
        assert defaults[0].new_value == "false"

    def test_detect_type_change(self, schema_differ: SchemaDiffer) -> None:
        """Test detecting type changes."""
        old_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "field1", "data_type": "String"}],
            version="1.0",
        )
        new_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "field1", "data_type": "Integer"}],
            version="2.0",
        )

        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        type_changes = [c for c in result.changes if c.change_type == ChangeType.TYPE_CHANGED]
        assert len(type_changes) == 1
        assert type_changes[0].is_breaking is True

    def test_detect_description_change(self) -> None:
        """Test detecting description changes when enabled."""
        differ = SchemaDiffer(detect_description_changes=True)

        old_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "field1", "data_type": "String", "description": "Old desc"}],
            version="1.0",
        )
        new_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "field1", "data_type": "String", "description": "New desc"}],
            version="2.0",
        )

        result = differ.compare_schemas(old_snapshot, new_snapshot)

        desc_changes = [c for c in result.changes if c.change_type == ChangeType.DESCRIPTION_CHANGED]
        assert len(desc_changes) == 1
        assert desc_changes[0].is_breaking is False

    def test_compare_fields_no_changes(self, schema_differ: SchemaDiffer) -> None:
        """Test comparing identical fields."""
        field = {"name": "test", "data_type": "String", "required": False}
        changes = schema_differ.compare_fields(field, field)
        assert len(changes) == 0

    def test_detect_fk_change(self, schema_differ: SchemaDiffer) -> None:
        """Test detecting FK entity changes."""
        old_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "ref_id", "data_type": "Integer", "fk_entity": "Contact"}],
            version="1.0",
        )
        new_snapshot = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "ref_id", "data_type": "Integer", "fk_entity": "Activity"}],
            version="2.0",
        )

        result = schema_differ.compare_schemas(old_snapshot, new_snapshot)

        fk_changes = [c for c in result.changes if c.change_type == ChangeType.FK_CHANGED]
        assert len(fk_changes) == 1
        assert fk_changes[0].is_breaking is True


# =============================================================================
# DriftDetector Tests
# =============================================================================


class TestDriftDetector:
    """Tests for DriftDetector class."""

    @pytest.fixture
    def detector(
        self,
        schema_cache: Any,
        snapshot_dir: Path,
    ) -> DriftDetector:
        """Create DriftDetector instance."""
        return DriftDetector(
            cache=schema_cache,
            mode=DriftMode.REPORT,
            snapshot_dir=snapshot_dir,
        )

    def test_get_stored_snapshot_from_snapshots(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
    ) -> None:
        """Test loading snapshot from snapshot directory."""
        # Save to snapshot dir
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.74",
        )
        snapshot.save(detector.snapshot_dir, version_suffix=False)

        loaded = detector.get_stored_snapshot("Contact")

        assert loaded is not None
        assert loaded.entity_name == "Contact"

    def test_get_stored_snapshot_from_cache(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
    ) -> None:
        """Test fallback to schema cache."""
        # Save to cache instead of snapshot dir
        detector.cache.save_schema("Contact", sample_old_fields)

        loaded = detector.get_stored_snapshot("Contact")

        assert loaded is not None
        assert loaded.entity_name == "Contact"

    def test_get_stored_snapshot_not_found(self, detector: DriftDetector) -> None:
        """Test when no snapshot exists."""
        loaded = detector.get_stored_snapshot("NonExistent")
        assert loaded is None

    def test_check_entity_new(
        self,
        detector: DriftDetector,
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test checking a new entity with no stored snapshot."""
        result = detector.check_entity("NewEntity", sample_new_fields)

        # All fields should be marked as added
        assert result.entity_name == "NewEntity"
        assert all(c.change_type == ChangeType.FIELD_ADDED for c in result.changes)
        assert len(result.changes) == len(sample_new_fields)

    def test_check_entity_with_changes(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test checking entity with stored snapshot."""
        # Store old schema
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        snapshot.save(detector.snapshot_dir, version_suffix=False)

        # Check with new fields
        result = detector.check_entity("Contact", sample_new_fields)

        assert result.has_changes is True
        assert len(result.added_fields) >= 1
        assert len(result.removed_fields) >= 1

    @pytest.mark.asyncio
    async def test_check_entity_from_api(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test checking entity by fetching from API."""
        # Store old schema
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        snapshot.save(detector.snapshot_dir, version_suffix=False)

        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = sample_new_fields
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        result = await detector.check_entity_from_api(mock_client, "Contact")

        assert result.entity_name == "Contact"
        assert result.has_changes is True
        mock_client.get_fields.assert_called_once_with("Contact")

    def test_check_all_cached(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test checking all cached entities."""
        # Store old snapshots
        old_contact = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        old_contact.save(detector.snapshot_dir, version_suffix=False)

        old_activity = SchemaSnapshot(
            entity_name="Activity",
            fields=[{"name": "id", "data_type": "Integer"}],
            version="5.73",
        )
        old_activity.save(detector.snapshot_dir, version_suffix=False)

        # Save new schemas to main cache
        detector.cache.save_schema("Contact", sample_new_fields)
        detector.cache.save_schema(
            "Activity",
            [
                {"name": "id", "data_type": "Integer"},
                {"name": "new_field", "data_type": "String"},
            ],
        )

        report = detector.check_all_cached()

        assert len(report.entity_changes) == 2
        assert report.has_changes is True

    @pytest.mark.asyncio
    async def test_check_all_from_api(
        self,
        detector: DriftDetector,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test checking all entities from API."""
        # Store old snapshots
        snapshot = SchemaSnapshot(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        snapshot.save(detector.snapshot_dir, version_suffix=False)

        # Add Contact to cache so it's included in check
        detector.cache.save_schema("Contact", sample_old_fields)

        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = sample_new_fields
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        report = await detector.check_all_from_api(mock_client)

        assert len(report.entity_changes) >= 1

    def test_update_snapshots(
        self,
        detector: DriftDetector,
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test updating snapshots."""
        entities = {
            "Contact": sample_new_fields,
            "Activity": [{"name": "id", "data_type": "Integer"}],
        }

        paths = detector.update_snapshots(entities, version="5.74")

        assert "Contact" in paths
        assert "Activity" in paths
        assert paths["Contact"].exists()
        assert paths["Activity"].exists()

    def test_generate_changelog(
        self,
        detector: DriftDetector,
        tmp_path: Path,
    ) -> None:
        """Test changelog generation."""
        report = DriftReport()
        change = SchemaChange(
            entity_name="Contact",
            changes=[
                FieldChange(
                    field_name="new_field",
                    change_type=ChangeType.FIELD_ADDED,
                    new_value="String",
                ),
            ],
        )
        report.add_entity_change(change)

        # Test without file output
        content = detector.generate_changelog(report)
        assert "Schema Drift Changelog" in content
        assert "Contact" in content

        # Test with file output
        output_path = tmp_path / "CHANGELOG.md"
        detector.generate_changelog(report, output_path)
        assert output_path.exists()


# =============================================================================
# Integration Tests
# =============================================================================


class TestDriftDetectionIntegration:
    """Integration tests for drift detection workflow."""

    def test_full_drift_detection_workflow(
        self,
        tmp_path: Path,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test complete drift detection workflow."""
        from tests.compat.schema_validator import SchemaCache

        # Setup
        cache_dir = tmp_path / "cache"
        snapshot_dir = tmp_path / "snapshots"

        cache = SchemaCache(cache_dir)
        detector = DriftDetector(cache, snapshot_dir=snapshot_dir)

        # Step 1: Store baseline snapshot
        baseline = SchemaSnapshot.from_api_fields(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        baseline.save(snapshot_dir, version_suffix=False)

        # Step 2: Check for drift
        result = detector.check_entity("Contact", sample_new_fields, current_version="5.74")

        assert result.has_changes is True
        assert result.old_version == "5.73"
        assert result.new_version == "5.74"

        # Step 3: Generate report
        report = DriftReport(base_version="5.73", target_version="5.74")
        report.add_entity_change(result)

        # Step 4: Generate changelog
        changelog = detector.generate_changelog(report)

        assert "Contact" in changelog
        assert "new_field" in changelog
        assert "old_field" in changelog

        # Step 5: Update snapshots
        paths = detector.update_snapshots({"Contact": sample_new_fields}, version="5.74")

        assert paths["Contact"].exists()

        # Step 6: Verify no drift after update
        result_after = detector.check_entity("Contact", sample_new_fields)
        assert result_after.has_changes is False

    def test_drift_modes(
        self,
        tmp_path: Path,
        sample_old_fields: list[dict[str, Any]],
        sample_new_fields: list[dict[str, Any]],
    ) -> None:
        """Test different drift detection modes."""
        from tests.compat.schema_validator import SchemaCache

        cache_dir = tmp_path / "cache"
        snapshot_dir = tmp_path / "snapshots"
        cache = SchemaCache(cache_dir)

        # Store baseline
        baseline = SchemaSnapshot.from_api_fields(
            entity_name="Contact",
            fields=sample_old_fields,
            version="5.73",
        )
        baseline.save(snapshot_dir, version_suffix=False)

        # Test STRICT mode
        strict_detector = DriftDetector(cache, mode=DriftMode.STRICT, snapshot_dir=snapshot_dir)
        result = strict_detector.check_entity("Contact", sample_new_fields)
        report = DriftReport(mode=DriftMode.STRICT)
        report.add_entity_change(result)
        assert report.should_fail() is True  # Any change fails

        # Test BREAKING mode
        breaking_detector = DriftDetector(cache, mode=DriftMode.BREAKING, snapshot_dir=snapshot_dir)
        report = DriftReport(mode=DriftMode.BREAKING)
        report.add_entity_change(result)
        assert report.should_fail() is True  # Has breaking changes

        # Test REPORT mode
        report_mode = DriftReport(mode=DriftMode.REPORT)
        report_mode.add_entity_change(result)
        assert report_mode.should_fail() is False  # Never fails


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_schemas(self, schema_differ: SchemaDiffer) -> None:
        """Test comparing empty schemas."""
        old = SchemaSnapshot(entity_name="Test", fields=[], version="1.0")
        new = SchemaSnapshot(entity_name="Test", fields=[], version="2.0")

        result = schema_differ.compare_schemas(old, new)

        assert result.has_changes is False

    def test_fields_without_names(self, schema_differ: SchemaDiffer) -> None:
        """Test handling fields without name attribute."""
        old = SchemaSnapshot(
            entity_name="Test",
            fields=[{"data_type": "String"}],  # No name
            version="1.0",
        )
        new = SchemaSnapshot(
            entity_name="Test",
            fields=[{"name": "field1", "data_type": "String"}],
            version="2.0",
        )

        # Should not raise
        result = schema_differ.compare_schemas(old, new)
        assert result is not None

    def test_mismatched_entity_names(self, schema_differ: SchemaDiffer) -> None:
        """Test comparing schemas from different entities."""
        old = SchemaSnapshot(entity_name="Contact", fields=[], version="1.0")
        new = SchemaSnapshot(entity_name="Activity", fields=[], version="2.0")

        # Should log warning but not raise
        result = schema_differ.compare_schemas(old, new)
        assert result.entity_name == "Activity"

    def test_invalid_json_file(self, snapshot_dir: Path) -> None:
        """Test handling invalid JSON file."""
        invalid_path = snapshot_dir / "invalid.json"
        invalid_path.write_text("not valid json")

        snapshot = SchemaSnapshot.from_schema_file(invalid_path)
        assert snapshot is None

    def test_malformed_schema_file(self, snapshot_dir: Path) -> None:
        """Test handling malformed schema file."""
        malformed_path = snapshot_dir / "malformed.json"
        malformed_path.write_text('{"some": "data"}')  # Missing required fields

        snapshot = SchemaSnapshot.from_schema_file(malformed_path)
        # Should still load with defaults
        assert snapshot is not None
        assert snapshot.fields == []
