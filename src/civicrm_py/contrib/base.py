"""Base protocols and interfaces for framework integrations.

Provides abstract protocols that framework integrations must implement:
- IntegrationProtocol: Core client and settings access
- LifecycleHooks: Application startup/shutdown hooks
- RequestContext: Request-scoped dependency injection

These protocols enable framework-agnostic integration patterns while
supporting both async and sync execution models.

Example:
    >>> class DjangoIntegration:
    ...     def get_client(self) -> SyncCiviClient:
    ...         return SyncCiviClient.from_env()
    ...
    ...     def get_settings(self) -> CiviSettings:
    ...         return CiviSettings.from_env()
    ...
    ...     def is_async(self) -> bool:
    ...         return False
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient, SyncCiviClient
    from civicrm_py.core.config import CiviSettings


@runtime_checkable
class IntegrationProtocol(Protocol):
    """Protocol for framework integration implementations.

    Defines the core interface that all framework integrations must implement
    to provide access to CiviCRM client and settings.

    Implementations should handle framework-specific configuration loading,
    client lifecycle management, and execution mode (async/sync) detection.

    Example:
        >>> class MyFrameworkIntegration:
        ...     def get_client(self) -> CiviClient:
        ...         return CiviClient.from_env()
        ...
        ...     def get_settings(self) -> CiviSettings:
        ...         return CiviSettings.from_env()
        ...
        ...     def is_async(self) -> bool:
        ...         return True
    """

    def get_client(self) -> CiviClient | SyncCiviClient:
        """Get configured CiviCRM client instance.

        Returns the appropriate client type (async or sync) based on
        the framework's execution model.

        Returns:
            CiviClient for async frameworks, SyncCiviClient for sync frameworks.

        Raises:
            CiviError: If client configuration is invalid.
        """
        ...

    def get_settings(self) -> CiviSettings:
        """Get CiviCRM configuration settings.

        Loads settings from framework-specific configuration sources
        (e.g., Django settings, Litestar config, environment variables).

        Returns:
            CiviSettings instance with connection configuration.

        Raises:
            ValueError: If required settings are missing.
        """
        ...

    def is_async(self) -> bool:
        """Check if framework supports async execution.

        Returns:
            True if framework uses async/await, False for sync-only frameworks.
        """
        ...


@runtime_checkable
class LifecycleHooks(Protocol):
    """Protocol for application lifecycle management.

    Provides hooks for framework startup and shutdown events to manage
    CiviCRM client lifecycle, connection pooling, and resource cleanup.

    Frameworks should call these hooks at appropriate lifecycle points:
    - on_startup/on_startup_sync: After application initialization
    - on_shutdown/on_shutdown_sync: Before application termination

    Example:
        >>> class MyIntegration:
        ...     async def on_startup(self) -> None:
        ...         self.client = await CiviClient.from_env().__aenter__()
        ...
        ...     async def on_shutdown(self) -> None:
        ...         await self.client.close()
    """

    async def on_startup(self) -> None:
        """Execute async startup tasks.

        Called when the application starts up. Use this to:
        - Initialize async CiviCRM client
        - Establish connection pools
        - Validate configuration
        - Warm up caches

        For async frameworks (Litestar, FastAPI, etc.).

        Raises:
            CiviError: If startup initialization fails.
        """
        ...

    async def on_shutdown(self) -> None:
        """Execute async shutdown tasks.

        Called when the application shuts down. Use this to:
        - Close CiviCRM client connections
        - Release connection pools
        - Flush pending operations
        - Clean up resources

        For async frameworks (Litestar, FastAPI, etc.).
        """
        ...

    def on_startup_sync(self) -> None:
        """Execute sync startup tasks.

        Synchronous version of on_startup for sync-only frameworks.

        Called when the application starts up. Use this to:
        - Initialize sync CiviCRM client
        - Validate configuration
        - Warm up caches

        For sync frameworks (Django, Flask, etc.).

        Raises:
            CiviError: If startup initialization fails.
        """
        ...

    def on_shutdown_sync(self) -> None:
        """Execute sync shutdown tasks.

        Synchronous version of on_shutdown for sync-only frameworks.

        Called when the application shuts down. Use this to:
        - Close CiviCRM client connections
        - Flush pending operations
        - Clean up resources

        For sync frameworks (Django, Flask, etc.).
        """
        ...


@runtime_checkable
class RequestContext(Protocol):
    """Protocol for request-scoped dependency injection.

    Provides access to CiviCRM client within request handlers with
    framework-specific dependency injection patterns.

    Implementations should integrate with framework DI systems:
    - Litestar: Provide method with @provide decorator
    - FastAPI: Use Depends() with get_client
    - Django: Integrate with middleware or view decorators

    Example:
        >>> class MyRequestContext:
        ...     def __init__(self):
        ...         self._client = None
        ...
        ...     def get_client(self) -> CiviClient:
        ...         if self._client is None:
        ...             self._client = CiviClient.from_env()
        ...         return self._client
        ...
        ...     def set_client(self, client: CiviClient) -> None:
        ...         self._client = client
    """

    def get_client(self) -> CiviClient | SyncCiviClient:
        """Get CiviCRM client for current request.

        Returns a client instance scoped to the current request.
        May create a new client or return a shared instance depending
        on framework conventions.

        Returns:
            CiviClient or SyncCiviClient for making API requests.

        Raises:
            CiviError: If client is not available in current context.
        """
        ...

    def set_client(self, client: CiviClient | SyncCiviClient) -> None:
        """Set CiviCRM client for current request.

        Stores a client instance in request-scoped storage for
        dependency injection or testing purposes.

        Args:
            client: Client instance to use for this request.
        """
        ...


__all__ = [
    "IntegrationProtocol",
    "LifecycleHooks",
    "RequestContext",
]
