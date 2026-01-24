"""SQLSpec integration for the Litestar CiviCRM plugin.

Enables local database caching alongside the CiviCRM API using sqlspec.
This integration is completely optional and degrades gracefully when
sqlspec is not installed.

Example:
    >>> from litestar import Litestar
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    >>> from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
    >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
    >>>
    >>> config = CiviPluginConfig(
    ...     sqlspec=SQLSpecPluginConfig(
    ...         enabled=True,
    ...         sqlspec_config=CiviSQLSpecConfig(
    ...             adapter="aiosqlite",
    ...             database="civi_cache.db",
    ...         ),
    ...         auto_run_migrations=True,
    ...     ),
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])

Using repositories in handlers:
    >>> from litestar import get
    >>> from civicrm_py.contrib.litestar.sqlspec_integration import (
    ...     provide_contact_repository,
    ... )
    >>>
    >>> @get("/cached-contacts")
    ... async def list_cached_contacts(
    ...     contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
    ... ) -> list[dict]:
    ...     async with contact_repository.get_session() as session:
    ...         contacts = await contact_repository.filter(session, is_deleted=False)
    ...         return [c.to_dict() for c in contacts]
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from litestar import Litestar
    from litestar.config.app import AppConfig
    from litestar.datastructures import State

    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig
    from civicrm_py.contrib.sqlspec.repository import (
        ActivityRepository,
        ContactRepository,
        ContributionRepository,
        EventRepository,
        MembershipRepository,
    )

logger = logging.getLogger("civicrm_py.contrib.litestar.sqlspec")

# Key used to store the SQLSpec state in app.state
SQLSPEC_STATE_KEY = "_civi_sqlspec"

# Key used to store correlation ID in request state
CORRELATION_ID_KEY = "_civi_correlation_id"


def _check_sqlspec_available() -> bool:
    """Check if sqlspec is available.

    Returns:
        True if sqlspec is installed, False otherwise.
    """
    try:
        import sqlspec  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    else:
        return True


SQLSPEC_AVAILABLE = _check_sqlspec_available()


@dataclass
class SQLSpecPluginConfig:
    """Configuration for SQLSpec integration with CiviPlugin.

    Controls the optional local database caching layer that can work
    alongside the CiviCRM API for improved performance and offline access.

    Attributes:
        enabled: Whether SQLSpec integration is enabled. When False,
            all SQLSpec features are disabled even if sqlspec is installed.
        sqlspec_config: Configuration for the sqlspec adapter. If None and
            enabled is True, a default in-memory SQLite config will be created.
        auto_run_migrations: Whether to run database migrations on startup.
            Creates cache tables automatically.
        provide_repositories: Whether to register repository DI providers
            for automatic injection in route handlers.
        enable_correlation_tracking: Enable correlation ID tracking across
            CiviClient API calls and sqlspec database operations.
        correlation_header: HTTP header name for incoming correlation IDs.
            If a request includes this header, its value will be used.

    Example:
        Basic SQLite caching:

        >>> config = SQLSpecPluginConfig(
        ...     enabled=True,
        ...     auto_run_migrations=True,
        ... )

        PostgreSQL with connection pooling:

        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
        >>>
        >>> config = SQLSpecPluginConfig(
        ...     enabled=True,
        ...     sqlspec_config=CiviSQLSpecConfig(
        ...         adapter="asyncpg",
        ...         dsn="postgresql://user:pass@localhost:5432/civi_cache",
        ...         pool_min_size=5,
        ...         pool_max_size=20,
        ...     ),
        ...     auto_run_migrations=True,
        ... )

        Disable auto-registration of DI providers:

        >>> config = SQLSpecPluginConfig(
        ...     enabled=True,
        ...     provide_repositories=False,  # Manual DI setup
        ... )
    """

    enabled: bool = False
    sqlspec_config: CiviSQLSpecConfig | None = None
    auto_run_migrations: bool = True
    provide_repositories: bool = True
    enable_correlation_tracking: bool = False
    correlation_header: str = "X-Correlation-ID"

    def __post_init__(self) -> None:
        """Validate configuration after initialization.

        Raises:
            ImportError: If enabled but sqlspec is not installed.
        """
        if self.enabled and not SQLSPEC_AVAILABLE:
            msg = (
                "SQLSpec integration is enabled but sqlspec is not installed. "
                "Install with: pip install 'civi-py[sqlspec]'"
            )
            raise ImportError(msg)


@dataclass
class SQLSpecState:
    """Internal state for SQLSpec integration.

    Stores initialized repository instances and configuration
    for use during request handling.

    Attributes:
        config: The SQLSpec configuration.
        repositories: Dictionary mapping repository names to instances.
        initialized: Whether migrations have been run.
    """

    config: CiviSQLSpecConfig
    repositories: dict[str, Any] = field(default_factory=dict)
    initialized: bool = False


# =============================================================================
# Lifecycle Handlers
# =============================================================================


async def initialize_sqlspec(app: Litestar, config: SQLSpecPluginConfig) -> None:
    """Initialize SQLSpec on application startup.

    Creates repository instances, optionally runs migrations, and stores
    state in the application for dependency injection.

    Args:
        app: The Litestar application instance.
        config: SQLSpec plugin configuration.
    """
    if not config.enabled:
        logger.debug("SQLSpec integration is disabled")
        return

    if not SQLSPEC_AVAILABLE:
        logger.warning("SQLSpec integration enabled but sqlspec not installed")
        return

    # Get or create sqlspec config
    sqlspec_config = config.sqlspec_config
    if sqlspec_config is None:
        from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig

        sqlspec_config = CiviSQLSpecConfig()
        logger.debug("Using default in-memory SQLite config")

    # Create state
    state = SQLSpecState(config=sqlspec_config)

    # Create repository instances
    from civicrm_py.contrib.sqlspec.repository import (
        ActivityRepository,
        ContactRepository,
        ContributionRepository,
        EventRepository,
        MembershipRepository,
    )

    state.repositories["contact"] = ContactRepository(sqlspec_config)
    state.repositories["activity"] = ActivityRepository(sqlspec_config)
    state.repositories["contribution"] = ContributionRepository(sqlspec_config)
    state.repositories["event"] = EventRepository(sqlspec_config)
    state.repositories["membership"] = MembershipRepository(sqlspec_config)

    # Run migrations if enabled
    if config.auto_run_migrations:
        logger.info("Running SQLSpec migrations")
        await _run_migrations(state)
        state.initialized = True

    # Store state
    setattr(app.state, SQLSPEC_STATE_KEY, state)

    logger.info(
        "SQLSpec initialized with %s adapter",
        sqlspec_config.adapter,
    )


async def cleanup_sqlspec(app: Litestar) -> None:
    """Clean up SQLSpec on application shutdown.

    Releases resources and removes state from application.

    Args:
        app: The Litestar application instance.
    """
    state: SQLSpecState | None = getattr(app.state, SQLSPEC_STATE_KEY, None)
    if state is None:
        return

    # Clean up repositories (nothing special needed currently)
    state.repositories.clear()

    # Remove state
    delattr(app.state, SQLSPEC_STATE_KEY)
    logger.info("SQLSpec cleanup complete")


async def _run_migrations(state: SQLSpecState) -> None:
    """Run database migrations for all repositories.

    Creates cache tables in the database if they don't exist.

    Args:
        state: SQLSpec state with repository instances.
    """
    # Get any repository to run table creation
    # Tables are created lazily on first session access
    for name, repo in state.repositories.items():
        try:
            async with repo.get_session():
                # Session context manager handles table creation
                pass
            logger.debug("Initialized tables for %s repository", name)
        except Exception:
            logger.exception("Failed to initialize tables for %s repository", name)
            raise


# =============================================================================
# Dependency Providers
# =============================================================================


def _get_sqlspec_state(state: State) -> SQLSpecState:
    """Get SQLSpec state from application state.

    Args:
        state: Litestar application state.

    Returns:
        SQLSpecState instance.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
    """
    sqlspec_state: SQLSpecState | None = state.get(SQLSPEC_STATE_KEY)
    if sqlspec_state is None:
        msg = (
            f"SQLSpec state not found (key: {SQLSPEC_STATE_KEY!r}). "
            "Ensure CiviPlugin is configured with SQLSpec enabled and "
            "startup completed successfully."
        )
        raise RuntimeError(msg)
    return sqlspec_state


async def provide_sqlspec_session(state: State) -> AsyncIterator[Any]:
    """Provide a sqlspec session for request handlers.

    Yields a database session that can be used for repository operations.
    The session is automatically cleaned up after the request.

    Args:
        state: Litestar application state.

    Yields:
        Database session from sqlspec adapter.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
        ImportError: If sqlspec is not installed.

    Example:
        >>> from typing import Annotated
        >>> from litestar import get
        >>> from litestar.params import Dependency
        >>>
        >>> @get("/contacts")
        ... async def list_contacts(
        ...     session: Annotated[Any, Dependency(skip_validation=True)],
        ...     contact_repository: ContactRepository,
        ... ) -> list[dict]:
        ...     contacts = await contact_repository.filter(session, is_deleted=False)
        ...     return [c.to_dict() for c in contacts]
    """
    if not SQLSPEC_AVAILABLE:
        msg = "sqlspec is required. Install with: pip install 'civi-py[sqlspec]'"
        raise ImportError(msg)

    sqlspec_state = _get_sqlspec_state(state)

    # Get a session from any repository (they share the same config)
    contact_repo = sqlspec_state.repositories.get("contact")
    if contact_repo is None:
        msg = "No repositories initialized"
        raise RuntimeError(msg)

    async with contact_repo.get_session() as session:
        yield session


async def provide_contact_repository(state: State) -> ContactRepository:
    """Provide ContactRepository with configured session.

    Args:
        state: Litestar application state.

    Returns:
        ContactRepository instance configured for the application.

    Raises:
        RuntimeError: If SQLSpec is not initialized.

    Example:
        >>> from typing import Annotated
        >>> from litestar import get
        >>> from litestar.params import Dependency
        >>>
        >>> @get("/cached-contacts")
        ... async def list_cached(
        ...     contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
        ... ) -> list[dict]:
        ...     async with contact_repository.get_session() as session:
        ...         contacts = await contact_repository.filter(session, is_deleted=False)
        ...         return [c.to_dict() for c in contacts]
    """
    sqlspec_state = _get_sqlspec_state(state)
    repo = sqlspec_state.repositories.get("contact")
    if repo is None:
        msg = "ContactRepository not initialized"
        raise RuntimeError(msg)
    return repo


async def provide_activity_repository(state: State) -> ActivityRepository:
    """Provide ActivityRepository with configured session.

    Args:
        state: Litestar application state.

    Returns:
        ActivityRepository instance configured for the application.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
    """
    sqlspec_state = _get_sqlspec_state(state)
    repo = sqlspec_state.repositories.get("activity")
    if repo is None:
        msg = "ActivityRepository not initialized"
        raise RuntimeError(msg)
    return repo


async def provide_contribution_repository(state: State) -> ContributionRepository:
    """Provide ContributionRepository with configured session.

    Args:
        state: Litestar application state.

    Returns:
        ContributionRepository instance configured for the application.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
    """
    sqlspec_state = _get_sqlspec_state(state)
    repo = sqlspec_state.repositories.get("contribution")
    if repo is None:
        msg = "ContributionRepository not initialized"
        raise RuntimeError(msg)
    return repo


async def provide_event_repository(state: State) -> EventRepository:
    """Provide EventRepository with configured session.

    Args:
        state: Litestar application state.

    Returns:
        EventRepository instance configured for the application.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
    """
    sqlspec_state = _get_sqlspec_state(state)
    repo = sqlspec_state.repositories.get("event")
    if repo is None:
        msg = "EventRepository not initialized"
        raise RuntimeError(msg)
    return repo


async def provide_membership_repository(state: State) -> MembershipRepository:
    """Provide MembershipRepository with configured session.

    Args:
        state: Litestar application state.

    Returns:
        MembershipRepository instance configured for the application.

    Raises:
        RuntimeError: If SQLSpec is not initialized.
    """
    sqlspec_state = _get_sqlspec_state(state)
    repo = sqlspec_state.repositories.get("membership")
    if repo is None:
        msg = "MembershipRepository not initialized"
        raise RuntimeError(msg)
    return repo


def get_sqlspec_dependency_providers() -> dict[str, Any]:
    """Get dependency provider mappings for SQLSpec repositories.

    Returns a dictionary mapping dependency names to their provider
    callables for use with Litestar's dependency injection.

    Returns:
        Dictionary with repository providers mapped by name.

    Example:
        >>> from litestar import Litestar
        >>> from civicrm_py.contrib.litestar.sqlspec_integration import (
        ...     get_sqlspec_dependency_providers,
        ... )
        >>>
        >>> # Manual registration (usually done automatically by CiviPlugin)
        >>> app = Litestar(
        ...     route_handlers=[...],
        ...     dependencies=get_sqlspec_dependency_providers(),
        ... )
    """
    from litestar.di import Provide

    return {
        "sqlspec_session": Provide(provide_sqlspec_session),
        "contact_repository": Provide(provide_contact_repository),
        "activity_repository": Provide(provide_activity_repository),
        "contribution_repository": Provide(provide_contribution_repository),
        "event_repository": Provide(provide_event_repository),
        "membership_repository": Provide(provide_membership_repository),
    }


# =============================================================================
# Correlation ID Middleware
# =============================================================================


def generate_correlation_id() -> str:
    """Generate a new correlation ID.

    Returns:
        UUID4 string for request correlation.
    """
    return str(uuid.uuid4())


def get_correlation_id(state: State) -> str | None:
    """Get correlation ID from request state.

    Args:
        state: Litestar request state.

    Returns:
        Correlation ID if set, None otherwise.
    """
    return state.get(CORRELATION_ID_KEY)


def set_correlation_id(state: State, correlation_id: str) -> None:
    """Set correlation ID in request state.

    Args:
        state: Litestar request state.
        correlation_id: Correlation ID to set.
    """
    setattr(state, CORRELATION_ID_KEY, correlation_id)


# =============================================================================
# SQLSpec Plugin (Standalone)
# =============================================================================


class SQLSpecPlugin:
    """Standalone Litestar plugin for SQLSpec integration.

    Can be used alongside CiviPlugin or independently for applications
    that only need the caching layer without full CiviCRM integration.

    This plugin:
    - Initializes SQLSpec repositories on application startup
    - Runs migrations if configured
    - Registers dependency providers for repository injection
    - Cleans up on application shutdown

    Attributes:
        config: SQLSpec plugin configuration.

    Example:
        Use with CiviPlugin:

        >>> from litestar import Litestar
        >>> from civicrm_py.contrib.litestar import CiviPlugin
        >>> from civicrm_py.contrib.litestar.sqlspec_integration import (
        ...     SQLSpecPlugin,
        ...     SQLSpecPluginConfig,
        ... )
        >>>
        >>> app = Litestar(
        ...     plugins=[
        ...         CiviPlugin(),
        ...         SQLSpecPlugin(SQLSpecPluginConfig(enabled=True)),
        ...     ],
        ... )

        Standalone usage:

        >>> app = Litestar(
        ...     route_handlers=[...],
        ...     plugins=[SQLSpecPlugin(SQLSpecPluginConfig(enabled=True))],
        ... )
    """

    __slots__ = ("_config",)

    def __init__(self, config: SQLSpecPluginConfig | None = None) -> None:
        """Initialize the SQLSpec plugin.

        Args:
            config: Plugin configuration. If None, uses disabled default.
        """
        self._config = config or SQLSpecPluginConfig()

    @property
    def config(self) -> SQLSpecPluginConfig:
        """Get the plugin configuration."""
        return self._config

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure Litestar application with SQLSpec integration.

        Called by Litestar during application initialization.

        Args:
            app_config: Litestar application configuration.

        Returns:
            Modified AppConfig with SQLSpec integration configured.
        """
        if not self._config.enabled:
            logger.debug("SQLSpec plugin is disabled")
            return app_config

        logger.info("Initializing SQLSpec plugin")

        # Add lifecycle handlers
        app_config.on_startup.append(self._on_startup)
        app_config.on_shutdown.append(self._on_shutdown)

        # Register dependency providers if enabled
        if self._config.provide_repositories:
            existing_deps = dict(app_config.dependencies) if app_config.dependencies else {}
            existing_deps.update(get_sqlspec_dependency_providers())
            app_config.dependencies = existing_deps
            logger.debug("Registered SQLSpec dependency providers")

        return app_config

    async def _on_startup(self, app: Litestar) -> None:
        """Initialize SQLSpec on application startup.

        Args:
            app: The Litestar application instance.
        """
        await initialize_sqlspec(app, self._config)

    async def _on_shutdown(self, app: Litestar) -> None:
        """Clean up SQLSpec on application shutdown.

        Args:
            app: The Litestar application instance.
        """
        await cleanup_sqlspec(app)
        logger.info("SQLSpec plugin shutdown complete")


__all__ = [
    "CORRELATION_ID_KEY",
    "SQLSPEC_AVAILABLE",
    "SQLSPEC_STATE_KEY",
    "SQLSpecPlugin",
    "SQLSpecPluginConfig",
    "SQLSpecState",
    "cleanup_sqlspec",
    "generate_correlation_id",
    "get_correlation_id",
    "get_sqlspec_dependency_providers",
    "initialize_sqlspec",
    "provide_activity_repository",
    "provide_contact_repository",
    "provide_contribution_repository",
    "provide_event_repository",
    "provide_membership_repository",
    "provide_sqlspec_session",
    "set_correlation_id",
]
