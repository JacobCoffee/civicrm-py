"""Comprehensive unit tests for CiviClient and SyncCiviClient.

Tests cover:
- Client initialization with CiviSettings object
- Client initialization with individual parameters
- Factory methods (from_env)
- Context manager cleanup
- All CRUD convenience methods
- Transport layer mocking
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from civi_py import CiviClient, CiviSettings
from civi_py.core.client import SyncCiviClient
from civi_py.core.serialization import APIRequest, APIResponse


class TestCiviClientInitialization:
    """Tests for CiviClient initialization."""

    def test_init_with_settings_object(self, civi_settings: CiviSettings) -> None:
        """Test client initialization with CiviSettings instance."""
        client = CiviClient(settings=civi_settings)

        assert client.settings is civi_settings
        assert client.settings.base_url == "https://test.example.org/civicrm/ajax/api4"
        assert client.settings.api_key == "test-api-key"
        assert client._transport is None

    def test_init_with_individual_params(self) -> None:
        """Test client initialization with individual parameters."""
        client = CiviClient(
            base_url="https://custom.example.org/api4",
            api_key="custom-key",
            site_key="custom-site-key",
            timeout=60,
            verify_ssl=False,
            debug=True,
            max_retries=5,
        )

        assert client.settings.base_url == "https://custom.example.org/api4"
        assert client.settings.api_key == "custom-key"
        assert client.settings.site_key == "custom-site-key"
        assert client.settings.timeout == 60
        assert client.settings.verify_ssl is False
        assert client.settings.debug is True
        assert client.settings.max_retries == 5

    def test_init_prefers_settings_over_params(self, civi_settings: CiviSettings) -> None:
        """Test that settings object takes precedence over individual params."""
        client = CiviClient(
            settings=civi_settings,
            base_url="https://ignored.example.org/api4",
            api_key="ignored-key",
        )

        # Should use settings object, not individual params
        assert client.settings.base_url == civi_settings.base_url
        assert client.settings.api_key == civi_settings.api_key

    def test_init_falls_back_to_env_when_no_params(self) -> None:
        """Test that client loads from environment when no settings/params provided."""
        env_vars = {
            "CIVI_BASE_URL": "https://env.example.org/api4",
            "CIVI_API_KEY": "env-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client = CiviClient()

            assert client.settings.base_url == "https://env.example.org/api4"
            assert client.settings.api_key == "env-key"

    def test_settings_property_returns_settings(self, civi_settings: CiviSettings) -> None:
        """Test that settings property returns the settings object."""
        client = CiviClient(settings=civi_settings)
        assert client.settings is civi_settings


class TestCiviClientFromEnv:
    """Tests for CiviClient.from_env() factory method."""

    def test_from_env_creates_client_from_environment(self) -> None:
        """Test from_env creates client with environment variables."""
        env_vars = {
            "CIVI_BASE_URL": "https://factory.example.org/api4",
            "CIVI_API_KEY": "factory-key",
            "CIVI_SITE_KEY": "factory-site-key",
            "CIVI_TIMEOUT": "45",
            "CIVI_VERIFY_SSL": "false",
            "CIVI_DEBUG": "true",
            "CIVI_MAX_RETRIES": "7",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client = CiviClient.from_env()

            assert client.settings.base_url == "https://factory.example.org/api4"
            assert client.settings.api_key == "factory-key"
            assert client.settings.site_key == "factory-site-key"
            assert client.settings.timeout == 45
            assert client.settings.verify_ssl is False
            assert client.settings.debug is True
            assert client.settings.max_retries == 7

    def test_from_env_raises_when_required_vars_missing(self) -> None:
        """Test from_env raises ValueError when required env vars missing."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="CIVI_BASE_URL"):
            CiviClient.from_env()


class TestCiviClientContextManager:
    """Tests for CiviClient async context manager."""

    async def test_aenter_returns_self(self, civi_settings: CiviSettings) -> None:
        """Test __aenter__ returns the client instance."""
        client = CiviClient(settings=civi_settings)

        result = await client.__aenter__()

        assert result is client

    async def test_aexit_closes_transport(self, civi_settings: CiviSettings) -> None:
        """Test __aexit__ closes the transport."""
        client = CiviClient(settings=civi_settings)

        # Create a mock transport
        mock_transport = AsyncMock()
        client._transport = mock_transport

        await client.__aexit__(None, None, None)

        mock_transport.close.assert_called_once()
        assert client._transport is None

    async def test_aexit_handles_none_transport(self, civi_settings: CiviSettings) -> None:
        """Test __aexit__ handles case when transport is None."""
        client = CiviClient(settings=civi_settings)
        assert client._transport is None

        # Should not raise
        await client.__aexit__(None, None, None)
        assert client._transport is None

    async def test_context_manager_usage(self, civi_settings: CiviSettings) -> None:
        """Test client can be used as async context manager."""
        async with CiviClient(settings=civi_settings) as client:
            assert isinstance(client, CiviClient)
            assert client.settings is civi_settings

    async def test_close_method_closes_transport(self, civi_settings: CiviSettings) -> None:
        """Test close() method closes the transport."""
        client = CiviClient(settings=civi_settings)

        mock_transport = AsyncMock()
        client._transport = mock_transport

        await client.close()

        mock_transport.close.assert_called_once()
        assert client._transport is None

    async def test_close_is_idempotent(self, civi_settings: CiviSettings) -> None:
        """Test close() can be called multiple times safely."""
        client = CiviClient(settings=civi_settings)

        mock_transport = AsyncMock()
        client._transport = mock_transport

        await client.close()
        await client.close()

        # Only called once since transport is None after first close
        mock_transport.close.assert_called_once()


class TestCiviClientRequest:
    """Tests for CiviClient.request() method."""

    async def test_request_creates_transport_on_first_call(self, civi_settings: CiviSettings) -> None:
        """Test request creates transport on first call."""
        client = CiviClient(settings=civi_settings)
        assert client._transport is None

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[{"id": 1}], count=1)
            mock_transport_cls.return_value = mock_transport

            await client.request("Contact", "get")

            mock_transport_cls.assert_called_once_with(civi_settings, client._auth)
            assert client._transport is mock_transport

    async def test_request_reuses_existing_transport(self, civi_settings: CiviSettings) -> None:
        """Test request reuses existing transport instance."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[{"id": 1}], count=1)
            mock_transport_cls.return_value = mock_transport

            await client.request("Contact", "get")
            await client.request("Activity", "get")

            # Transport should only be created once
            mock_transport_cls.assert_called_once()
            assert mock_transport.request.call_count == 2

    async def test_request_passes_entity_and_action(self, civi_settings: CiviSettings) -> None:
        """Test request passes entity and action to transport."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            await client.request("Contact", "get", {"limit": 10})

            mock_transport.request.assert_called_once_with("Contact", "get", {"limit": 10})

    async def test_request_with_api_request_object(self, civi_settings: CiviSettings) -> None:
        """Test request with APIRequest object."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            params = APIRequest(select=["id", "display_name"], limit=5)
            await client.request("Contact", "get", params)

            mock_transport.request.assert_called_once_with("Contact", "get", params)

    async def test_request_with_none_params(self, civi_settings: CiviSettings) -> None:
        """Test request with None params."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            await client.request("Contact", "get", None)

            mock_transport.request.assert_called_once_with("Contact", "get", None)


class TestCiviClientGetMethod:
    """Tests for CiviClient.get() convenience method."""

    async def test_get_calls_request_with_correct_action(self, civi_settings: CiviSettings) -> None:
        """Test get() calls request with 'get' action."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get("Contact")

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "get"

    async def test_get_passes_select_parameter(self, civi_settings: CiviSettings) -> None:
        """Test get() passes select parameter correctly."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get("Contact", select=["id", "display_name", "email"])

        call_args = client.request.call_args
        params = call_args[0][2]
        assert isinstance(params, APIRequest)
        assert params.select == ["id", "display_name", "email"]

    async def test_get_passes_where_parameter(self, civi_settings: CiviSettings) -> None:
        """Test get() passes where parameter correctly."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        where_clause = [["is_deleted", "=", False], ["contact_type", "=", "Individual"]]
        await client.get("Contact", where=where_clause)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert params.where == where_clause

    async def test_get_passes_order_by_parameter(self, civi_settings: CiviSettings) -> None:
        """Test get() passes order_by parameter correctly."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get("Contact", order_by={"created_date": "DESC"})

        call_args = client.request.call_args
        params = call_args[0][2]
        assert params.orderBy == {"created_date": "DESC"}

    async def test_get_passes_limit_and_offset(self, civi_settings: CiviSettings) -> None:
        """Test get() passes limit and offset parameters."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get("Contact", limit=25, offset=50)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert params.limit == 25
        assert params.offset == 50

    async def test_get_with_all_parameters(self, civi_settings: CiviSettings) -> None:
        """Test get() with all parameters combined."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get(
            "Contact",
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            order_by={"display_name": "ASC"},
            limit=10,
            offset=5,
        )

        call_args = client.request.call_args
        params = call_args[0][2]
        assert params.select == ["id", "display_name"]
        assert params.where == [["is_deleted", "=", False]]
        assert params.orderBy == {"display_name": "ASC"}
        assert params.limit == 10
        assert params.offset == 5


class TestCiviClientCreateMethod:
    """Tests for CiviClient.create() convenience method."""

    async def test_create_calls_request_with_correct_action(self, civi_settings: CiviSettings) -> None:
        """Test create() calls request with 'create' action."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        await client.create("Contact", {"first_name": "John", "last_name": "Doe"})

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "create"

    async def test_create_passes_values_in_api_request(self, civi_settings: CiviSettings) -> None:
        """Test create() passes values in APIRequest."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        values = {"first_name": "John", "last_name": "Doe", "email_primary.email": "john@example.com"}
        await client.create("Contact", values)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert isinstance(params, APIRequest)
        assert params.values == values

    async def test_create_returns_api_response(self, civi_settings: CiviSettings) -> None:
        """Test create() returns APIResponse."""
        client = CiviClient(settings=civi_settings)
        expected_response = APIResponse(values=[{"id": 100, "display_name": "John Doe"}], count=1)
        client.request = AsyncMock(return_value=expected_response)

        result = await client.create("Contact", {"first_name": "John"})

        assert result is expected_response
        assert result.values[0]["id"] == 100


class TestCiviClientUpdateMethod:
    """Tests for CiviClient.update() convenience method."""

    async def test_update_calls_request_with_correct_action(self, civi_settings: CiviSettings) -> None:
        """Test update() calls request with 'update' action."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        await client.update("Contact", {"last_name": "Smith"}, [["id", "=", 1]])

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "update"

    async def test_update_passes_values_and_where(self, civi_settings: CiviSettings) -> None:
        """Test update() passes both values and where clause."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        values = {"last_name": "Smith", "nick_name": "Johnny"}
        where = [["id", "=", 1]]
        await client.update("Contact", values, where)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert isinstance(params, APIRequest)
        assert params.values == values
        assert params.where == where

    async def test_update_with_complex_where_clause(self, civi_settings: CiviSettings) -> None:
        """Test update() with complex where clause."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        where = [["contact_type", "=", "Individual"], ["is_deleted", "=", False], ["created_date", ">", "2024-01-01"]]
        await client.update("Contact", {"source": "bulk update"}, where)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert params.where == where


class TestCiviClientDeleteMethod:
    """Tests for CiviClient.delete() convenience method."""

    async def test_delete_calls_request_with_correct_action(self, civi_settings: CiviSettings) -> None:
        """Test delete() calls request with 'delete' action."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.delete("Contact", [["id", "=", 1]])

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "delete"

    async def test_delete_passes_where_clause(self, civi_settings: CiviSettings) -> None:
        """Test delete() passes where clause correctly."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        where = [["id", "IN", [1, 2, 3]]]
        await client.delete("Contact", where)

        call_args = client.request.call_args
        params = call_args[0][2]
        assert isinstance(params, APIRequest)
        assert params.where == where
        assert params.values is None  # delete should not have values


class TestCiviClientGetFieldsMethod:
    """Tests for CiviClient.get_fields() convenience method."""

    async def test_get_fields_calls_request_with_getfields_action(self, civi_settings: CiviSettings) -> None:
        """Test get_fields() calls request with 'getFields' action."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get_fields("Contact")

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "getFields"

    async def test_get_fields_passes_empty_dict(self, civi_settings: CiviSettings) -> None:
        """Test get_fields() passes empty dict as params."""
        client = CiviClient(settings=civi_settings)
        client.request = AsyncMock(return_value=APIResponse(values=[], count=0))

        await client.get_fields("Activity")

        call_args = client.request.call_args
        assert call_args[0][2] == {}

    async def test_get_fields_returns_field_metadata(self, civi_settings: CiviSettings) -> None:
        """Test get_fields() returns field metadata."""
        client = CiviClient(settings=civi_settings)
        field_data = [
            {"name": "id", "type": "Integer", "required": False},
            {"name": "display_name", "type": "String", "required": False},
        ]
        client.request = AsyncMock(return_value=APIResponse(values=field_data, count=2))

        result = await client.get_fields("Contact")

        assert result.values == field_data
        assert result.count == 2


class TestSyncCiviClientInitialization:
    """Tests for SyncCiviClient initialization."""

    def test_init_with_settings_object(self, civi_settings: CiviSettings) -> None:
        """Test sync client initialization with CiviSettings instance."""
        client = SyncCiviClient(settings=civi_settings)

        assert client.settings is civi_settings
        assert client._transport is None

    def test_init_with_individual_params(self) -> None:
        """Test sync client initialization with individual parameters."""
        client = SyncCiviClient(
            base_url="https://sync.example.org/api4",
            api_key="sync-key",
            site_key="sync-site-key",
            timeout=45,
            verify_ssl=False,
            debug=True,
            max_retries=4,
        )

        assert client.settings.base_url == "https://sync.example.org/api4"
        assert client.settings.api_key == "sync-key"
        assert client.settings.site_key == "sync-site-key"
        assert client.settings.timeout == 45
        assert client.settings.verify_ssl is False
        assert client.settings.debug is True
        assert client.settings.max_retries == 4

    def test_init_falls_back_to_env(self) -> None:
        """Test sync client loads from environment when no settings provided."""
        env_vars = {
            "CIVI_BASE_URL": "https://sync-env.example.org/api4",
            "CIVI_API_KEY": "sync-env-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client = SyncCiviClient()

            assert client.settings.base_url == "https://sync-env.example.org/api4"


class TestSyncCiviClientFromEnv:
    """Tests for SyncCiviClient.from_env() factory method."""

    def test_from_env_creates_client(self) -> None:
        """Test from_env creates sync client from environment."""
        env_vars = {
            "CIVI_BASE_URL": "https://sync-factory.example.org/api4",
            "CIVI_API_KEY": "sync-factory-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client = SyncCiviClient.from_env()

            assert client.settings.base_url == "https://sync-factory.example.org/api4"
            assert client.settings.api_key == "sync-factory-key"


class TestSyncCiviClientContextManager:
    """Tests for SyncCiviClient context manager."""

    def test_enter_returns_self(self, civi_settings: CiviSettings) -> None:
        """Test __enter__ returns the client instance."""
        client = SyncCiviClient(settings=civi_settings)

        result = client.__enter__()

        assert result is client

    def test_exit_closes_transport(self, civi_settings: CiviSettings) -> None:
        """Test __exit__ closes the transport."""
        client = SyncCiviClient(settings=civi_settings)

        mock_transport = MagicMock()
        client._transport = mock_transport

        client.__exit__(None, None, None)

        mock_transport.close.assert_called_once()
        assert client._transport is None

    def test_context_manager_usage(self, civi_settings: CiviSettings) -> None:
        """Test sync client can be used as context manager."""
        with SyncCiviClient(settings=civi_settings) as client:
            assert isinstance(client, SyncCiviClient)

    def test_close_method_closes_transport(self, civi_settings: CiviSettings) -> None:
        """Test close() method closes the transport."""
        client = SyncCiviClient(settings=civi_settings)

        mock_transport = MagicMock()
        client._transport = mock_transport

        client.close()

        mock_transport.close.assert_called_once()
        assert client._transport is None


class TestSyncCiviClientRequest:
    """Tests for SyncCiviClient.request() method."""

    def test_request_creates_transport_on_first_call(self, civi_settings: CiviSettings) -> None:
        """Test request creates transport on first call."""
        client = SyncCiviClient(settings=civi_settings)

        with patch("civi_py.core.client.SyncTransport") as mock_transport_cls:
            mock_transport = MagicMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            client.request("Contact", "get")

            mock_transport_cls.assert_called_once_with(civi_settings, client._auth)

    def test_request_reuses_existing_transport(self, civi_settings: CiviSettings) -> None:
        """Test request reuses existing transport."""
        client = SyncCiviClient(settings=civi_settings)

        with patch("civi_py.core.client.SyncTransport") as mock_transport_cls:
            mock_transport = MagicMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            client.request("Contact", "get")
            client.request("Activity", "get")

            mock_transport_cls.assert_called_once()
            assert mock_transport.request.call_count == 2


class TestSyncCiviClientConvenienceMethods:
    """Tests for SyncCiviClient convenience methods."""

    def test_get_calls_request_correctly(self, civi_settings: CiviSettings) -> None:
        """Test get() calls request with correct parameters."""
        client = SyncCiviClient(settings=civi_settings)
        client.request = MagicMock(return_value=APIResponse(values=[], count=0))

        client.get("Contact", select=["id"], where=[["is_deleted", "=", False]], limit=10)

        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "get"
        params = call_args[0][2]
        assert params.select == ["id"]
        assert params.where == [["is_deleted", "=", False]]
        assert params.limit == 10

    def test_create_calls_request_correctly(self, civi_settings: CiviSettings) -> None:
        """Test create() calls request with correct parameters."""
        client = SyncCiviClient(settings=civi_settings)
        client.request = MagicMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        client.create("Contact", {"first_name": "Test"})

        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "create"
        params = call_args[0][2]
        assert params.values == {"first_name": "Test"}

    def test_update_calls_request_correctly(self, civi_settings: CiviSettings) -> None:
        """Test update() calls request with correct parameters."""
        client = SyncCiviClient(settings=civi_settings)
        client.request = MagicMock(return_value=APIResponse(values=[{"id": 1}], count=1))

        client.update("Contact", {"last_name": "Updated"}, [["id", "=", 1]])

        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "update"
        params = call_args[0][2]
        assert params.values == {"last_name": "Updated"}
        assert params.where == [["id", "=", 1]]

    def test_delete_calls_request_correctly(self, civi_settings: CiviSettings) -> None:
        """Test delete() calls request with correct parameters."""
        client = SyncCiviClient(settings=civi_settings)
        client.request = MagicMock(return_value=APIResponse(values=[], count=0))

        client.delete("Contact", [["id", "=", 1]])

        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "delete"
        params = call_args[0][2]
        assert params.where == [["id", "=", 1]]

    def test_get_fields_calls_request_correctly(self, civi_settings: CiviSettings) -> None:
        """Test get_fields() calls request with correct parameters."""
        client = SyncCiviClient(settings=civi_settings)
        client.request = MagicMock(return_value=APIResponse(values=[], count=0))

        client.get_fields("Contact")

        call_args = client.request.call_args
        assert call_args[0][0] == "Contact"
        assert call_args[0][1] == "getFields"
        assert call_args[0][2] == {}


class TestClientTransportIntegration:
    """Integration tests for client-transport interaction."""

    async def test_async_client_get_transport_creates_new_transport(self, civi_settings: CiviSettings) -> None:
        """Test _get_transport creates transport with correct settings."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport_cls.return_value = mock_transport

            result = await client._get_transport()

            assert result is mock_transport
            mock_transport_cls.assert_called_once_with(civi_settings, client._auth)

    async def test_async_client_get_transport_returns_cached(self, civi_settings: CiviSettings) -> None:
        """Test _get_transport returns cached transport on subsequent calls."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport_cls.return_value = mock_transport

            transport1 = await client._get_transport()
            transport2 = await client._get_transport()

            assert transport1 is transport2
            mock_transport_cls.assert_called_once()

    def test_sync_client_get_transport_creates_new_transport(self, civi_settings: CiviSettings) -> None:
        """Test _get_transport creates transport with correct settings."""
        client = SyncCiviClient(settings=civi_settings)

        with patch("civi_py.core.client.SyncTransport") as mock_transport_cls:
            mock_transport = MagicMock()
            mock_transport_cls.return_value = mock_transport

            result = client._get_transport()

            assert result is mock_transport
            mock_transport_cls.assert_called_once_with(civi_settings, client._auth)


class TestClientAuthProviderIntegration:
    """Tests for client-auth provider interaction."""

    def test_async_client_creates_auth_provider(self, civi_settings: CiviSettings) -> None:
        """Test async client creates auth provider from settings."""
        with patch("civi_py.core.client.AuthProvider") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth_cls.from_settings.return_value = mock_auth

            client = CiviClient(settings=civi_settings)

            mock_auth_cls.from_settings.assert_called_once_with(civi_settings)
            assert client._auth is mock_auth

    def test_sync_client_creates_auth_provider(self, civi_settings: CiviSettings) -> None:
        """Test sync client creates auth provider from settings."""
        with patch("civi_py.core.client.AuthProvider") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth_cls.from_settings.return_value = mock_auth

            client = SyncCiviClient(settings=civi_settings)

            mock_auth_cls.from_settings.assert_called_once_with(civi_settings)
            assert client._auth is mock_auth


def _raise_runtime_error() -> None:
    """Helper function to raise RuntimeError for testing."""
    raise RuntimeError


class TestClientEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_async_client_handles_exception_in_context(self, civi_settings: CiviSettings) -> None:
        """Test async client cleans up on exception in context manager."""
        client = CiviClient(settings=civi_settings)
        mock_transport = AsyncMock()
        client._transport = mock_transport

        with pytest.raises(RuntimeError):
            async with client:
                _raise_runtime_error()

        mock_transport.close.assert_called_once()

    def test_sync_client_handles_exception_in_context(self, civi_settings: CiviSettings) -> None:
        """Test sync client cleans up on exception in context manager."""
        client = SyncCiviClient(settings=civi_settings)
        mock_transport = MagicMock()
        client._transport = mock_transport

        with pytest.raises(RuntimeError), client:
            _raise_runtime_error()

        mock_transport.close.assert_called_once()

    async def test_multiple_entities_same_client(self, civi_settings: CiviSettings) -> None:
        """Test client can make requests to multiple entities."""
        client = CiviClient(settings=civi_settings)

        with patch("civi_py.core.client.AsyncTransport") as mock_transport_cls:
            mock_transport = AsyncMock()
            mock_transport.request.return_value = APIResponse(values=[], count=0)
            mock_transport_cls.return_value = mock_transport

            await client.get("Contact", limit=10)
            await client.get("Activity", limit=5)
            await client.get_fields("Contribution")

            assert mock_transport.request.call_count == 3
            calls = mock_transport.request.call_args_list
            assert calls[0][0][0] == "Contact"
            assert calls[1][0][0] == "Activity"
            assert calls[2][0][0] == "Contribution"
