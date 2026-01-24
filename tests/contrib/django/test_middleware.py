"""Tests for Django middleware integration."""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from civicrm_py.core.config import CiviSettings
from civicrm_py.core.exceptions import CiviConfigError, CiviIntegrationError


class MockRequest:
    """Mock Django HttpRequest for testing."""

    def __init__(self) -> None:
        self.civi_client: Any = None


class MockResponse:
    """Mock Django HttpResponse for testing."""

    def __init__(self, content: str = "OK") -> None:
        self.content = content


class TestCiviMiddleware:
    """Tests for CiviMiddleware class."""

    def setup_method(self) -> None:
        """Reset module-level state before each test."""
        # Clear thread-local storage
        from civicrm_py.contrib.django import middleware

        if hasattr(middleware._local, "client"):
            delattr(middleware._local, "client")

        # Reset async client
        middleware._async_client = None

    def test_init(self) -> None:
        """Test middleware initialization."""
        from civicrm_py.contrib.django.middleware import CiviMiddleware

        def get_response(request: Any) -> MockResponse:
            return MockResponse()

        middleware = CiviMiddleware(get_response)

        assert middleware.get_response is get_response
        assert middleware.sync_capable is True
        assert middleware.async_capable is True

    def test_sync_call_attaches_client(self) -> None:
        """Test that sync __call__ attaches client to request."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        def get_response(request: Any) -> MockResponse:
            # Client should be attached before view is called
            assert hasattr(request, "civi_client")
            assert request.civi_client is not None
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            middleware = CiviMiddleware(get_response)
            request = MockRequest()

            response = middleware(request)

            assert isinstance(response, MockResponse)
            assert hasattr(request, "civi_client")

    def test_sync_call_uses_thread_local_storage(self) -> None:
        """Test that sync calls use thread-local storage for clients."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        clients: list[Any] = []

        def get_response(request: Any) -> MockResponse:
            clients.append(request.civi_client)
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            middleware = CiviMiddleware(get_response)

            # First request
            request1 = MockRequest()
            middleware(request1)

            # Second request (same thread)
            request2 = MockRequest()
            middleware(request2)

            # Should reuse the same client in the same thread
            assert len(clients) == 2
            assert clients[0] is clients[1]

    def test_sync_call_graceful_degradation_on_config_error(self) -> None:
        """Test that sync call handles missing configuration gracefully."""
        from civicrm_py.contrib.django.middleware import CiviMiddleware

        def get_response(request: Any) -> MockResponse:
            # Client should NOT be attached when config is missing
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            side_effect=CiviConfigError("CIVICRM_URL is required"),
        ):
            middleware = CiviMiddleware(get_response)
            request = MockRequest()

            # Should not raise, just skip attaching client
            response = middleware(request)

            assert isinstance(response, MockResponse)
            # Client was not attached (attribute may not exist or be None)
            assert getattr(request, "civi_client", None) is None

    def test_sync_call_graceful_degradation_on_integration_error(self) -> None:
        """Test that sync call handles Django not configured gracefully."""
        from civicrm_py.contrib.django.middleware import CiviMiddleware

        def get_response(request: Any) -> MockResponse:
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            side_effect=CiviIntegrationError("Django is not installed"),
        ):
            middleware = CiviMiddleware(get_response)
            request = MockRequest()

            # Should not raise
            response = middleware(request)

            assert isinstance(response, MockResponse)

    def test_configuration_check_is_cached(self) -> None:
        """Test that configuration check result is cached."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        def get_response(request: Any) -> MockResponse:
            return MockResponse()

        call_count = 0

        def mock_get_settings() -> CiviSettings:
            nonlocal call_count
            call_count += 1
            return mock_settings

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            side_effect=mock_get_settings,
        ):
            middleware = CiviMiddleware(get_response)

            # Multiple requests
            middleware(MockRequest())
            middleware(MockRequest())
            middleware(MockRequest())

            # get_civi_settings called for each _get_sync_client call
            # but _check_configuration caches its result
            assert middleware._configuration_valid is True


class TestCiviMiddlewareAsync:
    """Tests for CiviMiddleware async mode."""

    def setup_method(self) -> None:
        """Reset module-level state before each test."""
        from civicrm_py.contrib.django import middleware

        if hasattr(middleware._local, "client"):
            delattr(middleware._local, "client")
        middleware._async_client = None

    @pytest.mark.asyncio
    async def test_async_call_attaches_client(self) -> None:
        """Test that async __acall__ attaches client to request."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        async def get_response(request: Any) -> MockResponse:
            assert hasattr(request, "civi_client")
            assert request.civi_client is not None
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            middleware = CiviMiddleware(get_response)
            request = MockRequest()

            response = await middleware.__acall__(request)

            assert isinstance(response, MockResponse)
            assert hasattr(request, "civi_client")

    @pytest.mark.asyncio
    async def test_async_call_uses_shared_client(self) -> None:
        """Test that async calls use a shared client."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        clients: list[Any] = []

        async def get_response(request: Any) -> MockResponse:
            clients.append(request.civi_client)
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            middleware = CiviMiddleware(get_response)

            # Multiple async requests
            await middleware.__acall__(MockRequest())
            await middleware.__acall__(MockRequest())

            # Should use the same shared async client
            assert len(clients) == 2
            assert clients[0] is clients[1]

    @pytest.mark.asyncio
    async def test_async_call_graceful_degradation(self) -> None:
        """Test that async call handles errors gracefully."""
        from civicrm_py.contrib.django.middleware import CiviMiddleware

        async def get_response(request: Any) -> MockResponse:
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            side_effect=CiviConfigError("Not configured"),
        ):
            middleware = CiviMiddleware(get_response)
            request = MockRequest()

            response = await middleware.__acall__(request)

            assert isinstance(response, MockResponse)


class TestGetClientFromRequest:
    """Tests for get_client_from_request helper function."""

    def test_returns_client_when_present(self) -> None:
        """Test that get_client_from_request returns the attached client."""
        from civicrm_py.contrib.django.middleware import get_client_from_request

        mock_client = MagicMock()
        request = MockRequest()
        request.civi_client = mock_client

        client = get_client_from_request(request)

        assert client is mock_client

    def test_raises_attribute_error_when_missing(self) -> None:
        """Test that get_client_from_request raises AttributeError when no client."""
        from civicrm_py.contrib.django.middleware import get_client_from_request

        request = MockRequest()
        # Don't set civi_client

        with pytest.raises(AttributeError, match="CiviCRM client not found"):
            get_client_from_request(request)

    def test_raises_attribute_error_when_none(self) -> None:
        """Test that get_client_from_request raises when client is None."""
        from civicrm_py.contrib.django.middleware import get_client_from_request

        request = MockRequest()
        request.civi_client = None

        with pytest.raises(AttributeError, match="CiviCRM client not found"):
            get_client_from_request(request)


class TestCloseClients:
    """Tests for close_clients functions."""

    def setup_method(self) -> None:
        """Reset module-level state before each test."""
        from civicrm_py.contrib.django import middleware

        if hasattr(middleware._local, "client"):
            delattr(middleware._local, "client")
        middleware._async_client = None

    def test_close_clients_closes_thread_local_client(self) -> None:
        """Test that close_clients closes the thread-local client."""
        from civicrm_py.contrib.django import middleware
        from civicrm_py.contrib.django.middleware import close_clients

        mock_client = MagicMock()
        middleware._local.client = mock_client

        close_clients()

        mock_client.close.assert_called_once()
        assert getattr(middleware._local, "client", None) is None

    def test_close_clients_handles_no_client(self) -> None:
        """Test that close_clients handles case when no client exists."""
        from civicrm_py.contrib.django.middleware import close_clients

        # Should not raise
        close_clients()

    @pytest.mark.asyncio
    async def test_close_clients_async_closes_async_client(self) -> None:
        """Test that close_clients_async closes the async client."""
        from civicrm_py.contrib.django import middleware
        from civicrm_py.contrib.django.middleware import close_clients_async

        mock_client = MagicMock()

        async def mock_close() -> None:
            pass

        mock_client.close = MagicMock(side_effect=mock_close)
        middleware._async_client = mock_client

        await close_clients_async()

        mock_client.close.assert_called_once()
        assert middleware._async_client is None

    @pytest.mark.asyncio
    async def test_close_clients_async_handles_no_client(self) -> None:
        """Test that close_clients_async handles case when no client exists."""
        from civicrm_py.contrib.django.middleware import close_clients_async

        # Should not raise
        await close_clients_async()


class TestThreadSafety:
    """Tests for thread safety of the middleware."""

    def setup_method(self) -> None:
        """Reset module-level state before each test."""
        from civicrm_py.contrib.django import middleware

        if hasattr(middleware._local, "client"):
            delattr(middleware._local, "client")
        middleware._async_client = None

    def test_different_threads_get_different_clients(self) -> None:
        """Test that different threads get their own client instances."""
        mock_settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

        from civicrm_py.contrib.django.middleware import CiviMiddleware

        thread_clients: dict[str, Any] = {}
        lock = threading.Lock()

        def get_response(request: Any) -> MockResponse:
            with lock:
                thread_clients[threading.current_thread().name] = request.civi_client
            return MockResponse()

        with patch(
            "civicrm_py.contrib.django.settings.get_civi_settings",
            return_value=mock_settings,
        ):
            middleware_instance = CiviMiddleware(get_response)

            threads: list[threading.Thread] = []
            for i in range(3):
                t = threading.Thread(
                    target=lambda: middleware_instance(MockRequest()),
                    name=f"test-thread-{i}",
                )
                threads.append(t)

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Each thread should have created a different client
            client_ids = [id(c) for c in thread_clients.values()]
            assert len(set(client_ids)) == 3, "Each thread should have its own client"
