"""CiviCRM version compatibility matrix and API difference tracking.

This module provides infrastructure for testing civi-py against multiple
CiviCRM versions, tracking API differences, and managing version-specific
cassettes.

Architecture:
    VersionInfo - Dataclass containing version metadata and capabilities
    APIDifference - Describes a specific API difference between versions
    VersionMatrix - Registry of supported versions and their differences
    VersionDetector - Detects CiviCRM version from live instance

Example:
    >>> from tests.compat.version_matrix import VersionMatrix, get_version_matrix
    >>>
    >>> # Get the version matrix
    >>> matrix = get_version_matrix()
    >>>
    >>> # Check if a version is supported
    >>> if matrix.is_supported("5.74.0"):
    ...     version_info = matrix.get_version("5.74")
    ...     print(f"Supported since: {version_info.release_date}")
    >>> # Get API differences for a version
    >>> differences = matrix.get_differences_since("5.60")
    >>> for diff in differences:
    ...     print(f"{diff.entity}.{diff.field}: {diff.description}")

Pytest Integration:
    @pytest.mark.skip_version("5.60", reason="Feature not available")
    def test_new_feature():
        ...

    @pytest.mark.min_version("5.70")
    def test_requires_modern_api():
        ...
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient


class DifferenceType(Enum):
    """Type of API difference between CiviCRM versions.

    Attributes:
        FIELD_ADDED: A new field was added to an entity.
        FIELD_REMOVED: A field was removed from an entity.
        FIELD_RENAMED: A field was renamed.
        FIELD_TYPE_CHANGED: A field's data type changed.
        FIELD_DEPRECATED: A field was marked as deprecated.
        ACTION_ADDED: A new action was added to an entity.
        ACTION_REMOVED: An action was removed.
        ACTION_CHANGED: An action's behavior changed.
        ENTITY_ADDED: A new entity was added.
        ENTITY_REMOVED: An entity was removed.
        ENTITY_RENAMED: An entity was renamed.
        BEHAVIOR_CHANGED: General behavior change without schema change.
        DEFAULT_CHANGED: Default value for a field changed.
        VALIDATION_CHANGED: Validation rules changed.
        PERMISSION_CHANGED: Permission requirements changed.
    """

    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_RENAMED = "field_renamed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    FIELD_DEPRECATED = "field_deprecated"
    ACTION_ADDED = "action_added"
    ACTION_REMOVED = "action_removed"
    ACTION_CHANGED = "action_changed"
    ENTITY_ADDED = "entity_added"
    ENTITY_REMOVED = "entity_removed"
    ENTITY_RENAMED = "entity_renamed"
    BEHAVIOR_CHANGED = "behavior_changed"
    DEFAULT_CHANGED = "default_changed"
    VALIDATION_CHANGED = "validation_changed"
    PERMISSION_CHANGED = "permission_changed"


class Severity(Enum):
    """Severity level for API differences.

    Attributes:
        BREAKING: Breaking change that requires code modification.
        DEPRECATION: Feature is deprecated and will be removed.
        ENHANCEMENT: Non-breaking enhancement or addition.
        INFO: Informational change with no impact.
    """

    BREAKING = "breaking"
    DEPRECATION = "deprecation"
    ENHANCEMENT = "enhancement"
    INFO = "info"


@dataclass(frozen=True)
class APIDifference:
    """Describes a specific API difference between CiviCRM versions.

    Attributes:
        entity: The CiviCRM entity affected (e.g., "Contact", "Activity").
        difference_type: Type of difference (field added, removed, etc.).
        introduced_in: Version where this change was introduced.
        severity: Severity level of the change.
        field: Field name if applicable.
        action: Action name if applicable.
        old_value: Previous value/behavior (for changes).
        new_value: New value/behavior.
        description: Human-readable description of the change.
        workaround: Suggested workaround for breaking changes.
        migration_guide: Link or text for migration guidance.
        removed_in: Version where deprecated feature was removed.
    """

    entity: str
    difference_type: DifferenceType
    introduced_in: str
    severity: Severity
    field: str | None = None
    action: str | None = None
    old_value: Any = None
    new_value: Any = None
    description: str = ""
    workaround: str | None = None
    migration_guide: str | None = None
    removed_in: str | None = None

    def __post_init__(self) -> None:
        """Validate the difference configuration."""
        if (
            self.difference_type
            in (
                DifferenceType.FIELD_ADDED,
                DifferenceType.FIELD_REMOVED,
                DifferenceType.FIELD_RENAMED,
                DifferenceType.FIELD_TYPE_CHANGED,
                DifferenceType.FIELD_DEPRECATED,
                DifferenceType.DEFAULT_CHANGED,
            )
            and not self.field
        ):
            msg = f"Field-related difference type {self.difference_type} requires a field name"
            raise ValueError(msg)

        if (
            self.difference_type
            in (
                DifferenceType.ACTION_ADDED,
                DifferenceType.ACTION_REMOVED,
                DifferenceType.ACTION_CHANGED,
            )
            and not self.action
        ):
            msg = f"Action-related difference type {self.difference_type} requires an action name"
            raise ValueError(msg)

    @property
    def is_breaking(self) -> bool:
        """Check if this is a breaking change."""
        return self.severity == Severity.BREAKING

    @property
    def is_deprecated(self) -> bool:
        """Check if this is a deprecation."""
        return self.severity == Severity.DEPRECATION

    @property
    def key(self) -> str:
        """Get a unique key for this difference."""
        parts = [self.entity, self.difference_type.value]
        if self.field:
            parts.append(self.field)
        if self.action:
            parts.append(self.action)
        return ":".join(parts)

    def affects_version(self, version: str) -> bool:
        """Check if this difference affects the given version.

        Args:
            version: Version string to check.

        Returns:
            True if the difference is relevant for this version.
        """
        return _compare_versions(version, self.introduced_in) >= 0

    def format_message(self) -> str:
        """Format a human-readable message about this difference."""
        parts = [f"[{self.severity.value.upper()}]"]

        if self.entity:
            parts.append(self.entity)
        if self.field:
            parts.append(f".{self.field}")
        if self.action:
            parts.append(f":{self.action}")

        parts.append(f" ({self.difference_type.value})")

        if self.description:
            parts.append(f": {self.description}")

        return "".join(parts)


@dataclass
class VersionInfo:
    """Metadata about a specific CiviCRM version.

    Attributes:
        version: The version string (e.g., "5.74.0").
        api_version: The API version (always 4 for API v4).
        release_date: When this version was released.
        end_of_life: When support ends (if known).
        is_lts: Whether this is a Long Term Support version.
        php_min_version: Minimum required PHP version.
        php_max_version: Maximum supported PHP version.
        mysql_min_version: Minimum required MySQL version.
        docker_image: Official Docker image tag for this version.
        docker_image_alt: Alternative Docker image (e.g., community builds).
        known_issues: List of known issues affecting this version.
        notes: Additional notes about this version.
        features: New features introduced in this version.
        deprecations: Features deprecated in this version.
    """

    version: str
    api_version: int = 4
    release_date: date | None = None
    end_of_life: date | None = None
    is_lts: bool = False
    php_min_version: str = "8.0"
    php_max_version: str | None = None
    mysql_min_version: str = "5.7"
    docker_image: str | None = None
    docker_image_alt: str | None = None
    known_issues: list[str] = field(default_factory=list)
    notes: str = ""
    features: list[str] = field(default_factory=list)
    deprecations: list[str] = field(default_factory=list)

    @property
    def major_version(self) -> int:
        """Get the major version number."""
        return int(self.version.split(".")[0])

    @property
    def minor_version(self) -> int:
        """Get the minor version number."""
        parts = self.version.split(".")
        return int(parts[1]) if len(parts) > 1 else 0

    @property
    def patch_version(self) -> int:
        """Get the patch version number."""
        parts = self.version.split(".")
        return int(parts[2]) if len(parts) > 2 else 0

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        """Get version as a tuple for comparison."""
        return (self.major_version, self.minor_version, self.patch_version)

    @property
    def short_version(self) -> str:
        """Get short version string (major.minor)."""
        return f"{self.major_version}.{self.minor_version}"

    @property
    def cassette_dir(self) -> str:
        """Get the cassette directory name for this version."""
        return f"v{self.short_version}"

    @property
    def is_active(self) -> bool:
        """Check if this version is still actively supported."""
        if self.end_of_life is None:
            return True
        # Import datetime for timezone-aware date comparison
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).date()
        return today < self.end_of_life

    def supports_php(self, php_version: str) -> bool:
        """Check if this version supports the given PHP version.

        Args:
            php_version: PHP version string (e.g., "8.1").

        Returns:
            True if PHP version is supported.
        """
        if _compare_versions(php_version, self.php_min_version) < 0:
            return False
        return not (self.php_max_version and _compare_versions(php_version, self.php_max_version) > 0)

    def get_docker_image(self) -> str:
        """Get the Docker image for this version.

        Returns:
            Docker image reference.

        Raises:
            ValueError: If no Docker image is configured.
        """
        if self.docker_image:
            return self.docker_image
        if self.docker_image_alt:
            return self.docker_image_alt
        # Default CiviCRM Docker image pattern
        return f"civicrm/civicrm:{self.version}"

    def __lt__(self, other: VersionInfo) -> bool:
        """Compare versions for sorting."""
        return self.version_tuple < other.version_tuple

    def __le__(self, other: VersionInfo) -> bool:
        """Compare versions for sorting."""
        return self.version_tuple <= other.version_tuple


class VersionMatrix:
    """Registry of supported CiviCRM versions and their differences.

    This class manages the compatibility matrix between civi-py and
    various CiviCRM versions, including tracking of API differences.

    Attributes:
        versions: Dictionary of version string to VersionInfo.
        differences: List of API differences across versions.
    """

    # Class-level cache of the default matrix
    _default_instance: ClassVar[VersionMatrix | None] = None

    def __init__(self) -> None:
        """Initialize an empty version matrix."""
        self._versions: dict[str, VersionInfo] = {}
        self._differences: list[APIDifference] = []
        self._differences_by_entity: dict[str, list[APIDifference]] = {}
        self._differences_by_version: dict[str, list[APIDifference]] = {}

    def register_version(self, version_info: VersionInfo) -> None:
        """Register a supported CiviCRM version.

        Args:
            version_info: Version metadata to register.
        """
        self._versions[version_info.version] = version_info
        # Also register short version for lookup
        self._versions[version_info.short_version] = version_info

    def register_difference(self, difference: APIDifference) -> None:
        """Register an API difference.

        Args:
            difference: API difference to register.
        """
        self._differences.append(difference)

        # Index by entity
        if difference.entity not in self._differences_by_entity:
            self._differences_by_entity[difference.entity] = []
        self._differences_by_entity[difference.entity].append(difference)

        # Index by version
        if difference.introduced_in not in self._differences_by_version:
            self._differences_by_version[difference.introduced_in] = []
        self._differences_by_version[difference.introduced_in].append(difference)

    def get_version(self, version: str) -> VersionInfo | None:
        """Get version info for a specific version.

        Args:
            version: Version string (full or short).

        Returns:
            VersionInfo or None if not found.
        """
        return self._versions.get(version)

    def get_closest_version(self, version: str) -> VersionInfo | None:
        """Get the closest matching version info.

        Args:
            version: Version string to match.

        Returns:
            Closest matching VersionInfo or None.
        """
        # Try exact match first
        if version in self._versions:
            return self._versions[version]

        # Parse the target version
        target = _parse_version(version)
        if target is None:
            return None

        # Find the closest version that's <= target
        best_match: VersionInfo | None = None
        for info in self._versions.values():
            if info.version_tuple <= target and (best_match is None or info.version_tuple > best_match.version_tuple):
                best_match = info

        return best_match

    def is_supported(self, version: str) -> bool:
        """Check if a version is supported.

        Args:
            version: Version string to check.

        Returns:
            True if version is supported.
        """
        return self.get_closest_version(version) is not None

    def get_supported_versions(self) -> list[VersionInfo]:
        """Get all supported versions.

        Returns:
            List of supported versions, sorted by version number.
        """
        # Get unique VersionInfo objects (avoid duplicates from short versions)
        seen = set()
        versions = []
        for info in self._versions.values():
            if info.version not in seen:
                seen.add(info.version)
                versions.append(info)
        return sorted(versions)

    def get_active_versions(self) -> list[VersionInfo]:
        """Get versions that are still actively supported.

        Returns:
            List of active versions.
        """
        return [v for v in self.get_supported_versions() if v.is_active]

    def get_lts_versions(self) -> list[VersionInfo]:
        """Get Long Term Support versions.

        Returns:
            List of LTS versions.
        """
        return [v for v in self.get_supported_versions() if v.is_lts]

    def get_differences(
        self,
        entity: str | None = None,
        severity: Severity | None = None,
        difference_type: DifferenceType | None = None,
    ) -> list[APIDifference]:
        """Get API differences with optional filtering.

        Args:
            entity: Filter by entity name.
            severity: Filter by severity level.
            difference_type: Filter by difference type.

        Returns:
            List of matching differences.
        """
        differences = self._differences

        if entity:
            differences = [d for d in differences if d.entity == entity]

        if severity:
            differences = [d for d in differences if d.severity == severity]

        if difference_type:
            differences = [d for d in differences if d.difference_type == difference_type]

        return differences

    def get_differences_for_entity(self, entity: str) -> list[APIDifference]:
        """Get all differences for a specific entity.

        Args:
            entity: Entity name.

        Returns:
            List of differences for the entity.
        """
        return self._differences_by_entity.get(entity, [])

    def get_differences_since(self, version: str) -> list[APIDifference]:
        """Get all differences introduced since a version.

        Args:
            version: Version to compare from.

        Returns:
            List of differences introduced after the version.
        """
        return [diff for diff in self._differences if _compare_versions(diff.introduced_in, version) > 0]

    def get_differences_between(self, from_version: str, to_version: str) -> list[APIDifference]:
        """Get differences between two versions.

        Args:
            from_version: Starting version.
            to_version: Ending version.

        Returns:
            List of differences between the versions.
        """
        return [
            diff
            for diff in self._differences
            if (
                _compare_versions(diff.introduced_in, from_version) > 0
                and _compare_versions(diff.introduced_in, to_version) <= 0
            )
        ]

    def get_breaking_changes(self, since_version: str | None = None) -> list[APIDifference]:
        """Get breaking changes, optionally since a version.

        Args:
            since_version: Only include changes after this version.

        Returns:
            List of breaking changes.
        """
        changes = self.get_differences(severity=Severity.BREAKING)
        if since_version:
            changes = [c for c in changes if _compare_versions(c.introduced_in, since_version) > 0]
        return changes

    def get_deprecations(self, version: str | None = None) -> list[APIDifference]:
        """Get deprecations, optionally for a specific version.

        Args:
            version: Filter deprecations affecting this version.

        Returns:
            List of deprecations.
        """
        deprecations = self.get_differences(severity=Severity.DEPRECATION)
        if version:
            deprecations = [d for d in deprecations if d.affects_version(version)]
        return deprecations

    def format_changelog(self, from_version: str, to_version: str) -> str:
        """Format a changelog between two versions.

        Args:
            from_version: Starting version.
            to_version: Ending version.

        Returns:
            Formatted changelog string.
        """
        differences = self.get_differences_between(from_version, to_version)

        if not differences:
            return f"No API differences between {from_version} and {to_version}"

        lines = [f"API Changes from {from_version} to {to_version}:", ""]

        # Group by severity
        by_severity: dict[Severity, list[APIDifference]] = {}
        for diff in differences:
            if diff.severity not in by_severity:
                by_severity[diff.severity] = []
            by_severity[diff.severity].append(diff)

        for severity in [Severity.BREAKING, Severity.DEPRECATION, Severity.ENHANCEMENT, Severity.INFO]:
            if severity in by_severity:
                lines.append(f"## {severity.value.title()} Changes")
                lines.append("")
                lines.extend(f"- {diff.format_message()}" for diff in by_severity[severity])
                lines.append("")

        return "\n".join(lines)


class VersionDetector:
    """Detects CiviCRM version from a live instance.

    This class can query a CiviCRM instance to determine its version,
    which is useful for:
    - Selecting appropriate cassettes for testing
    - Validating version-specific features
    - Auto-configuring the client for version differences
    """

    def __init__(self, client: CiviClient) -> None:
        """Initialize the version detector.

        Args:
            client: CiviClient instance to use for detection.
        """
        self._client = client
        self._cached_version: str | None = None
        self._cached_info: dict[str, Any] | None = None

    async def detect_version(self) -> str:
        """Detect the CiviCRM version from the instance.

        Returns:
            Version string (e.g., "5.74.0").

        Raises:
            CiviAPIError: If version detection fails.
        """
        if self._cached_version is not None:
            return self._cached_version

        # CiviCRM API v4 has a System.get action that returns version info
        response = await self._client.request("System", "get", {"select": ["version"]})

        if response.values:
            version = response.values[0].get("version", "")
            self._cached_version = version
            return version

        msg = "Could not detect CiviCRM version"
        raise RuntimeError(msg)

    async def detect_full_info(self) -> dict[str, Any]:
        """Detect full system information from the instance.

        Returns:
            Dictionary with system information.
        """
        if self._cached_info is not None:
            return self._cached_info

        response = await self._client.request("System", "get", {})

        if response.values:
            self._cached_info = response.values[0]
            return self._cached_info

        return {}

    async def get_api_version(self) -> int:
        """Get the API version (always 4 for CiviCRM API v4).

        Returns:
            API version number.
        """
        return 4

    async def get_version_info(self, matrix: VersionMatrix) -> VersionInfo | None:
        """Get VersionInfo from the matrix for the detected version.

        Args:
            matrix: Version matrix to look up in.

        Returns:
            VersionInfo for the detected version.
        """
        version = await self.detect_version()
        return matrix.get_closest_version(version)

    def clear_cache(self) -> None:
        """Clear the cached version information."""
        self._cached_version = None
        self._cached_info = None


def _parse_version(version: str) -> tuple[int, int, int] | None:
    """Parse a version string into a tuple.

    Args:
        version: Version string (e.g., "5.74.0", "5.74").

    Returns:
        Tuple of (major, minor, patch) or None if invalid.
    """
    # Handle versions like "5.74.0", "5.74", "5"
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0

    return (major, minor, patch)


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings.

    Args:
        v1: First version.
        v2: Second version.

    Returns:
        -1 if v1 < v2, 0 if equal, 1 if v1 > v2.
    """
    t1 = _parse_version(v1)
    t2 = _parse_version(v2)

    if t1 is None or t2 is None:
        # Fall back to string comparison
        return -1 if v1 < v2 else (1 if v1 > v2 else 0)

    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0


def _create_default_matrix() -> VersionMatrix:
    """Create the default version matrix with known CiviCRM versions.

    Returns:
        Configured VersionMatrix instance.
    """
    matrix = VersionMatrix()

    # Register supported CiviCRM versions
    # 5.60.x series (older LTS)
    matrix.register_version(
        VersionInfo(
            version="5.60.0",
            release_date=date(2023, 4, 5),
            end_of_life=date(2024, 4, 5),
            is_lts=True,
            php_min_version="7.4",
            php_max_version="8.1",
            mysql_min_version="5.7",
            docker_image="civicrm/civicrm:5.60",
            notes="Last version supporting PHP 7.4",
            features=["Improved SearchKit", "Enhanced FormBuilder"],
        ),
    )

    # 5.63.x series
    matrix.register_version(
        VersionInfo(
            version="5.63.0",
            release_date=date(2023, 7, 5),
            php_min_version="7.4",
            php_max_version="8.2",
            docker_image="civicrm/civicrm:5.63",
        ),
    )

    # 5.65.x series
    matrix.register_version(
        VersionInfo(
            version="5.65.0",
            release_date=date(2023, 9, 6),
            php_min_version="8.0",
            php_max_version="8.2",
            docker_image="civicrm/civicrm:5.65",
            notes="Dropped PHP 7.4 support",
        ),
    )

    # 5.68.x series (LTS)
    matrix.register_version(
        VersionInfo(
            version="5.68.0",
            release_date=date(2023, 12, 6),
            end_of_life=date(2025, 6, 1),
            is_lts=True,
            php_min_version="8.0",
            php_max_version="8.2",
            docker_image="civicrm/civicrm:5.68-latest",
            features=["CiviImport overhaul", "CiviGrant as extension"],
        ),
    )

    # 5.70.x series
    matrix.register_version(
        VersionInfo(
            version="5.70.0",
            release_date=date(2024, 2, 7),
            php_min_version="8.0",
            php_max_version="8.3",
            docker_image="civicrm/civicrm:5.70",
            features=["PHP 8.3 support", "Improved API performance"],
        ),
    )

    # 5.72.x series
    matrix.register_version(
        VersionInfo(
            version="5.72.0",
            release_date=date(2024, 4, 3),
            php_min_version="8.0",
            php_max_version="8.3",
            docker_image="civicrm/civicrm:5.72",
        ),
    )

    # 5.74.x series
    matrix.register_version(
        VersionInfo(
            version="5.74.0",
            release_date=date(2024, 6, 5),
            php_min_version="8.1",
            php_max_version="8.3",
            docker_image="civicrm/civicrm:5.74",
            notes="Dropped PHP 8.0 support",
        ),
    )

    # 5.76.x series (LTS)
    matrix.register_version(
        VersionInfo(
            version="5.76.0",
            release_date=date(2024, 8, 7),
            end_of_life=date(2026, 2, 1),
            is_lts=True,
            php_min_version="8.1",
            php_max_version="8.3",
            docker_image="civicrm/civicrm:5.76-latest",
            features=["New SearchKit features", "Improved OAuth support"],
        ),
    )

    # 5.78.x series
    matrix.register_version(
        VersionInfo(
            version="5.78.0",
            release_date=date(2024, 10, 2),
            php_min_version="8.1",
            php_max_version="8.4",
            docker_image="civicrm/civicrm:5.78",
            features=["PHP 8.4 support"],
        ),
    )

    # 5.80.x series
    matrix.register_version(
        VersionInfo(
            version="5.80.0",
            release_date=date(2024, 12, 4),
            php_min_version="8.1",
            php_max_version="8.4",
            docker_image="civicrm/civicrm:5.80",
            docker_image_alt="civicrm/civicrm:latest",
            features=["Enhanced API v4 features"],
        ),
    )

    # Register known API differences
    _register_known_differences(matrix)

    return matrix


def _register_known_differences(matrix: VersionMatrix) -> None:
    """Register known API differences between CiviCRM versions.

    Args:
        matrix: Version matrix to register differences in.
    """
    # 5.65: PHP 7.4 dropped
    matrix.register_difference(
        APIDifference(
            entity="System",
            difference_type=DifferenceType.BEHAVIOR_CHANGED,
            introduced_in="5.65.0",
            severity=Severity.INFO,
            description="PHP 7.4 support dropped; minimum is now PHP 8.0",
        ),
    )

    # 5.68: CiviGrant became extension
    matrix.register_difference(
        APIDifference(
            entity="Grant",
            difference_type=DifferenceType.ENTITY_REMOVED,
            introduced_in="5.68.0",
            severity=Severity.BREAKING,
            description="CiviGrant moved to optional extension",
            workaround="Install civigrant extension to use Grant entity",
        ),
    )

    # 5.70: Contact.preferred_communication_method behavior
    matrix.register_difference(
        APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_TYPE_CHANGED,
            introduced_in="5.70.0",
            severity=Severity.DEPRECATION,
            field="preferred_communication_method",
            old_value="String",
            new_value="Array",
            description="preferred_communication_method now returns array instead of string",
            workaround="Update code to handle array values",
        ),
    )

    # 5.72: Activity.original_id deprecated
    matrix.register_difference(
        APIDifference(
            entity="Activity",
            difference_type=DifferenceType.FIELD_DEPRECATED,
            introduced_in="5.72.0",
            severity=Severity.DEPRECATION,
            field="original_id",
            description="Activity.original_id is deprecated, use parent_id",
            workaround="Use parent_id instead of original_id",
            removed_in="6.0",
        ),
    )

    # 5.74: PHP 8.0 dropped
    matrix.register_difference(
        APIDifference(
            entity="System",
            difference_type=DifferenceType.BEHAVIOR_CHANGED,
            introduced_in="5.74.0",
            severity=Severity.INFO,
            description="PHP 8.0 support dropped; minimum is now PHP 8.1",
        ),
    )

    # 5.76: New SearchKit capabilities
    matrix.register_difference(
        APIDifference(
            entity="SearchDisplay",
            difference_type=DifferenceType.ACTION_ADDED,
            introduced_in="5.76.0",
            severity=Severity.ENHANCEMENT,
            action="getLinks",
            description="New getLinks action for retrieving display links",
        ),
    )

    # 5.78: PHP 8.4 support
    matrix.register_difference(
        APIDifference(
            entity="System",
            difference_type=DifferenceType.BEHAVIOR_CHANGED,
            introduced_in="5.78.0",
            severity=Severity.ENHANCEMENT,
            description="Added PHP 8.4 support",
        ),
    )

    # 5.80: Enhanced batch operations
    matrix.register_difference(
        APIDifference(
            entity="Contact",
            difference_type=DifferenceType.ACTION_ADDED,
            introduced_in="5.80.0",
            severity=Severity.ENHANCEMENT,
            action="merge",
            description="Enhanced merge action with better duplicate handling",
        ),
    )

    # Common deprecations across versions
    matrix.register_difference(
        APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_DEPRECATED,
            introduced_in="5.60.0",
            severity=Severity.DEPRECATION,
            field="contact_is_deleted",
            description="Use is_deleted instead of contact_is_deleted",
            workaround="Replace contact_is_deleted with is_deleted",
        ),
    )


@lru_cache(maxsize=1)
def get_version_matrix() -> VersionMatrix:
    """Get the default version matrix singleton.

    Returns:
        Configured VersionMatrix instance.
    """
    return _create_default_matrix()


def get_current_version() -> str:
    """Get the current CiviCRM version from environment.

    Reads from CIVI_VERSION environment variable.

    Returns:
        Version string or "default" if not set.
    """
    return os.environ.get("CIVI_VERSION", "default")


def get_cassette_version() -> str:
    """Get the cassette directory version.

    Returns:
        Version string for cassette directory naming.
    """
    version = get_current_version()
    if version == "default":
        return "default"

    # Parse to get short version (5.74 from 5.74.0)
    parsed = _parse_version(version)
    if parsed:
        return f"{parsed[0]}.{parsed[1]}"

    return version


def skip_for_version(
    current_version: str,
    skip_versions: list[str] | None = None,
    min_version: str | None = None,
    max_version: str | None = None,
    reason: str = "",
) -> str | None:
    """Check if a test should be skipped for the given version.

    Args:
        current_version: The current CiviCRM version.
        skip_versions: List of specific versions to skip.
        min_version: Minimum required version.
        max_version: Maximum supported version.
        reason: Reason for skipping.

    Returns:
        Skip reason string if should skip, None otherwise.
    """
    if current_version == "default":
        return None  # Don't skip for default/unknown versions

    if skip_versions:
        for skip_v in skip_versions:
            if current_version.startswith(skip_v):
                return reason or f"Test skipped for version {skip_v}"

    if min_version and _compare_versions(current_version, min_version) < 0:
        return reason or f"Test requires CiviCRM {min_version} or later"

    if max_version and _compare_versions(current_version, max_version) > 0:
        return reason or f"Test not supported after CiviCRM {max_version}"

    return None


__all__ = [
    "APIDifference",
    "DifferenceType",
    "Severity",
    "VersionDetector",
    "VersionInfo",
    "VersionMatrix",
    "get_cassette_version",
    "get_current_version",
    "get_version_matrix",
    "skip_for_version",
]
