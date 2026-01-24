"""Configuration for sqlspec integration with civi-py.

Provides configuration dataclass for database adapters used in caching
and persistence features within the civi-py CiviCRM client.

Example:
    >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
    >>>
    >>> # SQLite (default, in-memory)
    >>> config = CiviSQLSpecConfig()
    >>>
    >>> # SQLite with file
    >>> config = CiviSQLSpecConfig(
    ...     adapter="aiosqlite",
    ...     database="/path/to/cache.db",
    ... )
    >>>
    >>> # PostgreSQL
    >>> config = CiviSQLSpecConfig(
    ...     adapter="asyncpg",
    ...     dsn="postgresql://user:pass@localhost:5432/civi_cache",
    ...     pool_min_size=5,
    ...     pool_max_size=20,
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Check if sqlspec is available
try:
    from sqlspec.adapters.aiosqlite import AiosqliteConfig  # type: ignore[import-not-found]
    from sqlspec.adapters.asyncpg import AsyncpgConfig  # type: ignore[import-not-found]

    SQLSPEC_AVAILABLE = True
except ImportError:
    SQLSPEC_AVAILABLE = False

    class AiosqliteConfig:
        """Stub when sqlspec is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = "sqlspec[aiosqlite] is required for SQLite support. Install with: pip install 'civi-py[sqlspec]'"
            raise ImportError(msg)

    class AsyncpgConfig:
        """Stub when sqlspec is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = "sqlspec[asyncpg] is required for PostgreSQL support. Install with: pip install 'civi-py[sqlspec]'"
            raise ImportError(msg)


@dataclass
class CiviSQLSpecConfig:
    """Configuration for sqlspec integration with civi-py.

    Provides a unified configuration interface for both PostgreSQL (asyncpg)
    and SQLite (aiosqlite) database adapters used for caching and persistence.

    Attributes:
        adapter: Database adapter to use. Options are 'asyncpg' for PostgreSQL
            or 'aiosqlite' for SQLite. Defaults to 'aiosqlite'.
        dsn: Database connection string for PostgreSQL (asyncpg adapter).
            Example: 'postgresql://user:pass@localhost:5432/dbname'.
            Ignored when using aiosqlite adapter.
        database: Database file path for SQLite (aiosqlite adapter).
            Use ':memory:' for in-memory database. Defaults to ':memory:'.
            Ignored when using asyncpg adapter.
        pool_min_size: Minimum number of connections in the pool.
            Only applies to asyncpg adapter. Defaults to 1.
        pool_max_size: Maximum number of connections in the pool.
            Only applies to asyncpg adapter. Defaults to 10.
        timeout: Connection timeout in seconds. Applies to both adapters.
            Defaults to 30.0.
        table_prefix: Prefix for cache tables created by civi-py.
            Defaults to 'civi_cache_'.
        auto_create_tables: Whether to automatically create cache tables
            on startup. Defaults to True.

    Example:
        Basic SQLite (in-memory):

        >>> config = CiviSQLSpecConfig()
        >>> adapter_config = config.get_adapter_config()

        SQLite with persistent file:

        >>> config = CiviSQLSpecConfig(
        ...     adapter="aiosqlite",
        ...     database="/var/lib/civi/cache.db",
        ...     timeout=60.0,
        ... )

        PostgreSQL with connection pooling:

        >>> config = CiviSQLSpecConfig(
        ...     adapter="asyncpg",
        ...     dsn="postgresql://civi:secret@db.example.com:5432/civi_cache",
        ...     pool_min_size=5,
        ...     pool_max_size=20,
        ...     timeout=30.0,
        ... )
    """

    adapter: Literal["asyncpg", "aiosqlite"] = "aiosqlite"
    dsn: str | None = None
    database: str = ":memory:"
    pool_min_size: int = 1
    pool_max_size: int = 10
    timeout: float = 30.0
    table_prefix: str = "civi_cache_"
    auto_create_tables: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization.

        Raises:
            ValueError: If asyncpg adapter is selected but no DSN is provided.
        """
        if self.adapter == "asyncpg" and not self.dsn:
            msg = "DSN is required when using the asyncpg adapter"
            raise ValueError(msg)

    def get_adapter_config(self) -> AsyncpgConfig | AiosqliteConfig:
        """Create the appropriate sqlspec adapter configuration.

        Creates and returns a configured adapter instance based on the
        selected adapter type ('asyncpg' or 'aiosqlite').

        Returns:
            The configured adapter: AsyncpgConfig for PostgreSQL or
            AiosqliteConfig for SQLite.

        Raises:
            ImportError: If sqlspec is not installed or the required
                adapter extras are missing.
            ValueError: If an unknown adapter type is configured.

        Example:
            >>> config = CiviSQLSpecConfig(adapter="aiosqlite")
            >>> adapter_config = config.get_adapter_config()
            >>> # Use adapter_config with sqlspec.SQLSpec.add_config()
        """
        if self.adapter == "asyncpg":
            return self._create_asyncpg_config()
        if self.adapter == "aiosqlite":
            return self._create_aiosqlite_config()

        msg = f"Unknown adapter: {self.adapter}"
        raise ValueError(msg)

    def _create_asyncpg_config(self) -> AsyncpgConfig:
        """Create asyncpg adapter configuration.

        Returns:
            Configured AsyncpgConfig instance.

        Raises:
            ImportError: If sqlspec[asyncpg] is not installed.
        """
        # AsyncpgConfig stub raises ImportError if sqlspec not installed
        return AsyncpgConfig(
            pool_config={
                "dsn": self.dsn,
                "min_size": self.pool_min_size,
                "max_size": self.pool_max_size,
                "command_timeout": self.timeout,
            },
        )

    def _create_aiosqlite_config(self) -> AiosqliteConfig:
        """Create aiosqlite adapter configuration.

        Returns:
            Configured AiosqliteConfig instance.

        Raises:
            ImportError: If sqlspec[aiosqlite] is not installed.
        """
        # AiosqliteConfig stub raises ImportError if sqlspec not installed
        return AiosqliteConfig(
            pool_config={
                "database": self.database,
                "timeout": self.timeout,
            },
        )


__all__ = ["CiviSQLSpecConfig"]
