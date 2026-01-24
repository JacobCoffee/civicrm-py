"""Flask integration for civi-py.

Provides a Flask extension for seamless CiviCRM API v4 integration with:

- CiviFlask extension with init_app() pattern
- Request context integration via g.civi_client
- Flask CLI commands (flask civi-check, flask civi-shell)
- Configuration from app.config['CIVI_*'] or CiviSettings

Quick Start:

    1. Initialize the extension:

        from flask import Flask, g
        from civicrm_py.contrib.flask import CiviFlask

        app = Flask(__name__)
        app.config['CIVI_BASE_URL'] = 'https://example.org/civicrm/ajax/api4'
        app.config['CIVI_API_KEY'] = 'your-api-key'

        civi = CiviFlask(app)

    2. Use in views:

        @app.route('/contacts')
        def list_contacts():
            # Client is available on g.civi_client
            response = g.civi_client.get('Contact', limit=10)
            return {'contacts': response.values}

    3. Use CLI commands:

        $ flask civi-check
        CiviCRM API Status:
          URL: https://example.org/civicrm/ajax/api4
          Status: Connected

        $ flask civi-shell
        >>> client.get("Contact", limit=1)

Application Factory Pattern:

    from flask import Flask
    from civicrm_py.contrib.flask import CiviFlask

    civi = CiviFlask()

    def create_app():
        app = Flask(__name__)
        app.config.from_prefixed_env()
        civi.init_app(app)
        return app

Configuration Options (app.config):

    CIVI_BASE_URL (str, required): CiviCRM API v4 base URL
    CIVI_API_KEY (str, optional): API key for authentication
    CIVI_SITE_KEY (str, optional): Site key for some auth modes
    CIVI_AUTH_TYPE (str, default: "api_key"): Authentication type
    CIVI_TIMEOUT (int, default: 30): Request timeout in seconds
    CIVI_VERIFY_SSL (bool, default: True): SSL certificate verification
    CIVI_DEBUG (bool, default: False): Enable debug logging
    CIVI_MAX_RETRIES (int, default: 3): Maximum retry attempts
    CIVI_USE_THREAD_LOCAL (bool, default: True): Thread-local client storage

Alternative: Direct CiviSettings:

    from civicrm_py.core.config import CiviSettings
    from civicrm_py.contrib.flask import CiviFlask

    settings = CiviSettings(
        base_url='https://example.org/civicrm/ajax/api4',
        api_key='your-api-key',
    )
    civi = CiviFlask(app, settings=settings)

Components:

    CiviFlask: Flask extension class with init_app() pattern
    get_civi_client: Helper to get client from g or request context
    CiviFlaskConfig: Configuration dataclass for the extension
"""

from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

# Check if Flask is available
try:
    from flask import Flask
    from flask import g as flask_g

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

    class Flask:
        """Stub when Flask is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("Flask required: pip install civi-py[flask]")

    class _FlaskGStub:
        """Stub for Flask g object when Flask is not installed."""

        def __getattr__(self, name: str) -> Any:
            raise ImportError("Flask required: pip install civi-py[flask]")

        def __setattr__(self, name: str, value: Any) -> None:
            raise ImportError("Flask required: pip install civi-py[flask]")

    flask_g = _FlaskGStub()

if TYPE_CHECKING:
    from civicrm_py.core.client import SyncCiviClient
    from civicrm_py.core.config import CiviSettings

logger = logging.getLogger(__name__)


def _get_bool(value: str | bool | None, *, default: bool = False) -> bool:
    """Convert a value to boolean.

    Handles string values like 'true', '1', 'yes' from config.

    Args:
        value: Value to convert.
        default: Default if value is None.

    Returns:
        Boolean value.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return default


def _get_int(value: str | int | None, default: int) -> int:
    """Convert a value to integer.

    Args:
        value: Value to convert.
        default: Default if value is None or invalid.

    Returns:
        Integer value.
    """
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@dataclass
class CiviFlaskConfig:
    """Configuration for the Flask CiviCRM extension.

    Controls client lifecycle, CLI commands, and request context behavior.

    Attributes:
        settings: Optional pre-configured CiviSettings. If None, settings
            are loaded from Flask app.config.
        use_thread_local: Use thread-local storage for client instances.
            Recommended for multi-threaded WSGI servers like Gunicorn.
        register_cli: Whether to register CLI commands (civi-check, civi-shell).
        debug: Enable debug logging for the extension.

    Example:
        >>> config = CiviFlaskConfig(
        ...     use_thread_local=True,
        ...     register_cli=True,
        ...     debug=False,
        ... )
        >>> civi = CiviFlask(app, config=config)
    """

    settings: CiviSettings | None = None
    use_thread_local: bool = True
    register_cli: bool = True
    debug: bool = False


class CiviFlask:
    """Flask extension for CiviCRM API integration.

    Provides automatic client lifecycle management, request context integration,
    and CLI commands for CiviCRM API access in Flask applications.

    The extension:
    - Initializes SyncCiviClient on first request or explicit call
    - Attaches client to Flask's g object for request handlers
    - Provides CLI commands for connectivity checks and interactive shell
    - Supports both thread-local and shared client modes
    - Cleans up client on application teardown

    Thread Safety:
        When use_thread_local=True (default), each thread gets its own client
        instance stored in thread-local storage. This is safe for multi-threaded
        WSGI servers like Gunicorn with sync workers.

    Attributes:
        app: The Flask application instance (if initialized with app).
        config: Extension configuration.

    Example:
        Basic usage:

        >>> from flask import Flask, g
        >>> from civicrm_py.contrib.flask import CiviFlask
        >>>
        >>> app = Flask(__name__)
        >>> app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        >>> app.config["CIVI_API_KEY"] = "your-api-key"
        >>>
        >>> civi = CiviFlask(app)
        >>>
        >>> @app.route("/contacts")
        ... def list_contacts():
        ...     response = g.civi_client.get("Contact", limit=10)
        ...     return {"contacts": response.values}

        Application factory pattern:

        >>> from flask import Flask
        >>> from civicrm_py.contrib.flask import CiviFlask
        >>>
        >>> civi = CiviFlask()
        >>>
        >>> def create_app():
        ...     app = Flask(__name__)
        ...     app.config.from_prefixed_env()
        ...     civi.init_app(app)
        ...     return app

        With explicit settings:

        >>> from civicrm_py.core.config import CiviSettings
        >>> settings = CiviSettings(
        ...     base_url="https://example.org/civicrm/ajax/api4",
        ...     api_key="your-api-key",
        ... )
        >>> civi = CiviFlask(app, settings=settings)
    """

    __slots__ = (
        "_app",
        "_client",
        "_config",
        "_local",
        "_lock",
        "_settings",
    )

    def __init__(
        self,
        app: Flask | None = None,
        settings: CiviSettings | None = None,
        *,
        config: CiviFlaskConfig | None = None,
    ) -> None:
        """Initialize the Flask extension.

        Args:
            app: Flask application instance. If provided, init_app() is called
                automatically. If None, call init_app() later.
            settings: Pre-configured CiviSettings. If None, settings are loaded
                from Flask app.config when init_app() is called.
            config: Extension configuration. If None, uses defaults.
        """
        self._app: Flask | None = None
        self._config = config or CiviFlaskConfig()
        self._settings: CiviSettings | None = settings or self._config.settings
        self._lock = threading.Lock()
        self._local = threading.local()
        self._client: SyncCiviClient | None = None

        if self._config.debug:
            logging.getLogger("civicrm_py").setLevel(logging.DEBUG)

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Initialize the extension with a Flask application.

        Registers the extension with the Flask app, sets up lifecycle hooks,
        and optionally registers CLI commands.

        This method supports the Flask application factory pattern where
        the extension is created without an app, then initialized later.

        Args:
            app: Flask application instance to initialize with.

        Example:
            >>> civi = CiviFlask()
            >>> app = Flask(__name__)
            >>> civi.init_app(app)
        """
        self._app = app

        # Register extension with Flask
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["civi"] = self

        # Load settings from app.config if not provided
        if self._settings is None:
            self._settings = self._load_settings_from_config(app)

        # Register request hooks
        app.before_request(self._before_request)
        app.teardown_appcontext(self._teardown_appcontext)

        # Register CLI commands if enabled
        if self._config.register_cli:
            self._register_cli_commands(app)

        # Register cleanup on process exit
        atexit.register(self._cleanup)

        logger.info(
            "CiviFlask initialized for %s",
            self._settings.base_url if self._settings else "unknown",
        )

    def _load_settings_from_config(self, app: Flask) -> CiviSettings:
        """Load CiviSettings from Flask app.config.

        Maps Flask config keys (CIVI_*) to CiviSettings parameters.

        Args:
            app: Flask application instance.

        Returns:
            CiviSettings instance configured from app.config.

        Raises:
            ValueError: If required CIVI_BASE_URL is missing.
        """
        from civicrm_py.core.config import CiviSettings

        base_url = app.config.get("CIVI_BASE_URL")
        if not base_url:
            # Try environment variable as fallback
            import os

            base_url = os.environ.get("CIVI_BASE_URL")
            if not base_url:
                msg = "CIVI_BASE_URL must be set in app.config or environment"
                raise ValueError(msg)

        auth_type: Literal["api_key", "jwt", "basic"] = app.config.get("CIVI_AUTH_TYPE", "api_key")

        return CiviSettings(
            base_url=base_url,
            api_key=app.config.get("CIVI_API_KEY"),
            site_key=app.config.get("CIVI_SITE_KEY"),
            timeout=_get_int(app.config.get("CIVI_TIMEOUT"), 30),
            verify_ssl=_get_bool(app.config.get("CIVI_VERIFY_SSL"), default=True),
            debug=_get_bool(app.config.get("CIVI_DEBUG"), default=False),
            max_retries=_get_int(app.config.get("CIVI_MAX_RETRIES"), 3),
            auth_type=auth_type,
            jwt_token=app.config.get("CIVI_JWT_TOKEN"),
            username=app.config.get("CIVI_USERNAME"),
            password=app.config.get("CIVI_PASSWORD"),
        )

    def _register_cli_commands(self, app: Flask) -> None:
        """Register Flask CLI commands.

        Args:
            app: Flask application instance.
        """
        from civicrm_py.contrib.flask.cli import civi_check_command, civi_shell_command

        app.cli.add_command(civi_check_command)
        app.cli.add_command(civi_shell_command)
        logger.debug("Registered CLI commands: civi-check, civi-shell")

    def _before_request(self) -> None:
        """Before-request hook to attach client to g.

        Called before each request to make the CiviCRM client available
        via Flask's g object.
        """
        flask_g.civi_client = self.get_client()

    def _teardown_appcontext(self, exception: BaseException | None = None) -> None:
        """Teardown hook for app context cleanup.

        Called after each request to perform any necessary cleanup.
        The actual client cleanup is handled by _cleanup() at process exit.

        Args:
            exception: Exception that occurred during request, if any.
        """
        # We don't close the client on each request - it's reused across requests.
        # Thread-local clients are cleaned up when threads terminate.
        # The process-level cleanup is handled by atexit.
        _ = exception  # Unused, but required by Flask's teardown signature

    def _cleanup(self) -> None:
        """Clean up all client instances.

        Called via atexit when the Flask process terminates.
        Closes both shared and thread-local client instances.
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

    @property
    def settings(self) -> CiviSettings:
        """Get the CiviCRM settings.

        Returns:
            CiviSettings instance.

        Raises:
            RuntimeError: If extension is not initialized.
        """
        if self._settings is None:
            msg = "CiviFlask not initialized. Call init_app() first."
            raise RuntimeError(msg)
        return self._settings

    def get_client(self) -> SyncCiviClient:
        """Get or create a SyncCiviClient instance.

        If use_thread_local is True (default), returns a thread-local client.
        Otherwise, returns a shared client instance.

        Returns:
            SyncCiviClient instance.

        Raises:
            RuntimeError: If extension is not initialized.
        """
        if self._settings is None:
            msg = "CiviFlask not initialized. Call init_app() first."
            raise RuntimeError(msg)

        if self._config.use_thread_local:
            return self._get_thread_local_client()
        return self._get_shared_client()

    def _get_thread_local_client(self) -> SyncCiviClient:
        """Get or create a thread-local client instance.

        Returns:
            Thread-local SyncCiviClient instance.
        """
        from civicrm_py.core.client import SyncCiviClient

        client = getattr(self._local, "client", None)
        if client is None:
            client = SyncCiviClient(settings=self._settings)
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
        from civicrm_py.core.client import SyncCiviClient

        client = self._client
        if client is None:
            with self._lock:
                # Double-check after acquiring lock
                client = self._client
                if client is None:
                    client = SyncCiviClient(settings=self._settings)
                    self._client = client
                    logger.debug("Created shared CiviCRM client")
        return client

    def __repr__(self) -> str:
        """Return string representation.

        Returns:
            String representation of the extension.
        """
        url = self._settings.base_url if self._settings else "not initialized"
        return f"{self.__class__.__name__}(url={url!r})"


def get_civi_client() -> SyncCiviClient:
    """Get the CiviCRM client from the current request context.

    Convenience function to retrieve the client from Flask's g object.
    This is the preferred way to access the client in view functions.

    Returns:
        SyncCiviClient instance.

    Raises:
        RuntimeError: If called outside of a request context or if the
            extension is not initialized.

    Example:
        >>> from flask import Flask
        >>> from civicrm_py.contrib.flask import CiviFlask, get_civi_client
        >>>
        >>> app = Flask(__name__)
        >>> CiviFlask(app)
        >>>
        >>> @app.route("/contacts")
        ... def list_contacts():
        ...     client = get_civi_client()
        ...     response = client.get("Contact", limit=10)
        ...     return {"contacts": response.values}
    """
    client = getattr(flask_g, "civi_client", None)
    if client is None:
        msg = "CiviCRM client not available. Ensure CiviFlask is initialized and you are within a request context."
        raise RuntimeError(msg)
    return client


__all__ = [
    "CiviFlask",
    "CiviFlaskConfig",
    "civi_check_command",
    "civi_shell_command",
    "get_civi_client",
]

# Re-export CLI commands for convenience
from civicrm_py.contrib.flask.cli import civi_check_command, civi_shell_command  # noqa: E402
