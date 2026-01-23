"""Tests for ASGI middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from civi_py.contrib.asgi import CiviASGIMiddleware, get_civi_client
from civi_py.core.client import CiviClient
from civi_py.core.config import CiviSettings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, MutableMapping

    Scope = MutableMapping[str, Any]
    Message = Mapping[str, Any]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]


@pytest.fixture
def mock_app() -> AsyncMock:
    """Create a mock ASGI application."""
    return AsyncMock()


@pytest.fixture
def asgi_middleware(
    civi_settings: CiviSettings,
    mock_app: AsyncMock,
) -> CiviASGIMiddleware:
    """Create ASGI middleware with test settings."""
    return CiviASGIMiddleware(mock_app, settings=civi_settings)


class TestCiviASGIMiddleware:
    """Tests for CiviASGIMiddleware class."""

    def test_init_with_settings(
        self,
        civi_settings: CiviSettings,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware initialization with settings."""
        middleware = CiviASGIMiddleware(mock_app, settings=civi_settings)

        assert middleware._app is mock_app
        assert middleware._settings is civi_settings
        assert middleware._client_key == "civi_client"
        assert middleware._client is None

    def test_init_with_custom_client_key(
        self,
        civi_settings: CiviSettings,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware initialization with custom client key."""
        middleware = CiviASGIMiddleware(
            mock_app,
            settings=civi_settings,
            client_key="my_civi",
        )

        assert middleware._client_key == "my_civi"

    def test_init_without_settings(self, mock_app: AsyncMock) -> None:
        """Test middleware initialization without settings (uses env)."""
        middleware = CiviASGIMiddleware(mock_app)

        assert middleware._settings is None
        assert middleware._client is None

    def test_client_property(
        self,
        asgi_middleware: CiviASGIMiddleware,
    ) -> None:
        """Test client property returns None before initialization."""
        assert asgi_middleware.client is None

    @pytest.mark.asyncio
    async def test_handle_http_request(
        self,
        asgi_middleware: CiviASGIMiddleware,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware handles HTTP requests and injects client."""
        scope: Scope = {"type": "http", "state": {}}
        receive = AsyncMock()
        send = AsyncMock()

        await asgi_middleware(scope, receive, send)

        # Client should be initialized
        assert asgi_middleware.client is not None
        assert isinstance(asgi_middleware.client, CiviClient)

        # Client should be in scope state
        assert "civi_client" in scope["state"]
        assert scope["state"]["civi_client"] is asgi_middleware.client

        # App should be called
        mock_app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_handle_websocket_request(
        self,
        asgi_middleware: CiviASGIMiddleware,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware handles WebSocket requests."""
        scope: Scope = {"type": "websocket", "state": {}}
        receive = AsyncMock()
        send = AsyncMock()

        await asgi_middleware(scope, receive, send)

        # Client should be injected
        assert "civi_client" in scope["state"]
        mock_app.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_state_dict_if_missing(
        self,
        asgi_middleware: CiviASGIMiddleware,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware creates state dict if not present in scope."""
        scope: Scope = {"type": "http"}
        receive = AsyncMock()
        send = AsyncMock()

        await asgi_middleware(scope, receive, send)

        assert "state" in scope
        assert "civi_client" in scope["state"]

    @pytest.mark.asyncio
    async def test_passthrough_unknown_scope_type(
        self,
        asgi_middleware: CiviASGIMiddleware,
        mock_app: AsyncMock,
    ) -> None:
        """Test middleware passes through unknown scope types."""
        scope: Scope = {"type": "unknown"}
        receive = AsyncMock()
        send = AsyncMock()

        await asgi_middleware(scope, receive, send)

        # App should be called without modifications
        mock_app.assert_awaited_once_with(scope, receive, send)
        # Client should not be initialized for unknown scope
        assert asgi_middleware.client is None

    @pytest.mark.asyncio
    async def test_custom_client_key_injection(
        self,
        civi_settings: CiviSettings,
        mock_app: AsyncMock,
    ) -> None:
        """Test client is injected with custom key."""
        middleware = CiviASGIMiddleware(
            mock_app,
            settings=civi_settings,
            client_key="my_custom_client",
        )
        scope: Scope = {"type": "http", "state": {}}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert "my_custom_client" in scope["state"]
        assert "civi_client" not in scope["state"]

    @pytest.mark.asyncio
    async def test_client_reused_across_requests(
        self,
        asgi_middleware: CiviASGIMiddleware,
        mock_app: AsyncMock,
    ) -> None:
        """Test same client instance is reused across requests."""
        receive = AsyncMock()
        send = AsyncMock()

        # First request
        scope1: Scope = {"type": "http", "state": {}}
        await asgi_middleware(scope1, receive, send)
        client1 = scope1["state"]["civi_client"]

        # Second request
        scope2: Scope = {"type": "http", "state": {}}
        await asgi_middleware(scope2, receive, send)
        client2 = scope2["state"]["civi_client"]

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_startup_and_shutdown(
        self,
        asgi_middleware: CiviASGIMiddleware,
    ) -> None:
        """Test startup and shutdown lifecycle."""
        # Manual startup
        await asgi_middleware._startup()
        assert asgi_middleware.client is not None

        # Manual shutdown
        await asgi_middleware._shutdown()
        assert asgi_middleware.client is None
        # Verify client was closed (transport should be None)

    @pytest.mark.asyncio
    async def test_startup_with_env_settings(
        self,
        mock_app: AsyncMock,
    ) -> None:
        """Test startup loads settings from environment when not provided."""
        middleware = CiviASGIMiddleware(mock_app)

        with patch.dict(
            "os.environ",
            {
                "CIVI_BASE_URL": "https://env.example.org/civicrm/ajax/api4",
                "CIVI_API_KEY": "env-api-key",
            },
        ):
            await middleware._startup()

        assert middleware.client is not None
        assert middleware.client.settings.base_url == "https://env.example.org/civicrm/ajax/api4"

        await middleware._shutdown()

    @pytest.mark.asyncio
    async def test_startup_skips_if_already_initialized(
        self,
        asgi_middleware: CiviASGIMiddleware,
    ) -> None:
        """Test startup is idempotent."""
        await asgi_middleware._startup()
        first_client = asgi_middleware.client

        await asgi_middleware._startup()
        second_client = asgi_middleware.client

        assert first_client is second_client

        await asgi_middleware._shutdown()


class TestLifespanHandling:
    """Tests for ASGI lifespan protocol handling."""

    @pytest.mark.asyncio
    async def test_lifespan_startup(
        self,
        civi_settings: CiviSettings,
    ) -> None:
        """Test client is initialized on lifespan startup."""
        startup_called = False
        shutdown_called = False

        async def mock_app(
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            nonlocal startup_called, shutdown_called

            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    startup_called = True
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    shutdown_called = True
                    await send({"type": "lifespan.shutdown.complete"})
                    break

        middleware = CiviASGIMiddleware(mock_app, settings=civi_settings)
        scope: Scope = {"type": "lifespan"}

        messages = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        message_iter = iter(messages)

        async def receive() -> Message:
            return next(message_iter)

        sent_messages: list[Message] = []

        async def send(message: Message) -> None:
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert startup_called
        assert shutdown_called
        assert {"type": "lifespan.startup.complete"} in sent_messages
        assert {"type": "lifespan.shutdown.complete"} in sent_messages


class TestGetCiviClient:
    """Tests for get_civi_client helper function."""

    def test_get_client_from_scope(
        self,
        civi_settings: CiviSettings,
    ) -> None:
        """Test retrieving client from scope."""
        client = CiviClient(settings=civi_settings)
        scope: Scope = {"state": {"civi_client": client}}

        result = get_civi_client(scope)

        assert result is client

    def test_get_client_with_custom_key(
        self,
        civi_settings: CiviSettings,
    ) -> None:
        """Test retrieving client with custom key."""
        client = CiviClient(settings=civi_settings)
        scope: Scope = {"state": {"my_client": client}}

        result = get_civi_client(scope, client_key="my_client")

        assert result is client

    def test_raises_when_client_not_found(self) -> None:
        """Test error when client is not in scope."""
        scope: Scope = {"state": {}}

        with pytest.raises(RuntimeError, match="CiviClient not found"):
            get_civi_client(scope)

    def test_raises_when_state_missing(self) -> None:
        """Test error when state is not in scope."""
        scope: Scope = {}

        with pytest.raises(RuntimeError, match="CiviClient not found"):
            get_civi_client(scope)

    def test_error_message_includes_key(self) -> None:
        """Test error message includes the client key."""
        scope: Scope = {"state": {}}

        with pytest.raises(RuntimeError, match="custom_key"):
            get_civi_client(scope, client_key="custom_key")
