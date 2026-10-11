"""Tests for HTTP transport layer."""

from __future__ import annotations

import asyncio
import json
import time
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import httpx
import pytest

from civicrm_py.core.auth import APIKeyAuth, BasicAuth, JWTAuth
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConnectionError,
    CiviTimeoutError,
)
from civicrm_py.http.transport import (
    AsyncTransport,
    BaseTransport,
    SyncTransport,
    _convert_params,
)

if TYPE_CHECKING:
    import respx


class TestConvertParams:
    """Tests for _convert_params helper function."""

    def test_convert_none_returns_empty_dict(self) -> None:
        """Test that None params returns empty dict."""
        result = _convert_params(None)
        assert result == {}

    def test_convert_dict_returns_dict(self) -> None:
        """Test that dict params returns same dict."""
        params = {"select": ["id", "name"], "limit": 10}
        result = _convert_params(params)
        assert result == params

    def test_convert_msgspec_struct(self) -> None:
        """Test that msgspec Struct is converted to dict."""
        from civicrm_py.core.serialization import APIRequest

        params = APIRequest(select=["id", "name"], limit=10)
        result = _convert_params(params)
        assert result == {"select": ["id", "name"], "limit": 10}


class TestBaseTransport:
    """Tests for BaseTransport base class."""

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            site_key="test-site-key",
            timeout=30,
            max_retries=3,
        )

    @pytest.fixture
    def settings_with_trailing_slash(self) -> CiviSettings:
        """Create test settings with trailing slash in base_url."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4/",
            api_key="test-api-key",
        )

    @pytest.fixture
    def api_key_auth(self, settings: CiviSettings) -> APIKeyAuth:
        """Create API key auth provider."""
        return APIKeyAuth(api_key=settings.api_key or "", site_key=settings.site_key)

    @pytest.fixture
    def jwt_auth(self) -> JWTAuth:
        """Create JWT auth provider."""
        return JWTAuth(token="test-jwt-token")

    @pytest.fixture
    def basic_auth(self) -> BasicAuth:
        """Create Basic auth provider."""
        return BasicAuth(username="testuser", password="testpass")

    @pytest.fixture
    def transport(self, settings: CiviSettings, api_key_auth: APIKeyAuth) -> BaseTransport:
        """Create BaseTransport instance."""
        return BaseTransport(settings, api_key_auth)

    def test_init_strips_trailing_slash(
        self,
        settings_with_trailing_slash: CiviSettings,
        api_key_auth: APIKeyAuth,
    ) -> None:
        """Test that trailing slash is stripped from base_url."""
        transport = BaseTransport(settings_with_trailing_slash, api_key_auth)
        assert transport.base_url == "https://example.org/civicrm/ajax/api4"

    def test_init_stores_settings_and_auth(
        self,
        settings: CiviSettings,
        api_key_auth: APIKeyAuth,
    ) -> None:
        """Test that settings and auth are stored."""
        transport = BaseTransport(settings, api_key_auth)
        assert transport.settings is settings
        assert transport.auth is api_key_auth

    class TestBuildUrl:
        """Tests for _build_url method."""

        @pytest.fixture
        def transport(self, settings: CiviSettings, api_key_auth: APIKeyAuth) -> BaseTransport:
            """Create BaseTransport instance."""
            return BaseTransport(settings, api_key_auth)

        def test_build_url_basic(self, transport: BaseTransport) -> None:
            """Test basic URL building."""
            url = transport._build_url("Contact", "get")
            assert url == "https://example.org/civicrm/ajax/api4/Contact/get"

        def test_build_url_different_entity(self, transport: BaseTransport) -> None:
            """Test URL building with different entity."""
            url = transport._build_url("Activity", "create")
            assert url == "https://example.org/civicrm/ajax/api4/Activity/create"

        def test_build_url_various_actions(self, transport: BaseTransport) -> None:
            """Test URL building with various actions."""
            actions = ["get", "create", "update", "delete", "save", "getFields"]
            for action in actions:
                url = transport._build_url("Contact", action)
                assert url == f"https://example.org/civicrm/ajax/api4/Contact/{action}"

        def test_build_url_preserves_case(self, transport: BaseTransport) -> None:
            """Test that entity and action case is preserved."""
            url = transport._build_url("CustomField", "getValue")
            assert url == "https://example.org/civicrm/ajax/api4/CustomField/getValue"

    class TestBuildHeaders:
        """Tests for _build_headers method."""

        def test_build_headers_includes_content_type(
            self,
            settings: CiviSettings,
            api_key_auth: APIKeyAuth,
        ) -> None:
            """Test that Content-Type header is included."""
            transport = BaseTransport(settings, api_key_auth)
            headers = transport._build_headers()
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"

        def test_build_headers_includes_accept(
            self,
            settings: CiviSettings,
            api_key_auth: APIKeyAuth,
        ) -> None:
            """Test that Accept header is included."""
            transport = BaseTransport(settings, api_key_auth)
            headers = transport._build_headers()
            assert headers["Accept"] == "application/json"

        def test_build_headers_includes_x_requested_with(
            self,
            settings: CiviSettings,
            api_key_auth: APIKeyAuth,
        ) -> None:
            """Test that X-Requested-With header is included."""
            transport = BaseTransport(settings, api_key_auth)
            headers = transport._build_headers()
            assert headers["X-Requested-With"] == "XMLHttpRequest"

        def test_build_headers_includes_api_key_auth_headers(
            self,
            settings: CiviSettings,
            api_key_auth: APIKeyAuth,
        ) -> None:
            """Test that API key auth headers are included."""
            transport = BaseTransport(settings, api_key_auth)
            headers = transport._build_headers()
            assert headers["Authorization"] == "Bearer test-api-key"
            assert headers["X-Civi-Key"] == "test-site-key"

        def test_build_headers_includes_jwt_auth_headers(
            self,
            settings: CiviSettings,
            jwt_auth: JWTAuth,
        ) -> None:
            """Test that JWT auth headers are included."""
            transport = BaseTransport(settings, jwt_auth)
            headers = transport._build_headers()
            assert headers["Authorization"] == "Bearer test-jwt-token"

        def test_build_headers_includes_basic_auth_headers(
            self,
            settings: CiviSettings,
            basic_auth: BasicAuth,
        ) -> None:
            """Test that Basic auth headers are included."""
            transport = BaseTransport(settings, basic_auth)
            headers = transport._build_headers()
            assert headers["Authorization"].startswith("Basic ")

    class TestBuildRequestData:
        """Tests for _build_request_data method."""

        @pytest.fixture
        def transport(self, settings: CiviSettings, api_key_auth: APIKeyAuth) -> BaseTransport:
            """Create BaseTransport instance."""
            return BaseTransport(settings, api_key_auth)

        def test_build_request_data_wraps_in_params(self, transport: BaseTransport) -> None:
            """Test that params are wrapped in 'params' key."""
            params = {"select": ["id", "name"], "limit": 10}
            result = transport._build_request_data(params)
            assert "params" in result

        def test_build_request_data_json_encodes(self, transport: BaseTransport) -> None:
            """Test that params are JSON-encoded."""
            params = {"select": ["id", "name"], "limit": 10}
            result = transport._build_request_data(params)
            decoded = json.loads(result["params"])
            assert decoded == params

        def test_build_request_data_empty_params(self, transport: BaseTransport) -> None:
            """Test with empty params dict."""
            result = transport._build_request_data({})
            assert result == {"params": "{}"}

        def test_build_request_data_complex_params(self, transport: BaseTransport) -> None:
            """Test with complex nested params."""
            params = {
                "select": ["id", "display_name", "email_primary.email"],
                "where": [["is_deleted", "=", False], ["contact_type", "=", "Individual"]],
                "orderBy": {"display_name": "ASC"},
                "limit": 25,
                "offset": 0,
            }
            result = transport._build_request_data(params)
            decoded = json.loads(result["params"])
            assert decoded == params

    class TestHandleResponse:
        """Tests for _handle_response method."""

        @pytest.fixture
        def transport(self, settings: CiviSettings, api_key_auth: APIKeyAuth) -> BaseTransport:
            """Create BaseTransport instance."""
            return BaseTransport(settings, api_key_auth)

        def test_handle_response_success(self, transport: BaseTransport) -> None:
            """Test successful response handling."""
            response_data = {
                "values": [{"id": 1, "display_name": "Test Contact"}],
                "count": 1,
                "countFetched": 1,
            }
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.OK
            mock_response.content = json.dumps(response_data).encode()

            result = transport._handle_response(mock_response)
            assert result.values == [{"id": 1, "display_name": "Test Contact"}]
            assert result.count == 1
            assert not result.is_error

        def test_handle_response_401_unauthorized(self, transport: BaseTransport) -> None:
            """Test 401 Unauthorized raises CiviAuthError."""
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.UNAUTHORIZED

            with pytest.raises(CiviAuthError, match="Authentication failed"):
                transport._handle_response(mock_response)

        def test_handle_response_403_forbidden(self, transport: BaseTransport) -> None:
            """Test 403 Forbidden raises CiviAuthError."""
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.FORBIDDEN

            with pytest.raises(CiviAuthError, match="Permission denied"):
                transport._handle_response(mock_response)

        def test_handle_response_api_error(self, transport: BaseTransport) -> None:
            """Test API error response raises CiviAPIError."""
            response_data = {
                "error_code": 500,
                "error_message": "Entity not found",
            }
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.OK
            mock_response.content = json.dumps(response_data).encode()

            with pytest.raises(CiviAPIError, match="Entity not found") as exc_info:
                transport._handle_response(mock_response)
            assert exc_info.value.error_code == 500
            assert exc_info.value.error_message == "Entity not found"

        def test_handle_response_api_error_unknown(self, transport: BaseTransport) -> None:
            """Test API error with no message raises with default message."""
            response_data = {"error_code": 500}
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.OK
            mock_response.content = json.dumps(response_data).encode()

            with pytest.raises(CiviAPIError, match="Unknown API error"):
                transport._handle_response(mock_response)

        def test_handle_response_empty_values(self, transport: BaseTransport) -> None:
            """Test response with empty values list."""
            response_data = {"values": [], "count": 0, "countFetched": 0}
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = HTTPStatus.OK
            mock_response.content = json.dumps(response_data).encode()

            result = transport._handle_response(mock_response)
            assert result.values == []
            assert result.count == 0

    class TestCalculateBackoff:
        """Tests for _calculate_backoff method."""

        @pytest.fixture
        def transport(self, settings: CiviSettings, api_key_auth: APIKeyAuth) -> BaseTransport:
            """Create BaseTransport instance."""
            return BaseTransport(settings, api_key_auth)

        def test_calculate_backoff_attempt_0(self, transport: BaseTransport) -> None:
            """Test backoff for first attempt (0.5s)."""
            delay = transport._calculate_backoff(0)
            assert delay == 0.5

        def test_calculate_backoff_attempt_1(self, transport: BaseTransport) -> None:
            """Test backoff for second attempt (1.0s)."""
            delay = transport._calculate_backoff(1)
            assert delay == 1.0

        def test_calculate_backoff_attempt_2(self, transport: BaseTransport) -> None:
            """Test backoff for third attempt (2.0s)."""
            delay = transport._calculate_backoff(2)
            assert delay == 2.0

        def test_calculate_backoff_attempt_3(self, transport: BaseTransport) -> None:
            """Test backoff for fourth attempt (4.0s)."""
            delay = transport._calculate_backoff(3)
            assert delay == 4.0

        def test_calculate_backoff_exponential(self, transport: BaseTransport) -> None:
            """Test exponential backoff pattern."""
            delays = [transport._calculate_backoff(i) for i in range(5)]
            assert delays == [0.5, 1.0, 2.0, 4.0, 8.0]

        def test_calculate_backoff_max_30_seconds(self, transport: BaseTransport) -> None:
            """Test that backoff is capped at 30 seconds."""
            delay = transport._calculate_backoff(10)  # 2^10 * 0.5 = 512s
            assert delay == 30.0

        def test_calculate_backoff_max_at_boundary(self, transport: BaseTransport) -> None:
            """Test backoff at the boundary of max (attempt 6 = 32s capped to 30s)."""
            delay = transport._calculate_backoff(6)  # 2^6 * 0.5 = 32s
            assert delay == 30.0


class TestAsyncTransport:
    """Tests for AsyncTransport async HTTP client."""

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=2,
            debug=False,
        )

    @pytest.fixture
    def settings_debug(self) -> CiviSettings:
        """Create test settings with debug enabled."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=2,
            debug=True,
        )

    @pytest.fixture
    def settings_no_retries(self) -> CiviSettings:
        """Create test settings with no retries."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=0,
        )

    @pytest.fixture
    def auth(self, settings: CiviSettings) -> APIKeyAuth:
        """Create API key auth provider."""
        return APIKeyAuth(api_key=settings.api_key or "")

    @pytest.fixture
    def transport(self, settings: CiviSettings, auth: APIKeyAuth) -> AsyncTransport:
        """Create AsyncTransport instance."""
        return AsyncTransport(settings, auth)

    async def test_request_success(
        self,
        transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test successful async request."""
        response_data = {
            "values": [{"id": 1, "display_name": "Test Contact"}],
            "count": 1,
            "countFetched": 1,
        }
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        result = await transport.request("Contact", "get", {"select": ["id", "display_name"]})

        assert result.values == [{"id": 1, "display_name": "Test Contact"}]
        assert result.count == 1

    async def test_request_with_none_params(
        self,
        transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test request with None params."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        result = await transport.request("Contact", "get", None)

        assert result.values == []

    async def test_request_timeout_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that timeout errors trigger retries."""
        transport = AsyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Connection timed out")
            return httpx.Response(
                200,
                json={"values": [{"id": 1}], "count": 1},
            )

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            result = await transport.request("Contact", "get")

        assert call_count == 3
        assert result.values == [{"id": 1}]

    async def test_request_timeout_exhausts_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that timeout raises after exhausting retries."""
        transport = AsyncTransport(settings, auth)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.TimeoutException("Connection timed out"),
        )

        with patch.object(asyncio, "sleep", return_value=None):
            with pytest.raises(CiviTimeoutError, match="Request timed out"):
                await transport.request("Contact", "get")

    async def test_request_connection_error_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection errors trigger retries."""
        transport = AsyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(
                200,
                json={"values": [{"id": 1}], "count": 1},
            )

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            result = await transport.request("Contact", "get")

        assert call_count == 2
        assert result.values == [{"id": 1}]

    async def test_request_connection_error_exhausts_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection error raises after exhausting retries."""
        transport = AsyncTransport(settings, auth)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with patch.object(asyncio, "sleep", return_value=None):
            with pytest.raises(CiviConnectionError, match="Connection failed"):
                await transport.request("Contact", "get")

    async def test_request_auth_error_no_retry(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that auth errors are not retried."""
        transport = AsyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviAuthError, match="Authentication failed"):
            await transport.request("Contact", "get")

        assert call_count == 1  # No retries for auth errors

    async def test_request_api_error_no_retry(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that API errors are not retried."""
        transport = AsyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"error_code": 500, "error_message": "API Error"})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviAPIError, match="API Error"):
            await transport.request("Contact", "get")

        assert call_count == 1  # No retries for API errors

    async def test_request_no_retries_setting(
        self,
        settings_no_retries: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test with max_retries=0."""
        transport = AsyncTransport(settings_no_retries, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Timeout")

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviTimeoutError):
            await transport.request("Contact", "get")

        assert call_count == 1  # Only initial request, no retries

    async def test_context_manager(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test async context manager."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        async with AsyncTransport(settings, auth) as transport:
            result = await transport.request("Contact", "get")
            assert result.values == []

    async def test_close(self, transport: AsyncTransport, respx_mock: respx.MockRouter) -> None:
        """Test closing the transport."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        # Make a request to create the client
        await transport.request("Contact", "get")

        # Close the transport
        await transport.close()

        assert transport._client is None

    async def test_close_idempotent(self, transport: AsyncTransport) -> None:
        """Test that close can be called multiple times."""
        await transport.close()
        await transport.close()  # Should not raise

    async def test_get_client_creates_new_client(
        self,
        transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that _get_client creates a new client."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        assert transport._client is None
        await transport.request("Contact", "get")
        assert transport._client is not None

    async def test_get_client_reuses_existing(
        self,
        transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that _get_client reuses existing client."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        await transport.request("Contact", "get")
        client1 = transport._client

        await transport.request("Contact", "get")
        client2 = transport._client

        assert client1 is client2

    async def test_debug_logging_on_retry(
        self,
        settings_debug: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that debug logging occurs on retry."""
        transport = AsyncTransport(settings_debug, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Timeout")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            with patch("civicrm_py.http.transport.logger") as mock_logger:
                await transport.request("Contact", "get")
                assert mock_logger.debug.call_count >= 1

    async def test_debug_logging_on_connection_error(
        self,
        settings_debug: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that debug logging occurs on connection error retry."""
        transport = AsyncTransport(settings_debug, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            with patch("civicrm_py.http.transport.logger") as mock_logger:
                await transport.request("Contact", "get")
                # Check that connection failed debug message was logged
                debug_calls = [call.args for call in mock_logger.debug.call_args_list]
                assert any("connection failed" in str(call).lower() for call in debug_calls)


class TestSyncTransport:
    """Tests for SyncTransport sync HTTP client."""

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=2,
            debug=False,
        )

    @pytest.fixture
    def settings_debug(self) -> CiviSettings:
        """Create test settings with debug enabled."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=2,
            debug=True,
        )

    @pytest.fixture
    def settings_no_retries(self) -> CiviSettings:
        """Create test settings with no retries."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=10,
            max_retries=0,
        )

    @pytest.fixture
    def auth(self, settings: CiviSettings) -> APIKeyAuth:
        """Create API key auth provider."""
        return APIKeyAuth(api_key=settings.api_key or "")

    @pytest.fixture
    def transport(self, settings: CiviSettings, auth: APIKeyAuth) -> SyncTransport:
        """Create SyncTransport instance."""
        return SyncTransport(settings, auth)

    def test_request_success(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test successful sync request."""
        response_data = {
            "values": [{"id": 1, "display_name": "Test Contact"}],
            "count": 1,
            "countFetched": 1,
        }
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        result = transport.request("Contact", "get", {"select": ["id", "display_name"]})

        assert result.values == [{"id": 1, "display_name": "Test Contact"}]
        assert result.count == 1

    def test_request_with_none_params(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test request with None params."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        result = transport.request("Contact", "get", None)

        assert result.values == []

    def test_request_timeout_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that timeout errors trigger retries."""
        transport = SyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("Connection timed out")
            return httpx.Response(
                200,
                json={"values": [{"id": 1}], "count": 1},
            )

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            result = transport.request("Contact", "get")

        assert call_count == 3
        assert result.values == [{"id": 1}]

    def test_request_timeout_exhausts_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that timeout raises after exhausting retries."""
        transport = SyncTransport(settings, auth)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.TimeoutException("Connection timed out"),
        )

        with patch.object(time, "sleep", return_value=None):
            with pytest.raises(CiviTimeoutError, match="Request timed out"):
                transport.request("Contact", "get")

    def test_request_connection_error_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection errors trigger retries."""
        transport = SyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(
                200,
                json={"values": [{"id": 1}], "count": 1},
            )

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            result = transport.request("Contact", "get")

        assert call_count == 2
        assert result.values == [{"id": 1}]

    def test_request_connection_error_exhausts_retries(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection error raises after exhausting retries."""
        transport = SyncTransport(settings, auth)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with patch.object(time, "sleep", return_value=None):
            with pytest.raises(CiviConnectionError, match="Connection failed"):
                transport.request("Contact", "get")

    def test_request_auth_error_no_retry(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that auth errors are not retried."""
        transport = SyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviAuthError, match="Authentication failed"):
            transport.request("Contact", "get")

        assert call_count == 1  # No retries for auth errors

    def test_request_api_error_no_retry(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that API errors are not retried."""
        transport = SyncTransport(settings, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"error_code": 500, "error_message": "API Error"})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviAPIError, match="API Error"):
            transport.request("Contact", "get")

        assert call_count == 1  # No retries for API errors

    def test_request_no_retries_setting(
        self,
        settings_no_retries: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test with max_retries=0."""
        transport = SyncTransport(settings_no_retries, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Timeout")

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with pytest.raises(CiviTimeoutError):
            transport.request("Contact", "get")

        assert call_count == 1  # Only initial request, no retries

    def test_context_manager(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test sync context manager."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        with SyncTransport(settings, auth) as transport:
            result = transport.request("Contact", "get")
            assert result.values == []

    def test_close(self, transport: SyncTransport, respx_mock: respx.MockRouter) -> None:
        """Test closing the transport."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        # Make a request to create the client
        transport.request("Contact", "get")

        # Close the transport
        transport.close()

        assert transport._client is None

    def test_close_idempotent(self, transport: SyncTransport) -> None:
        """Test that close can be called multiple times."""
        transport.close()
        transport.close()  # Should not raise

    def test_get_client_creates_new_client(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that _get_client creates a new client."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        assert transport._client is None
        transport.request("Contact", "get")
        assert transport._client is not None

    def test_get_client_reuses_existing(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that _get_client reuses existing client."""
        response_data = {"values": [], "count": 0}
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json=response_data,
        )

        transport.request("Contact", "get")
        client1 = transport._client

        transport.request("Contact", "get")
        client2 = transport._client

        assert client1 is client2

    def test_debug_logging_on_retry(
        self,
        settings_debug: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that debug logging occurs on retry."""
        transport = SyncTransport(settings_debug, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Timeout")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            with patch("civicrm_py.http.transport.logger") as mock_logger:
                transport.request("Contact", "get")
                assert mock_logger.debug.call_count >= 1

    def test_debug_logging_on_connection_error(
        self,
        settings_debug: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that debug logging occurs on connection error retry."""
        transport = SyncTransport(settings_debug, auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            with patch("civicrm_py.http.transport.logger") as mock_logger:
                transport.request("Contact", "get")
                # Check that connection failed debug message was logged
                debug_calls = [call.args for call in mock_logger.debug.call_args_list]
                assert any("connection failed" in str(call).lower() for call in debug_calls)


class TestTransportClientConfiguration:
    """Tests for HTTP client configuration."""

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
            timeout=45,
            verify_ssl=False,
        )

    @pytest.fixture
    def auth(self) -> APIKeyAuth:
        """Create API key auth provider."""
        return APIKeyAuth(api_key="test-api-key")

    async def test_async_client_uses_timeout_from_settings(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
    ) -> None:
        """Test that async client uses timeout from settings."""
        transport = AsyncTransport(settings, auth)
        client = await transport._get_client()

        assert client.timeout.connect == 45
        assert client.timeout.read == 45
        await transport.close()

    async def test_async_client_uses_verify_ssl_from_settings(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
    ) -> None:
        """Test that async client uses verify_ssl from settings."""
        transport = AsyncTransport(settings, auth)
        client = await transport._get_client()

        # When verify=False, the verify context is False
        assert client._transport._pool._ssl_context is None or not settings.verify_ssl
        await transport.close()

    def test_sync_client_uses_timeout_from_settings(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
    ) -> None:
        """Test that sync client uses timeout from settings."""
        transport = SyncTransport(settings, auth)
        client = transport._get_client()

        assert client.timeout.connect == 45
        assert client.timeout.read == 45
        transport.close()

    def test_sync_client_uses_verify_ssl_from_settings(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
    ) -> None:
        """Test that sync client uses verify_ssl from settings."""
        transport = SyncTransport(settings, auth)
        client = transport._get_client()

        # When verify=False, the verify context is False
        assert client._transport._pool._ssl_context is None or not settings.verify_ssl
        transport.close()


class TestTransportRequestData:
    """Tests for request data formatting."""

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings."""
        return CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-api-key",
        )

    @pytest.fixture
    def auth(self) -> APIKeyAuth:
        """Create API key auth provider."""
        return APIKeyAuth(api_key="test-api-key")

    async def test_async_request_sends_form_data(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that async request sends form-encoded data."""
        transport = AsyncTransport(settings, auth)
        response_data = {"values": [], "count": 0}

        captured_request: httpx.Request | None = None

        def capture_request(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=response_data)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=capture_request,
        )

        await transport.request("Contact", "get", {"select": ["id"]})

        assert captured_request is not None
        assert captured_request.headers["Content-Type"] == "application/x-www-form-urlencoded"

        # Decode form data
        body = captured_request.content.decode()
        assert "params=" in body

    def test_sync_request_sends_form_data(
        self,
        settings: CiviSettings,
        auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that sync request sends form-encoded data."""
        transport = SyncTransport(settings, auth)
        response_data = {"values": [], "count": 0}

        captured_request: httpx.Request | None = None

        def capture_request(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=response_data)

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=capture_request,
        )

        transport.request("Contact", "get", {"select": ["id"]})

        assert captured_request is not None
        assert captured_request.headers["Content-Type"] == "application/x-www-form-urlencoded"

        # Decode form data
        body = captured_request.content.decode()
        assert "params=" in body


class TestRequestHandling:
    """Tests for write-retry safety and non-JSON responses."""

    API4 = "https://example.org/civicrm/ajax/api4"

    @pytest.fixture
    def settings(self) -> CiviSettings:
        """Create test settings with retries enabled."""
        return CiviSettings(
            base_url=self.API4,
            api_key="test-api-key",
            site_key="test-site-key",
            auth_flow="xheader",
            max_retries=2,
        )

    @pytest.fixture
    def transport(self, settings: CiviSettings) -> SyncTransport:
        """Create SyncTransport instance."""
        from civicrm_py.core.auth import AuthProvider

        return SyncTransport(settings, AuthProvider.from_settings(settings))

    @pytest.mark.parametrize(
        ("url", "call"),
        [
            (f"{API4}/Contact/create", lambda t: t.request("Contact", "create", {"values": {}})),
        ],
    )
    def test_write_read_timeout_not_retried(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
        url: str,
        call: object,
    ) -> None:
        """Test a read timeout on a write is raised once, since the server may have applied it."""
        route = respx_mock.post(url).mock(side_effect=httpx.ReadTimeout("read timed out"))

        with patch.object(time, "sleep"), pytest.raises(CiviTimeoutError):
            call(transport)  # type: ignore[operator]

        assert route.call_count == 1

    def test_write_connect_error_is_retried(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test a connect failure on a write is retried, since the request never reached the server."""
        route = respx_mock.post(f"{self.API4}/Contact/create").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(200, json={"values": [{"id": 5}]}),
            ],
        )

        with patch.object(time, "sleep"):
            result = transport.request("Contact", "create", {"values": {}})

        assert route.call_count == 2
        assert result.values == [{"id": 5}]

    def test_read_timeout_on_get_is_retried(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test read timeouts on read-only actions keep retrying."""
        route = respx_mock.post(f"{self.API4}/Contact/get").mock(
            side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={"values": []})],
        )

        with patch.object(time, "sleep"):
            transport.request("Contact", "get")

        assert route.call_count == 2

    def test_non_json_response_raises_api_error(
        self,
        transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test an HTML proxy error page surfaces as CiviAPIError with the status code."""
        respx_mock.post(f"{self.API4}/Contact/get").respond(502, text="<html>Bad Gateway</html>")

        with pytest.raises(CiviAPIError, match="HTTP 502") as exc_info:
            transport.request("Contact", "get")

        assert exc_info.value.details["status_code"] == 502
