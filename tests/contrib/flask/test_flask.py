"""Comprehensive integration tests for Flask contrib module.

Tests for CiviFlask extension, CiviFlaskConfig, helper functions,
and request context integration.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
import respx
from flask import Flask, g
from httpx import Response

from civicrm_py.contrib.flask import (
    CiviFlask,
    CiviFlaskConfig,
    _get_bool,
    _get_int,
    get_civi_client,
)
from civicrm_py.core.config import CiviSettings

if TYPE_CHECKING:
    from flask.testing import FlaskClient


# -----------------------------------------------------------------------------
# Helper Function Tests
# -----------------------------------------------------------------------------


class TestGetBoolHelper:
    """Tests for _get_bool helper function."""

    def test_returns_default_when_none(self) -> None:
        """Test that None returns the default value."""
        assert _get_bool(None, default=False) is False
        assert _get_bool(None, default=True) is True

    def test_returns_bool_directly(self) -> None:
        """Test that boolean values are returned as-is."""
        assert _get_bool(True) is True
        assert _get_bool(False) is False
        assert _get_bool(True, default=False) is True
        assert _get_bool(False, default=True) is False

    @pytest.mark.parametrize(
        "value",
        ["true", "True", "TRUE", "1", "yes", "Yes", "YES", "on", "On", "ON"],
    )
    def test_truthy_strings(self, value: str) -> None:
        """Test various truthy string representations."""
        assert _get_bool(value) is True

    @pytest.mark.parametrize(
        "value",
        ["false", "False", "FALSE", "0", "no", "No", "NO", "off", "Off", "OFF", "anything", ""],
    )
    def test_falsy_strings(self, value: str) -> None:
        """Test various falsy string representations."""
        assert _get_bool(value) is False

    def test_non_string_non_bool_returns_default(self) -> None:
        """Test that non-string, non-bool values return default."""
        assert _get_bool(123) is False  # type: ignore[arg-type]
        assert _get_bool(123, default=True) is True  # type: ignore[arg-type]


class TestGetIntHelper:
    """Tests for _get_int helper function."""

    def test_returns_default_when_none(self) -> None:
        """Test that None returns the default value."""
        assert _get_int(None, 42) == 42
        assert _get_int(None, 0) == 0

    def test_returns_int_directly(self) -> None:
        """Test that integer values are returned as-is."""
        assert _get_int(123, 0) == 123
        assert _get_int(0, 42) == 0
        assert _get_int(-1, 0) == -1

    def test_converts_valid_string_to_int(self) -> None:
        """Test that valid numeric strings are converted."""
        assert _get_int("123", 0) == 123
        assert _get_int("0", 42) == 0
        assert _get_int("-1", 0) == -1

    def test_invalid_string_returns_default(self) -> None:
        """Test that invalid strings return the default."""
        assert _get_int("abc", 42) == 42
        assert _get_int("", 99) == 99
        assert _get_int("12.34", 0) == 0
        assert _get_int("12abc", 5) == 5


# -----------------------------------------------------------------------------
# CiviFlaskConfig Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskConfig:
    """Tests for CiviFlaskConfig dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = CiviFlaskConfig()

        assert config.settings is None
        assert config.use_thread_local is True
        assert config.register_cli is True
        assert config.debug is False

    def test_custom_values(self) -> None:
        """Test that custom values are set correctly."""
        settings = CiviSettings(
            base_url="https://example.org/civicrm/ajax/api4",
            api_key="test-key",
        )
        config = CiviFlaskConfig(
            settings=settings,
            use_thread_local=False,
            register_cli=False,
            debug=True,
        )

        assert config.settings is settings
        assert config.use_thread_local is False
        assert config.register_cli is False
        assert config.debug is True


# -----------------------------------------------------------------------------
# CiviFlask Extension Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskInitialization:
    """Tests for CiviFlask extension initialization."""

    def test_init_without_app(self) -> None:
        """Test extension can be created without app for factory pattern."""
        civi = CiviFlask()

        assert civi._app is None
        assert civi._settings is None
        assert civi._client is None

    def test_init_with_app(self) -> None:
        """Test extension initialization with Flask app."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-api-key"

        civi = CiviFlask(app)

        assert civi._app is app
        assert civi._settings is not None
        assert civi._settings.base_url == "https://example.org/civicrm/ajax/api4"
        assert civi._settings.api_key == "test-api-key"
        assert "civi" in app.extensions
        assert app.extensions["civi"] is civi

    def test_init_with_explicit_settings(self) -> None:
        """Test extension initialization with explicit CiviSettings."""
        app = Flask(__name__)
        settings = CiviSettings(
            base_url="https://custom.org/civicrm/ajax/api4",
            api_key="custom-key",
        )

        civi = CiviFlask(app, settings=settings)

        assert civi._settings is settings
        assert civi._settings.base_url == "https://custom.org/civicrm/ajax/api4"
        assert civi._settings.api_key == "custom-key"

    def test_init_with_config(self) -> None:
        """Test extension initialization with CiviFlaskConfig."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(
            use_thread_local=False,
            register_cli=False,
            debug=True,
        )
        civi = CiviFlask(app, config=config)

        assert civi._config is config
        assert civi._config.use_thread_local is False
        assert civi._config.register_cli is False

    def test_init_app_factory_pattern(self) -> None:
        """Test extension with app factory pattern."""
        civi = CiviFlask()

        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi.init_app(app)

        assert civi._app is app
        assert civi._settings is not None
        assert "civi" in app.extensions

    def test_missing_base_url_raises_error(self) -> None:
        """Test that missing CIVI_BASE_URL raises ValueError."""
        app = Flask(__name__)
        # No CIVI_BASE_URL set

        with pytest.raises(ValueError, match="CIVI_BASE_URL must be set"):
            CiviFlask(app)

    def test_base_url_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that base_url can be loaded from environment when not in app.config."""
        monkeypatch.setenv("CIVI_BASE_URL", "https://env.org/civicrm/ajax/api4")

        app = Flask(__name__)
        # base_url not in app.config - should fall back to environment
        # api_key must be in app.config (env fallback not implemented for api_key)
        app.config["CIVI_API_KEY"] = "config-api-key"

        civi = CiviFlask(app)

        # base_url loaded from environment
        assert civi._settings.base_url == "https://env.org/civicrm/ajax/api4"
        # api_key loaded from app.config
        assert civi._settings.api_key == "config-api-key"

    def test_debug_mode_enables_logging(self) -> None:
        """Test that debug mode enables debug logging."""
        config = CiviFlaskConfig(debug=True)

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            CiviFlask(config=config)  # No app, just test config processing


class TestCiviFlaskSettingsFromConfig:
    """Tests for loading settings from Flask app.config."""

    def test_loads_all_config_values(self) -> None:
        """Test that all CIVI_* config values are loaded."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-api-key"
        app.config["CIVI_SITE_KEY"] = "test-site-key"
        app.config["CIVI_TIMEOUT"] = 60
        app.config["CIVI_VERIFY_SSL"] = False
        app.config["CIVI_DEBUG"] = True
        app.config["CIVI_MAX_RETRIES"] = 5
        app.config["CIVI_AUTH_TYPE"] = "api_key"

        civi = CiviFlask(app)

        assert civi._settings.base_url == "https://example.org/civicrm/ajax/api4"
        assert civi._settings.api_key == "test-api-key"
        assert civi._settings.site_key == "test-site-key"
        assert civi._settings.timeout == 60
        assert civi._settings.verify_ssl is False
        assert civi._settings.debug is True
        assert civi._settings.max_retries == 5
        assert civi._settings.auth_type == "api_key"

    def test_string_boolean_config_values(self) -> None:
        """Test that string boolean config values are converted."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["CIVI_VERIFY_SSL"] = "false"
        app.config["CIVI_DEBUG"] = "true"

        civi = CiviFlask(app)

        assert civi._settings.verify_ssl is False
        assert civi._settings.debug is True

    def test_string_integer_config_values(self) -> None:
        """Test that string integer config values are converted."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["CIVI_TIMEOUT"] = "45"
        app.config["CIVI_MAX_RETRIES"] = "7"

        civi = CiviFlask(app)

        assert civi._settings.timeout == 45
        assert civi._settings.max_retries == 7

    def test_default_config_values(self) -> None:
        """Test that default values are used when config not set."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi = CiviFlask(app)

        assert civi._settings.timeout == 30
        assert civi._settings.verify_ssl is True
        assert civi._settings.debug is False
        assert civi._settings.max_retries == 3
        assert civi._settings.auth_type == "api_key"

    def test_jwt_auth_type_config(self) -> None:
        """Test configuration with JWT authentication."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_AUTH_TYPE"] = "jwt"
        app.config["CIVI_JWT_TOKEN"] = "test-jwt-token"

        civi = CiviFlask(app)

        assert civi._settings.auth_type == "jwt"
        assert civi._settings.jwt_token == "test-jwt-token"

    def test_basic_auth_type_config(self) -> None:
        """Test configuration with basic authentication."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_AUTH_TYPE"] = "basic"
        app.config["CIVI_USERNAME"] = "testuser"
        app.config["CIVI_PASSWORD"] = "testpass"

        civi = CiviFlask(app)

        assert civi._settings.auth_type == "basic"
        assert civi._settings.username == "testuser"
        assert civi._settings.password == "testpass"


# -----------------------------------------------------------------------------
# Client Management Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskGetClient:
    """Tests for CiviFlask.get_client() method."""

    def test_get_client_raises_when_not_initialized(self) -> None:
        """Test that get_client raises error when not initialized."""
        civi = CiviFlask()

        with pytest.raises(RuntimeError, match="CiviFlask not initialized"):
            civi.get_client()

    @respx.mock
    def test_get_client_returns_sync_client(self, respx_mock: respx.MockRouter) -> None:
        """Test that get_client returns a SyncCiviClient."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi = CiviFlask(app)
        client = civi.get_client()

        from civicrm_py.core.client import SyncCiviClient

        assert isinstance(client, SyncCiviClient)

    @respx.mock
    def test_thread_local_mode_returns_same_client_per_thread(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that thread-local mode reuses client in same thread."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=True)
        civi = CiviFlask(app, config=config)

        client1 = civi.get_client()
        client2 = civi.get_client()

        assert client1 is client2

    @respx.mock
    def test_thread_local_mode_different_clients_per_thread(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that thread-local mode creates different clients per thread."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=True)
        civi = CiviFlask(app, config=config)

        # Store actual client objects (not just IDs) to prevent GC
        clients: dict[str, Any] = {}
        lock = threading.Lock()
        barrier = threading.Barrier(3)

        def get_client_in_thread(name: str) -> None:
            client = civi.get_client()
            with lock:
                # Store the actual client object to keep it alive
                clients[name] = client
            # Wait for all threads to reach this point
            barrier.wait()

        threads = [
            threading.Thread(target=get_client_in_thread, args=(f"thread-{i}",), name=f"worker-{i}") for i in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread should have a different client instance
        # Compare actual objects, not memory addresses
        client_objs = list(clients.values())
        assert len(client_objs) == 3
        # Check that no two clients are the same object
        assert client_objs[0] is not client_objs[1]
        assert client_objs[1] is not client_objs[2]
        assert client_objs[0] is not client_objs[2]

    @respx.mock
    def test_shared_mode_returns_same_client_always(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that shared mode returns same client across calls."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=False)
        civi = CiviFlask(app, config=config)

        client1 = civi.get_client()
        client2 = civi.get_client()

        assert client1 is client2

    @respx.mock
    def test_shared_mode_same_client_across_threads(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that shared mode uses same client across threads."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=False)
        civi = CiviFlask(app, config=config)

        clients: dict[str, Any] = {}
        lock = threading.Lock()

        def get_client_in_thread(name: str) -> None:
            client = civi.get_client()
            with lock:
                clients[name] = id(client)

        threads = [threading.Thread(target=get_client_in_thread, args=(f"thread-{i}",)) for i in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same shared client
        client_ids = list(clients.values())
        assert len(set(client_ids)) == 1


# -----------------------------------------------------------------------------
# Request Context Integration Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskRequestContext:
    """Tests for Flask request context integration."""

    @respx.mock
    def test_client_attached_to_g_before_request(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that client is attached to g before each request."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        @app.route("/test")
        def test_view() -> dict[str, Any]:
            assert hasattr(g, "civi_client")
            assert g.civi_client is not None
            return {"client_type": type(g.civi_client).__name__}

        client: FlaskClient = app.test_client()
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json == {"client_type": "SyncCiviClient"}

    @respx.mock
    def test_get_civi_client_helper_in_request(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test get_civi_client() helper within request context."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        @app.route("/test")
        def test_view() -> dict[str, Any]:
            client = get_civi_client()
            return {"client_type": type(client).__name__}

        test_client: FlaskClient = app.test_client()
        response = test_client.get("/test")

        assert response.status_code == 200
        assert response.json == {"client_type": "SyncCiviClient"}

    @respx.mock
    def test_get_civi_client_raises_outside_request(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test get_civi_client() raises error outside request context."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        CiviFlask(app)

        # Outside of request context, g.civi_client doesn't exist
        with pytest.raises(RuntimeError, match="CiviCRM client not available"):
            with app.app_context():
                get_civi_client()

    @respx.mock
    def test_client_available_in_multiple_requests(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that client is available across multiple requests."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        client_ids: list[int] = []

        @app.route("/test")
        def test_view() -> dict[str, int]:
            client_id = id(g.civi_client)
            client_ids.append(client_id)
            return {"client_id": client_id}

        test_client: FlaskClient = app.test_client()

        # Make multiple requests
        for _ in range(3):
            response = test_client.get("/test")
            assert response.status_code == 200

        # In thread-local mode (default), same client should be reused
        assert len(set(client_ids)) == 1


class TestCiviFlaskMakeApiCalls:
    """Tests for making actual API calls through the extension."""

    @respx.mock
    def test_make_api_call_in_view(self, respx_mock: respx.MockRouter) -> None:
        """Test making an API call within a Flask view."""
        # Mock the API response
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 1, "display_name": "John Doe"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        @app.route("/contacts")
        def list_contacts() -> dict[str, Any]:
            client = get_civi_client()
            response = client.get("Contact", limit=10)
            return {"contacts": response.values, "count": response.count}

        test_client: FlaskClient = app.test_client()
        response = test_client.get("/contacts")

        assert response.status_code == 200
        data = response.json
        assert data["count"] == 1
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["display_name"] == "John Doe"

    @respx.mock
    def test_api_error_handling_in_view(self, respx_mock: respx.MockRouter) -> None:
        """Test handling API errors in a Flask view."""
        # Mock an API error response
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                401,
                json={
                    "error_code": "unauthorized",
                    "error_message": "Invalid API key",
                },
            ),
        )

        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "invalid-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        @app.route("/contacts")
        def list_contacts() -> tuple[dict[str, str], int]:
            client = get_civi_client()
            try:
                client.get("Contact", limit=10)
                return {"status": "ok"}, 200
            except Exception as e:
                return {"error": str(e)}, 500

        test_client: FlaskClient = app.test_client()
        response = test_client.get("/contacts")

        assert response.status_code == 500
        assert "error" in response.json


# -----------------------------------------------------------------------------
# Cleanup and Lifecycle Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskCleanup:
    """Tests for client cleanup and teardown."""

    def test_cleanup_closes_shared_client(self) -> None:
        """Test that _cleanup closes the shared client."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=False)
        civi = CiviFlask(app, config=config)

        # Create a mock client
        mock_client = MagicMock()
        civi._client = mock_client

        civi._cleanup()

        mock_client.close.assert_called_once()
        assert civi._client is None

    def test_cleanup_closes_thread_local_client(self) -> None:
        """Test that _cleanup closes thread-local client."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=True)
        civi = CiviFlask(app, config=config)

        # Create a mock client in thread-local storage
        mock_client = MagicMock()
        civi._local.client = mock_client

        civi._cleanup()

        mock_client.close.assert_called_once()
        assert getattr(civi._local, "client", None) is None

    def test_cleanup_handles_no_client_gracefully(self) -> None:
        """Test that _cleanup handles case when no client exists."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi = CiviFlask(app)

        # No client created yet
        assert civi._client is None

        # Should not raise
        civi._cleanup()

    def test_cleanup_handles_client_close_error(self) -> None:
        """Test that _cleanup handles errors during client close."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(use_thread_local=False)
        civi = CiviFlask(app, config=config)

        # Create a mock client that raises on close
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("Close error")
        civi._client = mock_client

        # Should not raise, just log the error
        civi._cleanup()

        assert civi._client is None


# -----------------------------------------------------------------------------
# Settings Property Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskSettingsProperty:
    """Tests for CiviFlask.settings property."""

    def test_settings_raises_when_not_initialized(self) -> None:
        """Test that settings property raises error when not initialized."""
        civi = CiviFlask()

        with pytest.raises(RuntimeError, match="CiviFlask not initialized"):
            _ = civi.settings

    def test_settings_returns_configured_settings(self) -> None:
        """Test that settings property returns configured settings."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi = CiviFlask(app)

        settings = civi.settings
        assert settings.base_url == "https://example.org/civicrm/ajax/api4"
        assert settings.api_key == "test-key"


# -----------------------------------------------------------------------------
# Repr Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskRepr:
    """Tests for CiviFlask string representation."""

    def test_repr_when_not_initialized(self) -> None:
        """Test __repr__ when extension is not initialized."""
        civi = CiviFlask()

        result = repr(civi)

        assert "CiviFlask" in result
        assert "not initialized" in result

    def test_repr_when_initialized(self) -> None:
        """Test __repr__ when extension is initialized."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        civi = CiviFlask(app)

        result = repr(civi)

        assert "CiviFlask" in result
        assert "https://example.org/civicrm/ajax/api4" in result


# -----------------------------------------------------------------------------
# CLI Registration Tests
# -----------------------------------------------------------------------------


class TestCiviFlaskCLIRegistration:
    """Tests for Flask CLI command registration."""

    def test_cli_commands_registered_by_default(self) -> None:
        """Test that CLI commands are registered by default."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        CiviFlask(app)

        # Check that commands are registered
        command_names = [cmd.name for cmd in app.cli.commands.values()]
        assert "civi-check" in command_names
        assert "civi-shell" in command_names

    def test_cli_commands_not_registered_when_disabled(self) -> None:
        """Test that CLI commands are not registered when disabled."""
        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"

        config = CiviFlaskConfig(register_cli=False)
        CiviFlask(app, config=config)

        # Check that commands are NOT registered
        command_names = [cmd.name for cmd in app.cli.commands.values()]
        assert "civi-check" not in command_names
        assert "civi-shell" not in command_names


# -----------------------------------------------------------------------------
# Integration Tests with Test Client
# -----------------------------------------------------------------------------


class TestCiviFlaskIntegration:
    """Full integration tests using Flask test client."""

    @respx.mock
    def test_full_crud_workflow(self, respx_mock: respx.MockRouter) -> None:
        """Test a complete CRUD workflow through the extension."""
        # Mock create response
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/create").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 100, "display_name": "New Contact"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        # Mock get response
        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 100, "display_name": "New Contact"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        @app.route("/create-contact", methods=["POST"])
        def create_contact() -> tuple[dict[str, Any], int]:
            client = get_civi_client()
            response = client.create("Contact", {"display_name": "New Contact"})
            return {"id": response.values[0]["id"]}, 201

        @app.route("/get-contact/<int:contact_id>")
        def get_contact(contact_id: int) -> dict[str, Any]:
            client = get_civi_client()
            response = client.get("Contact", where=[["id", "=", contact_id]])
            if response.values:
                return response.values[0]
            return {"error": "Not found"}, 404  # type: ignore[return-value]

        test_client: FlaskClient = app.test_client()

        # Create a contact
        create_response = test_client.post("/create-contact")
        assert create_response.status_code == 201
        assert create_response.json["id"] == 100

        # Get the contact
        get_response = test_client.get("/get-contact/100")
        assert get_response.status_code == 200
        assert get_response.json["display_name"] == "New Contact"

    @respx.mock
    def test_multiple_extensions_different_apps(
        self,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test that extensions can be used with multiple apps."""
        app1 = Flask("app1")
        app1.config["CIVI_BASE_URL"] = "https://site1.org/civicrm/ajax/api4"
        app1.config["CIVI_API_KEY"] = "key1"

        app2 = Flask("app2")
        app2.config["CIVI_BASE_URL"] = "https://site2.org/civicrm/ajax/api4"
        app2.config["CIVI_API_KEY"] = "key2"

        civi1 = CiviFlask(app1)
        civi2 = CiviFlask(app2)

        assert civi1.settings.base_url == "https://site1.org/civicrm/ajax/api4"
        assert civi2.settings.base_url == "https://site2.org/civicrm/ajax/api4"
        assert civi1._settings is not civi2._settings

    @respx.mock
    def test_extension_with_blueprints(self, respx_mock: respx.MockRouter) -> None:
        """Test extension works correctly with Flask blueprints."""
        from flask import Blueprint

        respx_mock.post("https://example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 1, "display_name": "Test"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        app = Flask(__name__)
        app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
        app.config["CIVI_API_KEY"] = "test-key"
        app.config["TESTING"] = True

        CiviFlask(app)

        # Create a blueprint
        bp = Blueprint("crm", __name__, url_prefix="/crm")

        @bp.route("/contacts")
        def contacts() -> dict[str, Any]:
            client = get_civi_client()
            response = client.get("Contact", limit=10)
            return {"contacts": response.values}

        app.register_blueprint(bp)

        test_client: FlaskClient = app.test_client()
        response = test_client.get("/crm/contacts")

        assert response.status_code == 200
        assert len(response.json["contacts"]) == 1
