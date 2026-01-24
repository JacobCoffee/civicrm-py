"""Base integration class with common functionality for framework integrations.

This module provides the BaseIntegration class which implements shared logic
for all framework integrations (Django, Litestar, Flask, FastAPI, etc.).

The BaseIntegration class provides:
- Client lifecycle management (async and sync)
- Configuration loading from environment or settings
- Client factory methods with DI support
- Implementation of IntegrationProtocol and LifecycleHooks from base.py

Example:
    >>> from civicrm_py.contrib.integration import BaseIntegration
    >>> from civicrm_py.core.config import CiviSettings
    >>>
    >>> # Create from environment variables
    >>> integration = BaseIntegration.from_env()
    >>> await integration.startup()
    >>> client = integration.get_client()
    >>>
    >>> # Or with explicit settings
    >>> settings = CiviSettings(
    ...     base_url="https://example.org/civicrm/ajax/api4",
    ...     api_key="my-api-key",
    ... )
    >>> integration = BaseIntegration.from_settings(settings)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self

from civicrm_py.core.config import CiviSettings, get_settings
from civicrm_py.core.exceptions import CiviIntegrationError

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient, SyncCiviClient

logger = logging.getLogger(__name__)


class BaseIntegration:
    """Base class for framework integrations with common functionality.

    Provides shared implementation for client lifecycle management,
    configuration loading, and dependency injection support. Framework-specific
    integrations should inherit from this class.

    This class implements both IntegrationProtocol and LifecycleHooks protocols
    defined in civicrm_py.contrib.base, enabling consistent behavior across all
    framework integrations.

    The class supports both async and sync operation modes:
    - Async mode (default): For ASGI frameworks (Litestar, FastAPI, Starlette)
    - Sync mode: For WSGI frameworks (Django, Flask)

    Attributes:
        _settings: The CiviSettings configuration instance.
        _client: The async CiviClient instance (None until startup).
        _sync_client: The sync SyncCiviClient instance (None until startup_sync).
        _is_async: Whether the integration is running in async mode.

    Example:
        Basic usage with environment variables:

        >>> integration = BaseIntegration.from_env()
        >>> await integration.startup()
        >>> client = integration.get_client()
        >>> # ... use client ...
        >>> await integration.shutdown()

        Usage with explicit settings:

        >>> settings = CiviSettings(
        ...     base_url="https://example.org/civicrm/ajax/api4",
        ...     api_key="my-api-key",
        ... )
        >>> integration = BaseIntegration.from_settings(settings)
        >>> integration.startup_sync()
        >>> client = integration.get_sync_client()

        Context manager usage:

        >>> async with BaseIntegration.from_env() as integration:
        ...     client = integration.get_client()
        ...     response = await client.get("Contact", limit=10)
    """

    __slots__ = ("_client", "_is_async", "_settings", "_sync_client")

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        is_async: bool = True,
    ) -> None:
        """Initialize the BaseIntegration.

        Either provide a CiviSettings instance or let the integration
        load settings from environment variables automatically.

        Args:
            settings: CiviSettings instance for configuration. If None,
                settings will be loaded from environment variables using
                get_settings() which provides caching.
            is_async: Whether to use async mode. Defaults to True.
                Set to False for WSGI frameworks like Django and Flask.

        Example:
            >>> # With explicit settings
            >>> settings = CiviSettings(base_url="...", api_key="...")
            >>> integration = BaseIntegration(settings=settings)
            >>>
            >>> # From environment (cached)
            >>> integration = BaseIntegration()  # Uses get_settings()
        """
        if settings is None:
            settings = get_settings()

        self._settings: CiviSettings = settings
        self._client: CiviClient | None = None
        self._sync_client: SyncCiviClient | None = None
        self._is_async: bool = is_async

    # -------------------------------------------------------------------------
    # Class Methods for Construction
    # -------------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> Self:
        """Create integration instance from environment variables.

        Loads settings from environment variables using CiviSettings.from_env().
        Unlike the default constructor which uses cached settings, this method
        creates fresh settings from current environment state.

        Returns:
            New BaseIntegration instance configured from environment.

        Raises:
            ValueError: If required environment variables are missing
                (CIVI_BASE_URL, and auth credentials based on CIVI_AUTH_TYPE).

        Example:
            >>> # Set environment variables:
            >>> # CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
            >>> # CIVI_API_KEY=my-api-key
            >>> integration = BaseIntegration.from_env()
        """
        settings = CiviSettings.from_env()
        return cls(settings=settings)

    @classmethod
    def from_settings(cls, settings: CiviSettings) -> Self:
        """Create integration instance from explicit settings.

        Use this method when you have already constructed a CiviSettings
        instance, or when integrating with framework-specific configuration.

        Args:
            settings: CiviSettings instance with configuration.

        Returns:
            New BaseIntegration instance configured with provided settings.

        Example:
            >>> settings = CiviSettings(
            ...     base_url="https://example.org/civicrm/ajax/api4",
            ...     api_key="my-api-key",
            ... )
            >>> integration = BaseIntegration.from_settings(settings)
        """
        return cls(settings=settings)

    # -------------------------------------------------------------------------
    # Properties (IntegrationProtocol implementation)
    # -------------------------------------------------------------------------

    @property
    def settings(self) -> CiviSettings:
        """Get the integration settings.

        Returns:
            The CiviSettings configuration instance.
        """
        return self._settings

    @property
    def is_async(self) -> bool:
        """Check if integration is in async mode.

        The mode is determined by which startup method was called:
        - startup() sets async mode (True)
        - startup_sync() sets sync mode (False)

        Returns:
            True if using async client, False for sync mode.
        """
        return self._is_async

    # -------------------------------------------------------------------------
    # Async Lifecycle Methods (LifecycleHooks implementation)
    # -------------------------------------------------------------------------

    async def on_startup(self) -> None:
        """Called during application startup (async).

        Initializes the async CiviClient. This method is typically called
        by the framework during application startup:
        - Litestar: on_app_init hook
        - FastAPI: lifespan startup
        - Starlette: on_startup event

        Delegates to startup() for the actual initialization.

        Example:
            >>> # In Litestar plugin
            >>> async def on_app_init(self, app: Litestar) -> None:
            ...     await self.integration.on_startup()
        """
        await self.startup()

    async def on_shutdown(self) -> None:
        """Called during application shutdown (async).

        Closes the async CiviClient and releases resources. This method
        is typically called by the framework during application shutdown.

        Delegates to shutdown() for the actual cleanup.

        Example:
            >>> # In Litestar plugin
            >>> async def on_app_shutdown(self, app: Litestar) -> None:
            ...     await self.integration.on_shutdown()
        """
        await self.shutdown()

    def on_startup_sync(self) -> None:
        """Called during application startup (sync).

        Initializes the sync SyncCiviClient. This method is typically
        called by WSGI frameworks during application startup:
        - Django: AppConfig.ready()
        - Flask: before_first_request or app initialization

        Delegates to startup_sync() for the actual initialization.

        Example:
            >>> # In Django AppConfig
            >>> def ready(self) -> None:
            ...     self.integration.on_startup_sync()
        """
        self.startup_sync()

    def on_shutdown_sync(self) -> None:
        """Called during application shutdown (sync).

        Closes the sync SyncCiviClient and releases resources. This method
        is typically called by WSGI frameworks during application shutdown.

        Delegates to shutdown_sync() for the actual cleanup.

        Example:
            >>> # In Django or Flask cleanup
            >>> def cleanup() -> None:
            ...     integration.on_shutdown_sync()
        """
        self.shutdown_sync()

    # -------------------------------------------------------------------------
    # Client Lifecycle Management
    # -------------------------------------------------------------------------

    async def startup(self) -> None:
        """Initialize the async CiviClient.

        Creates and configures the async client instance. This method
        should be called during application startup for ASGI frameworks.

        The client is created lazily - no network connections are made
        until the first request.

        Raises:
            CiviIntegrationError: If async client is already initialized.
                Call shutdown() first to reinitialize.

        Example:
            >>> integration = BaseIntegration.from_env()
            >>> await integration.startup()
            >>> # Client is now ready to use
            >>> client = integration.get_client()
        """
        if self._client is not None:
            msg = "Async client already initialized. Call shutdown() first."
            raise CiviIntegrationError(msg)

        # Import here to avoid circular imports at module level
        from civicrm_py.core.client import CiviClient

        self._client = CiviClient(settings=self._settings)
        self._is_async = True
        logger.debug(
            "BaseIntegration async client initialized for %s",
            self._settings.base_url,
        )

    async def shutdown(self) -> None:
        """Close the async CiviClient and release resources.

        Gracefully closes the client connection pool and clears the
        client instance. Safe to call multiple times.

        Should be called during application shutdown for ASGI frameworks.

        Example:
            >>> await integration.shutdown()
            >>> # Client is now closed, get_client() will raise
        """
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("BaseIntegration async client closed")

    def startup_sync(self) -> None:
        """Initialize the sync SyncCiviClient.

        Creates and configures the sync client instance. This method
        should be called during application startup for WSGI frameworks.

        The client is created lazily - no network connections are made
        until the first request.

        Raises:
            CiviIntegrationError: If sync client is already initialized.
                Call shutdown_sync() first to reinitialize.

        Example:
            >>> integration = BaseIntegration.from_env()
            >>> integration.startup_sync()
            >>> # Client is now ready to use
            >>> client = integration.get_sync_client()
        """
        if self._sync_client is not None:
            msg = "Sync client already initialized. Call shutdown_sync() first."
            raise CiviIntegrationError(msg)

        # Import here to avoid circular imports at module level
        from civicrm_py.core.client import SyncCiviClient

        self._sync_client = SyncCiviClient(settings=self._settings)
        self._is_async = False
        logger.debug(
            "BaseIntegration sync client initialized for %s",
            self._settings.base_url,
        )

    def shutdown_sync(self) -> None:
        """Close the sync SyncCiviClient and release resources.

        Gracefully closes the client connection and clears the client
        instance. Safe to call multiple times.

        Should be called during application shutdown for WSGI frameworks.

        Example:
            >>> integration.shutdown_sync()
            >>> # Client is now closed, get_sync_client() will raise
        """
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None
            logger.debug("BaseIntegration sync client closed")

    # -------------------------------------------------------------------------
    # Client Factory / DI Support (RequestContext implementation)
    # -------------------------------------------------------------------------

    def get_client(self) -> CiviClient:
        """Get the async CiviClient instance.

        Returns the initialized async client for making API requests.
        The client must be initialized via startup() before calling
        this method.

        This method is typically used by framework dependency injection
        to provide the client to request handlers.

        Returns:
            The initialized async CiviClient.

        Raises:
            CiviIntegrationError: If async client is not initialized.
                Call startup() or on_startup() first.

        Example:
            >>> await integration.startup()
            >>> client = integration.get_client()
            >>> response = await client.get("Contact", limit=10)

            >>> # With Litestar DI
            >>> async def provide_client() -> CiviClient:
            ...     return integration.get_client()
        """
        if self._client is None:
            msg = "Async client not initialized. Call startup() or on_startup() before accessing the client."
            raise CiviIntegrationError(msg)
        return self._client

    def get_sync_client(self) -> SyncCiviClient:
        """Get the sync SyncCiviClient instance.

        Returns the initialized sync client for making API requests.
        The client must be initialized via startup_sync() before
        calling this method.

        This method is typically used by WSGI framework middleware
        or view decorators to provide the client.

        Returns:
            The initialized sync SyncCiviClient.

        Raises:
            CiviIntegrationError: If sync client is not initialized.
                Call startup_sync() or on_startup_sync() first.

        Example:
            >>> integration.startup_sync()
            >>> client = integration.get_sync_client()
            >>> response = client.get("Contact", limit=10)

            >>> # In Django middleware
            >>> def process_request(self, request):
            ...     request.civi_client = integration.get_sync_client()
        """
        if self._sync_client is None:
            msg = "Sync client not initialized. Call startup_sync() or on_startup_sync() before accessing the client."
            raise CiviIntegrationError(msg)
        return self._sync_client

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        """Async context manager entry.

        Automatically initializes the async client when entering the context.

        Returns:
            Self for use in async with statement.

        Example:
            >>> async with BaseIntegration.from_env() as integration:
            ...     client = integration.get_client()
            ...     response = await client.get("Contact", limit=10)
        """
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit.

        Automatically closes the async client when exiting the context.
        """
        await self.shutdown()

    def __enter__(self) -> Self:
        """Sync context manager entry.

        Automatically initializes the sync client when entering the context.

        Returns:
            Self for use in with statement.

        Example:
            >>> with BaseIntegration.from_env() as integration:
            ...     client = integration.get_sync_client()
            ...     response = client.get("Contact", limit=10)
        """
        self.startup_sync()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Sync context manager exit.

        Automatically closes the sync client when exiting the context.
        """
        self.shutdown_sync()

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return string representation of the integration.

        Returns:
            A string showing the integration mode, client status, and base URL.
        """
        mode = "async" if self._is_async else "sync"
        if self._client is not None:
            client_status = "async client initialized"
        elif self._sync_client is not None:
            client_status = "sync client initialized"
        else:
            client_status = "not initialized"
        return (
            f"<{self.__class__.__name__} mode={mode!r} status={client_status!r} base_url={self._settings.base_url!r}>"
        )


__all__ = [
    "BaseIntegration",
]
