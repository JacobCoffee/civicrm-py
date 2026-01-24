"""Django application configuration for civi-py.

Provides the CiviConfig AppConfig class that handles:
- Application registration with Django
- Startup initialization via ready() hook
- CiviCRM client lifecycle management

Example:
    Add to INSTALLED_APPS in your Django settings:

        INSTALLED_APPS = [
            # ...
            'civicrm_py.contrib.django',
        ]
"""

from __future__ import annotations

import atexit
import logging
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from civicrm_py.contrib.integration import BaseIntegration

logger = logging.getLogger(__name__)


class CiviConfig:
    """Django AppConfig for CiviCRM integration.

    This AppConfig handles initialization and shutdown of the CiviCRM client
    during Django's application lifecycle.

    The ready() hook initializes the client when Django starts, and an atexit
    handler ensures proper cleanup when the application terminates.

    Attributes:
        name: The full Python path to the application.
        verbose_name: Human-readable name for the application.
        default_auto_field: Default primary key field type for models.
        integration: The BaseIntegration instance managing the CiviCRM client.

    Example:
        The app is configured automatically when added to INSTALLED_APPS:

            INSTALLED_APPS = [
                'django.contrib.admin',
                'django.contrib.auth',
                # ...
                'civicrm_py.contrib.django',
            ]

        Configure CiviCRM settings in your Django settings.py:

            CIVICRM_URL = 'https://example.org/civicrm/ajax/api4'
            CIVICRM_API_KEY = 'your-api-key'
            CIVICRM_SITE_KEY = 'your-site-key'  # optional
    """

    name: ClassVar[str] = "civicrm_py.contrib.django"
    verbose_name: ClassVar[str] = "CiviCRM Integration"
    default_auto_field: ClassVar[str] = "django.db.models.BigAutoField"

    # Class-level integration instance (shared across requests)
    _integration: ClassVar[BaseIntegration | None] = None
    _initialized: ClassVar[bool] = False

    def __init__(self, app_name: str | None = None, app_module: object | None = None) -> None:
        """Initialize the AppConfig.

        Args:
            app_name: The full Python path to the application.
            app_module: The application module (for Django compatibility).
        """
        # Django 5+ compatibility - accept standard AppConfig init signature
        self._app_name = app_name or self.name
        self._app_module = app_module

    def ready(self) -> None:
        """Initialize CiviCRM integration when Django starts.

        This method is called by Django when the application is ready.
        It initializes the sync CiviCRM client for use throughout the
        application lifecycle.

        The initialization is guarded to prevent double-initialization
        in development servers with auto-reload enabled.

        Note:
            - Uses sync client since Django is WSGI-based (sync by default)
            - Registers atexit handler for cleanup
            - Logs initialization status for debugging
        """
        if CiviConfig._initialized:
            logger.debug("CiviConfig already initialized, skipping")
            return

        try:
            self._initialize_integration()
            CiviConfig._initialized = True
            logger.info("CiviCRM integration initialized successfully")
        except Exception:
            logger.exception("Failed to initialize CiviCRM integration")
            raise

    def _initialize_integration(self) -> None:
        """Initialize the BaseIntegration with settings from Django.

        Loads settings from Django's CIVICRM_* settings and creates
        the integration instance with sync client mode.
        """
        from civicrm_py.contrib.django.settings import DjangoIntegration

        # Create DjangoIntegration which auto-loads from Django settings
        integration = DjangoIntegration()
        integration.startup_sync()

        CiviConfig._integration = integration

        # Register cleanup on process exit
        atexit.register(self._shutdown_integration)

    @classmethod
    def _shutdown_integration(cls) -> None:
        """Shutdown the CiviCRM integration cleanly.

        Called via atexit when the Django process terminates.
        Closes the sync client and releases resources.
        """
        if cls._integration is not None:
            try:
                cls._integration.shutdown_sync()
                logger.debug("CiviCRM integration shutdown complete")
            except Exception:
                logger.exception("Error during CiviCRM integration shutdown")
            finally:
                cls._integration = None
                cls._initialized = False

    @classmethod
    def get_integration(cls) -> BaseIntegration:
        """Get the initialized BaseIntegration instance.

        Returns:
            The BaseIntegration instance managing the CiviCRM client.

        Raises:
            RuntimeError: If integration is not initialized.

        Example:
            >>> from civicrm_py.contrib.django import CiviConfig
            >>> integration = CiviConfig.get_integration()
            >>> client = integration.get_sync_client()
        """
        if cls._integration is None:
            msg = "CiviCRM integration not initialized. Ensure 'civicrm_py.contrib.django' is in INSTALLED_APPS."
            raise RuntimeError(msg)
        return cls._integration


# Django expects an AppConfig subclass, so we need to inherit from django.apps.AppConfig
# when Django is available. This try/except pattern allows the module to be imported
# even when Django is not installed (for documentation builds, type checking, etc.)
try:
    from django.apps import AppConfig as DjangoAppConfig

    class CiviAppConfig(DjangoAppConfig, CiviConfig):
        """Django AppConfig for CiviCRM integration.

        This is the actual AppConfig class that Django uses. It inherits from
        both Django's AppConfig and our CiviConfig to provide Django compatibility
        while keeping our custom initialization logic.

        Example:
            Add to INSTALLED_APPS:

                INSTALLED_APPS = [
                    'civicrm_py.contrib.django',
                ]
        """

        name = CiviConfig.name
        label = "civi"  # Unique label to avoid conflicts with django itself
        verbose_name = CiviConfig.verbose_name
        default_auto_field = CiviConfig.default_auto_field

except ImportError:
    # Django not installed - CiviConfig can still be used for type hints
    # and documentation, but CiviAppConfig won't be available
    CiviAppConfig = CiviConfig  # type: ignore[misc, assignment]


__all__ = [
    "CiviAppConfig",
    "CiviConfig",
]
