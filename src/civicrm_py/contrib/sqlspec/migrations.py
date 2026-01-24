"""Database migrations for sqlspec CiviCRM cache tables.

Provides schema management and migrations for the local cache layer used to
persist CiviCRM entities. Supports both SQLite and PostgreSQL databases.

This module requires the sqlspec optional dependency:

    pip install 'civi-py[sqlspec]'

Example:
    >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
    >>> from civicrm_py.contrib.sqlspec.migrations import MigrationConfig, upgrade
    >>>
    >>> sqlspec_config = CiviSQLSpecConfig(database="cache.db")
    >>> migration_config = MigrationConfig()
    >>>
    >>> # Run migrations
    >>> async with get_session(sqlspec_config) as session:
    ...     await upgrade(session, migration_config)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal


class DatabaseDialect(str, Enum):
    """Supported database dialects.

    Attributes:
        SQLITE: SQLite database (aiosqlite adapter).
        POSTGRESQL: PostgreSQL database (asyncpg adapter).
    """

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


@dataclass
class MigrationConfig:
    """Configuration for sqlspec cache schema migrations.

    Controls how cache tables are created and named, and which entity
    types should have corresponding cache tables.

    Attributes:
        table_prefix: Prefix for all cache tables. Defaults to 'civi_cache_'.
        include_entities: List of entity types to create tables for.
            Defaults to common entities: Contact, Activity, Contribution,
            Event, and Membership.
        version_table: Name of the migrations tracking table. This table
            stores the current migration version. Defaults to 'civi_migrations'.
        dialect: Database dialect to use for DDL generation. Defaults to
            'sqlite'. Set to 'postgresql' for asyncpg adapter.

    Example:
        >>> config = MigrationConfig()
        >>> config.table_prefix
        'civi_cache_'
        >>> config.include_entities
        ['Contact', 'Activity', 'Contribution', 'Event', 'Membership']

        >>> # Custom configuration
        >>> config = MigrationConfig(
        ...     table_prefix="app_civi_",
        ...     include_entities=["Contact", "Contribution"],
        ...     dialect="postgresql",
        ... )
    """

    table_prefix: str = "civi_cache_"
    include_entities: list[str] = field(
        default_factory=lambda: ["Contact", "Activity", "Contribution", "Event", "Membership"],
    )
    version_table: str = "civi_migrations"
    dialect: Literal["sqlite", "postgresql"] = "sqlite"


@dataclass
class Migration:
    """Represents a single migration.

    Attributes:
        version: Migration version number.
        description: Human-readable description of what this migration does.
        upgrade_sql: SQL statements to apply the migration (list for multi-statement).
        downgrade_sql: SQL statements to rollback the migration.
    """

    version: int
    description: str
    upgrade_sql: list[str]
    downgrade_sql: list[str]


@dataclass
class MigrationResult:
    """Result of a migration operation.

    Attributes:
        success: Whether the migration completed successfully.
        applied_versions: List of migration versions that were applied.
        current_version: Current migration version after operation.
        errors: List of any errors encountered.
    """

    success: bool = True
    applied_versions: list[int] = field(default_factory=list)
    current_version: int = 0
    errors: list[str] = field(default_factory=list)


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


def _is_postgresql(dialect: DatabaseDialect | str) -> bool:
    """Check if dialect is PostgreSQL.

    Args:
        dialect: Database dialect to check.

    Returns:
        True if PostgreSQL, False otherwise.
    """
    return dialect in {DatabaseDialect.POSTGRESQL, "postgresql"}


def _get_placeholder(dialect: DatabaseDialect | str, index: int = 1) -> str:
    """Get parameter placeholder for the given dialect.

    Args:
        dialect: Database dialect.
        index: Parameter index (1-based, for PostgreSQL $1, $2, etc.).

    Returns:
        Parameter placeholder string.
    """
    if _is_postgresql(dialect):
        return f"${index}"
    return "?"


def _get_timestamp_type(dialect: DatabaseDialect | str) -> str:
    """Get timestamp type for the given dialect.

    Args:
        dialect: Database dialect.

    Returns:
        SQL timestamp type.
    """
    if _is_postgresql(dialect):
        return "TIMESTAMP WITH TIME ZONE"
    return "TEXT"


def _get_json_type(dialect: DatabaseDialect | str) -> str:
    """Get JSON type for the given dialect.

    Args:
        dialect: Database dialect.

    Returns:
        SQL JSON type.
    """
    if _is_postgresql(dialect):
        return "JSONB"
    return "TEXT"


def _get_serial_type(dialect: DatabaseDialect | str) -> str:
    """Get auto-increment primary key type for the given dialect.

    Args:
        dialect: Database dialect.

    Returns:
        SQL serial/auto-increment type.
    """
    if _is_postgresql(dialect):
        return "SERIAL"
    return "INTEGER"


def _get_upsert_conflict_syntax(
    dialect: DatabaseDialect | str,
    table: str,
    columns: list[str],
    conflict_columns: list[str],
    update_columns: list[str],
) -> str:
    """Generate upsert SQL for the given dialect.

    Args:
        dialect: Database dialect.
        table: Table name.
        columns: All columns in the INSERT.
        conflict_columns: Columns that define uniqueness.
        update_columns: Columns to update on conflict.

    Returns:
        SQL upsert statement.
    """
    placeholders = [_get_placeholder(dialect, i + 1) for i in range(len(columns))]
    columns_str = ", ".join(columns)
    placeholders_str = ", ".join(placeholders)

    if _is_postgresql(dialect):
        conflict_str = ", ".join(conflict_columns)
        update_str = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_columns)
        return f"""
            INSERT INTO {table} ({columns_str})
            VALUES ({placeholders_str})
            ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}
        """
    # SQLite syntax
    update_str = ", ".join(f"{col} = excluded.{col}" for col in update_columns)
    return f"""
        INSERT INTO {table} ({columns_str})
        VALUES ({placeholders_str})
        ON CONFLICT DO UPDATE SET {update_str}
    """


def generate_version_table_ddl(config: MigrationConfig) -> str:
    """Generate CREATE TABLE DDL for the migrations version tracking table.

    Args:
        config: Migration configuration.

    Returns:
        SQL CREATE TABLE statement.

    Example:
        >>> config = MigrationConfig()
        >>> ddl = generate_version_table_ddl(config)
        >>> "civi_migrations" in ddl
        True
    """
    timestamp_type = _get_timestamp_type(config.dialect)

    return f"""
        CREATE TABLE IF NOT EXISTS {config.version_table} (
            id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL UNIQUE,
            description TEXT NOT NULL,
            applied_at {timestamp_type} NOT NULL,
            checksum TEXT
        )
    """


def generate_entity_table_ddl(entity_name: str, config: MigrationConfig) -> str:
    """Generate CREATE TABLE DDL for an entity cache table.

    Creates a table with:
    - id: Primary key from CiviCRM
    - data: JSON/JSONB for full entity data
    - created_at, updated_at: Local timestamps
    - sync_status: Current sync state
    - last_synced_at: When last synced with CiviCRM
    - last_modified_locally: When last changed locally

    Args:
        entity_name: CiviCRM entity name (e.g., 'Contact', 'Activity').
        config: Migration configuration.

    Returns:
        SQL CREATE TABLE statement.

    Example:
        >>> config = MigrationConfig()
        >>> ddl = generate_entity_table_ddl("Contact", config)
        >>> "civi_cache_contact" in ddl
        True
    """
    table_name = f"{config.table_prefix}{_camel_to_snake(entity_name)}"
    timestamp_type = _get_timestamp_type(config.dialect)
    json_type = _get_json_type(config.dialect)

    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY,
            data {json_type} NOT NULL,
            created_at {timestamp_type} NOT NULL,
            updated_at {timestamp_type} NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'synced',
            last_synced_at {timestamp_type},
            last_modified_locally {timestamp_type}
        )
    """


def generate_sync_metadata_table_ddl(config: MigrationConfig) -> str:
    """Generate CREATE TABLE DDL for the sync metadata tracking table.

    This table tracks synchronization state for all cached entities across
    all entity types.

    Args:
        config: Migration configuration.

    Returns:
        SQL CREATE TABLE statement.

    Example:
        >>> config = MigrationConfig()
        >>> ddl = generate_sync_metadata_table_ddl(config)
        >>> "sync_metadata" in ddl
        True
    """
    table_name = f"{config.table_prefix}sync_metadata"
    timestamp_type = _get_timestamp_type(config.dialect)

    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            entity_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            last_synced_at {timestamp_type},
            last_modified_locally {timestamp_type},
            sync_status TEXT NOT NULL DEFAULT 'synced',
            error_message TEXT,
            civi_modified_date TEXT,
            PRIMARY KEY (entity_id, entity_type)
        )
    """


def generate_sync_cursor_table_ddl(config: MigrationConfig) -> str:
    """Generate CREATE TABLE DDL for sync cursor tracking.

    This table tracks the last sync point for incremental syncs per entity type.

    Args:
        config: Migration configuration.

    Returns:
        SQL CREATE TABLE statement.
    """
    table_name = f"{config.table_prefix}sync_cursor"
    timestamp_type = _get_timestamp_type(config.dialect)

    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            entity_type TEXT PRIMARY KEY,
            last_sync_id INTEGER,
            last_sync_modified_date TEXT,
            last_full_sync_at {timestamp_type},
            sync_in_progress INTEGER DEFAULT 0
        )
    """


def generate_table_ddl(entity_name: str, config: MigrationConfig) -> str:
    """Generate CREATE TABLE DDL for an entity cache table.

    This is an alias for generate_entity_table_ddl for backward compatibility.

    Args:
        entity_name: CiviCRM entity name.
        config: Migration configuration.

    Returns:
        SQL CREATE TABLE statement.
    """
    return generate_entity_table_ddl(entity_name, config)


def _build_initial_migration(config: MigrationConfig) -> Migration:
    """Build the initial migration (version 1).

    Creates:
    - Migrations version tracking table
    - Entity cache tables for configured entities
    - Sync metadata table
    - Sync cursor table

    Args:
        config: Migration configuration.

    Returns:
        Migration object with upgrade and downgrade SQL.
    """
    upgrade_sql: list[str] = []
    downgrade_sql: list[str] = []

    # Version tracking table
    upgrade_sql.append(generate_version_table_ddl(config))
    downgrade_sql.insert(0, f"DROP TABLE IF EXISTS {config.version_table}")

    # Entity cache tables
    for entity_name in config.include_entities:
        table_name = f"{config.table_prefix}{_camel_to_snake(entity_name)}"
        upgrade_sql.append(generate_entity_table_ddl(entity_name, config))
        downgrade_sql.insert(0, f"DROP TABLE IF EXISTS {table_name}")

    # Sync metadata table
    sync_metadata_table = f"{config.table_prefix}sync_metadata"
    upgrade_sql.append(generate_sync_metadata_table_ddl(config))
    downgrade_sql.insert(0, f"DROP TABLE IF EXISTS {sync_metadata_table}")

    # Sync cursor table
    sync_cursor_table = f"{config.table_prefix}sync_cursor"
    upgrade_sql.append(generate_sync_cursor_table_ddl(config))
    downgrade_sql.insert(0, f"DROP TABLE IF EXISTS {sync_cursor_table}")

    return Migration(
        version=1,
        description="Initial schema: entity cache tables, sync metadata, and sync cursor",
        upgrade_sql=upgrade_sql,
        downgrade_sql=downgrade_sql,
    )


def get_all_migrations(config: MigrationConfig) -> list[Migration]:
    """Get all defined migrations.

    Args:
        config: Migration configuration.

    Returns:
        List of all migrations in order.
    """
    return [
        _build_initial_migration(config),
        # Future migrations would be added here
    ]


async def get_current_version(session: Any, config: MigrationConfig) -> int:
    """Get the current migration version from database.

    Queries the migrations tracking table to find the highest applied
    migration version. Returns 0 if no migrations have been applied or
    if the tracking table doesn't exist.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.

    Returns:
        Current migration version (0 if no migrations applied).

    Example:
        >>> async with get_session(sqlspec_config) as session:
        ...     version = await get_current_version(session, migration_config)
        ...     print(f"Current version: {version}")
    """
    # Check if version table exists
    if config.dialect == "postgresql":
        check_sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = $1
            )
        """
        result = await session.fetch_one(check_sql, [config.version_table])
        if not result or not result[0]:
            return 0
    else:
        check_sql = """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """
        result = await session.fetch_one(check_sql, [config.version_table])
        if not result:
            return 0

    # Get max version
    sql = f"SELECT MAX(version) as max_version FROM {config.version_table}"
    result = await session.fetch_one(sql, [])
    if not result or result[0] is None:
        return 0
    return int(result[0])


async def _record_migration(
    session: Any,
    config: MigrationConfig,
    migration: Migration,
) -> None:
    """Record a migration as applied.

    Args:
        session: Database session.
        config: Migration configuration.
        migration: Migration that was applied.
    """
    now = datetime.now(tz=UTC).isoformat()

    if config.dialect == "postgresql":
        sql = f"""
            INSERT INTO {config.version_table} (version, description, applied_at)
            VALUES ($1, $2, $3)
        """
    else:
        sql = f"""
            INSERT INTO {config.version_table} (version, description, applied_at)
            VALUES (?, ?, ?)
        """

    await session.execute(sql, [migration.version, migration.description, now])


async def _remove_migration_record(
    session: Any,
    config: MigrationConfig,
    version: int,
) -> None:
    """Remove a migration record.

    Args:
        session: Database session.
        config: Migration configuration.
        version: Version to remove.
    """
    if config.dialect == "postgresql":
        sql = f"DELETE FROM {config.version_table} WHERE version = $1"
    else:
        sql = f"DELETE FROM {config.version_table} WHERE version = ?"

    await session.execute(sql, [version])


async def create_entity_table(
    session: Any,
    entity_name: str,
    config: MigrationConfig,
) -> None:
    """Create a cache table for an entity type.

    Creates the table if it doesn't exist. Safe to call multiple times.

    Args:
        session: Database session from sqlspec.
        entity_name: CiviCRM entity name (e.g., 'Contact').
        config: Migration configuration.

    Example:
        >>> async with get_session(sqlspec_config) as session:
        ...     await create_entity_table(session, "Contact", migration_config)
    """
    ddl = generate_entity_table_ddl(entity_name, config)
    await session.execute(ddl, [])


async def create_sync_metadata_table(
    session: Any,
    config: MigrationConfig,
) -> None:
    """Create the sync metadata tracking table.

    Creates the table if it doesn't exist. Safe to call multiple times.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.

    Example:
        >>> async with get_session(sqlspec_config) as session:
        ...     await create_sync_metadata_table(session, migration_config)
    """
    ddl = generate_sync_metadata_table_ddl(config)
    await session.execute(ddl, [])


async def upgrade(
    session: Any,
    config: MigrationConfig,
    *,
    target_version: int | None = None,
) -> MigrationResult:
    """Run all pending migrations.

    Applies all migrations that haven't been applied yet, in order.
    Optionally stop at a specific target version.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.
        target_version: Optional version to stop at. If None, applies all.

    Returns:
        MigrationResult with applied versions and any errors.

    Example:
        >>> async with get_session(sqlspec_config) as session:
        ...     result = await upgrade(session, migration_config)
        ...     if result.success:
        ...         print(f"Upgraded to version {result.current_version}")
        ...     else:
        ...         print(f"Errors: {result.errors}")
    """
    result = MigrationResult()

    try:
        current = await get_current_version(session, config)
        result.current_version = current

        migrations = get_all_migrations(config)
        target = target_version if target_version is not None else len(migrations)

        for migration in migrations:
            if migration.version <= current:
                continue
            if migration.version > target:
                break

            try:
                # Execute all upgrade SQL statements
                for sql in migration.upgrade_sql:
                    await session.execute(sql, [])

                # Record migration (but version table needs to exist first)
                if migration.version > 1:
                    await _record_migration(session, config, migration)
                else:
                    # For version 1, the table was just created, so we can record now
                    await _record_migration(session, config, migration)

                result.applied_versions.append(migration.version)
                result.current_version = migration.version

            except Exception as e:  # noqa: BLE001
                result.success = False
                result.errors.append(f"Migration {migration.version} failed: {e}")
                break

    except Exception as e:  # noqa: BLE001
        result.success = False
        result.errors.append(f"Upgrade failed: {e}")

    return result


async def downgrade(
    session: Any,
    config: MigrationConfig,
    target_version: int = 0,
) -> MigrationResult:
    """Rollback migrations to target version.

    Reverts migrations in reverse order until the target version is reached.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.
        target_version: Version to rollback to. Defaults to 0 (remove all).

    Returns:
        MigrationResult with reverted versions and any errors.

    Example:
        >>> async with get_session(sqlspec_config) as session:
        ...     # Rollback to version 1
        ...     result = await downgrade(session, migration_config, target_version=1)
        ...
        ...     # Rollback all migrations
        ...     result = await downgrade(session, migration_config, target_version=0)
    """
    result = MigrationResult()

    try:
        current = await get_current_version(session, config)
        result.current_version = current

        if current <= target_version:
            return result

        migrations = get_all_migrations(config)
        # Get migrations to rollback in reverse order
        to_rollback = [m for m in reversed(migrations) if target_version < m.version <= current]

        for migration in to_rollback:
            try:
                # Execute all downgrade SQL statements
                for sql in migration.downgrade_sql:
                    await session.execute(sql, [])

                # Remove migration record (if version table still exists)
                if migration.version > 1:
                    import contextlib

                    with contextlib.suppress(Exception):
                        await _remove_migration_record(session, config, migration.version)

                result.applied_versions.append(migration.version)
                result.current_version = migration.version - 1

            except Exception as e:  # noqa: BLE001
                result.success = False
                result.errors.append(f"Rollback of migration {migration.version} failed: {e}")
                break

    except Exception as e:  # noqa: BLE001
        result.success = False
        result.errors.append(f"Downgrade failed: {e}")

    return result


async def get_migration_status(
    session: Any,
    config: MigrationConfig,
) -> dict[str, Any]:
    """Get current migration status.

    Returns information about the current migration state including
    applied migrations and pending migrations.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.

    Returns:
        Dictionary with status information:
        - current_version: Current migration version
        - latest_version: Latest available migration version
        - pending_count: Number of pending migrations
        - applied_migrations: List of applied migration info
        - pending_migrations: List of pending migration descriptions
    """
    current = await get_current_version(session, config)
    migrations = get_all_migrations(config)

    applied: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for migration in migrations:
        info = {
            "version": migration.version,
            "description": migration.description,
        }
        if migration.version <= current:
            applied.append(info)
        else:
            pending.append(info)

    return {
        "current_version": current,
        "latest_version": len(migrations),
        "pending_count": len(pending),
        "applied_migrations": applied,
        "pending_migrations": pending,
    }


async def verify_schema(
    session: Any,
    config: MigrationConfig,
) -> dict[str, bool]:
    """Verify that expected tables exist.

    Checks if all expected tables from the migration config exist in the
    database.

    Args:
        session: Database session from sqlspec.
        config: Migration configuration.

    Returns:
        Dictionary mapping table names to existence status.
    """
    tables: dict[str, bool] = {}

    # Check version table
    tables[config.version_table] = await _table_exists(session, config, config.version_table)

    # Check entity tables
    for entity_name in config.include_entities:
        table_name = f"{config.table_prefix}{_camel_to_snake(entity_name)}"
        tables[table_name] = await _table_exists(session, config, table_name)

    # Check sync metadata table
    sync_metadata_table = f"{config.table_prefix}sync_metadata"
    tables[sync_metadata_table] = await _table_exists(session, config, sync_metadata_table)

    # Check sync cursor table
    sync_cursor_table = f"{config.table_prefix}sync_cursor"
    tables[sync_cursor_table] = await _table_exists(session, config, sync_cursor_table)

    return tables


async def _table_exists(
    session: Any,
    config: MigrationConfig,
    table_name: str,
) -> bool:
    """Check if a table exists in the database.

    Args:
        session: Database session.
        config: Migration configuration.
        table_name: Name of the table to check.

    Returns:
        True if table exists, False otherwise.
    """
    if config.dialect == "postgresql":
        sql = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = $1
            )
        """
        result = await session.fetch_one(sql, [table_name])
        return bool(result and result[0])
    sql = """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """
    result = await session.fetch_one(sql, [table_name])
    return result is not None


__all__ = [
    "DatabaseDialect",
    "Migration",
    "MigrationConfig",
    "MigrationResult",
    "create_entity_table",
    "create_sync_metadata_table",
    "downgrade",
    "generate_entity_table_ddl",
    "generate_sync_metadata_table_ddl",
    "generate_table_ddl",
    "generate_version_table_ddl",
    "get_all_migrations",
    "get_current_version",
    "get_migration_status",
    "upgrade",
    "verify_schema",
]
