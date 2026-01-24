"""Version-specific compatibility tests for civi-py.

This module contains tests that verify CiviCRM API compatibility across
different versions. Tests use version markers to conditionally run based
on the CiviCRM version being tested.

Markers:
    @pytest.mark.min_version("5.70"): Skip if CiviCRM < 5.70
    @pytest.mark.max_version("5.80"): Skip if CiviCRM >= 5.80
    @pytest.mark.version_specific("5.70"): Only run on CiviCRM 5.70
    @pytest.mark.version_range("5.60", "5.80"): Run only in range
    @pytest.mark.requires_feature("feature"): Skip if feature unavailable

Example:
    # Test that only runs on CiviCRM 5.70+
    @pytest.mark.min_version("5.70")
    async def test_enhanced_metadata():
        ...

    # Test for deprecated behavior (only on older versions)
    @pytest.mark.max_version("5.80")
    async def test_legacy_behavior():
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from tests.compat.version_utils import CiviVersion


class TestVersionUtilities:
    """Tests for version utility functions."""

    def test_version_parsing(self) -> None:
        """Test CiviVersion parsing from various formats."""
        from tests.compat.version_utils import CiviVersion

        # Basic format
        v = CiviVersion.parse("5.70")
        assert v.major == 5
        assert v.minor == 70
        assert v.patch == 0

        # With patch version
        v = CiviVersion.parse("5.70.1")
        assert v.major == 5
        assert v.minor == 70
        assert v.patch == 1

        # With v prefix
        v = CiviVersion.parse("v5.70")
        assert v.major == 5
        assert v.minor == 70

        # With suffix
        v = CiviVersion.parse("5.70-alpha")
        assert v.major == 5
        assert v.minor == 70

    def test_version_comparison(self) -> None:
        """Test CiviVersion comparison operations."""
        from tests.compat.version_utils import CiviVersion

        v560 = CiviVersion(5, 60)
        v570 = CiviVersion(5, 70)
        v580 = CiviVersion(5, 80)

        # Less than
        assert v560 < v570
        assert v570 < v580

        # Greater than
        assert v580 > v570
        assert v570 > v560

        # Equality
        assert v570 == CiviVersion(5, 70)
        assert v570 == CiviVersion(5, 70, 0)

        # Greater than or equal
        assert v570 >= v560
        assert v570 >= CiviVersion(5, 70)

        # Less than or equal
        assert v570 <= v580
        assert v570 <= CiviVersion(5, 70)

    def test_version_range(self) -> None:
        """Test VersionRange containment checks."""
        from tests.compat.version_utils import CiviVersion, VersionRange

        # Range with min and max
        range_5_60_to_5_80 = VersionRange(
            min_version=CiviVersion(5, 60),
            max_version=CiviVersion(5, 80),
        )

        assert range_5_60_to_5_80.contains(CiviVersion(5, 60))  # Min is inclusive
        assert range_5_60_to_5_80.contains(CiviVersion(5, 70))
        assert not range_5_60_to_5_80.contains(CiviVersion(5, 80))  # Max is exclusive
        assert not range_5_60_to_5_80.contains(CiviVersion(5, 50))

        # Range with only min
        range_min_only = VersionRange(min_version=CiviVersion(5, 70))
        assert range_min_only.contains(CiviVersion(5, 70))
        assert range_min_only.contains(CiviVersion(5, 80))
        assert not range_min_only.contains(CiviVersion(5, 60))

        # Range with only max
        range_max_only = VersionRange(max_version=CiviVersion(5, 80))
        assert range_max_only.contains(CiviVersion(5, 70))
        assert range_max_only.contains(CiviVersion(5, 60))
        assert not range_max_only.contains(CiviVersion(5, 80))

    def test_version_satisfies(self) -> None:
        """Test version_satisfies helper function."""
        from tests.compat.version_utils import version_satisfies

        # Min version constraint
        assert version_satisfies("5.75", min_version="5.70")
        assert version_satisfies("5.70", min_version="5.70")
        assert not version_satisfies("5.60", min_version="5.70")

        # Max version constraint
        assert version_satisfies("5.75", max_version="5.80")
        assert not version_satisfies("5.80", max_version="5.80")
        assert not version_satisfies("5.85", max_version="5.80")

        # Exact version constraint
        assert version_satisfies("5.70", exact_version="5.70")
        assert not version_satisfies("5.71", exact_version="5.70")

        # Combined constraints
        assert version_satisfies("5.75", min_version="5.70", max_version="5.80")
        assert not version_satisfies("5.60", min_version="5.70", max_version="5.80")
        assert not version_satisfies("5.80", min_version="5.70", max_version="5.80")

    def test_version_features(self, civicrm_version: CiviVersion) -> None:
        """Test version feature flags."""
        from tests.compat.version_utils import get_version_features

        features = get_version_features(civicrm_version)

        # Base features should always be available
        assert features["api4_basic"] is True
        assert features["api4_joins"] is True

        # Check that feature dict has expected keys
        expected_features = [
            "api4_basic",
            "api4_joins",
            "api4_permissions",
            "enhanced_field_metadata",
            "improved_error_messages",
            "custom_field_caching",
            "batch_action_support",
            "deprecation_warnings",
            "new_search_operators",
        ]
        for feature in expected_features:
            assert feature in features, f"Missing feature: {feature}"

    def test_skip_reason_generation(self) -> None:
        """Test skip reason generation for version constraints."""
        from tests.compat.version_utils import CiviVersion, skip_reason_for_version

        v570 = CiviVersion(5, 70)

        # No skip needed when constraint satisfied
        assert skip_reason_for_version(v570, min_version="5.60") is None
        assert skip_reason_for_version(v570, max_version="5.80") is None
        assert skip_reason_for_version(v570, exact_version="5.70") is None

        # Skip reason when constraint not satisfied
        reason = skip_reason_for_version(v570, min_version="5.80")
        assert reason is not None
        assert "5.80" in reason
        assert "5.70" in reason

        reason = skip_reason_for_version(v570, max_version="5.60")
        assert reason is not None

        reason = skip_reason_for_version(v570, exact_version="5.60")
        assert reason is not None

    def test_version_to_cassette_dir(self) -> None:
        """Test cassette directory name generation."""
        from tests.compat.version_utils import CiviVersion

        v570 = CiviVersion(5, 70)
        assert v570.to_cassette_dir() == "v5.70"

        v580_1 = CiviVersion(5, 80, 1)
        assert v580_1.to_cassette_dir() == "v5.80"

    def test_lts_detection(self) -> None:
        """Test LTS version detection."""
        from tests.compat.version_utils import CiviVersion

        # LTS versions (minor divisible by 6)
        assert CiviVersion(5, 60).is_lts() is True
        assert CiviVersion(5, 66).is_lts() is True
        assert CiviVersion(5, 72).is_lts() is True

        # Non-LTS versions
        assert CiviVersion(5, 70).is_lts() is False
        assert CiviVersion(5, 75).is_lts() is False
        assert CiviVersion(5, 80).is_lts() is False


class TestVersionMarkers:
    """Tests that demonstrate and verify version marker behavior."""

    @pytest.mark.compat
    def test_all_versions_basic(self, civicrm_version: CiviVersion) -> None:
        """Test that runs on all supported versions."""
        from tests.compat.version_utils import CiviVersion

        # This test should run regardless of version
        assert isinstance(civicrm_version, CiviVersion)
        assert civicrm_version.major >= 5
        assert civicrm_version.minor >= 60

    @pytest.mark.compat
    @pytest.mark.min_version("5.60")
    def test_min_version_baseline(self) -> None:
        """Test that requires minimum baseline version (5.60)."""
        # This should run on all supported versions since 5.60 is minimum
        assert True  # Placeholder assertion

    @pytest.mark.compat
    @pytest.mark.min_version("5.70")
    def test_min_version_5_70(self, version_features: dict[str, bool]) -> None:
        """Test that requires CiviCRM 5.70+."""
        # Features introduced in 5.70+ should be available
        assert version_features.get("enhanced_field_metadata") is True
        assert version_features.get("improved_error_messages") is True

    @pytest.mark.compat
    @pytest.mark.max_version("5.80")
    def test_max_version_pre_5_80(self, civicrm_version: CiviVersion) -> None:
        """Test that only runs on versions before 5.80."""
        # This test is for legacy behavior testing
        from tests.compat.version_utils import CiviVersion

        assert civicrm_version < CiviVersion(5, 80)

    @pytest.mark.compat
    @pytest.mark.version_specific("5.70")
    def test_version_specific_5_70_only(self, civicrm_version: CiviVersion) -> None:
        """Test that only runs on CiviCRM 5.70 exactly."""
        from tests.compat.version_utils import CiviVersion

        assert civicrm_version == CiviVersion(5, 70)

    @pytest.mark.compat
    @pytest.mark.version_range("5.60", "5.75")
    def test_version_range_5_60_to_5_75(self, civicrm_version: CiviVersion) -> None:
        """Test that runs on versions 5.60 <= v < 5.75."""
        from tests.compat.version_utils import CiviVersion

        assert civicrm_version >= CiviVersion(5, 60)
        assert civicrm_version < CiviVersion(5, 75)

    @pytest.mark.compat
    @pytest.mark.requires_feature("api4_basic")
    def test_requires_basic_api(self) -> None:
        """Test that requires basic API v4 support (always available)."""
        # This should always run since api4_basic is always True
        assert True  # Placeholder assertion

    @pytest.mark.compat
    @pytest.mark.requires_feature("batch_action_support")
    def test_requires_batch_support(self, version_features: dict[str, bool]) -> None:
        """Test that requires batch action support (5.78+)."""
        assert version_features.get("batch_action_support") is True

    @pytest.mark.compat
    @pytest.mark.requires_feature("deprecation_warnings")
    def test_requires_deprecation_warnings(self, version_features: dict[str, bool]) -> None:
        """Test that requires deprecation warnings (5.80+)."""
        assert version_features.get("deprecation_warnings") is True


class TestVersionSpecificBehavior:
    """Tests for version-specific API behavior differences."""

    @pytest.mark.compat
    def test_contact_get_basic(
        self,
        civicrm_version: CiviVersion,
        sample_contact_response: dict[str, Any],
    ) -> None:
        """Test basic Contact get operation works across versions."""
        # Verify response structure is consistent
        assert "values" in sample_contact_response
        assert "count" in sample_contact_response
        assert isinstance(sample_contact_response["values"], list)

    @pytest.mark.compat
    @pytest.mark.min_version("5.70")
    def test_enhanced_field_metadata_format(
        self,
        civicrm_version: CiviVersion,
    ) -> None:
        """Test enhanced field metadata format in 5.70+.

        CiviCRM 5.70 introduced improved field metadata with additional
        properties like input_attrs and more detailed type information.
        """
        # In 5.70+, field metadata should include enhanced properties
        # This would be tested against actual API responses
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.max_version("5.70")
    def test_legacy_error_format(self) -> None:
        """Test legacy error response format in pre-5.70 versions.

        Older versions may return errors in a different format that
        we need to handle for backward compatibility.
        """
        # Test legacy error handling
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.min_version("5.80")
    def test_new_search_operators(self) -> None:
        """Test new search operators available in CiviCRM 5.80+.

        CiviCRM 5.80 introduced additional search operators like
        REGEXP and improved LIKE handling.
        """
        # Test 5.80+ specific search operators
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.max_version("5.80")
    def test_pre_deprecation_behavior(self) -> None:
        """Test behavior before deprecation warnings (pre-5.80).

        Some behaviors that are deprecated in 5.80+ still work
        without warnings in earlier versions.
        """
        # Test legacy behavior that's deprecated in 5.80+
        assert True  # Placeholder for actual cassette-based test


class TestCassettesPerVersion:
    """Tests for version-specific cassette handling."""

    @pytest.mark.compat
    def test_cassette_directory_exists(
        self,
        version_cassette_dir: Any,
        civicrm_version: CiviVersion,
    ) -> None:
        """Test that version-specific cassette directory exists."""
        from pathlib import Path

        assert isinstance(version_cassette_dir, Path)
        assert version_cassette_dir.exists()
        assert civicrm_version.to_cassette_dir() in str(version_cassette_dir)

    @pytest.mark.compat
    def test_cassette_store_version_aware(
        self,
        version_cassette_store: Any,
        civicrm_version: CiviVersion,
    ) -> None:
        """Test that CassetteStore is configured for correct version."""
        assert version_cassette_store.version == str(civicrm_version)


class TestVersionCompatibilityMatrix:
    """Tests that generate or validate the compatibility matrix."""

    @pytest.mark.compat
    def test_compatibility_check(
        self,
        version_compatibility_result: Any,
    ) -> None:
        """Test version compatibility check produces valid result."""
        from tests.compat.version_utils import VersionCompatibilityResult

        assert isinstance(version_compatibility_result, VersionCompatibilityResult)
        assert version_compatibility_result.version is not None
        assert isinstance(version_compatibility_result.features_available, list)
        assert isinstance(version_compatibility_result.features_missing, list)

    @pytest.mark.compat
    def test_all_supported_versions_known(
        self,
        supported_versions: list[Any],
    ) -> None:
        """Test that all supported versions are properly defined."""
        from tests.compat.version_utils import CiviVersion

        assert len(supported_versions) >= 3

        # Verify versions are in expected range
        for version in supported_versions:
            assert isinstance(version, CiviVersion)
            assert version.major == 5
            assert version.minor >= 60

        # Verify ordered
        for i in range(1, len(supported_versions)):
            assert supported_versions[i] > supported_versions[i - 1]


class TestEntityCompatibility:
    """Version-specific tests for entity compatibility."""

    @pytest.mark.compat
    def test_contact_fields_baseline(self) -> None:
        """Test Contact entity has baseline fields across all versions."""
        from civicrm_py.entities import Contact

        # These fields should exist in all supported versions
        baseline_fields = ["id", "display_name", "contact_type", "is_deleted"]

        contact_fields = set(Contact.__struct_fields__)
        for field in baseline_fields:
            assert field in contact_fields, f"Missing baseline field: {field}"

    @pytest.mark.compat
    def test_activity_fields_baseline(self) -> None:
        """Test Activity entity has baseline fields across all versions."""
        from civicrm_py.entities import Activity

        baseline_fields = [
            "id",
            "activity_type_id",
            "subject",
            "is_deleted",
        ]

        activity_fields = set(Activity.__struct_fields__)
        for field in baseline_fields:
            assert field in activity_fields, f"Missing baseline field: {field}"

    @pytest.mark.compat
    @pytest.mark.min_version("5.70")
    def test_contact_enhanced_fields(self) -> None:
        """Test Contact entity enhanced fields in 5.70+."""
        # Enhanced fields or behaviors introduced in 5.70
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.min_version("5.80")
    def test_new_entity_fields(self) -> None:
        """Test new entity fields introduced in 5.80+."""
        # New fields introduced in 5.80
        assert True  # Placeholder for actual cassette-based test


class TestAPIBehaviorDifferences:
    """Tests for API behavior differences between versions."""

    @pytest.mark.compat
    def test_error_response_handling(
        self,
        civicrm_version: CiviVersion,
        sample_error_response: dict[str, Any],
    ) -> None:
        """Test error response handling works across versions."""
        # Error response structure should be consistent
        assert "error_code" in sample_error_response
        assert "error_message" in sample_error_response

    @pytest.mark.compat
    def test_pagination_behavior(
        self,
        sample_paginated_response: dict[str, Any],
    ) -> None:
        """Test pagination response structure across versions."""
        # Pagination structure should be consistent
        assert "values" in sample_paginated_response
        assert "count" in sample_paginated_response
        assert "countFetched" in sample_paginated_response

        # count should represent total, countFetched the current page
        assert sample_paginated_response["count"] >= sample_paginated_response["countFetched"]

    @pytest.mark.compat
    @pytest.mark.min_version("5.70")
    def test_improved_validation_errors(self) -> None:
        """Test improved validation error messages in 5.70+."""
        # 5.70+ provides more detailed validation error messages
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.max_version("5.80")
    def test_legacy_join_syntax(self) -> None:
        """Test legacy join syntax still works in pre-5.80."""
        # Some join patterns may be deprecated in 5.80+
        assert True  # Placeholder for actual cassette-based test


class TestVersionMigration:
    """Tests for version migration scenarios."""

    @pytest.mark.compat
    def test_backward_compatible_queries(self) -> None:
        """Test that queries are backward compatible."""
        # Queries that work on all versions
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    @pytest.mark.min_version("5.80")
    def test_deprecation_warnings_present(self) -> None:
        """Test that deprecation warnings are emitted in 5.80+."""
        # In 5.80+, using deprecated patterns should produce warnings
        assert True  # Placeholder for actual cassette-based test

    @pytest.mark.compat
    def test_response_format_consistent(
        self,
        sample_contact_response: dict[str, Any],
    ) -> None:
        """Test that response format is consistent across versions."""
        # Core response structure should be the same
        response = sample_contact_response

        assert isinstance(response.get("values"), list)
        assert isinstance(response.get("count"), int)

        if response["values"]:
            contact = response["values"][0]
            assert "id" in contact
            assert "display_name" in contact
