"""Generic ASGI middleware for civi-py.

Provides request-scoped CiviClient injection for any ASGI framework including
Starlette, FastAPI, Litestar, Quart, and other ASGI-compatible applications.

Usage with FastAPI:
    from fastapi import FastAPI, Request
    from civicrm_py.contrib.asgi import CiviASGIMiddleware
    from civicrm_py import CiviSettings

    app = FastAPI()
    app.add_middleware(
        CiviASGIMiddleware,
        settings=CiviSettings.from_env(),
    )

    @app.get("/contacts")
    async def get_contacts(request: Request):
        client = request.state.civi_client
        return await client.get("Contact", limit=10)

Usage with Starlette:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from civicrm_py.contrib.asgi import CiviASGIMiddleware

    async def homepage(request):
        client = request.state.civi_client
        contacts = await client.get("Contact", limit=5)
        return JSONResponse({"count": len(contacts.values)})

    app = Starlette(routes=[Route("/", homepage)])
    app = CiviASGIMiddleware(app)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from civicrm_py.core.client import CiviClient
from civicrm_py.core.config import CiviSettings

logger = logging.getLogger("civicrm_py.contrib.asgi")

# ASGI type definitions
Scope = MutableMapping[str, Any]
Message = Mapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApplication = Callable[[Scope, Receive, Send], Awaitable[None]]


class CiviASGIMiddleware:
    """ASGI middleware that provides request-scoped CiviClient access.

    This middleware manages the CiviClient lifecycle:
    - Creates the client on application startup (lifespan)
    - Injects the client into each request's scope state
    - Closes the client on application shutdown

    The client is available at `scope["state"]["civi_client"]` or via
    framework-specific request state accessors (e.g., `request.state.civi_client`).

    Attributes:
        app: The wrapped ASGI application.
        settings: CiviCRM client configuration settings.
        client_key: Key used to store client in scope state.

    Example:
        >>> from civicrm_py.contrib.asgi import CiviASGIMiddleware
        >>> from civicrm_py import CiviSettings
        >>>
        >>> settings = CiviSettings(base_url="https://example.org/civicrm/ajax/api4", api_key="...")
        >>> app = CiviASGIMiddleware(my_asgi_app, settings=settings)
    """

    __slots__ = ("_app", "_client", "_client_key", "_settings")

    def __init__(
        self,
        app: ASGIApplication,
        settings: CiviSettings | None = None,
        *,
        client_key: str = "civi_client",
    ) -> None:
        """Initialize the ASGI middleware.

        Args:
            app: The ASGI application to wrap.
            settings: CiviCRM client settings. If None, will be loaded from
                environment variables on startup.
            client_key: The key used to store the client in scope["state"].
                Defaults to "civi_client".
        """
        self._app = app
        self._settings = settings
        self._client_key = client_key
        self._client: CiviClient | None = None

    @property
    def client(self) -> CiviClient | None:
        """Get the current CiviClient instance.

        Returns:
            The CiviClient if initialized, None otherwise.
        """
        return self._client

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Handle ASGI request.

        Routes requests based on scope type:
        - lifespan: Handles startup/shutdown lifecycle events
        - http/websocket: Injects client into scope state

        Args:
            scope: ASGI connection scope.
            receive: Receive channel callable.
            send: Send channel callable.
        """
        scope_type = scope.get("type")

        if scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        elif scope_type in ("http", "websocket"):
            await self._handle_request(scope, receive, send)
        else:
            # Pass through unknown scope types
            await self._app(scope, receive, send)

    async def _handle_lifespan(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Handle lifespan protocol for startup/shutdown events.

        Manages CiviClient lifecycle:
        - Creates and initializes client on startup
        - Closes client and releases resources on shutdown

        Args:
            scope: ASGI lifespan scope.
            receive: Receive channel callable.
            send: Send channel callable.
        """
        # Store original app for potential state passing
        original_receive = receive
        started = False

        async def wrapped_receive() -> Message:
            nonlocal started
            message = await original_receive()
            message_type = message.get("type")

            if message_type == "lifespan.startup":
                try:
                    await self._startup()
                    started = True
                except Exception:
                    logger.exception("Failed to initialize CiviClient during startup")
                    # We still need to let the app process the message
                    # The failure will be reported in the startup.complete
                    raise

            return message

        async def wrapped_send(message: Message) -> None:
            message_type = message.get("type")

            if message_type == "lifespan.shutdown.complete":
                # Cleanup before signaling shutdown complete
                await self._shutdown()

            await send(message)

        try:
            await self._app(scope, wrapped_receive, wrapped_send)
        finally:
            # Ensure cleanup happens even if app doesn't complete lifespan properly
            if started and self._client is not None:
                await self._shutdown()

    async def _handle_request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Handle HTTP or WebSocket request by injecting client into scope.

        Ensures scope["state"] exists and contains the CiviClient reference.

        Args:
            scope: ASGI request scope.
            receive: Receive channel callable.
            send: Send channel callable.
        """
        # Ensure state dict exists in scope
        if "state" not in scope:
            scope["state"] = {}

        # If client wasn't initialized via lifespan (app doesn't support it),
        # initialize lazily on first request
        if self._client is None:
            await self._startup()
            logger.debug(
                "CiviClient initialized lazily on first request. "
                "Consider using lifespan protocol for proper lifecycle management.",
            )

        # Inject client into scope state
        scope["state"][self._client_key] = self._client

        await self._app(scope, receive, send)

    async def _startup(self) -> None:
        """Initialize the CiviClient on application startup.

        Creates a new CiviClient instance using the configured settings.
        If no settings were provided, attempts to load from environment.
        """
        if self._client is not None:
            logger.warning("CiviClient already initialized, skipping startup")
            return

        settings = self._settings
        if settings is None:
            logger.debug("Loading CiviSettings from environment variables")
            settings = CiviSettings.from_env()

        self._client = CiviClient(settings)
        logger.info(
            "CiviClient initialized for %s",
            settings.base_url,
        )

    async def _shutdown(self) -> None:
        """Close the CiviClient on application shutdown.

        Releases any resources held by the client (HTTP connections, etc.).
        """
        if self._client is not None:
            logger.info("Closing CiviClient")
            await self._client.close()
            self._client = None


def get_civi_client(scope: Scope, *, client_key: str = "civi_client") -> CiviClient:
    """Retrieve CiviClient from ASGI scope.

    Convenience function to extract the CiviClient from scope state
    with proper error handling.

    Args:
        scope: ASGI scope dictionary.
        client_key: Key used to store client in scope state.
            Must match the key used in CiviASGIMiddleware.

    Returns:
        The CiviClient instance from scope state.

    Raises:
        RuntimeError: If CiviASGIMiddleware is not installed or
            client is not available in scope.

    Example:
        >>> async def my_endpoint(scope, receive, send):
        ...     client = get_civi_client(scope)
        ...     response = await client.get("Contact", limit=10)
    """
    state = scope.get("state", {})
    client = state.get(client_key)

    if client is None:
        msg = f"CiviClient not found in scope['state']['{client_key}']. Ensure CiviASGIMiddleware is installed."
        raise RuntimeError(msg)

    return client


__all__ = [
    "ASGIApplication",
    "CiviASGIMiddleware",
    "Message",
    "Receive",
    "Scope",
    "Send",
    "get_civi_client",
]
