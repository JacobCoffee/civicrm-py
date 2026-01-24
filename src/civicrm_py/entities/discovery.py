"""Dynamic entity discovery from CiviCRM API introspection.

This module provides functionality to discover and dynamically generate
entity classes from CiviCRM API metadata. It supports:

- Querying available entities from the CiviCRM instance
- Retrieving field definitions for any entity
- Dynamically generating Python entity classes
- Caching metadata for performance

The discovery system is particularly useful for:
- Custom entities defined in CiviCRM extensions
- Custom fields added to standard entities
- Building generic tools that work with any CiviCRM configuration

Example:
    >>> async with CiviClient() as client:
    ...     discovery = EntityDiscovery(client)
    ...
    ...     # List all available entities
    ...     entities = await discovery.get_entities()
    ...     for entity in entities:
    ...         print(f"{entity.name}: {entity.title}")
    ...
    ...     # Get a custom entity class
    ...     CustomEntity = await discovery.get_entity_class("Custom_MyEntity")
    ...
    ...     # Use it like any other entity
    ...     records = await client.get("Custom_MyEntity", limit=10)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, ClassVar

import msgspec

from civicrm_py.entities.base import BaseEntity, EntityMeta

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient

__all__ = [
    "EntityDiscovery",
    "EntityInfo",
    "FieldInfo",
    "discover_entities",
]

# Type defaults for required fields without explicit defaults
_TYPE_DEFAULTS: dict[type[Any], Any] = {
    str: "",
    int: 0,
    bool: False,
    float: 0.0,
}


def _get_default_for_type(py_type: type[object]) -> object | None:
    """Get the default value for a Python type.

    Args:
        py_type: Python type object.

    Returns:
        Appropriate default value for the type.
    """
    return _TYPE_DEFAULTS.get(py_type)


def _compute_field_type_and_default(
    field: FieldInfo,
) -> tuple[Any, Any]:
    """Compute the Python type and default value for a field.

    Args:
        field: FieldInfo describing the field.

    Returns:
        Tuple of (python_type, default_value).
    """
    py_type: Any = field.to_python_type_object()
    default: Any

    if field.required and field.default_value is None:
        # Required with no default - use type's default if available
        type_default = _get_default_for_type(py_type)
        if type_default is not None:
            default = type_default
        else:
            # No type default, make optional
            default = None
            py_type = py_type | None
    elif field.default_value is not None:
        # Has explicit default
        default = field.default_value
    else:
        # Optional field - use None as default
        default = None
        # Make type optional if not already NoneType
        if py_type is not type(None):
            py_type = py_type | None

    return py_type, default


def _build_struct_fields(
    fields: list[FieldInfo],
) -> list[tuple[str, Any, Any]]:
    """Build struct field definitions from FieldInfo list.

    Args:
        fields: List of FieldInfo objects.

    Returns:
        List of (name, type, default) tuples for struct creation.
    """
    struct_fields: list[tuple[str, Any, Any]] = []

    # Always include id as optional (may be None for new entities)
    has_id = any(f.name == "id" for f in fields)
    if not has_id:
        struct_fields.append(("id", int | None, None))

    for field in fields:
        # Skip internal fields
        if field.name.startswith("_"):
            continue

        py_type, default = _compute_field_type_and_default(field)
        struct_fields.append((field.name, py_type, default))

    return struct_fields


def _create_dynamic_entity_class(
    name: str,
    struct_fields: list[tuple[str, Any, Any]],
) -> type[BaseEntity]:
    """Create a dynamic entity class from field definitions.

    Uses msgspec.defstruct to create a proper struct class, then wraps
    it with BaseEntity methods via composition.

    Args:
        name: Entity name.
        struct_fields: List of (name, type, default) tuples.

    Returns:
        New entity class inheriting from BaseEntity.
    """
    # Use msgspec.defstruct to create a proper struct with all fields
    # Include the internal fields from BaseEntity
    all_fields = [
        *struct_fields,
        ("_state", "Any | None", None),
        ("_client", "Any | None", None),
    ]

    # Create the dynamic struct class
    dynamic_struct = msgspec.defstruct(
        name,
        all_fields,  # type: ignore[arg-type]
        bases=(BaseEntity,),
        kw_only=True,
        omit_defaults=True,
    )

    # Set entity name class variables (these are used internally by BaseEntity)
    dynamic_struct.__entity_name__ = name  # type: ignore[attr-defined]
    dynamic_struct._entity_name = name  # type: ignore[attr-defined]  # noqa: SLF001

    return dynamic_struct  # type: ignore[return-value]


logger = logging.getLogger(__name__)


class FieldInfo(msgspec.Struct, kw_only=True):
    """Information about an entity field from CiviCRM API.

    Contains metadata about a single field including its name, type,
    constraints, and relationships. This information is used to generate
    appropriate Python type hints and validation.

    Attributes:
        name: Field name as used in API requests.
        title: Human-readable field title.
        description: Detailed description of the field's purpose.
        data_type: CiviCRM data type ('String', 'Integer', 'Boolean', etc.).
        input_type: Form input type ('Text', 'Select', 'CheckBox', etc.).
        required: Whether the field is required for create operations.
        readonly: Whether the field is read-only.
        serialize: Serialization type for complex fields.
        fk_entity: Foreign key entity reference (e.g., 'Contact' for contact_id).
        options: Valid option values for select/radio fields.
        default_value: Default value if not specified.

    Example:
        >>> field = FieldInfo(
        ...     name="first_name",
        ...     title="First Name",
        ...     data_type="String",
        ...     required=False,
        ... )
        >>> field.to_python_type()
        'str'
    """

    name: str
    title: str | None = None
    description: str | None = None
    data_type: str | None = None
    input_type: str | None = None
    required: bool = False
    readonly: bool = False
    serialize: str | None = None
    fk_entity: str | None = None
    options: dict[str, Any] | None = None
    default_value: Any = None

    # Mapping from CiviCRM data types to Python type strings
    _TYPE_MAP: ClassVar[dict[str, str]] = {
        "String": "str",
        "Text": "str",
        "Memo": "str",
        "Integer": "int",
        "Boolean": "bool",
        "Float": "float",
        "Money": "float",
        "Date": "str",
        "Datetime": "str",
        "Timestamp": "int",
        "Array": "list[Any]",
        "Object": "dict[str, Any]",
        "Json": "dict[str, Any]",
        "Blob": "bytes",
    }

    def to_python_type(self) -> str:
        """Convert CiviCRM data type to Python type annotation string.

        Maps CiviCRM types (String, Integer, Boolean, etc.) to their
        Python equivalents. Unknown types default to 'Any'.

        Returns:
            Python type annotation as a string.

        Example:
            >>> FieldInfo(name="count", data_type="Integer").to_python_type()
            'int'
            >>> FieldInfo(name="active", data_type="Boolean").to_python_type()
            'bool'
            >>> FieldInfo(name="data", data_type="Unknown").to_python_type()
            'Any'
        """
        return self._TYPE_MAP.get(self.data_type or "String", "Any")

    def to_python_type_object(self) -> type[Any]:
        """Convert CiviCRM data type to actual Python type object.

        Returns the Python type class rather than a string annotation.
        Used for runtime type checking and dynamic class generation.

        Returns:
            Python type object.

        Example:
            >>> FieldInfo(name="count", data_type="Integer").to_python_type_object()
            <class 'int'>
        """
        type_objects: dict[str, type[Any]] = {
            "String": str,
            "Text": str,
            "Memo": str,
            "Integer": int,
            "Boolean": bool,
            "Float": float,
            "Money": float,
            "Date": str,
            "Datetime": str,
            "Timestamp": int,
            "Blob": bytes,
        }
        return type_objects.get(self.data_type or "String", object)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> FieldInfo:
        """Create FieldInfo from CiviCRM API getFields response.

        Parses the field metadata returned by the CiviCRM API and
        creates a structured FieldInfo object.

        Args:
            data: Dictionary from CiviCRM getFields response.

        Returns:
            FieldInfo instance with populated attributes.

        Example:
            >>> data = {"name": "first_name", "title": "First Name", "data_type": "String"}
            >>> field = FieldInfo.from_api_response(data)
            >>> field.name
            'first_name'
        """
        return cls(
            name=data.get("name", ""),
            title=data.get("title"),
            description=data.get("description"),
            data_type=data.get("data_type"),
            input_type=data.get("input_type"),
            required=data.get("required", False),
            readonly=data.get("readonly", False),
            serialize=data.get("serialize"),
            fk_entity=data.get("fk_entity"),
            options=data.get("options"),
            default_value=data.get("default_value"),
        )


class EntityInfo(msgspec.Struct, kw_only=True):
    """Information about a CiviCRM entity from API introspection.

    Contains metadata about an entity type including its name,
    description, and structural information.

    Attributes:
        name: API entity name (e.g., 'Contact', 'Activity').
        title: Human-readable title.
        description: Detailed description of the entity.
        type: Entity type ('primary', 'secondary', 'bridge', etc.).
        primary_key: List of primary key field names.
        searchable: Whether the entity supports search operations.
        label_field: Field used for display labels.

    Example:
        >>> entity = EntityInfo(
        ...     name="Contact",
        ...     title="Contact",
        ...     type="primary",
        ...     searchable=True,
        ... )
    """

    name: str
    title: str | None = None
    description: str | None = None
    type: str | None = None
    primary_key: list[str] | None = None
    searchable: bool = True
    label_field: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> EntityInfo:
        """Create EntityInfo from CiviCRM API Entity.get response.

        Parses the entity metadata returned by the CiviCRM API.

        Args:
            data: Dictionary from CiviCRM Entity.get response.

        Returns:
            EntityInfo instance with populated attributes.

        Example:
            >>> data = {"name": "Contact", "title": "Contact", "type": "primary"}
            >>> entity = EntityInfo.from_api_response(data)
            >>> entity.name
            'Contact'
        """
        # Handle primary_key which might be a string or list
        pk = data.get("primary_key")
        if isinstance(pk, str):
            pk = [pk]

        return cls(
            name=data.get("name", ""),
            title=data.get("title") or data.get("label"),
            description=data.get("description"),
            type=data.get("type"),
            primary_key=pk,
            searchable=data.get("searchable", True),
            label_field=data.get("label_field"),
        )


class CacheEntry(msgspec.Struct):
    """Cache entry with timestamp for TTL-based expiration.

    Attributes:
        data: The cached data.
        timestamp: Unix timestamp when the entry was created.
    """

    data: Any
    timestamp: float


class EntityDiscovery:
    """Discovers and generates entity classes from CiviCRM API.

    Provides methods to introspect a CiviCRM instance and discover
    available entities and their field definitions. Can dynamically
    generate Python entity classes from this metadata.

    The discovery system maintains caches for entity and field metadata
    to minimize API calls. Caches can be refreshed on demand or will
    automatically expire based on the configured TTL.

    Args:
        client: Active CiviClient instance for API calls.
        cache_ttl: Time-to-live for cached metadata in seconds.
            Default is 3600 (1 hour). Set to 0 to disable caching.

    Example:
        >>> async with CiviClient() as client:
        ...     discovery = EntityDiscovery(client)
        ...
        ...     # Get available entities
        ...     entities = await discovery.get_entities()
        ...
        ...     # Get entity class (generates if needed)
        ...     CustomEntity = await discovery.get_entity_class("Custom_MyEntity")
        ...
        ...     # Get field metadata
        ...     fields = await discovery.get_fields("Contact")

    Attributes:
        client: The CiviClient used for API calls.
        cache_ttl: Cache time-to-live in seconds.
    """

    def __init__(
        self,
        client: CiviClient,
        *,
        cache_ttl: float = 3600.0,
    ) -> None:
        """Initialize EntityDiscovery.

        Args:
            client: Active CiviClient instance for API calls.
            cache_ttl: Time-to-live for cached metadata in seconds.
                Default is 3600 (1 hour). Set to 0 to disable caching.
        """
        self.client = client
        self.cache_ttl = cache_ttl

        # Caches for metadata
        self._entity_cache: dict[str, type[BaseEntity]] = {}
        self._field_cache: dict[str, CacheEntry] = {}
        self._entity_list_cache: CacheEntry | None = None

    def _is_cache_valid(self, entry: CacheEntry | None) -> bool:
        """Check if a cache entry is still valid.

        Args:
            entry: Cache entry to check.

        Returns:
            True if entry exists and has not expired.
        """
        if entry is None:
            return False
        if self.cache_ttl <= 0:
            return False
        return (time.time() - entry.timestamp) < self.cache_ttl

    async def get_entities(
        self,
        *,
        refresh: bool = False,
    ) -> list[EntityInfo]:
        """Get list of all available entities from CiviCRM API.

        Calls the Entity.get action to retrieve metadata about all
        available entities in the CiviCRM instance.

        Args:
            refresh: Force refresh from API, ignoring cache.

        Returns:
            List of EntityInfo objects describing available entities.

        Raises:
            CiviAPIError: If the API request fails.

        Example:
            >>> entities = await discovery.get_entities()
            >>> for entity in entities:
            ...     print(f"{entity.name}: {entity.description}")
        """
        # Check cache
        if not refresh and self._is_cache_valid(self._entity_list_cache):
            return self._entity_list_cache.data  # type: ignore[union-attr]

        logger.debug("Fetching entity list from API")

        # Call Entity.get to get all available entities
        response = await self.client.request("Entity", "get", {})

        entities = [EntityInfo.from_api_response(data) for data in (response.values or [])]

        # Update cache
        self._entity_list_cache = CacheEntry(
            data=entities,
            timestamp=time.time(),
        )

        logger.debug("Discovered %d entities", len(entities))
        return entities

    async def get_fields(
        self,
        entity_name: str,
        *,
        refresh: bool = False,
    ) -> list[FieldInfo]:
        """Get field definitions for an entity.

        Calls the {entity}.getFields action to retrieve metadata
        about all fields available on the specified entity.

        Args:
            entity_name: CiviCRM entity name (e.g., 'Contact').
            refresh: Force refresh from API, ignoring cache.

        Returns:
            List of FieldInfo objects describing entity fields.

        Raises:
            CiviAPIError: If the API request fails.

        Example:
            >>> fields = await discovery.get_fields("Contact")
            >>> for field in fields:
            ...     print(f"{field.name}: {field.data_type}")
        """
        # Check cache
        cache_entry = self._field_cache.get(entity_name)
        if not refresh and self._is_cache_valid(cache_entry):
            return cache_entry.data  # type: ignore[union-attr]

        logger.debug("Fetching fields for %s from API", entity_name)

        # Call getFields action
        response = await self.client.get_fields(entity_name)

        fields = [FieldInfo.from_api_response(data) for data in (response.values or [])]

        # Update cache
        self._field_cache[entity_name] = CacheEntry(
            data=fields,
            timestamp=time.time(),
        )

        logger.debug("Discovered %d fields for %s", len(fields), entity_name)
        return fields

    async def get_entity_class(
        self,
        entity_name: str,
        *,
        refresh: bool = False,
    ) -> type[BaseEntity]:
        """Get or generate an entity class.

        First checks the static entity registry for pre-defined entity
        classes (like Contact, Activity, etc.). If not found, dynamically
        generates a class from API metadata.

        Generated classes are cached to avoid repeated generation.

        Args:
            entity_name: CiviCRM entity name.
            refresh: Force regeneration from API, ignoring cache.

        Returns:
            Entity class (static or dynamically generated).

        Raises:
            CiviAPIError: If the API request fails.

        Example:
            >>> # Get a built-in entity
            >>> Contact = await discovery.get_entity_class("Contact")
            >>>
            >>> # Get a custom entity (generates dynamically)
            >>> CustomEntity = await discovery.get_entity_class("Custom_MyEntity")
        """
        # Check static registry first (unless refresh requested)
        if not refresh:
            static_class = EntityMeta.get_entity_class(entity_name)
            if static_class is not None:
                logger.debug("Using static entity class for %s", entity_name)
                return static_class

            # Check dynamic cache
            if entity_name in self._entity_cache:
                logger.debug("Using cached dynamic entity class for %s", entity_name)
                return self._entity_cache[entity_name]

        # Generate from API metadata
        fields = await self.get_fields(entity_name, refresh=refresh)
        entity_class = self.generate_entity_class(entity_name, fields)

        # Cache the generated class
        self._entity_cache[entity_name] = entity_class

        logger.debug("Generated dynamic entity class for %s", entity_name)
        return entity_class

    def generate_entity_class(
        self,
        name: str,
        fields: list[FieldInfo],
    ) -> type[BaseEntity]:
        """Generate a new entity class from field metadata.

        Creates a new class that inherits from BaseEntity with
        fields defined according to the provided metadata.

        The generated class:
        - Has proper type hints for all fields
        - Supports dirty tracking via BaseEntity
        - Can be used with EntityManager for queries
        - Is compatible with msgspec serialization

        Args:
            name: Entity name (used as class name and __entity_name__).
            fields: List of FieldInfo objects defining entity fields.

        Returns:
            Dynamically generated entity class.

        Example:
            >>> fields = [
            ...     FieldInfo(name="id", data_type="Integer"),
            ...     FieldInfo(name="name", data_type="String"),
            ... ]
            >>> MyEntity = discovery.generate_entity_class("MyEntity", fields)
            >>> instance = MyEntity(id=1, name="Test")
        """
        # Build field definitions
        struct_fields = _build_struct_fields(fields)

        # Create dynamic entity class
        entity_class = _create_dynamic_entity_class(name, struct_fields)

        # Register in the entity registry (but don't overwrite static classes)
        if EntityMeta.get_entity_class(name) is None:
            EntityMeta.register_dynamic_entity(name, entity_class)

        return entity_class

    async def refresh_all(self) -> None:
        """Refresh all entity metadata from API.

        Clears all caches and re-fetches entity and field information.
        Use this after schema changes in CiviCRM.

        Example:
            >>> # After adding custom fields in CiviCRM
            >>> await discovery.refresh_all()
        """
        logger.info("Refreshing all entity metadata")

        # Clear caches
        self.clear_cache()

        # Refresh entity list
        entities = await self.get_entities(refresh=True)

        # Pre-fetch fields for all entities
        for entity in entities:
            try:
                await self.get_fields(entity.name, refresh=True)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to fetch fields for %s",
                    entity.name,
                    exc_info=True,
                )

        logger.info("Refreshed metadata for %d entities", len(entities))

    def clear_cache(self) -> None:
        """Clear all cached metadata.

        Removes all cached entity classes, field definitions, and
        entity lists. Next access will fetch fresh data from API.

        Example:
            >>> discovery.clear_cache()
            >>> # Next call will fetch from API
            >>> fields = await discovery.get_fields("Contact")
        """
        self._entity_cache.clear()
        self._field_cache.clear()
        self._entity_list_cache = None
        logger.debug("Cleared entity discovery cache")

    async def get_custom_fields(
        self,
        entity_name: str,
    ) -> list[FieldInfo]:
        """Get only custom fields for an entity.

        Filters the field list to return only custom fields
        (those typically prefixed with 'custom_').

        Args:
            entity_name: CiviCRM entity name.

        Returns:
            List of FieldInfo for custom fields only.

        Example:
            >>> custom_fields = await discovery.get_custom_fields("Contact")
        """
        all_fields = await self.get_fields(entity_name)
        return [f for f in all_fields if f.name.startswith("custom_")]

    async def get_entity_info(
        self,
        entity_name: str,
    ) -> EntityInfo | None:
        """Get metadata for a specific entity.

        Args:
            entity_name: CiviCRM entity name.

        Returns:
            EntityInfo if found, None otherwise.

        Example:
            >>> info = await discovery.get_entity_info("Contact")
            >>> if info:
            ...     print(info.description)
        """
        entities = await self.get_entities()
        for entity in entities:
            if entity.name == entity_name:
                return entity
        return None

    async def entity_exists(self, entity_name: str) -> bool:
        """Check if an entity exists in CiviCRM.

        Args:
            entity_name: CiviCRM entity name to check.

        Returns:
            True if entity exists, False otherwise.

        Example:
            >>> if await discovery.entity_exists("Custom_MyEntity"):
            ...     print("Entity exists!")
        """
        info = await self.get_entity_info(entity_name)
        return info is not None


async def discover_entities(
    client: CiviClient,
    *,
    include_custom: bool = True,
) -> dict[str, type[BaseEntity]]:
    """Discover and return all entity classes.

    Convenience function that creates an EntityDiscovery instance
    and generates classes for all available entities.

    Args:
        client: Active CiviClient instance.
        include_custom: Whether to include custom entities.
            Default True. Set False to only get core entities.

    Returns:
        Dict mapping entity names to their classes.

    Example:
        >>> async with CiviClient() as client:
        ...     entities = await discover_entities(client)
        ...     Contact = entities["Contact"]
        ...     CustomEntity = entities.get("Custom_MyEntity")
    """
    discovery = EntityDiscovery(client)
    entities = await discovery.get_entities()

    result: dict[str, type[BaseEntity]] = {}

    for entity_info in entities:
        # Skip custom entities if not requested
        if not include_custom and entity_info.name.startswith("Custom_"):
            continue

        try:
            entity_class = await discovery.get_entity_class(entity_info.name)
            result[entity_info.name] = entity_class
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to generate class for %s",
                entity_info.name,
                exc_info=True,
            )

    return result
