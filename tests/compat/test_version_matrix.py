"""Tests for CiviCRM version compatibility matrix.

These tests verify the version matrix infrastructure for testing
civi-py against multiple CiviCRM versions.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.compat.version_matrix import (
    APIDifference,
    DifferenceType,
    Severity,
    VersionDetector,
    VersionInfo,
    VersionMatrix,
    get_cassette_version,
    get_current_version,
    get_version_matrix,
    skip_for_version,
)


class TestVersionInfo:
    """Tests for VersionInfo dataclass."""

    def test_create_basic_version_info(self) -> None:
        """Test creating a basic VersionInfo instance."""
        info = VersionInfo(version="5.74.0")

        assert info.version == "5.74.0"
        assert info.api_version == 4
        assert info.major_version == 5
        assert info.minor_version == 74
        assert info.patch_version == 0

    def test_version_tuple(self) -> None:
        """Test version tuple generation."""
        info = VersionInfo(version="5.74.2")

        assert info.version_tuple == (5, 74, 2)

    def test_short_version(self) -> None:
        """Test short version string."""
        info = VersionInfo(version="5.74.0")

        assert info.short_version == "5.74"

    def test_cassette_dir(self) -> None:
        """Test cassette directory naming."""
        info = VersionInfo(version="5.74.0")

        assert info.cassette_dir == "v5.74"

    def test_version_comparison(self) -> None:
        """Test version comparison operators."""
        v1 = VersionInfo(version="5.70.0")
        v2 = VersionInfo(version="5.74.0")
        v3 = VersionInfo(version="5.74.0")

        assert v1 < v2
        assert v2 <= v3
        assert not v2 < v3

    def test_is_active_no_eol(self) -> None:
        """Test is_active when no end_of_life is set."""
        info = VersionInfo(version="5.74.0")

        assert info.is_active is True

    def test_is_active_future_eol(self) -> None:
        """Test is_active with future end_of_life."""
        info = VersionInfo(
            version="5.76.0",
            end_of_life=date(2099, 12, 31),
        )

        assert info.is_active is True

    def test_is_active_past_eol(self) -> None:
        """Test is_active with past end_of_life."""
        info = VersionInfo(
            version="5.60.0",
            end_of_life=date(2020, 1, 1),
        )

        assert info.is_active is False

    def test_supports_php_in_range(self) -> None:
        """Test PHP support check for supported version."""
        info = VersionInfo(
            version="5.74.0",
            php_min_version="8.1",
            php_max_version="8.3",
        )

        assert info.supports_php("8.1") is True
        assert info.supports_php("8.2") is True
        assert info.supports_php("8.3") is True

    def test_supports_php_below_min(self) -> None:
        """Test PHP support check for version below minimum."""
        info = VersionInfo(
            version="5.74.0",
            php_min_version="8.1",
        )

        assert info.supports_php("8.0") is False
        assert info.supports_php("7.4") is False

    def test_supports_php_above_max(self) -> None:
        """Test PHP support check for version above maximum."""
        info = VersionInfo(
            version="5.74.0",
            php_min_version="8.1",
            php_max_version="8.3",
        )

        assert info.supports_php("8.4") is False

    def test_get_docker_image_default(self) -> None:
        """Test getting default Docker image."""
        info = VersionInfo(version="5.74.0")

        assert info.get_docker_image() == "civicrm/civicrm:5.74.0"

    def test_get_docker_image_custom(self) -> None:
        """Test getting custom Docker image."""
        info = VersionInfo(
            version="5.74.0",
            docker_image="civicrm/civicrm:5.74-latest",
        )

        assert info.get_docker_image() == "civicrm/civicrm:5.74-latest"

    def test_get_docker_image_alt(self) -> None:
        """Test getting alternative Docker image."""
        info = VersionInfo(
            version="5.80.0",
            docker_image_alt="civicrm/civicrm:latest",
        )

        assert info.get_docker_image() == "civicrm/civicrm:latest"

    def test_lts_version(self) -> None:
        """Test LTS version flag."""
        lts_info = VersionInfo(version="5.76.0", is_lts=True)
        regular_info = VersionInfo(version="5.75.0", is_lts=False)

        assert lts_info.is_lts is True
        assert regular_info.is_lts is False


class TestAPIDifference:
    """Tests for APIDifference dataclass."""

    def test_create_field_difference(self) -> None:
        """Test creating a field-related difference."""
        diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_ADDED,
            introduced_in="5.74.0",
            severity=Severity.ENHANCEMENT,
            field="new_field",
            description="Added new_field to Contact entity",
        )

        assert diff.entity == "Contact"
        assert diff.field == "new_field"
        assert diff.is_breaking is False

    def test_create_action_difference(self) -> None:
        """Test creating an action-related difference."""
        diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.ACTION_ADDED,
            introduced_in="5.80.0",
            severity=Severity.ENHANCEMENT,
            action="merge",
            description="New merge action",
        )

        assert diff.action == "merge"

    def test_field_difference_requires_field(self) -> None:
        """Test that field differences require field name."""
        with pytest.raises(ValueError, match="requires a field name"):
            APIDifference(
                entity="Contact",
                difference_type=DifferenceType.FIELD_ADDED,
                introduced_in="5.74.0",
                severity=Severity.ENHANCEMENT,
                # Missing field
            )

    def test_action_difference_requires_action(self) -> None:
        """Test that action differences require action name."""
        with pytest.raises(ValueError, match="requires an action name"):
            APIDifference(
                entity="Contact",
                difference_type=DifferenceType.ACTION_REMOVED,
                introduced_in="5.74.0",
                severity=Severity.BREAKING,
                # Missing action
            )

    def test_is_breaking(self) -> None:
        """Test is_breaking property."""
        breaking = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_REMOVED,
            introduced_in="5.74.0",
            severity=Severity.BREAKING,
            field="removed_field",
        )

        non_breaking = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_ADDED,
            introduced_in="5.74.0",
            severity=Severity.ENHANCEMENT,
            field="new_field",
        )

        assert breaking.is_breaking is True
        assert non_breaking.is_breaking is False

    def test_is_deprecated(self) -> None:
        """Test is_deprecated property."""
        deprecated = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_DEPRECATED,
            introduced_in="5.70.0",
            severity=Severity.DEPRECATION,
            field="old_field",
        )

        assert deprecated.is_deprecated is True

    def test_key_generation(self) -> None:
        """Test unique key generation."""
        field_diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_ADDED,
            introduced_in="5.74.0",
            severity=Severity.ENHANCEMENT,
            field="new_field",
        )

        action_diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.ACTION_ADDED,
            introduced_in="5.74.0",
            severity=Severity.ENHANCEMENT,
            action="merge",
        )

        assert field_diff.key == "Contact:field_added:new_field"
        assert action_diff.key == "Contact:action_added:merge"

    def test_affects_version(self) -> None:
        """Test version affecting check."""
        diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_ADDED,
            introduced_in="5.74.0",
            severity=Severity.ENHANCEMENT,
            field="new_field",
        )

        assert diff.affects_version("5.74.0") is True
        assert diff.affects_version("5.75.0") is True
        assert diff.affects_version("5.80.0") is True
        assert diff.affects_version("5.70.0") is False
        assert diff.affects_version("5.73.0") is False

    def test_format_message(self) -> None:
        """Test formatted message generation."""
        diff = APIDifference(
            entity="Contact",
            difference_type=DifferenceType.FIELD_REMOVED,
            introduced_in="5.74.0",
            severity=Severity.BREAKING,
            field="removed_field",
            description="Field was removed due to data model changes",
        )

        message = diff.format_message()

        assert "[BREAKING]" in message
        assert "Contact" in message
        assert ".removed_field" in message
        assert "field_removed" in message
        assert "data model changes" in message


class TestVersionMatrix:
    """Tests for VersionMatrix class."""

    @pytest.fixture
    def empty_matrix(self) -> VersionMatrix:
        """Create an empty version matrix."""
        return VersionMatrix()

    @pytest.fixture
    def populated_matrix(self, empty_matrix: VersionMatrix) -> VersionMatrix:
        """Create a populated version matrix."""
        # Add some versions
        empty_matrix.register_version(
            VersionInfo(version="5.60.0", is_lts=True),
        )
        empty_matrix.register_version(
            VersionInfo(version="5.70.0"),
        )
        empty_matrix.register_version(
            VersionInfo(version="5.74.0"),
        )
        empty_matrix.register_version(
            VersionInfo(version="5.76.0", is_lts=True),
        )

        # Add some differences
        empty_matrix.register_difference(
            APIDifference(
                entity="Contact",
                difference_type=DifferenceType.FIELD_ADDED,
                introduced_in="5.70.0",
                severity=Severity.ENHANCEMENT,
                field="new_field",
            ),
        )
        empty_matrix.register_difference(
            APIDifference(
                entity="Contact",
                difference_type=DifferenceType.FIELD_REMOVED,
                introduced_in="5.74.0",
                severity=Severity.BREAKING,
                field="old_field",
            ),
        )
        empty_matrix.register_difference(
            APIDifference(
                entity="Activity",
                difference_type=DifferenceType.FIELD_DEPRECATED,
                introduced_in="5.72.0",
                severity=Severity.DEPRECATION,
                field="deprecated_field",
            ),
        )

        return empty_matrix

    def test_register_version(self, empty_matrix: VersionMatrix) -> None:
        """Test registering a version."""
        info = VersionInfo(version="5.74.0")
        empty_matrix.register_version(info)

        assert empty_matrix.get_version("5.74.0") is info
        assert empty_matrix.get_version("5.74") is info

    def test_get_version_not_found(self, empty_matrix: VersionMatrix) -> None:
        """Test getting a non-existent version."""
        assert empty_matrix.get_version("5.99.0") is None

    def test_get_closest_version(self, populated_matrix: VersionMatrix) -> None:
        """Test getting closest matching version."""
        # Exact match
        assert populated_matrix.get_closest_version("5.70.0").version == "5.70.0"

        # Closest match for version not in matrix
        closest = populated_matrix.get_closest_version("5.72.0")
        assert closest is not None
        assert closest.version == "5.70.0"

        # Version too old - no match
        assert populated_matrix.get_closest_version("5.50.0") is None

    def test_is_supported(self, populated_matrix: VersionMatrix) -> None:
        """Test version support check."""
        assert populated_matrix.is_supported("5.70.0") is True
        assert populated_matrix.is_supported("5.74.0") is True
        assert populated_matrix.is_supported("5.72.0") is True  # Closest match
        assert populated_matrix.is_supported("5.50.0") is False

    def test_get_supported_versions(self, populated_matrix: VersionMatrix) -> None:
        """Test getting all supported versions."""
        versions = populated_matrix.get_supported_versions()

        assert len(versions) == 4
        assert versions[0].version == "5.60.0"
        assert versions[-1].version == "5.76.0"

    def test_get_lts_versions(self, populated_matrix: VersionMatrix) -> None:
        """Test getting LTS versions."""
        lts_versions = populated_matrix.get_lts_versions()

        assert len(lts_versions) == 2
        assert all(v.is_lts for v in lts_versions)

    def test_get_differences(self, populated_matrix: VersionMatrix) -> None:
        """Test getting differences with filters."""
        # All differences
        all_diffs = populated_matrix.get_differences()
        assert len(all_diffs) == 3

        # Filter by entity
        contact_diffs = populated_matrix.get_differences(entity="Contact")
        assert len(contact_diffs) == 2

        # Filter by severity
        breaking_diffs = populated_matrix.get_differences(severity=Severity.BREAKING)
        assert len(breaking_diffs) == 1

        # Filter by type
        added_diffs = populated_matrix.get_differences(
            difference_type=DifferenceType.FIELD_ADDED,
        )
        assert len(added_diffs) == 1

    def test_get_differences_for_entity(self, populated_matrix: VersionMatrix) -> None:
        """Test getting differences for specific entity."""
        contact_diffs = populated_matrix.get_differences_for_entity("Contact")
        assert len(contact_diffs) == 2
        assert all(d.entity == "Contact" for d in contact_diffs)

    def test_get_differences_since(self, populated_matrix: VersionMatrix) -> None:
        """Test getting differences since a version."""
        since_570 = populated_matrix.get_differences_since("5.70.0")

        # Should include 5.72 and 5.74 differences, not 5.70
        assert len(since_570) == 2
        versions = {d.introduced_in for d in since_570}
        assert "5.70.0" not in versions
        assert "5.72.0" in versions
        assert "5.74.0" in versions

    def test_get_differences_between(self, populated_matrix: VersionMatrix) -> None:
        """Test getting differences between versions."""
        between = populated_matrix.get_differences_between("5.70.0", "5.74.0")

        assert len(between) == 2
        versions = {d.introduced_in for d in between}
        assert "5.72.0" in versions
        assert "5.74.0" in versions
        assert "5.70.0" not in versions

    def test_get_breaking_changes(self, populated_matrix: VersionMatrix) -> None:
        """Test getting breaking changes."""
        breaking = populated_matrix.get_breaking_changes()
        assert len(breaking) == 1
        assert breaking[0].severity == Severity.BREAKING

        # Since version
        breaking_since = populated_matrix.get_breaking_changes(since_version="5.73.0")
        assert len(breaking_since) == 1

        breaking_since_later = populated_matrix.get_breaking_changes(since_version="5.74.0")
        assert len(breaking_since_later) == 0

    def test_get_deprecations(self, populated_matrix: VersionMatrix) -> None:
        """Test getting deprecations."""
        deprecations = populated_matrix.get_deprecations()
        assert len(deprecations) == 1
        assert deprecations[0].is_deprecated is True

    def test_format_changelog(self, populated_matrix: VersionMatrix) -> None:
        """Test changelog formatting."""
        changelog = populated_matrix.format_changelog("5.70.0", "5.74.0")

        assert "5.70.0 to 5.74.0" in changelog
        assert "Breaking" in changelog
        assert "Deprecation" in changelog

    def test_format_changelog_no_differences(self, populated_matrix: VersionMatrix) -> None:
        """Test changelog formatting with no differences."""
        changelog = populated_matrix.format_changelog("5.74.0", "5.74.0")

        assert "No API differences" in changelog


class TestVersionDetector:
    """Tests for VersionDetector class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock CiviClient."""
        return MagicMock()

    async def test_detect_version(self, mock_client: MagicMock) -> None:
        """Test version detection from live instance."""
        mock_response = MagicMock()
        mock_response.values = [{"version": "5.74.3"}]
        mock_client.request = AsyncMock(return_value=mock_response)

        detector = VersionDetector(mock_client)

        version = await detector.detect_version()

        assert version == "5.74.3"
        mock_client.request.assert_called_once_with(
            "System",
            "get",
            {"select": ["version"]},
        )

    async def test_detect_version_cached(self, mock_client: MagicMock) -> None:
        """Test that version is cached after first detection."""
        mock_response = MagicMock()
        mock_response.values = [{"version": "5.74.3"}]
        mock_client.request = AsyncMock(return_value=mock_response)

        detector = VersionDetector(mock_client)

        # First call
        version1 = await detector.detect_version()
        # Second call should use cache
        version2 = await detector.detect_version()

        assert version1 == version2
        assert mock_client.request.call_count == 1

    async def test_detect_version_no_response(self, mock_client: MagicMock) -> None:
        """Test version detection failure."""
        mock_response = MagicMock()
        mock_response.values = []
        mock_client.request = AsyncMock(return_value=mock_response)

        detector = VersionDetector(mock_client)

        with pytest.raises(RuntimeError, match="Could not detect"):
            await detector.detect_version()

    async def test_get_api_version(self, mock_client: MagicMock) -> None:
        """Test getting API version (always 4)."""
        detector = VersionDetector(mock_client)

        api_version = await detector.get_api_version()

        assert api_version == 4

    async def test_get_version_info(self, mock_client: MagicMock) -> None:
        """Test getting VersionInfo from matrix."""
        mock_response = MagicMock()
        mock_response.values = [{"version": "5.74.0"}]
        mock_client.request = AsyncMock(return_value=mock_response)

        detector = VersionDetector(mock_client)
        matrix = get_version_matrix()

        info = await detector.get_version_info(matrix)

        assert info is not None
        assert info.version == "5.74.0"

    async def test_clear_cache(self, mock_client: MagicMock) -> None:
        """Test clearing the version cache."""
        mock_response = MagicMock()
        mock_response.values = [{"version": "5.74.3"}]
        mock_client.request = AsyncMock(return_value=mock_response)

        detector = VersionDetector(mock_client)

        # First call
        await detector.detect_version()
        assert detector._cached_version is not None

        # Clear cache
        detector.clear_cache()
        assert detector._cached_version is None
        assert detector._cached_info is None


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_version_matrix(self) -> None:
        """Test getting the default version matrix."""
        matrix = get_version_matrix()

        assert isinstance(matrix, VersionMatrix)
        # Should have registered versions
        assert matrix.is_supported("5.74.0")
        assert matrix.is_supported("5.76.0")

    def test_get_version_matrix_singleton(self) -> None:
        """Test that get_version_matrix returns singleton."""
        matrix1 = get_version_matrix()
        matrix2 = get_version_matrix()

        assert matrix1 is matrix2

    def test_get_current_version_default(self) -> None:
        """Test getting current version when env not set."""
        # Save and remove the env var if it exists
        old_value = os.environ.pop("CIVI_VERSION", None)
        try:
            version = get_current_version()
            assert version == "default"
        finally:
            # Restore original value if it existed
            if old_value is not None:
                os.environ["CIVI_VERSION"] = old_value

    def test_get_current_version_from_env(self) -> None:
        """Test getting current version from environment."""
        with patch.dict(os.environ, {"CIVI_VERSION": "5.74.0"}):
            version = get_current_version()
            assert version == "5.74.0"

    def test_get_cassette_version_default(self) -> None:
        """Test getting cassette version for default."""
        # Save and remove the env var if it exists
        old_value = os.environ.pop("CIVI_VERSION", None)
        try:
            version = get_cassette_version()
            assert version == "default"
        finally:
            # Restore original value if it existed
            if old_value is not None:
                os.environ["CIVI_VERSION"] = old_value

    def test_get_cassette_version_from_env(self) -> None:
        """Test getting cassette version from environment."""
        with patch.dict(os.environ, {"CIVI_VERSION": "5.74.0"}):
            version = get_cassette_version()
            assert version == "5.74"

    def test_get_cassette_version_short(self) -> None:
        """Test getting cassette version with short input."""
        with patch.dict(os.environ, {"CIVI_VERSION": "5.74"}):
            version = get_cassette_version()
            assert version == "5.74"


class TestSkipForVersion:
    """Tests for skip_for_version function."""

    def test_skip_for_default_version(self) -> None:
        """Test that default version is never skipped."""
        result = skip_for_version(
            "default",
            skip_versions=["5.74"],
        )
        assert result is None

    def test_skip_matching_version(self) -> None:
        """Test skipping a matching version."""
        result = skip_for_version(
            "5.74.0",
            skip_versions=["5.74"],
            reason="Not supported in 5.74",
        )
        assert result == "Not supported in 5.74"

    def test_skip_non_matching_version(self) -> None:
        """Test not skipping a non-matching version."""
        result = skip_for_version(
            "5.76.0",
            skip_versions=["5.74"],
        )
        assert result is None

    def test_skip_below_min_version(self) -> None:
        """Test skipping when below minimum version."""
        result = skip_for_version(
            "5.60.0",
            min_version="5.70.0",
        )
        assert "5.70.0 or later" in result

    def test_skip_above_max_version(self) -> None:
        """Test skipping when above maximum version."""
        result = skip_for_version(
            "5.80.0",
            max_version="5.76.0",
        )
        assert "not supported after" in result

    def test_no_skip_in_range(self) -> None:
        """Test not skipping when version is in range."""
        result = skip_for_version(
            "5.74.0",
            min_version="5.70.0",
            max_version="5.80.0",
        )
        assert result is None

    def test_skip_with_custom_reason(self) -> None:
        """Test skip with custom reason message."""
        result = skip_for_version(
            "5.60.0",
            min_version="5.70.0",
            reason="Custom skip reason",
        )
        assert result == "Custom skip reason"


class TestDefaultVersionMatrix:
    """Tests for the default version matrix configuration."""

    @pytest.fixture
    def matrix(self) -> VersionMatrix:
        """Get the default version matrix."""
        return get_version_matrix()

    def test_supported_version_range(self, matrix: VersionMatrix) -> None:
        """Test that expected version range is supported."""
        # These versions should be supported
        supported_versions = ["5.60", "5.68", "5.70", "5.74", "5.76", "5.78", "5.80"]

        for version in supported_versions:
            assert matrix.is_supported(version), f"Version {version} should be supported"

    def test_lts_versions_configured(self, matrix: VersionMatrix) -> None:
        """Test that LTS versions are properly configured."""
        lts = matrix.get_lts_versions()

        # Should have at least 2 LTS versions
        assert len(lts) >= 2

        # All should be marked as LTS
        for v in lts:
            assert v.is_lts is True

    def test_known_differences_registered(self, matrix: VersionMatrix) -> None:
        """Test that known differences are registered."""
        differences = matrix.get_differences()

        # Should have registered differences
        assert len(differences) > 0

        # Should have different severity levels
        severities = {d.severity for d in differences}
        assert Severity.BREAKING in severities or Severity.DEPRECATION in severities

    def test_php_requirements_configured(self, matrix: VersionMatrix) -> None:
        """Test that PHP requirements are properly configured."""
        v560 = matrix.get_version("5.60")
        v574 = matrix.get_version("5.74")

        assert v560 is not None
        assert v574 is not None

        # 5.60 should support older PHP
        assert v560.supports_php("7.4") is True

        # 5.74 should require newer PHP
        assert v574.supports_php("7.4") is False
        assert v574.supports_php("8.1") is True

    def test_docker_images_configured(self, matrix: VersionMatrix) -> None:
        """Test that Docker images are configured."""
        versions = matrix.get_supported_versions()

        for v in versions:
            # Should be able to get a Docker image
            image = v.get_docker_image()
            assert image is not None
            assert "civicrm" in image.lower()


class TestVersionMatrixIntegration:
    """Integration tests for version matrix with cassette system."""

    def test_cassette_directory_mapping(self) -> None:
        """Test that versions map to correct cassette directories."""
        matrix = get_version_matrix()

        test_cases = [
            ("5.74.0", "v5.74"),
            ("5.76.3", "v5.76"),
            ("5.80.0", "v5.80"),
        ]

        for version_str, expected_dir in test_cases:
            info = matrix.get_closest_version(version_str)
            if info:
                assert info.cassette_dir == expected_dir

    def test_differences_affect_testing(self) -> None:
        """Test that differences can be used for test decisions."""
        matrix = get_version_matrix()

        # Get breaking changes that might affect tests
        breaking = matrix.get_breaking_changes()

        for change in breaking:
            # Breaking changes should have workaround info
            if change.workaround:
                assert len(change.workaround) > 0

    def test_version_detection_environment(self) -> None:
        """Test version detection from environment variables."""
        test_versions = ["5.74.0", "5.76.0", "5.80.0"]

        for version in test_versions:
            with patch.dict(os.environ, {"CIVI_VERSION": version}):
                current = get_current_version()
                assert current == version

                cassette_v = get_cassette_version()
                # Should be short version (5.74 from 5.74.0)
                assert len(cassette_v.split(".")) == 2


class TestDifferenceTypes:
    """Tests for DifferenceType enum coverage."""

    @pytest.mark.parametrize(
        ("diff_type", "requires_field", "requires_action"),
        [
            (DifferenceType.FIELD_ADDED, True, False),
            (DifferenceType.FIELD_REMOVED, True, False),
            (DifferenceType.FIELD_RENAMED, True, False),
            (DifferenceType.FIELD_TYPE_CHANGED, True, False),
            (DifferenceType.FIELD_DEPRECATED, True, False),
            (DifferenceType.DEFAULT_CHANGED, True, False),
            (DifferenceType.ACTION_ADDED, False, True),
            (DifferenceType.ACTION_REMOVED, False, True),
            (DifferenceType.ACTION_CHANGED, False, True),
            (DifferenceType.ENTITY_ADDED, False, False),
            (DifferenceType.ENTITY_REMOVED, False, False),
            (DifferenceType.BEHAVIOR_CHANGED, False, False),
        ],
    )
    def test_difference_type_requirements(
        self,
        diff_type: DifferenceType,
        requires_field: bool,
        requires_action: bool,
    ) -> None:
        """Test that difference types enforce their requirements."""
        kwargs = {
            "entity": "TestEntity",
            "difference_type": diff_type,
            "introduced_in": "5.74.0",
            "severity": Severity.INFO,
        }

        if requires_field:
            # Should fail without field
            with pytest.raises(ValueError, match="field name"):
                APIDifference(**kwargs)

            # Should succeed with field
            kwargs["field"] = "test_field"
            diff = APIDifference(**kwargs)
            assert diff.field == "test_field"

        elif requires_action:
            # Should fail without action
            with pytest.raises(ValueError, match="action name"):
                APIDifference(**kwargs)

            # Should succeed with action
            kwargs["action"] = "test_action"
            diff = APIDifference(**kwargs)
            assert diff.action == "test_action"

        else:
            # Should succeed without field or action
            diff = APIDifference(**kwargs)
            assert diff.entity == "TestEntity"
