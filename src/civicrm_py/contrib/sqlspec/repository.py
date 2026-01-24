"""Repository layer for caching CiviCRM entities locally using sqlspec.

Provides a local cache layer that can sync with CiviCRM. Useful for:
- Offline access to frequently used data
- Faster queries for read-heavy workloads
- Local data transformation before sync

This module requires the sqlspec optional dependency:

    pip install 'civi-py[sqlspec]'

Example:
    >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, ContactRepository
    >>>
    >>> config = CiviSQLSpecConfig()
    >>> contact_repo = ContactRepository(config)
    >>>
    >>> async with contact_repo.get_session() as session:
    ...     # Sync contacts from CiviCRM to local DB
    ...     await contact_repo.sync_from_civi(session, client)
    ...
    ...     # Query local cache
    ...     contacts = await contact_repo.filter(session, is_deleted=False)
"""

from __future__ import annotations

import contextlib
import json
import re
from abc import ABC
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig
    from civicrm_py.core.client import CiviClient
    from civicrm_py.entities.activity import Activity
    from civicrm_py.entities.base import BaseEntity
    from civicrm_py.entities.contact import Contact
    from civicrm_py.entities.contribution import Contribution
    from civicrm_py.entities.event import Event
    from civicrm_py.entities.membership import Membership

# Check if sqlspec is available
try:
    from sqlspec import SQLSpec  # type: ignore[import-not-found]

    SQLSPEC_AVAILABLE = True
except ImportError:
    SQLSPEC_AVAILABLE = False

    class SQLSpec:
        """Stub when sqlspec is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = "sqlspec is required for repository features. Install with: pip install 'civi-py[sqlspec]'"
            raise ImportError(msg)

        def add_config(self, *args: Any, **kwargs: Any) -> None:
            """Stub for SQLSpec.add_config."""

        def get_session(self, *args: Any, **kwargs: Any) -> Any:
            """Stub for SQLSpec.get_session."""


# Type variable for entity subclasses
EntityT = TypeVar("EntityT", bound="BaseEntity")


class SyncStatus(str, Enum):
    """Status of entity synchronization.

    Attributes:
        PENDING: Entity has local changes not yet synced to CiviCRM.
        SYNCED: Entity is in sync with CiviCRM.
        CONFLICT: Local and remote changes conflict.
        ERROR: Sync failed with an error.
    """

    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass
class SyncMetadata:
    """Metadata for tracking entity synchronization state.

    Attributes:
        entity_id: The CiviCRM entity ID.
        entity_type: The entity type name (e.g., 'Contact', 'Activity').
        last_synced_at: Timestamp of last successful sync from CiviCRM.
        last_modified_locally: Timestamp of last local modification.
        sync_status: Current synchronization status.
        error_message: Error message if sync_status is ERROR.
        civi_modified_date: Last modified date from CiviCRM.
    """

    entity_id: int
    entity_type: str
    last_synced_at: datetime | None = None
    last_modified_locally: datetime | None = None
    sync_status: SyncStatus = SyncStatus.SYNCED
    error_message: str | None = None
    civi_modified_date: str | None = None


@dataclass
class SyncResult:
    """Result of a sync operation.

    Attributes:
        synced_count: Number of entities successfully synced.
        error_count: Number of entities that failed to sync.
        conflict_count: Number of entities with conflicts.
        errors: List of error messages with entity IDs.
    """

    synced_count: int = 0
    error_count: int = 0
    conflict_count: int = 0
    errors: list[tuple[int | None, str]] = field(default_factory=list)


# Field type mapping from Python types to SQL types
PYTHON_TO_SQL_TYPE: dict[str, str] = {
    "int": "INTEGER",
    "float": "REAL",
    "str": "TEXT",
    "bool": "INTEGER",  # SQLite uses INTEGER for boolean
    "list": "TEXT",  # JSON-encoded lists
    "dict": "TEXT",  # JSON-encoded dicts
    "datetime": "TEXT",  # ISO format strings
    "date": "TEXT",  # ISO format strings
}


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case.

    Args:
        name: CamelCase string.

    Returns:
        snake_case string.

    Example:
        >>> _camel_to_snake("ContactType")
        'contact_type'
    """
    pattern = re.compile(r"(?<!^)(?=[A-Z])")
    return pattern.sub("_", name).lower()


def _get_field_sql_type(field_type: type | str | None) -> str:
    """Get SQL type for a Python field type.

    Args:
        field_type: Python type or type annotation.

    Returns:
        SQL type string.
    """
    if field_type is None:
        return "TEXT"

    type_str = str(field_type)
    type_str_lower = type_str.lower()

    # Handle list types early (always TEXT for JSON storage)
    if "list" in type_str_lower:
        return "TEXT"

    # Try to find matching type in mapping
    def find_sql_type(search_str: str) -> str | None:
        for py_type, sql_type in PYTHON_TO_SQL_TYPE.items():
            if py_type in search_str:
                return sql_type
        return None

    # Handle Optional types - extract the non-None type
    if "None" in type_str:
        result = find_sql_type(type_str_lower)
        return result if result else "TEXT"

    # Direct type mapping for actual type objects
    if isinstance(field_type, type):
        type_name = field_type.__name__
        return PYTHON_TO_SQL_TYPE.get(type_name, "TEXT")

    # String-based type mapping
    result = find_sql_type(type_str_lower)
    return result if result else "TEXT"


class CiviRepository(ABC, Generic[EntityT]):
    """Base repository for caching CiviCRM entities locally using sqlspec.

    Provides a local cache layer that can sync with CiviCRM. Useful for:
    - Offline access to frequently used data
    - Faster queries for read-heavy workloads
    - Local data transformation before sync

    This is an abstract base class. Use entity-specific repositories like
    ContactRepository or ActivityRepository.

    Type Parameters:
        EntityT: The entity type this repository manages.

    Attributes:
        entity_type: The entity class this repository manages.
        config: SQLSpec configuration for database connection.

    Example:
        >>> contact_repo = ContactRepository(config)
        >>>
        >>> async with contact_repo.get_session() as session:
        ...     # Sync contacts from CiviCRM to local DB
        ...     await contact_repo.sync_from_civi(session, client)
        ...
        ...     # Query local cache
        ...     contacts = await contact_repo.filter(session, is_deleted=False)
    """

    # Subclasses must set this
    entity_type: type[EntityT]

    # Core fields that all entities have
    _core_fields: tuple[str, ...] = ("id", "created_date", "modified_date")

    # Fields to exclude from caching (internal state tracking)
    _excluded_fields: tuple[str, ...] = ("_state", "_client")

    def __init__(self, config: CiviSQLSpecConfig) -> None:
        """Initialize repository with database configuration.

        Args:
            config: SQLSpec configuration for database connection.

        Raises:
            ImportError: If sqlspec is not installed.
            AttributeError: If entity_type is not set on the subclass.
        """
        if not hasattr(self, "entity_type") or self.entity_type is None:
            msg = f"{self.__class__.__name__} must define 'entity_type' class attribute"
            raise AttributeError(msg)

        self._config = config
        self._adapter_config = config.get_adapter_config()
        self._table_name = self._get_table_name()
        self._metadata_table = f"{config.table_prefix}sync_metadata"
        self._initialized = False

    def _get_table_name(self) -> str:
        """Generate table name from entity type.

        Returns:
            Table name with configured prefix.
        """
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)
        snake_name = _camel_to_snake(entity_name)
        return f"{self._config.table_prefix}{snake_name}"

    def _get_entity_fields(self) -> dict[str, str]:
        """Get entity fields mapped to SQL column types.

        Returns:
            Dictionary of field name to SQL type.
        """
        import msgspec

        fields: dict[str, str] = {}

        # Get fields from msgspec struct
        try:
            struct_fields = msgspec.structs.fields(self.entity_type)
            for field_info in struct_fields:
                if field_info.name in self._excluded_fields:
                    continue
                if field_info.name.startswith("_"):
                    continue

                # Get the SQL type for this field
                sql_type = _get_field_sql_type(field_info.type)
                fields[field_info.name] = sql_type
        except TypeError:
            # Not a msgspec struct, fall back to __annotations__
            annotations = getattr(self.entity_type, "__annotations__", {})
            for field_name, field_type in annotations.items():
                if field_name in self._excluded_fields:
                    continue
                if field_name.startswith("_"):
                    continue
                sql_type = _get_field_sql_type(field_type)
                fields[field_name] = sql_type

        return fields

    def _get_create_table_sql(self) -> str:
        """Generate CREATE TABLE SQL statement.

        Returns:
            SQL CREATE TABLE statement.
        """
        fields = self._get_entity_fields()

        columns = []
        for field_name, sql_type in fields.items():
            if field_name == "id":
                columns.append(f"{field_name} INTEGER PRIMARY KEY")
            else:
                columns.append(f"{field_name} {sql_type}")

        return f"CREATE TABLE IF NOT EXISTS {self._table_name} ({', '.join(columns)})"

    def _get_create_metadata_table_sql(self) -> str:
        """Generate CREATE TABLE SQL for sync metadata.

        Returns:
            SQL CREATE TABLE statement for metadata table.
        """
        return f"""
            CREATE TABLE IF NOT EXISTS {self._metadata_table} (
                entity_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                last_synced_at TEXT,
                last_modified_locally TEXT,
                sync_status TEXT DEFAULT 'synced',
                error_message TEXT,
                civi_modified_date TEXT,
                PRIMARY KEY (entity_id, entity_type)
            )
        """

    async def get_session(self) -> AsyncIterator[Any]:
        """Get an async database session.

        Yields:
            Database session from sqlspec adapter.

        Raises:
            ImportError: If sqlspec is not installed.

        Example:
            >>> async with repo.get_session() as session:
            ...     contacts = await repo.all(session)
        """
        # SQLSpec stub raises ImportError if sqlspec not installed
        spec = SQLSpec()
        spec.add_config(self._adapter_config)

        async with spec.get_session() as session:
            # Initialize tables on first use
            if not self._initialized and self._config.auto_create_tables:
                await self._initialize_tables(session)
            yield session

    async def _initialize_tables(self, session: Any) -> None:
        """Initialize database tables.

        Args:
            session: Database session.
        """
        # Create entity table
        await session.execute(self._get_create_table_sql())

        # Create metadata table
        await session.execute(self._get_create_metadata_table_sql())

        self._initialized = True

    def _entity_to_row(self, entity: EntityT) -> dict[str, Any]:
        """Convert entity to database row dictionary.

        Args:
            entity: Entity instance to convert.

        Returns:
            Dictionary suitable for database insertion.
        """
        row: dict[str, Any] = {}
        fields = self._get_entity_fields()

        for field_name in fields:
            value = getattr(entity, field_name, None)

            # Convert lists and dicts to JSON
            if isinstance(value, list | dict):
                value = json.dumps(value)

            # Convert booleans to integers for SQLite
            elif isinstance(value, bool):
                value = 1 if value else 0

            row[field_name] = value

        return row

    def _row_to_entity(self, row: dict[str, Any]) -> EntityT:
        """Convert database row to entity instance.

        Args:
            row: Database row dictionary.

        Returns:
            Entity instance.
        """
        data: dict[str, Any] = {}
        fields = self._get_entity_fields()

        for field_name, sql_type in fields.items():
            if field_name not in row:
                continue

            value = row[field_name]

            # Parse JSON fields
            if sql_type == "TEXT" and isinstance(value, str):
                # Try to parse as JSON for list/dict fields
                if value.startswith(("[", "{")):
                    with contextlib.suppress(json.JSONDecodeError):
                        value = json.loads(value)

            # Convert integers back to booleans where appropriate
            elif sql_type == "INTEGER" and isinstance(value, int):
                # Check if the field type annotation suggests boolean
                annotations = getattr(self.entity_type, "__annotations__", {})
                if field_name in annotations:
                    type_str = str(annotations[field_name])
                    if "bool" in type_str.lower():
                        value = bool(value)

            data[field_name] = value

        return self.entity_type.from_dict(data)

    async def sync_from_civi(
        self,
        session: Any,
        client: CiviClient,
        *,
        limit: int | None = None,
        **filters: Any,
    ) -> SyncResult:
        """Pull data from CiviCRM to local database.

        Fetches entities from CiviCRM API and stores them in the local
        database cache. Updates sync metadata for each entity.

        Args:
            session: Database session.
            client: CiviCRM client for API requests.
            limit: Maximum number of entities to sync.
            **filters: Filter conditions for the CiviCRM query.

        Returns:
            SyncResult with counts and any errors.

        Example:
            >>> async with repo.get_session() as session:
            ...     result = await repo.sync_from_civi(session, client, is_deleted=False, limit=100)
            ...     print(f"Synced {result.synced_count} entities")
        """
        result = SyncResult()
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)

        # Build where clause from filters
        where: list[list[Any]] = []
        for key, value in filters.items():
            where.append([key, "=", value])

        try:
            # Fetch from CiviCRM
            response = await client.get(
                entity_name,
                where=where if where else None,
                limit=limit,
            )

            if not response.values:
                return result

            _now = datetime.now(tz=UTC).isoformat()

            for record in response.values:
                try:
                    entity_id = record.get("id")
                    if entity_id is None:
                        result.error_count += 1
                        result.errors.append((None, "Entity missing ID"))
                        continue

                    # Upsert entity data
                    await self._upsert_entity(session, record)

                    # Update sync metadata
                    metadata = SyncMetadata(
                        entity_id=entity_id,
                        entity_type=entity_name,
                        last_synced_at=datetime.now(tz=UTC),
                        sync_status=SyncStatus.SYNCED,
                        civi_modified_date=record.get("modified_date"),
                    )
                    await self._upsert_metadata(session, metadata)

                    result.synced_count += 1

                except Exception as e:  # noqa: BLE001
                    entity_id = record.get("id")
                    result.error_count += 1
                    result.errors.append((entity_id, str(e)))

        except Exception as e:  # noqa: BLE001
            result.error_count += 1
            result.errors.append((None, f"API request failed: {e}"))

        return result

    async def sync_to_civi(
        self,
        session: Any,
        client: CiviClient,
        *,
        only_pending: bool = True,
        **filters: Any,
    ) -> SyncResult:
        """Push local changes to CiviCRM.

        Finds entities with pending local changes and pushes them to
        CiviCRM. Updates sync metadata on success.

        Args:
            session: Database session.
            client: CiviCRM client for API requests.
            only_pending: Only sync entities with PENDING status.
            **filters: Additional filter conditions.

        Returns:
            SyncResult with counts and any errors.

        Example:
            >>> async with repo.get_session() as session:
            ...     result = await repo.sync_to_civi(session, client)
            ...     print(f"Pushed {result.synced_count} entities to CiviCRM")
        """
        result = SyncResult()
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)

        # Get entities to sync
        if only_pending:
            entities = await self._get_pending_entities(session)
        else:
            entities = await self.all(session, **filters)

        for entity in entities:
            entity_id = getattr(entity, "id", None)

            try:
                # Get metadata to check for conflicts
                metadata = await self._get_metadata(session, entity_id, entity_name) if entity_id else None

                if metadata and metadata.sync_status == SyncStatus.CONFLICT:
                    result.conflict_count += 1
                    continue

                # Convert entity to values dict
                values = entity.to_dict(exclude_none=True)

                if entity_id is None:
                    # Create new entity
                    response = await client.create(entity_name, values)
                    if response.values:
                        new_id = response.values[0].get("id")
                        if new_id:
                            # Update local entity with new ID
                            await self._update_entity_id(session, entity, new_id)
                            entity_id = new_id
                else:
                    # Update existing entity
                    values_without_id = {k: v for k, v in values.items() if k != "id"}
                    await client.update(entity_name, values_without_id, [["id", "=", entity_id]])

                # Update metadata
                if entity_id is not None:
                    metadata = SyncMetadata(
                        entity_id=entity_id,
                        entity_type=entity_name,
                        last_synced_at=datetime.now(tz=UTC),
                        sync_status=SyncStatus.SYNCED,
                    )
                    await self._upsert_metadata(session, metadata)

                result.synced_count += 1

            except Exception as e:  # noqa: BLE001
                result.error_count += 1
                result.errors.append((entity_id, str(e)))

                # Mark as error in metadata
                if entity_id is not None:
                    error_metadata = SyncMetadata(
                        entity_id=entity_id,
                        entity_type=entity_name,
                        sync_status=SyncStatus.ERROR,
                        error_message=str(e),
                    )
                    await self._upsert_metadata(session, error_metadata)

        return result

    async def filter(
        self,
        session: Any,
        *,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        **kwargs: Any,
    ) -> Sequence[EntityT]:
        """Query local cache with filter conditions.

        Args:
            session: Database session.
            limit: Maximum number of results.
            offset: Number of results to skip.
            order_by: Field to order by (prefix with '-' for descending).
            **kwargs: Filter conditions (field=value).

        Returns:
            Sequence of matching entities.

        Example:
            >>> async with repo.get_session() as session:
            ...     contacts = await repo.filter(
            ...         session, is_deleted=False, limit=10, order_by="-created_date"
            ...     )
        """
        # Build SQL query
        sql = f"SELECT * FROM {self._table_name}"
        params: list[Any] = []

        if kwargs:
            conditions = []
            for field_name, field_value in kwargs.items():
                conditions.append(f"{field_name} = ?")
                # Convert booleans for SQLite
                param_value = 1 if field_value is True else (0 if field_value is False else field_value)
                params.append(param_value)
            sql += f" WHERE {' AND '.join(conditions)}"

        if order_by:
            if order_by.startswith("-"):
                sql += f" ORDER BY {order_by[1:]} DESC"
            else:
                sql += f" ORDER BY {order_by} ASC"

        if limit is not None:
            sql += f" LIMIT {limit}"

        if offset is not None:
            sql += f" OFFSET {offset}"

        # Execute query
        rows = await session.fetch_all(sql, params)

        return [self._row_to_entity(dict(row)) for row in rows]

    async def get(self, session: Any, entity_id: int) -> EntityT | None:
        """Get single entity by ID from local cache.

        Args:
            session: Database session.
            entity_id: Entity ID to retrieve.

        Returns:
            Entity instance or None if not found.

        Example:
            >>> async with repo.get_session() as session:
            ...     contact = await repo.get(session, 42)
            ...     if contact:
            ...         print(contact.display_name)
        """
        sql = f"SELECT * FROM {self._table_name} WHERE id = ?"
        row = await session.fetch_one(sql, [entity_id])

        if row is None:
            return None

        return self._row_to_entity(dict(row))

    async def all(
        self,
        session: Any,
        *,
        limit: int | None = None,
        **kwargs: Any,
    ) -> Sequence[EntityT]:
        """Get all entities from local cache.

        Args:
            session: Database session.
            limit: Maximum number of results.
            **kwargs: Optional filter conditions.

        Returns:
            Sequence of all entities (optionally filtered).

        Example:
            >>> async with repo.get_session() as session:
            ...     all_contacts = await repo.all(session, limit=100)
        """
        return await self.filter(session, limit=limit, **kwargs)

    async def save(self, session: Any, entity: EntityT) -> EntityT:
        """Save entity to local cache.

        Creates or updates the entity in the local database and marks
        it as pending for sync to CiviCRM.

        Args:
            session: Database session.
            entity: Entity to save.

        Returns:
            Saved entity instance.

        Example:
            >>> async with repo.get_session() as session:
            ...     contact = Contact(first_name="John", last_name="Doe")
            ...     contact = await repo.save(session, contact)
        """
        entity_id = getattr(entity, "id", None)
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)

        # Upsert entity
        row = self._entity_to_row(entity)
        await self._upsert_entity(session, row)

        # Get ID if it was auto-generated
        if entity_id is None:
            # Get last inserted ID
            result = await session.fetch_one("SELECT last_insert_rowid() as id")
            if result:
                entity_id = result["id"]
                object.__setattr__(entity, "id", entity_id)

        # Mark as pending sync
        if entity_id is not None:
            metadata = SyncMetadata(
                entity_id=entity_id,
                entity_type=entity_name,
                last_modified_locally=datetime.now(tz=UTC),
                sync_status=SyncStatus.PENDING,
            )
            await self._upsert_metadata(session, metadata)

        return entity

    async def delete(self, session: Any, entity_id: int) -> bool:
        """Delete entity from local cache.

        Args:
            session: Database session.
            entity_id: ID of entity to delete.

        Returns:
            True if entity was deleted, False if not found.

        Example:
            >>> async with repo.get_session() as session:
            ...     deleted = await repo.delete(session, 42)
        """
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)

        # Delete entity
        sql = f"DELETE FROM {self._table_name} WHERE id = ?"
        result = await session.execute(sql, [entity_id])

        # Delete metadata
        meta_sql = f"DELETE FROM {self._metadata_table} WHERE entity_id = ? AND entity_type = ?"
        await session.execute(meta_sql, [entity_id, entity_name])

        return result.rowcount > 0 if hasattr(result, "rowcount") else True

    async def count(self, session: Any, **kwargs: Any) -> int:
        """Count entities in local cache.

        Args:
            session: Database session.
            **kwargs: Optional filter conditions.

        Returns:
            Number of matching entities.

        Example:
            >>> async with repo.get_session() as session:
            ...     total = await repo.count(session)
            ...     active = await repo.count(session, is_deleted=False)
        """
        sql = f"SELECT COUNT(*) as cnt FROM {self._table_name}"
        params: list[Any] = []

        if kwargs:
            conditions = []
            for field_name, field_value in kwargs.items():
                conditions.append(f"{field_name} = ?")
                param_value = 1 if field_value is True else (0 if field_value is False else field_value)
                params.append(param_value)
            sql += f" WHERE {' AND '.join(conditions)}"

        result = await session.fetch_one(sql, params)
        return result["cnt"] if result else 0

    async def get_sync_metadata(
        self,
        session: Any,
        entity_id: int,
    ) -> SyncMetadata | None:
        """Get sync metadata for an entity.

        Args:
            session: Database session.
            entity_id: Entity ID.

        Returns:
            SyncMetadata or None if not found.
        """
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)
        return await self._get_metadata(session, entity_id, entity_name)

    async def _upsert_entity(self, session: Any, data: dict[str, Any]) -> None:
        """Insert or update entity in database.

        Args:
            session: Database session.
            data: Entity data dictionary.
        """
        fields = list(data.keys())
        placeholders = ", ".join("?" * len(fields))
        columns = ", ".join(fields)

        # Build upsert SQL (SQLite syntax)
        update_clause = ", ".join(f"{f} = excluded.{f}" for f in fields if f != "id")

        sql = f"""
            INSERT INTO {self._table_name} ({columns})
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {update_clause}
        """

        values = [data.get(f) for f in fields]
        await session.execute(sql, values)

    async def _upsert_metadata(self, session: Any, metadata: SyncMetadata) -> None:
        """Insert or update sync metadata.

        Args:
            session: Database session.
            metadata: SyncMetadata instance.
        """
        sql = f"""
            INSERT INTO {self._metadata_table}
                (entity_id, entity_type, last_synced_at, last_modified_locally,
                 sync_status, error_message, civi_modified_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id, entity_type) DO UPDATE SET
                last_synced_at = excluded.last_synced_at,
                last_modified_locally = excluded.last_modified_locally,
                sync_status = excluded.sync_status,
                error_message = excluded.error_message,
                civi_modified_date = excluded.civi_modified_date
        """

        values = [
            metadata.entity_id,
            metadata.entity_type,
            metadata.last_synced_at.isoformat() if metadata.last_synced_at else None,
            metadata.last_modified_locally.isoformat() if metadata.last_modified_locally else None,
            metadata.sync_status.value,
            metadata.error_message,
            metadata.civi_modified_date,
        ]
        await session.execute(sql, values)

    async def _get_metadata(
        self,
        session: Any,
        entity_id: int,
        entity_type: str,
    ) -> SyncMetadata | None:
        """Get sync metadata from database.

        Args:
            session: Database session.
            entity_id: Entity ID.
            entity_type: Entity type name.

        Returns:
            SyncMetadata or None.
        """
        sql = f"""
            SELECT * FROM {self._metadata_table}
            WHERE entity_id = ? AND entity_type = ?
        """

        row = await session.fetch_one(sql, [entity_id, entity_type])
        if row is None:
            return None

        row_dict = dict(row)
        return SyncMetadata(
            entity_id=row_dict["entity_id"],
            entity_type=row_dict["entity_type"],
            last_synced_at=(
                datetime.fromisoformat(row_dict["last_synced_at"]) if row_dict.get("last_synced_at") else None
            ),
            last_modified_locally=(
                datetime.fromisoformat(row_dict["last_modified_locally"])
                if row_dict.get("last_modified_locally")
                else None
            ),
            sync_status=SyncStatus(row_dict["sync_status"]),
            error_message=row_dict.get("error_message"),
            civi_modified_date=row_dict.get("civi_modified_date"),
        )

    async def _get_pending_entities(self, session: Any) -> Sequence[EntityT]:
        """Get entities with pending local changes.

        Args:
            session: Database session.

        Returns:
            Sequence of entities pending sync.
        """
        entity_name = getattr(self.entity_type, "__entity_name__", self.entity_type.__name__)

        # Join entity table with metadata to find pending entities
        sql = f"""
            SELECT e.* FROM {self._table_name} e
            INNER JOIN {self._metadata_table} m
                ON e.id = m.entity_id AND m.entity_type = ?
            WHERE m.sync_status = ?
        """

        rows = await session.fetch_all(sql, [entity_name, SyncStatus.PENDING.value])
        return [self._row_to_entity(dict(row)) for row in rows]

    async def _update_entity_id(
        self,
        session: Any,
        entity: EntityT,
        new_id: int,
    ) -> None:
        """Update entity ID after CiviCRM creation.

        Args:
            session: Database session.
            entity: Entity instance.
            new_id: New ID from CiviCRM.
        """
        old_id = getattr(entity, "id", None)
        if old_id is not None:
            # Update the entity record with new ID
            sql = f"UPDATE {self._table_name} SET id = ? WHERE id = ?"
            await session.execute(sql, [new_id, old_id])

        object.__setattr__(entity, "id", new_id)


# =============================================================================
# Concrete Repository Classes
# =============================================================================


class ContactRepository(CiviRepository["Contact"]):
    """Repository for caching Contact entities.

    Example:
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, ContactRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = ContactRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     await repo.sync_from_civi(session, client, is_deleted=False)
        ...     contacts = await repo.filter(session, contact_type="Individual")
    """

    @property
    def entity_type(self) -> type[Contact]:
        """Get the entity type for this repository."""
        from civicrm_py.entities.contact import Contact

        return Contact


class ActivityRepository(CiviRepository["Activity"]):
    """Repository for caching Activity entities.

    Example:
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, ActivityRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = ActivityRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     await repo.sync_from_civi(session, client, is_deleted=False)
        ...     activities = await repo.filter(session, status_id=2)
    """

    @property
    def entity_type(self) -> type[Activity]:
        """Get the entity type for this repository."""
        from civicrm_py.entities.activity import Activity

        return Activity


class ContributionRepository(CiviRepository["Contribution"]):
    """Repository for caching Contribution entities.

    Example:
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, ContributionRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = ContributionRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     await repo.sync_from_civi(session, client, is_test=False)
        ...     contributions = await repo.filter(session, contribution_status_id=1)
    """

    @property
    def entity_type(self) -> type[Contribution]:
        """Get the entity type for this repository."""
        from civicrm_py.entities.contribution import Contribution

        return Contribution


class EventRepository(CiviRepository["Event"]):
    """Repository for caching Event entities.

    Example:
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, EventRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = EventRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     await repo.sync_from_civi(session, client, is_active=True)
        ...     events = await repo.filter(session, is_public=True)
    """

    @property
    def entity_type(self) -> type[Event]:
        """Get the entity type for this repository."""
        from civicrm_py.entities.event import Event

        return Event


class MembershipRepository(CiviRepository["Membership"]):
    """Repository for caching Membership entities.

    Example:
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, MembershipRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = MembershipRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     await repo.sync_from_civi(session, client, is_test=False)
        ...     memberships = await repo.filter(session, status_id=1)
    """

    @property
    def entity_type(self) -> type[Membership]:
        """Get the entity type for this repository."""
        from civicrm_py.entities.membership import Membership

        return Membership


__all__ = [
    "ActivityRepository",
    "CiviRepository",
    "ContactRepository",
    "ContributionRepository",
    "EntityT",
    "EventRepository",
    "MembershipRepository",
    "SyncMetadata",
    "SyncResult",
    "SyncStatus",
]
