"""Tests for version_utils module.

These tests verify the version comparison and constraint functionality
used for version-aware testing.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tests.compat.version_utils import (
    CiviVersion,
    VersionCompatibilityResult,
    VersionConstraint,
    VersionRange,
    check_version_compatibility,
    get_supported_versions,
    get_version_features,
    skip_reason_for_version,
    version_satisfies,
)


class TestCiviVersion:
    """Tests for CiviVersion class."""

    def test_basic_creation(self) -> None:
        """Test basic version creation."""
        v = CiviVersion(5, 70)
        assert v.major == 5
        assert v.minor == 70
        assert v.patch == 0

    def test_with_patch(self) -> None:
        """Test version with patch number."""
        v = CiviVersion(5, 70, 2)
        assert v.major == 5
        assert v.minor == 70
        assert v.patch == 2

    def test_str_representation(self) -> None:
        """Test string representation."""
        assert str(CiviVersion(5, 70)) == "5.70"
        assert str(CiviVersion(5, 70, 0)) == "5.70"
        assert str(CiviVersion(5, 70, 1)) == "5.70.1"

    def test_repr_representation(self) -> None:
        """Test debug representation."""
        assert repr(CiviVersion(5, 70)) == "CiviVersion(5, 70, 0)"
        assert repr(CiviVersion(5, 70, 1)) == "CiviVersion(5, 70, 1)"

    def test_equality(self) -> None:
        """Test version equality."""
        assert CiviVersion(5, 70) == CiviVersion(5, 70)
        assert CiviVersion(5, 70) == CiviVersion(5, 70, 0)
        assert CiviVersion(5, 70, 1) != CiviVersion(5, 70, 2)
        assert CiviVersion(5, 70) != CiviVersion(5, 71)

    def test_less_than(self) -> None:
        """Test less than comparison."""
        assert CiviVersion(5, 60) < CiviVersion(5, 70)
        assert CiviVersion(5, 70) < CiviVersion(5, 80)
        assert CiviVersion(5, 70, 0) < CiviVersion(5, 70, 1)
        assert not CiviVersion(5, 70) < CiviVersion(5, 70)
        assert not CiviVersion(5, 80) < CiviVersion(5, 70)

    def test_less_than_or_equal(self) -> None:
        """Test less than or equal comparison."""
        assert CiviVersion(5, 60) <= CiviVersion(5, 70)
        assert CiviVersion(5, 70) <= CiviVersion(5, 70)
        assert not CiviVersion(5, 80) <= CiviVersion(5, 70)

    def test_greater_than(self) -> None:
        """Test greater than comparison."""
        assert CiviVersion(5, 80) > CiviVersion(5, 70)
        assert CiviVersion(5, 70, 1) > CiviVersion(5, 70, 0)
        assert not CiviVersion(5, 70) > CiviVersion(5, 70)
        assert not CiviVersion(5, 60) > CiviVersion(5, 70)

    def test_greater_than_or_equal(self) -> None:
        """Test greater than or equal comparison."""
        assert CiviVersion(5, 80) >= CiviVersion(5, 70)
        assert CiviVersion(5, 70) >= CiviVersion(5, 70)
        assert not CiviVersion(5, 60) >= CiviVersion(5, 70)

    def test_hash(self) -> None:
        """Test version is hashable."""
        versions = {CiviVersion(5, 60), CiviVersion(5, 70), CiviVersion(5, 80)}
        assert len(versions) == 3
        assert CiviVersion(5, 70) in versions

    def test_parse_basic(self) -> None:
        """Test parsing basic version strings."""
        v = CiviVersion.parse("5.70")
        assert v == CiviVersion(5, 70)

    def test_parse_with_patch(self) -> None:
        """Test parsing version with patch."""
        v = CiviVersion.parse("5.70.2")
        assert v == CiviVersion(5, 70, 2)

    def test_parse_with_prefix(self) -> None:
        """Test parsing version with v prefix."""
        v = CiviVersion.parse("v5.70")
        assert v == CiviVersion(5, 70)

    def test_parse_with_suffix(self) -> None:
        """Test parsing version with suffix."""
        v = CiviVersion.parse("5.70-alpha")
        assert v == CiviVersion(5, 70)

        v = CiviVersion.parse("5.70-beta1")
        assert v == CiviVersion(5, 70)

        v = CiviVersion.parse("5.70_rc1")
        assert v == CiviVersion(5, 70)

    def test_parse_invalid(self) -> None:
        """Test parsing invalid version strings."""
        with pytest.raises(ValueError, match="Invalid version"):
            CiviVersion.parse("5")

        with pytest.raises(ValueError, match="Invalid version"):
            CiviVersion.parse("invalid")

        with pytest.raises(ValueError, match="Invalid version"):
            CiviVersion.parse("5.x")

    def test_from_env_default(self) -> None:
        """Test loading version from environment with default."""
        with patch.dict(os.environ, {}, clear=True):
            v = CiviVersion.from_env()
            assert v == CiviVersion(5, 74)

    def test_from_env_custom(self) -> None:
        """Test loading version from environment variable."""
        with patch.dict(os.environ, {"CIVI_VERSION": "5.80"}):
            v = CiviVersion.from_env()
            assert v == CiviVersion(5, 80)

    def test_from_env_custom_var(self) -> None:
        """Test loading from custom environment variable."""
        with patch.dict(os.environ, {"MY_CIVI_VERSION": "5.60"}):
            v = CiviVersion.from_env(env_var="MY_CIVI_VERSION")
            assert v == CiviVersion(5, 60)

    def test_from_env_default_keyword(self) -> None:
        """Test that 'default' keyword uses default version."""
        with patch.dict(os.environ, {"CIVI_VERSION": "default"}):
            v = CiviVersion.from_env(default="5.75")
            assert v == CiviVersion(5, 75)

    def test_to_cassette_dir(self) -> None:
        """Test cassette directory name generation."""
        assert CiviVersion(5, 70).to_cassette_dir() == "v5.70"
        assert CiviVersion(5, 80, 1).to_cassette_dir() == "v5.80"

    def test_is_lts(self) -> None:
        """Test LTS version detection."""
        # LTS versions (minor divisible by 6)
        assert CiviVersion(5, 60).is_lts() is True
        assert CiviVersion(5, 66).is_lts() is True
        assert CiviVersion(5, 72).is_lts() is True
        assert CiviVersion(5, 78).is_lts() is True

        # Non-LTS versions
        assert CiviVersion(5, 61).is_lts() is False
        assert CiviVersion(5, 70).is_lts() is False
        assert CiviVersion(5, 80).is_lts() is False


class TestVersionRange:
    """Tests for VersionRange class."""

    def test_full_range(self) -> None:
        """Test range with min and max."""
        vr = VersionRange(
            min_version=CiviVersion(5, 60),
            max_version=CiviVersion(5, 80),
        )

        assert vr.contains(CiviVersion(5, 60))  # Min inclusive
        assert vr.contains(CiviVersion(5, 70))
        assert not vr.contains(CiviVersion(5, 80))  # Max exclusive
        assert not vr.contains(CiviVersion(5, 50))
        assert not vr.contains(CiviVersion(5, 90))

    def test_min_only(self) -> None:
        """Test range with only minimum."""
        vr = VersionRange(min_version=CiviVersion(5, 70))

        assert vr.contains(CiviVersion(5, 70))
        assert vr.contains(CiviVersion(5, 80))
        assert vr.contains(CiviVersion(5, 99))
        assert not vr.contains(CiviVersion(5, 60))

    def test_max_only(self) -> None:
        """Test range with only maximum."""
        vr = VersionRange(max_version=CiviVersion(5, 80))

        assert vr.contains(CiviVersion(5, 70))
        assert vr.contains(CiviVersion(5, 60))
        assert vr.contains(CiviVersion(5, 50))
        assert not vr.contains(CiviVersion(5, 80))
        assert not vr.contains(CiviVersion(5, 90))

    def test_unbounded(self) -> None:
        """Test unbounded range contains all."""
        vr = VersionRange()

        assert vr.contains(CiviVersion(5, 50))
        assert vr.contains(CiviVersion(5, 70))
        assert vr.contains(CiviVersion(5, 99))

    def test_str_representation(self) -> None:
        """Test string representation of ranges."""
        assert str(VersionRange(min_version=CiviVersion(5, 70))) == ">=5.70"
        assert str(VersionRange(max_version=CiviVersion(5, 80))) == "<5.80"
        assert (
            str(
                VersionRange(
                    min_version=CiviVersion(5, 60),
                    max_version=CiviVersion(5, 80),
                )
            )
            == ">=5.60, <5.80"
        )
        assert str(VersionRange()) == "any"

    def test_from_constraint_strings(self) -> None:
        """Test creating range from string constraints."""
        vr = VersionRange.from_constraint(min_version="5.60", max_version="5.80")
        assert vr.min_version == CiviVersion(5, 60)
        assert vr.max_version == CiviVersion(5, 80)

    def test_from_constraint_mixed(self) -> None:
        """Test creating range from mixed types."""
        vr = VersionRange.from_constraint(
            min_version=CiviVersion(5, 60),
            max_version="5.80",
        )
        assert vr.min_version == CiviVersion(5, 60)
        assert vr.max_version == CiviVersion(5, 80)


class TestVersionSatisfies:
    """Tests for version_satisfies helper function."""

    def test_min_version(self) -> None:
        """Test minimum version constraint."""
        assert version_satisfies("5.75", min_version="5.70") is True
        assert version_satisfies("5.70", min_version="5.70") is True
        assert version_satisfies("5.60", min_version="5.70") is False

    def test_max_version(self) -> None:
        """Test maximum version constraint."""
        assert version_satisfies("5.75", max_version="5.80") is True
        assert version_satisfies("5.80", max_version="5.80") is False
        assert version_satisfies("5.85", max_version="5.80") is False

    def test_exact_version(self) -> None:
        """Test exact version constraint."""
        assert version_satisfies("5.70", exact_version="5.70") is True
        assert version_satisfies("5.71", exact_version="5.70") is False
        assert version_satisfies("5.70.0", exact_version="5.70") is True

    def test_combined_constraints(self) -> None:
        """Test combined min and max constraints."""
        assert version_satisfies("5.75", min_version="5.70", max_version="5.80") is True
        assert version_satisfies("5.70", min_version="5.70", max_version="5.80") is True
        assert version_satisfies("5.60", min_version="5.70", max_version="5.80") is False
        assert version_satisfies("5.80", min_version="5.70", max_version="5.80") is False

    def test_with_civiversion_object(self) -> None:
        """Test with CiviVersion objects instead of strings."""
        assert (
            version_satisfies(
                CiviVersion(5, 75),
                min_version=CiviVersion(5, 70),
            )
            is True
        )


class TestGetVersionFeatures:
    """Tests for get_version_features function."""

    def test_base_features_always_available(self) -> None:
        """Test that base features are always available."""
        for version in [CiviVersion(5, 60), CiviVersion(5, 70), CiviVersion(5, 80)]:
            features = get_version_features(version)
            assert features["api4_basic"] is True
            assert features["api4_joins"] is True
            assert features["api4_permissions"] is True

    def test_5_70_features(self) -> None:
        """Test features available in 5.70."""
        features = get_version_features(CiviVersion(5, 70))
        assert features["enhanced_field_metadata"] is True
        assert features["improved_error_messages"] is True

    def test_5_60_missing_5_70_features(self) -> None:
        """Test that 5.60 doesn't have 5.70 features."""
        features = get_version_features(CiviVersion(5, 60))
        assert features["enhanced_field_metadata"] is False
        assert features["improved_error_messages"] is False

    def test_5_80_features(self) -> None:
        """Test features available in 5.80."""
        features = get_version_features(CiviVersion(5, 80))
        assert features["deprecation_warnings"] is True
        assert features["new_search_operators"] is True

    def test_5_70_missing_5_80_features(self) -> None:
        """Test that 5.70 doesn't have 5.80 features."""
        features = get_version_features(CiviVersion(5, 70))
        assert features["deprecation_warnings"] is False
        assert features["new_search_operators"] is False


class TestSkipReasonForVersion:
    """Tests for skip_reason_for_version function."""

    def test_no_skip_when_satisfied(self) -> None:
        """Test no skip reason when constraints satisfied."""
        v = CiviVersion(5, 70)

        assert skip_reason_for_version(v, min_version="5.60") is None
        assert skip_reason_for_version(v, max_version="5.80") is None
        assert skip_reason_for_version(v, exact_version="5.70") is None

    def test_skip_for_min_version(self) -> None:
        """Test skip reason for minimum version constraint."""
        v = CiviVersion(5, 70)
        reason = skip_reason_for_version(v, min_version="5.80")

        assert reason is not None
        assert "5.80" in reason
        assert "5.70" in reason
        assert ">=" in reason

    def test_skip_for_max_version(self) -> None:
        """Test skip reason for maximum version constraint."""
        v = CiviVersion(5, 80)
        reason = skip_reason_for_version(v, max_version="5.80")

        assert reason is not None
        assert "5.80" in reason
        assert "<" in reason

    def test_skip_for_exact_version(self) -> None:
        """Test skip reason for exact version constraint."""
        v = CiviVersion(5, 70)
        reason = skip_reason_for_version(v, exact_version="5.60")

        assert reason is not None
        assert "5.60" in reason
        assert "exactly" in reason


class TestGetSupportedVersions:
    """Tests for get_supported_versions function."""

    def test_returns_list(self) -> None:
        """Test that it returns a list of versions."""
        versions = get_supported_versions()
        assert isinstance(versions, list)
        assert len(versions) >= 3

    def test_all_versions_are_civiversion(self) -> None:
        """Test all items are CiviVersion instances."""
        versions = get_supported_versions()
        for v in versions:
            assert isinstance(v, CiviVersion)

    def test_includes_baseline(self) -> None:
        """Test that baseline version 5.60 is included."""
        versions = get_supported_versions()
        assert CiviVersion(5, 60) in versions

    def test_versions_ordered(self) -> None:
        """Test that versions are in order."""
        versions = get_supported_versions()
        for i in range(1, len(versions)):
            assert versions[i] > versions[i - 1]


class TestCheckVersionCompatibility:
    """Tests for check_version_compatibility function."""

    def test_compatible_version(self) -> None:
        """Test checking a compatible version."""
        result = check_version_compatibility(CiviVersion(5, 70))

        assert isinstance(result, VersionCompatibilityResult)
        assert result.compatible is True
        assert result.version == CiviVersion(5, 70)
        assert len(result.features_available) > 0

    def test_old_version_warning(self) -> None:
        """Test that old versions get warnings."""
        result = check_version_compatibility(CiviVersion(5, 50))

        assert result.compatible is False
        assert len(result.warnings) > 0
        assert "below minimum" in result.warnings[0].lower()

    def test_lts_version_notes(self) -> None:
        """Test that LTS versions get appropriate notes."""
        result = check_version_compatibility(CiviVersion(5, 60))

        assert "LTS" in result.notes

    def test_required_features_missing(self) -> None:
        """Test checking with required features that are missing."""
        result = check_version_compatibility(
            CiviVersion(5, 60),
            required_features=["deprecation_warnings"],
        )

        assert result.compatible is False
        assert "deprecation_warnings" in result.features_missing

    def test_required_features_available(self) -> None:
        """Test checking with required features that are available."""
        result = check_version_compatibility(
            CiviVersion(5, 80),
            required_features=["deprecation_warnings"],
        )

        assert result.compatible is True
        assert "deprecation_warnings" not in result.features_missing

    def test_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = check_version_compatibility(CiviVersion(5, 70))
        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["version"] == "5.70"
        assert isinstance(data["compatible"], bool)
        assert isinstance(data["features_available"], list)


class TestVersionConstraintEnum:
    """Tests for VersionConstraint enum."""

    def test_enum_values(self) -> None:
        """Test enum has expected values."""
        assert VersionConstraint.MINIMUM.value == "min"
        assert VersionConstraint.MAXIMUM.value == "max"
        assert VersionConstraint.EXACT.value == "exact"
        assert VersionConstraint.RANGE.value == "range"
