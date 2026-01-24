"""Tests for dynamic entity discovery module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from civicrm_py.entities.base import BaseEntity, EntityMeta
from civicrm_py.entities.discovery import (
    EntityDiscovery,
    EntityInfo,
    FieldInfo,
    _build_struct_fields,
    _compute_field_type_and_default,
    _create_dynamic_entity_class,
    _get_default_for_type,
    discover_entities,
)

if TYPE_CHECKING:
    from collections.abc import Generator

# --- FieldInfo Tests ---


class TestFieldInfo:
    """Tests for FieldInfo struct."""

    def test_create_field_info(self) -> None:
        """Test basic FieldInfo creation."""
        field = FieldInfo(
            name="first_name",
            title="First Name",
            data_type="String",
            required=False,
        )
        assert field.name == "first_name"
        assert field.title == "First Name"
        assert field.data_type == "String"
        assert field.required is False

    def test_field_info_defaults(self) -> None:
        """Test FieldInfo default values."""
        field = FieldInfo(name="test_field")
        assert field.title is None
        assert field.description is None
        assert field.data_type is None
        assert field.input_type is None
        assert field.required is False
        assert field.readonly is False
        assert field.serialize is None
        assert field.fk_entity is None
        assert field.options is None
        assert field.default_value is None

    @pytest.mark.parametrize(
        ("data_type", "expected"),
        [
            ("String", "str"),
            ("Text", "str"),
            ("Memo", "str"),
            ("Integer", "int"),
            ("Boolean", "bool"),
            ("Float", "float"),
            ("Money", "float"),
            ("Date", "str"),
            ("Datetime", "str"),
            ("Timestamp", "int"),
            ("Array", "list[Any]"),
            ("Object", "dict[str, Any]"),
            ("Json", "dict[str, Any]"),
            ("Blob", "bytes"),
            ("Unknown", "Any"),
            # None defaults to "String" which maps to "str"
            (None, "str"),
        ],
    )
    def test_to_python_type(self, data_type: str | None, expected: str) -> None:
        """Test CiviCRM to Python type mapping."""
        field = FieldInfo(name="test", data_type=data_type)
        assert field.to_python_type() == expected

    @pytest.mark.parametrize(
        ("data_type", "expected"),
        [
            ("String", str),
            ("Integer", int),
            ("Boolean", bool),
            ("Float", float),
            ("Date", str),
            ("Timestamp", int),
            ("Blob", bytes),
            ("Unknown", object),
        ],
    )
    def test_to_python_type_object(
        self,
        data_type: str,
        expected: type[object],
    ) -> None:
        """Test CiviCRM to Python type object mapping."""
        field = FieldInfo(name="test", data_type=data_type)
        assert field.to_python_type_object() is expected

    def test_from_api_response(self) -> None:
        """Test creating FieldInfo from API response."""
        api_data = {
            "name": "contact_id",
            "title": "Contact ID",
            "description": "FK to Contact",
            "data_type": "Integer",
            "input_type": "EntityRef",
            "required": True,
            "readonly": False,
            "fk_entity": "Contact",
            "default_value": None,
        }
        field = FieldInfo.from_api_response(api_data)

        assert field.name == "contact_id"
        assert field.title == "Contact ID"
        assert field.description == "FK to Contact"
        assert field.data_type == "Integer"
        assert field.input_type == "EntityRef"
        assert field.required is True
        assert field.readonly is False
        assert field.fk_entity == "Contact"

    def test_from_api_response_minimal(self) -> None:
        """Test creating FieldInfo from minimal API response."""
        api_data = {"name": "simple_field"}
        field = FieldInfo.from_api_response(api_data)

        assert field.name == "simple_field"
        assert field.title is None
        assert field.data_type is None
        assert field.required is False


# --- EntityInfo Tests ---


class TestEntityInfo:
    """Tests for EntityInfo struct."""

    def test_create_entity_info(self) -> None:
        """Test basic EntityInfo creation."""
        entity = EntityInfo(
            name="Contact",
            title="Contact",
            type="primary",
            searchable=True,
        )
        assert entity.name == "Contact"
        assert entity.title == "Contact"
        assert entity.type == "primary"
        assert entity.searchable is True

    def test_entity_info_defaults(self) -> None:
        """Test EntityInfo default values."""
        entity = EntityInfo(name="TestEntity")
        assert entity.title is None
        assert entity.description is None
        assert entity.type is None
        assert entity.primary_key is None
        assert entity.searchable is True
        assert entity.label_field is None

    def test_from_api_response(self) -> None:
        """Test creating EntityInfo from API response."""
        api_data = {
            "name": "Activity",
            "title": "Activity",
            "description": "Tracks interactions and tasks",
            "type": "secondary",
            "primary_key": ["id"],
            "searchable": True,
            "label_field": "subject",
        }
        entity = EntityInfo.from_api_response(api_data)

        assert entity.name == "Activity"
        assert entity.title == "Activity"
        assert entity.description == "Tracks interactions and tasks"
        assert entity.type == "secondary"
        assert entity.primary_key == ["id"]
        assert entity.searchable is True
        assert entity.label_field == "subject"

    def test_from_api_response_with_label(self) -> None:
        """Test title fallback to label field."""
        api_data = {
            "name": "TestEntity",
            "label": "Test Entity Label",
        }
        entity = EntityInfo.from_api_response(api_data)
        assert entity.title == "Test Entity Label"

    def test_from_api_response_string_primary_key(self) -> None:
        """Test handling of string primary_key (converted to list)."""
        api_data = {
            "name": "TestEntity",
            "primary_key": "id",
        }
        entity = EntityInfo.from_api_response(api_data)
        assert entity.primary_key == ["id"]


# --- Helper Function Tests ---


class TestHelperFunctions:
    """Tests for discovery helper functions."""

    def test_get_default_for_type(self) -> None:
        """Test type default lookup."""
        assert _get_default_for_type(str) == ""
        assert _get_default_for_type(int) == 0
        assert _get_default_for_type(bool) is False
        assert _get_default_for_type(float) == 0.0
        assert _get_default_for_type(object) is None

    def test_compute_field_type_and_default_required_with_default(self) -> None:
        """Test field with known type default."""
        field = FieldInfo(name="count", data_type="Integer", required=True)
        py_type, default = _compute_field_type_and_default(field)
        assert py_type is int
        assert default == 0

    def test_compute_field_type_and_default_required_no_default(self) -> None:
        """Test required field with unknown type becomes optional."""
        field = FieldInfo(name="data", data_type="Object", required=True)
        _py_type, default = _compute_field_type_and_default(field)
        # Type becomes optional when no default available
        assert default is None

    def test_compute_field_type_and_default_with_explicit_default(self) -> None:
        """Test field with explicit default value."""
        field = FieldInfo(name="status", data_type="String", default_value="active")
        _py_type, default = _compute_field_type_and_default(field)
        assert default == "active"

    def test_compute_field_type_and_default_optional(self) -> None:
        """Test optional field."""
        field = FieldInfo(name="notes", data_type="String", required=False)
        _py_type, default = _compute_field_type_and_default(field)
        assert default is None

    def test_build_struct_fields_adds_id(self) -> None:
        """Test that id field is added if missing."""
        fields = [FieldInfo(name="name", data_type="String")]
        struct_fields = _build_struct_fields(fields)

        # Should have id and name
        field_names = [f[0] for f in struct_fields]
        assert "id" in field_names
        assert "name" in field_names

    def test_build_struct_fields_preserves_id(self) -> None:
        """Test that existing id field is not duplicated."""
        fields = [
            FieldInfo(name="id", data_type="Integer"),
            FieldInfo(name="name", data_type="String"),
        ]
        struct_fields = _build_struct_fields(fields)

        # Should only have one id
        field_names = [f[0] for f in struct_fields]
        assert field_names.count("id") == 1

    def test_build_struct_fields_skips_internal(self) -> None:
        """Test that internal fields (starting with _) are skipped."""
        fields = [
            FieldInfo(name="_internal", data_type="String"),
            FieldInfo(name="public", data_type="String"),
        ]
        struct_fields = _build_struct_fields(fields)

        field_names = [f[0] for f in struct_fields]
        assert "_internal" not in field_names
        assert "public" in field_names

    def test_create_dynamic_entity_class(self) -> None:
        """Test dynamic entity class creation."""
        struct_fields = [
            ("id", int | None, None),
            ("name", str, ""),
            ("active", bool, False),
        ]
        entity_class = _create_dynamic_entity_class("TestEntity", struct_fields)

        assert entity_class.__name__ == "TestEntity"
        assert issubclass(entity_class, BaseEntity)
        assert entity_class.__entity_name__ == "TestEntity"

    def test_create_dynamic_entity_class_instantiation(self) -> None:
        """Test that dynamic entity class can be instantiated."""
        struct_fields = [
            ("id", int | None, None),
            ("name", str | None, None),
        ]
        entity_class = _create_dynamic_entity_class("MyEntity", struct_fields)

        # Create instance
        instance = entity_class(id=1, name="Test")
        assert instance.id == 1
        assert instance.name == "Test"


# --- EntityDiscovery Tests ---


class TestEntityDiscovery:
    """Tests for EntityDiscovery class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create mock CiviClient."""
        return MagicMock(spec=["request", "get_fields"])

    @pytest.fixture
    def discovery(self, mock_client: MagicMock) -> EntityDiscovery:
        """Create EntityDiscovery with mock client."""
        return EntityDiscovery(mock_client, cache_ttl=3600)

    @pytest.mark.asyncio
    async def test_get_entities(self, discovery: EntityDiscovery) -> None:
        """Test fetching entity list."""
        # Setup mock response
        discovery.client.request = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "Contact", "title": "Contact", "type": "primary"},
                    {"name": "Activity", "title": "Activity", "type": "secondary"},
                ],
            ),
        )

        entities = await discovery.get_entities()

        assert len(entities) == 2
        assert entities[0].name == "Contact"
        assert entities[1].name == "Activity"
        discovery.client.request.assert_called_once_with("Entity", "get", {})

    @pytest.mark.asyncio
    async def test_get_entities_caching(self, discovery: EntityDiscovery) -> None:
        """Test that entity list is cached."""
        discovery.client.request = AsyncMock(
            return_value=MagicMock(
                values=[{"name": "Contact", "title": "Contact"}],
            ),
        )

        # First call
        await discovery.get_entities()
        # Second call should use cache
        await discovery.get_entities()

        # Should only have made one API call
        assert discovery.client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_get_entities_refresh(self, discovery: EntityDiscovery) -> None:
        """Test forcing refresh of entity list."""
        discovery.client.request = AsyncMock(
            return_value=MagicMock(
                values=[{"name": "Contact", "title": "Contact"}],
            ),
        )

        await discovery.get_entities()
        await discovery.get_entities(refresh=True)

        # Should have made two API calls
        assert discovery.client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_get_fields(self, discovery: EntityDiscovery) -> None:
        """Test fetching field definitions."""
        discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "id", "data_type": "Integer"},
                    {"name": "display_name", "data_type": "String"},
                ],
            ),
        )

        fields = await discovery.get_fields("Contact")

        assert len(fields) == 2
        assert fields[0].name == "id"
        assert fields[1].name == "display_name"
        discovery.client.get_fields.assert_called_once_with("Contact")

    @pytest.mark.asyncio
    async def test_get_fields_caching(self, discovery: EntityDiscovery) -> None:
        """Test that field definitions are cached."""
        discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[{"name": "id", "data_type": "Integer"}],
            ),
        )

        await discovery.get_fields("Contact")
        await discovery.get_fields("Contact")

        assert discovery.client.get_fields.call_count == 1

    @pytest.mark.asyncio
    async def test_get_entity_class_static(self, discovery: EntityDiscovery) -> None:
        """Test getting static entity class from registry when manually registered."""
        from civicrm_py.entities import Contact

        # Manually register Contact since msgspec.Struct doesn't use EntityMeta metaclass
        EntityMeta.register_dynamic_entity("Contact", Contact)

        entity_class = await discovery.get_entity_class("Contact")

        assert entity_class is Contact

    @pytest.mark.asyncio
    async def test_get_entity_class_dynamic(
        self,
        discovery: EntityDiscovery,
    ) -> None:
        """Test generating dynamic entity class."""
        discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "id", "data_type": "Integer"},
                    {"name": "custom_field", "data_type": "String"},
                ],
            ),
        )

        # Use a name not in static registry
        entity_class = await discovery.get_entity_class("Custom_TestEntity")

        assert entity_class.__name__ == "Custom_TestEntity"
        assert issubclass(entity_class, BaseEntity)

    @pytest.mark.asyncio
    async def test_get_entity_class_caching(
        self,
        discovery: EntityDiscovery,
    ) -> None:
        """Test that dynamic entity classes are cached."""
        discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[{"name": "id", "data_type": "Integer"}],
            ),
        )

        class1 = await discovery.get_entity_class("Custom_CacheTest")
        class2 = await discovery.get_entity_class("Custom_CacheTest")

        # Should return same class instance
        assert class1 is class2
        # Should only have made one API call
        assert discovery.client.get_fields.call_count == 1

    def test_clear_cache(self, discovery: EntityDiscovery) -> None:
        """Test clearing caches."""
        # Add some items to caches manually
        discovery._entity_cache["TestEntity"] = MagicMock()
        discovery._field_cache["TestEntity"] = MagicMock()
        discovery._entity_list_cache = MagicMock()

        discovery.clear_cache()

        assert len(discovery._entity_cache) == 0
        assert len(discovery._field_cache) == 0
        assert discovery._entity_list_cache is None

    @pytest.mark.asyncio
    async def test_get_custom_fields(self, discovery: EntityDiscovery) -> None:
        """Test getting only custom fields."""
        discovery.client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "id", "data_type": "Integer"},
                    {"name": "first_name", "data_type": "String"},
                    {"name": "custom_123", "data_type": "String"},
                    {"name": "custom_456", "data_type": "Integer"},
                ],
            ),
        )

        custom_fields = await discovery.get_custom_fields("Contact")

        assert len(custom_fields) == 2
        assert all(f.name.startswith("custom_") for f in custom_fields)

    @pytest.mark.asyncio
    async def test_get_entity_info(self, discovery: EntityDiscovery) -> None:
        """Test getting metadata for specific entity."""
        discovery.client.request = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "Contact", "title": "Contact"},
                    {"name": "Activity", "title": "Activity"},
                ],
            ),
        )

        info = await discovery.get_entity_info("Contact")

        assert info is not None
        assert info.name == "Contact"

    @pytest.mark.asyncio
    async def test_get_entity_info_not_found(
        self,
        discovery: EntityDiscovery,
    ) -> None:
        """Test getting metadata for non-existent entity."""
        discovery.client.request = AsyncMock(
            return_value=MagicMock(values=[{"name": "Contact", "title": "Contact"}]),
        )

        info = await discovery.get_entity_info("NonExistent")

        assert info is None

    @pytest.mark.asyncio
    async def test_entity_exists(self, discovery: EntityDiscovery) -> None:
        """Test checking if entity exists."""
        discovery.client.request = AsyncMock(
            return_value=MagicMock(values=[{"name": "Contact", "title": "Contact"}]),
        )

        assert await discovery.entity_exists("Contact") is True
        assert await discovery.entity_exists("NonExistent") is False


# --- discover_entities Tests ---


class TestDiscoverEntitiesFunction:
    """Tests for discover_entities convenience function."""

    @pytest.mark.asyncio
    async def test_discover_entities(self) -> None:
        """Test discover_entities function."""
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "Contact", "title": "Contact"},
                    {"name": "Activity", "title": "Activity"},
                ],
            ),
        )
        mock_client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "id", "data_type": "Integer"},
                    {"name": "name", "data_type": "String"},
                ],
            ),
        )

        entities = await discover_entities(mock_client)

        assert "Contact" in entities
        assert "Activity" in entities
        assert issubclass(entities["Contact"], BaseEntity)

    @pytest.mark.asyncio
    async def test_discover_entities_exclude_custom(self) -> None:
        """Test excluding custom entities."""
        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            return_value=MagicMock(
                values=[
                    {"name": "Contact", "title": "Contact"},
                    {"name": "Custom_MyEntity", "title": "My Entity"},
                ],
            ),
        )
        mock_client.get_fields = AsyncMock(
            return_value=MagicMock(
                values=[{"name": "id", "data_type": "Integer"}],
            ),
        )

        entities = await discover_entities(mock_client, include_custom=False)

        assert "Contact" in entities
        assert "Custom_MyEntity" not in entities


# --- Integration Tests ---


class TestDiscoveryIntegration:
    """Integration tests for entity discovery."""

    def test_generated_entity_dirty_tracking(self) -> None:
        """Test that generated entities support dirty tracking."""
        struct_fields = [
            ("id", int | None, None),
            ("name", str | None, None),
            ("active", bool, False),
        ]
        entity_class = _create_dynamic_entity_class("TrackingTest", struct_fields)

        instance = entity_class(id=1, name="Original")
        instance.mark_clean()

        # Modify field
        instance.name = "Modified"

        assert instance.is_dirty
        assert "name" in instance.dirty_fields

    def test_generated_entity_to_dict(self) -> None:
        """Test that generated entities can be serialized."""
        struct_fields = [
            ("id", int | None, None),
            ("name", str | None, None),
            ("count", int, 0),
        ]
        entity_class = _create_dynamic_entity_class("SerializeTest", struct_fields)

        instance = entity_class(id=1, name="Test", count=5)
        data = instance.to_dict()

        assert data["id"] == 1
        assert data["name"] == "Test"
        assert data["count"] == 5

    def test_generated_entity_from_dict(self) -> None:
        """Test that generated entities can be deserialized."""
        struct_fields = [
            ("id", int | None, None),
            ("name", str | None, None),
        ]
        entity_class = _create_dynamic_entity_class("DeserializeTest", struct_fields)

        instance = entity_class.from_dict({"id": 1, "name": "FromDict"})

        assert instance.id == 1
        assert instance.name == "FromDict"
        assert not instance.is_dirty  # Should be clean after from_dict


# --- Cleanup ---


@pytest.fixture(autouse=True)
def cleanup_registry() -> Generator[None, None, None]:
    """Clean up any dynamically registered entities after each test."""
    # Store original registry
    original_registry = EntityMeta._registry.copy()

    yield

    # Restore original registry, removing any test entities
    EntityMeta._registry.clear()
    EntityMeta._registry.update(original_registry)
