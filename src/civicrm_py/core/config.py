"""Configuration management for civi-py.

Uses dataclasses with environment variable loading following litestar-fullstack patterns.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal


def get_env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Get environment variable with optional default.

    Args:
        key: Environment variable name.
        default: Default value if not set.
        required: If True, raise ValueError when not set and no default.

    Returns:
        Environment variable value or default.

    Raises:
        ValueError: If required and not set with no default.
    """
    value = os.environ.get(key, default)
    if required and value is None:
        msg = f"Required environment variable {key} is not set"
        raise ValueError(msg)
    return value


def get_env_bool(key: str, *, default: bool = False) -> bool:
    """Get environment variable as boolean.

    Args:
        key: Environment variable name.
        default: Default value if not set.

    Returns:
        Boolean value (true/1/yes = True, false/0/no = False).
    """
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer.

    Args:
        key: Environment variable name.
        default: Default value if not set or invalid.

    Returns:
        Integer value.
    """
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class CiviSettings:
    """CiviCRM API client settings.

    Can be configured via environment variables or passed directly.

    Environment Variables:
        CIVI_BASE_URL: Base URL for CiviCRM API (e.g., https://example.org/civicrm/ajax/api4)
        CIVI_API_KEY: API key for authentication
        CIVI_SITE_KEY: Site key for authentication (optional for some setups)
        CIVI_TIMEOUT: Request timeout in seconds (default: 30)
        CIVI_VERIFY_SSL: Whether to verify SSL certificates (default: True)
        CIVI_DEBUG: Enable debug logging (default: False)
        CIVI_MAX_RETRIES: Maximum number of retries (default: 3)
        CIVI_AUTH_TYPE: Authentication type (api_key, jwt, basic) (default: api_key)
    """

    base_url: str
    api_key: str | None = None
    site_key: str | None = None
    timeout: int = 30
    verify_ssl: bool = True
    debug: bool = False
    max_retries: int = 3
    auth_type: Literal["api_key", "jwt", "basic"] = "api_key"
    jwt_token: str | None = None
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        """Validate settings after initialization."""
        if not self.base_url:
            msg = "base_url is required"
            raise ValueError(msg)

        # Validate auth credentials based on auth_type
        if self.auth_type == "api_key" and not self.api_key:
            msg = "api_key is required when auth_type is 'api_key'"
            raise ValueError(msg)
        if self.auth_type == "jwt" and not self.jwt_token:
            msg = "jwt_token is required when auth_type is 'jwt'"
            raise ValueError(msg)
        if self.auth_type == "basic" and (not self.username or not self.password):
            msg = "username and password are required when auth_type is 'basic'"
            raise ValueError(msg)

    @classmethod
    def from_env(cls) -> CiviSettings:
        """Create settings from environment variables.

        Returns:
            CiviSettings instance configured from environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        base_url = get_env("CIVI_BASE_URL", required=True)
        if base_url is None:  # for type checker
            msg = "CIVI_BASE_URL is required"
            raise ValueError(msg)

        return cls(
            base_url=base_url,
            api_key=get_env("CIVI_API_KEY"),
            site_key=get_env("CIVI_SITE_KEY"),
            timeout=get_env_int("CIVI_TIMEOUT", 30),
            verify_ssl=get_env_bool("CIVI_VERIFY_SSL", default=True),
            debug=get_env_bool("CIVI_DEBUG", default=False),
            max_retries=get_env_int("CIVI_MAX_RETRIES", 3),
            auth_type=get_env("CIVI_AUTH_TYPE", "api_key"),  # type: ignore[arg-type]
            jwt_token=get_env("CIVI_JWT_TOKEN"),
            username=get_env("CIVI_USERNAME"),
            password=get_env("CIVI_PASSWORD"),
        )


@lru_cache(maxsize=1)
def get_settings() -> CiviSettings:
    """Get cached settings instance from environment.

    Returns:
        Cached CiviSettings instance.
    """
    return CiviSettings.from_env()


def clear_settings_cache() -> None:
    """Clear the settings cache.

    Call this if environment variables change and you need to reload settings.
    """
    get_settings.cache_clear()


__all__ = [
    "CiviSettings",
    "clear_settings_cache",
    "get_env",
    "get_env_bool",
    "get_env_int",
    "get_settings",
]
