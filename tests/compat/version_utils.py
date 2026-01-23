"""Version utilities for CiviCRM compatibility testing.

This module provides utilities for comparing CiviCRM versions and
implementing version-based test skipping logic.

Example:
    from tests.compat.version_utils import CiviVersion, version_satisfies

    # Check if current version meets requirement
    current = CiviVersion.from_env()
    if current >= CiviVersion(5, 70):
        # Use 5.70+ features
        ...

    # Use with pytest markers
    @pytest.mark.min_version("5.70")
    def test_new_feature():
        ...
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class VersionConstraint(Enum):
    """Types of version constraints for test filtering.

    Attributes:
        MINIMUM: Test requires at least this version.
        MAXIMUM: Test requires at most this version (exclusive).
        EXACT: Test requires exactly this version.
        RANGE: Test requires version within a range.
    """

    MINIMUM = "min"
    MAXIMUM = "max"
    EXACT = "exact"
    RANGE = "range"


@total_ordering
@dataclass(frozen=True)
class CiviVersion:
    """Represents a CiviCRM version for comparison.

    CiviCRM versions follow semantic versioning (MAJOR.MINOR.PATCH).
    This class enables version comparisons for conditional test execution.

    Attributes:
        major: Major version number (e.g., 5 for CiviCRM 5.x).
        minor: Minor version number (e.g., 70 for CiviCRM 5.70).
        patch: Patch version number (default 0).

    Example:
        v570 = CiviVersion(5, 70)
        v580 = CiviVersion(5, 80)

        assert v570 < v580
        assert v570 >= CiviVersion(5, 60)
    """

    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        """Return string representation (e.g., '5.70.0')."""
        if self.patch:
            return f"{self.major}.{self.minor}.{self.patch}"
        return f"{self.major}.{self.minor}"

    def __repr__(self) -> str:
        """Return debug representation."""
        return f"CiviVersion({self.major}, {self.minor}, {self.patch})"

    def __eq__(self, other: object) -> bool:
        """Check version equality."""
        if not isinstance(other, CiviVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: object) -> bool:
        """Check if this version is less than another."""
        if not isinstance(other, CiviVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.major, self.minor, self.patch))

    @classmethod
    def parse(cls, version_str: str) -> CiviVersion:
        """Parse a version string into a CiviVersion.

        Supports various formats:
            - "5.70" -> CiviVersion(5, 70, 0)
            - "5.70.1" -> CiviVersion(5, 70, 1)
            - "v5.70" -> CiviVersion(5, 70, 0)
            - "5.70-alpha" -> CiviVersion(5, 70, 0)

        Args:
            version_str: Version string to parse.

        Returns:
            Parsed CiviVersion instance.

        Raises:
            ValueError: If version string cannot be parsed.
        """
        # Remove common prefixes
        version_str = version_str.strip().lstrip("v")

        # Remove suffixes like -alpha, -beta, -rc1
        version_str = re.sub(r"[-_].*$", "", version_str)

        # Split and parse
        parts = version_str.split(".")

        if len(parts) < 2:  # noqa: PLR2004
            msg = f"Invalid version string: {version_str!r} (expected at least MAJOR.MINOR)"
            raise ValueError(msg)

        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2]) if len(parts) > 2 else 0  # noqa: PLR2004
        except ValueError as e:
            msg = f"Invalid version string: {version_str!r}"
            raise ValueError(msg) from e

        return cls(major=major, minor=minor, patch=patch)

    @classmethod
    def from_env(cls, env_var: str = "CIVI_VERSION", default: str = "5.74") -> CiviVersion:
        """Get CiviCRM version from environment variable.

        Args:
            env_var: Environment variable name (default: CIVI_VERSION).
            default: Default version if not set (default: "5.74").

        Returns:
            CiviVersion from environment or default.
        """
        version_str = os.environ.get(env_var, default)

        # Handle special "default" value
        if version_str.lower() == "default":
            version_str = default

        return cls.parse(version_str)

    def to_cassette_dir(self) -> str:
        """Get the cassette directory name for this version.

        Returns:
            Directory name (e.g., "v5.70").
        """
        return f"v{self.major}.{self.minor}"

    def is_lts(self) -> bool:
        """Check if this is an LTS (Long Term Support) version.

        CiviCRM LTS versions are typically released every 6 months
        and receive extended support.

        Returns:
            True if this appears to be an LTS version.
        """
        # LTS versions are typically x.60, x.66, etc.
        return self.minor % 6 == 0


@dataclass
class VersionRange:
    """Represents a range of CiviCRM versions.

    Attributes:
        min_version: Minimum version (inclusive), or None for no minimum.
        max_version: Maximum version (exclusive), or None for no maximum.
    """

    min_version: CiviVersion | None = None
    max_version: CiviVersion | None = None

    def contains(self, version: CiviVersion) -> bool:
        """Check if a version falls within this range.

        Args:
            version: Version to check.

        Returns:
            True if version is within range.
        """
        if self.min_version is not None and version < self.min_version:
            return False
        return not (self.max_version is not None and version >= self.max_version)

    def __str__(self) -> str:
        """Return human-readable range description."""
        if self.min_version and self.max_version:
            return f">={self.min_version}, <{self.max_version}"
        if self.min_version:
            return f">={self.min_version}"
        if self.max_version:
            return f"<{self.max_version}"
        return "any"

    @classmethod
    def from_constraint(
        cls,
        min_version: str | CiviVersion | None = None,
        max_version: str | CiviVersion | None = None,
    ) -> VersionRange:
        """Create a VersionRange from string or CiviVersion constraints.

        Args:
            min_version: Minimum version (inclusive).
            max_version: Maximum version (exclusive).

        Returns:
            VersionRange instance.
        """
        min_v = CiviVersion.parse(min_version) if isinstance(min_version, str) else min_version
        max_v = CiviVersion.parse(max_version) if isinstance(max_version, str) else max_version
        return cls(min_version=min_v, max_version=max_v)


def version_satisfies(
    version: CiviVersion | str,
    *,
    min_version: CiviVersion | str | None = None,
    max_version: CiviVersion | str | None = None,
    exact_version: CiviVersion | str | None = None,
) -> bool:
    """Check if a version satisfies the given constraints.

    Args:
        version: Version to check.
        min_version: Minimum required version (inclusive).
        max_version: Maximum allowed version (exclusive).
        exact_version: Exact required version.

    Returns:
        True if version satisfies all constraints.

    Example:
        # Check if version is at least 5.70
        version_satisfies("5.75", min_version="5.70")  # True

        # Check if version is less than 5.80
        version_satisfies("5.75", max_version="5.80")  # True

        # Check if version is exactly 5.70
        version_satisfies("5.70", exact_version="5.70")  # True
    """
    # Parse version if string
    if isinstance(version, str):
        version = CiviVersion.parse(version)

    # Exact version check
    if exact_version is not None:
        if isinstance(exact_version, str):
            exact_version = CiviVersion.parse(exact_version)
        return version == exact_version

    # Range check
    version_range = VersionRange.from_constraint(min_version, max_version)
    return version_range.contains(version)


def get_supported_versions() -> list[CiviVersion]:
    """Get list of supported CiviCRM versions for testing.

    Returns:
        List of CiviVersion objects for supported versions.
    """
    return [
        CiviVersion(5, 60),  # LTS baseline
        CiviVersion(5, 70),  # Mid-range
        CiviVersion(5, 80),  # Latest
    ]


def get_version_features(version: CiviVersion) -> dict[str, bool]:
    """Get feature flags for a specific CiviCRM version.

    This maps CiviCRM versions to available API features,
    enabling version-conditional test logic.

    Args:
        version: CiviCRM version to check.

    Returns:
        Dictionary of feature name to availability.
    """
    features: dict[str, bool] = {
        # Base API v4 features (available in all supported versions)
        "api4_basic": True,
        "api4_joins": True,
        "api4_permissions": True,
        # Version-specific features
        "enhanced_field_metadata": version >= CiviVersion(5, 70),
        "improved_error_messages": version >= CiviVersion(5, 70),
        "custom_field_caching": version >= CiviVersion(5, 75),
        "batch_action_support": version >= CiviVersion(5, 78),
        "deprecation_warnings": version >= CiviVersion(5, 80),
        "new_search_operators": version >= CiviVersion(5, 80),
    }
    return features


def skip_reason_for_version(
    current: CiviVersion,
    *,
    min_version: str | None = None,
    max_version: str | None = None,
    exact_version: str | None = None,
) -> str | None:
    """Get skip reason if version doesn't meet requirements.

    Args:
        current: Current CiviCRM version.
        min_version: Minimum required version.
        max_version: Maximum allowed version (exclusive).
        exact_version: Exact required version.

    Returns:
        Skip reason string, or None if version is acceptable.
    """
    if exact_version:
        required = CiviVersion.parse(exact_version)
        if current != required:
            return f"Requires CiviCRM {exact_version} exactly (current: {current})"
        return None

    if min_version:
        min_v = CiviVersion.parse(min_version)
        if current < min_v:
            return f"Requires CiviCRM >= {min_version} (current: {current})"

    if max_version:
        max_v = CiviVersion.parse(max_version)
        if current >= max_v:
            return f"Requires CiviCRM < {max_version} (current: {current})"

    return None


@dataclass
class VersionCompatibilityResult:
    """Result of a version compatibility check.

    Attributes:
        version: CiviCRM version tested.
        compatible: Whether the version is compatible.
        features_available: List of available features.
        features_missing: List of missing/unavailable features.
        warnings: List of compatibility warnings.
        notes: Additional notes about this version.
    """

    version: CiviVersion
    compatible: bool
    features_available: list[str]
    features_missing: list[str]
    warnings: list[str]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": str(self.version),
            "compatible": self.compatible,
            "features_available": self.features_available,
            "features_missing": self.features_missing,
            "warnings": self.warnings,
            "notes": self.notes,
        }


def check_version_compatibility(
    version: CiviVersion,
    required_features: Sequence[str] | None = None,
) -> VersionCompatibilityResult:
    """Check compatibility for a CiviCRM version.

    Args:
        version: CiviCRM version to check.
        required_features: Optional list of required feature names.

    Returns:
        VersionCompatibilityResult with compatibility details.
    """
    features = get_version_features(version)
    required = set(required_features or [])

    available = [f for f, v in features.items() if v]
    missing = [f for f in required if not features.get(f, False)]

    warnings: list[str] = []
    notes = ""

    # Add version-specific warnings
    if version < CiviVersion(5, 60):
        warnings.append("Version is below minimum supported (5.60)")
        notes = "This version may have API incompatibilities"
    elif version.is_lts():
        notes = "LTS version with extended support"

    compatible = len(missing) == 0 and version >= CiviVersion(5, 60)

    return VersionCompatibilityResult(
        version=version,
        compatible=compatible,
        features_available=available,
        features_missing=missing,
        warnings=warnings,
        notes=notes,
    )


__all__ = [
    "CiviVersion",
    "VersionCompatibilityResult",
    "VersionConstraint",
    "VersionRange",
    "check_version_compatibility",
    "get_supported_versions",
    "get_version_features",
    "skip_reason_for_version",
    "version_satisfies",
]
