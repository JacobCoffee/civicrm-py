"""Pytest fixtures for cassette-based testing.

This module provides fixtures for VCR/cassette-style HTTP recording and replay.
Use these fixtures to test against recorded CiviCRM API responses.

Fixtures:
    cassette_manager: CassetteManager configured for the current test session
    cassette_mode: Current cassette mode (record, replay, auto)
    cassette_version: Target CiviCRM version for cassette storage
    use_cassette: Context manager fixture for cassette-based testing
    cassette_client: CiviClient configured to use cassettes

Markers:
    @pytest.mark.cassette(name): Use a specific cassette for this test
    @pytest.mark.record: Force recording mode for this test
    @pytest.mark.replay: Force replay mode for this test

Environment Variables:
    CIVI_CASSETTE_MODE: Override cassette mode (record, replay, auto, none)
    CIVI_VERSION: CiviCRM version for cassette storage (default: "default")
    CI: If set, automatically uses replay mode

Usage:
    @pytest.mark.cassette("Contact_get")
    async def test_contact_get(cassette_client):
        contacts = await cassette_client.api("Contact", "get")
        assert len(contacts.values) > 0

    # Or use the context manager directly
    async def test_custom_cassette(use_cassette, civi_client):
        with use_cassette("MyCustom_cassette"):
            result = await civi_client.api("Contact", "get")
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.compat.cassettes import (
    Cassette,
    CassetteManager,
    CassetteMode,
    CassetteStore,
    HTTPInteraction,
    HTTPRequest,
    HTTPResponse,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    import respx

    from civi_py import CiviClient, CiviSettings


# -----------------------------------------------------------------------------
# Configuration Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cassette_dir() -> Path:
    """Get the cassette storage directory.

    Returns:
        Path to tests/cassettes directory.
    """
    return Path(__file__).parent.parent / "cassettes"


@pytest.fixture(scope="session")
def cassette_version() -> str:
    """Get the CiviCRM version for cassette storage.

    Reads from CIVI_VERSION environment variable, defaults to "default".

    Returns:
        CiviCRM version string.
    """
    return os.environ.get("CIVI_VERSION", "default")


@pytest.fixture(scope="session")
def cassette_mode_env() -> CassetteMode:
    """Get the cassette mode from environment.

    Reads from CIVI_CASSETTE_MODE environment variable.
    Defaults to REPLAY in CI, AUTO otherwise.

    Returns:
        CassetteMode enum value.
    """
    mode_str = os.environ.get("CIVI_CASSETTE_MODE", "").lower()

    if mode_str:
        try:
            return CassetteMode(mode_str)
        except ValueError:
            pass

    # Default to replay in CI
    if os.environ.get("CI"):
        return CassetteMode.REPLAY

    return CassetteMode.AUTO


@pytest.fixture
def cassette_mode(request: pytest.FixtureRequest, cassette_mode_env: CassetteMode) -> CassetteMode:
    """Get the cassette mode for current test.

    Checks for @pytest.mark.record or @pytest.mark.replay markers
    to override the session-level mode.

    Args:
        request: Pytest request fixture.
        cassette_mode_env: Session-level mode from environment.

    Returns:
        CassetteMode for this test.
    """
    # Check for test-level markers
    if request.node.get_closest_marker("record"):
        return CassetteMode.RECORD
    if request.node.get_closest_marker("replay"):
        return CassetteMode.REPLAY

    return cassette_mode_env


# -----------------------------------------------------------------------------
# Manager Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cassette_store(cassette_dir: Path, cassette_version: str) -> CassetteStore:
    """Get a CassetteStore instance for the session.

    Args:
        cassette_dir: Base cassette directory.
        cassette_version: CiviCRM version.

    Returns:
        Configured CassetteStore.
    """
    return CassetteStore(cassette_dir, cassette_version)


@pytest.fixture
def cassette_manager(
    cassette_dir: Path,
    cassette_version: str,
    cassette_mode: CassetteMode,
    civi_settings: CiviSettings,
) -> CassetteManager:
    """Get a CassetteManager instance for the current test.

    Args:
        cassette_dir: Base cassette directory.
        cassette_version: CiviCRM version.
        cassette_mode: Current mode.
        civi_settings: CiviCRM settings for base URL.

    Returns:
        Configured CassetteManager.
    """
    return CassetteManager(
        cassette_dir=cassette_dir,
        civicrm_version=cassette_version,
        mode=cassette_mode,
        base_url=civi_settings.base_url,
    )


# -----------------------------------------------------------------------------
# Cassette Context Manager Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def use_cassette(
    cassette_manager: CassetteManager,
    respx_mock: respx.MockRouter,
) -> Generator[Any, None, None]:
    """Context manager fixture for using cassettes.

    Args:
        cassette_manager: Cassette manager instance.
        respx_mock: respx mock router.

    Yields:
        Context manager function.

    Example:
        def test_something(use_cassette):
            with use_cassette("Contact_get") as cassette:
                # Run test code
                ...
    """

    @contextmanager
    def _use_cassette(
        name: str,
        mode: CassetteMode | None = None,
    ) -> Generator[Cassette, None, None]:
        """Use a cassette for HTTP mocking.

        Args:
            name: Cassette name.
            mode: Override mode for this cassette.

        Yields:
            The cassette being used.
        """
        # Override mode if specified
        original_mode = cassette_manager.mode
        if mode is not None:
            cassette_manager.mode = mode

        try:
            cassette = cassette_manager.load_or_create(name)

            # Configure mock router if we have interactions to replay
            if cassette.interactions:
                cassette_manager.configure_mock(respx_mock, cassette)

            yield cassette

            # Save recording if needed
            if cassette_manager.is_recording():
                cassette_manager.save_current()

        finally:
            cassette_manager.mode = original_mode

    return _use_cassette


# -----------------------------------------------------------------------------
# Auto-cassette Fixtures (via markers)
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_cassette(
    request: pytest.FixtureRequest,
    cassette_manager: CassetteManager,
    respx_mock: respx.MockRouter,
) -> Generator[Cassette | None, None, None]:
    """Automatically load cassette if @pytest.mark.cassette is present.

    This fixture checks for the @pytest.mark.cassette(name) marker
    and automatically sets up the cassette for the test.

    Args:
        request: Pytest request fixture.
        cassette_manager: Cassette manager.
        respx_mock: respx mock router.

    Yields:
        Cassette if marker present, None otherwise.
    """
    marker = request.node.get_closest_marker("cassette")

    if marker is None:
        yield None
        return

    # Get cassette name from marker
    if marker.args:
        name = marker.args[0]
    elif "name" in marker.kwargs:
        name = marker.kwargs["name"]
    else:
        # Default to test function name
        name = request.node.name

    # Load or create cassette
    cassette = cassette_manager.load_or_create(name)

    # Configure mock if replaying
    if cassette.interactions:
        cassette_manager.configure_mock(respx_mock, cassette)

    yield cassette

    # Save if recording
    if cassette_manager.is_recording():
        cassette_manager.save_current()


# -----------------------------------------------------------------------------
# Client Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
async def cassette_client(
    civi_settings: CiviSettings,
    auto_cassette: Cassette | None,
) -> Generator[CiviClient, None, None]:
    """CiviClient configured for cassette-based testing.

    This client is set up with respx mocking and will use
    cassettes when the @pytest.mark.cassette marker is present.

    Args:
        civi_settings: CiviCRM settings.
        auto_cassette: Auto-loaded cassette (if marker present).

    Yields:
        Configured CiviClient.
    """
    from civi_py import CiviClient

    async with CiviClient(settings=civi_settings) as client:
        yield client


# -----------------------------------------------------------------------------
# Recording Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def record_interaction() -> Any:
    """Fixture for manually recording HTTP interactions.

    Returns a function that creates HTTPInteraction objects
    for adding to cassettes manually.

    Returns:
        Function to create HTTPInteraction.

    Example:
        def test_manual_recording(record_interaction, cassette_manager):
            cassette = Cassette(name="manual_test")

            interaction = record_interaction(
                method="POST",
                url="https://example.org/api/Contact/get",
                status_code=200,
                response_body={"values": [], "count": 0},
            )
            cassette.add_interaction(interaction)
    """

    def _record_interaction(
        method: str,
        url: str,
        status_code: int = 200,
        request_body: dict[str, Any] | str | None = None,
        response_body: dict[str, Any] | str | None = None,
        request_headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> HTTPInteraction:
        """Create an HTTP interaction for recording.

        Args:
            method: HTTP method.
            url: Request URL.
            status_code: Response status code.
            request_body: Request body.
            response_body: Response body.
            request_headers: Request headers.
            response_headers: Response headers.

        Returns:
            HTTPInteraction ready for cassette.
        """
        request = HTTPRequest(
            method=method,
            url=url,
            headers=request_headers or {},
            body=request_body,
        )
        response = HTTPResponse(
            status_code=status_code,
            headers=response_headers or {},
            body=response_body,
        )
        return HTTPInteraction(request=request, response=response)

    return _record_interaction


# -----------------------------------------------------------------------------
# Helper Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_cassette() -> Cassette:
    """Create a sample cassette for testing.

    Returns:
        Cassette with sample Contact data.
    """
    cassette = Cassette(
        name="sample_test",
        version="5.74",
        metadata={"description": "Sample cassette for testing"},
    )

    # Add sample Contact get interaction
    request = HTTPRequest(
        method="POST",
        url="https://example.org/civicrm/ajax/api4/Contact/get",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body={"params": '{"select": ["id", "display_name"]}'},
    )
    response = HTTPResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body={
            "values": [
                {"id": 1, "display_name": "Test Contact"},
                {"id": 2, "display_name": "Another Contact"},
            ],
            "count": 2,
            "countFetched": 2,
        },
    )
    cassette.add_interaction(HTTPInteraction(request=request, response=response))

    return cassette


@pytest.fixture
def empty_cassette() -> Cassette:
    """Create an empty cassette for testing.

    Returns:
        Empty Cassette.
    """
    return Cassette(name="empty_test", version="5.74")


# -----------------------------------------------------------------------------
# Schema Validation Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def schema_cache_dir(tmp_path: Path) -> Path:
    """Temporary directory for schema cache."""
    cache_dir = tmp_path / "schemas"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def schema_cache(schema_cache_dir: Path) -> Any:
    """SchemaCache instance with temporary directory."""
    from tests.compat.schema_validator import SchemaCache

    return SchemaCache(cache_dir=schema_cache_dir)


@pytest.fixture
def production_schema_cache() -> Any:
    """SchemaCache using actual production schemas directory."""
    from tests.compat.schema_validator import SchemaCache

    return SchemaCache()


@pytest.fixture
def schema_validator(schema_cache: Any) -> Any:
    """SchemaValidator with temporary cache."""
    from tests.compat.schema_validator import SchemaValidator

    return SchemaValidator(cache=schema_cache)


@pytest.fixture
def strict_schema_validator(schema_cache: Any) -> Any:
    """SchemaValidator in strict mode (warnings are errors)."""
    from tests.compat.schema_validator import SchemaValidator

    return SchemaValidator(cache=schema_cache, strict=True)


@pytest.fixture
def full_schema_validator(schema_cache: Any) -> Any:
    """SchemaValidator that reports all mismatches including extra API fields."""
    from tests.compat.schema_validator import SchemaValidator

    return SchemaValidator(
        cache=schema_cache,
        ignore_extra_api_fields=False,
    )


# -----------------------------------------------------------------------------
# Sample API Field Definition Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_string_field() -> dict[str, Any]:
    """Sample string field definition."""
    return {
        "name": "first_name",
        "title": "First Name",
        "description": "First Name.",
        "data_type": "String",
        "input_type": "Text",
        "required": False,
        "readonly": False,
        "serialize": None,
        "fk_entity": None,
        "options": None,
        "default_value": None,
    }


@pytest.fixture
def sample_integer_field() -> dict[str, Any]:
    """Sample integer field definition."""
    return {
        "name": "id",
        "title": "Contact ID",
        "description": "Unique Contact ID",
        "data_type": "Integer",
        "input_type": "Number",
        "required": False,
        "readonly": True,
        "serialize": None,
        "fk_entity": None,
        "options": None,
        "default_value": None,
    }


@pytest.fixture
def sample_boolean_field() -> dict[str, Any]:
    """Sample boolean field definition."""
    return {
        "name": "is_deleted",
        "title": "Contact is in Trash",
        "description": "",
        "data_type": "Boolean",
        "input_type": "CheckBox",
        "required": False,
        "readonly": False,
        "serialize": None,
        "fk_entity": None,
        "options": None,
        "default_value": "0",
    }


@pytest.fixture
def sample_required_field() -> dict[str, Any]:
    """Sample required field definition."""
    return {
        "name": "contact_type",
        "title": "Contact Type",
        "description": "Type of Contact.",
        "data_type": "String",
        "input_type": "Select",
        "required": True,
        "readonly": False,
        "serialize": None,
        "fk_entity": None,
        "options": {
            "Individual": "Individual",
            "Household": "Household",
            "Organization": "Organization",
        },
        "default_value": None,
    }


@pytest.fixture
def sample_fk_field() -> dict[str, Any]:
    """Sample foreign key field definition."""
    return {
        "name": "employer_id",
        "title": "Current Employer ID",
        "description": "FK to Contact ID",
        "data_type": "Integer",
        "input_type": "EntityRef",
        "required": False,
        "readonly": False,
        "serialize": None,
        "fk_entity": "Contact",
        "options": None,
        "default_value": None,
    }


@pytest.fixture
def sample_array_field() -> dict[str, Any]:
    """Sample array field definition."""
    return {
        "name": "target_contact_id",
        "title": "Activity Targets",
        "description": "Contact IDs of the target contacts for this activity.",
        "data_type": "Array",
        "input_type": "EntityRef",
        "required": False,
        "readonly": False,
        "serialize": None,
        "fk_entity": "Contact",
        "options": None,
        "default_value": None,
    }


@pytest.fixture
def sample_date_field() -> dict[str, Any]:
    """Sample date field definition."""
    return {
        "name": "birth_date",
        "title": "Birth Date",
        "description": "Date of birth",
        "data_type": "Date",
        "input_type": "Date",
        "required": False,
        "readonly": False,
        "serialize": None,
        "fk_entity": None,
        "options": None,
        "default_value": None,
    }


@pytest.fixture
def sample_timestamp_field() -> dict[str, Any]:
    """Sample timestamp field definition."""
    return {
        "name": "created_date",
        "title": "Created Date",
        "description": "When was the contact was created.",
        "data_type": "Timestamp",
        "input_type": "Date",
        "required": False,
        "readonly": True,
        "serialize": None,
        "fk_entity": None,
        "options": None,
        "default_value": None,
    }


# -----------------------------------------------------------------------------
# Complete Schema Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def minimal_contact_schema() -> list[dict[str, Any]]:
    """Minimal Contact schema for basic testing."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "display_name", "data_type": "String", "required": False},
        {"name": "first_name", "data_type": "String", "required": False},
        {"name": "last_name", "data_type": "String", "required": False},
        {"name": "contact_type", "data_type": "String", "required": True},
        {"name": "is_deleted", "data_type": "Boolean", "required": False},
    ]


@pytest.fixture
def minimal_activity_schema() -> list[dict[str, Any]]:
    """Minimal Activity schema for basic testing."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "activity_type_id", "data_type": "Integer", "required": True},
        {"name": "subject", "data_type": "String", "required": False},
        {"name": "details", "data_type": "Memo", "required": False},
        {"name": "activity_date_time", "data_type": "Datetime", "required": False},
        {"name": "source_contact_id", "data_type": "Integer", "required": False},
        {"name": "is_deleted", "data_type": "Boolean", "required": False},
    ]


@pytest.fixture
def schema_with_type_mismatch() -> list[dict[str, Any]]:
    """Schema with intentional type mismatch for testing."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "name", "data_type": "Integer", "required": False},  # Wrong type
    ]


@pytest.fixture
def schema_with_extra_field() -> list[dict[str, Any]]:
    """Schema with extra field not in model."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "display_name", "data_type": "String", "required": False},
        {"name": "api_only_field", "data_type": "String", "required": False},
    ]


# -----------------------------------------------------------------------------
# Production Schema Loaders
# -----------------------------------------------------------------------------


@pytest.fixture
def contact_schema(production_schema_cache: Any) -> list[dict[str, Any]] | None:
    """Load Contact schema from production cache."""
    return production_schema_cache.load_schema("Contact")


@pytest.fixture
def activity_schema(production_schema_cache: Any) -> list[dict[str, Any]] | None:
    """Load Activity schema from production cache."""
    return production_schema_cache.load_schema("Activity")


# -----------------------------------------------------------------------------
# Entity Class Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def contact_entity_class() -> type:
    """Get Contact entity class."""
    from civi_py.entities import Contact

    return Contact


@pytest.fixture
def activity_entity_class() -> type:
    """Get Activity entity class."""
    from civi_py.entities import Activity

    return Activity


@pytest.fixture
def all_entity_classes() -> dict[str, type]:
    """Get all registered entity classes."""
    from civi_py.entities import (
        Activity,
        Address,
        Contact,
        Contribution,
        Email,
        Event,
        Group,
        Membership,
        Note,
        Participant,
        Phone,
        Tag,
    )

    return {
        "Contact": Contact,
        "Activity": Activity,
        "Address": Address,
        "Email": Email,
        "Phone": Phone,
        "Contribution": Contribution,
        "Event": Event,
        "Membership": Membership,
        "Participant": Participant,
        "Group": Group,
        "Tag": Tag,
        "Note": Note,
    }


# -----------------------------------------------------------------------------
# Validation Result Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_validation_result() -> Any:
    """Sample successful validation result."""
    from tests.compat.schema_validator import ValidationResult

    return ValidationResult(
        entity_name="Contact",
        is_valid=True,
        errors=[],
        warnings=[],
        info=[],
        api_field_count=40,
        model_field_count=38,
    )


@pytest.fixture
def sample_failed_validation_result() -> Any:
    """Sample failed validation result with errors."""
    from tests.compat.schema_validator import (
        FieldMismatch,
        MismatchSeverity,
        MismatchType,
        ValidationResult,
    )

    return ValidationResult(
        entity_name="TestEntity",
        is_valid=False,
        errors=[
            FieldMismatch(
                field_name="bad_field",
                mismatch_type=MismatchType.TYPE_MISMATCH,
                severity=MismatchSeverity.ERROR,
                message="Type mismatch: API expects Integer, model has str",
                api_value="Integer",
                model_value="str",
            ),
        ],
        warnings=[],
        info=[],
        api_field_count=10,
        model_field_count=10,
    )


@pytest.fixture
def sample_validation_report(sample_validation_result: Any) -> Any:
    """Sample validation report with one result."""
    from tests.compat.schema_validator import ValidationReport

    report = ValidationReport()
    report.add_result(sample_validation_result)
    return report


# -----------------------------------------------------------------------------
# Field Coverage Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def field_coverage_validator(schema_cache: Any) -> Any:
    """FieldCoverageValidator with temporary cache."""
    from tests.compat.field_coverage import FieldCoverageValidator

    return FieldCoverageValidator(cache=schema_cache)


@pytest.fixture
def production_field_coverage_validator(production_schema_cache: Any) -> Any:
    """FieldCoverageValidator using production schemas."""
    from tests.compat.field_coverage import FieldCoverageValidator

    return FieldCoverageValidator(cache=production_schema_cache)


@pytest.fixture
def sample_field_info() -> Any:
    """Sample FieldInfo for testing."""
    from tests.compat.field_coverage import FieldInfo, FieldStatus

    return FieldInfo(
        name="test_field",
        status=FieldStatus.COVERED,
        api_type="String",
        model_type="str",
        is_required_api=False,
        is_required_model=False,
    )


@pytest.fixture
def sample_missing_field_info() -> Any:
    """Sample FieldInfo for a missing field."""
    from tests.compat.field_coverage import FieldInfo, FieldStatus

    return FieldInfo(
        name="missing_field",
        status=FieldStatus.MISSING,
        api_type="String",
        model_type=None,
        is_required_api=True,
        is_required_model=False,
        notes="Field not defined in model",
    )


@pytest.fixture
def sample_type_mismatch_field_info() -> Any:
    """Sample FieldInfo with type mismatch."""
    from tests.compat.field_coverage import FieldInfo, FieldStatus

    return FieldInfo(
        name="mismatched_field",
        status=FieldStatus.TYPE_MISMATCH,
        api_type="Integer",
        model_type="str",
        is_required_api=False,
        is_required_model=False,
        notes="Expected (int,)",
    )


@pytest.fixture
def sample_deprecated_field_info() -> Any:
    """Sample DeprecatedFieldInfo for testing."""
    from tests.compat.field_coverage import DeprecatedFieldInfo

    return DeprecatedFieldInfo(
        name="old_field",
        deprecation_message="This field is deprecated. Use new_field instead.",
        replacement="new_field",
        removal_version="6.0",
        in_model=True,
        recommendation="Remove old_field from model and use new_field",
    )


@pytest.fixture
def sample_field_coverage_report() -> Any:
    """Sample FieldCoverageReport for testing."""
    from tests.compat.field_coverage import (
        DeprecatedFieldInfo,
        FieldCoverageReport,
        FieldInfo,
        FieldStatus,
    )

    return FieldCoverageReport(
        entity_name="TestEntity",
        api_field_count=10,
        model_field_count=8,
        covered_fields=7,
        missing_fields=3,
        extra_fields=1,
        type_mismatches=1,
        required_total=2,
        required_covered=2,
        deprecated_fields=[
            DeprecatedFieldInfo(name="old_field", in_model=True),
        ],
        field_details=[
            FieldInfo(name="id", status=FieldStatus.COVERED),
            FieldInfo(name="name", status=FieldStatus.COVERED),
            FieldInfo(name="missing", status=FieldStatus.MISSING),
            FieldInfo(name="extra", status=FieldStatus.EXTRA),
            FieldInfo(name="bad_type", status=FieldStatus.TYPE_MISMATCH),
        ],
    )


@pytest.fixture
def sample_full_coverage_report() -> Any:
    """Sample FieldCoverageReport with 100% coverage."""
    from tests.compat.field_coverage import (
        FieldCoverageReport,
        FieldInfo,
        FieldStatus,
    )

    return FieldCoverageReport(
        entity_name="FullCoverageEntity",
        api_field_count=5,
        model_field_count=5,
        covered_fields=5,
        missing_fields=0,
        extra_fields=0,
        type_mismatches=0,
        required_total=2,
        required_covered=2,
        deprecated_fields=[],
        field_details=[
            FieldInfo(name="id", status=FieldStatus.COVERED),
            FieldInfo(name="name", status=FieldStatus.COVERED),
            FieldInfo(name="description", status=FieldStatus.COVERED),
            FieldInfo(name="is_active", status=FieldStatus.COVERED),
            FieldInfo(name="created_at", status=FieldStatus.COVERED),
        ],
    )


@pytest.fixture
def sample_field_coverage_summary(
    sample_field_coverage_report: Any,
    sample_full_coverage_report: Any,
) -> Any:
    """Sample FieldCoverageSummary with multiple reports."""
    from tests.compat.field_coverage import FieldCoverageSummary

    summary = FieldCoverageSummary()
    summary.add_report(sample_field_coverage_report)
    summary.add_report(sample_full_coverage_report)
    return summary


# -----------------------------------------------------------------------------
# Extended Schema Fixtures for Field Coverage Testing
# -----------------------------------------------------------------------------


@pytest.fixture
def schema_with_deprecated_field() -> list[dict[str, Any]]:
    """Schema with a deprecated field."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "name", "data_type": "String", "required": False},
        {
            "name": "old_name",
            "data_type": "String",
            "required": False,
            "deprecated": True,
            "deprecation_message": "Use name instead",
            "replacement": "name",
        },
    ]


@pytest.fixture
def schema_with_all_types() -> list[dict[str, Any]]:
    """Schema with all common CiviCRM data types."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "name", "data_type": "String", "required": True},
        {"name": "description", "data_type": "Text", "required": False},
        {"name": "notes", "data_type": "Memo", "required": False},
        {"name": "is_active", "data_type": "Boolean", "required": False},
        {"name": "amount", "data_type": "Float", "required": False},
        {"name": "price", "data_type": "Money", "required": False},
        {"name": "birth_date", "data_type": "Date", "required": False},
        {"name": "created_at", "data_type": "Datetime", "required": False},
        {"name": "last_modified", "data_type": "Timestamp", "required": False},
        {"name": "tags", "data_type": "Array", "required": False},
        {"name": "metadata", "data_type": "Object", "required": False},
        {"name": "config", "data_type": "Json", "required": False},
    ]


@pytest.fixture
def schema_with_fk_fields() -> list[dict[str, Any]]:
    """Schema with foreign key fields."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {
            "name": "contact_id",
            "data_type": "Integer",
            "required": True,
            "fk_entity": "Contact",
        },
        {
            "name": "activity_id",
            "data_type": "Integer",
            "required": False,
            "fk_entity": "Activity",
        },
        {
            "name": "campaign_id",
            "data_type": "Integer",
            "required": False,
            "fk_entity": "Campaign",
        },
    ]


@pytest.fixture
def comprehensive_contact_schema() -> list[dict[str, Any]]:
    """Comprehensive Contact schema with many field types."""
    return [
        {
            "name": "id",
            "title": "Contact ID",
            "data_type": "Integer",
            "required": False,
            "readonly": True,
        },
        {
            "name": "contact_type",
            "title": "Contact Type",
            "data_type": "String",
            "required": True,
            "readonly": False,
        },
        {
            "name": "display_name",
            "title": "Display Name",
            "data_type": "String",
            "required": False,
            "readonly": True,
        },
        {
            "name": "first_name",
            "title": "First Name",
            "data_type": "String",
            "required": False,
            "readonly": False,
        },
        {
            "name": "last_name",
            "title": "Last Name",
            "data_type": "String",
            "required": False,
            "readonly": False,
        },
        {
            "name": "birth_date",
            "title": "Birth Date",
            "data_type": "Date",
            "required": False,
            "readonly": False,
        },
        {
            "name": "is_deleted",
            "title": "Is Deleted",
            "data_type": "Boolean",
            "required": False,
            "readonly": False,
        },
        {
            "name": "contact_sub_type",
            "title": "Contact Sub Type",
            "data_type": "Array",
            "required": False,
            "readonly": False,
        },
        {
            "name": "employer_id",
            "title": "Employer ID",
            "data_type": "Integer",
            "required": False,
            "readonly": False,
            "fk_entity": "Contact",
        },
        {
            "name": "created_date",
            "title": "Created Date",
            "data_type": "Timestamp",
            "required": False,
            "readonly": True,
        },
    ]


# -----------------------------------------------------------------------------
# Drift Detection Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def drift_snapshot_dir(tmp_path: Path) -> Path:
    """Temporary directory for drift detection snapshots."""
    snapshot_path = tmp_path / "snapshots"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    return snapshot_path


@pytest.fixture
def production_snapshot_dir() -> Path:
    """Production snapshot directory."""
    return Path(__file__).parent / "schemas" / "snapshots"


@pytest.fixture
def schema_differ() -> Any:
    """SchemaDiffer instance for comparing schemas."""
    from tests.compat.drift_detector import SchemaDiffer

    return SchemaDiffer()


@pytest.fixture
def schema_differ_with_descriptions() -> Any:
    """SchemaDiffer that also detects description changes."""
    from tests.compat.drift_detector import SchemaDiffer

    return SchemaDiffer(detect_description_changes=True)


@pytest.fixture
def drift_detector(schema_cache: Any, drift_snapshot_dir: Path) -> Any:
    """DriftDetector with temporary directories."""
    from tests.compat.drift_detector import DriftDetector, DriftMode

    return DriftDetector(
        cache=schema_cache,
        mode=DriftMode.REPORT,
        snapshot_dir=drift_snapshot_dir,
    )


@pytest.fixture
def strict_drift_detector(schema_cache: Any, drift_snapshot_dir: Path) -> Any:
    """DriftDetector in strict mode (fail on any change)."""
    from tests.compat.drift_detector import DriftDetector, DriftMode

    return DriftDetector(
        cache=schema_cache,
        mode=DriftMode.STRICT,
        snapshot_dir=drift_snapshot_dir,
    )


@pytest.fixture
def breaking_drift_detector(schema_cache: Any, drift_snapshot_dir: Path) -> Any:
    """DriftDetector in breaking mode (fail only on breaking changes)."""
    from tests.compat.drift_detector import DriftDetector, DriftMode

    return DriftDetector(
        cache=schema_cache,
        mode=DriftMode.BREAKING,
        snapshot_dir=drift_snapshot_dir,
    )


@pytest.fixture
def production_drift_detector(production_schema_cache: Any, production_snapshot_dir: Path) -> Any:
    """DriftDetector using production schema cache."""
    from tests.compat.drift_detector import DriftDetector, DriftMode

    return DriftDetector(
        cache=production_schema_cache,
        mode=DriftMode.REPORT,
        snapshot_dir=production_snapshot_dir,
    )


# -----------------------------------------------------------------------------
# Drift Detection Markers
# -----------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for drift detection and version testing."""
    # Drift detection markers
    config.addinivalue_line(
        "markers",
        "detect_drift: automatically check for schema drift in this test",
    )
    config.addinivalue_line(
        "markers",
        "detect_drift_strict: fail test on any schema change",
    )
    config.addinivalue_line(
        "markers",
        "detect_drift_breaking: fail test only on breaking schema changes",
    )

    # Version-specific markers
    config.addinivalue_line(
        "markers",
        'min_version(version): skip test if CiviCRM version < specified (e.g., @pytest.mark.min_version("5.70"))',
    )
    config.addinivalue_line(
        "markers",
        'max_version(version): skip test if CiviCRM version >= specified (e.g., @pytest.mark.max_version("5.80"))',
    )
    config.addinivalue_line(
        "markers",
        'version_specific(version): only run test on specific CiviCRM version (e.g., @pytest.mark.version_specific("5.70"))',
    )
    config.addinivalue_line(
        "markers",
        "version_range(min, max): run test only within version range",
    )
    config.addinivalue_line(
        "markers",
        'requires_feature(feature): skip test if feature not available in current version (e.g., @pytest.mark.requires_feature("batch_action_support"))',
    )


# -----------------------------------------------------------------------------
# Version-Aware Test Skipping
# -----------------------------------------------------------------------------


def _skip_if_needed(skip_reason: str | None) -> None:
    """Skip test if skip_reason is provided."""
    if skip_reason:
        pytest.skip(skip_reason)


def _check_min_version(marker: Any, current_version: Any) -> None:
    """Check min_version marker."""
    from tests.compat.version_utils import skip_reason_for_version

    min_ver = marker.args[0] if marker.args else None
    if min_ver:
        _skip_if_needed(skip_reason_for_version(current_version, min_version=min_ver))


def _check_max_version(marker: Any, current_version: Any) -> None:
    """Check max_version marker."""
    from tests.compat.version_utils import skip_reason_for_version

    max_ver = marker.args[0] if marker.args else None
    if max_ver:
        _skip_if_needed(skip_reason_for_version(current_version, max_version=max_ver))


def _check_exact_version(marker: Any, current_version: Any) -> None:
    """Check version_specific marker."""
    from tests.compat.version_utils import skip_reason_for_version

    exact_ver = marker.args[0] if marker.args else None
    if exact_ver:
        _skip_if_needed(skip_reason_for_version(current_version, exact_version=exact_ver))


def _check_version_range(marker: Any, current_version: Any) -> None:
    """Check version_range marker."""
    from tests.compat.version_utils import skip_reason_for_version

    min_ver = marker.args[0] if len(marker.args) > 0 else None
    max_ver = marker.args[1] if len(marker.args) > 1 else None
    _skip_if_needed(
        skip_reason_for_version(
            current_version,
            min_version=min_ver,
            max_version=max_ver,
        )
    )


# Mapping of marker names to their handler functions
_VERSION_MARKER_HANDLERS: dict[str, Any] = {
    "min_version": _check_min_version,
    "max_version": _check_max_version,
    "version_specific": _check_exact_version,
    "version_range": _check_version_range,
}


def _check_version_marker(
    item: pytest.Item,
    marker_name: str,
    current_version: Any,
) -> None:
    """Check a version marker and skip if needed.

    Args:
        item: Pytest test item.
        marker_name: Name of the marker to check.
        current_version: Current CiviVersion.
    """
    marker = item.get_closest_marker(marker_name)
    if not marker:
        return

    handler = _VERSION_MARKER_HANDLERS.get(marker_name)
    if handler:
        handler(marker, current_version)


def _check_feature_marker(item: pytest.Item, current_version: Any) -> None:
    """Check requires_feature marker and skip if needed.

    Args:
        item: Pytest test item.
        current_version: Current CiviVersion.
    """
    from tests.compat.version_utils import get_version_features

    marker = item.get_closest_marker("requires_feature")
    if not marker:
        return

    feature_name = marker.args[0] if marker.args else None
    if feature_name:
        features = get_version_features(current_version)
        if not features.get(feature_name, False):
            pytest.skip(
                f"Feature '{feature_name}' not available in CiviCRM {current_version}",
            )


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Handle version-based test skipping before test execution.

    This hook runs before each test and checks for version markers:
        - @pytest.mark.min_version("5.70"): Skip if current < 5.70
        - @pytest.mark.max_version("5.80"): Skip if current >= 5.80
        - @pytest.mark.version_specific("5.70"): Skip if current != 5.70
        - @pytest.mark.version_range("5.60", "5.80"): Skip if outside range
        - @pytest.mark.requires_feature("feature_name"): Skip if feature unavailable

    Args:
        item: Pytest test item being set up.
    """
    from tests.compat.version_utils import CiviVersion

    # Get current version from environment
    current_version = CiviVersion.from_env()

    # Check version markers
    for marker_name in ["min_version", "max_version", "version_specific", "version_range"]:
        _check_version_marker(item, marker_name, current_version)

    # Check feature marker
    _check_feature_marker(item, current_version)


# -----------------------------------------------------------------------------
# Version-Aware Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def civicrm_version() -> Any:
    """Get the current CiviCRM version being tested.

    Reads from CIVI_VERSION environment variable.

    Returns:
        CiviVersion instance for the current test session.
    """
    from tests.compat.version_utils import CiviVersion

    return CiviVersion.from_env()


@pytest.fixture(scope="session")
def version_features(civicrm_version: Any) -> dict[str, bool]:
    """Get feature flags for the current CiviCRM version.

    Args:
        civicrm_version: Current CiviVersion from fixture.

    Returns:
        Dictionary of feature name to availability boolean.
    """
    from tests.compat.version_utils import get_version_features

    return get_version_features(civicrm_version)


@pytest.fixture(scope="session")
def supported_versions() -> list[Any]:
    """Get list of all supported CiviCRM versions for testing.

    Returns:
        List of CiviVersion objects for supported versions.
    """
    from tests.compat.version_utils import get_supported_versions

    return get_supported_versions()


@pytest.fixture
def version_cassette_dir(cassette_dir: Path, civicrm_version: Any) -> Path:
    """Get version-specific cassette directory.

    Args:
        cassette_dir: Base cassette directory.
        civicrm_version: Current CiviVersion.

    Returns:
        Path to version-specific cassette directory.
    """
    version_dir = cassette_dir / civicrm_version.to_cassette_dir()
    version_dir.mkdir(parents=True, exist_ok=True)
    return version_dir


@pytest.fixture
def version_cassette_store(
    cassette_dir: Path,
    civicrm_version: Any,
) -> CassetteStore:
    """Get version-specific CassetteStore.

    Args:
        cassette_dir: Base cassette directory.
        civicrm_version: Current CiviVersion.

    Returns:
        CassetteStore configured for current version.
    """
    return CassetteStore(cassette_dir, str(civicrm_version))


@pytest.fixture
def version_compatibility_result(civicrm_version: Any) -> Any:
    """Get compatibility check result for current version.

    Args:
        civicrm_version: Current CiviVersion.

    Returns:
        VersionCompatibilityResult for current version.
    """
    from tests.compat.version_utils import check_version_compatibility

    return check_version_compatibility(civicrm_version)


# -----------------------------------------------------------------------------
# Drift Detection Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def auto_drift_detection(
    request: pytest.FixtureRequest,
    production_drift_detector: Any,
) -> Generator[Any, None, None]:
    """Automatically detect drift if @pytest.mark.detect_drift is present.

    This fixture checks for drift detection markers and runs the appropriate
    checks after the test completes.

    Markers:
        @pytest.mark.detect_drift: Report drift but don't fail
        @pytest.mark.detect_drift_strict: Fail on any change
        @pytest.mark.detect_drift_breaking: Fail on breaking changes only

    Args:
        request: Pytest request fixture.
        production_drift_detector: Production drift detector.

    Yields:
        None (fixture runs after test).
    """
    from tests.compat.drift_detector import DriftMode

    # Determine mode from markers
    mode = None
    if request.node.get_closest_marker("detect_drift_strict"):
        mode = DriftMode.STRICT
    elif request.node.get_closest_marker("detect_drift_breaking"):
        mode = DriftMode.BREAKING
    elif request.node.get_closest_marker("detect_drift"):
        mode = DriftMode.REPORT

    if mode is None:
        yield None
        return

    # Run test first
    yield None

    # After test, check for drift
    production_drift_detector.mode = mode
    report = production_drift_detector.check_all_cached()

    if report.has_changes:
        summary = report.format_summary()
        print(f"\n{summary}")

        if report.should_fail():
            pytest.fail(f"Schema drift detected in {mode.value} mode:\n{summary}")


# -----------------------------------------------------------------------------
# Sample Drift Data Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_schema_snapshot() -> Any:
    """Sample SchemaSnapshot for testing."""
    from tests.compat.drift_detector import SchemaSnapshot

    return SchemaSnapshot(
        entity_name="Contact",
        fields=[
            {"name": "id", "data_type": "Integer", "required": False},
            {"name": "display_name", "data_type": "String", "required": False},
            {"name": "first_name", "data_type": "String", "required": False},
        ],
        version="5.74",
        civicrm_version="5.74",
    )


@pytest.fixture
def sample_old_schema_fields() -> list[dict[str, Any]]:
    """Sample old schema fields for drift testing."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "display_name", "data_type": "String", "required": False},
        {"name": "first_name", "data_type": "String", "required": False},
        {"name": "removed_field", "data_type": "String", "required": False},
    ]


@pytest.fixture
def sample_new_schema_fields() -> list[dict[str, Any]]:
    """Sample new schema fields with changes for drift testing."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "display_name", "data_type": "String", "required": False},
        {"name": "first_name", "data_type": "String", "required": True},  # Now required
        {"name": "new_field", "data_type": "Text", "required": False},  # Added
        # removed_field is gone
    ]


@pytest.fixture
def sample_drift_report() -> Any:
    """Sample DriftReport with changes."""
    from tests.compat.drift_detector import (
        ChangeType,
        DriftMode,
        DriftReport,
        FieldChange,
        SchemaChange,
    )

    report = DriftReport(mode=DriftMode.REPORT)
    change = SchemaChange(
        entity_name="Contact",
        changes=[
            FieldChange(
                field_name="new_field",
                change_type=ChangeType.FIELD_ADDED,
                new_value="Text",
                is_breaking=False,
            ),
            FieldChange(
                field_name="removed_field",
                change_type=ChangeType.FIELD_REMOVED,
                old_value="String",
                is_breaking=True,
            ),
        ],
        old_version="5.73",
        new_version="5.74",
    )
    report.add_entity_change(change)
    return report


@pytest.fixture
def sample_breaking_drift_report() -> Any:
    """Sample DriftReport with breaking changes."""
    from tests.compat.drift_detector import (
        ChangeType,
        DriftMode,
        DriftReport,
        FieldChange,
        SchemaChange,
    )

    report = DriftReport(mode=DriftMode.BREAKING)
    change = SchemaChange(
        entity_name="Contact",
        changes=[
            FieldChange(
                field_name="type_changed_field",
                change_type=ChangeType.TYPE_CHANGED,
                old_value="String",
                new_value="Integer",
                is_breaking=True,
            ),
        ],
    )
    report.add_entity_change(change)
    return report


# -----------------------------------------------------------------------------
# Version Matrix Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def version_matrix() -> Any:
    """Get the CiviCRM version matrix.

    Returns:
        Configured VersionMatrix instance.
    """
    from tests.compat.version_matrix import get_version_matrix

    return get_version_matrix()


@pytest.fixture(scope="session")
def current_civicrm_version() -> str:
    """Get the current CiviCRM version from environment.

    Returns:
        Version string or "default" if not set.
    """
    from tests.compat.version_matrix import get_current_version

    return get_current_version()


@pytest.fixture(scope="session")
def current_version_info(version_matrix: Any, current_civicrm_version: str) -> Any:
    """Get VersionInfo for the current CiviCRM version.

    Args:
        version_matrix: Version matrix instance.
        current_civicrm_version: Current version string.

    Returns:
        VersionInfo or None if version not in matrix.
    """
    return version_matrix.get_closest_version(current_civicrm_version)


@pytest.fixture(autouse=True)
def check_version_skip(request: pytest.FixtureRequest, current_civicrm_version: str) -> Generator[None, None, None]:
    """Automatically skip tests based on version markers.

    This fixture checks for version-related markers and skips tests
    that don't apply to the current CiviCRM version.

    Markers:
        @pytest.mark.min_version(version): Skip if current version is below this
        @pytest.mark.max_version(version): Skip if current version is above this
        @pytest.mark.skip_version(version): Skip if current version matches this
        @pytest.mark.requires_version(version): Skip if current version doesn't match

    Args:
        request: Pytest request fixture.
        current_civicrm_version: Current version string.

    Yields:
        None (fixture runs before test).
    """
    from tests.compat.version_matrix import skip_for_version

    # Check min_version marker
    min_version_marker = request.node.get_closest_marker("min_version")
    if min_version_marker:
        min_version = min_version_marker.args[0] if min_version_marker.args else None
        reason = min_version_marker.kwargs.get("reason", "")
        skip_reason = skip_for_version(current_civicrm_version, min_version=min_version, reason=reason)
        if skip_reason:
            pytest.skip(skip_reason)

    # Check max_version marker
    max_version_marker = request.node.get_closest_marker("max_version")
    if max_version_marker:
        max_version = max_version_marker.args[0] if max_version_marker.args else None
        reason = max_version_marker.kwargs.get("reason", "")
        skip_reason = skip_for_version(current_civicrm_version, max_version=max_version, reason=reason)
        if skip_reason:
            pytest.skip(skip_reason)

    # Check skip_version marker
    skip_version_marker = request.node.get_closest_marker("skip_version")
    if skip_version_marker:
        skip_versions = list(skip_version_marker.args) if skip_version_marker.args else []
        reason = skip_version_marker.kwargs.get("reason", "")
        skip_reason = skip_for_version(current_civicrm_version, skip_versions=skip_versions, reason=reason)
        if skip_reason:
            pytest.skip(skip_reason)

    return


# Add version markers to pytest_configure (extend existing function if present)
def _register_version_markers(config: pytest.Config) -> None:
    """Register custom markers for version-specific testing."""
    # Version-related markers
    config.addinivalue_line(
        "markers",
        "min_version(version): skip test if CiviCRM version is below specified version",
    )
    config.addinivalue_line(
        "markers",
        "max_version(version): skip test if CiviCRM version is above specified version",
    )
    config.addinivalue_line(
        "markers",
        "skip_version(version, ...): skip test for specified CiviCRM version(s)",
    )
    config.addinivalue_line(
        "markers",
        "requires_version(version): skip test if CiviCRM version doesn't match",
    )


# Extend pytest_configure to register version markers
_original_pytest_configure = pytest_configure if "pytest_configure" in dir() else None


def pytest_configure(config: pytest.Config) -> None:
    """Register all custom markers."""
    if _original_pytest_configure:
        _original_pytest_configure(config)
    _register_version_markers(config)
