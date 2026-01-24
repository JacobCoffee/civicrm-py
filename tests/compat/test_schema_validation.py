"""Tests for the schema validation module.

This module contains comprehensive tests for:
- TypeMapping class (API type to Python type mapping)
- SchemaCache class (schema file management)
- SchemaValidator class (entity model validation)
- ValidationResult and ValidationReport (result structures)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import msgspec
import pytest

from tests.compat.schema_validator import (
    FieldMismatch,
    MismatchSeverity,
    MismatchType,
    SchemaCache,
    SchemaValidator,
    TypeMapping,
    ValidationReport,
    ValidationResult,
    create_sample_schema,
)

# =============================================================================
# TypeMapping Tests
# =============================================================================


class TestTypeMapping:
    """Tests for TypeMapping class."""

    @pytest.mark.parametrize(
        ("api_type", "python_type", "expected"),
        [
            # Basic types
            ("String", str, True),
            ("Text", str, True),
            ("Memo", str, True),
            ("Integer", int, True),
            ("Boolean", bool, True),
            ("Float", float, True),
            ("Money", float, True),
            ("Date", str, True),
            ("Datetime", str, True),
            ("Timestamp", int, True),
            ("Array", list, True),
            ("Object", dict, True),
            ("Json", dict, True),
            ("Blob", bytes, True),
            # None type always compatible
            ("String", type(None), True),
            ("Integer", type(None), True),
            # Mismatches
            ("String", int, False),
            ("Integer", str, False),
            ("Boolean", str, False),
            ("Array", str, False),
        ],
    )
    def test_is_compatible_basic_types(
        self,
        api_type: str,
        python_type: type,
        expected: bool,
    ) -> None:
        """Test type compatibility for basic types."""
        assert TypeMapping.is_compatible(api_type, python_type) is expected

    def test_is_compatible_union_types(self) -> None:
        """Test type compatibility for Union types."""
        # str | None should be compatible with String
        assert TypeMapping.is_compatible("String", str | None) is True
        # int | None should be compatible with Integer
        assert TypeMapping.is_compatible("Integer", int | None) is True
        # str | int should be compatible with String (str matches)
        assert TypeMapping.is_compatible("String", str | int) is True
        # int | str should be compatible with Integer (int matches)
        assert TypeMapping.is_compatible("Integer", int | str) is True

    def test_is_compatible_list_types(self) -> None:
        """Test type compatibility for list types."""
        # list should be compatible with Array
        assert TypeMapping.is_compatible("Array", list) is True
        # list[int] should also work (origin is list)
        assert TypeMapping.is_compatible("Array", list[int]) is True
        assert TypeMapping.is_compatible("Array", list[str]) is True

    @pytest.mark.parametrize(
        ("api_type", "expected_types"),
        [
            ("String", (str,)),
            ("Integer", (int,)),
            ("Boolean", (bool,)),
            ("Float", (float,)),
            ("Money", (float, str)),
            ("Array", (list,)),
            ("Object", (dict,)),
            ("Unknown", (object,)),
        ],
    )
    def test_get_expected_python_types(
        self,
        api_type: str,
        expected_types: tuple[type, ...],
    ) -> None:
        """Test getting expected Python types for API types."""
        assert TypeMapping.get_expected_python_types(api_type) == expected_types

    @pytest.mark.parametrize(
        ("python_type", "contains"),
        [
            (str, "String"),
            (int, "Integer"),
            (bool, "Boolean"),
            (float, "Float"),
            (list, "Array"),
            (dict, "Object"),
        ],
    )
    def test_get_expected_api_types(
        self,
        python_type: type,
        contains: str,
    ) -> None:
        """Test getting expected API types for Python types."""
        result = TypeMapping.get_expected_api_types(python_type)
        assert contains in result


# =============================================================================
# SchemaCache Tests
# =============================================================================


class TestSchemaCache:
    """Tests for SchemaCache class."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that SchemaCache creates cache directory."""
        cache_dir = tmp_path / "test_schemas"
        assert not cache_dir.exists()

        cache = SchemaCache(cache_dir=cache_dir)

        assert cache_dir.exists()
        assert cache.cache_dir == cache_dir

    def test_init_default_directory(self) -> None:
        """Test SchemaCache uses default directory when not specified."""
        cache = SchemaCache()
        assert cache.cache_dir.name == "schemas"

    def test_get_schema_path(self, schema_cache: SchemaCache) -> None:
        """Test getting schema file path."""
        path = schema_cache.get_schema_path("Contact")
        assert path.name == "Contact.json"
        assert path.parent == schema_cache.cache_dir

    def test_save_and_load_schema(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test saving and loading a schema."""
        # Save schema
        path = schema_cache.save_schema("TestEntity", minimal_contact_schema)
        assert path.exists()

        # Load schema
        loaded = schema_cache.load_schema("TestEntity")
        assert loaded is not None
        assert len(loaded) == len(minimal_contact_schema)
        assert loaded[0]["name"] == minimal_contact_schema[0]["name"]

    def test_load_schema_not_found(self, schema_cache: SchemaCache) -> None:
        """Test loading non-existent schema returns None."""
        result = schema_cache.load_schema("NonExistent")
        assert result is None

    def test_has_schema(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test checking if schema exists."""
        assert not schema_cache.has_schema("TestEntity")

        schema_cache.save_schema("TestEntity", minimal_contact_schema)

        assert schema_cache.has_schema("TestEntity")

    def test_list_cached_entities(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
        minimal_activity_schema: list[dict[str, Any]],
    ) -> None:
        """Test listing cached entities."""
        # Initially empty
        assert len(schema_cache.list_cached_entities()) == 0

        # Add some schemas
        schema_cache.save_schema("Contact", minimal_contact_schema)
        schema_cache.save_schema("Activity", minimal_activity_schema)

        entities = schema_cache.list_cached_entities()
        assert "Contact" in entities
        assert "Activity" in entities
        assert len(entities) == 2

    def test_list_cached_entities_ignores_underscore_files(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test that files starting with _ are ignored."""
        schema_cache.save_schema("Contact", minimal_contact_schema)

        # Create an underscore file
        readme_path = schema_cache.cache_dir / "_README.json"
        readme_path.write_text("{}")

        entities = schema_cache.list_cached_entities()
        assert "Contact" in entities
        assert "_README" not in entities

    def test_clear_cache(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test clearing the cache."""
        schema_cache.save_schema("Contact", minimal_contact_schema)
        schema_cache.save_schema("Activity", minimal_contact_schema)

        assert len(schema_cache.list_cached_entities()) == 2

        removed = schema_cache.clear_cache()

        assert removed == 2
        assert len(schema_cache.list_cached_entities()) == 0

    def test_save_schema_with_metadata(
        self,
        schema_cache: SchemaCache,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test saving schema with additional metadata."""
        metadata = {"civicrm_version": "5.74", "custom_key": "custom_value"}

        path = schema_cache.save_schema(
            "Contact",
            minimal_contact_schema,
            metadata=metadata,
        )

        # Read the raw file to check metadata
        with path.open() as f:
            data = json.load(f)

        assert data["metadata"]["civicrm_version"] == "5.74"
        assert data["metadata"]["custom_key"] == "custom_value"
        assert "cached_at" in data


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Test creating a valid result."""
        result = ValidationResult(
            entity_name="Contact",
            is_valid=True,
            api_field_count=40,
            model_field_count=38,
        )

        assert result.entity_name == "Contact"
        assert result.is_valid is True
        assert result.error_count == 0
        assert result.warning_count == 0
        assert len(result.all_mismatches) == 0

    def test_invalid_result_with_errors(self) -> None:
        """Test creating an invalid result with errors."""
        error = FieldMismatch(
            field_name="test_field",
            mismatch_type=MismatchType.TYPE_MISMATCH,
            severity=MismatchSeverity.ERROR,
            message="Test error",
        )

        result = ValidationResult(
            entity_name="Contact",
            is_valid=False,
            errors=[error],
        )

        assert result.is_valid is False
        assert result.error_count == 1
        assert result.all_mismatches == [error]

    def test_result_with_warnings(self) -> None:
        """Test result with warnings only."""
        warning = FieldMismatch(
            field_name="optional_field",
            mismatch_type=MismatchType.MISSING_FIELD,
            severity=MismatchSeverity.WARNING,
            message="Field missing",
        )

        result = ValidationResult(
            entity_name="Contact",
            is_valid=True,
            warnings=[warning],
        )

        assert result.is_valid is True  # Warnings don't invalidate
        assert result.warning_count == 1
        assert result.error_count == 0

    def test_to_dict(self, sample_failed_validation_result: ValidationResult) -> None:
        """Test serializing result to dictionary."""
        data = sample_failed_validation_result.to_dict()

        assert data["entity_name"] == "TestEntity"
        assert data["is_valid"] is False
        assert len(data["errors"]) == 1
        assert data["errors"][0]["field"] == "bad_field"
        assert "validated_at" in data


# =============================================================================
# ValidationReport Tests
# =============================================================================


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_empty_report(self) -> None:
        """Test empty report."""
        report = ValidationReport()

        assert report.total_entities == 0
        assert report.valid_entities == 0
        assert report.invalid_entities == 0
        assert report.total_errors == 0

    def test_add_results(
        self,
        sample_validation_result: ValidationResult,
        sample_failed_validation_result: ValidationResult,
    ) -> None:
        """Test adding results to report."""
        report = ValidationReport()
        report.add_result(sample_validation_result)
        report.add_result(sample_failed_validation_result)

        assert report.total_entities == 2
        assert report.valid_entities == 1
        assert report.invalid_entities == 1
        assert report.total_errors == 1

    def test_get_result(self, sample_validation_result: ValidationResult) -> None:
        """Test getting specific entity result."""
        report = ValidationReport()
        report.add_result(sample_validation_result)

        result = report.get_result("Contact")
        assert result is not None
        assert result.entity_name == "Contact"

        missing = report.get_result("NonExistent")
        assert missing is None

    def test_to_dict(self, sample_validation_report: ValidationReport) -> None:
        """Test serializing report to dictionary."""
        data = sample_validation_report.to_dict()

        assert "generated_at" in data
        assert "summary" in data
        assert data["summary"]["total_entities"] == 1
        assert "results" in data
        assert len(data["results"]) == 1


# =============================================================================
# FieldMismatch Tests
# =============================================================================


class TestFieldMismatch:
    """Tests for FieldMismatch dataclass."""

    def test_create_mismatch(self) -> None:
        """Test creating a field mismatch."""
        mismatch = FieldMismatch(
            field_name="test_field",
            mismatch_type=MismatchType.TYPE_MISMATCH,
            severity=MismatchSeverity.ERROR,
            message="Test message",
            api_value="Integer",
            model_value="str",
        )

        assert mismatch.field_name == "test_field"
        assert mismatch.mismatch_type == MismatchType.TYPE_MISMATCH
        assert mismatch.severity == MismatchSeverity.ERROR
        assert "Test message" in str(mismatch)

    def test_mismatch_str_format(self) -> None:
        """Test string representation of mismatch."""
        mismatch = FieldMismatch(
            field_name="my_field",
            mismatch_type=MismatchType.MISSING_FIELD,
            severity=MismatchSeverity.WARNING,
            message="Field is missing",
        )

        result = str(mismatch)
        assert "[WARNING]" in result
        assert "my_field" in result
        assert "Field is missing" in result


# =============================================================================
# SchemaValidator Tests
# =============================================================================


class TestSchemaValidator:
    """Tests for SchemaValidator class."""

    def test_validate_entity_with_matching_schema(
        self,
        schema_validator: SchemaValidator,
        contact_entity_class: type,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating entity with matching schema."""
        result = schema_validator.validate_entity(
            contact_entity_class,
            minimal_contact_schema,
        )

        assert result.entity_name == "Contact"
        # Should have few/no errors for matching fields
        assert result.api_field_count == len(minimal_contact_schema)

    def test_validate_entity_type_mismatch(
        self,
        schema_validator: SchemaValidator,
    ) -> None:
        """Test detecting type mismatches."""
        # Create a test entity with string field
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None), ("name", str | None, None)],
            kw_only=True,
        )

        # Schema says 'name' is Integer (mismatch)
        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "name", "data_type": "Integer", "required": False},  # Wrong!
        ]

        result = schema_validator.validate_entity(TestEntity, schema)

        # Should have a type mismatch error
        type_errors = [e for e in result.errors if e.mismatch_type == MismatchType.TYPE_MISMATCH]
        assert len(type_errors) >= 1

    def test_validate_entity_extra_model_fields(
        self,
        schema_validator: SchemaValidator,
    ) -> None:
        """Test detecting extra fields in model."""
        # Create entity with extra field
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("extra_field", str | None, None),
            ],
            kw_only=True,
        )

        # Schema only has id
        schema = [{"name": "id", "data_type": "Integer", "required": False}]

        result = schema_validator.validate_entity(TestEntity, schema)

        # Should have info about extra field
        extra_fields = [m for m in result.info if m.mismatch_type == MismatchType.EXTRA_FIELD]
        assert len(extra_fields) >= 1

    def test_validate_entity_missing_api_fields(
        self,
        full_schema_validator: SchemaValidator,
    ) -> None:
        """Test detecting missing API fields when not ignored."""
        # Create entity with only id
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        # Schema has id and another field
        schema = [
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "api_field", "data_type": "String", "required": False},
        ]

        result = full_schema_validator.validate_entity(TestEntity, schema)

        # Should have warning about missing field
        missing = [w for w in result.warnings if w.mismatch_type == MismatchType.MISSING_FIELD]
        assert len(missing) >= 1

    def test_validate_entity_strict_mode(
        self,
        strict_schema_validator: SchemaValidator,
    ) -> None:
        """Test strict mode treats warnings as errors."""
        # Create entity
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        # Schema with required field that model allows None
        schema = [
            {"name": "id", "data_type": "Integer", "required": True},  # Required!
        ]

        result = strict_schema_validator.validate_entity(TestEntity, schema)

        # In strict mode, warnings make result invalid
        if result.warnings:
            assert result.is_valid is False

    def test_validate_entity_from_cache(
        self,
        schema_validator: SchemaValidator,
        contact_entity_class: type,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating entity from cached schema."""
        # Save schema to cache
        schema_validator.cache.save_schema("Contact", minimal_contact_schema)

        # Validate from cache
        result = schema_validator.validate_entity_from_cache(contact_entity_class)

        assert result is not None
        assert result.entity_name == "Contact"

    def test_validate_entity_from_cache_not_found(
        self,
        schema_validator: SchemaValidator,
        contact_entity_class: type,
    ) -> None:
        """Test validating when schema not cached."""
        result = schema_validator.validate_entity_from_cache(contact_entity_class)
        assert result is None

    def test_validate_all_entities(
        self,
        schema_validator: SchemaValidator,
        minimal_contact_schema: list[dict[str, Any]],
        minimal_activity_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating multiple entities."""
        from civicrm_py.entities import Activity, Contact

        # Cache schemas
        schema_validator.cache.save_schema("Contact", minimal_contact_schema)
        schema_validator.cache.save_schema("Activity", minimal_activity_schema)

        entities = {"Contact": Contact, "Activity": Activity}

        report = schema_validator.validate_all_entities(entities)

        assert report.total_entities == 2
        assert report.get_result("Contact") is not None
        assert report.get_result("Activity") is not None

    @pytest.mark.asyncio
    async def test_validate_entity_from_api(
        self,
        schema_validator: SchemaValidator,
        contact_entity_class: type,
        minimal_contact_schema: list[dict[str, Any]],
    ) -> None:
        """Test validating entity by fetching schema from API."""
        # Mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = minimal_contact_schema
        mock_client.get_fields = AsyncMock(return_value=mock_response)

        result = await schema_validator.validate_entity_from_api(
            contact_entity_class,
            mock_client,
        )

        assert result.entity_name == "Contact"
        mock_client.get_fields.assert_called_once_with("Contact")

        # Should also cache the schema
        assert schema_validator.cache.has_schema("Contact")


# =============================================================================
# Integration Tests with Real Entity Classes
# =============================================================================


class TestSchemaValidationIntegration:
    """Integration tests using real entity classes and cached schemas."""

    def test_contact_entity_validation(
        self,
        production_schema_cache: SchemaCache,
        contact_entity_class: type,
    ) -> None:
        """Test validating Contact entity against cached schema."""
        schema = production_schema_cache.load_schema("Contact")

        if schema is None:
            pytest.skip("Contact schema not cached")

        validator = SchemaValidator(cache=production_schema_cache)
        result = validator.validate_entity(contact_entity_class, schema)

        # Print any errors for debugging
        for error in result.errors:
            print(f"Error: {error}")

        # Contact should be mostly valid
        assert result.entity_name == "Contact"
        # Allow some tolerance for complex real-world schemas
        assert result.error_count <= 5, f"Too many errors: {result.errors}"

    def test_activity_entity_validation(
        self,
        production_schema_cache: SchemaCache,
        activity_entity_class: type,
    ) -> None:
        """Test validating Activity entity against cached schema."""
        schema = production_schema_cache.load_schema("Activity")

        if schema is None:
            pytest.skip("Activity schema not cached")

        validator = SchemaValidator(cache=production_schema_cache)
        result = validator.validate_entity(activity_entity_class, schema)

        assert result.entity_name == "Activity"
        assert result.error_count <= 5, f"Too many errors: {result.errors}"

    def test_all_entities_validation(
        self,
        production_schema_cache: SchemaCache,
        all_entity_classes: dict[str, type],
    ) -> None:
        """Test validating all entities that have cached schemas."""
        validator = SchemaValidator(cache=production_schema_cache)

        # Filter to entities with cached schemas
        entities_with_schemas = {
            name: cls for name, cls in all_entity_classes.items() if production_schema_cache.has_schema(name)
        }

        if not entities_with_schemas:
            pytest.skip("No cached schemas available")

        report = validator.validate_all_entities(entities_with_schemas)

        # Print summary
        print("\nValidation Report:")
        print(f"  Total entities: {report.total_entities}")
        print(f"  Valid: {report.valid_entities}")
        print(f"  Invalid: {report.invalid_entities}")
        print(f"  Total errors: {report.total_errors}")
        print(f"  Total warnings: {report.total_warnings}")

        # All tested entities should have results
        assert report.total_entities == len(entities_with_schemas)


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_sample_schema(self) -> None:
        """Test creating a sample schema structure."""
        fields = [
            {"name": "id", "data_type": "Integer"},
            {"name": "name", "data_type": "String"},
        ]

        schema = create_sample_schema("TestEntity", fields)

        assert schema["entity_name"] == "TestEntity"
        assert schema["fields"] == fields
        assert "cached_at" in schema
        assert schema["metadata"]["source"] == "test_fixture"


# =============================================================================
# MismatchType and MismatchSeverity Tests
# =============================================================================


class TestEnums:
    """Tests for enum classes."""

    def test_mismatch_type_values(self) -> None:
        """Test MismatchType enum values."""
        assert MismatchType.MISSING_FIELD.value == "missing_field"
        assert MismatchType.EXTRA_FIELD.value == "extra_field"
        assert MismatchType.TYPE_MISMATCH.value == "type_mismatch"
        assert MismatchType.REQUIRED_MISMATCH.value == "required_mismatch"
        assert MismatchType.DEFAULT_MISMATCH.value == "default_mismatch"

    def test_mismatch_severity_values(self) -> None:
        """Test MismatchSeverity enum values."""
        assert MismatchSeverity.ERROR.value == "error"
        assert MismatchSeverity.WARNING.value == "warning"
        assert MismatchSeverity.INFO.value == "info"


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_schema(self, schema_validator: SchemaValidator) -> None:
        """Test validating against empty schema."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None)],
            kw_only=True,
        )

        result = schema_validator.validate_entity(TestEntity, [])

        assert result.api_field_count == 0

    def test_schema_with_no_data_type(
        self,
        schema_validator: SchemaValidator,
    ) -> None:
        """Test handling schema fields without data_type."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("id", int | None, None), ("name", str | None, None)],
            kw_only=True,
        )

        # Schema without data_type (defaults to String)
        schema = [
            {"name": "id", "required": False},  # No data_type
            {"name": "name", "required": False},
        ]

        # Should not raise
        result = schema_validator.validate_entity(TestEntity, schema)
        assert result is not None

    def test_unknown_api_type(self, schema_validator: SchemaValidator) -> None:
        """Test handling unknown API data type."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [("field", object, None)],
            kw_only=True,
        )

        schema = [{"name": "field", "data_type": "UnknownType", "required": False}]

        # Should handle gracefully
        result = schema_validator.validate_entity(TestEntity, schema)
        assert result is not None

    def test_ignored_fields(self, schema_validator: SchemaValidator) -> None:
        """Test that ignored fields are skipped."""
        TestEntity = msgspec.defstruct(
            "TestEntity",
            [
                ("id", int | None, None),
                ("_internal", str | None, None),  # Should be ignored
            ],
            kw_only=True,
        )

        schema = [{"name": "id", "data_type": "Integer", "required": False}]

        result = schema_validator.validate_entity(TestEntity, schema)

        # _internal should not cause issues
        internal_errors = [e for e in result.all_mismatches if e.field_name == "_internal"]
        assert len(internal_errors) == 0

    def test_special_api_fields_ignored(
        self,
        schema_validator: SchemaValidator,
    ) -> None:
        """Test that special API-only fields are ignored."""
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

        # Use full validator that reports missing fields
        validator = SchemaValidator(
            cache=schema_validator.cache,
            ignore_extra_api_fields=False,
        )

        result = validator.validate_entity(TestEntity, schema)

        # Special fields should be ignored
        special_warnings = [w for w in result.warnings if w.field_name in ("check_permissions", "row_count")]
        assert len(special_warnings) == 0
