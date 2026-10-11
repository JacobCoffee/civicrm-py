"""Authentication providers for CiviCRM API.

CiviCRM's AuthX extension supports multiple authentication methods:
- API Key + Site Key (most common)
- JWT tokens
- Basic Auth (for some configurations)

Credentials can be sent through either the standard ``Authorization`` header
(AuthX "header" flow) or the ``X-Civi-Auth`` header (AuthX "xheader" flow).
The xheader flow survives hosts that strip ``Authorization`` (common on
WordPress/Apache), but each flow has its own allowed-credentials setting on
the CiviCRM side (``authx_header_cred`` / ``authx_xheader_cred``).

See https://docs.civicrm.org/dev/en/latest/framework/authx/
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from civicrm_py.core.config import CiviSettings

AuthFlow = Literal["header", "xheader"]

_FLOW_HEADERS: dict[str, str] = {
    "header": "Authorization",
    "xheader": "X-Civi-Auth",
}

SITE_KEY_HEADER = "X-Civi-Key"


def _credential_header(flow: AuthFlow) -> str:
    """Resolve the HTTP header name that carries the credential for an AuthX flow."""
    try:
        return _FLOW_HEADERS[flow]
    except KeyError:
        msg = f"Unknown auth_flow: {flow!r} (expected 'header' or 'xheader')"
        raise ValueError(msg) from None


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
                flow=settings.auth_flow,
            )
        if settings.auth_type == "jwt":
            return JWTAuth(token=settings.jwt_token or "", flow=settings.auth_flow)
        if settings.auth_type == "basic":
            return BasicAuth(
                username=settings.username or "",
                password=settings.password or "",
                flow=settings.auth_flow,
            )
        msg = f"Unknown auth_type: {settings.auth_type}"
        raise ValueError(msg)


class APIKeyAuth(AuthProvider):
    """API Key authentication for CiviCRM.

    Sends ``Bearer <api_key>`` via the configured AuthX flow header. When a
    site key is given it is sent as ``X-Civi-Key``, which satisfies AuthX's
    site-key guard for users lacking the ``authenticate with api key``
    permission.
    """

    def __init__(self, api_key: str, site_key: str | None = None, flow: AuthFlow = "header") -> None:
        """Initialize API key authentication.

        Args:
            api_key: CiviCRM API key.
            site_key: Optional CiviCRM site key (AuthX site-key guard).
            flow: AuthX flow, ``"header"`` (Authorization) or ``"xheader"`` (X-Civi-Auth).
        """
        self.api_key = api_key
        self.site_key = site_key
        self.flow = flow
        self._header = _credential_header(flow)

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with the Bearer credential and optional site key.
        """
        headers: dict[str, str] = {self._header: f"Bearer {self.api_key}"}
        if self.site_key:
            headers[SITE_KEY_HEADER] = self.site_key
        return headers

    def is_valid(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)


class JWTAuth(AuthProvider):
    """JWT token authentication for CiviCRM.

    Sends ``Bearer <token>`` via the configured AuthX flow header.
    """

    def __init__(self, token: str, flow: AuthFlow = "header") -> None:
        """Initialize JWT authentication.

        Args:
            token: JWT token for authentication.
            flow: AuthX flow, ``"header"`` (Authorization) or ``"xheader"`` (X-Civi-Auth).
        """
        self.token = token
        self.flow = flow
        self._header = _credential_header(flow)

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with the Bearer credential.
        """
        return {self._header: f"Bearer {self.token}"}

    def is_valid(self) -> bool:
        """Check if token is set."""
        return bool(self.token)


class BasicAuth(AuthProvider):
    """HTTP Basic authentication for CiviCRM.

    Sends ``Basic <b64(user:pass)>`` via the configured AuthX flow header.
    """

    def __init__(self, username: str, password: str, flow: AuthFlow = "header") -> None:
        """Initialize basic authentication.

        Args:
            username: Username for authentication.
            password: Password for authentication.
            flow: AuthX flow, ``"header"`` (Authorization) or ``"xheader"`` (X-Civi-Auth).
        """
        self.username = username
        self.password = password
        self.flow = flow
        self._header = _credential_header(flow)

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers.

        Returns:
            Headers dict with Basic credentials.
        """
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {self._header: f"Basic {encoded}"}

    def is_valid(self) -> bool:
        """Check if username and password are set."""
        return bool(self.username and self.password)


__all__ = [
    "SITE_KEY_HEADER",
    "APIKeyAuth",
    "AuthFlow",
    "AuthProvider",
    "BasicAuth",
    "JWTAuth",
]
