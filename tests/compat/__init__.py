"""CiviCRM API compatibility testing module.

This package provides comprehensive tools for validating civi-py's coverage
and compatibility with CiviCRM API v4.

Version Compatibility (Phase 8.5.5):
    - version_matrix: CiviCRM version compatibility tracking
    - VersionInfo: Version metadata and capabilities
    - VersionMatrix: Registry of supported versions and differences
    - APIDifference: Describes API differences between versions
    - VersionDetector: Detect version from live instance

Coverage Validation (Phase 8.5.7 & 8.5.8):
    - coverage_validator: Entity and action coverage validation
    - EntityCoverageValidator: Compare implemented vs available entities
    - ActionCoverageValidator: Compare implemented vs available actions
    - Coverage report generation in JSON and console formats
    - Priority-ranked TODO lists for missing implementations

Schema Validation:
    - schema_validator: Core validation logic for comparing entity models to API schemas
    - test_schema_validation: Tests for the schema validator
    - schemas/: Cached JSON schema files from CiviCRM API getFields responses

API Drift Detection (Phase 8.5.6):
    - drift_detector: Schema diff and drift detection logic
    - SchemaSnapshot: Versioned schema storage
    - SchemaDiffer: Compare schemas and generate diffs
    - DriftReport: Aggregate reporting with breaking change detection
    - DriftDetector: High-level detection with pytest integration
    - schemas/snapshots/: Versioned schema snapshots for drift comparison

Report Generation (Phase 8.5.14):
    - report_generator: Comprehensive coverage report generation
    - ReportGenerator: Main report coordinator
    - AggregateReport: Combined coverage report structure
    - HTMLReportGenerator: Standalone HTML report with inline CSS
    - MarkdownReportGenerator: Documentation-friendly Markdown output
    - BadgeGenerator: SVG badges for README

VCR/Cassette Support:
    This module also provides VCR/cassette-style API response recording and replay
    for testing against different CiviCRM versions without requiring a live instance.

Usage:
    >>> from tests.compat.coverage_validator import (
    ...     EntityCoverageValidator,
    ...     ActionCoverageValidator,
    ...     generate_coverage_reports,
    ... )
    >>>
    >>> async with CiviClient() as client:
    ...     report = await generate_coverage_reports(client, output_dir="./reports")
    ...     print(f"Entity Coverage: {report.overall_entity_coverage:.1f}%")
    ...     print(f"Action Coverage: {report.overall_action_coverage:.1f}%")

    >>> # Generate standalone HTML report
    >>> from tests.compat.report_generator import ReportGenerator
    >>> generator = ReportGenerator(output_dir="./coverage_reports")
    >>> report = generator.generate_aggregate_report_offline()
    >>> generator.save_all_formats(report)

    >>> # CLI usage
    >>> # python -m tests.compat.report_generator -o ./coverage_reports

Version Matrix Usage:
    >>> from tests.compat.version_matrix import (
    ...     get_version_matrix,
    ...     VersionDetector,
    ...     skip_for_version,
    ... )
    >>>
    >>> # Get supported versions
    >>> matrix = get_version_matrix()
    >>> for version in matrix.get_lts_versions():
    ...     print(f"{version.version}: {version.docker_image}")
    >>>
    >>> # Get API differences
    >>> differences = matrix.get_differences_between("5.60", "5.76")
    >>> for diff in differences:
    ...     print(diff.format_message())

Drift Detection Usage:
    >>> from tests.compat.drift_detector import DriftDetector, DriftMode
    >>> from tests.compat.schema_validator import SchemaCache
    >>>
    >>> cache = SchemaCache()
    >>> detector = DriftDetector(cache, mode=DriftMode.BREAKING)
    >>> report = detector.check_all_cached()
    >>> if report.has_breaking_changes:
    ...     print(report.format_changelog())

Pytest Markers for Version Testing:
    @pytest.mark.min_version(version) - Skip if CiviCRM version is below
    @pytest.mark.max_version(version) - Skip if CiviCRM version is above
    @pytest.mark.skip_version(version) - Skip for specific version(s)

Pytest Markers for Drift Detection:
    @pytest.mark.detect_drift - Report drift but don't fail
    @pytest.mark.detect_drift_strict - Fail on any schema change
    @pytest.mark.detect_drift_breaking - Fail only on breaking changes
"""

from __future__ import annotations
