"""CiviClient - Main entry point for CiviCRM API v4.

Provides both async and sync context-managed access to CiviCRM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from civicrm_py.core.auth import AuthProvider
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.serialization import APIRequest, APIResponse
from civicrm_py.http.transport import AsyncTransport, SyncTransport

if TYPE_CHECKING:
    from types import TracebackType


class CiviClient:
    """Async client for CiviCRM API v4.

    Usage:
        async with CiviClient(settings) as client:
            response = await client.request("Contact", "get", {"limit": 10})

    Or with environment variables:
        async with CiviClient.from_env() as client:
            response = await client.request("Contact", "get")
    """

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        site_key: str | None = None,
        timeout: int = 30,
        verify_ssl: bool = True,
        debug: bool = False,
        max_retries: int = 3,
    ) -> None:
        """Initialize CiviClient.

        Either provide a CiviSettings instance or individual parameters.
        If neither settings nor base_url is provided, will attempt to
        load from environment variables.

        Args:
            settings: Pre-configured CiviSettings instance.
            base_url: CiviCRM API base URL.
            api_key: API key for authentication.
            site_key: Optional site key.
            timeout: Request timeout in seconds.
            verify_ssl: Whether to verify SSL certificates.
            debug: Enable debug logging.
            max_retries: Maximum retry attempts.
        """
        if settings is not None:
            self._settings = settings
        elif base_url is not None:
            self._settings = CiviSettings(
                base_url=base_url,
                api_key=api_key,
                site_key=site_key,
                timeout=timeout,
                verify_ssl=verify_ssl,
                debug=debug,
                max_retries=max_retries,
            )
        else:
            self._settings = CiviSettings.from_env()

        self._auth = AuthProvider.from_settings(self._settings)
        self._transport: AsyncTransport | None = None

    @classmethod
    def from_env(cls) -> CiviClient:
        """Create client from environment variables.

        Returns:
            CiviClient configured from environment.
        """
        return cls(settings=CiviSettings.from_env())

    @property
    def settings(self) -> CiviSettings:
        """Get client settings."""
        return self._settings

    async def _get_transport(self) -> AsyncTransport:
        """Get or create async transport."""
        if self._transport is None:
            self._transport = AsyncTransport(self._settings, self._auth)
        return self._transport

    async def request(
        self,
        entity: str,
        action: str,
        params: APIRequest | dict[str, Any] | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Make API request.

        Args:
            entity: CiviCRM entity name (e.g., 'Contact', 'Activity').
            action: API action (e.g., 'get', 'create', 'delete').
            params: Request parameters.

        Returns:
            API response with values and metadata.

        Raises:
            CiviConnectionError: On network error.
            CiviTimeoutError: On request timeout.
            CiviAuthError: On authentication failure.
            CiviAPIError: On API error response.
        """
        transport = await self._get_transport()
        return await transport.request(entity, action, params)

    async def get(
        self,
        entity: str,
        *,
        select: list[str] | None = None,
        where: list[list[Any]] | None = None,
        order_by: dict[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Get entities with optional filtering.

        Args:
            entity: Entity name.
            select: Fields to return.
            where: Filter conditions.
            order_by: Sort order.
            limit: Max records.
            offset: Skip records.

        Returns:
            API response.
        """
        params = APIRequest(
            select=select,
            where=where,
            orderBy=order_by,
            limit=limit,
            offset=offset,
        )
        return await self.request(entity, "get", params)

    async def create(
        self,
        entity: str,
        values: dict[str, Any],
    ) -> APIResponse[dict[str, Any]]:
        """Create a new entity.

        Args:
            entity: Entity name.
            values: Field values for the new entity.

        Returns:
            API response with created entity.
        """
        params = APIRequest(values=values)
        return await self.request(entity, "create", params)

    async def update(
        self,
        entity: str,
        values: dict[str, Any],
        where: list[list[Any]],
    ) -> APIResponse[dict[str, Any]]:
        """Update existing entities.

        Args:
            entity: Entity name.
            values: Field values to update.
            where: Filter to select entities to update.

        Returns:
            API response with updated entities.
        """
        params = APIRequest(values=values, where=where)
        return await self.request(entity, "update", params)

    async def delete(
        self,
        entity: str,
        where: list[list[Any]],
    ) -> APIResponse[dict[str, Any]]:
        """Delete entities.

        Args:
            entity: Entity name.
            where: Filter to select entities to delete.

        Returns:
            API response.
        """
        params = APIRequest(where=where)
        return await self.request(entity, "delete", params)

    async def get_fields(
        self,
        entity: str,
    ) -> APIResponse[dict[str, Any]]:
        """Get field metadata for an entity.

        Args:
            entity: Entity name.

        Returns:
            API response with field definitions.
        """
        return await self.request(entity, "getFields", {})

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._transport is not None:
            await self._transport.close()
            self._transport = None

    async def __aenter__(self) -> Self:
        """Enter async context."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context."""
        await self.close()


class SyncCiviClient:
    """Sync client for CiviCRM API v4.

    Usage:
        with SyncCiviClient(settings) as client:
            response = client.request("Contact", "get", {"limit": 10})
    """

    def __init__(
        self,
        settings: CiviSettings | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        site_key: str | None = None,
        timeout: int = 30,
        verify_ssl: bool = True,
        debug: bool = False,
        max_retries: int = 3,
    ) -> None:
        """Initialize SyncCiviClient.

        Args:
            settings: Pre-configured CiviSettings instance.
            base_url: CiviCRM API base URL.
            api_key: API key for authentication.
            site_key: Optional site key.
            timeout: Request timeout in seconds.
            verify_ssl: Whether to verify SSL certificates.
            debug: Enable debug logging.
            max_retries: Maximum retry attempts.
        """
        if settings is not None:
            self._settings = settings
        elif base_url is not None:
            self._settings = CiviSettings(
                base_url=base_url,
                api_key=api_key,
                site_key=site_key,
                timeout=timeout,
                verify_ssl=verify_ssl,
                debug=debug,
                max_retries=max_retries,
            )
        else:
            self._settings = CiviSettings.from_env()

        self._auth = AuthProvider.from_settings(self._settings)
        self._transport: SyncTransport | None = None

    @classmethod
    def from_env(cls) -> SyncCiviClient:
        """Create client from environment variables."""
        return cls(settings=CiviSettings.from_env())

    @property
    def settings(self) -> CiviSettings:
        """Get client settings."""
        return self._settings

    def _get_transport(self) -> SyncTransport:
        """Get or create sync transport."""
        if self._transport is None:
            self._transport = SyncTransport(self._settings, self._auth)
        return self._transport

    def request(
        self,
        entity: str,
        action: str,
        params: APIRequest | dict[str, Any] | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Make API request."""
        transport = self._get_transport()
        return transport.request(entity, action, params)

    def get(
        self,
        entity: str,
        *,
        select: list[str] | None = None,
        where: list[list[Any]] | None = None,
        order_by: dict[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> APIResponse[dict[str, Any]]:
        """Get entities with optional filtering."""
        params = APIRequest(
            select=select,
            where=where,
            orderBy=order_by,
            limit=limit,
            offset=offset,
        )
        return self.request(entity, "get", params)

    def create(
        self,
        entity: str,
        values: dict[str, Any],
    ) -> APIResponse[dict[str, Any]]:
        """Create a new entity."""
        params = APIRequest(values=values)
        return self.request(entity, "create", params)

    def update(
        self,
        entity: str,
        values: dict[str, Any],
        where: list[list[Any]],
    ) -> APIResponse[dict[str, Any]]:
        """Update existing entities."""
        params = APIRequest(values=values, where=where)
        return self.request(entity, "update", params)

    def delete(
        self,
        entity: str,
        where: list[list[Any]],
    ) -> APIResponse[dict[str, Any]]:
        """Delete entities."""
        params = APIRequest(where=where)
        return self.request(entity, "delete", params)

    def get_fields(
        self,
        entity: str,
    ) -> APIResponse[dict[str, Any]]:
        """Get field metadata for an entity."""
        return self.request(entity, "getFields", {})

    def close(self) -> None:
        """Close the client and release resources."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def __enter__(self) -> Self:
        """Enter sync context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit sync context."""
        self.close()


__all__ = [
    "CiviClient",
    "SyncCiviClient",
]
