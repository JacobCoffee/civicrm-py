"""Falcon framework integration for civi-py.

Provides CiviCRM client integration for Falcon applications supporting both
WSGI (traditional synchronous) and ASGI (async) modes. The middleware injects
a CiviClient into the request context, making it available via `req.context.civi_client`.

WSGI Usage (Falcon 3.x sync mode):
    import falcon
    from civicrm_py.contrib.falcon import CiviFalconMiddleware
    from civicrm_py.core.config import CiviSettings

    middleware = CiviFalconMiddleware()
    app = falcon.App(middleware=[middleware])

    class ContactResource:
        def on_get(self, req, resp):
            client = req.context.civi_client
            response = client.get("Contact", limit=10)
            resp.media = {"contacts": response.values}

    app.add_route("/contacts", ContactResource())

ASGI Usage (Falcon 3.x async mode):
    import falcon.asgi
    from civicrm_py.contrib.falcon import CiviFalconASGIMiddleware

    middleware = CiviFalconASGIMiddleware()
    app = falcon.asgi.App(middleware=[middleware])

    class ContactResource:
        async def on_get(self, req, resp):
            client = req.context.civi_client
            response = await client.get("Contact", limit=10)
            resp.media = {"contacts": response.values}

    app.add_route("/contacts", ContactResource())

Auto-detection Usage:
    from civicrm_py.contrib.falcon import get_civi_middleware

    # Returns appropriate middleware based on app type
    middleware = get_civi_middleware(app)

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
import threading
from typing import Any

from civicrm_py.core.client import CiviClient, SyncCiviClient
from civicrm_py.core.config import CiviSettings

logger = logging.getLogger("civicrm_py.contrib.falcon")

# Default context key for accessing the client
CIVI_CLIENT_CONTEXT_KEY = "civi_client"


class CiviFalconMiddleware:
    """WSGI middleware for Falcon that provides CiviClient access.

    Injects a SyncCiviClient instance into each request's context, making it
    available via `req.context.civi_client`. The client is created lazily on
    first request and managed for the application's lifecycle.

    Features:
        - Lazy client initialization on first request
        - Thread-local client support for multi-threaded WSGI servers
        - Configurable context key
        - Clean shutdown via close() method

    Thread Safety:
        When use_thread_local=True (default), each thread gets its own client
        instance stored in thread-local storage. This is safe for multi-threaded
        WSGI servers like Gunicorn with sync workers.

    Args:
        settings: CiviCRM settings. If None, settings are loaded from environment.
        client_key: Key to store client under in req.context. Defaults to "civi_client".
        use_thread_local: If True, use thread-local storage for clients.
            Defaults to True for thread safety.

    Example:
        import falcon
        from civicrm_py.contrib.falcon import CiviFalconMiddleware
        from civicrm_py.core.config import CiviSettings

        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="your-api-key",
        )
        middleware = CiviFalconMiddleware(settings=settings)
        app = falcon.App(middleware=[middleware])

        class ContactResource:
            def on_get(self, req, resp):
                client = req.context.civi_client
                response = client.get("Contact", limit=10)
                resp.media = {"contacts": response.values}

        app.add_route("/contacts", ContactResource())
    """

    __slots__ = (
        "_client",
        "_client_key",
        "_local",
        "_lock",
        "_settings",
        "_use_thread_local",
    )

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        client_key: str = CIVI_CLIENT_CONTEXT_KEY,
        use_thread_local: bool = True,
    ) -> None:
        """Initialize the Falcon WSGI middleware.

        Args:
            settings: CiviCRM settings. If None, loaded from environment variables.
            client_key: Key to store client under in req.context.
            use_thread_local: Use thread-local storage for client instances.
        """
        self._settings = settings
        self._client_key = client_key
        self._use_thread_local = use_thread_local
        self._lock = threading.Lock()
        self._local = threading.local()
        self._client: SyncCiviClient | None = None

    @property
    def settings(self) -> CiviSettings:
        """Get the CiviCRM settings, loading from environment if needed.

        Returns:
            CiviSettings instance.
        """
        if self._settings is None:
            self._settings = CiviSettings.from_env()
        return self._settings

    def _get_client(self) -> SyncCiviClient:
        """Get or create the CiviCRM client.

        If use_thread_local is True, returns a thread-local client instance.
        Otherwise, returns a shared client instance.

        Returns:
            SyncCiviClient instance.
        """
        if self._use_thread_local:
            return self._get_thread_local_client()
        return self._get_shared_client()

    def _get_thread_local_client(self) -> SyncCiviClient:
        """Get or create a thread-local client instance.

        Returns:
            Thread-local SyncCiviClient instance.
        """
        client = getattr(self._local, "client", None)
        if client is None:
            client = SyncCiviClient(settings=self.settings)
            self._local.client = client
            logger.debug(
                "Created thread-local CiviCRM client for thread %s",
                threading.current_thread().name,
            )
        return client

    def _get_shared_client(self) -> SyncCiviClient:
        """Get or create a shared client instance.

        Uses double-checked locking for thread-safe lazy initialization.

        Returns:
            Shared SyncCiviClient instance.
        """
        client = self._client
        if client is None:
            with self._lock:
                # Double-check after acquiring lock
                client = self._client
                if client is None:
                    client = SyncCiviClient(settings=self.settings)
                    self._client = client
                    logger.debug("Created shared CiviCRM client")
        return client

    def process_request(self, req: Any, resp: Any) -> None:
        """Process incoming request by injecting CiviClient.

        Injects the CiviCRM client into the request context before
        the request reaches the resource handler.

        Args:
            req: Falcon Request object.
            resp: Falcon Response object.
        """
        setattr(req.context, self._client_key, self._get_client())

    def process_response(
        self,
        req: Any,
        resp: Any,
        resource: Any,
        req_succeeded: bool,
    ) -> None:
        """Process response after resource handler completes.

        Currently a no-op but included for middleware interface completeness.
        Can be extended for logging, metrics, or cleanup tasks.

        Args:
            req: Falcon Request object.
            resp: Falcon Response object.
            resource: Resource object that handled the request (may be None).
            req_succeeded: True if no exceptions were raised.
        """
        # No-op - client cleanup handled in close()

    def close(self) -> None:
        """Close all client instances and release resources.

        Should be called during application shutdown to properly clean up
        HTTP connections and other resources.

        Note:
            This method closes the shared client if use_thread_local=False.
            For thread-local clients, each thread's client should be closed
            individually, but this is typically handled automatically when
            threads terminate. Calling close() will close any client in the
            current thread's local storage.

        Example:
            # During application shutdown
            import atexit
            atexit.register(middleware.close)
        """
        # Close shared client if exists
        if self._client is not None:
            with self._lock:
                if self._client is not None:
                    try:
                        self._client.close()
                        logger.debug("Closed shared CiviCRM client")
                    except Exception:
                        logger.exception("Error closing shared CiviCRM client")
                    finally:
                        self._client = None

        # Close thread-local client for current thread
        client = getattr(self._local, "client", None)
        if client is not None:
            try:
                client.close()
                logger.debug(
                    "Closed thread-local CiviCRM client for thread %s",
                    threading.current_thread().name,
                )
            except Exception:
                logger.exception("Error closing thread-local CiviCRM client")
            finally:
                self._local.client = None

    def __repr__(self) -> str:
        """Return string representation.

        Returns:
            String representation of the middleware.
        """
        return f"{self.__class__.__name__}(client_key={self._client_key!r}, use_thread_local={self._use_thread_local})"


class CiviFalconASGIMiddleware:
    """ASGI middleware for Falcon that provides async CiviClient access.

    Injects a CiviClient instance into each request's context, making it
    available via `req.context.civi_client`. Manages client lifecycle through
    Falcon's ASGI middleware protocol (process_startup, process_shutdown).

    Features:
        - Async client initialization via process_startup
        - Proper cleanup via process_shutdown
        - Request-scoped client injection
        - Configurable context key

    Args:
        settings: CiviCRM settings. If None, settings are loaded from environment.
        client_key: Key to store client under in req.context. Defaults to "civi_client".

    Example:
        import falcon.asgi
        from civicrm_py.contrib.falcon import CiviFalconASGIMiddleware
        from civicrm_py.core.config import CiviSettings

        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="your-api-key",
        )
        middleware = CiviFalconASGIMiddleware(settings=settings)
        app = falcon.asgi.App(middleware=[middleware])

        class ContactResource:
            async def on_get(self, req, resp):
                client = req.context.civi_client
                response = await client.get("Contact", limit=10)
                resp.media = {"contacts": response.values}

        app.add_route("/contacts", ContactResource())
    """

    __slots__ = ("_client", "_client_key", "_settings")

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        client_key: str = CIVI_CLIENT_CONTEXT_KEY,
    ) -> None:
        """Initialize the Falcon ASGI middleware.

        Args:
            settings: CiviCRM settings. If None, loaded from environment variables.
            client_key: Key to store client under in req.context.
        """
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

    @property
    def settings(self) -> CiviSettings:
        """Get the CiviCRM settings, loading from environment if needed.

        Returns:
            CiviSettings instance.
        """
        if self._settings is None:
            self._settings = CiviSettings.from_env()
        return self._settings

    async def process_startup(self, scope: dict[str, Any], event: dict[str, Any]) -> None:
        """Handle application startup event.

        Initializes the CiviClient when the ASGI application starts.
        This method is called by Falcon's ASGI framework during startup.

        Args:
            scope: ASGI lifespan scope.
            event: Startup event dictionary.
        """
        if self._client is not None:
            logger.warning("CiviClient already initialized, skipping startup")
            return

        self._client = CiviClient(settings=self.settings)
        logger.info("CiviClient initialized for %s", self.settings.base_url)

    async def process_shutdown(self, scope: dict[str, Any], event: dict[str, Any]) -> None:
        """Handle application shutdown event.

        Closes the CiviClient when the ASGI application shuts down.
        This method is called by Falcon's ASGI framework during shutdown.

        Args:
            scope: ASGI lifespan scope.
            event: Shutdown event dictionary.
        """
        if self._client is not None:
            logger.info("Closing CiviClient")
            await self._client.close()
            self._client = None

    async def process_request(self, req: Any, resp: Any) -> None:
        """Process incoming request by injecting CiviClient.

        Injects the async CiviCRM client into the request context before
        the request reaches the resource handler.

        Args:
            req: Falcon ASGI Request object.
            resp: Falcon ASGI Response object.
        """
        # Lazy initialization if startup hook wasn't called
        if self._client is None:
            self._client = CiviClient(settings=self.settings)
            logger.debug(
                "CiviClient initialized lazily on first request. "
                "Consider using process_startup for proper lifecycle management.",
            )

        setattr(req.context, self._client_key, self._client)

    async def process_response(
        self,
        req: Any,
        resp: Any,
        resource: Any,
        req_succeeded: bool,
    ) -> None:
        """Process response after resource handler completes.

        Currently a no-op but included for middleware interface completeness.
        Can be extended for logging, metrics, or cleanup tasks.

        Args:
            req: Falcon ASGI Request object.
            resp: Falcon ASGI Response object.
            resource: Resource object that handled the request (may be None).
            req_succeeded: True if no exceptions were raised.
        """
        # No-op - client cleanup handled in process_shutdown

    async def close(self) -> None:
        """Manually close the client.

        This method can be called to manually close the client outside of
        the normal ASGI lifecycle. Useful for testing or graceful shutdown.
        """
        if self._client is not None:
            await self._client.close()
            self._client = None

    def __repr__(self) -> str:
        """Return string representation.

        Returns:
            String representation of the middleware.
        """
        initialized = self._client is not None
        return f"{self.__class__.__name__}(client_key={self._client_key!r}, initialized={initialized})"


def get_civi_middleware(
    app: Any = None,
    settings: CiviSettings | None = None,
    *,
    client_key: str = CIVI_CLIENT_CONTEXT_KEY,
) -> CiviFalconMiddleware | CiviFalconASGIMiddleware:
    """Get the appropriate Civi middleware based on Falcon app type.

    Auto-detects whether the application is WSGI or ASGI and returns
    the corresponding middleware class instance.

    Args:
        app: Optional Falcon application instance for auto-detection.
            If None, returns WSGI middleware by default.
        settings: CiviCRM settings. If None, loaded from environment.
        client_key: Key to store client under in req.context.

    Returns:
        CiviFalconMiddleware for WSGI apps, CiviFalconASGIMiddleware for ASGI apps.

    Example:
        import falcon
        from civicrm_py.contrib.falcon import get_civi_middleware

        # WSGI app
        app = falcon.App()
        middleware = get_civi_middleware(app)  # Returns CiviFalconMiddleware

        # ASGI app
        app = falcon.asgi.App()
        middleware = get_civi_middleware(app)  # Returns CiviFalconASGIMiddleware
    """
    is_asgi = False

    if app is not None:
        # Check if the app is an ASGI app by looking at its module or type name
        app_type = type(app)
        app_module = app_type.__module__
        app_name = app_type.__name__

        # falcon.asgi.App is the ASGI application class
        if "asgi" in app_module.lower() or (app_name == "App" and "asgi" in str(app_module)):
            is_asgi = True

        # Alternative: check for ASGI-specific attributes
        if hasattr(app, "_handle_websocket"):
            is_asgi = True

    if is_asgi:
        return CiviFalconASGIMiddleware(settings=settings, client_key=client_key)
    return CiviFalconMiddleware(settings=settings, client_key=client_key)


def get_client_from_context(context: Any, *, client_key: str = CIVI_CLIENT_CONTEXT_KEY) -> CiviClient | SyncCiviClient:
    """Get the CiviClient from Falcon request context.

    Convenience function to extract the CiviClient from request context
    with proper error handling.

    Args:
        context: Falcon request context (req.context).
        client_key: Key used to store client in context.
            Must match the key used in middleware.

    Returns:
        The CiviClient or SyncCiviClient instance from context.

    Raises:
        RuntimeError: If middleware is not installed or client is not available.

    Example:
        from civicrm_py.contrib.falcon import get_client_from_context

        class ContactResource:
            def on_get(self, req, resp):
                client = get_client_from_context(req.context)
                response = client.get("Contact", limit=10)
                resp.media = {"contacts": response.values}
    """
    client = getattr(context, client_key, None)

    if client is None:
        msg = (
            f"CiviClient not found in req.context.{client_key}. "
            "Ensure CiviFalconMiddleware or CiviFalconASGIMiddleware is installed."
        )
        raise RuntimeError(msg)

    return client


__all__ = [
    "CIVI_CLIENT_CONTEXT_KEY",
    "CiviFalconASGIMiddleware",
    "CiviFalconMiddleware",
    "get_civi_middleware",
    "get_client_from_context",
]
