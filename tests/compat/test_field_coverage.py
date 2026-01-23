"""Tests for the field coverage validation module.

This module contains comprehensive tests for:
- FieldCoverageValidator class
- FieldCoverageReport and FieldCoverageSummary dataclasses
- FieldStatus enumeration
- Type accuracy calculations
- Deprecated field detection
- Integration with real entity classes
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import msgspec
import pytest

from tests.compat.field_coverage import (
    DeprecatedFieldInfo,
    FieldCoverageReport,
    FieldCoverageSummary,
    FieldCoverageValidator,
    FieldInfo,
    FieldStatus,
    generate_field_coverage_report,
)
from tests.compat.schema_validator import SchemaCache

# =============================================================================
# FieldStatus Tests
# =============================================================================


class TestFieldStatus:
    """Tests for FieldStatus enumeration."""

    def test_field_status_values(self) -> None:
        """Test FieldStatus enum values."""
        assert FieldStatus.COVERED.value == "covered"
        assert FieldStatus.MISSING.value == "missing"
        assert FieldStatus.EXTRA.value == "extra"
        assert FieldStatus.TYPE_MISMATCH.value == "type_mismatch"
        assert FieldStatus.DEPRECATED.value == "deprecated"
        assert FieldStatus.REQUIRED_MISMATCH.value == "required_mismatch"

    def test_all_statuses_exist(self) -> None:
        """Test all expected statuses exist."""
        expected = {"COVERED", "MISSING", "EXTRA", "TYPE_MISMATCH", "DEPRECATED", "REQUIRED_MISMATCH"}
        actual = {s.name for s in FieldStatus}
        assert actual == expected


# =============================================================================
# FieldInfo Tests
# =============================================================================


class TestFieldInfo:
    """Tests for FieldInfo dataclass."""

    def test_create_field_info(self) -> None:
        """Test creating FieldInfo instance."""
        info = FieldInfo(
            name="test_field",
            status=FieldStatus.COVERED,
            api_type="String",
            model_type="str",
            is_required_api=True,
            is_required_model=True,
        )

        assert info.name == "test_field"
        assert info.status == FieldStatus.COVERED
        assert info.api_type == "String"
        assert info.model_type == "str"
        assert info.is_required_api is True
        assert info.is_required_model is True

    def test_is_covered_property(self) -> None:
        """Test is_covered property."""
        covered = FieldInfo(name="field", status=FieldStatus.COVERED)
        assert covered.is_covered is True

        missing = FieldInfo(name="field", status=FieldStatus.MISSING)
        assert missing.is_covered is False

    def test_has_type_issue_property(self) -> None:
        """Test has_type_issue property."""
        mismatch = FieldInfo(name="field", status=FieldStatus.TYPE_MISMATCH)
        assert mismatch.has_type_issue is True

        covered = FieldInfo(name="field", status=FieldStatus.COVERED)
        assert covered.has_type_issue is False

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        info = FieldInfo(
            name="test_field",
            status=FieldStatus.COVERED,
            api_type="Integer",
            model_type="int",
            is_required_api=False,
            is_required_model=False,
            is_deprecated=True,
            deprecation_message="Use new_field instead",
        )

        data = info.to_dict()

        assert data["name"] == "test_field"
        assert data["status"] == "covered"
        assert data["api_type"] == "Integer"
        assert data["model_type"] == "int"
        assert data["is_deprecated"] is True
        assert data["deprecation_message"] == "Use new_field instead"


# =============================================================================
# DeprecatedFieldInfo Tests
# =============================================================================


class TestDeprecatedFieldInfo:
    """Tests for DeprecatedFieldInfo dataclass."""

    def test_create_deprecated_info(self) -> None:
        """Test creating DeprecatedFieldInfo."""
        info = DeprecatedFieldInfo(
            name="old_field",
            deprecation_message="This field is deprecated",
            replacement="new_field",
            removal_version="6.0",
            in_model=True,
            recommendation="Remove from model",
        )

        assert info.name == "old_field"
        assert info.deprecation_message == "This field is deprecated"
        assert info.replacement == "new_field"
        assert info.removal_version == "6.0"
        assert info.in_model is True
        assert info.recommendation == "Remove from model"

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        info = DeprecatedFieldInfo(
            name="old_field",
            deprecation_message="Deprecated",
            in_model=True,
        )

        data = info.to_dict()

        assert data["name"] == "old_field"
        assert data["deprecation_message"] == "Deprecated"
        assert data["in_model"] is True


# =============================================================================
# FieldCoverageReport Tests
# =============================================================================


class TestFieldCoverageReport:
    """Tests for FieldCoverageReport dataclass."""

    def test_empty_report(self) -> None:
        """Test creating empty report."""
        report = FieldCoverageReport(entity_name="TestEntity")

        assert report.entity_name == "TestEntity"
        assert report.api_field_count == 0
        assert report.model_field_count == 0
        assert report.covered_fields == 0
        assert report.coverage_percentage == 100.0  # No fields to cover
        assert report.type_accuracy == 100.0  # No fields to check

    def test_coverage_percentage(self) -> None:
        """Test coverage percentage calculation."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            api_field_count=10,
            covered_fields=8,
        )

        assert report.coverage_percentage == 80.0

    def test_type_accuracy(self) -> None:
        """Test type accuracy calculation."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            covered_fields=10,
            type_mismatches=2,
        )

        assert report.type_accuracy == 80.0

    def test_required_coverage(self) -> None:
        """Test required field coverage calculation."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            required_total=5,
            required_covered=4,
        )

        assert report.required_coverage == 80.0

    def test_is_fully_covered(self) -> None:
        """Test is_fully_covered property."""
        # Full coverage
        full_report = FieldCoverageReport(
            entity_name="TestEntity",
            api_field_count=10,
            covered_fields=10,
            type_mismatches=0,
        )
        assert full_report.is_fully_covered is True

        # Not fully covered
        partial_report = FieldCoverageReport(
            entity_name="TestEntity",
            api_field_count=10,
            covered_fields=8,
        )
        assert partial_report.is_fully_covered is False

    def test_has_deprecated_in_model(self) -> None:
        """Test deprecated field detection."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            deprecated_fields=[
                DeprecatedFieldInfo(name="old_field", in_model=True),
                DeprecatedFieldInfo(name="old_field2", in_model=False),
            ],
        )

        assert report.has_deprecated_in_model is True

    def test_get_fields_by_status(self) -> None:
        """Test getting fields by status."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            field_details=[
                FieldInfo(name="field1", status=FieldStatus.COVERED),
                FieldInfo(name="field2", status=FieldStatus.COVERED),
                FieldInfo(name="field3", status=FieldStatus.MISSING),
                FieldInfo(name="field4", status=FieldStatus.TYPE_MISMATCH),
            ],
        )

        covered = report.get_fields_by_status(FieldStatus.COVERED)
        assert len(covered) == 2

        missing = report.get_fields_by_status(FieldStatus.MISSING)
        assert len(missing) == 1
        assert missing[0].name == "field3"

    def test_get_missing_field_names(self) -> None:
        """Test getting missing field names."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            field_details=[
                FieldInfo(name="field1", status=FieldStatus.COVERED),
                FieldInfo(name="field2", status=FieldStatus.MISSING),
                FieldInfo(name="field3", status=FieldStatus.MISSING),
            ],
        )

        missing = report.get_missing_field_names()
        assert "field2" in missing
        assert "field3" in missing
        assert "field1" not in missing

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        report = FieldCoverageReport(
            entity_name="TestEntity",
            api_field_count=10,
            model_field_count=8,
            covered_fields=8,
            missing_fields=2,
            type_mismatches=1,
        )

        data = report.to_dict()

        assert data["entity_name"] == "TestEntity"
        assert data["summary"]["api_field_count"] == 10
        assert data["summary"]["coverage_percentage"] == 80.0
        assert "generated_at" in data

    def test_to_console(self) -> None:
        """Test console output generation."""
        report = FieldCoverageReport(
            entity_name="Contact",
            api_field_count=40,
            model_field_count=35,
            covered_fields=35,
            missing_fields=5,
            type_mismatches=2,
            field_details=[
                FieldInfo(name="missing_field", status=FieldStatus.MISSING),
            ],
        )

        output = report.to_console()

        assert "FIELD COVERAGE: Contact" in output
        assert "40" in output  # API fields
        assert "35" in output  # Model fields
        assert "MISSING FIELDS" in output


# =============================================================================
# FieldCoverageSummary Tests
# =============================================================================


class TestFieldCoverageSummary:
    """Tests for FieldCoverageSummary dataclass."""

    def test_empty_summary(self) -> None:
        """Test empty summary."""
        summary = FieldCoverageSummary()

        assert summary.entity_count == 0
        assert summary.overall_coverage == 100.0
        assert summary.fully_covered_count == 0
        assert summary.has_issues is False

    def test_add_report(self) -> None:
        """Test adding reports to summary."""
        summary = FieldCoverageSummary()

        report1 = FieldCoverageReport(
            entity_name="Contact",
            api_field_count=40,
            covered_fields=40,
        )
        report2 = FieldCoverageReport(
            entity_name="Activity",
            api_field_count=20,
            covered_fields=18,
            missing_fields=2,
        )

        summary.add_report(report1)
        summary.add_report(report2)

        assert summary.entity_count == 2
        assert summary.total_api_fields == 60
        assert summary.total_covered == 58
        assert summary.total_missing == 2

    def test_overall_coverage(self) -> None:
        """Test overall coverage calculation."""
        summary = FieldCoverageSummary()
        summary.total_api_fields = 100
        summary.total_covered = 85

        assert summary.overall_coverage == 85.0

    def test_get_report(self) -> None:
        """Test getting specific entity report."""
        summary = FieldCoverageSummary()
        report = FieldCoverageReport(entity_name="Contact")
        summary.add_report(report)

        result = summary.get_report("Contact")
        assert result is not None
        assert result.entity_name == "Contact"

        missing = summary.get_report("NonExistent")
        assert missing is None

    def test_entities_with_issues(self) -> None:
        """Test tracking entities with issues."""
        summary = FieldCoverageSummary()

        # Full coverage
        report1 = FieldCoverageReport(
            entity_name="Good",
            api_field_count=10,
            covered_fields=10,
        )
        # Partial coverage
        report2 = FieldCoverageReport(
            entity_name="Bad",
            api_field_count=10,
            covered_fields=5,
            missing_fields=5,
        )

        summary.add_report(report1)
        summary.add_report(report2)

        assert summary.has_issues is True
        assert "Bad" in summary.entities_with_issues
        assert "Good" not in summary.entities_with_issues

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        summary = FieldCoverageSummary()
        summary.add_report(FieldCoverageReport(entity_name="Contact"))

        data = summary.to_dict()

        assert "summary" in data
        assert data["summary"]["entity_count"] == 1
        assert "reports" in data
        assert len(data["reports"]) == 1

    def test_to_console(self) -> None:
        """Test console output generation."""
        summary = FieldCoverageSummary()
        summary.add_report(
            FieldCoverageReport(
                entity_name="Contact",
                api_field_count=40,
                covered_fields=40,
            ),
        )

        output = summary.to_console()

        assert "FIELD COVERAGE SUMMARY" in output
        assert "Contact" in output

    def test_save_json(self, tmp_path: Path) -> None:
        """Test saving summary to JSON file."""
        summary = FieldCoverageSummary()
        summary.add_report(FieldCoverageReport(entity_name="Contact"))

        json_path = tmp_path / "summary.json"
        summary.save_json(json_path)

        assert json_path.exists()
        with json_path.open() as f:
            data = json.load(f)
        assert data["summary"]["entity_count"] == 1

    def test_save_console(self, tmp_path: Path) -> None:
        """Test saving console output to file."""
        summary = FieldCoverageSummary()
        summary.add_report(FieldCoverageReport(entity_name="Contact"))

        txt_path = tmp_path / "summary.txt"
        summary.save_console(txt_path)

        assert txt_path.exists()
        content = txt_path.read_text()
        assert "Contact" in content


# =============================================================================
# FieldCoverageValidator Tests
# =============================================================================


class TestFieldCoverageValidator:
    """Tests for FieldCoverageValidator class."""

    @pytest.fixture
    def validator(self, schema_cache: SchemaCache) -> FieldCoverageValidator:
        """Create validator with test cache."""
        return FieldCoverageValidator(cache=schema_cache)

    def test_init_default_cache(self) -> None:
        """Test validator initialization with default cache."""
        validator = FieldCoverageValidator()
        assert validator.cache is not None

    def test_init_custom_cache(self, schema_cache: SchemaCache) -> None:
        """Test validator initialization with custom cache."""
        validator = FieldCoverageValidator(cache=schema_cache)
        assert validator.cache is schema_cache

    def test_validate_entity_full_coverage(self, validator: FieldCoverageValidator) -> None:
        """Test validating entity with full field coverage."""
        # Create test entity
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("name", str | None, None),
                ("is_active", bool, False),
            ],
            kw_only=True,
        )

        # Matching schema
        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "name", "data_type": "String", "required": False},
            {"name": "is_active", "data_type": "Boolean", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.entity_name == "TestEntity"
        assert report.api_field_count == 3
        assert report.covered_fields == 3
        assert report.coverage_percentage == 100.0
        assert report.type_accuracy == 100.0

    def test_validate_entity_missing_fields(self, validator: FieldCoverageValidator) -> None:
        """Test detecting missing fields."""
        # Create entity with fewer fields than schema
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "name", "data_type": "String", "required": False},
            {"name": "description", "data_type": "Text", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.api_field_count == 3
        assert report.covered_fields == 1
        assert report.missing_fields == 2
        assert "name" in report.get_missing_field_names()
        assert "description" in report.get_missing_field_names()

    def test_validate_entity_extra_fields(self, validator: FieldCoverageValidator) -> None:
        """Test detecting extra fields in model."""
        # Create entity with more fields than schema
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("extra_field", str | None, None),
            ],
            kw_only=True,
        )

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.extra_fields == 1
        assert "extra_field" in report.get_extra_field_names()

    def test_validate_entity_type_mismatch(self, validator: FieldCoverageValidator) -> None:
        """Test detecting type mismatches."""
        # Entity with string where API expects integer
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("count", str | None, None)],  # Wrong type!
            kw_only=True,
        )

        schema = [
            {"name": "count", "data_type": "Integer", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.type_mismatches == 1
        mismatches = report.get_type_mismatch_fields()
        assert len(mismatches) == 1
        assert mismatches[0].name == "count"
        assert mismatches[0].api_type == "Integer"

    def test_validate_entity_deprecated_fields(self, validator: FieldCoverageValidator) -> None:
        """Test detecting deprecated fields."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("old_field", str | None, None),  # Deprecated but in model
            ],
            kw_only=True,
        )

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {
                "name": "old_field",
                "data_type": "String",
                "required": False,
                "deprecated": True,
                "deprecation_message": "Use new_field instead",
            },
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.deprecated_count == 1
        assert report.has_deprecated_in_model is True
        assert report.deprecated_fields[0].name == "old_field"
        assert report.deprecated_fields[0].in_model is True

    def test_validate_entity_required_coverage(self, validator: FieldCoverageValidator) -> None:
        """Test required field coverage tracking."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("required_field", str | None, None),
            ],
            kw_only=True,
        )

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "required_field", "data_type": "String", "required": True},
            {"name": "another_required", "data_type": "String", "required": True},
        ]

        report = validator.validate_entity(TestEntity, schema)

        assert report.required_total == 2
        assert report.required_covered == 1
        assert report.required_coverage == 50.0

    def test_validate_entity_ignores_internal_fields(
        self,
        validator: FieldCoverageValidator,
    ) -> None:
        """Test that internal fields are ignored."""
        # Check_permissions should be ignored from API fields
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "check_permissions", "data_type": "Boolean", "required": False},
            {"name": "row_count", "data_type": "Integer", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        # Only 'id' should count (others are ignored)
        assert report.api_field_count == 1

    def test_validate_entity_from_cache(
        self,
        validator: FieldCoverageValidator,
        minimal_contact_schema: list[dict[str, Any]],
        contact_entity_class: type,
    ) -> None:
        """Test validating from cached schema."""
        # Save schema to cache
        validator.cache.save_schema("Contact", minimal_contact_schema)

        report = validator.validate_entity_from_cache(contact_entity_class)

        assert report is not None
        assert report.entity_name == "Contact"

    def test_validate_entity_from_cache_not_found(
        self,
        validator: FieldCoverageValidator,
        contact_entity_class: type,
    ) -> None:
        """Test validating when schema not cached."""
        report = validator.validate_entity_from_cache(contact_entity_class)
        assert report is None

    @pytest.mark.asyncio
    async def test_validate_entity_from_api(
        self,
        validator: FieldCoverageValidator,
        contact_entity_class: type,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating by fetching schema from API."""
        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = minimal_contact_schema
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        report = await validator.validate_entity_from_api(
            contact_entity_class,
            mock_client,
        )

        assert report.entity_name == "Contact"
        mock_client.get_fields.assert_called_once_with("Contact")

        # Should also cache the schema
        assert validator.cache.has_schema("Contact")

    def test_validate_all_entities(
        self,
        validator: FieldCoverageValidator,
        minimal_contact_schema: list[dict[str, Any]],
        minimal_activity_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating multiple entities from cache."""
        from civi_py.entities import Activity, Contact

        # Cache schemas
        validator.cache.save_schema("Contact", minimal_contact_schema)
        validator.cache.save_schema("Activity", minimal_activity_schema)

        entities = {"Contact": Contact, "Activity": Activity}
        summary = validator.validate_all_entities(entities)

        assert summary.entity_count == 2
        assert summary.get_report("Contact") is not None
        assert summary.get_report("Activity") is not None


# =============================================================================
# Integration Tests with Real Entity Classes
# =============================================================================


class TestFieldCoverageIntegration:
    """Integration tests using real entity classes and cached schemas."""

    def test_contact_field_coverage(
        self,
        production_schema_cache: SchemaCache,
        contact_entity_class: type,
    ) -> None:
        """Test Contact entity field coverage against cached schema."""
        schema = production_schema_cache.load_schema("Contact")

        if schema is None:
            pytest.skip("Contact schema not cached")

        validator = FieldCoverageValidator(cache=production_schema_cache)
        report = validator.validate_entity(contact_entity_class, schema)

        # Print report for debugging
        print(report.to_console())

        # Contact should have high coverage
        assert report.entity_name == "Contact"
        assert report.coverage_percentage >= 70.0, f"Coverage too low: {report.coverage_percentage}%"
        assert report.type_accuracy >= 90.0, f"Type accuracy too low: {report.type_accuracy}%"

    def test_activity_field_coverage(
        self,
        production_schema_cache: SchemaCache,
        activity_entity_class: type,
    ) -> None:
        """Test Activity entity field coverage against cached schema."""
        schema = production_schema_cache.load_schema("Activity")

        if schema is None:
            pytest.skip("Activity schema not cached")

        validator = FieldCoverageValidator(cache=production_schema_cache)
        report = validator.validate_entity(activity_entity_class, schema)

        assert report.entity_name == "Activity"
        assert report.coverage_percentage >= 60.0

    def test_all_entities_field_coverage(
        self,
        production_schema_cache: SchemaCache,
        all_entity_classes: dict[str, type],
    ) -> None:
        """Test field coverage for all entities with cached schemas."""
        validator = FieldCoverageValidator(cache=production_schema_cache)

        # Filter to entities with cached schemas
        entities_with_schemas = {
            name: cls for name, cls in all_entity_classes.items() if production_schema_cache.has_schema(name)
        }

        if not entities_with_schemas:
            pytest.skip("No cached schemas available")

        summary = validator.validate_all_entities(entities_with_schemas)

        # Print summary for debugging
        print(summary.to_console())

        # Basic assertions
        assert summary.entity_count >= 1
        assert summary.overall_coverage >= 50.0

    def test_coverage_report_json_export(
        self,
        production_schema_cache: SchemaCache,
        contact_entity_class: type,
        tmp_path: Path,
    ) -> None:
        """Test exporting coverage report to JSON."""
        schema = production_schema_cache.load_schema("Contact")

        if schema is None:
            pytest.skip("Contact schema not cached")

        validator = FieldCoverageValidator(cache=production_schema_cache)
        report = validator.validate_entity(contact_entity_class, schema)

        # Export to JSON
        json_path = tmp_path / "contact_coverage.json"
        with json_path.open("w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Verify JSON is valid
        with json_path.open() as f:
            data = json.load(f)

        assert data["entity_name"] == "Contact"
        assert "summary" in data
        assert "field_details" in data


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestFieldCoverageEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_schema(self) -> None:
        """Test validating against empty schema."""
        validator = FieldCoverageValidator()
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        report = validator.validate_entity(TestEntity, [])

        assert report.api_field_count == 0
        assert report.coverage_percentage == 100.0  # No fields to cover

    def test_empty_entity(self) -> None:
        """Test validating entity with no fields."""
        validator = FieldCoverageValidator()
        EmptyEntity = msgspec.defstruct("EmptyEntity", [], kw_only=True)

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
        ]

        report = validator.validate_entity(EmptyEntity, schema)

        assert report.model_field_count == 0
        assert report.missing_fields == 1

    def test_schema_without_data_type(self) -> None:
        """Test handling schema fields without data_type."""
        validator = FieldCoverageValidator()
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("field", str | None, None)],
            kw_only=True,
        )

        schema = [
            {"name": "field", "required": False},  # No data_type
        ]

        # Should not raise
        report = validator.validate_entity(TestEntity, schema)
        assert report is not None

    def test_union_types_coverage(self) -> None:
        """Test coverage with Union types."""
        validator = FieldCoverageValidator()
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("optional_int", int | None, None)],
            kw_only=True,
        )

        schema = [
            {"name": "optional_int", "data_type": "Integer", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        # int | None should be compatible with Integer
        assert report.type_mismatches == 0
        assert report.covered_fields == 1

    def test_list_types_coverage(self) -> None:
        """Test coverage with list types."""
        validator = FieldCoverageValidator()
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("tags", list[str] | None, None)],
            kw_only=True,
        )

        schema = [
            {"name": "tags", "data_type": "Array", "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        # list[str] should be compatible with Array
        assert report.type_mismatches == 0
        assert report.covered_fields == 1

    def test_relationship_fields_ignored(self) -> None:
        """Test that relationship fields are not counted as extra."""
        validator = FieldCoverageValidator()

        # Create a mock entity class with relationship attribute
        class MockEntity:
            __entity_name__: ClassVar[str] = "MockEntity"
            __annotations__ = {"id": "int | None"}

            # Simulate relationship field
            class MockRelatedField:
                pass

            related_items = MockRelatedField()

        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
        ]

        # The relationship field should be ignored
        # This is a simplified test since real entities use descriptors
        report = validator.validate_entity(MockEntity, schema)
        assert report is not None


# =============================================================================
# Async Tests
# =============================================================================


class TestFieldCoverageAsync:
    """Async tests for field coverage validation."""

    @pytest.mark.asyncio
    async def test_validate_all_entities_from_api(self) -> None:
        """Test validating all entities from live API."""
        from civi_py.entities import Contact

        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "display_name", "data_type": "String", "required": False},
        ]
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        validator = FieldCoverageValidator()
        entities = {"Contact": Contact}

        summary = await validator.validate_all_entities_from_api(
            mock_client,
            entities,
            cache_schemas=False,
        )

        assert summary.entity_count == 1
        assert "Contact" in [r.entity_name for r in summary.reports]

    @pytest.mark.asyncio
    async def test_generate_field_coverage_report(self, tmp_path: Path) -> None:
        """Test the main report generation function."""
        from civi_py.entities import Contact

        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [
            {"name": "id", "data_type": "Integer", "required": False},
        ]
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        entities = {"Contact": Contact}

        summary = await generate_field_coverage_report(
            mock_client,
            entities,
            output_dir=tmp_path,
            cache_schemas=False,
        )

        assert summary is not None
        assert summary.entity_count == 1

        # Check files were created
        assert (tmp_path / "field_coverage_summary.json").exists()
        assert (tmp_path / "field_coverage_summary.txt").exists()
        assert (tmp_path / "entities" / "contact_fields.json").exists()


# =============================================================================
# Parametrized Type Mapping Tests
# =============================================================================


class TestTypeAccuracyParametrized:
    """Parametrized tests for type accuracy calculations."""

    @pytest.mark.parametrize(
        ("api_type", "python_type", "should_match"),
        [
            ("String", str, True),
            ("String", "str", True),
            ("String", str | None, True),
            ("Integer", int, True),
            ("Integer", int | None, True),
            ("Boolean", bool, True),
            ("Float", float, True),
            ("Array", list, True),
            ("Array", list[str], True),
            ("Date", str, True),
            ("Datetime", str, True),
            ("Timestamp", str, True),  # Can be str or int
            ("Timestamp", int, True),
            ("String", int, False),
            ("Integer", str, False),
            ("Boolean", str, False),
        ],
    )
    def test_type_compatibility_in_coverage(
        self,
        api_type: str,
        python_type: type | str,
        should_match: bool,
    ) -> None:
        """Test type compatibility affects coverage calculation."""
        validator = FieldCoverageValidator()

        # Create entity with the specified type
        if isinstance(python_type, str):
            # Handle string type annotations
            TestEntity = type("TestEntity", (), {"__annotations__": {"field": python_type}})
        else:
            TestEntity = msgspec.defstruct(
                "TestEntity",
                [("field", python_type, None)],
                kw_only=True,
            )

        schema = [
            {"name": "field", "data_type": api_type, "required": False},
        ]

        report = validator.validate_entity(TestEntity, schema)

        if should_match:
            assert report.type_mismatches == 0, f"Expected {api_type} to match {python_type}"
        else:
            assert report.type_mismatches > 0, f"Expected {api_type} to NOT match {python_type}"
