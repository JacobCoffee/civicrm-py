"""CI helper utilities for nightly compatibility testing.

This module provides utilities for running compatibility tests in CI environments,
including drift detection, cassette management, and notification helpers.

Phase 8.5.12: Nightly CI workflow support

Usage:
    # Check for schema drift
    from tests.compat.ci_helpers import DriftChecker
    checker = DriftChecker()
    result = checker.check_drift()
    if result.has_breaking_changes:
        print("Breaking changes detected!")

    # Manage cassettes in CI
    from tests.compat.ci_helpers import CassetteUpdater
    updater = CassetteUpdater()
    if updater.has_changes():
        updater.create_update_summary()
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# =============================================================================
# Constants
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent.parent
CASSETTE_DIR = REPO_ROOT / "tests" / "cassettes"
SCHEMA_DIR = REPO_ROOT / "tests" / "compat" / "schemas"
SNAPSHOT_DIR = SCHEMA_DIR / "snapshots"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class DriftResult:
    """Result of drift detection check.

    Attributes:
        has_drift: True if any schema changes detected.
        has_breaking_changes: True if breaking changes detected.
        entities_changed: List of entities with changes.
        breaking_entities: List of entities with breaking changes.
        summary: Human-readable summary of changes.
        details: Detailed change information.
    """

    has_drift: bool = False
    has_breaking_changes: bool = False
    entities_changed: list[str] = field(default_factory=list)
    breaking_entities: list[str] = field(default_factory=list)
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "has_drift": self.has_drift,
            "has_breaking_changes": self.has_breaking_changes,
            "entities_changed": self.entities_changed,
            "breaking_entities": self.breaking_entities,
            "summary": self.summary,
            "details": self.details,
            "timestamp": datetime.now(UTC).isoformat(),
        }


@dataclass
class CassetteChange:
    """Represents a change to a cassette file.

    Attributes:
        path: Path to the cassette file.
        change_type: Type of change (added, modified, deleted).
        entity: Entity name extracted from path.
        version: CiviCRM version from path.
    """

    path: Path
    change_type: str  # added, modified, deleted
    entity: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        """Extract entity and version from path."""
        parts = self.path.parts
        for i, part in enumerate(parts):
            if part.startswith("v") and i + 2 < len(parts):
                self.version = part.lstrip("v")
                if parts[i + 1] == "entities":
                    self.entity = self.path.stem


@dataclass
class CassetteUpdateSummary:
    """Summary of cassette changes.

    Attributes:
        changes: List of individual changes.
        total_added: Count of added cassettes.
        total_modified: Count of modified cassettes.
        total_deleted: Count of deleted cassettes.
        civicrm_version: CiviCRM version these changes are for.
    """

    changes: list[CassetteChange] = field(default_factory=list)
    total_added: int = 0
    total_modified: int = 0
    total_deleted: int = 0
    civicrm_version: str = ""

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self.changes) > 0

    def to_markdown(self) -> str:
        """Generate markdown summary of changes."""
        lines = [
            "## Cassette Update Summary",
            "",
            f"**CiviCRM Version**: {self.civicrm_version}",
            f"**Total Changes**: {len(self.changes)}",
            "",
            "| Change | File | Entity |",
            "|--------|------|--------|",
        ]

        for change in self.changes:
            emoji = {"added": "+", "modified": "~", "deleted": "-"}.get(
                change.change_type,
                "?",
            )
            lines.append(f"| {emoji} {change.change_type} | {change.path.name} | {change.entity} |")

        return "\n".join(lines)


# =============================================================================
# Drift Detection
# =============================================================================


class DriftChecker:
    """Check for CiviCRM API schema drift.

    This class compares current API schemas against stored snapshots
    to detect changes that may affect compatibility.

    Example:
        checker = DriftChecker()
        result = checker.check_drift()

        if result.has_breaking_changes:
            print(f"Breaking changes in: {result.breaking_entities}")
    """

    def __init__(
        self,
        schema_dir: Path | None = None,
        snapshot_dir: Path | None = None,
    ) -> None:
        """Initialize drift checker.

        Args:
            schema_dir: Directory containing current schemas.
            snapshot_dir: Directory containing schema snapshots.
        """
        self.schema_dir = schema_dir or SCHEMA_DIR
        self.snapshot_dir = snapshot_dir or SNAPSHOT_DIR

    def check_drift(self, entities: Sequence[str] | None = None) -> DriftResult:
        """Check for schema drift.

        Args:
            entities: Specific entities to check. If None, checks all.

        Returns:
            DriftResult with detection results.
        """
        result = DriftResult()

        try:
            # Import drift detector
            from tests.compat.drift_detector import DriftDetector, DriftMode
            from tests.compat.schema_validator import SchemaCache

            cache = SchemaCache(cache_dir=self.schema_dir)
            detector = DriftDetector(
                cache=cache,
                mode=DriftMode.REPORT,
                snapshot_dir=self.snapshot_dir,
            )

            # Run drift detection
            report = detector.check_all_cached()

            # Extract results
            result.has_drift = report.has_changes
            result.has_breaking_changes = report.has_breaking_changes

            for entity_change in report.entity_changes:
                result.entities_changed.append(entity_change.entity_name)
                if entity_change.has_breaking_changes:
                    result.breaking_entities.append(entity_change.entity_name)

            result.summary = report.format_summary()
            result.details = {
                "total_entities": len(report.entity_changes),
                "breaking_count": len(result.breaking_entities),
            }

        except ImportError:
            result.summary = "Drift detection modules not available"
        except Exception as e:
            result.summary = f"Drift detection error: {e}"

        return result

    def save_result(self, result: DriftResult, output_path: Path | None = None) -> Path:
        """Save drift result to JSON file.

        Args:
            result: Drift detection result.
            output_path: Output file path. Defaults to drift-result.json.

        Returns:
            Path to saved file.
        """
        output_path = output_path or Path("drift-result.json")
        with output_path.open("w") as f:
            json.dump(result.to_dict(), f, indent=2)
        return output_path


# =============================================================================
# Cassette Management
# =============================================================================


class CassetteUpdater:
    """Manage cassette updates in CI environments.

    This class helps track and commit cassette changes
    during nightly compatibility runs.

    Example:
        updater = CassetteUpdater()
        if updater.has_changes():
            summary = updater.create_update_summary()
            print(summary.to_markdown())
    """

    def __init__(
        self,
        cassette_dir: Path | None = None,
        civicrm_version: str | None = None,
    ) -> None:
        """Initialize cassette updater.

        Args:
            cassette_dir: Directory containing cassettes.
            civicrm_version: CiviCRM version for updates.
        """
        self.cassette_dir = cassette_dir or CASSETTE_DIR
        self.civicrm_version = civicrm_version or os.environ.get("CIVI_VERSION", "unknown")

    def has_changes(self) -> bool:
        """Check if there are uncommitted cassette changes.

        Returns:
            True if cassette files have been modified.
        """
        try:
            result = subprocess.run(  # noqa: S603
                ["git", "diff", "--quiet", str(self.cassette_dir)],  # noqa: S607
                capture_output=True,
                check=False,
                cwd=REPO_ROOT,
            )
            return result.returncode != 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def get_changes(self) -> list[CassetteChange]:
        """Get list of cassette changes.

        Returns:
            List of CassetteChange objects.
        """
        changes = []

        try:
            # Get modified files
            result = subprocess.run(  # noqa: S603
                ["git", "diff", "--name-status", str(self.cassette_dir)],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
                cwd=REPO_ROOT,
            )

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) >= 2:
                    status, path = parts[0], parts[1]
                    change_type = {
                        "A": "added",
                        "M": "modified",
                        "D": "deleted",
                    }.get(status, "unknown")

                    changes.append(
                        CassetteChange(
                            path=Path(path),
                            change_type=change_type,
                        ),
                    )

            # Also check for untracked files
            result = subprocess.run(  # noqa: S603
                ["git", "ls-files", "--others", "--exclude-standard", str(self.cassette_dir)],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
                cwd=REPO_ROOT,
            )

            changes.extend(
                CassetteChange(path=Path(line), change_type="added")
                for line in result.stdout.strip().split("\n")
                if line
            )

        except subprocess.SubprocessError:
            pass

        return changes

    def create_update_summary(self) -> CassetteUpdateSummary:
        """Create summary of cassette changes.

        Returns:
            CassetteUpdateSummary with all changes.
        """
        changes = self.get_changes()

        summary = CassetteUpdateSummary(
            changes=changes,
            civicrm_version=self.civicrm_version,
        )

        for change in changes:
            if change.change_type == "added":
                summary.total_added += 1
            elif change.change_type == "modified":
                summary.total_modified += 1
            elif change.change_type == "deleted":
                summary.total_deleted += 1

        return summary


# =============================================================================
# CI Environment Helpers
# =============================================================================


class CIEnvironment:
    """Helper for CI environment detection and configuration.

    Detects the CI environment (GitHub Actions, GitLab CI, etc.)
    and provides appropriate configuration.
    """

    def __init__(self) -> None:
        """Initialize CI environment helper."""
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        self.is_gitlab_ci = os.environ.get("GITLAB_CI") == "true"
        self.is_ci = os.environ.get("CI") == "true"

    @property
    def run_id(self) -> str:
        """Get CI run ID."""
        if self.is_github_actions:
            return os.environ.get("GITHUB_RUN_ID", "")
        if self.is_gitlab_ci:
            return os.environ.get("CI_PIPELINE_ID", "")
        return ""

    @property
    def repository(self) -> str:
        """Get repository name."""
        if self.is_github_actions:
            return os.environ.get("GITHUB_REPOSITORY", "")
        if self.is_gitlab_ci:
            return os.environ.get("CI_PROJECT_PATH", "")
        return ""

    @property
    def branch(self) -> str:
        """Get current branch name."""
        if self.is_github_actions:
            return os.environ.get("GITHUB_REF_NAME", "")
        if self.is_gitlab_ci:
            return os.environ.get("CI_COMMIT_REF_NAME", "")
        return ""

    def set_output(self, name: str, value: str) -> None:
        """Set CI output variable.

        Args:
            name: Output variable name.
            value: Output value.
        """
        if self.is_github_actions:
            # GitHub Actions output
            output_file = os.environ.get("GITHUB_OUTPUT")
            if output_file:
                with Path(output_file).open("a") as f:
                    f.write(f"{name}={value}\n")
            else:
                print(f"::set-output name={name}::{value}")  # noqa: T201

    def write_summary(self, content: str) -> None:
        """Write to CI job summary.

        Args:
            content: Markdown content for summary.
        """
        if self.is_github_actions:
            summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_file:
                with Path(summary_file).open("a") as f:
                    f.write(content)
                    f.write("\n")


# =============================================================================
# Notification Helpers
# =============================================================================


@dataclass
class NotificationPayload:
    """Notification payload for alerts.

    Attributes:
        title: Notification title.
        message: Main message content.
        severity: Severity level (info, warning, error).
        details: Additional details.
        run_url: URL to CI run.
    """

    title: str
    message: str
    severity: str = "info"  # info, warning, error
    details: dict[str, Any] = field(default_factory=dict)
    run_url: str = ""

    def to_slack_payload(self) -> dict[str, Any]:
        """Convert to Slack webhook payload."""
        color = {
            "info": "#36a64f",
            "warning": "#ffcc00",
            "error": "#ff0000",
        }.get(self.severity, "#808080")

        return {
            "attachments": [
                {
                    "color": color,
                    "title": self.title,
                    "text": self.message,
                    "fields": [{"title": k, "value": str(v), "short": True} for k, v in self.details.items()],
                    "footer": "civi-py Nightly Compatibility",
                    "ts": int(datetime.now(UTC).timestamp()),
                },
            ],
        }

    def to_discord_payload(self) -> dict[str, Any]:
        """Convert to Discord webhook payload."""
        color = {
            "info": 3066993,  # Green
            "warning": 16776960,  # Yellow
            "error": 15158332,  # Red
        }.get(self.severity, 8421504)  # Gray

        return {
            "embeds": [
                {
                    "title": self.title,
                    "description": self.message,
                    "color": color,
                    "fields": [{"name": k, "value": str(v), "inline": True} for k, v in self.details.items()],
                    "url": self.run_url,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            ],
        }


def send_slack_notification(
    webhook_url: str,
    payload: NotificationPayload,
) -> bool:
    """Send notification to Slack webhook.

    Args:
        webhook_url: Slack incoming webhook URL.
        payload: Notification payload.

    Returns:
        True if notification sent successfully.
    """
    try:
        import httpx

        response = httpx.post(
            webhook_url,
            json=payload.to_slack_payload(),
            timeout=10.0,
        )
        return response.status_code == 200
    except Exception:
        return False


def send_discord_notification(
    webhook_url: str,
    payload: NotificationPayload,
) -> bool:
    """Send notification to Discord webhook.

    Args:
        webhook_url: Discord webhook URL.
        payload: Notification payload.

    Returns:
        True if notification sent successfully.
    """
    try:
        import httpx

        response = httpx.post(
            webhook_url,
            json=payload.to_discord_payload(),
            timeout=10.0,
        )
        return response.status_code in (200, 204)
    except Exception:
        return False


# =============================================================================
# CLI Interface
# =============================================================================


def main() -> int:
    """CLI entrypoint for CI helpers.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="CI helper utilities for civi-py compatibility testing",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Drift check command
    drift_parser = subparsers.add_parser("drift", help="Check for schema drift")
    drift_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("drift-result.json"),
        help="Output file for results",
    )
    drift_parser.add_argument(
        "--fail-on-breaking",
        action="store_true",
        help="Exit with error if breaking changes detected",
    )

    # Cassette check command
    cassette_parser = subparsers.add_parser("cassettes", help="Check cassette changes")
    cassette_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print markdown summary",
    )

    args = parser.parse_args()

    if args.command == "drift":
        checker = DriftChecker()
        result = checker.check_drift()

        # Save result
        checker.save_result(result, args.output)

        # Print summary
        print(f"Drift detected: {result.has_drift}")  # noqa: T201
        print(f"Breaking changes: {result.has_breaking_changes}")  # noqa: T201

        if result.summary:
            print(f"\n{result.summary}")  # noqa: T201

        # Set CI outputs
        ci = CIEnvironment()
        ci.set_output("drift_detected", str(result.has_drift).lower())
        ci.set_output("breaking_changes", str(result.has_breaking_changes).lower())

        if args.fail_on_breaking and result.has_breaking_changes:
            return 1

    elif args.command == "cassettes":
        updater = CassetteUpdater()

        if updater.has_changes():
            summary = updater.create_update_summary()

            if args.summary:
                print(summary.to_markdown())  # noqa: T201
            else:
                print(f"Changes detected: {len(summary.changes)}")  # noqa: T201
                print(f"  Added: {summary.total_added}")  # noqa: T201
                print(f"  Modified: {summary.total_modified}")  # noqa: T201
                print(f"  Deleted: {summary.total_deleted}")  # noqa: T201

            # Set CI outputs
            ci = CIEnvironment()
            ci.set_output("cassettes_changed", "true")
            ci.set_output("change_count", str(len(summary.changes)))
        else:
            print("No cassette changes detected.")  # noqa: T201
            ci = CIEnvironment()
            ci.set_output("cassettes_changed", "false")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
