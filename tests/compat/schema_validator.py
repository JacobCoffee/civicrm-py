"""Schema validation for CiviCRM API compatibility.

This module provides tools to compare civi-py entity models against CiviCRM
API v4 field definitions fetched via getFields(). It enables automated
detection of:

- Missing fields in our models
- Extra fields not in the API schema
- Type mismatches between API and Python types
- Required field discrepancies

Usage:
    >>> validator = SchemaValidator()
    >>> result = validator.validate_entity(Contact, contact_schema)
    >>> if not result.is_valid:
    ...     for error in result.errors:
    ...         print(f"{error.severity}: {error.message}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import msgspec

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient
    from civicrm_py.entities.base import BaseEntity

__all__ = [
    "FieldMismatch",
    "MismatchSeverity",
    "MismatchType",
    "SchemaCache",
    "SchemaValidator",
    "TypeMapping",
    "ValidationReport",
    "ValidationResult",
]

logger = logging.getLogger(__name__)


class MismatchType(Enum):
    """Types of mismatches between model and API schema."""

    MISSING_FIELD = "missing_field"  # Field in API but not in model
    EXTRA_FIELD = "extra_field"  # Field in model but not in API
    TYPE_MISMATCH = "type_mismatch"  # Python type doesn't match API data_type
    REQUIRED_MISMATCH = "required_mismatch"  # Required flag doesn't match
    DEFAULT_MISMATCH = "default_mismatch"  # Default value doesn't match


class MismatchSeverity(Enum):
    """Severity levels for schema mismatches."""

    ERROR = "error"  # Critical - will cause runtime failures
    WARNING = "warning"  # May cause issues in some cases
    INFO = "info"  # Informational - no immediate issue


@dataclass
class FieldMismatch:
    """Represents a single mismatch between model and API schema."""

    field_name: str
    mismatch_type: MismatchType
    severity: MismatchSeverity
    message: str
    api_value: Any = None
    model_value: Any = None

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"[{self.severity.value.upper()}] {self.field_name}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validating a single entity against its API schema."""

    entity_name: str
    is_valid: bool = True  # Default to valid, will be set false if errors found
    errors: list[FieldMismatch] = field(default_factory=list)
    warnings: list[FieldMismatch] = field(default_factory=list)
    info: list[FieldMismatch] = field(default_factory=list)
    api_field_count: int = 0
    model_field_count: int = 0
    validated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def all_mismatches(self) -> list[FieldMismatch]:
        """Get all mismatches regardless of severity."""
        return self.errors + self.warnings + self.info

    @property
    def error_count(self) -> int:
        """Number of error-level mismatches."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Number of warning-level mismatches."""
        return len(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_name": self.entity_name,
            "is_valid": self.is_valid,
            "errors": [
                {
                    "field": e.field_name,
                    "type": e.mismatch_type.value,
                    "message": e.message,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "field": w.field_name,
                    "type": w.mismatch_type.value,
                    "message": w.message,
                }
                for w in self.warnings
            ],
            "api_field_count": self.api_field_count,
            "model_field_count": self.model_field_count,
            "validated_at": self.validated_at,
        }


@dataclass
class ValidationReport:
    """Aggregate report for multiple entity validations."""

    results: list[ValidationResult] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def total_entities(self) -> int:
        """Total number of entities validated."""
        return len(self.results)

    @property
    def valid_entities(self) -> int:
        """Number of entities with no errors."""
        return sum(1 for r in self.results if r.is_valid)

    @property
    def invalid_entities(self) -> int:
        """Number of entities with at least one error."""
        return self.total_entities - self.valid_entities

    @property
    def total_errors(self) -> int:
        """Total number of errors across all entities."""
        return sum(r.error_count for r in self.results)

    @property
    def total_warnings(self) -> int:
        """Total number of warnings across all entities."""
        return sum(r.warning_count for r in self.results)

    def add_result(self, result: ValidationResult) -> None:
        """Add a validation result to the report."""
        self.results.append(result)

    def get_result(self, entity_name: str) -> ValidationResult | None:
        """Get result for a specific entity."""
        for result in self.results:
            if result.entity_name == entity_name:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "generated_at": self.generated_at,
            "summary": {
                "total_entities": self.total_entities,
                "valid_entities": self.valid_entities,
                "invalid_entities": self.invalid_entities,
                "total_errors": self.total_errors,
                "total_warnings": self.total_warnings,
            },
            "results": [r.to_dict() for r in self.results],
        }


class TypeMapping:
    """Maps CiviCRM API data types to Python types.

    This class provides bidirectional mapping between CiviCRM's data types
    (String, Integer, Boolean, etc.) and their Python equivalents.
    """

    # CiviCRM API type -> Python type(s)
    # Some API types can map to multiple Python types (e.g., Date -> str or datetime)
    API_TO_PYTHON: ClassVar[dict[str, tuple[type, ...]]] = {
        "String": (str,),
        "Text": (str,),
        "Memo": (str,),
        "Integer": (int,),
        "Boolean": (bool,),
        "Float": (float,),
        "Money": (float, str),  # Can be str for precision
        "Date": (str,),  # ISO format string
        "Datetime": (str,),  # ISO format string
        "Timestamp": (int, str),  # Unix timestamp or ISO string
        "Array": (list,),
        "Object": (dict,),
        "Json": (dict, str),  # Can be dict or JSON string
        "Blob": (bytes, str),
    }

    # Python type -> CiviCRM API type(s)
    PYTHON_TO_API: ClassVar[dict[type, tuple[str, ...]]] = {
        str: ("String", "Text", "Memo", "Date", "Datetime"),
        int: ("Integer", "Timestamp"),
        bool: ("Boolean",),
        float: ("Float", "Money"),
        list: ("Array",),
        dict: ("Object", "Json"),
        bytes: ("Blob",),
    }

    @classmethod
    def _check_union_compatibility(cls, api_type: str, args: tuple[type, ...]) -> bool:
        """Check if any non-None type in a union is compatible with the API type."""
        non_none_args = [arg for arg in args if arg is not type(None)]
        if not non_none_args:
            # Only None types - this is unusual but accept it
            return True
        # Check that at least one non-None type is compatible
        return any(cls.is_compatible(api_type, arg) for arg in non_none_args)

    @classmethod
    def is_compatible(cls, api_type: str, python_type: type | str) -> bool:
        """Check if a Python type is compatible with a CiviCRM API type.

        Args:
            api_type: CiviCRM data type name (e.g., "String", "Integer").
            python_type: Python type or string representation to check.

        Returns:
            True if the types are compatible.
        """
        import types
        import typing

        # Handle string type annotations (from __annotations__ fallback)
        if isinstance(python_type, str):
            return cls._is_compatible_string(api_type, python_type)

        # Handle None type (optional fields) - None alone is always compatible
        if python_type is type(None):
            return True

        # Handle Python 3.10+ union types (e.g., int | None using | operator)
        if isinstance(python_type, types.UnionType):
            return cls._check_union_compatibility(api_type, python_type.__args__)

        # Handle typing.Union and generic types
        origin = getattr(python_type, "__origin__", None)
        if origin is typing.Union:
            return cls._check_union_compatibility(api_type, getattr(python_type, "__args__", ()))

        if origin is not None:
            # For generic types like list[int], dict[str, Any], check the origin
            compatible_types = cls.API_TO_PYTHON.get(api_type, ())
            return origin in compatible_types

        # Direct type lookup
        compatible_types = cls.API_TO_PYTHON.get(api_type, ())
        return python_type in compatible_types

    @classmethod
    def _is_compatible_string(cls, api_type: str, type_str: str) -> bool:
        """Check compatibility using string type representation.

        Args:
            api_type: CiviCRM data type name.
            type_str: String representation of Python type.

        Returns:
            True if types are compatible.
        """
        # Normalize the type string
        type_str = type_str.strip()

        # Handle Union types like "str | None" or "int | None"
        if " | " in type_str:
            parts = [p.strip() for p in type_str.split(" | ")]
            # Filter out None and check at least one type is compatible
            non_none_parts = [p for p in parts if p != "None"]
            if not non_none_parts:
                return True
            return any(cls._is_compatible_string(api_type, p) for p in non_none_parts)

        # Handle generic types like "list[int]"
        if "[" in type_str:
            # Extract base type
            base_type = type_str.split("[")[0]
            return cls._is_compatible_string(api_type, base_type)

        # Map string type names to expected API types
        string_to_api: dict[str, tuple[str, ...]] = {
            "str": ("String", "Text", "Memo", "Date", "Datetime", "Timestamp"),
            "int": ("Integer", "Timestamp"),
            "bool": ("Boolean",),
            "float": ("Float", "Money"),
            "list": ("Array",),
            "dict": ("Object", "Json"),
            "bytes": ("Blob",),
        }

        expected_api_types = string_to_api.get(type_str, ())
        return api_type in expected_api_types

    @classmethod
    def get_expected_python_types(cls, api_type: str) -> tuple[type, ...]:
        """Get expected Python types for a CiviCRM API type.

        Args:
            api_type: CiviCRM data type name.

        Returns:
            Tuple of compatible Python types.
        """
        return cls.API_TO_PYTHON.get(api_type, (object,))

    @classmethod
    def get_expected_api_types(cls, python_type: type) -> tuple[str, ...]:
        """Get expected CiviCRM API types for a Python type.

        Args:
            python_type: Python type to look up.

        Returns:
            Tuple of compatible CiviCRM API types.
        """
        # Handle Optional/Union types
        origin = getattr(python_type, "__origin__", None)
        if origin is not None:
            args = getattr(python_type, "__args__", ())
            # Get API types for all non-None args
            result: set[str] = set()
            for arg in args:
                if arg is not type(None):
                    result.update(cls.get_expected_api_types(arg))
            return tuple(result) if result else ("String",)

        return cls.PYTHON_TO_API.get(python_type, ("String",))


class SchemaCache:
    """Manages cached API schema files.

    Schemas are stored as JSON files in the schemas/ directory and can be
    refreshed from a live CiviCRM API.
    """

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        """Initialize schema cache.

        Args:
            cache_dir: Directory for cached schema files.
                       Defaults to tests/compat/schemas/.
        """
        if cache_dir is None:
            self.cache_dir = Path(__file__).parent / "schemas"
        else:
            self.cache_dir = Path(cache_dir)

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_schema_path(self, entity_name: str) -> Path:
        """Get path to schema file for an entity.

        Args:
            entity_name: CiviCRM entity name.

        Returns:
            Path to the schema JSON file.
        """
        return self.cache_dir / f"{entity_name}.json"

    def load_schema(self, entity_name: str) -> list[dict[str, Any]] | None:
        """Load cached schema for an entity.

        Args:
            entity_name: CiviCRM entity name.

        Returns:
            List of field definitions, or None if not cached.
        """
        path = self.get_schema_path(entity_name)
        if not path.exists():
            return None

        try:
            with path.open("r") as f:
                data = json.load(f)
                return data.get("fields", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load schema for %s: %s", entity_name, e)
            return None

    def save_schema(
        self,
        entity_name: str,
        fields: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Save schema to cache.

        Args:
            entity_name: CiviCRM entity name.
            fields: List of field definitions from getFields.
            metadata: Optional metadata (version, timestamp, etc.).

        Returns:
            Path to the saved schema file.
        """
        path = self.get_schema_path(entity_name)
        data = {
            "entity_name": entity_name,
            "fields": fields,
            "cached_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        with path.open("w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Saved schema for %s to %s", entity_name, path)
        return path

    def has_schema(self, entity_name: str) -> bool:
        """Check if schema is cached for an entity.

        Args:
            entity_name: CiviCRM entity name.

        Returns:
            True if schema is cached.
        """
        return self.get_schema_path(entity_name).exists()

    def list_cached_entities(self) -> list[str]:
        """List all entities with cached schemas.

        Returns:
            List of entity names.
        """
        return [p.stem for p in self.cache_dir.glob("*.json") if not p.name.startswith("_")]

    def clear_cache(self) -> int:
        """Remove all cached schemas.

        Returns:
            Number of files removed.
        """
        count = 0
        for path in self.cache_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count

    async def refresh_from_api(
        self,
        client: CiviClient,
        entity_names: list[str] | None = None,
    ) -> dict[str, Path]:
        """Refresh schemas from live CiviCRM API.

        Args:
            client: Active CiviClient instance.
            entity_names: Entities to refresh. If None, discovers all.

        Returns:
            Dict mapping entity names to their schema file paths.
        """
        from civicrm_py.entities.discovery import EntityDiscovery

        discovery = EntityDiscovery(client)
        paths: dict[str, Path] = {}

        if entity_names is None:
            # Discover all entities
            entities = await discovery.get_entities()
            entity_names = [e.name for e in entities]

        for entity_name in entity_names:
            try:
                response = await client.get_fields(entity_name)
                fields = response.values or []
                path = self.save_schema(entity_name, fields)
                paths[entity_name] = path
            except Exception as e:
                logger.warning("Failed to fetch schema for %s: %s", entity_name, e)

        return paths


class SchemaValidator:
    """Validates entity models against CiviCRM API schemas.

    The validator compares Python entity class fields with the field
    definitions returned by CiviCRM's getFields() action, identifying
    mismatches in field presence, types, and requirements.

    Example:
        >>> from civicrm_py.entities import Contact
        >>> validator = SchemaValidator()
        >>> schema = cache.load_schema("Contact")
        >>> result = validator.validate_entity(Contact, schema)
        >>> print(f"Valid: {result.is_valid}, Errors: {result.error_count}")
    """

    # Fields that are typically internal/computed and can be ignored
    IGNORED_API_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "check_permissions",
            "row_count",
            "entity_table",
            "entity_id",
        }
    )

    # Fields in our models that don't exist in API (computed properties, relations)
    IGNORED_MODEL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "_state",
            "_client",
            "_cached_field_names",
            "objects",
        }
    )

    def __init__(
        self,
        cache: SchemaCache | None = None,
        *,
        strict: bool = False,
        ignore_extra_api_fields: bool = True,
    ) -> None:
        """Initialize schema validator.

        Args:
            cache: Schema cache instance. Creates default if None.
            strict: If True, treat warnings as errors.
            ignore_extra_api_fields: If True, don't report fields in API but not in model.
        """
        self.cache = cache or SchemaCache()
        self.strict = strict
        self.ignore_extra_api_fields = ignore_extra_api_fields

    def validate_entity(
        self,
        entity_class: type[BaseEntity],
        api_fields: list[dict[str, Any]],
    ) -> ValidationResult:
        """Validate an entity class against API field definitions.

        Args:
            entity_class: Entity class to validate.
            api_fields: Field definitions from CiviCRM getFields().

        Returns:
            ValidationResult with any mismatches found.
        """
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
        result = ValidationResult(entity_name=entity_name)

        # Get model field info using msgspec
        model_fields = self._get_model_fields(entity_class)
        api_field_map = {f["name"]: f for f in api_fields}

        result.api_field_count = len(api_field_map)
        result.model_field_count = len(model_fields)

        # Check for type mismatches and missing required fields
        for field_name, field_info in model_fields.items():
            if field_name in self.IGNORED_MODEL_FIELDS:
                continue

            api_field = api_field_map.get(field_name)
            if api_field is None:
                # Field in model but not in API - might be a relationship or computed
                if not self._is_relationship_field(entity_class, field_name):
                    mismatch = FieldMismatch(
                        field_name=field_name,
                        mismatch_type=MismatchType.EXTRA_FIELD,
                        severity=MismatchSeverity.INFO,
                        message=f"Field '{field_name}' exists in model but not in API schema",
                        model_value=field_info.get("type"),
                    )
                    result.info.append(mismatch)
            else:
                # Check type compatibility
                self._check_type_compatibility(
                    field_name,
                    field_info,
                    api_field,
                    result,
                )

                # Check required status
                self._check_required_status(
                    field_name,
                    field_info,
                    api_field,
                    result,
                )

        # Check for fields in API but not in model
        if not self.ignore_extra_api_fields:
            for api_field_name, api_field in api_field_map.items():
                if api_field_name in self.IGNORED_API_FIELDS:
                    continue
                if api_field_name not in model_fields:
                    mismatch = FieldMismatch(
                        field_name=api_field_name,
                        mismatch_type=MismatchType.MISSING_FIELD,
                        severity=MismatchSeverity.WARNING,
                        message=f"API field '{api_field_name}' not defined in model",
                        api_value=api_field.get("data_type"),
                    )
                    result.warnings.append(mismatch)

        # Determine overall validity
        result.is_valid = len(result.errors) == 0
        if self.strict:
            result.is_valid = result.is_valid and len(result.warnings) == 0

        return result

    def validate_entity_from_cache(
        self,
        entity_class: type[BaseEntity],
    ) -> ValidationResult | None:
        """Validate entity using cached schema.

        Args:
            entity_class: Entity class to validate.

        Returns:
            ValidationResult, or None if no cached schema.
        """
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
        api_fields = self.cache.load_schema(entity_name)

        if api_fields is None:
            return None

        return self.validate_entity(entity_class, api_fields)

    async def validate_entity_from_api(
        self,
        entity_class: type[BaseEntity],
        client: CiviClient,
    ) -> ValidationResult:
        """Validate entity by fetching schema from API.

        Args:
            entity_class: Entity class to validate.
            client: Active CiviClient instance.

        Returns:
            ValidationResult with any mismatches.
        """
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)

        # Fetch fields from API
        response = await client.get_fields(entity_name)
        api_fields = response.values or []

        # Cache for future use
        self.cache.save_schema(entity_name, api_fields)

        return self.validate_entity(entity_class, api_fields)

    def validate_all_entities(
        self,
        entities: dict[str, type[BaseEntity]],
    ) -> ValidationReport:
        """Validate multiple entities using cached schemas.

        Args:
            entities: Dict mapping entity names to classes.

        Returns:
            ValidationReport with results for all entities.
        """
        report = ValidationReport()

        for entity_class in entities.values():
            result = self.validate_entity_from_cache(entity_class)
            if result is not None:
                report.add_result(result)

        return report

    def _get_model_fields(
        self,
        entity_class: type[BaseEntity],
    ) -> dict[str, dict[str, Any]]:
        """Extract field information from an entity class.

        Args:
            entity_class: Entity class to inspect.

        Returns:
            Dict mapping field names to their metadata.
        """
        fields: dict[str, dict[str, Any]] = {}

        # Use msgspec.structs.fields to get field info
        try:
            struct_fields = msgspec.structs.fields(entity_class)
            for f in struct_fields:
                if f.name.startswith("_"):
                    continue
                fields[f.name] = {
                    "type": f.type,
                    "default": f.default if f.default is not msgspec.UNSET else None,
                    "required": f.default is msgspec.UNSET and f.default_factory is msgspec.NODEFAULT,
                }
        except (TypeError, NameError):
            # Fallback for non-msgspec classes or forward reference issues
            # Use __annotations__ directly without resolving forward refs
            annotations = getattr(entity_class, "__annotations__", {})
            for name, type_hint in annotations.items():
                if name.startswith("_"):
                    continue
                # Handle forward references by converting to string
                type_hint_str = type_hint if isinstance(type_hint, str) else str(type_hint)

                default = getattr(entity_class, name, None)
                fields[name] = {
                    "type": type_hint,
                    "type_str": type_hint_str,
                    "default": default,
                    "required": default is None and "None" not in type_hint_str,
                }

        return fields

    def _is_relationship_field(
        self,
        entity_class: type[BaseEntity],
        field_name: str,
    ) -> bool:
        """Check if a field is a relationship descriptor.

        Args:
            entity_class: Entity class to check.
            field_name: Field name to check.

        Returns:
            True if field is a ForeignKey or RelatedField.
        """
        try:
            field_value = getattr(entity_class, field_name, None)
            if field_value is None:
                return False
            type_name = type(field_value).__name__
            return type_name in ("ForeignKey", "RelatedField", "ManyToManyField")
        except Exception:
            return False

    def _check_type_compatibility(
        self,
        field_name: str,
        model_field: dict[str, Any],
        api_field: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check if model field type is compatible with API type.

        Args:
            field_name: Name of the field.
            model_field: Model field metadata.
            api_field: API field definition.
            result: ValidationResult to append mismatches to.
        """
        api_type = api_field.get("data_type", "String")
        model_type = model_field.get("type")

        if model_type is None:
            return

        if not TypeMapping.is_compatible(api_type, model_type):
            expected = TypeMapping.get_expected_python_types(api_type)
            mismatch = FieldMismatch(
                field_name=field_name,
                mismatch_type=MismatchType.TYPE_MISMATCH,
                severity=MismatchSeverity.ERROR,
                message=f"Type mismatch: API expects {api_type} ({expected}), model has {model_type}",
                api_value=api_type,
                model_value=str(model_type),
            )
            result.errors.append(mismatch)

    def _check_required_status(
        self,
        field_name: str,
        model_field: dict[str, Any],
        api_field: dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check if model field required status matches API.

        Args:
            field_name: Name of the field.
            model_field: Model field metadata.
            api_field: API field definition.
            result: ValidationResult to append mismatches to.
        """
        api_required = api_field.get("required", False)
        model_required = model_field.get("required", False)

        # Only flag if API requires but model doesn't
        if api_required and not model_required:
            # Check if model type allows None
            model_type = model_field.get("type")
            type_str = str(model_type) if model_type else ""
            allows_none = "None" in type_str or model_field.get("default") is not None

            if allows_none:
                mismatch = FieldMismatch(
                    field_name=field_name,
                    mismatch_type=MismatchType.REQUIRED_MISMATCH,
                    severity=MismatchSeverity.WARNING,
                    message=f"API marks '{field_name}' as required, but model allows None",
                    api_value=True,
                    model_value=False,
                )
                result.warnings.append(mismatch)


def create_sample_schema(
    entity_name: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a sample schema structure for testing.

    Args:
        entity_name: Entity name.
        fields: List of field definitions.

    Returns:
        Complete schema structure.
    """
    return {
        "entity_name": entity_name,
        "fields": fields,
        "cached_at": datetime.now(UTC).isoformat(),
        "metadata": {
            "source": "test_fixture",
            "civicrm_version": "5.74",
        },
    }
