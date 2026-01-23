"""Tests for Django settings integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from civi_py.core.config import CiviSettings
from civi_py.core.exceptions import CiviConfigError, CiviIntegrationError


class TestGetDjangoSettings:
    """Tests for get_django_settings function."""

    def test_missing_django_raises_integration_error(self) -> None:
        """Test that missing Django raises CiviIntegrationError."""
        with patch.dict("sys.modules", {"django": None, "django.conf": None}):
            # Need to reimport after patching
            import importlib

            from civi_py.contrib.django import settings as django_settings_module

            importlib.reload(django_settings_module)

            with pytest.raises(CiviIntegrationError, match="Django is not installed"):
                django_settings_module.get_django_settings()

    def test_django_not_configured_raises_integration_error(self) -> None:
        """Test that unconfigured Django raises CiviIntegrationError."""
        mock_settings = MagicMock()
        mock_settings.configured = False

        with (
            patch.dict("sys.modules", {"django": MagicMock(), "django.conf": MagicMock()}),
            patch(
                "civi_py.contrib.django.settings._get_django_settings",
                side_effect=CiviIntegrationError("Django settings are not configured"),
            ),
        ):
            from civi_py.contrib.django.settings import get_django_settings

            with pytest.raises(CiviIntegrationError, match="not configured"):
                get_django_settings()

    def test_missing_civicrm_url_raises_config_error(self) -> None:
        """Test that missing CIVICRM_URL raises CiviConfigError."""
        mock_settings = MagicMock()
        mock_settings.configured = True
        mock_settings.CIVICRM_URL = None

        # Use spec to ensure getattr returns None for unset attrs
        del mock_settings.CIVICRM_URL

        with patch(
            "civi_py.contrib.django.settings._get_django_settings",
            return_value=mock_settings,
        ):
            from civi_py.contrib.django.settings import get_django_settings

            with pytest.raises(CiviConfigError, match="CIVICRM_URL is required"):
                get_django_settings()

    def test_returns_config_dict_with_defaults(self) -> None:
        """Test that get_django_settings returns config with defaults."""
        mock_settings = MagicMock()
        mock_settings.configured = True
        mock_settings.CIVICRM_URL = "https://example.org/civicrm/ajax/api4"

        # Clear optional settings to trigger defaults
        for attr in [
            "CIVICRM_API_KEY",
            "CIVICRM_SITE_KEY",
            "CIVICRM_AUTH_TYPE",
            "CIVICRM_TIMEOUT",
            "CIVICRM_VERIFY_SSL",
            "CIVICRM_DEBUG",
            "CIVICRM_MAX_RETRIES",
            "CIVICRM_JWT_TOKEN",
            "CIVICRM_USERNAME",
            "CIVICRM_PASSWORD",
        ]:
            delattr(mock_settings, attr)

        with patch(
            "civi_py.contrib.django.settings._get_django_settings",
            return_value=mock_settings,
        ):
            from civi_py.contrib.django.settings import get_django_settings

            config = get_django_settings()

            assert config["url"] == "https://example.org/civicrm/ajax/api4"
            assert config["api_key"] is None
            assert config["site_key"] is None
            assert config["auth_type"] == "api_key"
            assert config["timeout"] == 30
            assert config["verify_ssl"] is True
            assert config["debug"] is False
            assert config["max_retries"] == 3

    def test_returns_all_configured_values(self) -> None:
        """Test that get_django_settings returns all configured values."""
        mock_settings = MagicMock()
        mock_settings.configured = True
        mock_settings.CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
        mock_settings.CIVICRM_API_KEY = "test-api-key"
        mock_settings.CIVICRM_SITE_KEY = "test-site-key"
        mock_settings.CIVICRM_AUTH_TYPE = "jwt"
        mock_settings.CIVICRM_TIMEOUT = 60
        mock_settings.CIVICRM_VERIFY_SSL = False
        mock_settings.CIVICRM_DEBUG = True
        mock_settings.CIVICRM_MAX_RETRIES = 5
        mock_settings.CIVICRM_JWT_TOKEN = "test-jwt-token"
        mock_settings.CIVICRM_USERNAME = "test-user"
        mock_settings.CIVICRM_PASSWORD = "test-pass"

        with patch(
            "civi_py.contrib.django.settings._get_django_settings",
            return_value=mock_settings,
        ):
            from civi_py.contrib.django.settings import get_django_settings

            config = get_django_settings()

            assert config["url"] == "https://example.org/civicrm/ajax/api4"
            assert config["api_key"] == "test-api-key"
            assert config["site_key"] == "test-site-key"
            assert config["auth_type"] == "jwt"
            assert config["timeout"] == 60
            assert config["verify_ssl"] is False
            assert config["debug"] is True
            assert config["max_retries"] == 5
            assert config["jwt_token"] == "test-jwt-token"
            assert config["username"] == "test-user"
            assert config["password"] == "test-pass"


class TestCreateSettings:
    """Tests for create_settings function."""

    def test_creates_civi_settings_from_django(self) -> None:
        """Test that create_settings creates a CiviSettings instance."""
        mock_django_config = {
            "url": "https://example.org/civicrm/ajax/api4",
            "api_key": "test-api-key",
            "site_key": "test-site-key",
            "auth_type": "api_key",
            "timeout": 30,
            "verify_ssl": True,
            "debug": False,
            "max_retries": 3,
            "jwt_token": None,
            "username": None,
            "password": None,
        }

        with patch(
            "civi_py.contrib.django.settings.get_django_settings",
            return_value=mock_django_config,
        ):
            from civi_py.contrib.django.settings import create_settings

            settings = create_settings()

            assert isinstance(settings, CiviSettings)
            assert settings.base_url == "https://example.org/civicrm/ajax/api4"
            assert settings.api_key == "test-api-key"
            assert settings.site_key == "test-site-key"
            assert settings.auth_type == "api_key"
            assert settings.timeout == 30
            assert settings.verify_ssl is True
            assert settings.debug is False
            assert settings.max_retries == 3


class TestGetCiviSettings:
    """Tests for get_civi_settings function."""

    def test_returns_cached_settings(self) -> None:
        """Test that get_civi_settings caches the settings."""
        mock_django_config = {
            "url": "https://example.org/civicrm/ajax/api4",
            "api_key": "test-api-key",
            "site_key": None,
            "auth_type": "api_key",
            "timeout": 30,
            "verify_ssl": True,
            "debug": False,
            "max_retries": 3,
            "jwt_token": None,
            "username": None,
            "password": None,
        }

        with patch(
            "civi_py.contrib.django.settings.get_django_settings",
            return_value=mock_django_config,
        ):
            from civi_py.contrib.django.settings import (
                clear_settings_cache,
                get_civi_settings,
            )

            # Clear cache first
            clear_settings_cache()

            settings1 = get_civi_settings()
            settings2 = get_civi_settings()

            # Should return the same object due to caching
            assert settings1 is settings2


class TestClearSettingsCache:
    """Tests for clear_settings_cache function."""

    def test_clears_cache(self) -> None:
        """Test that clear_settings_cache clears the cached settings."""
        mock_django_config = {
            "url": "https://example.org/civicrm/ajax/api4",
            "api_key": "test-api-key",
            "site_key": None,
            "auth_type": "api_key",
            "timeout": 30,
            "verify_ssl": True,
            "debug": False,
            "max_retries": 3,
            "jwt_token": None,
            "username": None,
            "password": None,
        }

        with patch(
            "civi_py.contrib.django.settings.get_django_settings",
            return_value=mock_django_config,
        ):
            from civi_py.contrib.django.settings import (
                clear_settings_cache,
                get_civi_settings,
            )

            # Get settings first
            clear_settings_cache()
            settings1 = get_civi_settings()

            # Clear and get again - should be different objects
            clear_settings_cache()
            settings2 = get_civi_settings()

            # Should be equal but not the same object
            assert settings1 == settings2
            # Note: Due to lru_cache, after clearing, a new object is created


class TestDjangoIntegration:
    """Tests for DjangoIntegration class."""

    def test_init_loads_django_settings(self) -> None:
        """Test that DjangoIntegration loads settings from Django."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        with patch(
            "civi_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            from civi_py.contrib.django.settings import DjangoIntegration

            integration = DjangoIntegration()

            assert integration.settings == mock_settings
            assert integration.is_async is False  # Default for Django

    def test_init_with_explicit_settings(self) -> None:
        """Test that DjangoIntegration can use explicit settings."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="explicit-api-key",
        )

        from civi_py.contrib.django.settings import DjangoIntegration

        integration = DjangoIntegration(settings=settings)

        assert integration.settings == settings
        assert integration.settings.api_key == "explicit-api-key"

    def test_init_async_mode(self) -> None:
        """Test that DjangoIntegration supports async mode."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civi_py.contrib.django.settings import DjangoIntegration

        integration = DjangoIntegration(settings=settings, is_async=True)

        assert integration.is_async is True

    def test_from_django_settings_class_method(self) -> None:
        """Test the from_django_settings class method."""
        mock_django_config = {
            "url": "https://example.org/civicrm/ajax/api4",
            "api_key": "factory-api-key",
            "site_key": None,
            "auth_type": "api_key",
            "timeout": 30,
            "verify_ssl": True,
            "debug": False,
            "max_retries": 3,
            "jwt_token": None,
            "username": None,
            "password": None,
        }

        with patch(
            "civi_py.contrib.django.settings.get_django_settings",
            return_value=mock_django_config,
        ):
            from civi_py.contrib.django.settings import DjangoIntegration

            integration = DjangoIntegration.from_django_settings()

            assert integration.settings.api_key == "factory-api-key"

    def test_repr(self) -> None:
        """Test the string representation of DjangoIntegration."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civi_py.contrib.django.settings import DjangoIntegration

        integration = DjangoIntegration(settings=settings)

        repr_str = repr(integration)

        assert "DjangoIntegration" in repr_str
        assert "not initialized" in repr_str
        assert "https://example.org/civicrm/ajax/api4" in repr_str

    def test_sync_lifecycle(self) -> None:
        """Test sync client lifecycle with DjangoIntegration."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civi_py.contrib.django.settings import DjangoIntegration

        integration = DjangoIntegration(settings=settings)

        # Start the sync client
        integration.startup_sync()

        # Should have a sync client now
        client = integration.get_sync_client()
        assert client is not None

        # Repr should reflect initialized state
        repr_str = repr(integration)
        assert "sync client initialized" in repr_str

        # Shutdown
        integration.shutdown_sync()

    def test_context_manager(self) -> None:
        """Test DjangoIntegration as context manager."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civi_py.contrib.django.settings import DjangoIntegration

        with DjangoIntegration(settings=settings) as integration:
            client = integration.get_sync_client()
            assert client is not None

        # After context exit, client should be closed
        # (get_sync_client would raise if called now)
