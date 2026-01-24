"""SQLSpec integration for civi-py.

Provides database adapter configuration, repository layer, and migrations
for caching and persistence features using sqlspec with support for
PostgreSQL (asyncpg) and SQLite (aiosqlite).

This module requires the sqlspec optional dependency:

    pip install 'civi-py[sqlspec]'

Quick Start:

    1. SQLite (default, in-memory):

        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
        >>>
        >>> config = CiviSQLSpecConfig()
        >>> adapter_config = config.get_adapter_config()

    2. SQLite with persistent file:

        >>> config = CiviSQLSpecConfig(
        ...     adapter="aiosqlite",
        ...     database="/path/to/cache.db",
        ... )

    3. PostgreSQL with connection pooling:

        >>> config = CiviSQLSpecConfig(
        ...     adapter="asyncpg",
        ...     dsn="postgresql://user:pass@localhost:5432/dbname",
        ...     pool_min_size=5,
        ...     pool_max_size=20,
        ... )

Repository Layer:

    The repository layer provides local caching of CiviCRM entities with
    bidirectional sync capabilities:

        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig, ContactRepository
        >>>
        >>> config = CiviSQLSpecConfig(database="cache.db")
        >>> repo = ContactRepository(config)
        >>>
        >>> async with repo.get_session() as session:
        ...     # Sync contacts from CiviCRM to local DB
        ...     await repo.sync_from_civi(session, client, is_deleted=False)
        ...
        ...     # Query local cache
        ...     contacts = await repo.filter(session, contact_type="Individual")
        ...
        ...     # Sync local changes back to CiviCRM
        ...     await repo.sync_to_civi(session, client)

Migrations:

    The migrations module provides schema management for cache tables:

        >>> from civicrm_py.contrib.sqlspec import MigrationConfig, upgrade
        >>>
        >>> migration_config = MigrationConfig()
        >>>
        >>> async with get_session(sqlspec_config) as session:
        ...     result = await upgrade(session, migration_config)
        ...     print(f"Applied: {result.applied_versions}")

    Or via CLI (requires click):

        $ civi-py db upgrade --database cache.db
        $ civi-py db status --database cache.db
        $ civi-py db downgrade --database cache.db --version 0

Available Repositories:

    - ContactRepository: Cache Contact entities
    - ActivityRepository: Cache Activity entities
    - ContributionRepository: Cache Contribution entities
    - EventRepository: Cache Event entities
    - MembershipRepository: Cache Membership entities
    - CiviRepository: Base class for custom repositories

Migration Classes:

    - MigrationConfig: Configuration for migrations
    - MigrationResult: Result of migration operations
    - upgrade: Apply pending migrations
    - downgrade: Rollback migrations
    - get_current_version: Get current schema version
    - get_migration_status: Get detailed migration status

Configuration Options:

    adapter (str): Database adapter ('asyncpg' or 'aiosqlite')
    dsn (str): PostgreSQL connection string (required for asyncpg)
    database (str): SQLite database path (default: ':memory:')
    pool_min_size (int): Minimum pool connections (asyncpg only)
    pool_max_size (int): Maximum pool connections (asyncpg only)
    timeout (float): Connection timeout in seconds
    table_prefix (str): Prefix for cache tables (default: 'civi_cache_')
    auto_create_tables (bool): Auto-create tables on startup

Environment Variables:

    When using with Litestar or other frameworks, you can configure
    via environment variables:

    - CIVI_SQLSPEC_ADAPTER: 'asyncpg' or 'aiosqlite'
    - CIVI_SQLSPEC_DSN: PostgreSQL connection string
    - CIVI_SQLSPEC_DATABASE: SQLite database path
    - CIVI_SQLSPEC_POOL_MIN_SIZE: Minimum pool size
    - CIVI_SQLSPEC_POOL_MAX_SIZE: Maximum pool size
    - CIVI_SQLSPEC_TIMEOUT: Connection timeout
    - CIVI_SQLSPEC_TABLE_PREFIX: Cache table prefix
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig
    from civicrm_py.contrib.sqlspec.migrations import (
        DatabaseDialect,
        Migration,
        MigrationConfig,
        MigrationResult,
        create_entity_table,
        create_sync_metadata_table,
        downgrade,
        generate_entity_table_ddl,
        generate_sync_metadata_table_ddl,
        generate_table_ddl,
        get_current_version,
        get_migration_status,
        upgrade,
        verify_schema,
    )
    from civicrm_py.contrib.sqlspec.repository import (
        ActivityRepository,
        CiviRepository,
        ContactRepository,
        ContributionRepository,
        EventRepository,
        MembershipRepository,
        SyncMetadata,
        SyncResult,
        SyncStatus,
    )

# Cache for lazy-loaded classes
_cache: dict[str, Any] = {}

# Mapping of attribute names to their module and class name
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Config
    "CiviSQLSpecConfig": ("civicrm_py.contrib.sqlspec.config", "CiviSQLSpecConfig"),
    # Repository base
    "CiviRepository": ("civicrm_py.contrib.sqlspec.repository", "CiviRepository"),
    # Entity repositories
    "ContactRepository": ("civicrm_py.contrib.sqlspec.repository", "ContactRepository"),
    "ActivityRepository": ("civicrm_py.contrib.sqlspec.repository", "ActivityRepository"),
    "ContributionRepository": ("civicrm_py.contrib.sqlspec.repository", "ContributionRepository"),
    "EventRepository": ("civicrm_py.contrib.sqlspec.repository", "EventRepository"),
    "MembershipRepository": ("civicrm_py.contrib.sqlspec.repository", "MembershipRepository"),
    # Sync types
    "SyncStatus": ("civicrm_py.contrib.sqlspec.repository", "SyncStatus"),
    "SyncMetadata": ("civicrm_py.contrib.sqlspec.repository", "SyncMetadata"),
    "SyncResult": ("civicrm_py.contrib.sqlspec.repository", "SyncResult"),
    # Migration types
    "MigrationConfig": ("civicrm_py.contrib.sqlspec.migrations", "MigrationConfig"),
    "MigrationResult": ("civicrm_py.contrib.sqlspec.migrations", "MigrationResult"),
    "Migration": ("civicrm_py.contrib.sqlspec.migrations", "Migration"),
    "DatabaseDialect": ("civicrm_py.contrib.sqlspec.migrations", "DatabaseDialect"),
    # Migration functions
    "upgrade": ("civicrm_py.contrib.sqlspec.migrations", "upgrade"),
    "downgrade": ("civicrm_py.contrib.sqlspec.migrations", "downgrade"),
    "get_current_version": ("civicrm_py.contrib.sqlspec.migrations", "get_current_version"),
    "get_migration_status": ("civicrm_py.contrib.sqlspec.migrations", "get_migration_status"),
    "verify_schema": ("civicrm_py.contrib.sqlspec.migrations", "verify_schema"),
    "create_entity_table": ("civicrm_py.contrib.sqlspec.migrations", "create_entity_table"),
    "create_sync_metadata_table": ("civicrm_py.contrib.sqlspec.migrations", "create_sync_metadata_table"),
    "generate_entity_table_ddl": ("civicrm_py.contrib.sqlspec.migrations", "generate_entity_table_ddl"),
    "generate_sync_metadata_table_ddl": ("civicrm_py.contrib.sqlspec.migrations", "generate_sync_metadata_table_ddl"),
    "generate_table_ddl": ("civicrm_py.contrib.sqlspec.migrations", "generate_table_ddl"),
}


def __getattr__(name: str) -> object:
    """Lazy import of sqlspec integration classes.

    This allows the module to be imported even when sqlspec is not
    installed, with errors only raised when actually trying to use
    the classes.

    Args:
        name: Attribute name to retrieve.

    Returns:
        The requested class.

    Raises:
        AttributeError: If the requested attribute is not exported.
        ImportError: If sqlspec is not installed (when accessing repository classes).
    """
    if name in _cache:
        return _cache[name]

    if name in _LAZY_IMPORTS:
        module_path, class_name = _LAZY_IMPORTS[name]
        try:
            import importlib

            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            _cache[name] = cls
        except ImportError as e:
            # Provide helpful error message
            if "sqlspec" in str(e):
                msg = f"sqlspec is required for {name}. Install with: pip install 'civi-py[sqlspec]'"
                raise ImportError(msg) from e
            raise
        else:
            return cls

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return list of available attributes for IDE support."""
    return [*_LAZY_IMPORTS.keys(), "__all__", "__getattr__", "__dir__"]


__all__ = [
    "ActivityRepository",
    "CiviRepository",
    "CiviSQLSpecConfig",
    "ContactRepository",
    "ContributionRepository",
    "DatabaseDialect",
    "EventRepository",
    "MembershipRepository",
    "Migration",
    "MigrationConfig",
    "MigrationResult",
    "SyncMetadata",
    "SyncResult",
    "SyncStatus",
    "create_entity_table",
    "create_sync_metadata_table",
    "downgrade",
    "generate_entity_table_ddl",
    "generate_sync_metadata_table_ddl",
    "generate_table_ddl",
    "get_current_version",
    "get_migration_status",
    "upgrade",
    "verify_schema",
]
