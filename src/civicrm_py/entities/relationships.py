"""Entity relationship handling for CiviCRM.

Provides descriptors and managers for navigating relationships between entities,
enabling Django-ORM-like patterns for accessing related records.

Features:
- ForeignKey: Lazy loading of single related entities (e.g., activity.source_contact)
- RelatedField: Reverse relationships returning RelatedManager (e.g., contact.activities)
- RelatedManager: QuerySet wrapper for filtering related entities
- Eager loading support via QuerySet.select_related() and prefetch_related()

Example:
    >>> # Define relationships in entity classes
    >>> class Activity(BaseEntity):
    ...     source_contact_id: int | None = None
    ...     source_contact = ForeignKey["Contact"]("Contact", "source_contact_id")

    >>> class Contact(BaseEntity):
    ...     activities = RelatedField("Activity", "source_contact_id")

    >>> # Use relationships
    >>> contact = await Contact.objects.get(id=1)
    >>> activities = await contact.activities.all()
    >>> first_activity = await contact.activities.filter(status_id=2).first()
    >>>
    >>> activity = await Activity.objects.get(id=1)
    >>> source_contact = await activity.source_contact  # Lazy loads Contact
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient
    from civicrm_py.entities.base import BaseEntity
    from civicrm_py.query.queryset import QuerySet

# Type variable for entity types
T = TypeVar("T", bound="BaseEntity")

# Module-level cache for foreign key relationships
# Uses object id as key. Cache entries should be cleared when entities go out of scope.
# For long-running applications, consider implementing cache size limits.
_fk_cache: dict[int, dict[str, Any]] = {}


class RelatedManager(Generic[T]):
    """Manager for accessing related entities through reverse relationships.

    Provides a QuerySet-like interface for filtering and retrieving related
    entities. The manager automatically filters results to only include
    records related to the parent entity.

    RelatedManager is lazily evaluated - no queries are executed until
    a terminal method (all, first, count, etc.) is called.

    Attributes:
        parent: The parent entity instance.
        related_entity: Name of the related entity class.
        foreign_key: Foreign key field on the related entity.

    Example:
        >>> # On Contact instance
        >>> contact.activities  # Returns RelatedManager[Activity]
        >>> await contact.activities.all()  # Returns list[Activity]
        >>> await contact.activities.filter(activity_type_id=1).all()
        >>> await contact.activities.count()
        >>>
        >>> # With additional filters
        >>> recent = (
        ...     await contact.activities.filter(activity_date_time__gte="2024-01-01")
        ...     .order_by("-activity_date_time")
        ...     .limit(10)
        ...     .all()
        ... )
    """

    __slots__ = ("_cached_queryset", "_foreign_key", "_parent", "_related_entity")

    def __init__(
        self,
        parent: BaseEntity,
        related_entity: str,
        foreign_key: str,
    ) -> None:
        """Initialize RelatedManager.

        Args:
            parent: The parent entity instance that owns this relationship.
            related_entity: CiviCRM entity name of the related entity.
            foreign_key: Field name on the related entity that references the parent.
        """
        self._parent = parent
        self._related_entity = related_entity
        self._foreign_key = foreign_key
        self._cached_queryset: QuerySet[T] | None = None

    def _get_client(self) -> CiviClient:
        """Get the client from the parent entity.

        Returns:
            CiviClient instance.

        Raises:
            RuntimeError: If parent has no client bound.
        """
        client = getattr(self._parent, "_client", None)
        if client is None:
            msg = (
                f"Cannot access related {self._related_entity} - "
                f"parent {self._parent.__class__.__name__} has no client bound. "
                "Ensure the entity was loaded through a client."
            )
            raise RuntimeError(msg)
        return client

    def _get_parent_id(self) -> int:
        """Get the parent entity's ID.

        Returns:
            Parent entity ID.

        Raises:
            RuntimeError: If parent has no ID (not persisted).
        """
        parent_id = getattr(self._parent, "id", None)
        if parent_id is None:
            msg = (
                f"Cannot access related {self._related_entity} - "
                f"parent {self._parent.__class__.__name__} has no ID (not persisted)"
            )
            raise RuntimeError(msg)
        return parent_id

    def _get_queryset(self) -> QuerySet[T]:
        """Get a QuerySet filtered to related entities.

        Creates a new QuerySet with a filter on the foreign key field
        matching the parent entity's ID.

        Returns:
            QuerySet filtered to related entities.
        """
        from civicrm_py.query.queryset import QuerySet

        client = self._get_client()
        parent_id = self._get_parent_id()

        # Create base QuerySet for the related entity
        qs: QuerySet[T] = QuerySet(client, self._related_entity)

        # Filter by foreign key
        return qs.filter(**{self._foreign_key: parent_id})

    def filter(self, **kwargs: Any) -> QuerySet[T]:  # noqa: ANN401
        """Return filtered QuerySet of related entities.

        Args:
            **kwargs: Filter conditions using Django-style lookups.

        Returns:
            QuerySet with filter applied.

        Example:
            >>> await contact.activities.filter(status_id=2).all()
            >>> await contact.activities.filter(activity_date_time__gte="2024-01-01").all()
        """
        return self._get_queryset().filter(**kwargs)

    def exclude(self, **kwargs: Any) -> QuerySet[T]:  # noqa: ANN401
        """Return QuerySet excluding matching related entities.

        Args:
            **kwargs: Filter conditions to exclude.

        Returns:
            QuerySet with exclusion applied.

        Example:
            >>> await contact.activities.exclude(is_deleted=True).all()
        """
        return self._get_queryset().exclude(**kwargs)

    def select(self, *fields: str) -> QuerySet[T]:
        """Specify fields to return for related entities.

        Args:
            *fields: Field names to select.

        Returns:
            QuerySet with field selection.

        Example:
            >>> await contact.activities.select("id", "subject", "activity_date_time").all()
        """
        return self._get_queryset().select(*fields)

    def order_by(self, *fields: str) -> QuerySet[T]:
        """Set sort order for related entities.

        Args:
            *fields: Field names. Prefix with '-' for descending.

        Returns:
            QuerySet with sort order.

        Example:
            >>> await contact.activities.order_by("-activity_date_time").all()
        """
        return self._get_queryset().order_by(*fields)

    def limit(self, n: int) -> QuerySet[T]:
        """Limit number of related entities returned.

        Args:
            n: Maximum records to return.

        Returns:
            QuerySet with limit.

        Example:
            >>> await contact.activities.limit(5).all()
        """
        return self._get_queryset().limit(n)

    def offset(self, n: int) -> QuerySet[T]:
        """Skip first n related entities.

        Args:
            n: Number of records to skip.

        Returns:
            QuerySet with offset.

        Example:
            >>> await contact.activities.offset(10).limit(10).all()
        """
        return self._get_queryset().offset(n)

    async def all(self) -> list[dict[str, Any]]:
        """Get all related entities.

        Returns:
            List of related entity dictionaries.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> activities = await contact.activities.all()
        """
        return await self._get_queryset().all()

    async def first(self) -> dict[str, Any] | None:
        """Get first related entity.

        Returns:
            First related entity dict or None if no results.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> latest_activity = await contact.activities.order_by("-created_date").first()
        """
        return await self._get_queryset().first()

    async def count(self) -> int:
        """Count related entities.

        Returns:
            Total count of related entities.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> activity_count = await contact.activities.count()
        """
        return await self._get_queryset().count()

    async def exists(self) -> bool:
        """Check if any related entities exist.

        Returns:
            True if at least one related entity exists.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> has_activities = await contact.activities.exists()
        """
        return await self._get_queryset().exists()

    async def get(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
        """Get a single related entity matching filters.

        Args:
            **kwargs: Filter conditions.

        Returns:
            Single related entity dict.

        Raises:
            CiviNotFoundError: If no matching entity found.
            CiviAPIError: If multiple entities found or other error.

        Example:
            >>> activity = await contact.activities.get(id=123)
        """
        return await self._get_queryset().get(**kwargs)

    def values(self, *fields: str) -> QuerySet[T]:
        """Return dictionaries with specified fields.

        Args:
            *fields: Fields to include in dictionaries.

        Returns:
            QuerySet that returns dicts.

        Example:
            >>> await contact.activities.values("id", "subject").all()
        """
        return self._get_queryset().values(*fields)

    def values_list(self, *fields: str, flat: bool = False) -> QuerySet[T]:
        """Return tuples or flat list of values.

        Args:
            *fields: Fields to include.
            flat: If True and single field, return flat list.

        Returns:
            QuerySet that returns tuples or list.

        Example:
            >>> await contact.activities.values_list("id", flat=True)
            [1, 2, 3, ...]
        """
        return self._get_queryset().values_list(*fields, flat=flat)

    def __repr__(self) -> str:
        """Return string representation."""
        parent_cls = self._parent.__class__.__name__
        parent_id = getattr(self._parent, "id", None)
        return (
            f"<RelatedManager "
            f"parent={parent_cls}(id={parent_id}) "
            f"related={self._related_entity} "
            f"fk={self._foreign_key}>"
        )


class ForeignKey(Generic[T]):
    """Descriptor for lazy-loading foreign key relationships.

    Provides access to a single related entity by fetching it lazily
    when accessed. The foreign key value is stored on the entity,
    and the related entity is fetched on first access.

    ForeignKey is a descriptor that returns an awaitable when accessed
    on an instance. Use `await entity.related_field` to get the related
    entity.

    Example:
        >>> class Activity(BaseEntity):
        ...     source_contact_id: int | None = None
        ...     source_contact = ForeignKey["Contact"]("Contact", "source_contact_id")

        >>> activity = await Activity.objects.get(id=1)
        >>> contact = await activity.source_contact  # Lazy loads Contact
        >>> print(contact.display_name)

    Notes:
        - Returns None if the foreign key field is None
        - Caches the loaded entity for subsequent access
        - Cache can be cleared by deleting the attribute
    """

    __slots__ = ("_attr_name", "_entity_name", "_fk_field")

    def __init__(self, entity_name: str, fk_field: str) -> None:
        """Initialize ForeignKey descriptor.

        Args:
            entity_name: CiviCRM entity name of the related entity.
            fk_field: Field name on this entity that stores the foreign key.
        """
        self._entity_name = entity_name
        self._fk_field = fk_field
        self._attr_name: str | None = None  # Set by __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when descriptor is assigned to a class attribute.

        Args:
            owner: The class this descriptor is being assigned to.
            name: The attribute name being assigned.
        """
        self._attr_name = name

    @overload
    def __get__(self, obj: None, objtype: type[BaseEntity]) -> ForeignKey[T]: ...

    @overload
    def __get__(self, obj: BaseEntity, objtype: type[BaseEntity] | None) -> ForeignKeyAccessor[T]: ...

    def __get__(
        self,
        obj: BaseEntity | None,
        objtype: type[BaseEntity] | None = None,
    ) -> ForeignKey[T] | ForeignKeyAccessor[T]:
        """Get the related entity accessor.

        When accessed on a class, returns the descriptor itself.
        When accessed on an instance, returns an awaitable accessor.

        Args:
            obj: Entity instance (None for class access).
            objtype: Entity class.

        Returns:
            ForeignKey descriptor (class access) or ForeignKeyAccessor (instance access).
        """
        if obj is None:
            return self

        return ForeignKeyAccessor(obj, self._entity_name, self._fk_field, self._attr_name)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ForeignKey({self._entity_name!r}, fk={self._fk_field!r})"


class ForeignKeyAccessor(Generic[T]):
    """Awaitable accessor for foreign key relationships.

    This class is returned when accessing a ForeignKey on an entity instance.
    It can be awaited to load the related entity.

    Example:
        >>> activity.source_contact  # Returns ForeignKeyAccessor
        >>> await activity.source_contact  # Returns Contact or None
    """

    __slots__ = ("_attr_name", "_cache_key", "_entity_name", "_fk_field", "_obj")

    def __init__(
        self,
        obj: BaseEntity,
        entity_name: str,
        fk_field: str,
        attr_name: str | None,
    ) -> None:
        """Initialize accessor.

        Args:
            obj: The entity instance.
            entity_name: CiviCRM entity name of the related entity.
            fk_field: Field name storing the foreign key.
            attr_name: Attribute name for cache key.
        """
        self._obj = obj
        self._entity_name = entity_name
        self._fk_field = fk_field
        self._attr_name = attr_name
        self._cache_key = f"_fk_cache_{attr_name}" if attr_name else f"_fk_cache_{fk_field}"

    def __await__(self) -> Any:  # noqa: ANN401
        """Make this accessor awaitable.

        Returns:
            Generator that yields the related entity or None.
        """
        return self._load().__await__()

    async def _load(self) -> dict[str, Any] | None:
        """Load the related entity.

        Returns:
            The related entity dict or None if foreign key is None.

        Raises:
            RuntimeError: If no client is bound to the entity.
            CiviNotFoundError: If related entity doesn't exist.

        Note:
            Currently returns a dictionary representation of the entity.
            Future versions may return proper entity instances when
            EntityManager fully supports typed returns.
        """
        # Check cache first using object id as key
        obj_id = id(self._obj)
        obj_cache = _fk_cache.get(obj_id)
        if obj_cache is not None and self._cache_key in obj_cache:
            return obj_cache[self._cache_key]

        # Get foreign key value
        fk_value = getattr(self._obj, self._fk_field, None)
        if fk_value is None:
            return None

        # Get client
        client = getattr(self._obj, "_client", None)
        if client is None:
            msg = f"Cannot load related {self._entity_name} - entity {self._obj.__class__.__name__} has no client bound"
            raise RuntimeError(msg)

        # Load related entity
        from civicrm_py.query.queryset import QuerySet

        qs: QuerySet[Any] = QuerySet(client, self._entity_name)
        result: dict[str, Any] | None = await qs.filter(id=fk_value).first()  # type: ignore[assignment]

        if result is not None:
            # Cache the result in module-level cache using object id
            if obj_id not in _fk_cache:
                _fk_cache[obj_id] = {}
            _fk_cache[obj_id][self._cache_key] = result

        return result

    def clear_cache(self) -> None:
        """Clear the cached related entity.

        Call this to force a fresh load on next access.
        """
        obj_id = id(self._obj)
        obj_cache = _fk_cache.get(obj_id)
        if obj_cache is not None and self._cache_key in obj_cache:
            del obj_cache[self._cache_key]

    def __repr__(self) -> str:
        """Return string representation."""
        fk_value = getattr(self._obj, self._fk_field, None)
        return f"<ForeignKeyAccessor {self._entity_name}(id={fk_value})>"


class RelatedField:
    """Descriptor for reverse relationships (one-to-many).

    Creates a RelatedManager when accessed on an entity instance,
    enabling navigation from a parent entity to its related children.

    Example:
        >>> class Contact(BaseEntity):
        ...     activities = RelatedField("Activity", "source_contact_id")
        ...     contributions = RelatedField("Contribution", "contact_id")
        ...     memberships = RelatedField("Membership", "contact_id")

        >>> contact = await Contact.objects.get(id=1)
        >>> activities = await contact.activities.all()
        >>> contributions = await contact.contributions.filter(total_amount__gt=100).all()
    """

    __slots__ = ("_entity_name", "_foreign_key")

    def __init__(self, entity_name: str, foreign_key: str) -> None:
        """Initialize RelatedField descriptor.

        Args:
            entity_name: CiviCRM entity name of the related entity.
            foreign_key: Field name on the related entity that references this entity.
        """
        self._entity_name = entity_name
        self._foreign_key = foreign_key

    @overload
    def __get__(self, obj: None, objtype: type) -> RelatedField: ...

    @overload
    def __get__(self, obj: BaseEntity, objtype: type | None) -> RelatedManager[Any]: ...

    def __get__(
        self,
        obj: BaseEntity | None,
        objtype: type | None = None,
    ) -> RelatedField | RelatedManager[Any]:
        """Get RelatedManager for this relationship.

        When accessed on a class, returns the descriptor itself.
        When accessed on an instance, returns a RelatedManager.

        Args:
            obj: Entity instance (None for class access).
            objtype: Entity class.

        Returns:
            RelatedField descriptor (class access) or RelatedManager (instance access).
        """
        if obj is None:
            return self

        return RelatedManager(obj, self._entity_name, self._foreign_key)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"RelatedField({self._entity_name!r}, fk={self._foreign_key!r})"


class ManyToManyField:
    """Descriptor for many-to-many relationships via junction tables.

    Handles relationships that go through an intermediate entity,
    such as GroupContact linking Groups and Contacts.

    Example:
        >>> class Contact(BaseEntity):
        ...     groups = ManyToManyField(
        ...         "Group",
        ...         through="GroupContact",
        ...         through_fk="contact_id",
        ...         target_fk="group_id",
        ...     )

        >>> contact = await Contact.objects.get(id=1)
        >>> groups = await contact.groups.all()

    Note:
        This is a placeholder for future implementation. The basic
        relationship patterns are handled by RelatedField and ForeignKey.
    """

    __slots__ = ("_entity_name", "_target_fk", "_through", "_through_fk")

    def __init__(
        self,
        entity_name: str,
        *,
        through: str,
        through_fk: str,
        target_fk: str,
    ) -> None:
        """Initialize ManyToManyField descriptor.

        Args:
            entity_name: CiviCRM entity name of the target entity.
            through: Junction entity name.
            through_fk: Field on junction entity referencing this entity.
            target_fk: Field on junction entity referencing target entity.
        """
        self._entity_name = entity_name
        self._through = through
        self._through_fk = through_fk
        self._target_fk = target_fk

    def __get__(
        self,
        obj: BaseEntity | None,
        objtype: type | None = None,
    ) -> ManyToManyField | ManyToManyManager:
        """Get manager for this relationship.

        Args:
            obj: Entity instance (None for class access).
            objtype: Entity class.

        Returns:
            ManyToManyField descriptor or ManyToManyManager.
        """
        if obj is None:
            return self

        return ManyToManyManager(
            obj,
            self._entity_name,
            self._through,
            self._through_fk,
            self._target_fk,
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ManyToManyField({self._entity_name!r}, through={self._through!r})"


class ManyToManyManager:
    """Manager for many-to-many relationships.

    Provides methods for querying entities related through a junction table.
    """

    __slots__ = ("_entity_name", "_parent", "_target_fk", "_through", "_through_fk")

    def __init__(
        self,
        parent: BaseEntity,
        entity_name: str,
        through: str,
        through_fk: str,
        target_fk: str,
    ) -> None:
        """Initialize ManyToManyManager.

        Args:
            parent: The parent entity instance.
            entity_name: Target entity name.
            through: Junction entity name.
            through_fk: Field on junction referencing parent.
            target_fk: Field on junction referencing target.
        """
        self._parent = parent
        self._entity_name = entity_name
        self._through = through
        self._through_fk = through_fk
        self._target_fk = target_fk

    def _get_client(self) -> CiviClient:
        """Get client from parent entity."""
        client = getattr(self._parent, "_client", None)
        if client is None:
            msg = "Parent entity has no client bound"
            raise RuntimeError(msg)
        return client

    def _get_parent_id(self) -> int:
        """Get parent entity ID."""
        parent_id = getattr(self._parent, "id", None)
        if parent_id is None:
            msg = "Parent entity has no ID"
            raise RuntimeError(msg)
        return parent_id

    async def all(self) -> list[dict[str, Any]]:
        """Get all related entities through the junction table.

        This performs two queries:
        1. Get junction records for this parent
        2. Get target entities matching those IDs

        Returns:
            List of related entity dictionaries.
        """
        from civicrm_py.query.queryset import QuerySet

        client = self._get_client()
        parent_id = self._get_parent_id()

        # Get junction records
        junction_qs: QuerySet[Any] = QuerySet(client, self._through)
        junction_records = (
            await junction_qs.filter(
                **{self._through_fk: parent_id},
            )
            .values(self._target_fk)
            .all()
        )

        if not junction_records:
            return []

        # Extract target IDs
        target_ids = [r.get(self._target_fk) for r in junction_records if r.get(self._target_fk)]

        if not target_ids:
            return []

        # Get target entities
        target_qs: QuerySet[Any] = QuerySet(client, self._entity_name)
        return await target_qs.filter(id__in=target_ids).all()

    async def count(self) -> int:
        """Count related entities."""
        from civicrm_py.query.queryset import QuerySet

        client = self._get_client()
        parent_id = self._get_parent_id()

        junction_qs: QuerySet[Any] = QuerySet(client, self._through)
        return await junction_qs.filter(**{self._through_fk: parent_id}).count()

    async def exists(self) -> bool:
        """Check if any related entities exist."""
        count = await self.count()
        return count > 0

    def __repr__(self) -> str:
        """Return string representation."""
        parent_cls = self._parent.__class__.__name__
        parent_id = getattr(self._parent, "id", None)
        return (
            f"<ManyToManyManager "
            f"parent={parent_cls}(id={parent_id}) "
            f"target={self._entity_name} "
            f"through={self._through}>"
        )


# Registry for relationship metadata
_relationship_registry: dict[str, dict[str, Any]] = {}


def register_relationship(
    entity_name: str,
    field_name: str,
    relationship_type: str,
    related_entity: str,
    foreign_key: str,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """Register a relationship for introspection.

    This allows runtime discovery of entity relationships.

    Args:
        entity_name: Entity class name.
        field_name: Relationship field name.
        relationship_type: Type ('foreign_key', 'related', 'many_to_many').
        related_entity: Related entity name.
        foreign_key: Foreign key field name.
        **kwargs: Additional relationship metadata.
    """
    if entity_name not in _relationship_registry:
        _relationship_registry[entity_name] = {}

    _relationship_registry[entity_name][field_name] = {
        "type": relationship_type,
        "related_entity": related_entity,
        "foreign_key": foreign_key,
        **kwargs,
    }


def get_relationships(entity_name: str) -> dict[str, Any]:
    """Get all registered relationships for an entity.

    Args:
        entity_name: Entity class name.

    Returns:
        Dictionary mapping field names to relationship metadata.
    """
    return _relationship_registry.get(entity_name, {})


def get_reverse_relationships(entity_name: str) -> list[dict[str, Any]]:
    """Get all relationships that point to this entity.

    Args:
        entity_name: Target entity name.

    Returns:
        List of relationship metadata dictionaries.
    """
    reverse = []
    for source_entity, relationships in _relationship_registry.items():
        for field_name, rel_info in relationships.items():
            if rel_info.get("related_entity") == entity_name:
                reverse.append(
                    {
                        "source_entity": source_entity,
                        "field_name": field_name,
                        **rel_info,
                    },
                )
    return reverse


__all__ = [
    "ForeignKey",
    "ForeignKeyAccessor",
    "ManyToManyField",
    "ManyToManyManager",
    "RelatedField",
    "RelatedManager",
    "get_relationships",
    "get_reverse_relationships",
    "register_relationship",
]
