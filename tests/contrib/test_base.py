"""Tests for contrib.base protocols."""

from __future__ import annotations

import pytest

from civicrm_py.contrib.base import IntegrationProtocol, LifecycleHooks, RequestContext
from civicrm_py.core.client import CiviClient, SyncCiviClient
from civicrm_py.core.config import CiviSettings


class MockAsyncIntegration:
    """Mock async framework integration."""

    def __init__(self, settings: CiviSettings) -> None:
        self.settings = settings
        self.client: CiviClient | None = None

    def get_client(self) -> CiviClient:
        """Get async client."""
        if self.client is None:
            self.client = CiviClient(settings=self.settings)
        return self.client

    def get_settings(self) -> CiviSettings:
        """Get settings."""
        return self.settings

    def is_async(self) -> bool:
        """Check async support."""
        return True

    async def on_startup(self) -> None:
        """Startup hook."""
        self.client = CiviClient(settings=self.settings)

    async def on_shutdown(self) -> None:
        """Shutdown hook."""
        if self.client is not None:
            await self.client.close()
            self.client = None

    def on_startup_sync(self) -> None:
        """Sync startup hook."""

    def on_shutdown_sync(self) -> None:
        """Sync shutdown hook."""


class MockSyncIntegration:
    """Mock sync framework integration."""

    def __init__(self, settings: CiviSettings) -> None:
        self.settings = settings
        self.client: SyncCiviClient | None = None

    def get_client(self) -> SyncCiviClient:
        """Get sync client."""
        if self.client is None:
            self.client = SyncCiviClient(settings=self.settings)
        return self.client

    def get_settings(self) -> CiviSettings:
        """Get settings."""
        return self.settings

    def is_async(self) -> bool:
        """Check async support."""
        return False

    async def on_startup(self) -> None:
        """Async startup hook."""

    async def on_shutdown(self) -> None:
        """Async shutdown hook."""

    def on_startup_sync(self) -> None:
        """Sync startup hook."""
        self.client = SyncCiviClient(settings=self.settings)

    def on_shutdown_sync(self) -> None:
        """Sync shutdown hook."""
        if self.client is not None:
            self.client.close()
            self.client = None


class MockRequestContext:
    """Mock request context."""

    def __init__(self) -> None:
        self._client: CiviClient | SyncCiviClient | None = None

    def get_client(self) -> CiviClient | SyncCiviClient:
        """Get client from context."""
        if self._client is None:
            msg = "No client available in context"
            raise RuntimeError(msg)
        return self._client

    def set_client(self, client: CiviClient | SyncCiviClient) -> None:
        """Set client in context."""
        self._client = client


def test_async_integration_protocol(civi_settings: CiviSettings) -> None:
    """Test that async integration implements IntegrationProtocol."""
    integration = MockAsyncIntegration(civi_settings)

    # Verify protocol conformance
    assert isinstance(integration, IntegrationProtocol)

    # Test interface methods
    assert integration.is_async() is True
    assert isinstance(integration.get_settings(), CiviSettings)
    assert isinstance(integration.get_client(), CiviClient)


def test_sync_integration_protocol(civi_settings: CiviSettings) -> None:
    """Test that sync integration implements IntegrationProtocol."""
    integration = MockSyncIntegration(civi_settings)

    # Verify protocol conformance
    assert isinstance(integration, IntegrationProtocol)

    # Test interface methods
    assert integration.is_async() is False
    assert isinstance(integration.get_settings(), CiviSettings)
    assert isinstance(integration.get_client(), SyncCiviClient)


@pytest.mark.asyncio
async def test_async_lifecycle_hooks(civi_settings: CiviSettings) -> None:
    """Test that async integration implements LifecycleHooks."""
    integration = MockAsyncIntegration(civi_settings)

    # Verify protocol conformance
    assert isinstance(integration, LifecycleHooks)

    # Test lifecycle
    assert integration.client is None
    await integration.on_startup()
    assert integration.client is not None
    await integration.on_shutdown()
    assert integration.client is None


def test_sync_lifecycle_hooks(civi_settings: CiviSettings) -> None:
    """Test that sync integration implements LifecycleHooks."""
    integration = MockSyncIntegration(civi_settings)

    # Verify protocol conformance
    assert isinstance(integration, LifecycleHooks)

    # Test lifecycle
    assert integration.client is None
    integration.on_startup_sync()
    assert integration.client is not None
    integration.on_shutdown_sync()
    assert integration.client is None


def test_request_context_protocol(civi_settings: CiviSettings) -> None:
    """Test that request context implements RequestContext."""
    context = MockRequestContext()

    # Verify protocol conformance
    assert isinstance(context, RequestContext)

    # Test context operations
    with pytest.raises(RuntimeError, match="No client available"):
        context.get_client()

    client = CiviClient(settings=civi_settings)
    context.set_client(client)
    assert context.get_client() is client


def test_request_context_with_sync_client(civi_settings: CiviSettings) -> None:
    """Test request context with sync client."""
    context = MockRequestContext()

    sync_client = SyncCiviClient(settings=civi_settings)
    context.set_client(sync_client)
    assert context.get_client() is sync_client


def test_integration_client_lifecycle(civi_settings: CiviSettings) -> None:
    """Test client lifecycle management."""
    async_integration = MockAsyncIntegration(civi_settings)

    # Client created lazily
    client1 = async_integration.get_client()
    client2 = async_integration.get_client()
    assert client1 is client2  # Same instance


def test_integration_settings_access(civi_settings: CiviSettings) -> None:
    """Test settings access through integration."""
    integration = MockAsyncIntegration(civi_settings)
    settings = integration.get_settings()

    assert settings.base_url == civi_settings.base_url
    assert settings.api_key == civi_settings.api_key
    assert settings.timeout == civi_settings.timeout
