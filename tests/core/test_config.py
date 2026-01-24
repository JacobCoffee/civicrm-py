"""Tests for CiviSettings configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from civicrm_py.core.config import (
    CiviSettings,
    clear_settings_cache,
    get_env,
    get_env_bool,
    get_env_int,
    get_settings,
)


class TestGetEnvHelpers:
    """Tests for environment variable helper functions."""

    def test_get_env_returns_value(self) -> None:
        """Test get_env returns environment variable value."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert get_env("TEST_VAR") == "test_value"

    def test_get_env_returns_default(self) -> None:
        """Test get_env returns default when not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_env("NONEXISTENT_VAR", "default") == "default"

    def test_get_env_required_raises(self) -> None:
        """Test get_env raises when required and not set."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="Required environment variable"):
            get_env("REQUIRED_VAR", required=True)

    def test_get_env_bool_true_values(self) -> None:
        """Test get_env_bool recognizes true values."""
        for value in ["true", "True", "TRUE", "1", "yes", "on"]:
            with patch.dict(os.environ, {"BOOL_VAR": value}):
                assert get_env_bool("BOOL_VAR") is True

    def test_get_env_bool_false_values(self) -> None:
        """Test get_env_bool recognizes false values."""
        for value in ["false", "False", "FALSE", "0", "no", "off"]:
            with patch.dict(os.environ, {"BOOL_VAR": value}):
                assert get_env_bool("BOOL_VAR") is False

    def test_get_env_bool_default(self) -> None:
        """Test get_env_bool returns default when not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_env_bool("BOOL_VAR", default=True) is True
            assert get_env_bool("BOOL_VAR", default=False) is False

    def test_get_env_int_returns_int(self) -> None:
        """Test get_env_int parses integer."""
        with patch.dict(os.environ, {"INT_VAR": "42"}):
            assert get_env_int("INT_VAR", 0) == 42

    def test_get_env_int_returns_default_on_invalid(self) -> None:
        """Test get_env_int returns default on invalid value."""
        with patch.dict(os.environ, {"INT_VAR": "not_a_number"}):
            assert get_env_int("INT_VAR", 10) == 10


class TestCiviSettings:
    """Tests for CiviSettings configuration class."""

    def test_settings_from_values(self) -> None:
        """Test creating settings with explicit values."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-key",
            site_key="test-site-key",
        )

        assert settings.base_url == "https://example.org/civicrm/ajax/api4"
        assert settings.api_key == "test-key"
        assert settings.site_key == "test-site-key"

    def test_settings_defaults(self) -> None:
        """Test default values are applied."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            api_key="key",
        )

        assert settings.timeout == 30
        assert settings.verify_ssl is True
        assert settings.debug is False
        assert settings.max_retries == 3
        assert settings.auth_type == "api_key"

    def test_settings_custom_values(self) -> None:
        """Test custom values override defaults."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            api_key="key",
            timeout=60,
            verify_ssl=False,
            debug=True,
            max_retries=5,
        )

        assert settings.timeout == 60
        assert settings.verify_ssl is False
        assert settings.debug is True
        assert settings.max_retries == 5

    def test_settings_requires_base_url(self) -> None:
        """Test that base_url is required."""
        with pytest.raises(ValueError, match="base_url is required"):
            CiviSettings(
                base_url="",
                api_key="key",
            )

    def test_settings_requires_api_key_for_api_key_auth(self) -> None:
        """Test that api_key is required for api_key auth_type."""
        with pytest.raises(ValueError, match="api_key is required"):
            CiviSettings(
                base_url="https://example.org/api4",
                auth_type="api_key",
            )

    def test_settings_requires_jwt_token_for_jwt_auth(self) -> None:
        """Test that jwt_token is required for jwt auth_type."""
        with pytest.raises(ValueError, match="jwt_token is required"):
            CiviSettings(
                base_url="https://example.org/api4",
                auth_type="jwt",
            )

    def test_settings_requires_credentials_for_basic_auth(self) -> None:
        """Test that username/password are required for basic auth_type."""
        with pytest.raises(ValueError, match="username and password are required"):
            CiviSettings(
                base_url="https://example.org/api4",
                auth_type="basic",
            )

    def test_settings_jwt_auth(self) -> None:
        """Test JWT authentication settings."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="jwt",
            jwt_token="test-token",  # noqa: S106
        )
        assert settings.jwt_token == "test-token"
        assert settings.auth_type == "jwt"

    def test_settings_basic_auth(self) -> None:
        """Test basic authentication settings."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            auth_type="basic",
            username="user",
            password="pass",  # noqa: S106
        )
        assert settings.username == "user"
        assert settings.password == "pass"
        assert settings.auth_type == "basic"

    def test_settings_from_env(self) -> None:
        """Test creating settings from environment variables."""
        env_vars = {
            "CIVI_BASE_URL": "https://env.example.org/api4",
            "CIVI_API_KEY": "env-api-key",
            "CIVI_SITE_KEY": "env-site-key",
            "CIVI_TIMEOUT": "45",
            "CIVI_VERIFY_SSL": "false",
            "CIVI_DEBUG": "true",
            "CIVI_MAX_RETRIES": "5",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = CiviSettings.from_env()

            assert settings.base_url == "https://env.example.org/api4"
            assert settings.api_key == "env-api-key"
            assert settings.site_key == "env-site-key"
            assert settings.timeout == 45
            assert settings.verify_ssl is False
            assert settings.debug is True
            assert settings.max_retries == 5

    def test_settings_frozen(self) -> None:
        """Test that settings are immutable."""
        settings = CiviSettings(
            base_url="https://example.org/api4",
            api_key="key",
        )
        with pytest.raises(AttributeError):
            settings.base_url = "https://other.org/api4"  # type: ignore[misc]


class TestGetSettings:
    """Tests for get_settings caching."""

    def test_get_settings_caches_result(self) -> None:
        """Test that get_settings returns cached instance."""
        env_vars = {
            "CIVI_BASE_URL": "https://cached.example.org/api4",
            "CIVI_API_KEY": "cached-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            clear_settings_cache()
            settings1 = get_settings()
            settings2 = get_settings()

            assert settings1 is settings2

    def test_clear_settings_cache(self) -> None:
        """Test clearing settings cache."""
        env_vars = {
            "CIVI_BASE_URL": "https://first.example.org/api4",
            "CIVI_API_KEY": "first-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            clear_settings_cache()
            settings1 = get_settings()

        new_env_vars = {
            "CIVI_BASE_URL": "https://second.example.org/api4",
            "CIVI_API_KEY": "second-key",
        }
        with patch.dict(os.environ, new_env_vars, clear=True):
            clear_settings_cache()
            settings2 = get_settings()

            assert settings1.base_url != settings2.base_url
