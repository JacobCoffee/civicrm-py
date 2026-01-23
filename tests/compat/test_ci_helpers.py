"""Tests for CI helper utilities.

Phase 8.5.12: Nightly CI workflow support
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.compat.ci_helpers import (
    CassetteChange,
    CassetteUpdater,
    CassetteUpdateSummary,
    CIEnvironment,
    DriftChecker,
    DriftResult,
    NotificationPayload,
)

# =============================================================================
# DriftResult Tests
# =============================================================================


class TestDriftResult:
    """Tests for DriftResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = DriftResult()

        assert result.has_drift is False
        assert result.has_breaking_changes is False
        assert result.entities_changed == []
        assert result.breaking_entities == []
        assert result.summary == ""
        assert result.details == {}

    def test_with_values(self):
        """Test with custom values."""
        result = DriftResult(
            has_drift=True,
            has_breaking_changes=True,
            entities_changed=["Contact", "Activity"],
            breaking_entities=["Contact"],
            summary="Breaking changes detected",
            details={"count": 2},
        )

        assert result.has_drift is True
        assert result.has_breaking_changes is True
        assert len(result.entities_changed) == 2
        assert len(result.breaking_entities) == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = DriftResult(
            has_drift=True,
            entities_changed=["Contact"],
        )

        data = result.to_dict()

        assert data["has_drift"] is True
        assert data["entities_changed"] == ["Contact"]
        assert "timestamp" in data


# =============================================================================
# CassetteChange Tests
# =============================================================================


class TestCassetteChange:
    """Tests for CassetteChange dataclass."""

    def test_basic_change(self):
        """Test basic change creation."""
        change = CassetteChange(
            path=Path("tests/cassettes/v5.74/entities/Contact_get.json"),
            change_type="modified",
        )

        assert change.change_type == "modified"
        assert change.version == "5.74"
        assert change.entity == "Contact_get"

    def test_added_change(self):
        """Test added change type."""
        change = CassetteChange(
            path=Path("tests/cassettes/v5.75/entities/Activity_get.json"),
            change_type="added",
        )

        assert change.change_type == "added"
        assert change.version == "5.75"
        assert change.entity == "Activity_get"

    def test_non_entity_path(self):
        """Test with non-entity path."""
        change = CassetteChange(
            path=Path("tests/cassettes/README.md"),
            change_type="modified",
        )

        assert change.entity == ""


# =============================================================================
# CassetteUpdateSummary Tests
# =============================================================================


class TestCassetteUpdateSummary:
    """Tests for CassetteUpdateSummary dataclass."""

    def test_empty_summary(self):
        """Test empty summary."""
        summary = CassetteUpdateSummary()

        assert summary.has_changes() is False
        assert summary.total_added == 0
        assert summary.total_modified == 0
        assert summary.total_deleted == 0

    def test_with_changes(self):
        """Test summary with changes."""
        changes = [
            CassetteChange(
                path=Path("tests/cassettes/v5.74/entities/Contact_get.json"),
                change_type="modified",
            ),
            CassetteChange(
                path=Path("tests/cassettes/v5.74/entities/Activity_get.json"),
                change_type="added",
            ),
        ]

        summary = CassetteUpdateSummary(
            changes=changes,
            total_added=1,
            total_modified=1,
            civicrm_version="5.74",
        )

        assert summary.has_changes() is True
        assert len(summary.changes) == 2

    def test_to_markdown(self):
        """Test markdown generation."""
        changes = [
            CassetteChange(
                path=Path("tests/cassettes/v5.74/entities/Contact_get.json"),
                change_type="modified",
            ),
        ]

        summary = CassetteUpdateSummary(
            changes=changes,
            civicrm_version="5.74",
        )

        markdown = summary.to_markdown()

        assert "## Cassette Update Summary" in markdown
        assert "5.74" in markdown
        assert "Contact_get" in markdown
        assert "modified" in markdown


# =============================================================================
# DriftChecker Tests
# =============================================================================


class TestDriftChecker:
    """Tests for DriftChecker class."""

    def test_init_default(self, tmp_path):
        """Test default initialization."""
        checker = DriftChecker()
        assert checker.schema_dir is not None
        assert checker.snapshot_dir is not None

    def test_init_custom_paths(self, tmp_path):
        """Test initialization with custom paths."""
        schema_dir = tmp_path / "schemas"
        snapshot_dir = tmp_path / "snapshots"

        checker = DriftChecker(
            schema_dir=schema_dir,
            snapshot_dir=snapshot_dir,
        )

        assert checker.schema_dir == schema_dir
        assert checker.snapshot_dir == snapshot_dir

    def test_check_drift_no_modules(self, tmp_path, monkeypatch):
        """Test drift check when modules unavailable."""
        # Create a checker that will fail to import
        checker = DriftChecker(
            schema_dir=tmp_path,
            snapshot_dir=tmp_path,
        )

        # Mock the import to fail
        with patch.dict("sys.modules", {"tests.compat.drift_detector": None}):
            result = checker.check_drift()

        # Should return empty result with error message
        assert result.has_drift is False

    def test_save_result(self, tmp_path):
        """Test saving drift result."""
        checker = DriftChecker()
        result = DriftResult(
            has_drift=True,
            entities_changed=["Contact"],
        )

        output_path = tmp_path / "result.json"
        saved_path = checker.save_result(result, output_path)

        assert saved_path.exists()

        with saved_path.open() as f:
            data = json.load(f)

        assert data["has_drift"] is True
        assert data["entities_changed"] == ["Contact"]


# =============================================================================
# CassetteUpdater Tests
# =============================================================================


class TestCassetteUpdater:
    """Tests for CassetteUpdater class."""

    def test_init_default(self):
        """Test default initialization."""
        updater = CassetteUpdater()
        assert updater.cassette_dir is not None

    def test_init_custom(self, tmp_path):
        """Test initialization with custom values."""
        updater = CassetteUpdater(
            cassette_dir=tmp_path,
            civicrm_version="5.74",
        )

        assert updater.cassette_dir == tmp_path
        assert updater.civicrm_version == "5.74"

    def test_has_changes_no_git(self, tmp_path, monkeypatch):
        """Test has_changes when git not available."""
        updater = CassetteUpdater(cassette_dir=tmp_path)

        # Should return False when git fails
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert updater.has_changes() is False

    def test_has_changes_no_changes(self, tmp_path, monkeypatch):
        """Test has_changes when no changes."""
        updater = CassetteUpdater(cassette_dir=tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0  # No changes

        with patch("subprocess.run", return_value=mock_result):
            assert updater.has_changes() is False

    def test_has_changes_with_changes(self, tmp_path):
        """Test has_changes when changes exist."""
        updater = CassetteUpdater(cassette_dir=tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 1  # Has changes

        with patch("subprocess.run", return_value=mock_result):
            assert updater.has_changes() is True

    def test_create_update_summary(self, tmp_path):
        """Test creating update summary."""
        updater = CassetteUpdater(
            cassette_dir=tmp_path,
            civicrm_version="5.74",
        )

        # Mock git commands
        with patch.object(updater, "get_changes") as mock_get:
            mock_get.return_value = [
                CassetteChange(
                    path=Path("tests/cassettes/v5.74/entities/Contact_get.json"),
                    change_type="modified",
                ),
            ]

            summary = updater.create_update_summary()

            assert summary.has_changes()
            assert summary.civicrm_version == "5.74"
            assert summary.total_modified == 1


# =============================================================================
# CIEnvironment Tests
# =============================================================================


class TestCIEnvironment:
    """Tests for CIEnvironment class."""

    def test_not_in_ci(self, monkeypatch):
        """Test when not in CI environment."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        ci = CIEnvironment()

        assert ci.is_ci is False
        assert ci.is_github_actions is False
        assert ci.is_gitlab_ci is False

    def test_github_actions(self, monkeypatch):
        """Test GitHub Actions detection."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_RUN_ID", "12345")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_REF_NAME", "main")

        ci = CIEnvironment()

        assert ci.is_ci is True
        assert ci.is_github_actions is True
        assert ci.run_id == "12345"
        assert ci.repository == "owner/repo"
        assert ci.branch == "main"

    def test_gitlab_ci(self, monkeypatch):
        """Test GitLab CI detection."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITLAB_CI", "true")
        monkeypatch.setenv("CI_PIPELINE_ID", "67890")
        monkeypatch.setenv("CI_PROJECT_PATH", "group/project")
        monkeypatch.setenv("CI_COMMIT_REF_NAME", "develop")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        ci = CIEnvironment()

        assert ci.is_ci is True
        assert ci.is_gitlab_ci is True
        assert ci.run_id == "67890"
        assert ci.repository == "group/project"
        assert ci.branch == "develop"

    def test_set_output_github(self, tmp_path, monkeypatch):
        """Test setting output in GitHub Actions."""
        output_file = tmp_path / "github_output"
        output_file.touch()

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        ci = CIEnvironment()
        ci.set_output("test_key", "test_value")

        content = output_file.read_text()
        assert "test_key=test_value" in content

    def test_write_summary_github(self, tmp_path, monkeypatch):
        """Test writing summary in GitHub Actions."""
        summary_file = tmp_path / "step_summary"
        summary_file.touch()

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        ci = CIEnvironment()
        ci.write_summary("# Test Summary\n\nThis is a test.")

        content = summary_file.read_text()
        assert "# Test Summary" in content


# =============================================================================
# NotificationPayload Tests
# =============================================================================


class TestNotificationPayload:
    """Tests for NotificationPayload dataclass."""

    def test_basic_payload(self):
        """Test basic payload creation."""
        payload = NotificationPayload(
            title="Test Alert",
            message="This is a test",
        )

        assert payload.title == "Test Alert"
        assert payload.message == "This is a test"
        assert payload.severity == "info"

    def test_error_payload(self):
        """Test error severity payload."""
        payload = NotificationPayload(
            title="Error Alert",
            message="Something went wrong",
            severity="error",
            details={"error_code": "E001"},
        )

        assert payload.severity == "error"
        assert payload.details["error_code"] == "E001"

    def test_to_slack_payload(self):
        """Test Slack payload generation."""
        payload = NotificationPayload(
            title="Test",
            message="Test message",
            severity="warning",
            details={"key": "value"},
        )

        slack_payload = payload.to_slack_payload()

        assert "attachments" in slack_payload
        assert slack_payload["attachments"][0]["color"] == "#ffcc00"
        assert slack_payload["attachments"][0]["title"] == "Test"

    def test_to_discord_payload(self):
        """Test Discord payload generation."""
        payload = NotificationPayload(
            title="Test",
            message="Test message",
            severity="error",
            run_url="https://example.com/run/123",
        )

        discord_payload = payload.to_discord_payload()

        assert "embeds" in discord_payload
        assert discord_payload["embeds"][0]["color"] == 15158332  # Red
        assert discord_payload["embeds"][0]["url"] == "https://example.com/run/123"


# =============================================================================
# Integration Tests
# =============================================================================


class TestCIHelpersIntegration:
    """Integration tests for CI helpers."""

    @pytest.mark.integration
    def test_full_drift_check_workflow(self, tmp_path):
        """Test complete drift check workflow."""
        # Create mock schema and snapshot directories
        schema_dir = tmp_path / "schemas"
        snapshot_dir = tmp_path / "snapshots"
        schema_dir.mkdir()
        snapshot_dir.mkdir()

        # Run drift checker
        checker = DriftChecker(
            schema_dir=schema_dir,
            snapshot_dir=snapshot_dir,
        )

        result = checker.check_drift()

        # Should complete without error
        assert isinstance(result, DriftResult)

        # Save result
        output = checker.save_result(result, tmp_path / "result.json")
        assert output.exists()

    @pytest.mark.integration
    def test_cassette_update_workflow(self, tmp_path):
        """Test complete cassette update workflow."""
        cassette_dir = tmp_path / "cassettes"
        cassette_dir.mkdir()

        updater = CassetteUpdater(
            cassette_dir=cassette_dir,
            civicrm_version="5.74",
        )

        # Should complete without error
        summary = updater.create_update_summary()
        assert isinstance(summary, CassetteUpdateSummary)

        # Generate markdown
        markdown = summary.to_markdown()
        assert "## Cassette Update Summary" in markdown
