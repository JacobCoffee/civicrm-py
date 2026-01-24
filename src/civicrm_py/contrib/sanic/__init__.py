"""Sanic integration for civi-py.

Provides first-class Sanic framework support with:
- CiviSanic extension for automatic client lifecycle management
- Request context injection via request.ctx.civi_client
- Application context for shared client access via app.ctx.civi_client
- Health check endpoint support

This is a Tier 3 integration - high-performance async framework using Sanic's
native extension patterns and lifecycle listeners.

Quick Start:
    >>> from sanic import Sanic, json
    >>> from civicrm_py.contrib.sanic import CiviSanic
    >>>
    >>> app = Sanic("myapp")
    >>> CiviSanic(app)  # Initialize with defaults from environment
    >>>
    >>> @app.get("/contacts")
    ... async def get_contacts(request):
    ...     client = request.ctx.civi_client
    ...     response = await client.get("Contact", limit=10)
    ...     return json({"contacts": response.values})

Factory Pattern (Application Factory):
    >>> from sanic import Sanic
    >>> from civicrm_py.contrib.sanic import CiviSanic
    >>> from civicrm_py.core.config import CiviSettings
    >>>
    >>> civi = CiviSanic()  # Create extension without app
    >>>
    >>> def create_app() -> Sanic:
    ...     app = Sanic("myapp")
    ...     settings = CiviSettings.from_env()
    ...     civi.init_app(app, settings)
    ...     return app

With Custom Settings:
    >>> from civicrm_py.core.config import CiviSettings
    >>>
    >>> settings = CiviSettings(
    ...     base_url="https://example.org/civicrm/ajax/api4",
    ...     api_key="your-api-key",
    ...     timeout=60,
    ... )
    >>> CiviSanic(app, settings=settings)

Accessing Client:
    The client is available in two ways:
    - request.ctx.civi_client: Per-request access (recommended for handlers)
    - app.ctx.civi_client: Application-level access (for background tasks)

Health Check:
    >>> civi = CiviSanic(app, enable_health_check=True)
    >>> # GET /health/civi returns {"status": "healthy", "connected": true}

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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from collections.abc import Callable

    from sanic import Request, Sanic
    from sanic.response import HTTPResponse

    from civicrm_py.core.client import CiviClient
    from civicrm_py.core.config import CiviSettings


def _check_sanic_available() -> bool:
    """Check if Sanic is available.

    Returns:
        True if Sanic is installed, False otherwise.
    """
    try:
        import sanic  # noqa: F401
    except ImportError:
        return False
    else:
        return True


SANIC_AVAILABLE = _check_sanic_available()

# Type variables for Sanic app generics
_Ctx = TypeVar("_Ctx")
_St = TypeVar("_St")


# Stub classes for when Sanic is not installed
# These provide type information to the type checker
class _SanicContextStub:
    """Stub for Sanic context objects when Sanic is not installed."""

    civi_ext: Any
    civi_client: Any

    def __getattr__(self, name: str) -> Any:
        raise ImportError("sanic required: pip install civi-py[sanic]")

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)


class _SanicStub(Generic[_Ctx, _St]):
    """Stub for Sanic app when Sanic is not installed."""

    name: str
    ctx: _SanicContextStub

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("sanic required: pip install civi-py[sanic]")

    def listener(self, event: str) -> Any:
        raise ImportError("sanic required: pip install civi-py[sanic]")

    def middleware(self, event: str) -> Any:
        raise ImportError("sanic required: pip install civi-py[sanic]")

    def get(self, path: str, **kwargs: Any) -> Any:
        raise ImportError("sanic required: pip install civi-py[sanic]")


class _RequestStub(Generic[_Ctx, _St]):
    """Stub for Sanic Request when Sanic is not installed."""

    ctx: _SanicContextStub

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("sanic required: pip install civi-py[sanic]")


class _HTTPResponseStub:
    """Stub for Sanic HTTPResponse when Sanic is not installed."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("sanic required: pip install civi-py[sanic]")


def _sanic_json_stub(*args: Any, **kwargs: Any) -> _HTTPResponseStub:
    """Stub for sanic.response.json when Sanic is not installed."""
    raise ImportError("sanic required: pip install civi-py[sanic]")


def _get_sanic_json() -> Callable[..., Any]:
    """Get Sanic's json response function, or stub if not available.

    Returns:
        Sanic's json function or a stub.
    """
    if SANIC_AVAILABLE:
        from sanic.response import json

        return json
    return _sanic_json_stub


logger = logging.getLogger("civicrm_py.contrib.sanic")


@dataclass
class CiviSanicConfig:
    """Configuration for the CiviSanic extension.

    Attributes:
        settings: CiviCRM client settings. If None, loads from environment.
        enable_health_check: Whether to register health check endpoint.
        health_check_path: URL path for health check endpoint.
        client_context_key: Key used to store client in request context.
        debug: Enable debug logging for civi-py.
    """

    settings: CiviSettings | None = None
    enable_health_check: bool = False
    health_check_path: str = "/health/civi"
    client_context_key: str = "civi_client"
    debug: bool = False


class CiviSanic:
    """Sanic extension for CiviCRM API integration.

    Provides automatic client lifecycle management using Sanic's listener
    pattern for server startup/shutdown events, and middleware for request
    context injection.

    The extension follows Sanic's two-phase initialization pattern:
    1. Extension instantiation (optionally without app)
    2. Application binding via init_app()

    Attributes:
        config: Extension configuration instance.
        client: The CiviClient instance (available after startup).

    Example:
        Direct initialization:

        >>> from sanic import Sanic, json
        >>> from civicrm_py.contrib.sanic import CiviSanic
        >>>
        >>> app = Sanic("myapp")
        >>> civi = CiviSanic(app)
        >>>
        >>> @app.get("/contacts")
        ... async def list_contacts(request):
        ...     response = await request.ctx.civi_client.get("Contact", limit=10)
        ...     return json({"contacts": response.values})

        Factory pattern:

        >>> civi = CiviSanic()
        >>>
        >>> def create_app():
        ...     app = Sanic("myapp")
        ...     civi.init_app(app)
        ...     return app

        With health check:

        >>> civi = CiviSanic(app, enable_health_check=True)
        >>> # GET /health/civi now available
    """

    __slots__ = ("_client", "_config")

    def __init__(
        self,
        app: Sanic[Any, Any] | None = None,
        settings: CiviSettings | None = None,
        *,
        enable_health_check: bool = False,
        health_check_path: str = "/health/civi",
        client_context_key: str = "civi_client",
        debug: bool = False,
    ) -> None:
        """Initialize the CiviSanic extension.

        Args:
            app: Sanic application instance. If None, call init_app() later.
            settings: CiviCRM client settings. If None, loads from environment
                variables on startup.
            enable_health_check: Register a health check endpoint.
            health_check_path: URL path for health check endpoint.
            client_context_key: Key used to store client in request/app context.
            debug: Enable debug logging for civi-py.
        """
        self._config = CiviSanicConfig(
            settings=settings,
            enable_health_check=enable_health_check,
            health_check_path=health_check_path,
            client_context_key=client_context_key,
            debug=debug,
        )
        self._client: CiviClient | None = None

        if debug:
            logging.getLogger("civicrm_py").setLevel(logging.DEBUG)

        if app is not None:
            self.init_app(app, settings)

    @property
    def config(self) -> CiviSanicConfig:
        """Get the extension configuration."""
        return self._config

    @property
    def client(self) -> CiviClient | None:
        """Get the CiviClient instance.

        Returns:
            The CiviClient if initialized (after server startup), None otherwise.
        """
        return self._client

    def init_app(
        self,
        app: Sanic[Any, Any],
        settings: CiviSettings | None = None,
    ) -> None:
        """Bind the extension to a Sanic application.

        Registers lifecycle listeners for client initialization and cleanup,
        and middleware for request context injection.

        Args:
            app: Sanic application instance.
            settings: CiviCRM settings. Overrides settings passed to __init__.
        """
        # Update settings if provided
        if settings is not None:
            self._config.settings = settings

        # Store extension reference in app context for access elsewhere
        app.ctx.civi_ext = self

        # Register lifecycle listeners
        @app.listener("before_server_start")
        async def _startup(
            app: Sanic[Any, Any],
            loop: AbstractEventLoop,
        ) -> None:
            del loop  # Required by Sanic listener signature but unused
            await self._on_startup(app)

        @app.listener("after_server_stop")
        async def _shutdown(
            app: Sanic[Any, Any],
            loop: AbstractEventLoop,
        ) -> None:
            del loop  # Required by Sanic listener signature but unused
            await self._on_shutdown(app)

        # Register request middleware for context injection
        @app.middleware("request")
        async def _inject_client(request: Request[Any, Any]) -> None:
            self._inject_request_context(request)

        # Register health check if enabled
        if self._config.enable_health_check:
            self._register_health_check(app)

        logger.info("CiviSanic extension initialized for app '%s'", app.name)

    async def _on_startup(self, app: Sanic[Any, Any]) -> None:
        """Initialize CiviClient on server startup.

        Creates the CiviClient instance and stores it in application context.

        Args:
            app: The Sanic application instance.
        """
        from civicrm_py.core.client import CiviClient
        from civicrm_py.core.config import CiviSettings

        settings = self._config.settings
        if settings is None:
            logger.debug("Loading CiviSettings from environment variables")
            settings = CiviSettings.from_env()

        self._client = CiviClient(settings)

        # Store client in app context for background task access
        setattr(app.ctx, self._config.client_context_key, self._client)

        logger.info("CiviClient initialized for %s", settings.base_url)

    async def _on_shutdown(self, app: Sanic[Any, Any]) -> None:
        """Clean up CiviClient on server shutdown.

        Closes the client and releases resources.

        Args:
            app: The Sanic application instance.
        """
        if self._client is not None:
            logger.info("Closing CiviClient")
            await self._client.close()
            self._client = None

        # Clear from app context
        if hasattr(app.ctx, self._config.client_context_key):
            delattr(app.ctx, self._config.client_context_key)

        logger.debug("CiviSanic shutdown complete")

    def _inject_request_context(self, request: Request[Any, Any]) -> None:
        """Inject CiviClient into request context.

        Makes the client available at request.ctx.civi_client for handlers.

        Args:
            request: The incoming Sanic request.
        """
        setattr(request.ctx, self._config.client_context_key, self._client)

    def _register_health_check(self, app: Sanic[Any, Any]) -> None:
        """Register the health check endpoint.

        Args:
            app: The Sanic application instance.
        """
        path = self._config.health_check_path
        sanic_json = _get_sanic_json()

        @app.get(path, name="civi_health_check")
        async def _health_check(request: Request[Any, Any]) -> HTTPResponse:
            return await self._health_check_handler(request, sanic_json)

        logger.debug("Registered health check at %s", path)

    async def _health_check_handler(
        self,
        request: Request[Any, Any],
        json_response: Callable[..., HTTPResponse],
    ) -> HTTPResponse:
        """Handle health check request.

        Args:
            request: The incoming Sanic request.
            json_response: Sanic's json response function.

        Returns:
            JSON response with health status.
        """
        from civicrm_py.core.exceptions import CiviError

        client: CiviClient | None = getattr(
            request.ctx,
            self._config.client_context_key,
            None,
        )

        if client is None:
            return json_response(
                {
                    "status": "unhealthy",
                    "connected": False,
                    "error": "CiviClient not initialized",
                },
                status=503,
            )

        try:
            # Attempt a lightweight API call to verify connectivity
            await client.request("Contact", "getFields", {})
            return json_response(
                {
                    "status": "healthy",
                    "connected": True,
                    "base_url": client.settings.base_url,
                },
            )
        except CiviError as exc:
            logger.warning("CiviCRM health check failed: %s", exc)
            return json_response(
                {
                    "status": "unhealthy",
                    "connected": False,
                    "error": str(exc),
                },
                status=503,
            )


def get_civi_client(request: Request[Any, Any]) -> CiviClient:
    """Retrieve CiviClient from Sanic request context.

    Convenience function to extract the CiviClient from request context
    with proper error handling.

    Args:
        request: Sanic request object.

    Returns:
        The CiviClient instance from request context.

    Raises:
        RuntimeError: If CiviSanic extension is not initialized or
            client is not available in request context.

    Example:
        >>> from civicrm_py.contrib.sanic import get_civi_client
        >>>
        >>> @app.get("/contacts")
        ... async def get_contacts(request):
        ...     client = get_civi_client(request)
        ...     response = await client.get("Contact", limit=10)
        ...     return json({"contacts": response.values})
    """
    from civicrm_py.core.client import CiviClient

    client = getattr(request.ctx, "civi_client", None)

    if client is None:
        msg = (
            "CiviClient not found in request.ctx.civi_client. "
            "Ensure CiviSanic extension is initialized with init_app()."
        )
        raise RuntimeError(msg)

    if not isinstance(client, CiviClient):
        msg = f"Expected CiviClient, got {type(client).__name__}"
        raise TypeError(msg)

    return client


__all__ = [
    "CiviSanic",
    "CiviSanicConfig",
    "SANIC_AVAILABLE",
    "get_civi_client",
]
