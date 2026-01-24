"""Bottle integration for civi-py.

Provides a lightweight Bottle plugin for CiviCRM API access with:
- CiviBottlePlugin for automatic client lifecycle management
- Keyword argument injection for route handlers
- Proper plugin API implementation (setup, apply, close)

Quick Start:
    >>> from bottle import Bottle, run
    >>> from civicrm_py.contrib.bottle import CiviBottlePlugin
    >>>
    >>> app = Bottle()
    >>> app.install(CiviBottlePlugin())
    >>>
    >>> @app.get("/contacts")
    ... def list_contacts(civi_client):
    ...     response = civi_client.get("Contact", limit=10)
    ...     return {"contacts": response.values}
    >>>
    >>> run(app, host="localhost", port=8080)

With Configuration:
    >>> from civicrm_py.core.config import CiviSettings
    >>> from civicrm_py.contrib.bottle import CiviBottlePlugin
    >>>
    >>> settings = CiviSettings(
    ...     base_url="https://example.org/civicrm/ajax/api4",
    ...     api_key="your-api-key",
    ... )
    >>> plugin = CiviBottlePlugin(settings=settings, keyword="civi")
    >>> app.install(plugin)
    >>>
    >>> @app.get("/contacts")
    ... def list_contacts(civi):
    ...     return civi.get("Contact", limit=10).values

Environment Variables:
    Set these environment variables for automatic configuration:
    - CIVI_BASE_URL: CiviCRM API base URL
    - CIVI_API_KEY: API key for authentication
    - CIVI_SITE_KEY: Optional site key
    - CIVI_TIMEOUT: Request timeout (default: 30)
    - CIVI_VERIFY_SSL: Verify SSL certificates (default: true)

Thread Safety:
    The plugin creates a shared SyncCiviClient instance that is safe for
    use across multiple threads when used with threaded WSGI servers.
    The underlying httpx client handles connection pooling appropriately.

Alternative: WSGI Middleware:
    For middleware-based integration, use CiviWSGIMiddleware instead:
    >>> from civicrm_py.contrib.wsgi import CiviWSGIMiddleware
    >>> app = CiviWSGIMiddleware(app)
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from civicrm_py.core.client import SyncCiviClient
from civicrm_py.core.config import CiviSettings


def _check_bottle_available() -> bool:
    """Check if Bottle is available.

    Returns:
        True if Bottle is installed, False otherwise.
    """
    try:
        import bottle  # noqa: F401
    except ImportError:
        return False
    else:
        return True


BOTTLE_AVAILABLE = _check_bottle_available()


# Stub classes for when Bottle is not installed
# These provide type information to the type checker
class _BottleStub:
    """Stub for Bottle app when Bottle is not installed."""

    plugins: list[Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("bottle required: pip install civi-py[bottle]")


class _RouteStub:
    """Stub for Bottle Route when Bottle is not installed."""

    rule: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise ImportError("bottle required: pip install civi-py[bottle]")


if TYPE_CHECKING:
    from collections.abc import Callable

    from bottle import Bottle, Route
else:
    if BOTTLE_AVAILABLE:
        from bottle import Bottle, Route
    else:
        Bottle = _BottleStub
        Route = _RouteStub

__all__ = [
    "BOTTLE_AVAILABLE",
    "CiviBottlePlugin",
]

logger = logging.getLogger(__name__)


class CiviBottlePlugin:
    """Bottle plugin for CiviCRM client integration.

    Implements Bottle's plugin API v2 to provide automatic client injection
    into route handlers. The plugin injects a SyncCiviClient instance as a
    keyword argument to routes that accept the configured keyword parameter.

    Attributes:
        name: Plugin name used by Bottle for identification.
        api: Bottle plugin API version (2 for modern Bottle).
        keyword: Keyword argument name for client injection.

    Features:
        - Lazy client initialization on first request
        - Keyword argument injection for route handlers
        - Clean shutdown via close() method
        - Compatible with Bottle's plugin management (install/uninstall)

    Args:
        settings: CiviCRM settings. If None, settings are loaded from environment.
        keyword: Name of the keyword argument to inject. Defaults to "civi_client".

    Example:
        >>> from bottle import Bottle
        >>> from civicrm_py.contrib.bottle import CiviBottlePlugin
        >>>
        >>> app = Bottle()
        >>> app.install(CiviBottlePlugin())
        >>>
        >>> @app.get("/contacts")
        ... def get_contacts(civi_client):
        ...     response = civi_client.get("Contact", limit=10)
        ...     return {"contacts": response.values}
        >>>
        >>> @app.get("/activities")
        ... def get_activities(civi_client):
        ...     response = civi_client.get("Activity", limit=10)
        ...     return {"activities": response.values}

    Example with custom keyword:
        >>> plugin = CiviBottlePlugin(keyword="civi")
        >>> app.install(plugin)
        >>>
        >>> @app.get("/contacts")
        ... def get_contacts(civi):  # Uses "civi" instead of "civi_client"
        ...     return civi.get("Contact", limit=10).values
    """

    # Bottle plugin API attributes
    name: str = "civi"
    """Plugin name for Bottle's plugin registry."""

    api: int = 2
    """Bottle plugin API version (v2 for keyword injection support)."""

    __slots__ = (
        "_client",
        "_settings",
        "keyword",
    )

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        keyword: str = "civi_client",
    ) -> None:
        """Initialize the Bottle plugin.

        Args:
            settings: CiviCRM settings. If None, loaded from environment variables.
            keyword: Keyword argument name for client injection in route handlers.
        """
        self._settings = settings
        self._client: SyncCiviClient | None = None
        self.keyword = keyword

    @property
    def settings(self) -> CiviSettings:
        """Get the CiviCRM settings, loading from environment if needed.

        Returns:
            CiviSettings instance.
        """
        if self._settings is None:
            self._settings = CiviSettings.from_env()
        return self._settings

    @property
    def client(self) -> SyncCiviClient:
        """Get the CiviCRM client, creating it if needed.

        Returns:
            SyncCiviClient instance.
        """
        if self._client is None:
            self._client = SyncCiviClient(settings=self.settings)
            logger.debug("Created CiviCRM client for Bottle plugin")
        return self._client

    def setup(self, app: Bottle) -> None:
        """Called when the plugin is installed on an application.

        This is part of Bottle's plugin API v2. The client is created lazily
        on first use rather than during setup to support deferred configuration.

        Args:
            app: The Bottle application instance.

        Example:
            >>> app = Bottle()
            >>> plugin = CiviBottlePlugin()
            >>> app.install(plugin)  # Calls setup(app) internally
        """
        # Verify no conflicting plugin with same name
        for other in app.plugins:
            if other is not self and getattr(other, "name", None) == self.name:
                logger.warning(
                    "Another plugin with name %r is already installed. Consider using a unique name.",
                    self.name,
                )

        logger.debug(
            "CiviBottlePlugin installed with keyword=%r",
            self.keyword,
        )

    def apply(
        self,
        callback: Callable[..., Any],
        route: Route,
    ) -> Callable[..., Any]:
        """Apply the plugin to a route callback.

        This is part of Bottle's plugin API v2. Wraps route callbacks to
        inject the CiviCRM client as a keyword argument if the callback
        accepts the configured keyword parameter.

        Args:
            callback: The original route callback function.
            route: The Route object (contains route metadata).

        Returns:
            Wrapped callback if it accepts the keyword, original callback otherwise.

        Example:
            # Route that accepts civi_client gets it injected
            @app.get("/contacts")
            def with_client(civi_client):
                return civi_client.get("Contact", limit=10).values

            # Route without civi_client parameter is unchanged
            @app.get("/health")
            def health_check():
                return {"status": "ok"}
        """
        # Get the callback signature to check for keyword parameter
        # Handle wrapped functions (e.g., from decorators)
        try:
            sig = inspect.signature(callback)
        except (ValueError, TypeError):
            # Cannot inspect signature, return callback unchanged
            logger.debug(
                "Cannot inspect signature for route %s, skipping injection",
                route.rule if route else "unknown",
            )
            return callback

        # Check if callback accepts our keyword argument
        if self.keyword not in sig.parameters:
            # Callback doesn't want the client, return unchanged
            return callback

        # Check if the parameter can accept a positional or keyword argument
        param = sig.parameters[self.keyword]
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            # For *args or **kwargs, don't inject
            return callback

        # Create wrapper that injects the client
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Wrapper that injects CiviCRM client into route handler."""
            kwargs[self.keyword] = self.client
            return callback(*args, **kwargs)

        # Preserve function metadata
        wrapper.__name__ = getattr(callback, "__name__", "wrapped")
        wrapper.__doc__ = getattr(callback, "__doc__", None)

        logger.debug(
            "Injecting %r into route %s",
            self.keyword,
            route.rule if route else "unknown",
        )

        return wrapper

    def close(self) -> None:
        """Close the plugin and release resources.

        Should be called during application shutdown to properly clean up
        HTTP connections and other resources.

        This is part of Bottle's plugin API v2.

        Example:
            >>> import atexit
            >>> plugin = CiviBottlePlugin()
            >>> app.install(plugin)
            >>> atexit.register(plugin.close)
        """
        if self._client is not None:
            try:
                self._client.close()
                logger.debug("Closed CiviCRM client")
            except Exception:
                logger.exception("Error closing CiviCRM client")
            finally:
                self._client = None

    def __repr__(self) -> str:
        """Return string representation of the plugin.

        Returns:
            String representation with plugin configuration.
        """
        return f"{self.__class__.__name__}(keyword={self.keyword!r})"
