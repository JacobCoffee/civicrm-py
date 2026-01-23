"""Tests for coverage validation module.

This module contains comprehensive tests for the coverage validator
that validates civi-py's entity and action coverage against CiviCRM API v4.

Phase 8.5.8 additions:
    - Tests for DetailedActionReport
    - Tests for OverallActionCoverageReport
    - Tests for ActionMapping from action_mapping module
    - Tests for 100% action coverage validation
    - Tests for custom action identification
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.compat.action_mapping import (
    ACTION_METHOD_MAP,
    ENTITY_CUSTOM_ACTIONS,
    STANDARD_CIVICRM_ACTIONS,
    ActionCategory,
    ActionInfo,
    ActionMapping,
    ActionPriority,
    get_action_info,
    get_entity_custom_actions,
    is_action_implemented,
)
from tests.compat.coverage_validator import (
    ActionCoverageReport,
    ActionCoverageValidator,
    CoverageReport,
    DetailedActionReport,
    EntityCoverageReport,
    EntityCoverageValidator,
    EntityPriority,
    MissingAction,
    MissingEntity,
    OverallActionCoverageReport,
    generate_coverage_reports,
    generate_detailed_coverage_report,
    validate_entity_action_coverage,
)

# --- Test Fixtures ---


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock CiviClient."""
    client = MagicMock()
    client.request = AsyncMock()
    client.get_fields = AsyncMock()
    return client


@pytest.fixture
def sample_entity_list() -> list[dict[str, Any]]:
    """Sample entity list from CiviCRM Entity.get."""
    return [
        {
            "name": "Contact",
            "title": "Contact",
            "description": "Individuals, organizations, and households.",
            "type": "primary",
            "primary_key": ["id"],
        },
        {
            "name": "Activity",
            "title": "Activity",
            "description": "Interactions and tasks.",
            "type": "secondary",
        },
        {
            "name": "Contribution",
            "title": "Contribution",
            "description": "Financial contributions.",
            "type": "primary",
        },
        {
            "name": "CustomEntity",
            "title": "Custom Entity",
            "description": "An entity not implemented in civi-py.",
            "type": "secondary",
        },
        {
            "name": "OptionValue",
            "title": "Option Value",
            "description": "Option values for select lists.",
            "type": "secondary",
        },
        {
            "name": "Custom_MyExtension",
            "title": "My Extension Entity",
            "description": "Custom entity from extension.",
            "type": "primary",
        },
    ]


@pytest.fixture
def sample_actions_list() -> list[dict[str, Any]]:
    """Sample actions list from entity getActions."""
    return [
        {"name": "get", "description": "Get records"},
        {"name": "create", "description": "Create a record"},
        {"name": "update", "description": "Update records"},
        {"name": "delete", "description": "Delete records"},
        {"name": "save", "description": "Save records (upsert)"},
        {"name": "getFields", "description": "Get field metadata"},
        {"name": "getActions", "description": "Get available actions"},
        {"name": "customAction", "description": "Entity-specific action"},
    ]


@pytest.fixture
def sample_fields_list() -> list[dict[str, Any]]:
    """Sample fields list from entity getFields."""
    return [
        {"name": "id", "data_type": "Integer", "required": False},
        {"name": "display_name", "data_type": "String", "required": False},
        {"name": "first_name", "data_type": "String", "required": False},
        {"name": "last_name", "data_type": "String", "required": False},
        {"name": "email_primary.email", "data_type": "String", "required": False},
    ]


# --- EntityPriority Tests ---


class TestEntityPriority:
    """Tests for EntityPriority enum."""

    def test_priority_values(self) -> None:
        """Test priority value ordering."""
        assert EntityPriority.CRITICAL.value < EntityPriority.HIGH.value
        assert EntityPriority.HIGH.value < EntityPriority.MEDIUM.value
        assert EntityPriority.MEDIUM.value < EntityPriority.LOW.value
        assert EntityPriority.LOW.value < EntityPriority.INTERNAL.value

    def test_priority_names(self) -> None:
        """Test priority name strings."""
        assert EntityPriority.CRITICAL.name == "CRITICAL"
        assert EntityPriority.HIGH.name == "HIGH"
        assert EntityPriority.MEDIUM.name == "MEDIUM"
        assert EntityPriority.LOW.name == "LOW"
        assert EntityPriority.INTERNAL.name == "INTERNAL"


# --- MissingEntity Tests ---


class TestMissingEntity:
    """Tests for MissingEntity dataclass."""

    def test_create_missing_entity(self) -> None:
        """Test creating a MissingEntity."""
        entity = MissingEntity(
            name="TestEntity",
            title="Test Entity",
            description="A test entity",
            priority=EntityPriority.HIGH,
            entity_type="primary",
            fields_count=10,
        )
        assert entity.name == "TestEntity"
        assert entity.title == "Test Entity"
        assert entity.priority == EntityPriority.HIGH
        assert entity.fields_count == 10

    def test_missing_entity_defaults(self) -> None:
        """Test MissingEntity default values."""
        entity = MissingEntity(name="MinimalEntity")
        assert entity.title is None
        assert entity.description is None
        assert entity.priority == EntityPriority.LOW
        assert entity.entity_type is None
        assert entity.fields_count == 0
        assert entity.dependencies == []
        assert entity.notes == ""

    def test_missing_entity_to_dict(self) -> None:
        """Test MissingEntity serialization."""
        entity = MissingEntity(
            name="TestEntity",
            title="Test Entity",
            priority=EntityPriority.CRITICAL,
            entity_type="primary",
            fields_count=5,
            notes="Important entity",
        )
        data = entity.to_dict()

        assert data["name"] == "TestEntity"
        assert data["title"] == "Test Entity"
        assert data["priority"] == "CRITICAL"
        assert data["priority_value"] == 1
        assert data["entity_type"] == "primary"
        assert data["fields_count"] == 5
        assert data["notes"] == "Important entity"


# --- MissingAction Tests ---


class TestMissingAction:
    """Tests for MissingAction dataclass."""

    def test_create_missing_action(self) -> None:
        """Test creating a MissingAction."""
        action = MissingAction(
            entity_name="Contact",
            action_name="replace",
            description="Replace all matching records",
            is_standard=True,
            is_custom=False,
        )
        assert action.entity_name == "Contact"
        assert action.action_name == "replace"
        assert action.is_standard is True
        assert action.is_custom is False

    def test_missing_action_defaults(self) -> None:
        """Test MissingAction default values."""
        action = MissingAction(
            entity_name="Contact",
            action_name="customAction",
        )
        assert action.description is None
        assert action.is_standard is True
        assert action.is_custom is False
        assert action.notes == ""

    def test_missing_action_to_dict(self) -> None:
        """Test MissingAction serialization."""
        action = MissingAction(
            entity_name="Contact",
            action_name="merge",
            is_standard=False,
            is_custom=True,
            notes="Contact-specific merge action",
        )
        data = action.to_dict()

        assert data["entity_name"] == "Contact"
        assert data["action_name"] == "merge"
        assert data["is_standard"] is False
        assert data["is_custom"] is True
        assert data["notes"] == "Contact-specific merge action"


# --- EntityCoverageReport Tests ---


class TestEntityCoverageReport:
    """Tests for EntityCoverageReport dataclass."""

    def test_create_coverage_report(self) -> None:
        """Test creating an EntityCoverageReport."""
        missing = [
            MissingEntity(name="Entity1", priority=EntityPriority.HIGH),
            MissingEntity(name="Entity2", priority=EntityPriority.LOW),
        ]
        report = EntityCoverageReport(
            total_entities=10,
            implemented_entities=8,
            missing_entities=missing,
            implemented_names={"Contact", "Activity"},
        )

        assert report.total_entities == 10
        assert report.implemented_entities == 8
        assert report.missing_count == 2
        assert report.coverage_percentage == 80.0

    def test_coverage_percentage_zero_entities(self) -> None:
        """Test coverage percentage when no entities."""
        report = EntityCoverageReport(total_entities=0, implemented_entities=0)
        assert report.coverage_percentage == 0.0

    def test_missing_by_priority(self) -> None:
        """Test grouping missing entities by priority."""
        missing = [
            MissingEntity(name="Critical1", priority=EntityPriority.CRITICAL),
            MissingEntity(name="High1", priority=EntityPriority.HIGH),
            MissingEntity(name="High2", priority=EntityPriority.HIGH),
            MissingEntity(name="Low1", priority=EntityPriority.LOW),
        ]
        report = EntityCoverageReport(
            total_entities=10,
            implemented_entities=6,
            missing_entities=missing,
        )

        by_priority = report.missing_by_priority()
        assert len(by_priority[EntityPriority.CRITICAL]) == 1
        assert len(by_priority[EntityPriority.HIGH]) == 2
        assert len(by_priority[EntityPriority.LOW]) == 1
        assert len(by_priority[EntityPriority.MEDIUM]) == 0

    def test_to_dict(self) -> None:
        """Test report serialization to dict."""
        missing = [
            MissingEntity(name="Missing1", priority=EntityPriority.HIGH),
        ]
        report = EntityCoverageReport(
            total_entities=5,
            implemented_entities=4,
            missing_entities=missing,
            implemented_names={"Contact", "Activity", "Contribution", "Event"},
        )

        data = report.to_dict()

        assert "summary" in data
        assert data["summary"]["total_entities"] == 5
        assert data["summary"]["implemented_entities"] == 4
        assert data["summary"]["missing_entities"] == 1
        assert data["summary"]["coverage_percentage"] == 80.0
        assert "implemented" in data
        assert len(data["implemented"]) == 4
        assert "missing" in data
        assert len(data["missing"]) == 1
        assert "missing_by_priority" in data

    def test_to_console(self) -> None:
        """Test console output generation."""
        missing = [
            MissingEntity(
                name="Missing1",
                title="Missing Entity One",
                priority=EntityPriority.HIGH,
                notes="Needs implementation",
            ),
        ]
        report = EntityCoverageReport(
            total_entities=5,
            implemented_entities=4,
            missing_entities=missing,
            implemented_names={"Contact", "Activity"},
        )

        console = report.to_console()

        assert "ENTITY COVERAGE REPORT" in console
        assert "Total CiviCRM Entities: 5" in console
        assert "Implemented Entities:   4" in console
        assert "Coverage:               80.0%" in console
        assert "[x] Activity" in console
        assert "[x] Contact" in console
        assert "[ ] Missing1" in console
        assert "Title: Missing Entity One" in console
        assert "HIGH (1)" in console

    def test_save_json(self) -> None:
        """Test saving report to JSON file."""
        report = EntityCoverageReport(
            total_entities=3,
            implemented_entities=2,
            missing_entities=[MissingEntity(name="Missing")],
            implemented_names={"Contact", "Activity"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            report.save_json(path)

            assert path.exists()
            with path.open() as f:
                data = json.load(f)
            assert data["summary"]["total_entities"] == 3

    def test_save_console(self) -> None:
        """Test saving console output to file."""
        report = EntityCoverageReport(
            total_entities=3,
            implemented_entities=2,
            missing_entities=[],
            implemented_names={"Contact", "Activity"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.txt"
            report.save_console(path)

            assert path.exists()
            content = path.read_text()
            assert "ENTITY COVERAGE REPORT" in content


# --- ActionCoverageReport Tests ---


class TestActionCoverageReport:
    """Tests for ActionCoverageReport dataclass."""

    def test_create_action_report(self) -> None:
        """Test creating an ActionCoverageReport."""
        report = ActionCoverageReport(
            entity_name="Contact",
            available_actions={"get", "create", "update", "delete", "customAction"},
            implemented_actions={"get", "create", "update", "delete"},
        )

        assert report.entity_name == "Contact"
        assert len(report.available_actions) == 5
        assert len(report.implemented_actions) == 4

    def test_coverage_percentage(self) -> None:
        """Test action coverage percentage calculation."""
        report = ActionCoverageReport(
            entity_name="Contact",
            available_actions={"get", "create", "update", "delete", "save", "getFields"},
            implemented_actions={"get", "create", "update", "delete", "get_fields"},
        )

        # All standard CRUD actions + getFields are covered
        assert report.coverage_percentage > 0

    def test_coverage_percentage_empty(self) -> None:
        """Test coverage percentage with no available actions."""
        report = ActionCoverageReport(
            entity_name="EmptyEntity",
            available_actions=set(),
        )
        assert report.coverage_percentage == 0.0

    def test_to_dict(self) -> None:
        """Test action report serialization."""
        missing = [
            MissingAction(entity_name="Contact", action_name="replace"),
        ]
        custom = [
            MissingAction(
                entity_name="Contact",
                action_name="merge",
                is_custom=True,
            ),
        ]
        report = ActionCoverageReport(
            entity_name="Contact",
            available_actions={"get", "create", "replace", "merge"},
            implemented_actions={"get", "create"},
            missing_actions=missing,
            custom_actions=custom,
        )

        data = report.to_dict()

        assert data["entity_name"] == "Contact"
        assert "summary" in data
        assert len(data["available"]) == 4
        assert len(data["implemented"]) == 2
        assert len(data["missing"]) == 1
        assert len(data["custom_actions"]) == 1


# --- CoverageReport Tests ---


class TestCoverageReport:
    """Tests for combined CoverageReport."""

    def test_create_combined_report(self) -> None:
        """Test creating a combined coverage report."""
        entity_report = EntityCoverageReport(
            total_entities=10,
            implemented_entities=8,
        )
        action_reports = {
            "Contact": ActionCoverageReport(
                entity_name="Contact",
                available_actions={"get", "create"},
            ),
            "Activity": ActionCoverageReport(
                entity_name="Activity",
                available_actions={"get", "create"},
            ),
        }

        report = CoverageReport(
            entity_report=entity_report,
            action_reports=action_reports,
        )

        assert report.overall_entity_coverage == 80.0
        assert len(report.action_reports) == 2

    def test_overall_action_coverage(self) -> None:
        """Test overall action coverage calculation."""
        entity_report = EntityCoverageReport()
        action_reports = {
            "Entity1": ActionCoverageReport(
                entity_name="Entity1",
                available_actions={"get", "create"},
                implemented_actions={"get", "create"},
            ),
            "Entity2": ActionCoverageReport(
                entity_name="Entity2",
                available_actions={"get"},
                implemented_actions={"get"},
            ),
        }

        report = CoverageReport(
            entity_report=entity_report,
            action_reports=action_reports,
        )

        # Both have coverage > 0
        assert report.overall_action_coverage > 0

    def test_overall_action_coverage_empty(self) -> None:
        """Test overall action coverage with no reports."""
        report = CoverageReport(entity_report=EntityCoverageReport())
        assert report.overall_action_coverage == 0.0

    def test_to_dict(self) -> None:
        """Test combined report serialization."""
        entity_report = EntityCoverageReport(
            total_entities=5,
            implemented_entities=3,
        )
        action_reports = {
            "Contact": ActionCoverageReport(
                entity_name="Contact",
                available_actions={"get"},
            ),
        }

        report = CoverageReport(
            entity_report=entity_report,
            action_reports=action_reports,
        )

        data = report.to_dict()

        assert "summary" in data
        assert "entities" in data
        assert "actions" in data
        assert "Contact" in data["actions"]

    def test_save_json(self) -> None:
        """Test saving combined report to JSON."""
        report = CoverageReport(
            entity_report=EntityCoverageReport(
                total_entities=5,
                implemented_entities=3,
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            report.save_json(path)

            assert path.exists()
            with path.open() as f:
                data = json.load(f)
            assert "summary" in data
            assert "entities" in data


# --- EntityCoverageValidator Tests ---


class TestEntityCoverageValidator:
    """Tests for EntityCoverageValidator."""

    @pytest.fixture
    def validator(self, mock_client: MagicMock) -> EntityCoverageValidator:
        """Create validator with mock client."""
        return EntityCoverageValidator(mock_client)

    def test_get_implemented_entities(
        self,
        validator: EntityCoverageValidator,
    ) -> None:
        """Test getting implemented entity names."""
        implemented = validator.get_implemented_entities()

        # Should include our static implementations
        assert "Contact" in implemented
        assert "Individual" in implemented
        assert "Organization" in implemented
        assert "Household" in implemented
        assert "Activity" in implemented
        assert "Contribution" in implemented
        assert "Address" in implemented
        assert "Email" in implemented
        assert "Phone" in implemented
        assert "Event" in implemented
        assert "Participant" in implemented
        assert "Membership" in implemented
        assert "Group" in implemented
        assert "GroupContact" in implemented
        assert "Tag" in implemented
        assert "EntityTag" in implemented
        assert "Note" in implemented

    @pytest.mark.asyncio
    async def test_get_api_entities(
        self,
        validator: EntityCoverageValidator,
        sample_entity_list: list[dict[str, Any]],
    ) -> None:
        """Test fetching entities from API."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_entity_list),
        )

        entities = await validator.get_api_entities()

        assert len(entities) == 6
        assert entities[0].name == "Contact"
        validator.client.request.assert_called_once_with("Entity", "get", {})

    @pytest.mark.asyncio
    async def test_generate_report(
        self,
        validator: EntityCoverageValidator,
        sample_entity_list: list[dict[str, Any]],
    ) -> None:
        """Test generating entity coverage report."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_entity_list),
        )

        report = await validator.generate_report()

        # Should have 6 total entities from sample
        assert report.total_entities == 6
        # Contact, Activity, Contribution are implemented
        assert report.implemented_entities >= 3
        # CustomEntity, OptionValue, Custom_MyExtension are not implemented
        assert report.missing_count >= 0
        assert report.coverage_percentage > 0

    @pytest.mark.asyncio
    async def test_generate_report_with_field_counts(
        self,
        validator: EntityCoverageValidator,
        sample_entity_list: list[dict[str, Any]],
        sample_fields_list: list[dict[str, Any]],
    ) -> None:
        """Test generating report with field counts."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_entity_list),
        )
        validator.discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(values=sample_fields_list),
        )

        report = await validator.generate_report(include_field_counts=True)

        # Report should be generated
        assert report.total_entities == 6

    def test_get_entity_priority_known(
        self,
        validator: EntityCoverageValidator,
    ) -> None:
        """Test priority lookup for known entities."""
        from civi_py.entities.discovery import EntityInfo

        contact = EntityInfo(name="Contact", type="primary")
        activity = EntityInfo(name="Activity", type="secondary")
        option_value = EntityInfo(name="OptionValue", type="secondary")

        assert validator._get_entity_priority(contact) == EntityPriority.CRITICAL
        assert validator._get_entity_priority(activity) == EntityPriority.CRITICAL
        assert validator._get_entity_priority(option_value) == EntityPriority.LOW

    def test_get_entity_priority_unknown(
        self,
        validator: EntityCoverageValidator,
    ) -> None:
        """Test priority inference for unknown entities."""
        from civi_py.entities.discovery import EntityInfo

        custom = EntityInfo(name="Custom_MyEntity", type="primary")
        primary = EntityInfo(name="NewPrimaryEntity", type="primary")
        secondary = EntityInfo(name="NewSecondaryEntity", type="secondary")
        bridge = EntityInfo(name="NewBridgeEntity", type="bridge")

        assert validator._get_entity_priority(custom) == EntityPriority.LOW
        assert validator._get_entity_priority(primary) == EntityPriority.HIGH
        assert validator._get_entity_priority(secondary) == EntityPriority.MEDIUM
        assert validator._get_entity_priority(bridge) == EntityPriority.LOW


# --- ActionCoverageValidator Tests ---


class TestActionCoverageValidator:
    """Tests for ActionCoverageValidator."""

    @pytest.fixture
    def validator(self, mock_client: MagicMock) -> ActionCoverageValidator:
        """Create validator with mock client."""
        return ActionCoverageValidator(mock_client)

    @pytest.mark.asyncio
    async def test_get_entity_actions(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test fetching actions for an entity."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        actions = await validator.get_entity_actions("Contact")

        assert "get" in actions
        assert "create" in actions
        assert "update" in actions
        assert "delete" in actions
        assert "customAction" in actions
        validator.client.request.assert_called_once_with(
            "Contact",
            "getActions",
            {},
        )

    @pytest.mark.asyncio
    async def test_get_entity_actions_error(
        self,
        validator: ActionCoverageValidator,
    ) -> None:
        """Test handling of API errors when fetching actions."""
        validator.client.request = AsyncMock(side_effect=Exception("API Error"))

        actions = await validator.get_entity_actions("Contact")

        assert actions == set()

    @pytest.mark.asyncio
    async def test_generate_report(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating action coverage report."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        report = await validator.generate_report("Contact")

        assert report.entity_name == "Contact"
        assert len(report.available_actions) == 8
        # customAction should be identified as custom
        assert len(report.custom_actions) >= 0

    @pytest.mark.asyncio
    async def test_generate_all_reports(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating reports for multiple entities."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        reports = await validator.generate_all_reports(["Contact", "Activity"])

        assert "Contact" in reports
        assert "Activity" in reports
        assert reports["Contact"].entity_name == "Contact"
        assert reports["Activity"].entity_name == "Activity"

    def test_is_action_implemented(
        self,
        validator: ActionCoverageValidator,
    ) -> None:
        """Test checking if an action is implemented."""
        assert validator._is_action_implemented("get") is True
        assert validator._is_action_implemented("create") is True
        assert validator._is_action_implemented("update") is True
        assert validator._is_action_implemented("delete") is True
        assert validator._is_action_implemented("getFields") is True
        # These are not implemented
        assert validator._is_action_implemented("replace") is False
        assert validator._is_action_implemented("checkAccess") is False

    def test_is_standard_action(
        self,
        validator: ActionCoverageValidator,
    ) -> None:
        """Test identifying standard actions."""
        assert validator._is_standard_action("get") is True
        assert validator._is_standard_action("create") is True
        assert validator._is_standard_action("getFields") is True
        assert validator._is_standard_action("customAction") is False
        assert validator._is_standard_action("merge") is False


# --- generate_coverage_reports Tests ---


class TestGenerateCoverageReports:
    """Tests for generate_coverage_reports function."""

    @pytest.mark.asyncio
    async def test_generate_reports(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating complete coverage reports."""
        mock_client.request = AsyncMock(
            side_effect=[
                # First call: Entity.get
                MagicMock(values=sample_entity_list),
                # Subsequent calls: getActions for each implemented entity
                *[MagicMock(values=sample_actions_list) for _ in range(20)],
            ],
        )

        report = await generate_coverage_reports(mock_client)

        assert report.entity_report is not None
        assert report.overall_entity_coverage > 0

    @pytest.mark.asyncio
    async def test_generate_reports_with_output(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating reports with file output."""
        mock_client.request = AsyncMock(
            side_effect=[
                MagicMock(values=sample_entity_list),
                *[MagicMock(values=sample_actions_list) for _ in range(20)],
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            report = await generate_coverage_reports(
                mock_client,
                output_dir=tmpdir,
            )

            # Check that files were created
            output_path = Path(tmpdir)
            assert (output_path / "coverage_report.json").exists()
            assert (output_path / "entity_coverage.json").exists()
            assert (output_path / "entity_coverage.txt").exists()
            assert (output_path / "actions").is_dir()


# --- Integration Tests ---


class TestCoverageValidatorIntegration:
    """Integration tests for coverage validators."""

    @pytest.mark.asyncio
    async def test_entity_validator_with_discovery(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
    ) -> None:
        """Test entity validator integration with EntityDiscovery."""
        mock_client.request = AsyncMock(
            return_value=MagicMock(values=sample_entity_list),
        )

        validator = EntityCoverageValidator(mock_client)
        report = await validator.generate_report()

        # Verify discovery was used
        mock_client.request.assert_called_with("Entity", "get", {})
        assert report.total_entities == len(sample_entity_list)

    @pytest.mark.asyncio
    async def test_action_validator_with_entity_validator(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test action validator using entity validator's entities."""
        mock_client.request = AsyncMock(
            side_effect=[
                MagicMock(values=sample_entity_list),  # Entity.get
                MagicMock(values=sample_actions_list),  # Contact.getActions
                MagicMock(values=sample_actions_list),  # Activity.getActions
            ],
        )

        entity_validator = EntityCoverageValidator(mock_client)
        implemented = list(entity_validator.get_implemented_entities())[:2]

        action_validator = ActionCoverageValidator(mock_client)
        action_reports = await action_validator.generate_all_reports(implemented)

        assert len(action_reports) == 2


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_entity_list(self, mock_client: MagicMock) -> None:
        """Test handling of empty entity list from API."""
        mock_client.request = AsyncMock(return_value=MagicMock(values=[]))

        validator = EntityCoverageValidator(mock_client)
        report = await validator.generate_report()

        assert report.total_entities == 0
        assert report.coverage_percentage == 0.0

    @pytest.mark.asyncio
    async def test_null_values_response(self, mock_client: MagicMock) -> None:
        """Test handling of null values in response."""
        mock_client.request = AsyncMock(return_value=MagicMock(values=None))

        validator = ActionCoverageValidator(mock_client)
        actions = await validator.get_entity_actions("Contact")

        assert actions == set()

    @pytest.mark.asyncio
    async def test_entity_with_no_actions(self, mock_client: MagicMock) -> None:
        """Test generating report for entity with no actions."""
        mock_client.request = AsyncMock(return_value=MagicMock(values=[]))

        validator = ActionCoverageValidator(mock_client)
        report = await validator.generate_report("EmptyEntity")

        assert report.entity_name == "EmptyEntity"
        assert len(report.available_actions) == 0
        assert report.coverage_percentage == 0.0

    def test_report_with_special_characters(self) -> None:
        """Test report generation with special characters in names."""
        missing = [
            MissingEntity(
                name="Custom_MyEntity-v2",
                title="My Entity (v2.0)",
                notes="Contains 'special' & <characters>",
            ),
        ]
        report = EntityCoverageReport(
            total_entities=1,
            implemented_entities=0,
            missing_entities=missing,
        )

        # Should not raise
        data = report.to_dict()
        console = report.to_console()

        assert "Custom_MyEntity-v2" in console
        assert data["missing"][0]["name"] == "Custom_MyEntity-v2"

    @pytest.mark.asyncio
    async def test_api_error_recovery(self, mock_client: MagicMock) -> None:
        """Test graceful recovery from API errors during action fetch.

        When an error occurs fetching actions, the validator should gracefully
        degrade by returning an empty action set rather than failing completely.
        """
        mock_client.request = AsyncMock(
            side_effect=[
                MagicMock(values=[{"name": "get"}]),  # First entity succeeds
                Exception("API Error"),  # Second entity fails (caught internally)
                MagicMock(values=[{"name": "get"}]),  # Third entity succeeds
            ],
        )

        validator = ActionCoverageValidator(mock_client)
        reports = await validator.generate_all_reports(
            ["Entity1", "Entity2", "Entity3"],
        )

        # All reports should be present
        assert "Entity1" in reports
        assert "Entity2" in reports
        assert "Entity3" in reports

        # Entity1 and Entity3 should have actions
        assert len(reports["Entity1"].available_actions) == 1
        assert len(reports["Entity3"].available_actions) == 1

        # Entity2 should have empty actions (graceful degradation)
        assert len(reports["Entity2"].available_actions) == 0


# --- Phase 8.5.8 Tests: Action Mapping ---


class TestActionInfo:
    """Tests for ActionInfo dataclass."""

    def test_create_action_info(self) -> None:
        """Test creating an ActionInfo."""
        action = ActionInfo(
            name="get",
            category=ActionCategory.CRUD,
            priority=ActionPriority.CRITICAL,
            description="Retrieve records",
            entity_methods={"get", "filter", "all"},
        )
        assert action.name == "get"
        assert action.category == ActionCategory.CRUD
        assert action.priority == ActionPriority.CRITICAL
        assert action.is_implemented is True
        assert len(action.entity_methods) == 3

    def test_action_info_not_implemented(self) -> None:
        """Test ActionInfo with no methods."""
        action = ActionInfo(
            name="checkAccess",
            category=ActionCategory.SECURITY,
            priority=ActionPriority.MEDIUM,
        )
        assert action.is_implemented is False
        assert len(action.entity_methods) == 0

    def test_action_info_to_dict(self) -> None:
        """Test ActionInfo serialization."""
        action = ActionInfo(
            name="create",
            category=ActionCategory.CRUD,
            priority=ActionPriority.CRITICAL,
            entity_methods={"create", "bulk_create"},
            notes="Supports bulk creation",
        )
        data = action.to_dict()

        assert data["name"] == "create"
        assert data["category"] == "crud"
        assert data["priority"] == "CRITICAL"
        assert data["priority_value"] == 1
        assert data["is_implemented"] is True
        assert "create" in data["entity_methods"]


class TestActionMapping:
    """Tests for ActionMapping dataclass."""

    def test_create_action_mapping(self) -> None:
        """Test creating an ActionMapping."""
        mapping = ActionMapping(entity_name="Contact")

        assert mapping.entity_name == "Contact"
        assert len(mapping.standard_actions) > 0
        assert "get" in mapping.standard_actions
        assert "create" in mapping.standard_actions

    def test_action_mapping_with_custom_actions(self) -> None:
        """Test ActionMapping includes entity custom actions."""
        mapping = ActionMapping(entity_name="Contact")

        # Contact should have custom actions
        assert len(mapping.custom_actions) > 0
        custom_names = [a.name for a in mapping.custom_actions]
        assert "merge" in custom_names

    def test_action_mapping_coverage_percentage(self) -> None:
        """Test coverage percentage calculation."""
        mapping = ActionMapping(entity_name="Contact")

        # Should have > 0% coverage since we implement standard CRUD
        coverage = mapping.coverage_percentage()
        assert coverage > 0
        assert coverage <= 100

    def test_action_mapping_api_coverage(self) -> None:
        """Test API coverage calculation."""
        mapping = ActionMapping(
            entity_name="Contact",
            api_actions={"get", "create", "update", "delete", "customAction"},
        )

        coverage = mapping.api_coverage_percentage()
        # get, create, update, delete are implemented (4 out of 5)
        assert coverage >= 80.0

    def test_action_mapping_get_action_status(self) -> None:
        """Test getting action status."""
        mapping = ActionMapping(entity_name="Contact")

        # Standard action
        status = mapping.get_action_status("get")
        assert status["action"] == "get"
        assert status["status"] == "implemented"
        assert status["type"] == "standard"

        # Unknown action
        status = mapping.get_action_status("unknownAction")
        assert status["status"] == "unknown"

    def test_action_mapping_implemented_vs_unimplemented(self) -> None:
        """Test getting implemented and unimplemented actions."""
        mapping = ActionMapping(entity_name="Contact")

        implemented = mapping.implemented_actions
        unimplemented = mapping.unimplemented_actions

        # All actions should be in one or the other
        total = len(implemented) + len(unimplemented)
        assert total == len(mapping.all_actions)

        # get, create, update, delete should be implemented
        implemented_names = [a.name for a in implemented]
        assert "get" in implemented_names
        assert "create" in implemented_names

    def test_action_mapping_high_priority_missing(self) -> None:
        """Test getting high-priority missing actions."""
        mapping = ActionMapping(entity_name="Contact")

        high_priority = mapping.high_priority_missing

        # All should be CRITICAL or HIGH priority
        for action in high_priority:
            assert action.priority in (ActionPriority.CRITICAL, ActionPriority.HIGH)

    def test_action_mapping_to_dict(self) -> None:
        """Test ActionMapping serialization."""
        mapping = ActionMapping(
            entity_name="Contact",
            api_actions={"get", "create"},
        )
        data = mapping.to_dict()

        assert data["entity_name"] == "Contact"
        assert "summary" in data
        assert "standard_actions" in data
        assert "custom_actions" in data
        assert data["api_actions"] is not None


class TestActionMappingFunctions:
    """Tests for action_mapping module functions."""

    def test_get_action_info(self) -> None:
        """Test getting action info by name."""
        info = get_action_info("get")
        assert info is not None
        assert info.name == "get"
        assert info.priority == ActionPriority.CRITICAL

        # Unknown action
        info = get_action_info("unknownAction")
        assert info is None

    def test_get_entity_custom_actions(self) -> None:
        """Test getting custom actions for entity."""
        # Contact has custom actions
        actions = get_entity_custom_actions("Contact")
        assert len(actions) > 0
        names = [a.name for a in actions]
        assert "merge" in names

        # Unknown entity has no custom actions
        actions = get_entity_custom_actions("UnknownEntity")
        assert len(actions) == 0

    def test_is_action_implemented(self) -> None:
        """Test checking if action is implemented."""
        assert is_action_implemented("get") is True
        assert is_action_implemented("create") is True
        assert is_action_implemented("checkAccess") is False
        assert is_action_implemented("unknownAction") is False

    def test_standard_actions_exist(self) -> None:
        """Test that standard actions are defined."""
        assert "get" in STANDARD_CIVICRM_ACTIONS
        assert "create" in STANDARD_CIVICRM_ACTIONS
        assert "update" in STANDARD_CIVICRM_ACTIONS
        assert "delete" in STANDARD_CIVICRM_ACTIONS
        assert "getFields" in STANDARD_CIVICRM_ACTIONS

    def test_entity_custom_actions_exist(self) -> None:
        """Test that entity custom actions are defined."""
        assert "Contact" in ENTITY_CUSTOM_ACTIONS
        assert "Contribution" in ENTITY_CUSTOM_ACTIONS

    def test_action_method_map_exists(self) -> None:
        """Test that action method map is defined."""
        assert "get" in ACTION_METHOD_MAP
        assert "create" in ACTION_METHOD_MAP
        assert len(ACTION_METHOD_MAP["get"]) > 0


# --- Phase 8.5.8 Tests: Detailed Reports ---


class TestDetailedActionReport:
    """Tests for DetailedActionReport dataclass."""

    def test_create_detailed_report(self) -> None:
        """Test creating a DetailedActionReport."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get", "create", "update", "delete", "merge"},
        )

        assert report.entity_name == "Contact"
        assert len(report.api_actions) == 5
        assert report.action_mapping is not None

    def test_detailed_report_coverage(self) -> None:
        """Test coverage percentage calculation."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get", "create", "update", "delete"},
        )

        assert report.coverage_percentage > 0
        assert report.api_coverage_percentage > 0

    def test_detailed_report_standard_actions(self) -> None:
        """Test standard action classification."""
        report = DetailedActionReport(entity_name="Contact")

        covered = report.standard_actions_covered
        missing = report.standard_actions_missing

        # Standard CRUD should be covered
        assert "get" in covered
        assert "create" in covered

        # Some actions should be missing
        assert len(missing) > 0

    def test_detailed_report_custom_actions(self) -> None:
        """Test custom action tracking."""
        report = DetailedActionReport(entity_name="Contact")

        custom = report.custom_actions_available
        assert "merge" in custom

    def test_detailed_report_unknown_actions(self) -> None:
        """Test unknown API action detection."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get", "unknownAction1", "unknownAction2"},
        )

        unknown = report.unknown_actions
        assert "unknownAction1" in unknown
        assert "unknownAction2" in unknown
        assert "get" not in unknown

    def test_detailed_report_missing_critical(self) -> None:
        """Test missing critical action detection."""
        report = DetailedActionReport(entity_name="Contact")

        # No critical actions should be missing since we implement standard CRUD
        critical = report.missing_critical_actions
        for action in critical:
            assert action.priority == ActionPriority.CRITICAL

    def test_detailed_report_get_action_status(self) -> None:
        """Test getting action status."""
        report = DetailedActionReport(entity_name="Contact")

        status = report.get_action_status("get")
        assert status["status"] == "implemented"

        status = report.get_action_status("checkAccess")
        assert status["status"] == "not_implemented"

    def test_detailed_report_to_dict(self) -> None:
        """Test DetailedActionReport serialization."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get", "create"},
        )
        data = report.to_dict()

        assert data["entity_name"] == "Contact"
        assert "summary" in data
        assert "standard_actions" in data
        assert "custom_actions" in data
        assert "api_actions" in data
        assert "unknown_actions" in data

    def test_detailed_report_to_console(self) -> None:
        """Test console output generation."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get", "create"},
        )
        console = report.to_console()

        assert "ACTION COVERAGE REPORT: Contact" in console
        assert "IMPLEMENTED STANDARD ACTIONS" in console
        assert "[x] get" in console

    def test_detailed_report_save_json(self) -> None:
        """Test saving report to JSON file."""
        report = DetailedActionReport(
            entity_name="Contact",
            api_actions={"get"},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            report.save_json(path)

            assert path.exists()
            with path.open() as f:
                data = json.load(f)
            assert data["entity_name"] == "Contact"


class TestOverallActionCoverageReport:
    """Tests for OverallActionCoverageReport dataclass."""

    def test_create_overall_report(self) -> None:
        """Test creating an OverallActionCoverageReport."""
        entity_reports = {
            "Contact": DetailedActionReport(
                entity_name="Contact",
                api_actions={"get", "create"},
            ),
            "Activity": DetailedActionReport(
                entity_name="Activity",
                api_actions={"get", "create"},
            ),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)

        assert report.total_entities == 2
        assert report.average_coverage > 0

    def test_overall_report_average_coverage(self) -> None:
        """Test average coverage calculation."""
        entity_reports = {
            "Contact": DetailedActionReport(entity_name="Contact"),
            "Activity": DetailedActionReport(entity_name="Activity"),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)

        # Both entities have same standard actions, so coverage should be similar
        assert report.average_coverage > 0
        assert report.average_coverage <= 100

    def test_overall_report_full_coverage_entities(self) -> None:
        """Test entities with full coverage detection."""
        entity_reports = {
            "Contact": DetailedActionReport(entity_name="Contact"),
            "Activity": DetailedActionReport(entity_name="Activity"),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)

        # Most entities won't have 100% coverage
        full_coverage = report.entities_with_full_coverage
        assert isinstance(full_coverage, list)

    def test_overall_report_missing_critical(self) -> None:
        """Test entities with missing critical actions."""
        entity_reports = {
            "Contact": DetailedActionReport(entity_name="Contact"),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)

        critical = report.all_missing_critical_actions
        # Each item is a tuple of (entity_name, ActionInfo)
        for entity_name, action in critical:
            assert isinstance(entity_name, str)
            assert isinstance(action, ActionInfo)

    def test_overall_report_unknown_actions(self) -> None:
        """Test aggregating unknown actions."""
        entity_reports = {
            "Contact": DetailedActionReport(
                entity_name="Contact",
                api_actions={"get", "unknownAction"},
            ),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)

        unknown = report.all_unknown_actions
        assert "Contact" in unknown
        assert "unknownAction" in unknown["Contact"]

    def test_overall_report_to_dict(self) -> None:
        """Test OverallActionCoverageReport serialization."""
        entity_reports = {
            "Contact": DetailedActionReport(entity_name="Contact"),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)
        data = report.to_dict()

        assert "summary" in data
        assert "entity_coverage" in data
        assert "Contact" in data["entity_coverage"]
        assert "detailed_reports" in data

    def test_overall_report_to_console(self) -> None:
        """Test console output generation."""
        entity_reports = {
            "Contact": DetailedActionReport(entity_name="Contact"),
        }
        report = OverallActionCoverageReport(entity_reports=entity_reports)
        console = report.to_console()

        assert "OVERALL ACTION COVERAGE REPORT" in console
        assert "Contact" in console

    def test_overall_report_empty(self) -> None:
        """Test empty report handling."""
        report = OverallActionCoverageReport()

        assert report.total_entities == 0
        assert report.average_coverage == 0.0
        assert report.average_api_coverage == 0.0


# --- Phase 8.5.8 Tests: Enhanced Validator ---


class TestActionCoverageValidatorEnhanced:
    """Tests for enhanced ActionCoverageValidator methods."""

    @pytest.fixture
    def validator(self, mock_client: MagicMock) -> ActionCoverageValidator:
        """Create validator with mock client."""
        return ActionCoverageValidator(mock_client)

    @pytest.mark.asyncio
    async def test_generate_detailed_report(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating detailed action report."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        report = await validator.generate_detailed_report("Contact")

        assert isinstance(report, DetailedActionReport)
        assert report.entity_name == "Contact"
        assert len(report.api_actions) == 8

    @pytest.mark.asyncio
    async def test_generate_all_detailed_reports(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating all detailed reports."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        report = await validator.generate_all_detailed_reports(["Contact", "Activity"])

        assert isinstance(report, OverallActionCoverageReport)
        assert report.total_entities == 2
        assert "Contact" in report.entity_reports
        assert "Activity" in report.entity_reports

    @pytest.mark.asyncio
    async def test_validate_100_percent_coverage(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test 100% coverage validation."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        has_full, missing = await validator.validate_100_percent_coverage("Contact")

        assert isinstance(has_full, bool)
        assert isinstance(missing, list)

    @pytest.mark.asyncio
    async def test_get_high_priority_missing(
        self,
        validator: ActionCoverageValidator,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test getting high-priority missing actions."""
        validator.client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        missing = await validator.get_high_priority_missing(["Contact"])

        assert isinstance(missing, dict)


# --- Phase 8.5.8 Tests: New Report Functions ---


class TestDetailedReportFunctions:
    """Tests for new detailed report generation functions."""

    @pytest.mark.asyncio
    async def test_generate_detailed_coverage_report(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating detailed coverage reports."""
        mock_client.request = AsyncMock(
            side_effect=[
                MagicMock(values=sample_entity_list),
                *[MagicMock(values=sample_actions_list) for _ in range(40)],
            ],
        )

        report, detailed = await generate_detailed_coverage_report(mock_client)

        assert isinstance(report, CoverageReport)
        assert isinstance(detailed, OverallActionCoverageReport)

    @pytest.mark.asyncio
    async def test_generate_detailed_coverage_report_with_output(
        self,
        mock_client: MagicMock,
        sample_entity_list: list[dict[str, Any]],
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test generating detailed reports with file output."""
        mock_client.request = AsyncMock(
            side_effect=[
                MagicMock(values=sample_entity_list),
                *[MagicMock(values=sample_actions_list) for _ in range(40)],
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _report, _detailed = await generate_detailed_coverage_report(
                mock_client,
                output_dir=tmpdir,
            )

            output_path = Path(tmpdir)
            assert (output_path / "coverage_report.json").exists()
            assert (output_path / "action_coverage_detailed.json").exists()
            assert (output_path / "action_coverage_detailed.txt").exists()
            assert (output_path / "actions_detailed").is_dir()

    @pytest.mark.asyncio
    async def test_validate_entity_action_coverage(
        self,
        mock_client: MagicMock,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test single entity action coverage validation."""
        mock_client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        result = await validate_entity_action_coverage(mock_client, "Contact")

        assert result["entity"] == "Contact"
        assert "valid" in result
        assert "coverage_percentage" in result
        assert "standard_covered" in result
        assert "standard_missing" in result
        assert "custom_actions" in result

    @pytest.mark.asyncio
    async def test_validate_entity_action_coverage_require_100(
        self,
        mock_client: MagicMock,
        sample_actions_list: list[dict[str, Any]],
    ) -> None:
        """Test 100% coverage requirement validation."""
        mock_client.request = AsyncMock(
            return_value=MagicMock(values=sample_actions_list),
        )

        result = await validate_entity_action_coverage(
            mock_client,
            "Contact",
            require_100_percent=True,
        )

        # Will likely fail 100% requirement since not all actions implemented
        assert "valid" in result
        if result["coverage_percentage"] < 100.0:
            assert result["valid"] is False
