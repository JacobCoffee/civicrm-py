"""Base entity classes for CiviCRM entities.

Provides the foundation for all CiviCRM entity models with:
- High-performance msgspec.Struct serialization
- Dirty field tracking for efficient updates
- Django-ORM-like query interface via EntityManager
- Automatic entity name binding

Example:
    >>> class Contact(BaseEntity):
    ...     __entity_name__ = "Contact"
    ...     display_name: str = ""
    ...     first_name: str | None = None
    ...     last_name: str | None = None
    >>> # Create from API response
    >>> contact = Contact.from_dict({"id": 1, "display_name": "John Doe"})
    >>> contact.first_name = "John"
    >>> contact.to_dict(only_dirty=True)
    {'first_name': 'John'}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeVar

import msgspec

# Type variable for entity subclasses (used in factory functions)
EntityT = TypeVar("EntityT", bound="BaseEntity")

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient
    from civicrm_py.core.exceptions import CiviError, CiviNotFoundError  # noqa: F401


class EntityState(msgspec.Struct, frozen=True):
    """Immutable state container for entity tracking.

    Tracks the original field values and which fields have been modified.
    Uses frozen struct for hashability and immutability.

    Attributes:
        original_values: Dictionary of field values at load/save time.
        dirty_fields: Frozenset of field names that have been modified.
    """

    original_values: dict[str, Any]
    dirty_fields: frozenset[str]

    @classmethod
    def new(cls, values: dict[str, Any] | None = None) -> EntityState:
        """Create new clean state with optional initial values.

        Args:
            values: Initial field values to track.

        Returns:
            New EntityState with no dirty fields.
        """
        return cls(
            original_values=values or {},
            dirty_fields=frozenset(),
        )

    def mark_dirty(self, field: str) -> EntityState:
        """Return new state with field marked as dirty.

        Args:
            field: Name of the modified field.

        Returns:
            New EntityState with field added to dirty set.
        """
        return EntityState(
            original_values=self.original_values,
            dirty_fields=self.dirty_fields | {field},
        )

    def mark_clean(self, current_values: dict[str, Any]) -> EntityState:
        """Return new state with all fields marked clean.

        Args:
            current_values: Current field values to set as original.

        Returns:
            New EntityState with empty dirty set.
        """
        return EntityState(
            original_values=current_values,
            dirty_fields=frozenset(),
        )


class FieldDescriptor:
    """Descriptor for typed field access with dirty tracking.

    Intercepts attribute access to track which fields have been modified,
    enabling efficient PATCH-style updates that only send changed fields.

    This descriptor is primarily for advanced use cases where fine-grained
    control over field access is needed. Standard entity fields use the
    built-in __setattr__ tracking.

    Attributes:
        name: The field name.
        type_hint: The field's type annotation.
        default: Default value for the field.

    Example:
        >>> class MyEntity(BaseEntity):
        ...     my_field = FieldDescriptor("my_field", str, "")
    """

    def __init__(
        self,
        name: str,
        type_hint: type[object] | None = None,
        default: object = msgspec.UNSET,
    ) -> None:
        """Initialize field descriptor.

        Args:
            name: Field name.
            type_hint: Type annotation for the field.
            default: Default value (UNSET means required).
        """
        self.name = name
        self.type_hint = type_hint
        self.default = default

    def __get__(self, obj: BaseEntity | None, objtype: type[BaseEntity] | None = None) -> object:
        """Get field value from entity.

        Args:
            obj: Entity instance (None for class access).
            objtype: Entity class.

        Returns:
            Field value or self if accessed on class.
        """
        if obj is None:
            return self
        return getattr(obj, f"_field_{self.name}", self.default)

    def __set__(self, obj: BaseEntity, value: object) -> None:
        """Set field value and mark as dirty.

        Args:
            obj: Entity instance.
            value: New field value.
        """
        # Store the actual value
        msgspec.Struct.__setattr__(obj, f"_field_{self.name}", value)

        # Mark field as dirty if we have state tracking
        state = getattr(obj, "_state", None)
        if state is not None and (self.name not in state.original_values or state.original_values[self.name] != value):
            msgspec.Struct.__setattr__(obj, "_state", state.mark_dirty(self.name))

    def __repr__(self) -> str:
        """String representation."""
        return f"FieldDescriptor({self.name!r}, type={self.type_hint}, default={self.default!r})"


class EntityMeta(type):
    """Metaclass that binds EntityManager to entity classes.

    Handles:
    - Extracting __entity_name__ or defaulting to class name
    - Setting up the `objects` manager placeholder
    - Registering entity classes for client binding

    All entity classes are registered in a global registry that allows
    the client to look up entity classes by name and bind managers.

    Example:
        >>> class Contact(BaseEntity, metaclass=EntityMeta):
        ...     __entity_name__ = "Contact"
        >>> EntityMeta.get_entity_class("Contact")
        <class 'Contact'>
    """

    # Registry of all entity classes for client binding
    _registry: ClassVar[dict[str, type[BaseEntity]]] = {}

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: object,
    ) -> EntityMeta:
        """Create new entity class with manager binding.

        Args:
            name: Class name.
            bases: Base classes.
            namespace: Class namespace/attributes.
            **kwargs: Additional class creation kwargs.

        Returns:
            New entity class.
        """
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Skip processing for BaseEntity itself
        if name != "BaseEntity" and any(isinstance(b, EntityMeta) for b in bases):
            # Set entity name (explicit or default to class name)
            entity_name = namespace.get("__entity_name__", name)
            cls._entity_name = entity_name  # type: ignore[attr-defined]

            # Register for client binding
            mcs._registry[entity_name] = cls  # type: ignore[assignment]

            # Manager placeholder (set when client binds)
            if "objects" not in namespace:
                cls.objects = None  # type: ignore[attr-defined]

        return cls

    @classmethod
    def get_entity_class(cls, name: str) -> type[BaseEntity] | None:
        """Get entity class by name from registry.

        Args:
            name: CiviCRM entity name.

        Returns:
            Entity class or None if not registered.
        """
        return cls._registry.get(name)

    @classmethod
    def get_all_entities(cls) -> dict[str, type[BaseEntity]]:
        """Get all registered entity classes.

        Returns:
            Dictionary mapping entity names to classes.
        """
        return dict(cls._registry)

    @classmethod
    def clear_registry(cls) -> None:
        """Clear the entity registry (mainly for testing)."""
        cls._registry.clear()

    @classmethod
    def register_dynamic_entity(cls, name: str, entity_class: type[BaseEntity]) -> None:
        """Register a dynamically generated entity class.

        Used by EntityDiscovery to register classes generated from API metadata.

        Args:
            name: CiviCRM entity name.
            entity_class: The entity class to register.
        """
        cls._registry[name] = entity_class


class BaseEntity(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Base class for all CiviCRM entities.

    Provides:
    - High-performance msgspec serialization
    - Dirty field tracking for efficient updates
    - Django-ORM-like query interface via `objects` manager
    - Factory methods for creating from API responses

    Subclasses should define:
    - __entity_name__: CiviCRM entity name (defaults to class name)
    - Field definitions as class attributes with type hints

    The dirty field tracking enables PATCH-style updates where only
    modified fields are sent to the API, reducing bandwidth and
    avoiding overwriting concurrent changes.

    Example:
        >>> class Contact(BaseEntity):
        ...     __entity_name__ = "Contact"
        ...     display_name: str | None = None
        ...     first_name: str | None = None
        >>> contact = Contact(id=1, display_name="John Doe")
        >>> contact.first_name = "John"
        >>> contact.is_dirty
        True
        >>> contact.dirty_fields
        {'first_name'}
        >>> contact.to_dict(only_dirty=True)
        {'id': 1, 'first_name': 'John'}

    Attributes:
        id: Primary key (None for unsaved entities).
        objects: Class-level EntityManager (set by client binding).
    """

    # Class-level entity name (set by subclasses)
    __entity_name__: ClassVar[str] = ""

    # Internal state tracking (excluded from serialization by name prefix)
    _state: EntityState | None = msgspec.field(default=None, name="_state")
    _client: Any | None = msgspec.field(default=None, name="_client")

    # Class-level attributes (set by metaclass/binding)
    _entity_name: ClassVar[str] = ""
    objects: ClassVar[Any] = None  # EntityManager[Self] - set by client binding

    # Cached field names per class
    _cached_field_names: ClassVar[frozenset[str] | None] = None

    def __post_init__(self) -> None:
        """Initialize entity state after construction.

        Captures initial field values for dirty tracking.
        """
        # Capture initial values for dirty tracking
        initial_values = self._get_field_values()
        msgspec.Struct.__setattr__(self, "_state", EntityState.new(initial_values))

    def __setattr__(self, name: str, value: object) -> None:
        """Override setattr to track dirty fields.

        Args:
            name: Attribute name.
            value: New value.
        """
        # Let msgspec handle internal attributes
        if name.startswith("_"):
            msgspec.Struct.__setattr__(self, name, value)
            return

        # Track dirty state for entity fields
        if self._state is not None and name in self._get_field_names():
            current = getattr(self, name, msgspec.UNSET)
            if current != value:
                msgspec.Struct.__setattr__(self, "_state", self._state.mark_dirty(name))

        msgspec.Struct.__setattr__(self, name, value)

    @classmethod
    def _get_field_names(cls) -> frozenset[str]:
        """Get all field names for this entity class.

        Returns:
            Frozenset of field names excluding internal fields.
        """
        # Check cache first
        if cls._cached_field_names is not None:
            return cls._cached_field_names

        # Build field names from msgspec struct info
        info = msgspec.structs.fields(cls)
        names = frozenset(f.name for f in info if not f.name.startswith("_"))

        # Cache on class (bypass __setattr__)
        type.__setattr__(cls, "_cached_field_names", names)
        return names

    def _get_field_values(self) -> dict[str, Any]:
        """Get current values for all non-internal fields.

        Returns:
            Dictionary of field name to current value.
        """
        return {name: getattr(self, name) for name in self._get_field_names()}

    @property
    def is_dirty(self) -> bool:
        """Check if entity has unsaved changes.

        Returns:
            True if any field has been modified since last save/load.
        """
        return bool(self._state and self._state.dirty_fields)

    @property
    def dirty_fields(self) -> set[str]:
        """Get set of modified field names.

        Returns:
            Set of field names that have been changed.
        """
        if self._state is None:
            return set()
        return set(self._state.dirty_fields)

    @property
    def is_new(self) -> bool:
        """Check if entity has not been saved to CiviCRM.

        Returns:
            True if entity has no ID (not yet persisted).
        """
        entity_id = getattr(self, "id", None)
        return entity_id is None

    def mark_clean(self) -> None:
        """Mark all fields as clean (not dirty).

        Called after successful save operations to reset tracking.
        """
        current_values = self._get_field_values()
        msgspec.Struct.__setattr__(self, "_state", EntityState.new(current_values))

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        client: CiviClient | None = None,
    ) -> Self:
        """Create entity instance from API response dictionary.

        Handles type coercion and sets up state tracking. Only fields
        defined on the entity class are populated; unknown fields are
        ignored.

        Args:
            data: Dictionary from CiviCRM API response.
            client: Optional client reference for save/delete operations.

        Returns:
            New entity instance with fields populated from data.

        Example:
            >>> contact = Contact.from_dict({"id": 1, "display_name": "John Doe", "first_name": "John"})
        """
        # Filter to only known fields
        field_names = cls._get_field_names()
        filtered = {k: v for k, v in data.items() if k in field_names}

        # Create instance via msgspec for validation
        instance = msgspec.convert(filtered, cls, strict=False)

        # Set client reference
        msgspec.Struct.__setattr__(instance, "_client", client)

        # Reset dirty tracking since this is fresh from API
        instance.mark_clean()

        return instance

    def to_dict(self, *, only_dirty: bool = False, exclude_none: bool = True) -> dict[str, Any]:
        """Convert entity to dictionary for API requests.

        Args:
            only_dirty: If True, only include modified fields.
            exclude_none: If True, exclude fields with None values.

        Returns:
            Dictionary suitable for API create/update requests.

        Example:
            >>> contact = Contact(display_name="John Doe")
            >>> contact.first_name = "John"
            >>> contact.to_dict(only_dirty=True)
            {'first_name': 'John'}
        """
        result: dict[str, Any] = {}

        if only_dirty:
            # Only include dirty fields
            for name in self.dirty_fields:
                value = getattr(self, name)
                if not exclude_none or value is not None:
                    result[name] = value
            # Always include ID for updates (if present)
            entity_id = getattr(self, "id", None)
            if entity_id is not None:
                result["id"] = entity_id
        else:
            # Include all fields
            for name in self._get_field_names():
                value = getattr(self, name)
                if not exclude_none or value is not None:
                    result[name] = value

        return result

    async def save(self, *, client: CiviClient | None = None) -> Self:
        """Save entity to CiviCRM (create or update).

        Creates new entity if ID is None, otherwise updates existing.
        Only sends dirty fields for updates (PATCH-style).

        Args:
            client: Optional client to use. Falls back to bound client.

        Returns:
            Self with updated fields from API response.

        Raises:
            CiviError: If no client is available.
            CiviAPIError: If the API request fails.

        Example:
            >>> contact = Contact(display_name="John Doe")
            >>> await contact.save(client=civi_client)
            >>> contact.id  # Now has ID from CiviCRM
            42
        """
        from civicrm_py.core.exceptions import CiviError

        active_client = client or self._client
        if active_client is None:
            msg = "No client available. Pass client parameter or bind entity to client."
            raise CiviError(msg)

        entity_name = self.__class__.__entity_name__
        if not entity_name:
            msg = f"Entity class {self.__class__.__name__} has no __entity_name__ defined"
            raise CiviError(msg)

        if self.is_new:
            # Create new entity
            values = self.to_dict(exclude_none=True)
            values.pop("id", None)  # Remove None id
            response = await active_client.create(entity_name, values)
        else:
            # Update existing - only send dirty fields
            values = self.to_dict(only_dirty=True)
            entity_id = getattr(self, "id", None)
            if not values or (len(values) == 1 and "id" in values):
                # Nothing to update
                return self
            response = await active_client.update(
                entity_name,
                values,
                [["id", "=", entity_id]],
            )

        # Update self with response data
        if response.values:
            updated_data = response.values[0]
            for key, value in updated_data.items():
                if key in self._get_field_names():
                    msgspec.Struct.__setattr__(self, key, value)

        # Reset dirty tracking
        self.mark_clean()

        return self

    async def delete(self, *, client: CiviClient | None = None) -> None:
        """Delete this entity from CiviCRM.

        Args:
            client: Optional client to use. Falls back to bound client.

        Raises:
            CiviError: If no client available or entity not persisted.
            CiviAPIError: If the API request fails.

        Example:
            >>> contact = await Contact.objects.get(id=42)
            >>> await contact.delete()
        """
        from civicrm_py.core.exceptions import CiviError

        entity_id = getattr(self, "id", None)
        if entity_id is None:
            msg = "Cannot delete entity without ID"
            raise CiviError(msg)

        active_client = client or self._client
        if active_client is None:
            msg = "No client available. Pass client parameter or bind entity to client."
            raise CiviError(msg)

        entity_name = self.__class__.__entity_name__
        if not entity_name:
            msg = f"Entity class {self.__class__.__name__} has no __entity_name__ defined"
            raise CiviError(msg)

        await active_client.delete(entity_name, [["id", "=", entity_id]])

        # Clear ID to indicate deleted
        msgspec.Struct.__setattr__(self, "id", None)

    async def refresh(self, *, client: CiviClient | None = None) -> Self:
        """Reload entity from CiviCRM.

        Fetches fresh data from the API and updates all fields.
        Discards any unsaved changes.

        Args:
            client: Optional client to use. Falls back to bound client.

        Returns:
            Self with refreshed data from API.

        Raises:
            CiviError: If no client available or entity not persisted.
            CiviNotFoundError: If entity no longer exists.

        Example:
            >>> contact = await Contact.objects.get(id=42)
            >>> contact.first_name = "Changed"
            >>> await contact.refresh()  # Discards change
            >>> contact.first_name  # Original value from API
        """
        from civicrm_py.core.exceptions import CiviError, CiviNotFoundError

        entity_id = getattr(self, "id", None)
        if entity_id is None:
            msg = "Cannot refresh entity without ID"
            raise CiviError(msg)

        active_client = client or self._client
        if active_client is None:
            msg = "No client available. Pass client parameter or bind entity to client."
            raise CiviError(msg)

        entity_name = self.__class__.__entity_name__
        if not entity_name:
            msg = f"Entity class {self.__class__.__name__} has no __entity_name__ defined"
            raise CiviError(msg)

        response = await active_client.get(
            entity_name,
            where=[["id", "=", entity_id]],
            limit=1,
        )

        if not response.values:
            msg = f"{entity_name} with id={entity_id} not found"
            raise CiviNotFoundError(msg)

        # Update all fields from response
        data = response.values[0]
        for key, value in data.items():
            if key in self._get_field_names():
                msgspec.Struct.__setattr__(self, key, value)

        # Reset dirty tracking
        self.mark_clean()

        return self

    def __repr__(self) -> str:
        """String representation showing entity type and ID."""
        cls_name = self.__class__.__name__
        entity_id = getattr(self, "id", None)
        if entity_id is not None:
            return f"<{cls_name} id={entity_id}>"
        return f"<{cls_name} (unsaved)>"

    def __eq__(self, other: object) -> bool:
        """Equality based on entity type and ID.

        Two entities are equal if they have the same class and ID.
        Unsaved entities (no ID) are only equal to themselves.

        Args:
            other: Object to compare.

        Returns:
            True if entities are equal, NotImplemented if not comparable.
        """
        if not isinstance(other, BaseEntity):
            return NotImplemented
        if self.__class__ != other.__class__:
            return False
        # Both must have IDs to be equal by ID
        self_id = getattr(self, "id", None)
        other_id = getattr(other, "id", None)
        if self_id is None or other_id is None:
            return self is other
        return self_id == other_id

    def __hash__(self) -> int:
        """Hash based on entity type and ID.

        Unsaved entities hash by object identity.

        Returns:
            Hash value.
        """
        entity_id = getattr(self, "id", None)
        if entity_id is None:
            return hash(id(self))
        return hash((self.__class__.__name__, entity_id))


def entity_from_dict(
    entity_class: type[EntityT],
    data: dict[str, Any],
    *,
    client: CiviClient | None = None,
) -> EntityT:
    """Factory function to create entity from API response.

    Convenience function for creating entities with type inference.

    Args:
        entity_class: The entity class to instantiate.
        data: Dictionary from CiviCRM API response.
        client: Optional client reference.

    Returns:
        New entity instance.

    Example:
        >>> contact = entity_from_dict(Contact, {"id": 1, "display_name": "John"})
    """
    return entity_class.from_dict(data, client=client)


def get_entity_name(entity_class: type[BaseEntity]) -> str:
    """Get the CiviCRM entity name for an entity class.

    Args:
        entity_class: Entity class to get name for.

    Returns:
        CiviCRM entity name (e.g., "Contact", "Activity").

    Raises:
        ValueError: If class has no entity name defined.

    Example:
        >>> get_entity_name(Contact)
        'Contact'
    """
    name = getattr(entity_class, "__entity_name__", None) or getattr(entity_class, "_entity_name", None)
    if not name:
        msg = f"Entity class {entity_class.__name__} has no __entity_name__ defined"
        raise ValueError(msg)
    return name


__all__ = [
    "BaseEntity",
    "EntityMeta",
    "EntityState",
    "EntityT",
    "FieldDescriptor",
    "entity_from_dict",
    "get_entity_name",
]
