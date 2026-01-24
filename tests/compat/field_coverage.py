"""Field coverage validation for CiviCRM API entity models.

This module provides comprehensive field-level validation between civi-py entity
models and CiviCRM API v4 field definitions. It builds upon the SchemaValidator
to provide detailed coverage metrics including:

- Total field coverage percentage per entity
- Required vs optional field coverage
- Type accuracy (correct Python type mappings)
- Deprecated field detection and warnings
- Missing fields in our models
- Extra fields not in the API schema

Key Components:
    - FieldCoverageValidator: Main validator class for field coverage
    - FieldCoverageReport: Per-entity field coverage statistics
    - FieldCoverageSummary: Aggregate summary across all entities
    - FieldStatus: Enumeration of field coverage states

Usage:
    >>> from tests.compat.field_coverage import FieldCoverageValidator
    >>> validator = FieldCoverageValidator()
    >>> report = validator.validate_entity(Contact, contact_schema)
    >>> print(f"Coverage: {report.coverage_percentage:.1f}%")
    >>> print(f"Type accuracy: {report.type_accuracy:.1f}%")

    # Async usage with live API:
    >>> async with CiviClient() as client:
    ...     validator = FieldCoverageValidator()
    ...     summary = await validator.validate_all_entities_from_api(client)
    ...     summary.save_json("field_coverage_report.json")
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

from tests.compat.schema_validator import (
    SchemaCache,
    SchemaValidator,
    TypeMapping,
    ValidationResult,
)

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient
    from civicrm_py.entities.base import BaseEntity

__all__ = [
    "DeprecatedFieldInfo",
    "FieldCoverageReport",
    "FieldCoverageSummary",
    "FieldCoverageValidator",
    "FieldInfo",
    "FieldStatus",
]

logger = logging.getLogger(__name__)


class FieldStatus(Enum):
    """Status of a field in coverage analysis."""

    COVERED = "covered"  # Field exists in both API and model with correct type
    MISSING = "missing"  # Field in API but not in model
    EXTRA = "extra"  # Field in model but not in API
    TYPE_MISMATCH = "type_mismatch"  # Field exists but type doesn't match
    DEPRECATED = "deprecated"  # Field marked as deprecated in API
    REQUIRED_MISMATCH = "required_mismatch"  # Required status doesn't match


@dataclass
class FieldInfo:
    """Detailed information about a field's coverage status.

    Attributes:
        name: Field name.
        status: Coverage status of the field.
        api_type: Data type from CiviCRM API (if available).
        model_type: Python type from model (if available).
        is_required_api: Whether API marks this as required.
        is_required_model: Whether model marks this as required.
        is_readonly: Whether field is readonly in API.
        is_deprecated: Whether field is deprecated.
        deprecation_message: Deprecation message if applicable.
        fk_entity: Foreign key target entity (if applicable).
        description: Field description from API.
        notes: Additional notes about coverage.
    """

    name: str
    status: FieldStatus
    api_type: str | None = None
    model_type: str | None = None
    is_required_api: bool = False
    is_required_model: bool = False
    is_readonly: bool = False
    is_deprecated: bool = False
    deprecation_message: str | None = None
    fk_entity: str | None = None
    description: str | None = None
    notes: str = ""

    @property
    def is_covered(self) -> bool:
        """Check if field is properly covered."""
        return self.status == FieldStatus.COVERED

    @property
    def has_type_issue(self) -> bool:
        """Check if field has type-related issue."""
        return self.status == FieldStatus.TYPE_MISMATCH

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "api_type": self.api_type,
            "model_type": self.model_type,
            "is_required_api": self.is_required_api,
            "is_required_model": self.is_required_model,
            "is_readonly": self.is_readonly,
            "is_deprecated": self.is_deprecated,
            "deprecation_message": self.deprecation_message,
            "fk_entity": self.fk_entity,
            "description": self.description,
            "notes": self.notes,
        }


@dataclass
class DeprecatedFieldInfo:
    """Information about a deprecated field.

    Attributes:
        name: Field name.
        deprecation_message: Message explaining deprecation.
        replacement: Suggested replacement field (if any).
        removal_version: Version when field will be removed.
        in_model: Whether field exists in our model.
        recommendation: Recommended action.
    """

    name: str
    deprecation_message: str | None = None
    replacement: str | None = None
    removal_version: str | None = None
    in_model: bool = False
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "deprecation_message": self.deprecation_message,
            "replacement": self.replacement,
            "removal_version": self.removal_version,
            "in_model": self.in_model,
            "recommendation": self.recommendation,
        }


@dataclass
class FieldCoverageReport:
    """Comprehensive field coverage report for a single entity.

    Attributes:
        entity_name: CiviCRM entity name.
        api_field_count: Total fields in API schema.
        model_field_count: Total fields in our model.
        covered_fields: Number of properly covered fields.
        missing_fields: Number of API fields not in model.
        extra_fields: Number of model fields not in API.
        type_mismatches: Number of type mismatch issues.
        required_covered: Number of required fields covered.
        required_total: Total required fields in API.
        deprecated_fields: List of deprecated field info.
        field_details: Detailed info for each field.
        validation_result: Underlying SchemaValidator result.
        generated_at: Report generation timestamp.
    """

    entity_name: str
    api_field_count: int = 0
    model_field_count: int = 0
    covered_fields: int = 0
    missing_fields: int = 0
    extra_fields: int = 0
    type_mismatches: int = 0
    required_covered: int = 0
    required_total: int = 0
    deprecated_fields: list[DeprecatedFieldInfo] = field(default_factory=list)
    field_details: list[FieldInfo] = field(default_factory=list)
    validation_result: ValidationResult | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def coverage_percentage(self) -> float:
        """Calculate overall field coverage percentage.

        Coverage = covered_fields / api_field_count * 100
        """
        if self.api_field_count == 0:
            return 100.0  # No fields to cover
        return (self.covered_fields / self.api_field_count) * 100

    @property
    def type_accuracy(self) -> float:
        """Calculate type mapping accuracy percentage.

        Type accuracy = (covered - type_mismatches) / covered * 100
        Only counts fields that exist in both API and model.
        """
        if self.covered_fields == 0:
            return 100.0  # No fields to check
        correct_types = self.covered_fields - self.type_mismatches
        return (correct_types / self.covered_fields) * 100

    @property
    def required_coverage(self) -> float:
        """Calculate required field coverage percentage."""
        if self.required_total == 0:
            return 100.0  # No required fields
        return (self.required_covered / self.required_total) * 100

    @property
    def has_deprecated_in_model(self) -> bool:
        """Check if any deprecated fields are in our model."""
        return any(d.in_model for d in self.deprecated_fields)

    @property
    def deprecated_count(self) -> int:
        """Number of deprecated fields."""
        return len(self.deprecated_fields)

    @property
    def is_fully_covered(self) -> bool:
        """Check if entity has 100% field coverage with no issues."""
        return self.coverage_percentage >= 100.0 and self.type_accuracy >= 100.0 and not self.has_deprecated_in_model

    def get_fields_by_status(self, status: FieldStatus) -> list[FieldInfo]:
        """Get all fields with a specific status."""
        return [f for f in self.field_details if f.status == status]

    def get_missing_field_names(self) -> list[str]:
        """Get names of fields missing from model."""
        return [f.name for f in self.field_details if f.status == FieldStatus.MISSING]

    def get_extra_field_names(self) -> list[str]:
        """Get names of fields in model but not in API."""
        return [f.name for f in self.field_details if f.status == FieldStatus.EXTRA]

    def get_type_mismatch_fields(self) -> list[FieldInfo]:
        """Get fields with type mismatches."""
        return [f for f in self.field_details if f.status == FieldStatus.TYPE_MISMATCH]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_name": self.entity_name,
            "summary": {
                "api_field_count": self.api_field_count,
                "model_field_count": self.model_field_count,
                "covered_fields": self.covered_fields,
                "missing_fields": self.missing_fields,
                "extra_fields": self.extra_fields,
                "type_mismatches": self.type_mismatches,
                "coverage_percentage": round(self.coverage_percentage, 2),
                "type_accuracy": round(self.type_accuracy, 2),
                "required_covered": self.required_covered,
                "required_total": self.required_total,
                "required_coverage": round(self.required_coverage, 2),
                "deprecated_count": self.deprecated_count,
                "has_deprecated_in_model": self.has_deprecated_in_model,
                "is_fully_covered": self.is_fully_covered,
            },
            "deprecated_fields": [d.to_dict() for d in self.deprecated_fields],
            "missing_field_names": self.get_missing_field_names(),
            "extra_field_names": self.get_extra_field_names(),
            "type_mismatch_details": [f.to_dict() for f in self.get_type_mismatch_fields()],
            "field_details": [f.to_dict() for f in self.field_details],
            "generated_at": self.generated_at.isoformat(),
        }

    def to_console(self) -> str:
        """Generate console-friendly output."""
        lines = [
            "-" * 60,
            f"FIELD COVERAGE: {self.entity_name}",
            "-" * 60,
            "",
            f"  API Fields:          {self.api_field_count}",
            f"  Model Fields:        {self.model_field_count}",
            f"  Covered Fields:      {self.covered_fields}",
            f"  Missing Fields:      {self.missing_fields}",
            f"  Extra Fields:        {self.extra_fields}",
            f"  Type Mismatches:     {self.type_mismatches}",
            "",
            f"  Coverage:            {self.coverage_percentage:.1f}%",
            f"  Type Accuracy:       {self.type_accuracy:.1f}%",
            f"  Required Coverage:   {self.required_coverage:.1f}% ({self.required_covered}/{self.required_total})",
            "",
        ]

        if self.deprecated_fields:
            lines.append("  DEPRECATED FIELDS:")
            for dep in self.deprecated_fields:
                in_model = "[IN MODEL]" if dep.in_model else ""
                lines.append(f"    - {dep.name} {in_model}")
                if dep.deprecation_message:
                    lines.append(f"      {dep.deprecation_message}")

        if self.missing_fields > 0:
            lines.append("")
            lines.append("  MISSING FIELDS (in API, not in model):")
            missing_names = self.get_missing_field_names()[:10]
            lines.extend(f"    - {name}" for name in missing_names)
            if self.missing_fields > 10:
                lines.append(f"    ... and {self.missing_fields - 10} more")

        type_mismatches = self.get_type_mismatch_fields()
        if type_mismatches:
            lines.append("")
            lines.append("  TYPE MISMATCHES:")
            lines.extend(f"    - {f.name}: API={f.api_type}, Model={f.model_type}" for f in type_mismatches[:10])
            if len(type_mismatches) > 10:
                lines.append(f"    ... and {len(type_mismatches) - 10} more")

        return "\n".join(lines)


@dataclass
class FieldCoverageSummary:
    """Aggregate field coverage summary across all entities.

    Attributes:
        reports: Individual entity reports.
        total_api_fields: Total fields across all API schemas.
        total_model_fields: Total fields across all models.
        total_covered: Total properly covered fields.
        total_missing: Total missing fields.
        total_extra: Total extra fields.
        total_type_mismatches: Total type mismatch issues.
        entities_with_issues: Entities with coverage issues.
        generated_at: Summary generation timestamp.
    """

    reports: list[FieldCoverageReport] = field(default_factory=list)
    total_api_fields: int = 0
    total_model_fields: int = 0
    total_covered: int = 0
    total_missing: int = 0
    total_extra: int = 0
    total_type_mismatches: int = 0
    entities_with_issues: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def entity_count(self) -> int:
        """Number of entities in summary."""
        return len(self.reports)

    @property
    def overall_coverage(self) -> float:
        """Calculate overall field coverage across all entities."""
        if self.total_api_fields == 0:
            return 100.0
        return (self.total_covered / self.total_api_fields) * 100

    @property
    def overall_type_accuracy(self) -> float:
        """Calculate overall type mapping accuracy."""
        if self.total_covered == 0:
            return 100.0
        correct = self.total_covered - self.total_type_mismatches
        return (correct / self.total_covered) * 100

    @property
    def fully_covered_count(self) -> int:
        """Number of entities with 100% coverage."""
        return sum(1 for r in self.reports if r.is_fully_covered)

    @property
    def has_issues(self) -> bool:
        """Check if any entity has coverage issues."""
        return bool(self.entities_with_issues)

    def get_report(self, entity_name: str) -> FieldCoverageReport | None:
        """Get report for a specific entity."""
        for report in self.reports:
            if report.entity_name == entity_name:
                return report
        return None

    def add_report(self, report: FieldCoverageReport) -> None:
        """Add an entity report and update totals."""
        self.reports.append(report)
        self.total_api_fields += report.api_field_count
        self.total_model_fields += report.model_field_count
        self.total_covered += report.covered_fields
        self.total_missing += report.missing_fields
        self.total_extra += report.extra_fields
        self.total_type_mismatches += report.type_mismatches

        if not report.is_fully_covered:
            self.entities_with_issues.append(report.entity_name)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": {
                "entity_count": self.entity_count,
                "fully_covered_count": self.fully_covered_count,
                "entities_with_issues": len(self.entities_with_issues),
                "total_api_fields": self.total_api_fields,
                "total_model_fields": self.total_model_fields,
                "total_covered": self.total_covered,
                "total_missing": self.total_missing,
                "total_extra": self.total_extra,
                "total_type_mismatches": self.total_type_mismatches,
                "overall_coverage": round(self.overall_coverage, 2),
                "overall_type_accuracy": round(self.overall_type_accuracy, 2),
                "generated_at": self.generated_at.isoformat(),
            },
            "entities_with_issues": self.entities_with_issues,
            "reports": [r.to_dict() for r in self.reports],
        }

    def to_console(self) -> str:
        """Generate console-friendly summary output."""
        lines = [
            "=" * 60,
            "FIELD COVERAGE SUMMARY",
            "=" * 60,
            "",
            f"  Entities Validated:    {self.entity_count}",
            f"  Fully Covered:         {self.fully_covered_count}",
            f"  With Issues:           {len(self.entities_with_issues)}",
            "",
            f"  Total API Fields:      {self.total_api_fields}",
            f"  Total Model Fields:    {self.total_model_fields}",
            f"  Total Covered:         {self.total_covered}",
            f"  Total Missing:         {self.total_missing}",
            f"  Total Extra:           {self.total_extra}",
            f"  Total Type Mismatches: {self.total_type_mismatches}",
            "",
            f"  Overall Coverage:      {self.overall_coverage:.1f}%",
            f"  Overall Type Accuracy: {self.overall_type_accuracy:.1f}%",
            "",
        ]

        if self.entities_with_issues:
            lines.append("ENTITIES WITH ISSUES:")
            for name in self.entities_with_issues:
                report = self.get_report(name)
                if report:
                    lines.append(
                        f"  - {name}: {report.coverage_percentage:.1f}% coverage, {report.type_mismatches} type issues",
                    )
            lines.append("")

        # Per-entity summaries
        lines.append("-" * 60)
        lines.append("PER-ENTITY BREAKDOWN")
        lines.append("-" * 60)

        for report in sorted(self.reports, key=lambda r: r.entity_name):
            status = "[OK]" if report.is_fully_covered else "[!!]"
            lines.append(
                f"  {status} {report.entity_name}: "
                f"{report.coverage_percentage:.0f}% coverage, "
                f"{report.type_accuracy:.0f}% type accuracy",
            )

        lines.extend(["", "=" * 60])
        return "\n".join(lines)

    def save_json(self, path: str | Path) -> None:
        """Save summary to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Field coverage summary saved to %s", path)

    def save_console(self, path: str | Path) -> None:
        """Save console output to text file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_console())
        logger.info("Field coverage console report saved to %s", path)


class FieldCoverageValidator:
    """Validates field-level coverage between models and API schemas.

    This validator provides detailed field coverage analysis by:
    1. Fetching all fields per entity via getFields()
    2. Comparing against entity model fields
    3. Generating coverage reports with type accuracy
    4. Detecting deprecated/removed fields in models

    Attributes:
        cache: SchemaCache for storing/loading API schemas.
        schema_validator: SchemaValidator for type checking.

    Example:
        >>> validator = FieldCoverageValidator()
        >>> report = validator.validate_entity(Contact, contact_schema)
        >>> print(f"Coverage: {report.coverage_percentage:.1f}%")

        >>> # With live API
        >>> async with CiviClient() as client:
        ...     summary = await validator.validate_all_entities_from_api(client)
        ...     print(summary.to_console())
    """

    # Fields to ignore in API schema (internal/computed)
    IGNORED_API_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "check_permissions",
            "row_count",
            "entity_table",
            "entity_id",
        },
    )

    # Fields to ignore in model (internal/computed)
    IGNORED_MODEL_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "_state",
            "_client",
            "_cached_field_names",
            "objects",
        },
    )

    # Relationship field type names to ignore
    RELATIONSHIP_FIELD_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "ForeignKey",
            "RelatedField",
            "ManyToManyField",
            "ForeignKeyAccessor",
            "RelatedManager",
        },
    )

    def __init__(
        self,
        cache: SchemaCache | None = None,
    ) -> None:
        """Initialize field coverage validator.

        Args:
            cache: SchemaCache instance. Creates default if None.
        """
        self.cache = cache or SchemaCache()
        self.schema_validator = SchemaValidator(
            cache=self.cache,
            ignore_extra_api_fields=False,
        )

    def _check_deprecated_field(
        self,
        field_name: str,
        api_field: dict[str, Any],
        model_fields: dict[str, dict[str, Any]],
    ) -> DeprecatedFieldInfo | None:
        """Check if a field is deprecated and create info if so."""
        if not api_field.get("deprecated", False):
            return None

        dep_info = DeprecatedFieldInfo(
            name=field_name,
            deprecation_message=api_field.get("deprecation_message"),
            replacement=api_field.get("replacement"),
            removal_version=api_field.get("removal_version"),
            in_model=field_name in model_fields,
        )
        if dep_info.in_model:
            dep_info.recommendation = f"Consider removing '{field_name}' from model"
        else:
            dep_info.recommendation = "Field already excluded from model"
        return dep_info

    def _create_field_info_for_api_field(
        self,
        field_name: str,
        api_field: dict[str, Any],
        model_fields: dict[str, dict[str, Any]],
    ) -> tuple[FieldInfo, FieldStatus]:
        """Create FieldInfo for an API field, checking against model."""
        api_type = api_field.get("data_type", "String")
        is_required = api_field.get("required", False)
        is_readonly = api_field.get("readonly", False)
        is_deprecated = api_field.get("deprecated", False)
        deprecation_msg = api_field.get("deprecation_message")

        if field_name in model_fields:
            model_field = model_fields[field_name]
            model_type = model_field.get("type")
            model_type_str = str(model_type) if model_type else "Unknown"
            model_required = model_field.get("required", False)

            # Check type compatibility
            if model_type is not None and not TypeMapping.is_compatible(api_type, model_type):
                status = FieldStatus.TYPE_MISMATCH
                notes = f"Expected {TypeMapping.get_expected_python_types(api_type)}"
            else:
                status = FieldStatus.COVERED
                notes = ""

            return FieldInfo(
                name=field_name,
                status=status,
                api_type=api_type,
                model_type=model_type_str,
                is_required_api=is_required,
                is_required_model=model_required,
                is_readonly=is_readonly,
                is_deprecated=is_deprecated,
                deprecation_message=deprecation_msg,
                fk_entity=api_field.get("fk_entity"),
                description=api_field.get("description"),
                notes=notes,
            ), status

        # Field missing from model
        return FieldInfo(
            name=field_name,
            status=FieldStatus.MISSING,
            api_type=api_type,
            model_type=None,
            is_required_api=is_required,
            is_required_model=False,
            is_readonly=is_readonly,
            is_deprecated=is_deprecated,
            deprecation_message=deprecation_msg,
            fk_entity=api_field.get("fk_entity"),
            description=api_field.get("description"),
            notes="Field not defined in model",
        ), FieldStatus.MISSING

    def validate_entity(
        self,
        entity_class: type[BaseEntity],
        api_fields: list[dict[str, Any]],
    ) -> FieldCoverageReport:
        """Validate field coverage for a single entity.

        Args:
            entity_class: Entity class to validate.
            api_fields: Field definitions from CiviCRM getFields().

        Returns:
            FieldCoverageReport with detailed coverage metrics.
        """
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
        report = FieldCoverageReport(entity_name=entity_name)

        model_fields = self._get_model_fields(entity_class)
        api_field_map = {f["name"]: f for f in api_fields if f.get("name") not in self.IGNORED_API_FIELDS}

        report.api_field_count = len(api_field_map)
        report.model_field_count = len(model_fields)

        # Process API fields
        self._process_api_fields(report, api_field_map, model_fields)

        # Process extra model fields
        self._process_extra_model_fields(report, entity_class, model_fields, api_field_map)

        # Run schema validation for reference
        report.validation_result = self.schema_validator.validate_entity(entity_class, api_fields)

        return report

    def _process_api_fields(
        self,
        report: FieldCoverageReport,
        api_field_map: dict[str, dict[str, Any]],
        model_fields: dict[str, dict[str, Any]],
    ) -> None:
        """Process API fields and update report."""
        covered_count = 0
        missing_count = 0
        type_mismatch_count = 0
        required_total = 0
        required_covered = 0
        deprecated_fields: list[DeprecatedFieldInfo] = []

        for field_name, api_field in api_field_map.items():
            is_required = api_field.get("required", False)
            if is_required:
                required_total += 1

            # Check deprecated
            dep_info = self._check_deprecated_field(field_name, api_field, model_fields)
            if dep_info:
                deprecated_fields.append(dep_info)

            # Create field info
            field_info, status = self._create_field_info_for_api_field(
                field_name,
                api_field,
                model_fields,
            )
            report.field_details.append(field_info)

            # Update counts
            if status == FieldStatus.COVERED:
                covered_count += 1
                if is_required:
                    required_covered += 1
            elif status == FieldStatus.MISSING:
                missing_count += 1
            elif status == FieldStatus.TYPE_MISMATCH:
                type_mismatch_count += 1

        report.covered_fields = covered_count
        report.missing_fields = missing_count
        report.type_mismatches = type_mismatch_count
        report.required_total = required_total
        report.required_covered = required_covered
        report.deprecated_fields = deprecated_fields

    def _process_extra_model_fields(
        self,
        report: FieldCoverageReport,
        entity_class: type[BaseEntity],
        model_fields: dict[str, dict[str, Any]],
        api_field_map: dict[str, dict[str, Any]],
    ) -> None:
        """Process fields in model but not in API."""
        extra_count = 0

        for field_name, model_field in model_fields.items():
            if field_name in api_field_map:
                continue
            if self._is_relationship_field(entity_class, field_name):
                continue

            extra_count += 1
            model_type = model_field.get("type")
            model_type_str = str(model_type) if model_type else "Unknown"

            field_info = FieldInfo(
                name=field_name,
                status=FieldStatus.EXTRA,
                api_type=None,
                model_type=model_type_str,
                is_required_api=False,
                is_required_model=model_field.get("required", False),
                notes="Field exists in model but not in API schema",
            )
            report.field_details.append(field_info)

        report.extra_fields = extra_count

    def validate_entity_from_cache(
        self,
        entity_class: type[BaseEntity],
    ) -> FieldCoverageReport | None:
        """Validate entity using cached API schema.

        Args:
            entity_class: Entity class to validate.

        Returns:
            FieldCoverageReport, or None if no cached schema.
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
        *,
        cache_schema: bool = True,
    ) -> FieldCoverageReport:
        """Validate entity by fetching schema from live API.

        Args:
            entity_class: Entity class to validate.
            client: Active CiviClient instance.
            cache_schema: Whether to cache the fetched schema.

        Returns:
            FieldCoverageReport with field coverage details.
        """
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)

        # Fetch fields from API
        response = await client.get_fields(entity_name)
        api_fields = response.values or []

        # Cache for future use
        if cache_schema:
            self.cache.save_schema(entity_name, api_fields)

        return self.validate_entity(entity_class, api_fields)

    def validate_all_entities(
        self,
        entities: dict[str, type[BaseEntity]],
    ) -> FieldCoverageSummary:
        """Validate multiple entities using cached schemas.

        Args:
            entities: Dict mapping entity names to classes.

        Returns:
            FieldCoverageSummary with aggregate metrics.
        """
        summary = FieldCoverageSummary()

        for entity_class in entities.values():
            report = self.validate_entity_from_cache(entity_class)
            if report is not None:
                summary.add_report(report)

        return summary

    async def validate_all_entities_from_api(
        self,
        client: CiviClient,
        entities: dict[str, type[BaseEntity]] | None = None,
        *,
        cache_schemas: bool = True,
    ) -> FieldCoverageSummary:
        """Validate all entities by fetching schemas from live API.

        Args:
            client: Active CiviClient instance.
            entities: Dict mapping entity names to classes.
                     If None, uses all registered entities.
            cache_schemas: Whether to cache fetched schemas.

        Returns:
            FieldCoverageSummary with aggregate metrics.
        """
        from civicrm_py.entities.base import EntityMeta

        if entities is None:
            entities = EntityMeta.get_all_entities()

        summary = FieldCoverageSummary()

        for entity_name, entity_class in entities.items():
            try:
                report = await self.validate_entity_from_api(
                    entity_class,
                    client,
                    cache_schema=cache_schemas,
                )
                summary.add_report(report)
            except Exception as e:
                logger.warning("Failed to validate %s: %s", entity_name, e)

        return summary

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
                if f.name in self.IGNORED_MODEL_FIELDS:
                    continue

                fields[f.name] = {
                    "type": f.type,
                    "default": f.default if f.default is not msgspec.UNSET else None,
                    "required": f.default is msgspec.UNSET and f.default_factory is msgspec.NODEFAULT,
                }
        except (TypeError, NameError):
            # Fallback for non-msgspec classes
            annotations = getattr(entity_class, "__annotations__", {})
            for name, type_hint in annotations.items():
                if name.startswith("_"):
                    continue
                if name in self.IGNORED_MODEL_FIELDS:
                    continue

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
            True if field is a ForeignKey, RelatedField, etc.
        """
        try:
            field_value = getattr(entity_class, field_name, None)
            if field_value is None:
                return False
            type_name = type(field_value).__name__
            return type_name in self.RELATIONSHIP_FIELD_TYPES
        except Exception:
            return False


async def generate_field_coverage_report(
    client: CiviClient,
    entities: dict[str, type[BaseEntity]] | None = None,
    *,
    output_dir: str | Path | None = None,
    cache_schemas: bool = True,
) -> FieldCoverageSummary:
    """Generate comprehensive field coverage report.

    This is the main entry point for field coverage validation.

    Args:
        client: Active CiviClient instance.
        entities: Dict mapping entity names to classes. If None, uses all registered.
        output_dir: Directory to save reports. If None, reports are not saved.
        cache_schemas: Whether to cache fetched schemas.

    Returns:
        FieldCoverageSummary with complete coverage information.

    Example:
        >>> async with CiviClient() as client:
        ...     summary = await generate_field_coverage_report(
        ...         client,
        ...         output_dir="./coverage_reports",
        ...     )
        ...     print(f"Overall coverage: {summary.overall_coverage:.1f}%")
    """
    validator = FieldCoverageValidator()
    summary = await validator.validate_all_entities_from_api(
        client,
        entities,
        cache_schemas=cache_schemas,
    )

    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save summary report
        summary.save_json(output_path / "field_coverage_summary.json")
        summary.save_console(output_path / "field_coverage_summary.txt")

        # Save individual entity reports
        entities_dir = output_path / "entities"
        entities_dir.mkdir(exist_ok=True)

        for report in summary.reports:
            entity_path = entities_dir / f"{report.entity_name.lower()}_fields.json"
            with entity_path.open("w") as f:
                json.dump(report.to_dict(), f, indent=2)

            console_path = entities_dir / f"{report.entity_name.lower()}_fields.txt"
            console_path.write_text(report.to_console())

        logger.info("Field coverage reports saved to %s", output_path)

    return summary
