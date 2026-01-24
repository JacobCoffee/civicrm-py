"""EntityManager - Django-style .objects pattern for CiviCRM entities.

Provides a manager class that serves as the entry point for entity queries,
similar to Django's Manager and the .objects attribute on model classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from civicrm_py.core.exceptions import DoesNotExist, MultipleObjectsReturned

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient, SyncCiviClient
    from civicrm_py.core.serialization import APIResponse, FieldMetadata
    from civicrm_py.query.queryset import QuerySet

T = TypeVar("T")


class EntityManager(Generic[T]):
    """Manager for CiviCRM entity operations.

    Provides Django-style query interface with .objects pattern.
    Creates QuerySet instances for chainable queries and provides
    direct CRUD shortcuts.

    Example:
        # Via entity class (when properly configured)
        contacts = await Contact.objects.filter(last_name="Smith").all()

        # Direct instantiation
        manager = EntityManager(client, "Contact")
        contacts = await manager.filter(last_name="Smith").all()

        # CRUD operations
        contact = await manager.create(first_name="John", last_name="Doe")
        contact = await manager.get(id=123)
        await manager.delete(where=[["id", "=", 123]])
    """

    def __init__(
        self,
        client: CiviClient,
        entity_name: str,
        *,
        model_class: type[T] | None = None,
    ) -> None:
        """Initialize EntityManager.

        Args:
            client: CiviClient instance for API communication.
            entity_name: Name of the CiviCRM entity (e.g., "Contact").
            model_class: Optional Pydantic model class for result conversion.
        """
        self._client = client
        self._entity_name = entity_name
        self._model_class = model_class

    @property
    def client(self) -> CiviClient:
        """Get the underlying CiviClient."""
        return self._client

    @property
    def entity_name(self) -> str:
        """Get the entity name this manager operates on."""
        return self._entity_name

    @property
    def model_class(self) -> type[T] | None:
        """Get the model class for result conversion."""
        return self._model_class

    def _create_queryset(self) -> QuerySet:
        """Create a new QuerySet instance.

        Returns:
            Fresh QuerySet bound to this manager.
        """
        from civicrm_py.query.queryset import QuerySet

        return QuerySet(
            client=self._client,
            entity=self._entity_name,
        )

    def _kwargs_to_where(self, **kwargs: Any) -> list[list[Any]]:
        """Convert keyword arguments to CiviCRM where clause format.

        Supports simple equality lookups and Django-style operators:
        - field=value -> ["field", "=", value]
        - field__gt=value -> ["field", ">", value]
        - field__gte=value -> ["field", ">=", value]
        - field__lt=value -> ["field", "<", value]
        - field__lte=value -> ["field", "<=", value]
        - field__ne=value -> ["field", "!=", value]
        - field__in=values -> ["field", "IN", values]
        - field__not_in=values -> ["field", "NOT IN", values]
        - field__like=value -> ["field", "LIKE", value]
        - field__not_like=value -> ["field", "NOT LIKE", value]
        - field__contains=value -> ["field", "CONTAINS", value]
        - field__is_null=True -> ["field", "IS NULL"]
        - field__is_not_null=True -> ["field", "IS NOT NULL"]

        Args:
            **kwargs: Field lookups as keyword arguments.

        Returns:
            List of where clause conditions.
        """
        operator_map = {
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "ne": "!=",
            "in": "IN",
            "not_in": "NOT IN",
            "like": "LIKE",
            "not_like": "NOT LIKE",
            "contains": "CONTAINS",
            "is_null": "IS NULL",
            "is_not_null": "IS NOT NULL",
        }

        where: list[list[Any]] = []
        for key, value in kwargs.items():
            if "__" in key:
                field, operator_key = key.rsplit("__", 1)
                operator = operator_map.get(operator_key, "=")
                if operator_key not in operator_map:
                    # Not a recognized operator, treat as field name with double underscore
                    field = key
                    operator = "="
            else:
                field = key
                operator = "="

            if operator in ("IS NULL", "IS NOT NULL"):
                where.append([field, operator])
            else:
                where.append([field, operator, value])

        return where

    # -------------------------------------------------------------------------
    # QuerySet Factory Methods
    # -------------------------------------------------------------------------

    def all(self) -> QuerySet:
        """Return a QuerySet that will fetch all records.

        This creates a new QuerySet without any filters applied.
        The actual query is not executed until the QuerySet is evaluated.

        Returns:
            QuerySet for all records.

        Example:
            all_contacts = await Contact.objects.all().execute()
        """
        return self._create_queryset()

    def filter(self, *args: list[Any], **kwargs: Any) -> QuerySet:
        """Return a filtered QuerySet.

        Accepts both positional arguments as raw CiviCRM where conditions
        and keyword arguments as Django-style field lookups.

        Args:
            *args: Raw where conditions as lists [field, operator, value].
            **kwargs: Field lookups as keyword arguments.

        Returns:
            Filtered QuerySet.

        Example:
            # Using kwargs (Django-style)
            contacts = Contact.objects.filter(last_name="Smith", is_deleted=False)

            # Using raw conditions
            contacts = Contact.objects.filter(["created_date", ">=", "2024-01-01"])

            # Combined
            contacts = Contact.objects.filter(
                ["is_deleted", "=", False],
                last_name__like="Smith%"
            )
        """
        qs = self._create_queryset()
        return qs.filter(*args, **kwargs)

    def exclude(self, *args: list[Any], **kwargs: Any) -> QuerySet:
        """Return a QuerySet excluding matching records.

        This is the inverse of filter() - it excludes records that match
        the specified conditions.

        Args:
            *args: Raw where conditions to exclude.
            **kwargs: Field lookups for records to exclude.

        Returns:
            QuerySet excluding matched records.

        Example:
            # Exclude deleted contacts
            contacts = Contact.objects.exclude(is_deleted=True)
        """
        qs = self._create_queryset()
        return qs.exclude(*args, **kwargs)

    def select(self, *fields: str) -> QuerySet:
        """Return a QuerySet that selects specific fields.

        Args:
            *fields: Field names to include in results.

        Returns:
            QuerySet with field selection.

        Example:
            contacts = Contact.objects.select("id", "display_name", "email_primary.email")
        """
        qs = self._create_queryset()
        return qs.select(*fields)

    def order_by(self, *fields: str) -> QuerySet:
        """Return an ordered QuerySet.

        Fields can be prefixed with '-' for descending order.

        Args:
            *fields: Field names to order by.

        Returns:
            Ordered QuerySet.

        Example:
            contacts = Contact.objects.order_by("-created_date", "display_name")
        """
        qs = self._create_queryset()
        return qs.order_by(*fields)

    def limit(self, count: int) -> QuerySet:
        """Return a QuerySet limited to a specific number of records.

        Args:
            count: Maximum number of records to return.

        Returns:
            Limited QuerySet.

        Example:
            top_10 = Contact.objects.order_by("-created_date").limit(10)
        """
        qs = self._create_queryset()
        return qs.limit(count)

    def offset(self, count: int) -> QuerySet:
        """Return a QuerySet with an offset.

        Args:
            count: Number of records to skip.

        Returns:
            QuerySet with offset.

        Example:
            page_2 = Contact.objects.limit(10).offset(10)
        """
        qs = self._create_queryset()
        return qs.offset(count)

    # -------------------------------------------------------------------------
    # Direct CRUD Operations (Async)
    # -------------------------------------------------------------------------

    async def get(self, **kwargs: Any) -> T | dict[str, Any]:
        """Get a single record matching the given criteria.

        This method retrieves exactly one record. If zero or multiple
        records match, an exception is raised.

        Args:
            **kwargs: Field lookups to identify the record.

        Returns:
            The matching entity (as model instance or dict).

        Raises:
            DoesNotExist: If no record matches.
            MultipleObjectsReturned: If multiple records match.

        Example:
            contact = await Contact.objects.get(id=123)
            contact = await Contact.objects.get(email_primary__email="john@example.com")
        """
        where = self._kwargs_to_where(**kwargs)
        response = await self._client.get(
            self._entity_name,
            where=where,
            limit=2,  # We only need to know if there's more than one
        )

        values = response.values or []
        count = len(values)

        if count == 0:
            raise DoesNotExist(self._entity_name, kwargs)

        if count > 1:
            raise MultipleObjectsReturned(self._entity_name, count, kwargs)

        result = values[0]
        if self._model_class is not None:
            return self._model_class.model_validate(result)
        return result

    async def create(self, **kwargs: Any) -> T | dict[str, Any]:
        """Create a new entity.

        Args:
            **kwargs: Field values for the new entity.

        Returns:
            The created entity (as model instance or dict).

        Raises:
            CiviAPIError: If creation fails.

        Example:
            contact = await Contact.objects.create(
                first_name="John",
                last_name="Doe",
                email_primary={"email": "john@example.com"}
            )
        """
        response = await self._client.create(self._entity_name, kwargs)

        if response.values and len(response.values) > 0:
            result = response.values[0]
            if self._model_class is not None:
                return self._model_class.model_validate(result)
            return result

        # Return empty dict if no values returned
        return {} if self._model_class is None else self._model_class.model_validate({})

    async def update(
        self,
        values: dict[str, Any],
        *,
        where: list[list[Any]] | None = None,
        **kwargs: Any,
    ) -> APIResponse[dict[str, Any]]:
        """Update entities matching the criteria.

        Args:
            values: Field values to update.
            where: Raw where conditions.
            **kwargs: Field lookups for filtering (converted to where).

        Returns:
            API response with updated entities.

        Raises:
            CiviAPIError: If update fails.
            ValueError: If no filter criteria provided.

        Example:
            # Update by ID
            await Contact.objects.update(
                {"job_title": "Senior Developer"},
                id=123
            )

            # Update multiple
            await Contact.objects.update(
                {"is_opt_out": True},
                where=[["email_primary.email", "LIKE", "%@spam.com"]]
            )
        """
        if where is None and not kwargs:
            msg = "update() requires filter criteria (where or kwargs)"
            raise ValueError(msg)

        combined_where = where or []
        if kwargs:
            combined_where.extend(self._kwargs_to_where(**kwargs))

        return await self._client.update(self._entity_name, values, combined_where)

    async def delete(
        self,
        *,
        where: list[list[Any]] | None = None,
        **kwargs: Any,
    ) -> APIResponse[dict[str, Any]]:
        """Delete entities matching the criteria.

        Args:
            where: Raw where conditions.
            **kwargs: Field lookups for filtering (converted to where).

        Returns:
            API response.

        Raises:
            CiviAPIError: If delete fails.
            ValueError: If no filter criteria provided.

        Example:
            # Delete by ID
            await Contact.objects.delete(id=123)

            # Delete with conditions
            await Contact.objects.delete(
                where=[["is_deleted", "=", True], ["modified_date", "<", "2020-01-01"]]
            )
        """
        if where is None and not kwargs:
            msg = "delete() requires filter criteria (where or kwargs)"
            raise ValueError(msg)

        combined_where = where or []
        if kwargs:
            combined_where.extend(self._kwargs_to_where(**kwargs))

        return await self._client.delete(self._entity_name, combined_where)

    async def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T | dict[str, Any], bool]:
        """Get an existing entity or create a new one.

        Looks up an entity matching the given kwargs. If found, returns it.
        If not found, creates a new entity with kwargs + defaults.

        Args:
            defaults: Additional fields for creation (not used in lookup).
            **kwargs: Field lookups for the existing entity.

        Returns:
            Tuple of (entity, created) where created is True if new.

        Raises:
            MultipleObjectsReturned: If multiple records match.
            CiviAPIError: If creation fails.

        Example:
            contact, created = await Contact.objects.get_or_create(
                email_primary__email="john@example.com",
                defaults={"first_name": "John", "last_name": "Doe"}
            )
            if created:
                print("New contact created!")
        """
        try:
            entity = await self.get(**kwargs)
            return entity, False
        except DoesNotExist:
            # Create with kwargs + defaults
            create_kwargs = {**kwargs, **(defaults or {})}
            # Remove lookup operators from field names for creation
            clean_kwargs = {}
            for key, value in create_kwargs.items():
                if "__" in key:
                    field = key.rsplit("__", 1)[0]
                    # Only use if it was a simple equality lookup
                    if key.count("__") == 1 and key.rsplit("__", 1)[1] in (
                        "gt",
                        "gte",
                        "lt",
                        "lte",
                        "ne",
                        "in",
                        "not_in",
                        "like",
                        "not_like",
                        "contains",
                        "is_null",
                        "is_not_null",
                    ):
                        continue  # Skip non-equality lookups
                    clean_kwargs[field] = value
                else:
                    clean_kwargs[key] = value

            entity = await self.create(**clean_kwargs)
            return entity, True

    async def update_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T | dict[str, Any], bool]:
        """Update an existing entity or create a new one.

        Looks up an entity matching the given kwargs. If found, updates it
        with defaults. If not found, creates a new entity with kwargs + defaults.

        Args:
            defaults: Fields to update (existing) or add (new entity).
            **kwargs: Field lookups for the existing entity.

        Returns:
            Tuple of (entity, created) where created is True if new.

        Raises:
            MultipleObjectsReturned: If multiple records match.
            CiviAPIError: If update/create fails.

        Example:
            contact, created = await Contact.objects.update_or_create(
                email_primary__email="john@example.com",
                defaults={"job_title": "Developer", "is_opt_out": False}
            )
        """
        try:
            entity = await self.get(**kwargs)
            # Update the existing entity
            if defaults:
                # Get entity ID for update
                entity_id = entity.get("id") if isinstance(entity, dict) else getattr(entity, "id", None)  # type: ignore[union-attr]
                if entity_id is not None:
                    await self.update(defaults, id=entity_id)
                    # Fetch updated entity
                    entity = await self.get(id=entity_id)
            return entity, False
        except DoesNotExist:
            # Create with kwargs + defaults
            create_kwargs = {**kwargs, **(defaults or {})}
            # Clean up lookup operators
            clean_kwargs = {}
            for key, value in create_kwargs.items():
                if "__" in key:
                    field = key.rsplit("__", 1)[0]
                    if key.count("__") == 1 and key.rsplit("__", 1)[1] in (
                        "gt",
                        "gte",
                        "lt",
                        "lte",
                        "ne",
                        "in",
                        "not_in",
                        "like",
                        "not_like",
                        "contains",
                        "is_null",
                        "is_not_null",
                    ):
                        continue
                    clean_kwargs[field] = value
                else:
                    clean_kwargs[key] = value

            entity = await self.create(**clean_kwargs)
            return entity, True

    async def bulk_create(
        self,
        objs: list[dict[str, Any]] | list[T],
    ) -> list[T | dict[str, Any]]:
        """Create multiple entities in bulk.

        Note: CiviCRM API v4 doesn't have native bulk create, so this
        makes individual create calls. For large batches, consider
        using the save action with multiple records.

        Args:
            objs: List of entities to create (as dicts or model instances).

        Returns:
            List of created entities.

        Raises:
            CiviAPIError: If any creation fails.

        Example:
            contacts = await Contact.objects.bulk_create([
                {"first_name": "John", "last_name": "Doe"},
                {"first_name": "Jane", "last_name": "Smith"},
            ])
        """
        results: list[T | dict[str, Any]] = []
        for obj in objs:
            if isinstance(obj, dict):
                values = obj
            else:
                # Assume Pydantic model with model_dump
                values = obj.model_dump(exclude_unset=True) if hasattr(obj, "model_dump") else dict(obj)  # type: ignore[call-overload]

            entity = await self.create(**values)  # type: ignore[arg-type]
            results.append(entity)

        return results

    async def get_fields(self) -> list[FieldMetadata] | list[dict[str, Any]]:
        """Get field metadata for this entity.

        Returns:
            List of field definitions.

        Example:
            fields = await Contact.objects.get_fields()
            for field in fields:
                print(f"{field['name']}: {field.get('type', 'unknown')}")
        """
        response = await self._client.get_fields(self._entity_name)
        return response.values or []

    async def count(self, **kwargs: Any) -> int:
        """Count entities matching the criteria.

        Args:
            **kwargs: Field lookups for filtering.

        Returns:
            Number of matching entities.

        Example:
            total = await Contact.objects.count()
            active = await Contact.objects.count(is_deleted=False)
        """
        where = self._kwargs_to_where(**kwargs) if kwargs else None
        response = await self._client.get(
            self._entity_name,
            select=["id"],
            where=where,
            limit=0,  # Don't fetch records, just count
        )
        return response.count or 0

    async def exists(self, **kwargs: Any) -> bool:
        """Check if any entities match the criteria.

        Args:
            **kwargs: Field lookups for filtering.

        Returns:
            True if at least one entity matches.

        Example:
            if await Contact.objects.exists(email_primary__email="john@example.com"):
                print("Email already registered")
        """
        where = self._kwargs_to_where(**kwargs) if kwargs else None
        response = await self._client.get(
            self._entity_name,
            select=["id"],
            where=where,
            limit=1,
        )
        return bool(response.values)


class SyncEntityManager(Generic[T]):
    """Synchronous manager for CiviCRM entity operations.

    Provides the same interface as EntityManager but uses synchronous
    client for blocking operations.

    Example:
        with SyncCiviClient() as client:
            manager = SyncEntityManager(client, "Contact")
            contact = manager.get(id=123)
    """

    def __init__(
        self,
        client: SyncCiviClient,
        entity_name: str,
        *,
        model_class: type[T] | None = None,
    ) -> None:
        """Initialize SyncEntityManager.

        Args:
            client: SyncCiviClient instance for API communication.
            entity_name: Name of the CiviCRM entity.
            model_class: Optional Pydantic model class for result conversion.
        """
        self._client = client
        self._entity_name = entity_name
        self._model_class = model_class

    @property
    def client(self) -> SyncCiviClient:
        """Get the underlying SyncCiviClient."""
        return self._client

    @property
    def entity_name(self) -> str:
        """Get the entity name this manager operates on."""
        return self._entity_name

    def _kwargs_to_where(self, **kwargs: Any) -> list[list[Any]]:
        """Convert keyword arguments to CiviCRM where clause format."""
        operator_map = {
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
            "ne": "!=",
            "in": "IN",
            "not_in": "NOT IN",
            "like": "LIKE",
            "not_like": "NOT LIKE",
            "contains": "CONTAINS",
            "is_null": "IS NULL",
            "is_not_null": "IS NOT NULL",
        }

        where: list[list[Any]] = []
        for key, value in kwargs.items():
            if "__" in key:
                field, operator_key = key.rsplit("__", 1)
                operator = operator_map.get(operator_key, "=")
                if operator_key not in operator_map:
                    field = key
                    operator = "="
            else:
                field = key
                operator = "="

            if operator in ("IS NULL", "IS NOT NULL"):
                where.append([field, operator])
            else:
                where.append([field, operator, value])

        return where

    def get(self, **kwargs: Any) -> T | dict[str, Any]:
        """Get a single record matching the given criteria.

        Args:
            **kwargs: Field lookups to identify the record.

        Returns:
            The matching entity.

        Raises:
            DoesNotExist: If no record matches.
            MultipleObjectsReturned: If multiple records match.
        """
        where = self._kwargs_to_where(**kwargs)
        response = self._client.get(
            self._entity_name,
            where=where,
            limit=2,
        )

        values = response.values or []
        count = len(values)

        if count == 0:
            raise DoesNotExist(self._entity_name, kwargs)

        if count > 1:
            raise MultipleObjectsReturned(self._entity_name, count, kwargs)

        result = values[0]
        if self._model_class is not None:
            return self._model_class.model_validate(result)
        return result

    def create(self, **kwargs: Any) -> T | dict[str, Any]:
        """Create a new entity.

        Args:
            **kwargs: Field values for the new entity.

        Returns:
            The created entity.
        """
        response = self._client.create(self._entity_name, kwargs)

        if response.values and len(response.values) > 0:
            result = response.values[0]
            if self._model_class is not None:
                return self._model_class.model_validate(result)
            return result

        return {} if self._model_class is None else self._model_class.model_validate({})

    def update(
        self,
        values: dict[str, Any],
        *,
        where: list[list[Any]] | None = None,
        **kwargs: Any,
    ) -> APIResponse[dict[str, Any]]:
        """Update entities matching the criteria.

        Args:
            values: Field values to update.
            where: Raw where conditions.
            **kwargs: Field lookups for filtering.

        Returns:
            API response with updated entities.
        """
        if where is None and not kwargs:
            msg = "update() requires filter criteria (where or kwargs)"
            raise ValueError(msg)

        combined_where = where or []
        if kwargs:
            combined_where.extend(self._kwargs_to_where(**kwargs))

        return self._client.update(self._entity_name, values, combined_where)

    def delete(
        self,
        *,
        where: list[list[Any]] | None = None,
        **kwargs: Any,
    ) -> APIResponse[dict[str, Any]]:
        """Delete entities matching the criteria.

        Args:
            where: Raw where conditions.
            **kwargs: Field lookups for filtering.

        Returns:
            API response.
        """
        if where is None and not kwargs:
            msg = "delete() requires filter criteria (where or kwargs)"
            raise ValueError(msg)

        combined_where = where or []
        if kwargs:
            combined_where.extend(self._kwargs_to_where(**kwargs))

        return self._client.delete(self._entity_name, combined_where)

    def count(self, **kwargs: Any) -> int:
        """Count entities matching the criteria.

        Args:
            **kwargs: Field lookups for filtering.

        Returns:
            Number of matching entities.
        """
        where = self._kwargs_to_where(**kwargs) if kwargs else None
        response = self._client.get(
            self._entity_name,
            select=["id"],
            where=where,
            limit=0,
        )
        return response.count or 0

    def exists(self, **kwargs: Any) -> bool:
        """Check if any entities match the criteria.

        Args:
            **kwargs: Field lookups for filtering.

        Returns:
            True if at least one entity matches.
        """
        where = self._kwargs_to_where(**kwargs) if kwargs else None
        response = self._client.get(
            self._entity_name,
            select=["id"],
            where=where,
            limit=1,
        )
        return bool(response.values)


class ManagerDescriptor(Generic[T]):
    """Descriptor that provides .objects access on entity classes.

    This descriptor enables the Django-style Manager.objects pattern
    on entity model classes.

    Example:
        class Contact(BaseEntity):
            objects: ClassVar[EntityManager["Contact"]] = ManagerDescriptor()

            id: int
            display_name: str

        # Usage:
        contacts = await Contact.objects.filter(last_name="Smith").all()
    """

    def __init__(
        self,
        manager_class: type[EntityManager[T]] = EntityManager,
    ) -> None:
        """Initialize descriptor.

        Args:
            manager_class: Manager class to instantiate.
        """
        self._manager_class = manager_class
        self._entity_name: str | None = None
        self._model_class: type[T] | None = None

    def __set_name__(self, owner: type[T], name: str) -> None:
        """Called when descriptor is assigned to a class attribute.

        Args:
            owner: The class that owns this descriptor.
            name: The attribute name.
        """
        self._model_class = owner
        # Try to get entity name from class
        self._entity_name = getattr(owner, "__entity_name__", owner.__name__)

    def __get__(
        self,
        obj: T | None,
        objtype: type[T] | None = None,
    ) -> EntityManager[T]:
        """Get the manager instance.

        Args:
            obj: Instance (None for class access).
            objtype: The class type.

        Returns:
            EntityManager bound to the entity class.

        Raises:
            RuntimeError: If no client is configured.
        """
        if objtype is None:
            objtype = type(obj)  # type: ignore[assignment]

        # Get client from class or global context
        client = getattr(objtype, "_client", None)
        if client is None:
            # Try to get from a global/thread-local context
            from civicrm_py.core.context import get_current_client

            client = get_current_client()

        if client is None:
            msg = (
                f"No client configured for {objtype.__name__}. Either set _client on the class or use a client context."
            )
            raise RuntimeError(msg)

        return self._manager_class(
            client=client,
            entity_name=self._entity_name or objtype.__name__,
            model_class=self._model_class,
        )


__all__ = [
    "DoesNotExist",
    "EntityManager",
    "ManagerDescriptor",
    "MultipleObjectsReturned",
    "SyncEntityManager",
]
