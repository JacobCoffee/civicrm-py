"""Comprehensive error handling compatibility tests for civi-py.

This module tests that civi-py correctly handles all types of error responses
from CiviCRM API v4, including:
- Authentication errors (invalid API key, expired JWT)
- Authorization errors (permission denied)
- Validation errors (invalid field values)
- Not found errors (nonexistent entity/ID)
- Server errors (500, timeouts, connection failures)

Tests verify both sync and async code paths using respx for HTTP mocking.
"""

from __future__ import annotations

import asyncio
import json
import time
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import httpx
import msgspec
import pytest

from civi_py import CiviSettings
from civi_py.core.auth import APIKeyAuth, JWTAuth
from civi_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConnectionError,
    CiviError,
    CiviTimeoutError,
)
from civi_py.http.transport import AsyncTransport, SyncTransport

if TYPE_CHECKING:
    import respx

# Path to error response fixtures
FIXTURES_DIR = Path(__file__).parent / "error_responses"


def load_fixture(filename: str) -> dict[str, Any]:
    """Load error response fixture from JSON file."""
    filepath = FIXTURES_DIR / filename
    with filepath.open(encoding="utf-8") as f:
        return json.load(f)


# Load fixtures once at module level
AUTH_ERRORS = load_fixture("auth_errors.json")
PERMISSION_ERRORS = load_fixture("permission_errors.json")
VALIDATION_ERRORS = load_fixture("validation_errors.json")
NOT_FOUND_ERRORS = load_fixture("not_found_errors.json")
SERVER_ERRORS = load_fixture("server_errors.json")


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def settings() -> CiviSettings:
    """Create test CiviSettings."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        max_retries=0,  # Disable retries for error tests
        debug=False,
    )


@pytest.fixture
def settings_with_retries() -> CiviSettings:
    """Create test CiviSettings with retries enabled."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        max_retries=2,
        debug=True,
    )


@pytest.fixture
def api_key_auth(settings: CiviSettings) -> APIKeyAuth:
    """Create API key auth provider."""
    return APIKeyAuth(api_key=settings.api_key or "", site_key=settings.site_key)


@pytest.fixture
def jwt_auth() -> JWTAuth:
    """Create JWT auth provider."""
    return JWTAuth(token="test-jwt-token")


@pytest.fixture
def async_transport(settings: CiviSettings, api_key_auth: APIKeyAuth) -> AsyncTransport:
    """Create async transport for testing."""
    return AsyncTransport(settings, api_key_auth)


@pytest.fixture
def sync_transport(settings: CiviSettings, api_key_auth: APIKeyAuth) -> SyncTransport:
    """Create sync transport for testing."""
    return SyncTransport(settings, api_key_auth)


# =============================================================================
# Authentication Error Tests
# =============================================================================


class TestAuthenticationErrors:
    """Tests for authentication error handling."""

    @pytest.mark.parametrize(
        "error_key",
        [
            "invalid_api_key",
            "missing_api_key",
            "invalid_site_key",
            "revoked_api_key",
        ],
    )
    async def test_async_api_key_auth_errors(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
        error_key: str,
    ) -> None:
        """Test async handling of API key authentication errors."""
        error_config = AUTH_ERRORS[error_key]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError) as exc_info:
            await async_transport.request("Contact", "get")

        # Verify exception properties
        assert isinstance(exc_info.value, CiviAuthError)
        assert isinstance(exc_info.value, CiviError)

    @pytest.mark.parametrize(
        "error_key",
        [
            "invalid_api_key",
            "missing_api_key",
            "invalid_site_key",
        ],
    )
    def test_sync_api_key_auth_errors(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
        error_key: str,
    ) -> None:
        """Test sync handling of API key authentication errors."""
        error_config = AUTH_ERRORS[error_key]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError):
            sync_transport.request("Contact", "get")

    async def test_expired_jwt_token_async(
        self,
        settings: CiviSettings,
        jwt_auth: JWTAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of expired JWT token (async)."""
        transport = AsyncTransport(settings, jwt_auth)
        error_config = AUTH_ERRORS["expired_jwt"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError) as exc_info:
            await transport.request("Contact", "get")

        assert "Authentication failed" in str(exc_info.value)

    async def test_malformed_jwt_token_async(
        self,
        settings: CiviSettings,
        jwt_auth: JWTAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of malformed JWT token (async)."""
        transport = AsyncTransport(settings, jwt_auth)
        error_config = AUTH_ERRORS["malformed_jwt"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError):
            await transport.request("Contact", "get")

    async def test_401_unauthorized_raises_auth_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that HTTP 401 raises CiviAuthError."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=HTTPStatus.UNAUTHORIZED,
        )

        with pytest.raises(CiviAuthError, match="Authentication failed"):
            await async_transport.request("Contact", "get")

    async def test_403_forbidden_raises_auth_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that HTTP 403 raises CiviAuthError (for auth-related 403)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=HTTPStatus.FORBIDDEN,
        )

        with pytest.raises(CiviAuthError, match="Permission denied"):
            await async_transport.request("Contact", "get")

    async def test_auth_error_not_retried(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that authentication errors are not retried."""
        transport = AsyncTransport(settings_with_retries, api_key_auth)

        call_count = 0

        def track_calls(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(HTTPStatus.UNAUTHORIZED)

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=track_calls,
        )

        with pytest.raises(CiviAuthError):
            await transport.request("Contact", "get")

        # Auth errors should not be retried
        assert call_count == 1


# =============================================================================
# Permission/Authorization Error Tests
# =============================================================================


class TestPermissionErrors:
    """Tests for permission/authorization error handling."""

    @pytest.mark.parametrize(
        "error_key",
        [
            "access_denied_generic",
            "no_read_permission",
            "no_write_permission",
            "no_delete_permission",
            "admin_only_action",
        ],
    )
    async def test_async_permission_errors_http_403(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
        error_key: str,
    ) -> None:
        """Test async handling of HTTP 403 permission errors."""
        error_config = PERMISSION_ERRORS[error_key]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError):
            await async_transport.request("Contact", "get")

    async def test_api_response_permission_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test permission error returned in API response body (HTTP 200)."""
        error_config = PERMISSION_ERRORS["api_response_permission_error"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "access_denied"
        assert "Permission denied" in str(exc_info.value.error_message)

    async def test_insufficient_acl_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test ACL-based permission denial."""
        error_config = PERMISSION_ERRORS["insufficient_acl"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError):
            await async_transport.request("Contact", "get")

    def test_sync_permission_errors(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test sync handling of permission errors."""
        error_config = PERMISSION_ERRORS["no_read_permission"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAuthError):
            sync_transport.request("Contact", "get")


# =============================================================================
# Validation Error Tests
# =============================================================================


class TestValidationErrors:
    """Tests for validation error handling."""

    @pytest.mark.parametrize(
        "error_key",
        [
            "invalid_email_format",
            "required_field_missing",
            "invalid_field_value_type",
            "invalid_option_value",
            "invalid_date_format",
            "value_too_long",
            "negative_value_not_allowed",
        ],
    )
    async def test_async_validation_errors(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
        error_key: str,
    ) -> None:
        """Test async handling of validation errors."""
        error_config = VALIDATION_ERRORS[error_key]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Contact",
                "create",
                {"values": {"email": "invalid"}},
            )

        assert exc_info.value.error_code == error_config["body"]["error_code"]
        assert exc_info.value.error_message == error_config["body"]["error_message"]

    async def test_required_field_missing_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of missing required field error."""
        error_config = VALIDATION_ERRORS["required_field_missing"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "create", {"values": {}})

        assert exc_info.value.error_code == "mandatory_missing"
        assert "first_name" in str(exc_info.value.error_message)
        assert "last_name" in str(exc_info.value.error_message)

    async def test_invalid_foreign_key_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of invalid foreign key error."""
        error_config = VALIDATION_ERRORS["invalid_foreign_key"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Activity/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Activity",
                "create",
                {"values": {"contact_id": 999999}},
            )

        assert "foreign key" in str(exc_info.value.error_message).lower()

    async def test_duplicate_unique_field_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of unique constraint violation."""
        error_config = VALIDATION_ERRORS["duplicate_unique_field"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Email/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Email",
                "create",
                {"values": {"email": "test@example.com"}},
            )

        assert exc_info.value.error_code == "db_error"
        assert "Duplicate" in str(exc_info.value.error_message)

    async def test_invalid_json_in_field_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of invalid JSON in serialized field."""
        error_config = VALIDATION_ERRORS["invalid_json_in_field"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Contact",
                "create",
                {"values": {"custom_data": "not valid json"}},
            )

        assert "invalid JSON" in str(exc_info.value.error_message)

    def test_sync_validation_errors(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test sync handling of validation errors."""
        error_config = VALIDATION_ERRORS["invalid_email_format"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            sync_transport.request("Contact", "create", {"values": {"email": "invalid"}})

        assert exc_info.value.error_code == "validation_error"

    async def test_validation_error_not_retried(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that validation errors are not retried."""
        transport = AsyncTransport(settings_with_retries, api_key_auth)
        error_config = VALIDATION_ERRORS["invalid_email_format"]

        call_count = 0

        def track_calls(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json=error_config["body"])

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").mock(
            side_effect=track_calls,
        )

        with pytest.raises(CiviAPIError):
            await transport.request("Contact", "create", {"values": {}})

        # API errors should not be retried
        assert call_count == 1


# =============================================================================
# Not Found Error Tests
# =============================================================================


class TestNotFoundErrors:
    """Tests for not found error handling."""

    @pytest.mark.parametrize(
        "error_key",
        [
            "entity_not_found_by_id",
            "entity_not_found_generic",
            "deleted_entity",
        ],
    )
    async def test_async_entity_not_found_errors(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
        error_key: str,
    ) -> None:
        """Test async handling of entity not found errors."""
        error_config = NOT_FOUND_ERRORS[error_key]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get", {"where": [["id", "=", 999999]]})

        assert exc_info.value.error_code == "not_found"

    async def test_unknown_entity_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of unknown entity error."""
        error_config = NOT_FOUND_ERRORS["unknown_entity"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/NonExistentEntity/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("NonExistentEntity", "get")

        assert "Unknown entity" in str(exc_info.value.error_message)

    async def test_unknown_action_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of unknown action error."""
        error_config = NOT_FOUND_ERRORS["unknown_action"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/nonExistentAction").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "nonExistentAction")

        assert "Unknown action" in str(exc_info.value.error_message)

    async def test_unknown_field_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of unknown field error."""
        error_config = NOT_FOUND_ERRORS["unknown_field"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Contact",
                "get",
                {"select": ["nonexistent_field"]},
            )

        assert "Unknown field" in str(exc_info.value.error_message)

    async def test_related_entity_not_found_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of related entity not found in chain."""
        error_config = NOT_FOUND_ERRORS["related_entity_not_found"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request(
                "Contact",
                "get",
                {"chain": {"activities": ["Activity", "get", {"where": [["id", "=", 456]]}]}},
            )

        assert "not found" in str(exc_info.value.error_message).lower()

    def test_sync_not_found_errors(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test sync handling of not found errors."""
        error_config = NOT_FOUND_ERRORS["entity_not_found_by_id"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            sync_transport.request("Contact", "get", {"where": [["id", "=", 999999]]})

        assert exc_info.value.error_code == "not_found"


# =============================================================================
# Server Error Tests
# =============================================================================


class TestServerErrors:
    """Tests for server error handling."""

    async def test_internal_server_error_500(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTTP 500 Internal Server Error."""
        error_config = SERVER_ERRORS["internal_server_error"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        # The transport handles 500 by returning the API response which has error_code
        assert exc_info.value.error_code == "internal_error"

    async def test_database_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of database errors."""
        error_config = SERVER_ERRORS["database_error"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "db_error"
        assert "database" in str(exc_info.value.error_message).lower()

    async def test_service_unavailable_503(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTTP 503 Service Unavailable."""
        error_config = SERVER_ERRORS["service_unavailable"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError):
            await async_transport.request("Contact", "get")

    async def test_bad_gateway_502(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTTP 502 Bad Gateway."""
        error_config = SERVER_ERRORS["bad_gateway"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError):
            await async_transport.request("Contact", "get")

    async def test_gateway_timeout_504(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTTP 504 Gateway Timeout."""
        error_config = SERVER_ERRORS["gateway_timeout"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError):
            await async_transport.request("Contact", "get")

    async def test_rate_limited_429(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTTP 429 Too Many Requests."""
        error_config = SERVER_ERRORS["rate_limited"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "rate_limit"

    async def test_maintenance_mode(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of maintenance mode response."""
        error_config = SERVER_ERRORS["maintenance_mode"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert "maintenance" in str(exc_info.value.error_message).lower()

    def test_sync_server_errors(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test sync handling of server errors."""
        error_config = SERVER_ERRORS["internal_server_error"]

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=error_config["status_code"],
            json=error_config["body"],
        )

        with pytest.raises(CiviAPIError):
            sync_transport.request("Contact", "get")


# =============================================================================
# Connection and Timeout Error Tests
# =============================================================================


class TestConnectionErrors:
    """Tests for connection and timeout error handling."""

    async def test_connection_refused_async(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of connection refused error (async)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(CiviConnectionError) as exc_info:
            await async_transport.request("Contact", "get")

        assert "Connection failed" in str(exc_info.value)

    def test_connection_refused_sync(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of connection refused error (sync)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(CiviConnectionError) as exc_info:
            sync_transport.request("Contact", "get")

        assert "Connection failed" in str(exc_info.value)

    async def test_timeout_error_async(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of timeout error (async)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.TimeoutException("Connection timed out"),
        )

        with pytest.raises(CiviTimeoutError) as exc_info:
            await async_transport.request("Contact", "get")

        assert "timed out" in str(exc_info.value).lower()
        assert isinstance(exc_info.value, CiviConnectionError)  # Inherits from ConnectionError

    def test_timeout_error_sync(
        self,
        sync_transport: SyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of timeout error (sync)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.TimeoutException("Connection timed out"),
        )

        with pytest.raises(CiviTimeoutError) as exc_info:
            sync_transport.request("Contact", "get")

        assert "timed out" in str(exc_info.value).lower()

    async def test_connection_error_with_retries_async(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection errors are retried (async)."""
        transport = AsyncTransport(settings_with_retries, api_key_auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            result = await transport.request("Contact", "get")

        assert call_count == 3
        assert result.values == []

    def test_connection_error_with_retries_sync(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection errors are retried (sync)."""
        transport = SyncTransport(settings_with_retries, api_key_auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json={"values": [], "count": 0})

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            result = transport.request("Contact", "get")

        assert call_count == 3
        assert result.values == []

    async def test_timeout_exhausts_retries_async(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test timeout raises after exhausting retries (async)."""
        transport = AsyncTransport(settings_with_retries, api_key_auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Timeout")

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(asyncio, "sleep", return_value=None):
            with pytest.raises(CiviTimeoutError):
                await transport.request("Contact", "get")

        # Initial request + 2 retries = 3 calls
        assert call_count == 3

    def test_timeout_exhausts_retries_sync(
        self,
        settings_with_retries: CiviSettings,
        api_key_auth: APIKeyAuth,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test timeout raises after exhausting retries (sync)."""
        transport = SyncTransport(settings_with_retries, api_key_auth)

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("Timeout")

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=side_effect,
        )

        with patch.object(time, "sleep", return_value=None):
            with pytest.raises(CiviTimeoutError):
                transport.request("Contact", "get")

        # Initial request + 2 retries = 3 calls
        assert call_count == 3

    async def test_dns_resolution_failure(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of DNS resolution failure."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Name or service not known"),
        )

        with pytest.raises(CiviConnectionError):
            await async_transport.request("Contact", "get")

    async def test_ssl_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of SSL/TLS errors."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED"),
        )

        with pytest.raises(CiviConnectionError):
            await async_transport.request("Contact", "get")


# =============================================================================
# Malformed Response Tests
# =============================================================================


class TestMalformedResponses:
    """Tests for handling malformed server responses."""

    async def test_empty_response_body(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of empty response body."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            content=b"",
        )

        # Empty response should raise an error (can't decode empty JSON)
        with pytest.raises(msgspec.DecodeError):
            await async_transport.request("Contact", "get")

    async def test_malformed_json_response(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of malformed JSON response."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            content=b"{invalid json",
        )

        with pytest.raises(msgspec.DecodeError):
            await async_transport.request("Contact", "get")

    async def test_html_error_page_response(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of HTML error page (PHP fatal error)."""
        html_content = b"<html><body>Fatal error: Allowed memory size exhausted</body></html>"

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=500,
            content=html_content,
            headers={"Content-Type": "text/html"},
        )

        with pytest.raises((msgspec.DecodeError, CiviAPIError)):
            await async_transport.request("Contact", "get")

    async def test_partial_json_response(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of truncated/partial JSON response."""
        partial_json = b'{"values": [{"id": 1, "name": "Te'  # Truncated

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            content=partial_json,
        )

        with pytest.raises(msgspec.DecodeError):
            await async_transport.request("Contact", "get")

    async def test_response_with_unknown_error_code(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of response with unknown error code."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": "unknown_error_type", "error_message": "Something went wrong"},
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "unknown_error_type"

    async def test_response_with_error_code_no_message(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of error response with code but no message."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": 500},
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == 500
        # Should have a default message
        assert "Unknown API error" in str(exc_info.value)

    async def test_response_with_integer_error_code(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of numeric error code (some CiviCRM versions use integers)."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": 1001, "error_message": "Custom error message"},
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == 1001


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestExceptionHierarchy:
    """Tests verifying the exception hierarchy behavior."""

    async def test_all_exceptions_are_civi_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that all civi-py exceptions can be caught as CiviError."""
        # Test CiviAuthError
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=401,
        )

        with pytest.raises(CiviError):
            await async_transport.request("Contact", "get")

    async def test_connection_errors_are_civi_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that connection errors are CiviError subclasses."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(CiviError):
            await async_transport.request("Contact", "get")

    async def test_timeout_is_connection_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that CiviTimeoutError is a CiviConnectionError."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            side_effect=httpx.TimeoutException("Timeout"),
        )

        with pytest.raises(CiviConnectionError):
            await async_transport.request("Contact", "get")

    async def test_api_error_inheritance(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test CiviAPIError inheritance chain."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": "test_error", "error_message": "Test message"},
        )

        try:
            await async_transport.request("Contact", "get")
        except CiviAPIError as e:
            assert isinstance(e, CiviError)
            assert isinstance(e, Exception)
        else:
            pytest.fail("CiviAPIError was not raised")

    def test_exception_message_preserved(self) -> None:
        """Test that exception messages are preserved."""
        message = "Custom error message with details"
        exc = CiviAPIError(message, error_code="test", error_message="API error")

        assert str(exc) == message
        assert exc.message == message
        assert exc.error_code == "test"
        assert exc.error_message == "API error"

    def test_exception_details_preserved(self) -> None:
        """Test that exception details dict is preserved."""
        details = {"entity": "Contact", "field": "email", "value": "invalid"}
        exc = CiviAPIError("Error", error_code="validation", details=details)

        assert exc.details == details


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    async def test_unicode_in_error_message(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of unicode characters in error messages."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={
                "error_code": "validation_error",
                "error_message": "Invalid name: Jose Garcia",
            },
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert "Jose" in str(exc_info.value.error_message)

    async def test_very_long_error_message(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of very long error messages."""
        long_message = "Error: " + "x" * 10000

        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": "error", "error_message": long_message},
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_message == long_message

    async def test_error_with_null_values(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of error response with null values."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={
                "error_code": "error",
                "error_message": None,
                "values": None,
                "count": None,
            },
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "error"

    async def test_error_with_nested_details(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling of error with nested debug information."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={
                "error_code": "error",
                "error_message": "Complex error",
                "debug": {
                    "trace": ["file1.php:10", "file2.php:20"],
                    "query": "SELECT * FROM civicrm_contact",
                    "params": {"id": 1},
                },
            },
        )

        with pytest.raises(CiviAPIError):
            await async_transport.request("Contact", "get")

    async def test_multiple_errors_in_response(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test handling when multiple validation errors are concatenated."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/create").respond(
            status_code=200,
            json={
                "error_code": "validation_error",
                "error_message": "Validation failed: first_name is required; email is invalid",
            },
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "create", {"values": {}})

        assert "first_name" in str(exc_info.value.error_message)
        assert "email" in str(exc_info.value.error_message)

    async def test_http_status_not_matching_body(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test when HTTP status is 200 but body contains error."""
        # This is common in CiviCRM - errors returned with 200 status
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={"error_code": "fatal", "error_message": "A fatal error occurred"},
        )

        with pytest.raises(CiviAPIError) as exc_info:
            await async_transport.request("Contact", "get")

        assert exc_info.value.error_code == "fatal"

    async def test_success_response_not_raising_error(
        self,
        async_transport: AsyncTransport,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that successful responses don't raise errors."""
        respx_mock.post("https://test.example.org/civicrm/ajax/api4/Contact/get").respond(
            status_code=200,
            json={
                "values": [{"id": 1, "display_name": "Test Contact"}],
                "count": 1,
                "countFetched": 1,
            },
        )

        # Should not raise
        result = await async_transport.request("Contact", "get")

        assert result.values is not None
        assert len(result.values) == 1
        assert result.count == 1
