"""Quart integration for civi-py.

Provides first-class Quart support with:
- CiviQuart extension class following Quart/Flask extension patterns
- Async g.civi_client integration for request-scoped client access
- Application factory support via init_app() pattern
- Lifecycle management with before_serving/after_serving hooks

Quart is an async Flask alternative built on ASGI, so this integration
uses the async CiviClient for optimal performance.

Quick Start:
    >>> from quart import Quart, g
    >>> from civicrm_py.contrib.quart import CiviQuart
    >>>
    >>> app = Quart(__name__)
    >>> civi = CiviQuart(app)
    >>>
    >>> @app.route("/contacts")
    ... async def get_contacts():
    ...     response = await g.civi_client.get("Contact", limit=10)
    ...     return {"contacts": response.values}

Application Factory Pattern:
    >>> # In extensions.py
    >>> from civicrm_py.contrib.quart import CiviQuart
    >>> civi = CiviQuart()
    >>>
    >>> # In app.py
    >>> def create_app():
    ...     app = Quart(__name__)
    ...     civi.init_app(app)
    ...     return app

With Custom Settings:
    >>> from civicrm_py.core.config import CiviSettings
    >>> from civicrm_py.contrib.quart import CiviQuart
    >>>
    >>> settings = CiviSettings(
    ...     base_url="https://example.org/civicrm/ajax/api4",
    ...     api_key="your-api-key",
    ... )
    >>> civi = CiviQuart(app, settings=settings)

Accessing the Client:
    The CiviClient is available via Quart's `g` object in request handlers:

    >>> @app.route("/contacts/<int:contact_id>")
    ... async def get_contact(contact_id: int):
    ...     response = await g.civi_client.get(
    ...         "Contact",
    ...         where=[["id", "=", contact_id]],
    ...     )
    ...     if not response.values:
    ...         abort(404)
    ...     return response.values[0]

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

if TYPE_CHECKING:
    from quart import Quart

    from civicrm_py.core.client import CiviClient
    from civicrm_py.core.config import CiviSettings


def _check_quart_available() -> bool:
    """Check if Quart is available.

    Returns:
        True if Quart is installed, False otherwise.
    """
    try:
        import quart  # noqa: F401
    except ImportError:
        return False
    else:
        return True


QUART_AVAILABLE = _check_quart_available()


# Stub classes for when Quart is not installed
# These provide type information to the type checker
class _QuartStub:
    """Stub for Quart app when Quart is not installed."""

    name: str
    extensions: dict[str, Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("quart required: pip install civi-py[quart]")

    def before_serving(self, func: Any) -> Any:
        raise ImportError("quart required: pip install civi-py[quart]")

    def after_serving(self, func: Any) -> Any:
        raise ImportError("quart required: pip install civi-py[quart]")

    def before_request(self, func: Any) -> Any:
        raise ImportError("quart required: pip install civi-py[quart]")


class _QuartGlobalsStub:
    """Stub for Quart's g object when Quart is not installed."""

    civi_client: Any

    def __getattr__(self, name: str) -> Any:
        raise ImportError("quart required: pip install civi-py[quart]")

    def __setattr__(self, name: str, value: Any) -> None:
        raise ImportError("quart required: pip install civi-py[quart]")


def _get_quart_g() -> Any:
    """Get Quart's g object, or stub if not available.

    Returns:
        Quart's g object or a stub instance.
    """
    if QUART_AVAILABLE:
        from quart import g

        return g
    return _QuartGlobalsStub()


logger = logging.getLogger("civicrm_py.contrib.quart")


class CiviQuart:
    """Quart extension for CiviCRM API integration.

    Provides automatic client lifecycle management and request-scoped
    client injection via Quart's g object, following standard Quart/Flask
    extension patterns.

    The extension:
    - Initializes CiviClient on application startup (before_serving)
    - Injects client into g.civi_client before each request
    - Closes client on application shutdown (after_serving)

    Attributes:
        settings: CiviCRM client configuration settings.
        client: The CiviClient instance (available after startup).

    Example:
        Direct initialization:

        >>> from quart import Quart, g
        >>> from civicrm_py.contrib.quart import CiviQuart
        >>>
        >>> app = Quart(__name__)
        >>> civi = CiviQuart(app)
        >>>
        >>> @app.route("/contacts")
        ... async def list_contacts():
        ...     response = await g.civi_client.get("Contact", limit=10)
        ...     return {"contacts": response.values}

        Application factory pattern:

        >>> civi = CiviQuart()
        >>>
        >>> def create_app():
        ...     app = Quart(__name__)
        ...     civi.init_app(app)
        ...     return app

        With custom settings:

        >>> from civicrm_py.core.config import CiviSettings
        >>>
        >>> settings = CiviSettings(
        ...     base_url="https://crm.example.org/civicrm/ajax/api4",
        ...     api_key="secret-key",
        ... )
        >>> civi = CiviQuart(app, settings=settings)
    """

    __slots__ = ("_app", "_client", "_settings")

    def __init__(
        self,
        app: Quart | None = None,
        settings: CiviSettings | None = None,
    ) -> None:
        """Initialize the CiviQuart extension.

        Args:
            app: Quart application instance. If provided, init_app() is called
                automatically. If None, you must call init_app() manually.
            settings: CiviCRM client settings. If None, settings will be loaded
                from environment variables on startup.
        """
        self._settings = settings
        self._client: CiviClient | None = None
        self._app: Quart | None = None

        if app is not None:
            self.init_app(app)

    @property
    def settings(self) -> CiviSettings | None:
        """Get the configured CiviSettings.

        Returns:
            CiviSettings if configured, None if using environment variables.
        """
        return self._settings

    @property
    def client(self) -> CiviClient | None:
        """Get the CiviClient instance.

        Returns:
            The CiviClient if initialized, None before startup.

        Note:
            Prefer using g.civi_client in request handlers for proper
            request scoping. This property is useful for accessing the
            client outside of request context (e.g., in CLI commands).
        """
        return self._client

    def init_app(self, app: Quart) -> None:
        """Initialize the extension with a Quart application.

        Registers lifecycle hooks and request callbacks with the application.
        This method supports the application factory pattern.

        Args:
            app: Quart application instance to configure.

        Example:
            >>> civi = CiviQuart()
            >>> app = Quart(__name__)
            >>> civi.init_app(app)
        """
        self._app = app

        # Register lifecycle hooks
        app.before_serving(self._startup)
        app.after_serving(self._shutdown)

        # Inject client into g before each request
        app.before_request(self._inject_client)

        # Store extension instance on app for access
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["civi"] = self

        logger.debug("CiviQuart extension registered with app %s", app.name)

    async def _startup(self) -> None:
        """Initialize CiviClient on application startup.

        Creates a new CiviClient instance using the configured settings.
        If no settings were provided, loads from environment variables.

        This method is registered as a before_serving hook.
        """
        if self._client is not None:
            logger.warning("CiviClient already initialized, skipping startup")
            return

        # Import here to avoid circular imports and allow lazy loading
        from civicrm_py.core.client import CiviClient
        from civicrm_py.core.config import CiviSettings

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
        """Close CiviClient on application shutdown.

        Releases any resources held by the client (HTTP connections, etc.).

        This method is registered as an after_serving hook.
        """
        if self._client is not None:
            logger.info("Closing CiviClient")
            await self._client.close()
            self._client = None

    async def _inject_client(self) -> None:
        """Inject CiviClient into Quart's g object.

        Makes the client available as g.civi_client in request handlers.

        This method is registered as a before_request hook.

        Raises:
            RuntimeError: If called before the client is initialized.
        """
        if self._client is None:
            # This shouldn't happen if lifecycle hooks are working correctly,
            # but handle it gracefully
            logger.warning(
                "CiviClient not initialized when injecting into request. This may indicate a lifecycle issue.",
            )
            # Initialize lazily to be resilient
            await self._startup()

        g = _get_quart_g()
        g.civi_client = self._client

    def __repr__(self) -> str:
        """Return string representation of the extension.

        Returns:
            String representation showing initialization state.
        """
        state = "initialized" if self._client is not None else "not initialized"
        app_name = self._app.name if self._app is not None else "no app"
        return f"CiviQuart({app_name}, {state})"


def get_civi_client() -> CiviClient:
    """Get CiviClient from the current request context.

    Convenience function to retrieve the CiviClient from Quart's g object
    with proper error handling.

    Returns:
        The CiviClient instance from the current request context.

    Raises:
        RuntimeError: If CiviQuart extension is not initialized or
            called outside of request context.

    Example:
        >>> from civicrm_py.contrib.quart import get_civi_client
        >>>
        >>> @app.route("/contacts")
        ... async def list_contacts():
        ...     client = get_civi_client()
        ...     response = await client.get("Contact", limit=10)
        ...     return {"contacts": response.values}
    """
    g = _get_quart_g()
    client = getattr(g, "civi_client", None)
    if client is None:
        msg = (
            "CiviClient not found in request context. "
            "Ensure CiviQuart extension is initialized and this is called "
            "within a request context."
        )
        raise RuntimeError(msg)

    return client


__all__ = [
    "CiviQuart",
    "QUART_AVAILABLE",
    "get_civi_client",
]
