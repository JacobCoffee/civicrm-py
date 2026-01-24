"""CLI commands for sqlspec database migrations.

Provides command-line interface for managing cache database schema using Click.
These commands can be integrated with larger CLI applications or used standalone.

This module requires both sqlspec and click optional dependencies:

    pip install 'civi-py[sqlspec,cli]'

Usage:
    The commands can be invoked via the civi-py CLI or programmatically:

    # Via CLI (if installed as entry point)
    $ civi-py db upgrade
    $ civi-py db downgrade --version 1
    $ civi-py db status

    # Programmatically
    >>> from civicrm_py.contrib.sqlspec.cli import db_group
    >>> import click
    >>> @click.group()
    ... def cli():
    ...     pass
    >>> cli.add_command(db_group, name="db")

Example:
    >>> from civicrm_py.contrib.sqlspec.cli import upgrade_command
    >>> import asyncio
    >>>
    >>> # Run upgrade programmatically
    >>> asyncio.run(upgrade_command.main([], standalone_mode=False))
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

# Check if click is available
try:
    import click

    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False

    class click:
        """Stub when click is not installed."""

        @staticmethod
        def group(*args: Any, **kwargs: Any) -> Any:
            """Stub for click.group decorator."""

            def decorator(f: Any) -> Any:
                return f

            return decorator

        @staticmethod
        def command(*args: Any, **kwargs: Any) -> Any:
            """Stub for click.command decorator."""

            def decorator(f: Any) -> Any:
                return f

            return decorator

        @staticmethod
        def option(*args: Any, **kwargs: Any) -> Any:
            """Stub for click.option decorator."""

            def decorator(f: Any) -> Any:
                return f

            return decorator

        @staticmethod
        def echo(*args: Any, **kwargs: Any) -> None:
            """Stub for click.echo."""
            msg = "click is required for CLI commands. Install with: pip install 'civi-py[cli]'"
            raise ImportError(msg)

        @staticmethod
        def style(*args: Any, **kwargs: Any) -> str:
            """Stub for click.style."""
            msg = "click is required for CLI commands. Install with: pip install 'civi-py[cli]'"
            raise ImportError(msg)

        @staticmethod
        def confirm(*args: Any, **kwargs: Any) -> bool:
            """Stub for click.confirm."""
            msg = "click is required for CLI commands. Install with: pip install 'civi-py[cli]'"
            raise ImportError(msg)

        class Choice:
            """Stub for click.Choice."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                msg = "click is required for CLI commands. Install with: pip install 'civi-py[cli]'"
                raise ImportError(msg)


# Check if sqlspec is available
try:
    from sqlspec import SQLSpec  # type: ignore[import-not-found]

    SQLSPEC_AVAILABLE = True
except ImportError:
    SQLSPEC_AVAILABLE = False

    class SQLSpec:
        """Stub when sqlspec is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = "sqlspec is required for database commands. Install with: pip install 'civi-py[sqlspec]'"
            raise ImportError(msg)

        def add_config(self, *args: Any, **kwargs: Any) -> None:
            """Stub for SQLSpec.add_config."""

        def get_session(self, *args: Any, **kwargs: Any) -> Any:
            """Stub for SQLSpec.get_session."""


def _check_click_available() -> None:
    """Check if click is available.

    Raises:
        ImportError: If click is not installed.
    """
    if not CLICK_AVAILABLE:
        msg = "click is required for CLI commands. Install with: pip install 'civi-py[cli]'"
        raise ImportError(msg)


def _check_sqlspec_available() -> None:
    """Check if sqlspec is available.

    Raises:
        ImportError: If sqlspec is not installed.
    """
    if not SQLSPEC_AVAILABLE:
        msg = "sqlspec is required for database commands. Install with: pip install 'civi-py[sqlspec]'"
        raise ImportError(msg)


def _get_config_from_options(
    adapter: str,
    database: str | None,
    dsn: str | None,
    table_prefix: str,
    dialect: str,
) -> tuple[Any, Any]:
    """Create config objects from CLI options.

    Args:
        adapter: Database adapter name.
        database: SQLite database path.
        dsn: PostgreSQL DSN.
        table_prefix: Table prefix.
        dialect: SQL dialect.

    Returns:
        Tuple of (CiviSQLSpecConfig, MigrationConfig).
    """
    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig
    from civicrm_py.contrib.sqlspec.migrations import MigrationConfig

    sqlspec_config = CiviSQLSpecConfig(
        adapter=adapter,  # type: ignore[arg-type]
        database=database or ":memory:",
        dsn=dsn,
        table_prefix=table_prefix,
    )

    migration_config = MigrationConfig(
        table_prefix=table_prefix,
        dialect=dialect,  # type: ignore[arg-type]
    )

    return sqlspec_config, migration_config


async def _run_upgrade(
    sqlspec_config: Any,
    migration_config: Any,
    target_version: int | None,
) -> dict[str, Any]:
    """Run database upgrade.

    Args:
        sqlspec_config: SQLSpec configuration.
        migration_config: Migration configuration.
        target_version: Target version or None for latest.

    Returns:
        Migration result as dictionary.
    """
    from civicrm_py.contrib.sqlspec.migrations import upgrade

    # SQLSpec stub raises ImportError if sqlspec not installed
    spec = SQLSpec()
    spec.add_config(sqlspec_config.get_adapter_config())

    async with spec.get_session() as session:
        result = await upgrade(session, migration_config, target_version=target_version)
        return {
            "success": result.success,
            "applied_versions": result.applied_versions,
            "current_version": result.current_version,
            "errors": result.errors,
        }


async def _run_downgrade(
    sqlspec_config: Any,
    migration_config: Any,
    target_version: int,
) -> dict[str, Any]:
    """Run database downgrade.

    Args:
        sqlspec_config: SQLSpec configuration.
        migration_config: Migration configuration.
        target_version: Target version to downgrade to.

    Returns:
        Migration result as dictionary.
    """
    from civicrm_py.contrib.sqlspec.migrations import downgrade

    # SQLSpec stub raises ImportError if sqlspec not installed
    spec = SQLSpec()
    spec.add_config(sqlspec_config.get_adapter_config())

    async with spec.get_session() as session:
        result = await downgrade(session, migration_config, target_version=target_version)
        return {
            "success": result.success,
            "applied_versions": result.applied_versions,
            "current_version": result.current_version,
            "errors": result.errors,
        }


async def _get_status(
    sqlspec_config: Any,
    migration_config: Any,
) -> dict[str, Any]:
    """Get database migration status.

    Args:
        sqlspec_config: SQLSpec configuration.
        migration_config: Migration configuration.

    Returns:
        Status information dictionary.
    """
    from civicrm_py.contrib.sqlspec.migrations import get_migration_status, verify_schema

    # SQLSpec stub raises ImportError if sqlspec not installed
    spec = SQLSpec()
    spec.add_config(sqlspec_config.get_adapter_config())

    async with spec.get_session() as session:
        status = await get_migration_status(session, migration_config)
        tables = await verify_schema(session, migration_config)
        return {
            **status,
            "tables": tables,
        }


def _create_db_group() -> object:
    """Create the database CLI command group.

    Returns:
        Click command group.
    """
    _check_click_available()
    # click stub raises ImportError if click not installed, but _check_click_available
    # already verified it's available, so this will use the real click module

    @click.group(name="db")
    def db_group() -> None:
        """Database migration commands for civi-py cache tables.

        Manage the local cache database schema used to persist CiviCRM entities
        for offline access and improved query performance.
        """

    @db_group.command(name="upgrade")
    @click.option(
        "--adapter",
        type=click.Choice(["aiosqlite", "asyncpg"]),
        default="aiosqlite",
        help="Database adapter to use.",
    )
    @click.option(
        "--database",
        "-d",
        type=str,
        default=None,
        help="SQLite database file path (for aiosqlite adapter).",
    )
    @click.option(
        "--dsn",
        type=str,
        default=None,
        envvar="CIVI_SQLSPEC_DSN",
        help="PostgreSQL connection string (for asyncpg adapter).",
    )
    @click.option(
        "--table-prefix",
        type=str,
        default="civi_cache_",
        help="Prefix for cache table names.",
    )
    @click.option(
        "--version",
        "-v",
        type=int,
        default=None,
        help="Target version (default: latest).",
    )
    def upgrade_command(
        adapter: str,
        database: str | None,
        dsn: str | None,
        table_prefix: str,
        version: int | None,
    ) -> None:
        """Run pending database migrations.

        Applies all migrations that haven't been applied yet to bring the
        database schema up to date. Optionally specify a target version.

        Examples:
            # Upgrade to latest
            civi-py db upgrade --database cache.db

            # Upgrade PostgreSQL
            civi-py db upgrade --adapter asyncpg --dsn postgresql://localhost/civi

            # Upgrade to specific version
            civi-py db upgrade --database cache.db --version 1
        """
        _check_sqlspec_available()

        dialect = "postgresql" if adapter == "asyncpg" else "sqlite"
        sqlspec_config, migration_config = _get_config_from_options(
            adapter=adapter,
            database=database,
            dsn=dsn,
            table_prefix=table_prefix,
            dialect=dialect,
        )

        click.echo("Running database migrations...")

        try:
            result = asyncio.run(_run_upgrade(sqlspec_config, migration_config, version))

            if result["success"]:
                if result["applied_versions"]:
                    click.echo(
                        click.style("SUCCESS: ", fg="green") + f"Applied migrations: {result['applied_versions']}",
                    )
                else:
                    click.echo(click.style("OK: ", fg="green") + "Database is already up to date.")
                click.echo(f"Current version: {result['current_version']}")
            else:
                click.echo(click.style("ERROR: ", fg="red") + "Migration failed.")
                for error in result["errors"]:
                    click.echo(f"  - {error}")
                sys.exit(1)

        except Exception as e:  # noqa: BLE001
            click.echo(click.style("ERROR: ", fg="red") + str(e))
            sys.exit(1)

    @db_group.command(name="downgrade")
    @click.option(
        "--adapter",
        type=click.Choice(["aiosqlite", "asyncpg"]),
        default="aiosqlite",
        help="Database adapter to use.",
    )
    @click.option(
        "--database",
        "-d",
        type=str,
        default=None,
        help="SQLite database file path (for aiosqlite adapter).",
    )
    @click.option(
        "--dsn",
        type=str,
        default=None,
        envvar="CIVI_SQLSPEC_DSN",
        help="PostgreSQL connection string (for asyncpg adapter).",
    )
    @click.option(
        "--table-prefix",
        type=str,
        default="civi_cache_",
        help="Prefix for cache table names.",
    )
    @click.option(
        "--version",
        "-v",
        type=int,
        default=0,
        help="Target version to downgrade to (default: 0, removes all).",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        help="Skip confirmation prompt.",
    )
    def downgrade_command(
        adapter: str,
        database: str | None,
        dsn: str | None,
        table_prefix: str,
        version: int,
        *,
        yes: bool,
    ) -> None:
        """Rollback database migrations.

        Reverts migrations in reverse order until the target version is reached.
        Use with caution as this will delete cache tables and data.

        Examples:
            # Rollback to version 1
            civi-py db downgrade --database cache.db --version 1

            # Remove all migrations (reset)
            civi-py db downgrade --database cache.db --version 0 --yes
        """
        _check_sqlspec_available()

        if not yes and not click.confirm(
            f"This will rollback migrations to version {version}. Cache data may be lost. Continue?",
        ):
            click.echo("Aborted.")
            return

        dialect = "postgresql" if adapter == "asyncpg" else "sqlite"
        sqlspec_config, migration_config = _get_config_from_options(
            adapter=adapter,
            database=database,
            dsn=dsn,
            table_prefix=table_prefix,
            dialect=dialect,
        )

        click.echo(f"Rolling back migrations to version {version}...")

        try:
            result = asyncio.run(_run_downgrade(sqlspec_config, migration_config, version))

            if result["success"]:
                if result["applied_versions"]:
                    click.echo(
                        click.style("SUCCESS: ", fg="green") + f"Rolled back migrations: {result['applied_versions']}",
                    )
                else:
                    click.echo(click.style("OK: ", fg="green") + "No migrations to rollback.")
                click.echo(f"Current version: {result['current_version']}")
            else:
                click.echo(click.style("ERROR: ", fg="red") + "Rollback failed.")
                for error in result["errors"]:
                    click.echo(f"  - {error}")
                sys.exit(1)

        except Exception as e:  # noqa: BLE001
            click.echo(click.style("ERROR: ", fg="red") + str(e))
            sys.exit(1)

    @db_group.command(name="status")
    @click.option(
        "--adapter",
        type=click.Choice(["aiosqlite", "asyncpg"]),
        default="aiosqlite",
        help="Database adapter to use.",
    )
    @click.option(
        "--database",
        "-d",
        type=str,
        default=None,
        help="SQLite database file path (for aiosqlite adapter).",
    )
    @click.option(
        "--dsn",
        type=str,
        default=None,
        envvar="CIVI_SQLSPEC_DSN",
        help="PostgreSQL connection string (for asyncpg adapter).",
    )
    @click.option(
        "--table-prefix",
        type=str,
        default="civi_cache_",
        help="Prefix for cache table names.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Output as JSON.",
    )
    def status_command(
        adapter: str,
        database: str | None,
        dsn: str | None,
        table_prefix: str,
        *,
        as_json: bool,
    ) -> None:
        """Show database migration status.

        Displays the current migration version, pending migrations,
        and table existence status.

        Examples:
            # Check status
            civi-py db status --database cache.db

            # Output as JSON
            civi-py db status --database cache.db --json
        """
        _check_sqlspec_available()

        dialect = "postgresql" if adapter == "asyncpg" else "sqlite"
        sqlspec_config, migration_config = _get_config_from_options(
            adapter=adapter,
            database=database,
            dsn=dsn,
            table_prefix=table_prefix,
            dialect=dialect,
        )

        try:
            status = asyncio.run(_get_status(sqlspec_config, migration_config))

            if as_json:
                import json

                click.echo(json.dumps(status, indent=2))
            else:
                click.echo("Database Migration Status")
                click.echo("=" * 40)
                click.echo(f"Current version: {status['current_version']}")
                click.echo(f"Latest version:  {status['latest_version']}")
                click.echo(f"Pending count:   {status['pending_count']}")
                click.echo()

                if status["applied_migrations"]:
                    click.echo("Applied Migrations:")
                    for m in status["applied_migrations"]:
                        click.echo(f"  [{m['version']}] {m['description']}")
                else:
                    click.echo("Applied Migrations: None")
                click.echo()

                if status["pending_migrations"]:
                    click.echo(click.style("Pending Migrations:", fg="yellow"))
                    for m in status["pending_migrations"]:
                        click.echo(f"  [{m['version']}] {m['description']}")
                else:
                    click.echo(click.style("Pending Migrations: None", fg="green"))
                click.echo()

                click.echo("Tables:")
                for table_name, exists in status["tables"].items():
                    status_str = click.style("EXISTS", fg="green") if exists else click.style("MISSING", fg="red")
                    click.echo(f"  {table_name}: {status_str}")

        except Exception as e:  # noqa: BLE001
            click.echo(click.style("ERROR: ", fg="red") + str(e))
            sys.exit(1)

    @db_group.command(name="init")
    @click.option(
        "--adapter",
        type=click.Choice(["aiosqlite", "asyncpg"]),
        default="aiosqlite",
        help="Database adapter to use.",
    )
    @click.option(
        "--database",
        "-d",
        type=str,
        default="civi_cache.db",
        help="SQLite database file path.",
    )
    @click.option(
        "--dsn",
        type=str,
        default=None,
        envvar="CIVI_SQLSPEC_DSN",
        help="PostgreSQL connection string.",
    )
    @click.option(
        "--table-prefix",
        type=str,
        default="civi_cache_",
        help="Prefix for cache table names.",
    )
    def init_command(
        adapter: str,
        database: str,
        dsn: str | None,
        table_prefix: str,
    ) -> None:
        """Initialize a new cache database.

        Creates a new cache database with all migrations applied.
        This is a convenience command equivalent to 'upgrade'.

        Examples:
            # Create new SQLite cache database
            civi-py db init --database ./cache.db

            # Create PostgreSQL cache schema
            civi-py db init --adapter asyncpg --dsn postgresql://localhost/civi
        """
        _check_sqlspec_available()

        dialect = "postgresql" if adapter == "asyncpg" else "sqlite"
        sqlspec_config, migration_config = _get_config_from_options(
            adapter=adapter,
            database=database,
            dsn=dsn,
            table_prefix=table_prefix,
            dialect=dialect,
        )

        click.echo("Initializing cache database...")
        if adapter == "aiosqlite":
            click.echo(f"Database: {database}")
        else:
            click.echo(f"DSN: {dsn}")

        try:
            result = asyncio.run(_run_upgrade(sqlspec_config, migration_config, None))

            if result["success"]:
                click.echo(click.style("SUCCESS: ", fg="green") + "Database initialized.")
                click.echo(f"Applied migrations: {result['applied_versions']}")
                click.echo(f"Current version: {result['current_version']}")
            else:
                click.echo(click.style("ERROR: ", fg="red") + "Initialization failed.")
                for error in result["errors"]:
                    click.echo(f"  - {error}")
                sys.exit(1)

        except Exception as e:  # noqa: BLE001
            click.echo(click.style("ERROR: ", fg="red") + str(e))
            sys.exit(1)

    return db_group


# Create the command group lazily to avoid import errors
def get_db_group() -> Any:
    """Get the database CLI command group.

    Returns:
        Click command group for database operations.

    Raises:
        ImportError: If click is not installed.
    """
    return _create_db_group()


# For direct imports, we use a lazy property
class _LazyDBGroup:
    """Lazy loader for db_group to avoid import errors."""

    _group: Any = None

    def __getattr__(self, name: str) -> Any:
        if self._group is None:
            self._group = _create_db_group()
        return getattr(self._group, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._group is None:
            self._group = _create_db_group()
        return self._group(*args, **kwargs)


# This allows `from civicrm_py.contrib.sqlspec.cli import db_group`
# to work, but defers the click import until actually used
db_group = _LazyDBGroup()


__all__ = [
    "db_group",
    "get_db_group",
]
