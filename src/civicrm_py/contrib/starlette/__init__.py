"""Starlette integration for civi-py.

Provides a thin wrapper around the generic CiviASGIMiddleware optimized for
Starlette applications with idiomatic lifecycle management and request state access.

Quick Start:
    >>> from starlette.applications import Starlette
    >>> from starlette.routing import Route
    >>> from starlette.responses import JSONResponse
    >>> from civicrm_py.contrib.starlette import CiviMiddleware, civi_startup, civi_shutdown
    >>>
    >>> async def get_contacts(request):
    ...     client = request.state.civi_client
    ...     response = await client.get("Contact", limit=10)
    ...     return JSONResponse({"contacts": response.values})
    >>>
    >>> app = Starlette(
    ...     routes=[Route("/contacts", get_contacts)],
    ...     on_startup=[civi_startup],
    ...     on_shutdown=[civi_shutdown],
    ... )
    >>> app = CiviMiddleware(app)

With Custom Settings:
    >>> from civicrm_py import CiviSettings
    >>> from civicrm_py.contrib.starlette import CiviMiddleware
    >>>
    >>> settings = CiviSettings(
    ...     base_url="https://example.org/civicrm/ajax/api4",
    ...     api_key="your-api-key",
    ... )
    >>> app = CiviMiddleware(app, settings=settings)

Using app.state for Shared Client:
    >>> from starlette.applications import Starlette
    >>> from civicrm_py.contrib.starlette import create_startup_handler, create_shutdown_handler
    >>>
    >>> app = Starlette()
    >>> app.add_event_handler("startup", create_startup_handler(app))
    >>> app.add_event_handler("shutdown", create_shutdown_handler(app))

Environment Variables:
    Set these environment variables for automatic configuration:
    - CIVI_BASE_URL: CiviCRM API base URL
    - CIVI_API_KEY: API key for authentication
    - CIVI_SITE_KEY: Optional site key
    - CIVI_TIMEOUT: Request timeout (default: 30)
    - CIVI_VERIFY_SSL: Verify SSL certificates (default: true)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from civicrm_py.contrib.asgi import ASGIApplication, CiviASGIMiddleware, get_civi_client
from civicrm_py.core.client import CiviClient
from civicrm_py.core.config import CiviSettings

# Check if Starlette is available
try:
    from starlette.applications import Starlette
    from starlette.requests import Request as StarletteRequest

    STARLETTE_AVAILABLE = True
except ImportError:
    STARLETTE_AVAILABLE = False

    class Starlette:
        """Stub when Starlette is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("Starlette required: pip install civi-py[starlette]")

    class StarletteRequest:
        """Stub when Starlette is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("Starlette required: pip install civi-py[starlette]")


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request

logger = logging.getLogger("civicrm_py.contrib.starlette")

# Default key for storing client in request/app state
CIVI_CLIENT_STATE_KEY = "civi_client"


class CiviMiddleware(CiviASGIMiddleware):
    """Starlette middleware wrapper for CiviCRM client injection.

    This is a thin wrapper around CiviASGIMiddleware that provides
    Starlette-specific type hints and documentation. The client is
    automatically injected into `request.state.civi_client` for each request.

    The middleware handles client lifecycle automatically:
    - Creates the client on first request (or during lifespan startup)
    - Injects the client into request.state for each request
    - Closes the client on application shutdown

    Attributes:
        settings: CiviCRM client configuration settings.

    Example:
        >>> from starlette.applications import Starlette
        >>> from starlette.routing import Route
        >>> from starlette.responses import JSONResponse
        >>> from civicrm_py.contrib.starlette import CiviMiddleware
        >>>
        >>> async def contacts(request):
        ...     client = request.state.civi_client
        ...     return JSONResponse({"count": 0})
        >>>
        >>> app = Starlette(routes=[Route("/contacts", contacts)])
        >>> app = CiviMiddleware(app)
    """

    def __init__(
        self,
        app: ASGIApplication,
        settings: CiviSettings | None = None,
        *,
        client_key: str = CIVI_CLIENT_STATE_KEY,
    ) -> None:
        """Initialize the Starlette middleware.

        Args:
            app: The Starlette application to wrap.
            settings: CiviCRM client settings. If None, will be loaded from
                environment variables on startup.
            client_key: The key used to store the client in request.state.
                Defaults to "civi_client".
        """
        super().__init__(app, settings, client_key=client_key)


def get_client_from_request(
    request: Request,
    *,
    client_key: str = CIVI_CLIENT_STATE_KEY,
) -> CiviClient:
    """Get CiviClient from Starlette request state.

    Convenience function to extract the CiviClient from request.state
    with proper error handling.

    Args:
        request: Starlette Request object.
        client_key: Key used to store client in request state.
            Must match the key used in CiviMiddleware.

    Returns:
        The CiviClient instance from request state.

    Raises:
        RuntimeError: If CiviMiddleware is not installed or
            client is not available in request state.

    Example:
        >>> from starlette.requests import Request
        >>> from civicrm_py.contrib.starlette import get_client_from_request
        >>>
        >>> async def my_endpoint(request: Request):
        ...     client = get_client_from_request(request)
        ...     response = await client.get("Contact", limit=10)
        ...     return JSONResponse({"contacts": response.values})
    """
    client = getattr(request.state, client_key, None)

    if client is None:
        msg = f"CiviClient not found in request.state.{client_key}. Ensure CiviMiddleware is installed."
        raise RuntimeError(msg)

    return client


def create_startup_handler(
    app: Starlette,
    settings: CiviSettings | None = None,
    *,
    client_key: str = CIVI_CLIENT_STATE_KEY,
) -> Callable[[], Awaitable[None]]:
    """Create a startup event handler that initializes CiviClient on app.state.

    Use this when you want to manage the client lifecycle via Starlette's
    on_startup/on_shutdown handlers instead of relying on the ASGI lifespan
    protocol.

    This pattern is useful when:
    - You need access to the client from background tasks via app.state
    - You want explicit control over client initialization
    - You're using multiple startup handlers that need sequencing

    Args:
        app: Starlette application instance.
        settings: CiviCRM client settings. If None, loads from environment.
        client_key: Key to store client in app.state.

    Returns:
        Async startup handler function.

    Example:
        >>> from starlette.applications import Starlette
        >>> from civicrm_py.contrib.starlette import (
        ...     create_startup_handler,
        ...     create_shutdown_handler,
        ... )
        >>>
        >>> app = Starlette()
        >>> app.add_event_handler("startup", create_startup_handler(app))
        >>> app.add_event_handler("shutdown", create_shutdown_handler(app))
    """

    async def startup_handler() -> None:
        resolved_settings = settings
        if resolved_settings is None:
            logger.debug("Loading CiviSettings from environment variables")
            resolved_settings = CiviSettings.from_env()

        client = CiviClient(resolved_settings)
        setattr(app.state, client_key, client)
        logger.info(
            "CiviClient initialized on app.state.%s for %s",
            client_key,
            resolved_settings.base_url,
        )

    return startup_handler


def create_shutdown_handler(
    app: Starlette,
    *,
    client_key: str = CIVI_CLIENT_STATE_KEY,
) -> Callable[[], Awaitable[None]]:
    """Create a shutdown event handler that closes CiviClient from app.state.

    Companion to create_startup_handler for clean resource management.

    Args:
        app: Starlette application instance.
        client_key: Key used to store client in app.state.

    Returns:
        Async shutdown handler function.

    Example:
        >>> app.add_event_handler("shutdown", create_shutdown_handler(app))
    """

    async def shutdown_handler() -> None:
        client = getattr(app.state, client_key, None)
        if client is not None:
            logger.info("Closing CiviClient")
            await client.close()
            # Remove reference
            delattr(app.state, client_key)

    return shutdown_handler


# Pre-built handlers for common use case with environment-based settings
# These are module-level for use as simple on_startup/on_shutdown callables
_global_client: CiviClient | None = None


async def civi_startup() -> None:
    """Global startup handler for simple single-client applications.

    Initializes a global CiviClient from environment variables.
    For multi-app or customized scenarios, use create_startup_handler() instead.

    Note:
        This creates a module-level client. For app-state based client
        management, use create_startup_handler(app) instead.

    Example:
        >>> app = Starlette(
        ...     routes=[...],
        ...     on_startup=[civi_startup],
        ...     on_shutdown=[civi_shutdown],
        ... )
    """
    global _global_client  # noqa: PLW0603

    if _global_client is not None:
        logger.warning("Global CiviClient already initialized, skipping startup")
        return

    settings = CiviSettings.from_env()
    _global_client = CiviClient(settings)
    logger.info("Global CiviClient initialized for %s", settings.base_url)


async def civi_shutdown() -> None:
    """Global shutdown handler for simple single-client applications.

    Closes the global CiviClient created by civi_startup().

    Example:
        >>> app = Starlette(
        ...     routes=[...],
        ...     on_startup=[civi_startup],
        ...     on_shutdown=[civi_shutdown],
        ... )
    """
    global _global_client  # noqa: PLW0603

    if _global_client is not None:
        logger.info("Closing global CiviClient")
        await _global_client.close()
        _global_client = None


def get_global_client() -> CiviClient:
    """Get the global CiviClient instance.

    Only available after civi_startup() has been called.

    Returns:
        The global CiviClient instance.

    Raises:
        RuntimeError: If civi_startup() has not been called.

    Example:
        >>> async def my_background_task():
        ...     client = get_global_client()
        ...     await client.get("Contact", limit=1)
    """
    if _global_client is None:
        msg = "Global CiviClient not initialized. Ensure civi_startup() is registered as an on_startup handler."
        raise RuntimeError(msg)
    return _global_client


__all__ = [
    "CIVI_CLIENT_STATE_KEY",
    "CiviMiddleware",
    "civi_shutdown",
    "civi_startup",
    "create_shutdown_handler",
    "create_startup_handler",
    "get_civi_client",
    "get_client_from_request",
    "get_global_client",
]
