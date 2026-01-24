"""Generic WSGI middleware for civi-py.

Provides CiviCRM client integration for any WSGI-compatible framework including
Flask, Bottle, Falcon (WSGI mode), and other WSGI applications.

Example usage with Flask:
    from flask import Flask
    from civicrm_py.contrib.wsgi import CiviWSGIMiddleware
    from civicrm_py.core.config import CiviSettings

    app = Flask(__name__)
    settings = CiviSettings(base_url="https://example.org/civicrm/ajax/api4", api_key="...")
    app.wsgi_app = CiviWSGIMiddleware(app.wsgi_app, settings)

    @app.route("/contacts")
    def list_contacts():
        from flask import request
        client = request.environ["civi.client"]
        return client.get("Contact", limit=10).values

Example usage with Bottle:
    from bottle import Bottle, request
    from civicrm_py.contrib.wsgi import CiviWSGIMiddleware

    app = Bottle()
    app = CiviWSGIMiddleware(app)  # Uses settings from environment

    @app.route("/contacts")
    def list_contacts():
        client = request.environ["civi.client"]
        return client.get("Contact", limit=10).values
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, MutableMapping
from typing import Any

from civicrm_py.core.client import SyncCiviClient
from civicrm_py.core.config import CiviSettings

__all__ = [
    "CiviWSGIMiddleware",
    "StartResponse",
    "WSGIApplication",
    "WSGIEnviron",
    "get_client_from_environ",
]

logger = logging.getLogger(__name__)

# WSGI type definitions
WSGIEnviron = MutableMapping[str, Any]
"""WSGI environ dictionary type."""

StartResponse = Callable[[str, list[tuple[str, str]]], Callable[[bytes], None]]
"""WSGI start_response callable type."""

WSGIApplication = Callable[[WSGIEnviron, StartResponse], Iterable[bytes]]
"""WSGI application callable type."""


def get_client_from_environ(
    environ: WSGIEnviron,
    key: str = "civi.client",
) -> SyncCiviClient:
    """Get the CiviCRM client from WSGI environ.

    Args:
        environ: WSGI environ dictionary.
        key: Key to look up client under.

    Returns:
        SyncCiviClient instance.

    Raises:
        KeyError: If client is not found in environ.

    Example:
        from flask import request
        from civicrm_py.contrib.wsgi import get_client_from_environ

        client = get_client_from_environ(request.environ)
        contacts = client.get("Contact", limit=10)
    """
    client = environ.get(key)
    if client is None:
        msg = f"CiviCRM client not found in environ['{key}']. Ensure CiviWSGIMiddleware is configured."
        raise KeyError(msg)
    if not isinstance(client, SyncCiviClient):
        msg = f"Expected SyncCiviClient, got {type(client).__name__}"
        raise TypeError(msg)
    return client


class CiviWSGIMiddleware:
    """WSGI middleware for CiviCRM client integration.

    This middleware injects a SyncCiviClient instance into the WSGI environ
    dictionary, making it available to request handlers. The client is created
    lazily on first request and supports thread-local storage for thread-safety.

    Features:
        - Lazy client initialization on first request
        - Thread-local client support for multi-threaded WSGI servers
        - Configurable environ key
        - Clean shutdown via close() method

    Thread Safety:
        When use_thread_local=True (default), each thread gets its own client
        instance stored in thread-local storage. This is safe for multi-threaded
        WSGI servers like Gunicorn with sync workers.

        When use_thread_local=False, a single shared client is used across all
        threads. This may be appropriate for single-threaded environments or
        when using async workers.

    Args:
        app: The WSGI application to wrap.
        settings: CiviCRM settings. If None, settings are loaded from environment.
        client_key: Key to store client under in environ. Defaults to "civi.client".
        use_thread_local: If True, use thread-local storage for clients.
            Defaults to True for thread safety.

    Example:
        from flask import Flask
        from civicrm_py.contrib.wsgi import CiviWSGIMiddleware
        from civicrm_py.core.config import CiviSettings

        app = Flask(__name__)
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="your-api-key",
        )
        app.wsgi_app = CiviWSGIMiddleware(app.wsgi_app, settings)

        # In request handlers:
        @app.route("/contacts")
        def list_contacts():
            from flask import request
            client = request.environ["civi.client"]
            response = client.get("Contact", limit=10)
            return {"contacts": response.values}
    """

    __slots__ = (
        "_app",
        "_client",
        "_client_key",
        "_local",
        "_lock",
        "_settings",
        "_use_thread_local",
    )

    def __init__(
        self,
        app: WSGIApplication,
        settings: CiviSettings | None = None,
        *,
        client_key: str = "civi.client",
        use_thread_local: bool = True,
    ) -> None:
        """Initialize the WSGI middleware.

        Args:
            app: The WSGI application to wrap.
            settings: CiviCRM settings. If None, loaded from environment variables.
            client_key: Key to store client under in environ.
            use_thread_local: Use thread-local storage for client instances.
        """
        self._app = app
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

    def __call__(
        self,
        environ: WSGIEnviron,
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        """Handle WSGI request.

        Injects the CiviCRM client into the environ dictionary before
        passing the request to the wrapped application.

        Args:
            environ: WSGI environ dictionary.
            start_response: WSGI start_response callable.

        Returns:
            Response iterable from the wrapped application.
        """
        # Inject client into environ
        environ[self._client_key] = self._get_client()

        # Call wrapped application
        return self._app(environ, start_response)

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
