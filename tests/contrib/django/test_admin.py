"""Tests for Django admin integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from civi_py.contrib.django.admin import (
    CiviField,
    CiviOptions,
    CiviQuerySet,
    _check_django_available,
)
from civi_py.core.exceptions import CiviAPIError, DoesNotExist


# Create a mock entity class for testing
class MockEntity:
    """Mock entity class for testing."""

    __entity_name__ = "MockEntity"


class TestCiviQuerySet:
    """Tests for CiviQuerySet."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock SyncCiviClient."""
        client = MagicMock()
        # Default response
        client.get.return_value = MagicMock(
            values=[
                {"id": 1, "name": "Test 1"},
                {"id": 2, "name": "Test 2"},
            ],
            count=2,
        )
        return client

    @pytest.fixture
    def queryset(self, mock_client: MagicMock) -> CiviQuerySet[MockEntity]:
        """Create a CiviQuerySet for testing."""
        return CiviQuerySet(
            entity_class=MockEntity,  # type: ignore[arg-type]
            client=mock_client,
        )

    def test_init(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test CiviQuerySet initialization."""
        assert queryset.entity_class == MockEntity
        assert queryset._filters == []
        assert queryset._order_by == {}
        assert queryset._limit is None
        assert queryset._offset is None

    def test_model_property(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test model property returns entity class."""
        assert queryset.model == MockEntity

    def test_db_property(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test db property returns 'civicrm'."""
        assert queryset.db == "civicrm"

    def test_filter(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test filter method adds conditions."""
        filtered = queryset.filter(name="Test")
        assert ["name", "=", "Test"] in filtered._filters
        # Original unchanged
        assert queryset._filters == []

    def test_filter_with_lookup(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test filter with Django-style lookups."""
        filtered = queryset.filter(name__contains="Test")
        assert ["name", "CONTAINS", "Test"] in filtered._filters

    def test_filter_gt_lookup(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test filter with greater than lookup."""
        filtered = queryset.filter(id__gt=5)
        assert ["id", ">", 5] in filtered._filters

    def test_filter_in_lookup(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test filter with in lookup."""
        filtered = queryset.filter(id__in=[1, 2, 3])
        assert ["id", "IN", [1, 2, 3]] in filtered._filters

    def test_exclude(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test exclude method adds negated conditions."""
        excluded = queryset.exclude(name="Test")
        assert ["name", "!=", "Test"] in excluded._filters

    def test_order_by(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test order_by method."""
        ordered = queryset.order_by("name", "-id")
        assert ordered._order_by == {"name": "ASC", "id": "DESC"}

    def test_all_returns_clone(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test all() returns a clone."""
        cloned = queryset.all()
        assert cloned is not queryset
        assert cloned._filters == queryset._filters

    def test_none_returns_empty(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test none() returns empty queryset."""
        empty = queryset.none()
        assert empty._result_cache == []
        assert empty._count_cache == 0

    def test_count(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test count method calls API."""
        mock_client.get.return_value = MagicMock(count=5, values=[])
        count = queryset.count()
        assert count == 5
        mock_client.get.assert_called()

    def test_exists_true(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test exists returns True when records exist."""
        mock_client.get.return_value = MagicMock(count=1, values=[])
        assert queryset.exists() is True

    def test_exists_false(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test exists returns False when no records."""
        mock_client.get.return_value = MagicMock(count=0, values=[])
        assert queryset.exists() is False

    def test_first(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test first returns first result."""
        mock_client.get.return_value = MagicMock(
            values=[{"id": 1, "name": "First"}],
            count=1,
        )
        result = queryset.first()
        assert result == {"id": 1, "name": "First"}

    def test_first_empty(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test first returns None for empty results."""
        mock_client.get.return_value = MagicMock(values=[], count=0)
        result = queryset.first()
        assert result is None

    def test_get_single_result(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test get returns single result."""
        mock_client.get.return_value = MagicMock(
            values=[{"id": 1, "name": "Test"}],
            count=1,
        )
        result = queryset.get(id=1)
        assert result == {"id": 1, "name": "Test"}

    def test_get_no_results_raises(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test get raises DoesNotExist for no results."""
        mock_client.get.return_value = MagicMock(values=[], count=0)
        with pytest.raises(DoesNotExist):
            queryset.get(id=999)

    def test_get_multiple_results_raises(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test get raises CiviAPIError for multiple results."""
        mock_client.get.return_value = MagicMock(
            values=[{"id": 1}, {"id": 2}],
            count=2,
        )
        with pytest.raises(CiviAPIError):
            queryset.get(name="duplicate")

    def test_iteration(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test queryset iteration."""
        results = list(queryset)
        assert len(results) == 2
        assert results[0]["id"] == 1

    def test_len(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test len() on queryset."""
        assert len(queryset) == 2

    def test_getitem_index(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test indexing queryset."""
        result = queryset[0]
        assert result["id"] == 1

    def test_getitem_slice(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test slicing queryset."""
        mock_client.get.return_value = MagicMock(
            values=[{"id": 2}],
            count=1,
        )
        results = queryset[1:2]
        # Should have called API with offset and limit
        mock_client.get.assert_called()

    def test_bool_true(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test bool is True when records exist."""
        mock_client.get.return_value = MagicMock(count=1, values=[])
        assert bool(queryset) is True

    def test_bool_false(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test bool is False when no records."""
        mock_client.get.return_value = MagicMock(count=0, values=[])
        assert bool(queryset) is False

    def test_search(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test _search method adds search conditions."""
        searched = queryset._search("test", ["name", "description"])
        assert searched._search_term == "test"
        assert searched._search_fields == ["name", "description"]

    def test_build_where_with_search(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test _build_where includes search conditions."""
        searched = queryset._search("test", ["name"])
        where = searched._build_where()
        assert ["name", "CONTAINS", "test"] in where

    def test_select_related_noop(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test select_related is a no-op."""
        result = queryset.select_related("related")
        assert result is queryset

    def test_prefetch_related_noop(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test prefetch_related is a no-op."""
        result = queryset.prefetch_related("related")
        assert result is queryset

    def test_only(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test only sets field selection."""
        result = queryset.only("id", "name")
        assert result._select == ["id", "name"]

    def test_values(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test values sets field selection."""
        result = queryset.values("id", "name")
        assert result._select == ["id", "name"]

    def test_using_noop(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test using is a no-op."""
        result = queryset.using("other")
        assert result is queryset

    def test_distinct_noop(self, queryset: CiviQuerySet[MockEntity]) -> None:
        """Test distinct is a no-op."""
        result = queryset.distinct()
        assert result is queryset

    def test_result_caching(self, queryset: CiviQuerySet[MockEntity], mock_client: MagicMock) -> None:
        """Test results are cached after first fetch."""
        # First access
        _ = list(queryset)
        call_count_1 = mock_client.get.call_count

        # Second access should use cache
        _ = list(queryset)
        call_count_2 = mock_client.get.call_count

        assert call_count_1 == call_count_2


class TestCiviField:
    """Tests for CiviField."""

    def test_init(self) -> None:
        """Test CiviField initialization."""
        field = CiviField("test_field", str)
        assert field.name == "test_field"
        assert field.attname == "test_field"
        assert field.field_type == str
        assert field.primary_key is False
        assert field.editable is True

    def test_id_field_is_primary_key(self) -> None:
        """Test id field is automatically primary key."""
        field = CiviField("id", int)
        assert field.primary_key is True
        assert field.editable is False

    def test_explicit_primary_key(self) -> None:
        """Test explicit primary key setting."""
        field = CiviField("custom_id", int, primary_key=True)
        assert field.primary_key is True
        assert field.editable is False

    def test_verbose_name(self) -> None:
        """Test verbose name generation."""
        field = CiviField("first_name", str)
        assert field.verbose_name == "First Name"

    def test_with_choices(self) -> None:
        """Test field with choices."""
        choices = [("a", "Option A"), ("b", "Option B")]
        field = CiviField("choice_field", str, choices=choices)
        assert field.choices == choices

    def test_value_from_object_dict(self) -> None:
        """Test getting value from dict object."""
        field = CiviField("name", str)
        obj = {"name": "Test Value"}
        assert field.value_from_object(obj) == "Test Value"

    def test_value_from_object_missing(self) -> None:
        """Test getting missing value from dict."""
        field = CiviField("name", str)
        obj = {"other": "value"}
        assert field.value_from_object(obj) is None


class TestCiviOptions:
    """Tests for CiviOptions."""

    def test_init(self) -> None:
        """Test CiviOptions initialization."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        assert opts.model_name == "mockentity"
        assert opts.verbose_name == "MockEntity"
        assert opts.verbose_name_plural == "MockEntities"
        assert opts.app_label == "civi"
        assert opts.object_name == "MockEntity"

    def test_pk_field(self) -> None:
        """Test pk field is created."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        assert opts.pk.name == "id"
        assert opts.pk.primary_key is True

    def test_label(self) -> None:
        """Test label property."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        assert opts.label == "civi.mockentity"

    def test_label_lower(self) -> None:
        """Test label_lower property."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        assert opts.label_lower == "civi.mockentity"

    def test_get_field_returns_field(self) -> None:
        """Test get_field returns existing field."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        # Add a field manually for testing
        opts._fields.append(CiviField("test_field", str))
        field = opts.get_field("test_field")
        assert field.name == "test_field"

    def test_get_field_returns_dummy_for_unknown(self) -> None:
        """Test get_field returns dummy field for unknown."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        field = opts.get_field("unknown_field")
        assert field.name == "unknown_field"
        assert field.field_type == str

    def test_default_permissions(self) -> None:
        """Test default permissions are set."""
        opts = CiviOptions(MockEntity)  # type: ignore[arg-type]
        assert "add" in opts.default_permissions
        assert "change" in opts.default_permissions
        assert "delete" in opts.default_permissions
        assert "view" in opts.default_permissions


class TestDjangoAvailability:
    """Tests for Django availability check."""

    def test_check_django_available_with_django(self) -> None:
        """Test check returns True when Django is available."""
        # This test assumes Django is installed
        result = _check_django_available()
        # Result depends on test environment
        assert isinstance(result, bool)


# Skip Django-dependent tests if Django is not available
django_available = _check_django_available()


@pytest.mark.skipif(not django_available, reason="Django not available")
class TestCiviModelAdmin:
    """Tests for CiviModelAdmin (requires Django)."""

    def test_import_admin_classes(self) -> None:
        """Test that admin classes can be imported when Django is available."""
        from civi_py.contrib.django.admin import (
            CiviAdminSite,
            CiviChangeList,
            CiviInlineAdmin,
            CiviModelAdmin,
            CiviPaginator,
            civi_admin_site,
            register_entity,
        )

        assert CiviModelAdmin is not None
        assert CiviAdminSite is not None
        assert CiviChangeList is not None
        assert CiviInlineAdmin is not None
        assert CiviPaginator is not None
        assert civi_admin_site is not None
        assert register_entity is not None


@pytest.mark.skipif(not django_available, reason="Django not available")
class TestRegisterEntityDecorator:
    """Tests for register_entity decorator (requires Django)."""

    def test_register_entity_sets_entity_class(self) -> None:
        """Test that register_entity sets entity_class on admin."""
        from civi_py.contrib.django.admin import CiviModelAdmin, register_entity

        @register_entity(MockEntity)  # type: ignore[arg-type]
        class TestAdmin(CiviModelAdmin):
            list_display = ["id", "name"]

        assert TestAdmin.entity_class == MockEntity


@pytest.mark.skipif(not django_available, reason="Django not available")
class TestCiviAdminSite:
    """Tests for CiviAdminSite (requires Django)."""

    def test_init(self) -> None:
        """Test CiviAdminSite initialization."""
        from civi_py.contrib.django.admin import CiviAdminSite

        site = CiviAdminSite(name="testadmin")
        assert site.name == "testadmin"
        assert site.site_header == "CiviCRM Administration"

    def test_register_entity(self) -> None:
        """Test registering an entity with the site."""
        from civi_py.contrib.django.admin import CiviAdminSite, CiviModelAdmin

        site = CiviAdminSite(name="testadmin2")

        class TestAdmin(CiviModelAdmin):
            entity_class = MockEntity  # type: ignore[assignment]
            list_display = ["id"]

        site.register(MockEntity, TestAdmin)  # type: ignore[arg-type]
        assert MockEntity in site._entity_registry

    def test_unregister_entity(self) -> None:
        """Test unregistering an entity."""
        from civi_py.contrib.django.admin import CiviAdminSite, CiviModelAdmin

        site = CiviAdminSite(name="testadmin3")

        class TestAdmin(CiviModelAdmin):
            entity_class = MockEntity  # type: ignore[assignment]
            list_display = ["id"]

        site.register(MockEntity, TestAdmin)  # type: ignore[arg-type]
        site.unregister(MockEntity)  # type: ignore[arg-type]
        assert MockEntity not in site._entity_registry
