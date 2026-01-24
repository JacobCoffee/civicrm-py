"""Authentication providers for CiviCRM API.

CiviCRM API v4 supports multiple authentication methods:
- API Key + Site Key (most common)
- JWT tokens
- Basic Auth (for some configurations)
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from civicrm_py.core.config import CiviSettings


class AuthProvider(ABC):
    """Abstract base class for authentication providers.

    Auth providers are responsible for adding authentication
    headers to API requests.
    """

    @abstractmethod
    def get_headers(self) -> dict[str, str]:
        """Get authentication headers for API request.

        Returns:
            Dictionary of HTTP headers to add to the request.
        """

    @abstractmethod
    def is_valid(self) -> bool:
        """Check if authentication credentials are valid.

        Returns:
            True if credentials appear valid (non-empty).
        """

    @classmethod
    def from_settings(cls, settings: CiviSettings) -> AuthProvider:
        """Create appropriate auth provider from settings.

        Args:
            settings: CiviSettings instance with auth configuration.

        Returns:
            Configured AuthProvider instance.

        Raises:
            ValueError: If auth_type is not recognized.
        """
        if settings.auth_type == "api_key":
            return APIKeyAuth(
                api_key=settings.api_key or "",
                site_key=settings.site_key,
            )
        if settings.auth_type == "jwt":
            return JWTAuth(token=settings.jwt_token or "")
        if settings.auth_type == "basic":
            return BasicAuth(
                username=settings.username or "",
                password=settings.password or "",
            )
        msg = f"Unknown auth_type: {settings.auth_type}"
        raise ValueError(msg)


class APIKeyAuth(AuthProvider):
    """API Key authentication for CiviCRM.

    Uses Authorization: Bearer header with API key for CiviCRM API v4.
    This is the standard authentication method for CiviCRM Standalone
    using the authx extension.

    The X-Requested-With header is included for CSRF compatibility.
    """

    def __init__(self, api_key: str, site_key: str | None = None) -> None:
        """Initialize API key authentication.

        Args:
            api_key: CiviCRM API key.
            site_key: Optional CiviCRM site key (for CMS integrations).
        """
        self.api_key = api_key
        self.site_key = site_key

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with Authorization Bearer token for API authentication.
        """
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.site_key:
            headers["X-Civi-Site-Key"] = self.site_key
        return headers

    def is_valid(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)


class JWTAuth(AuthProvider):
    """JWT token authentication for CiviCRM.

    Uses standard Authorization: Bearer header.
    """

    def __init__(self, token: str) -> None:
        """Initialize JWT authentication.

        Args:
            token: JWT token for authentication.
        """
        self.token = token

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with Authorization Bearer token.
        """
        return {"Authorization": f"Bearer {self.token}"}

    def is_valid(self) -> bool:
        """Check if token is set."""
        return bool(self.token)


class BasicAuth(AuthProvider):
    """HTTP Basic authentication for CiviCRM.

    Uses standard Authorization: Basic header.
    """

    def __init__(self, username: str, password: str) -> None:
        """Initialize basic authentication.

        Args:
            username: Username for authentication.
            password: Password for authentication.
        """
        self.username = username
        self.password = password

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with Authorization Basic credentials.
        """
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def is_valid(self) -> bool:
        """Check if username and password are set."""
        return bool(self.username and self.password)


__all__ = [
    "APIKeyAuth",
    "AuthProvider",
    "BasicAuth",
    "JWTAuth",
]
