"""HTTP transport layer for CiviCRM API.

Provides both async and sync HTTP clients with:
- Connection pooling
- Retry logic with exponential backoff
- Timeout handling
- SSL verification options
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Self

import httpx
import msgspec

from civicrm_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConnectionError,
    CiviTimeoutError,
)
from civicrm_py.core.serialization import APIResponse, decode_response, to_dict

if TYPE_CHECKING:
    from civicrm_py.core.auth import AuthProvider
    from civicrm_py.core.config import CiviSettings
    from civicrm_py.core.serialization import APIRequest

logger = logging.getLogger(__name__)


def _convert_params(params: APIRequest | dict[str, Any] | None) -> dict[str, Any]:
    """Convert params to dict, handling msgspec Structs."""
    if params is None:
        return {}
    if isinstance(params, msgspec.Struct):
        return to_dict(params)
    return dict(params)


class BaseTransport:
    """Base class for HTTP transports."""

    def __init__(
        self,
        settings: CiviSettings,
        auth: AuthProvider,
    ) -> None:
        """Initialize transport.

        Args:
            settings: Client settings.
            auth: Authentication provider.
        """
        self.settings = settings
        self.auth = auth
        self.base_url = settings.base_url.rstrip("/")

    def _build_url(self, entity: str, action: str) -> str:
        """Build API endpoint URL.

        Args:
            entity: CiviCRM entity name (e.g., 'Contact').
            action: API action (e.g., 'get', 'create').

        Returns:
            Full URL for the API endpoint.
        """
        return f"{self.base_url}/{entity}/{action}"

    def _build_headers(self) -> dict[str, str]:
        """Build request headers.

        Returns:
            Headers dict including auth and content type.
        """
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        headers.update(self.auth.get_headers())
        return headers

    def _build_request_data(self, params: dict[str, Any]) -> dict[str, str]:
        """Build form-encoded request data for CiviCRM API v4.

        CiviCRM API v4 expects form-encoded POST data with a 'params' field
        containing the JSON-encoded request parameters.

        Args:
            params: Request parameters dict.

        Returns:
            Form data dict with 'params' key containing JSON string.
        """
        return {"params": json.dumps(params)}

    def _handle_response(self, response: httpx.Response) -> APIResponse[dict[str, Any]]:
        """Process HTTP response.

        Args:
            response: httpx Response object.

        Returns:
            Decoded API response.

        Raises:
            CiviAuthError: On 401/403 status.
            CiviAPIError: On API error response.
        """
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            msg = "Authentication failed"
            raise CiviAuthError(msg)
        if response.status_code == HTTPStatus.FORBIDDEN:
            msg = "Permission denied"
            raise CiviAuthError(msg)

        api_response = decode_response(response.content)

        if api_response.is_error:
            raise CiviAPIError(
                api_response.error_message or "Unknown API error",
                error_code=api_response.error_code,
                error_message=api_response.error_message,
            )

        return api_response

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds.
        """
        return min(2**attempt * 0.5, 30.0)


class AsyncTransport(BaseTransport):
    """Async HTTP transport using httpx.AsyncClient."""

    def __init__(
        self,
        settings: CiviSettings,
        auth: AuthProvider,
    ) -> None:
        """Initialize async transport.

        Args:
            settings: Client settings.
            auth: Authentication provider.
        """
        super().__init__(settings, auth)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client.

        Returns:
            Configured httpx.AsyncClient.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.timeout),
                verify=self.settings.verify_ssl,
                follow_redirects=True,
            )
        return self._client

    async def request(
        self,
        entity: str,
        action: str,
        params: APIRequest | dict[str, Any] | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Make async API request.

        Args:
            entity: CiviCRM entity name.
            action: API action.
            params: Request parameters.

        Returns:
            API response.

        Raises:
            CiviConnectionError: On network error.
            CiviTimeoutError: On request timeout.
            CiviAuthError: On authentication failure.
            CiviAPIError: On API error response.
        """
        url = self._build_url(entity, action)
        headers = self._build_headers()
        body = _convert_params(params)
        last_error: Exception | None = None

        for attempt in range(self.settings.max_retries + 1):
            try:
                client = await self._get_client()
                form_data = self._build_request_data(body)
                response = await client.post(url, data=form_data, headers=headers)
                return self._handle_response(response)
            except httpx.TimeoutException as e:
                last_error = CiviTimeoutError(f"Request timed out: {e}")
                if self.settings.debug:
                    logger.debug("Attempt %d timed out: %s", attempt + 1, e)
            except httpx.ConnectError as e:
                last_error = CiviConnectionError(f"Connection failed: {e}")
                if self.settings.debug:
                    logger.debug("Attempt %d connection failed: %s", attempt + 1, e)
            except (CiviAuthError, CiviAPIError):
                raise

            if attempt < self.settings.max_retries:
                delay = self._calculate_backoff(attempt)
                if self.settings.debug:
                    logger.debug("Retrying in %.1f seconds...", delay)
                await asyncio.sleep(delay)

        if last_error:
            raise last_error
        msg = "Request failed after retries"
        raise CiviConnectionError(msg)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> Self:
        """Enter async context."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context."""
        await self.close()


class SyncTransport(BaseTransport):
    """Sync HTTP transport using httpx.Client."""

    def __init__(
        self,
        settings: CiviSettings,
        auth: AuthProvider,
    ) -> None:
        """Initialize sync transport.

        Args:
            settings: Client settings.
            auth: Authentication provider.
        """
        super().__init__(settings, auth)
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create sync HTTP client.

        Returns:
            Configured httpx.Client.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self.settings.timeout),
                verify=self.settings.verify_ssl,
                follow_redirects=True,
            )
        return self._client

    def request(
        self,
        entity: str,
        action: str,
        params: APIRequest | dict[str, Any] | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Make sync API request.

        Args:
            entity: CiviCRM entity name.
            action: API action.
            params: Request parameters.

        Returns:
            API response.

        Raises:
            CiviConnectionError: On network error.
            CiviTimeoutError: On request timeout.
            CiviAuthError: On authentication failure.
            CiviAPIError: On API error response.
        """
        url = self._build_url(entity, action)
        headers = self._build_headers()
        body = _convert_params(params)
        last_error: Exception | None = None

        for attempt in range(self.settings.max_retries + 1):
            try:
                client = self._get_client()
                form_data = self._build_request_data(body)
                response = client.post(url, data=form_data, headers=headers)
                return self._handle_response(response)
            except httpx.TimeoutException as e:
                last_error = CiviTimeoutError(f"Request timed out: {e}")
                if self.settings.debug:
                    logger.debug("Attempt %d timed out: %s", attempt + 1, e)
            except httpx.ConnectError as e:
                last_error = CiviConnectionError(f"Connection failed: {e}")
                if self.settings.debug:
                    logger.debug("Attempt %d connection failed: %s", attempt + 1, e)
            except (CiviAuthError, CiviAPIError):
                raise

            if attempt < self.settings.max_retries:
                delay = self._calculate_backoff(attempt)
                if self.settings.debug:
                    logger.debug("Retrying in %.1f seconds...", delay)
                time.sleep(delay)

        if last_error:
            raise last_error
        msg = "Request failed after retries"
        raise CiviConnectionError(msg)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        """Enter sync context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit sync context."""
        self.close()


__all__ = [
    "AsyncTransport",
    "SyncTransport",
]
