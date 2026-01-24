"""Django settings integration for civi-py.

This module provides integration with Django's settings system, allowing
CiviCRM configuration to be defined in Django's settings.py.

Django Settings:
    CIVICRM_URL (str, required): Base URL for CiviCRM API v4
        Example: "https://example.org/civicrm/ajax/api4"
    CIVICRM_API_KEY (str, optional): API key for authentication
    CIVICRM_SITE_KEY (str, optional): Site key for some auth modes
    CIVICRM_AUTH_TYPE (str, default: "api_key"): Authentication type
        Options: "api_key", "jwt", "basic"
    CIVICRM_TIMEOUT (int, default: 30): Request timeout in seconds
    CIVICRM_VERIFY_SSL (bool, default: True): Whether to verify SSL certificates
    CIVICRM_DEBUG (bool, default: False): Enable debug logging
    CIVICRM_MAX_RETRIES (int, default: 3): Maximum number of retries
    CIVICRM_JWT_TOKEN (str, optional): JWT token for JWT auth
    CIVICRM_USERNAME (str, optional): Username for basic auth
    CIVICRM_PASSWORD (str, optional): Password for basic auth

Example:
    In Django settings.py:

    >>> CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
    >>> CIVICRM_API_KEY = "your-api-key"
    >>> CIVICRM_SITE_KEY = "your-site-key"

    In your code:

    >>> from civicrm_py.contrib.django.settings import get_civi_settings
    >>> settings = get_civi_settings()

    Or use the DjangoIntegration class:

    >>> from civicrm_py.contrib.django.settings import DjangoIntegration
    >>> integration = DjangoIntegration()
    >>> integration.startup_sync()
    >>> client = integration.get_sync_client()
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, Self

from civicrm_py.contrib.integration import BaseIntegration
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.exceptions import CiviConfigError, CiviIntegrationError

if TYPE_CHECKING:
    from types import ModuleType

logger = logging.getLogger(__name__)

# Type alias for auth types
AuthType = Literal["api_key", "jwt", "basic"]


def _get_django_settings() -> ModuleType:
    """Import and return Django settings module.

    Returns:
        The Django settings module.

    Raises:
        CiviIntegrationError: If Django is not installed or not configured.
    """
    try:
        from django.conf import settings as django_settings
    except ImportError as e:
        msg = "Django is not installed. Install it with: pip install django or pip install civi-py[django]"
        raise CiviIntegrationError(msg) from e

    # Check if Django is properly configured
    if not django_settings.configured:
        msg = (
            "Django settings are not configured. Make sure Django is properly "
            "set up before importing civi-py Django integration."
        )
        raise CiviIntegrationError(msg)

    return django_settings


def get_django_settings() -> dict[str, Any]:
    """Read CiviCRM configuration from Django settings.

    Extracts all CIVICRM_* settings from Django's settings module and
    returns them as a dictionary with lowercase keys (without the CIVICRM_ prefix).

    Returns:
        Dictionary with CiviCRM configuration values:
            - url: Base URL for CiviCRM API
            - api_key: API key (optional)
            - site_key: Site key (optional)
            - auth_type: Authentication type (default: "api_key")
            - timeout: Request timeout (default: 30)
            - verify_ssl: SSL verification (default: True)
            - debug: Debug mode (default: False)
            - max_retries: Max retries (default: 3)
            - jwt_token: JWT token (optional)
            - username: Basic auth username (optional)
            - password: Basic auth password (optional)

    Raises:
        CiviIntegrationError: If Django is not installed or configured.
        CiviConfigError: If required settings (CIVICRM_URL) are missing.

    Example:
        >>> config = get_django_settings()
        >>> print(config["url"])
        "https://example.org/civicrm/ajax/api4"
    """
    django_settings = _get_django_settings()

    # Get URL (required)
    url = getattr(django_settings, "CIVICRM_URL", None)
    if not url:
        msg = (
            "CIVICRM_URL is required in Django settings. "
            "Add CIVICRM_URL = 'https://your-site.org/civicrm/ajax/api4' to settings.py"
        )
        raise CiviConfigError(msg)

    # Get optional settings with defaults
    return {
        "url": url,
        "api_key": getattr(django_settings, "CIVICRM_API_KEY", None),
        "site_key": getattr(django_settings, "CIVICRM_SITE_KEY", None),
        "auth_type": getattr(django_settings, "CIVICRM_AUTH_TYPE", "api_key"),
        "timeout": getattr(django_settings, "CIVICRM_TIMEOUT", 30),
        "verify_ssl": getattr(django_settings, "CIVICRM_VERIFY_SSL", True),
        "debug": getattr(django_settings, "CIVICRM_DEBUG", False),
        "max_retries": getattr(django_settings, "CIVICRM_MAX_RETRIES", 3),
        "jwt_token": getattr(django_settings, "CIVICRM_JWT_TOKEN", None),
        "username": getattr(django_settings, "CIVICRM_USERNAME", None),
        "password": getattr(django_settings, "CIVICRM_PASSWORD", None),
    }


def create_settings() -> CiviSettings:
    """Create CiviSettings instance from Django settings.

    Reads configuration from Django's settings module and creates a
    validated CiviSettings instance.

    Returns:
        CiviSettings instance configured from Django settings.

    Raises:
        CiviIntegrationError: If Django is not installed or configured.
        CiviConfigError: If required settings are missing.
        ValueError: If CiviSettings validation fails (e.g., missing credentials
            for the specified auth_type).

    Example:
        >>> settings = create_settings()
        >>> print(settings.base_url)
        "https://example.org/civicrm/ajax/api4"
    """
    config = get_django_settings()

    return CiviSettings(
        base_url=config["url"],
        api_key=config["api_key"],
        site_key=config["site_key"],
        auth_type=config["auth_type"],
        timeout=config["timeout"],
        verify_ssl=config["verify_ssl"],
        debug=config["debug"],
        max_retries=config["max_retries"],
        jwt_token=config["jwt_token"],
        username=config["username"],
        password=config["password"],
    )


@lru_cache(maxsize=1)
def get_civi_settings() -> CiviSettings:
    """Get cached CiviSettings instance from Django settings.

    This is the primary entry point for getting CiviCRM configuration
    in Django applications. The settings are cached after the first call.

    Returns:
        Cached CiviSettings instance configured from Django settings.

    Raises:
        CiviIntegrationError: If Django is not installed or configured.
        CiviConfigError: If required settings are missing.
        ValueError: If CiviSettings validation fails.

    Example:
        >>> from civicrm_py.contrib.django.settings import get_civi_settings
        >>> settings = get_civi_settings()
        >>> print(settings.base_url)
        "https://example.org/civicrm/ajax/api4"
    """
    return create_settings()


def clear_settings_cache() -> None:
    """Clear the cached Django settings.

    Call this if Django settings change and you need to reload CiviCRM
    configuration. Typically only needed in testing scenarios.

    Example:
        >>> from civicrm_py.contrib.django.settings import clear_settings_cache
        >>> clear_settings_cache()
    """
    get_civi_settings.cache_clear()


class DjangoIntegration(BaseIntegration):
    """Django-specific integration for civi-py.

    Extends BaseIntegration to automatically load configuration from
    Django's settings module. This class is designed for use in Django
    applications and provides sync-first operation by default.

    The integration reads CiviCRM configuration from Django settings
    (CIVICRM_URL, CIVICRM_API_KEY, etc.) and initializes the appropriate
    client.

    Attributes:
        _settings: CiviSettings instance loaded from Django.
        _sync_client: SyncCiviClient for making API requests.

    Example:
        In Django AppConfig:

        >>> # myapp/apps.py
        >>> from django.apps import AppConfig
        >>> from civicrm_py.contrib.django.settings import DjangoIntegration
        >>>
        >>> class MyAppConfig(AppConfig):
        ...     name = "myapp"
        ...     civi_integration: DjangoIntegration | None = None
        ...
        ...     def ready(self) -> None:
        ...         self.civi_integration = DjangoIntegration()
        ...         self.civi_integration.startup_sync()

        In Django views:

        >>> from myapp.apps import MyAppConfig
        >>> def my_view(request):
        ...     client = MyAppConfig.civi_integration.get_sync_client()
        ...     contacts = client.get("Contact", limit=10)
        ...     return render(request, "contacts.html", {"contacts": contacts})

        Or use the context manager:

        >>> with DjangoIntegration() as integration:
        ...     client = integration.get_sync_client()
        ...     contacts = client.get("Contact", limit=10)
    """

    __slots__ = ()

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        is_async: bool = False,
    ) -> None:
        """Initialize Django integration.

        If no settings are provided, configuration is loaded from Django
        settings. By default, the integration runs in sync mode since
        Django is primarily a sync framework.

        Args:
            settings: Optional CiviSettings instance. If None, settings are
                loaded from Django's settings.py using get_civi_settings().
            is_async: Whether to use async mode. Defaults to False for Django.
                Set to True if using Django with ASGI and async views.

        Raises:
            CiviIntegrationError: If Django is not installed or configured.
            CiviConfigError: If required Django settings are missing.
            ValueError: If CiviSettings validation fails.

        Example:
            >>> # Auto-load from Django settings
            >>> integration = DjangoIntegration()
            >>>
            >>> # Or with explicit settings
            >>> settings = CiviSettings(base_url="...", api_key="...")
            >>> integration = DjangoIntegration(settings=settings)
            >>>
            >>> # For Django ASGI with async views
            >>> integration = DjangoIntegration(is_async=True)
        """
        if settings is None:
            settings = get_civi_settings()

        super().__init__(settings=settings, is_async=is_async)
        logger.debug(
            "DjangoIntegration initialized with base_url=%s",
            settings.base_url,
        )

    @classmethod
    def from_django_settings(cls) -> Self:
        """Create integration instance from Django settings.

        Factory method that explicitly creates a new integration from
        Django settings without caching.

        Returns:
            New DjangoIntegration instance.

        Raises:
            CiviIntegrationError: If Django is not installed or configured.
            CiviConfigError: If required Django settings are missing.

        Example:
            >>> integration = DjangoIntegration.from_django_settings()
            >>> integration.startup_sync()
        """
        settings = create_settings()
        return cls(settings=settings)

    def __repr__(self) -> str:
        """Return string representation of the Django integration.

        Returns:
            A string showing the integration status and base URL.
        """
        if self._sync_client is not None:
            status = "sync client initialized"
        elif self._client is not None:
            status = "async client initialized"
        else:
            status = "not initialized"
        return f"<DjangoIntegration status={status!r} base_url={self._settings.base_url!r}>"


__all__ = [
    "AuthType",
    "DjangoIntegration",
    "clear_settings_cache",
    "create_settings",
    "get_civi_settings",
    "get_django_settings",
]
