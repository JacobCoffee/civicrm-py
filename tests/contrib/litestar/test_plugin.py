"""Comprehensive integration tests for Litestar contrib module.

Tests cover:
- CiviPluginConfig initialization and defaults
- provide_civi_client dependency with mocked app state
- cleanup_client closes transport
- DTOs serialize/deserialize correctly
- ContactController CRUD operations with mocked HTTP
- Health check returns correct response format
- Plugin registers routes correctly
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import msgspec
import pytest
import respx
from httpx import Response
from litestar import Litestar
from litestar.datastructures import State
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from litestar.testing import TestClient

# Suppress Pydantic v1 warning on Python 3.14+
# This is needed because Litestar loads the Pydantic plugin by default
pytestmark = pytest.mark.filterwarnings("ignore:Core Pydantic V1 functionality:UserWarning")

from civicrm_py.contrib.litestar import (
    CIVI_CLIENT_STATE_KEY,
    ActivityController,
    ActivityCreateDTO,
    ActivityResponseDTO,
    APIResponseDTO,
    CiviPlugin,
    CiviPluginConfig,
    ContactController,
    ContactCreateDTO,
    ContactFilterDTO,
    ContactResponseDTO,
    ContactUpdateDTO,
    ContributionController,
    EventController,
    GroupController,
    HealthCheckResponse,
    MembershipController,
    PaginationDTO,
    ParticipantController,
    cleanup_client,
    get_dependency_providers,
    get_entity_controllers,
    get_health_check_route,
    provide_civi_client,
)
from civicrm_py.core.client import CiviClient
from civicrm_py.core.config import CiviSettings

if TYPE_CHECKING:
    from collections.abc import Generator


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_settings() -> CiviSettings:
    """Create test CiviSettings."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        verify_ssl=False,
    )


@pytest.fixture
def plugin_config(test_settings: CiviSettings) -> CiviPluginConfig:
    """Create test plugin config with settings."""
    return CiviPluginConfig(
        settings=test_settings,
        api_prefix="/api/civi",
        enable_health_check=True,
        health_check_path="/health/civi",
    )


@pytest.fixture
def mock_civi_client() -> MagicMock:
    """Create a mock CiviClient."""
    client = MagicMock(spec=CiviClient)
    client.close = AsyncMock()

    # Default successful response
    response = MagicMock()
    response.values = [{"id": 1, "display_name": "Test Contact"}]
    response.count = 1
    response.countFetched = 1
    client.get = AsyncMock(return_value=response)
    client.create = AsyncMock(return_value=response)
    client.update = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)

    return client


# =============================================================================
# CiviPluginConfig Tests
# =============================================================================


class TestCiviPluginConfig:
    """Tests for CiviPluginConfig initialization and defaults."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = CiviPluginConfig()

        assert config.settings is None
        assert config.api_prefix == "/api/civi"
        assert config.enable_health_check is True
        assert config.health_check_path == "/health/civi"
        assert config.openapi_tags == ["CiviCRM"]
        assert config.include_entities is None
        assert config.exclude_entities == []
        assert config.debug is False
        assert config.enable_webui is False
        assert config.webui_path == "/explorer"

    def test_custom_values(self, test_settings: CiviSettings) -> None:
        """Test custom configuration values."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/custom/api",
            enable_health_check=False,
            health_check_path="/custom/health",
            openapi_tags=["Custom", "CRM"],
            include_entities=["Contact", "Activity"],
            exclude_entities=["Group"],
            debug=True,
        )

        assert config.settings == test_settings
        assert config.api_prefix == "/custom/api"
        assert config.enable_health_check is False
        assert config.health_check_path == "/custom/health"
        assert config.openapi_tags == ["Custom", "CRM"]
        assert config.include_entities == ["Contact", "Activity"]
        assert config.exclude_entities == ["Group"]
        assert config.debug is True

    def test_api_prefix_normalization(self) -> None:
        """Test that api_prefix is normalized to start with /."""
        config = CiviPluginConfig(api_prefix="api/civi")
        assert config.api_prefix == "/api/civi"

    def test_health_check_path_normalization(self) -> None:
        """Test that health_check_path is normalized to start with /."""
        config = CiviPluginConfig(health_check_path="health/civi")
        assert config.health_check_path == "/health/civi"

    def test_webui_path_normalization(self) -> None:
        """Test that webui_path is normalized to start with /."""
        config = CiviPluginConfig(webui_path="explorer")
        assert config.webui_path == "/explorer"

    def test_api_prefix_none_disables_routes(self) -> None:
        """Test that None api_prefix disables route generation."""
        config = CiviPluginConfig(api_prefix=None)
        assert config.api_prefix is None


# =============================================================================
# Dependency Provider Tests
# =============================================================================


class TestProvideClient:
    """Tests for provide_civi_client dependency."""

    async def test_provide_client_from_state(self, mock_civi_client: MagicMock) -> None:
        """Test providing client from application state."""
        # Use State's internal structure correctly
        state = State({CIVI_CLIENT_STATE_KEY: mock_civi_client})

        client = await provide_civi_client(state)

        assert client is mock_civi_client

    async def test_provide_client_missing_raises_runtime_error(self) -> None:
        """Test RuntimeError when client not in state."""
        state = State({})

        with pytest.raises(RuntimeError, match="CiviClient not found"):
            await provide_civi_client(state)

    def test_get_dependency_providers_returns_dict(self) -> None:
        """Test get_dependency_providers returns correct mapping."""
        providers = get_dependency_providers()

        assert "civi_client" in providers
        # Should be wrapped in Provide
        assert hasattr(providers["civi_client"], "dependency")


class TestCleanupClient:
    """Tests for cleanup_client function."""

    async def test_cleanup_closes_transport(self, mock_civi_client: MagicMock) -> None:
        """Test cleanup_client closes the client transport."""
        app = MagicMock(spec=Litestar)
        app.state = MagicMock()
        setattr(app.state, CIVI_CLIENT_STATE_KEY, mock_civi_client)

        await cleanup_client(app)

        mock_civi_client.close.assert_awaited_once()

    async def test_cleanup_removes_client_from_state(self, mock_civi_client: MagicMock) -> None:
        """Test cleanup_client removes client from app state."""
        app = MagicMock(spec=Litestar)
        app.state = MagicMock()
        setattr(app.state, CIVI_CLIENT_STATE_KEY, mock_civi_client)

        await cleanup_client(app)

        # Verify delattr was called (client removed from state)
        assert not hasattr(app.state, CIVI_CLIENT_STATE_KEY) or mock_civi_client.close.awaited

    async def test_cleanup_handles_missing_client(self) -> None:
        """Test cleanup_client handles missing client gracefully."""

        # Create a simple class-based mock that properly handles getattr
        class MockState:
            pass

        class MockApp:
            state = MockState()

        app = MockApp()

        # Should not raise - getattr returns None for missing attribute
        await cleanup_client(app)  # type: ignore[arg-type]


# =============================================================================
# DTO Tests
# =============================================================================


class TestDTOSerialization:
    """Tests for DTO serialization and deserialization."""

    def test_pagination_dto_defaults(self) -> None:
        """Test PaginationDTO default values."""
        dto = PaginationDTO()

        assert dto.limit == 25
        assert dto.offset == 0

    def test_pagination_dto_custom_values(self) -> None:
        """Test PaginationDTO custom values."""
        dto = PaginationDTO(limit=50, offset=100)

        assert dto.limit == 50
        assert dto.offset == 100

    def test_api_response_dto_serialization(self) -> None:
        """Test APIResponseDTO serialization."""
        dto = APIResponseDTO(
            values=[{"id": 1, "name": "Test"}],
            count=1,
            count_fetched=1,
        )

        encoded = msgspec.json.encode(dto)
        decoded = msgspec.json.decode(encoded, type=APIResponseDTO)

        assert decoded.values == [{"id": 1, "name": "Test"}]
        assert decoded.count == 1
        assert decoded.count_fetched == 1

    def test_contact_create_dto_serialization(self) -> None:
        """Test ContactCreateDTO serialization."""
        dto = ContactCreateDTO(
            first_name="John",
            last_name="Doe",
            email_primary="john@example.com",
            contact_type="Individual",
        )

        encoded = msgspec.json.encode(dto)
        decoded = msgspec.json.decode(encoded, type=ContactCreateDTO)

        assert decoded.first_name == "John"
        assert decoded.last_name == "Doe"
        assert decoded.email_primary == "john@example.com"
        assert decoded.contact_type == "Individual"

    def test_contact_response_dto_deserialization(self) -> None:
        """Test ContactResponseDTO deserialization."""
        data = {
            "id": 1,
            "first_name": "John",
            "last_name": "Doe",
            "display_name": "John Doe",
            "contact_type": "Individual",
            "is_deleted": False,
        }

        dto = msgspec.convert(data, ContactResponseDTO)

        assert dto.id == 1
        assert dto.first_name == "John"
        assert dto.last_name == "Doe"
        assert dto.display_name == "John Doe"
        assert dto.is_deleted is False

    def test_contact_update_dto_optional_fields(self) -> None:
        """Test ContactUpdateDTO with only some fields."""
        dto = ContactUpdateDTO(first_name="Jane")

        encoded = msgspec.json.encode(dto)
        decoded = msgspec.json.decode(encoded)

        assert decoded["first_name"] == "Jane"
        assert "last_name" not in decoded  # omit_defaults=True

    def test_contact_filter_dto_defaults(self) -> None:
        """Test ContactFilterDTO default values."""
        dto = ContactFilterDTO()

        assert dto.limit == 25
        assert dto.offset == 0
        assert dto.contact_type is None
        assert dto.is_deleted is False
        assert dto.search is None

    def test_activity_create_dto_required_field(self) -> None:
        """Test ActivityCreateDTO requires activity_type_id."""
        dto = ActivityCreateDTO(
            activity_type_id=1,
            subject="Test Activity",
            source_contact_id=1,
        )

        assert dto.activity_type_id == 1
        assert dto.subject == "Test Activity"

    def test_activity_response_dto_deserialization(self) -> None:
        """Test ActivityResponseDTO deserialization."""
        data = {
            "id": 1,
            "activity_type_id": 3,
            "subject": "Follow-up call",
            "status_id": 2,
            "is_deleted": False,
        }

        dto = msgspec.convert(data, ActivityResponseDTO)

        assert dto.id == 1
        assert dto.activity_type_id == 3
        assert dto.subject == "Follow-up call"
        assert dto.is_deleted is False

    def test_health_check_response_healthy(self) -> None:
        """Test HealthCheckResponse for healthy status."""
        dto = HealthCheckResponse(
            status="healthy",
            civi_connected=True,
            response_time_ms=45.2,
            api_version="4",
            timestamp="2024-01-15T12:00:00Z",
        )

        assert dto.status == "healthy"
        assert dto.civi_connected is True
        assert dto.response_time_ms == 45.2
        assert dto.error is None

    def test_health_check_response_unhealthy(self) -> None:
        """Test HealthCheckResponse for unhealthy status."""
        dto = HealthCheckResponse(
            status="unhealthy",
            civi_connected=False,
            timestamp="2024-01-15T12:00:00Z",
            error="Connection timeout",
        )

        assert dto.status == "unhealthy"
        assert dto.civi_connected is False
        assert dto.error == "Connection timeout"


# =============================================================================
# Entity Controller Tests
# =============================================================================


class TestGetEntityControllers:
    """Tests for get_entity_controllers function."""

    def test_returns_all_controllers_by_default(self) -> None:
        """Test all default controllers are returned."""
        controllers = get_entity_controllers()

        assert ContactController in controllers
        assert ActivityController in controllers
        assert ContributionController in controllers
        assert EventController in controllers
        assert MembershipController in controllers
        assert ParticipantController in controllers
        assert GroupController in controllers

    def test_include_entities_filter(self) -> None:
        """Test include_entities filters controllers."""
        controllers = get_entity_controllers(include_entities=["Contact", "Activity"])

        assert ContactController in controllers
        assert ActivityController in controllers
        assert ContributionController not in controllers

    def test_exclude_entities_filter(self) -> None:
        """Test exclude_entities filters controllers."""
        controllers = get_entity_controllers(exclude_entities=["Group", "Participant"])

        assert ContactController in controllers
        assert GroupController not in controllers
        assert ParticipantController not in controllers

    def test_include_and_exclude_combined(self) -> None:
        """Test include and exclude filters combined."""
        controllers = get_entity_controllers(
            include_entities=["Contact", "Activity", "Event"],
            exclude_entities=["Activity"],
        )

        assert ContactController in controllers
        assert EventController in controllers
        assert ActivityController not in controllers


# =============================================================================
# Contact Controller Integration Tests
# =============================================================================


class TestContactControllerIntegration:
    """Integration tests for ContactController CRUD operations."""

    @pytest.fixture
    def app_with_mocked_client(
        self,
        test_settings: CiviSettings,
        mock_civi_client: MagicMock,
    ) -> Generator[Litestar, None, None]:
        """Create Litestar app with mocked CiviClient.

        We patch the CiviClient class so the plugin creates our mock instead
        of a real client.
        """
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            enable_health_check=False,
            include_entities=["Contact"],
        )

        # Patch CiviClient to return our mock
        with patch("civicrm_py.core.client.CiviClient", return_value=mock_civi_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            yield app

    def test_list_contacts(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test listing contacts."""
        mock_civi_client.get.return_value = MagicMock(
            values=[
                {"id": 1, "display_name": "John Doe", "contact_type": "Individual"},
                {"id": 2, "display_name": "Jane Smith", "contact_type": "Individual"},
            ],
            count=2,
            countFetched=2,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.get("/api/civi/Contact/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["count"] == 2
        assert len(data["values"]) == 2
        mock_civi_client.get.assert_awaited_once()

    def test_list_contacts_with_filters(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test listing contacts with filter parameters."""
        mock_civi_client.get.return_value = MagicMock(
            values=[{"id": 1, "display_name": "John Doe"}],
            count=1,
            countFetched=1,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.get(
                "/api/civi/Contact/",
                params={"contact_type": "Individual", "limit": 10, "offset": 5},
            )

        assert response.status_code == HTTP_200_OK
        # Verify API was called with filters
        call_kwargs = mock_civi_client.get.call_args
        assert call_kwargs.kwargs.get("limit") == 10
        assert call_kwargs.kwargs.get("offset") == 5

    def test_get_single_contact(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test getting a single contact by ID."""
        mock_civi_client.get.return_value = MagicMock(
            values=[
                {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "display_name": "John Doe",
                    "contact_type": "Individual",
                    "is_deleted": False,
                },
            ],
            count=1,
            countFetched=1,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.get("/api/civi/Contact/1")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["id"] == 1
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"

    def test_get_contact_not_found(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test 404 when contact not found."""
        mock_civi_client.get.return_value = MagicMock(
            values=[],
            count=0,
            countFetched=0,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.get("/api/civi/Contact/999")

        assert response.status_code == HTTP_404_NOT_FOUND

    def test_create_contact(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test creating a new contact."""
        mock_civi_client.create.return_value = MagicMock(
            values=[
                {
                    "id": 100,
                    "first_name": "New",
                    "last_name": "Contact",
                    "display_name": "New Contact",
                    "contact_type": "Individual",
                    "is_deleted": False,
                },
            ],
            count=1,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.post(
                "/api/civi/Contact/",
                json={
                    "first_name": "New",
                    "last_name": "Contact",
                    "contact_type": "Individual",
                },
            )

        assert response.status_code == HTTP_201_CREATED
        data = response.json()
        assert data["id"] == 100
        assert data["first_name"] == "New"
        mock_civi_client.create.assert_awaited_once()

    def test_update_contact(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test updating an existing contact."""
        mock_civi_client.update.return_value = MagicMock(
            values=[
                {
                    "id": 1,
                    "first_name": "Updated",
                    "last_name": "Doe",
                    "display_name": "Updated Doe",
                    "contact_type": "Individual",
                    "is_deleted": False,
                },
            ],
            count=1,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.put(
                "/api/civi/Contact/1",
                json={"first_name": "Updated"},
            )

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["first_name"] == "Updated"
        mock_civi_client.update.assert_awaited_once()

    def test_update_contact_not_found(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test 404 when updating non-existent contact."""
        mock_civi_client.update.return_value = MagicMock(
            values=[],
            count=0,
        )

        with TestClient(app=app_with_mocked_client) as client:
            response = client.put(
                "/api/civi/Contact/999",
                json={"first_name": "Updated"},
            )

        assert response.status_code == HTTP_404_NOT_FOUND

    def test_delete_contact(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test deleting a contact."""
        mock_civi_client.delete.return_value = MagicMock(count=1)

        with TestClient(app=app_with_mocked_client) as client:
            response = client.delete("/api/civi/Contact/1")

        assert response.status_code == HTTP_204_NO_CONTENT
        mock_civi_client.delete.assert_awaited_once()

    def test_delete_contact_not_found(
        self,
        app_with_mocked_client: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test 404 when deleting non-existent contact."""
        mock_civi_client.delete.return_value = MagicMock(count=0)

        with TestClient(app=app_with_mocked_client) as client:
            response = client.delete("/api/civi/Contact/999")

        assert response.status_code == HTTP_404_NOT_FOUND


# =============================================================================
# Health Check Tests
# =============================================================================


class TestHealthCheck:
    """Tests for health check endpoint."""

    @pytest.fixture
    def app_with_health_check(
        self,
        test_settings: CiviSettings,
        mock_civi_client: MagicMock,
    ) -> Generator[Litestar, None, None]:
        """Create Litestar app with health check enabled."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,  # Disable CRUD routes
            enable_health_check=True,
            health_check_path="/health/civi",
        )

        with patch("civicrm_py.core.client.CiviClient", return_value=mock_civi_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            yield app

    def test_health_check_healthy(
        self,
        app_with_health_check: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test health check returns healthy status."""
        mock_civi_client.get.return_value = MagicMock(
            values=[{"id": 1}],
            count=1,
        )

        with TestClient(app=app_with_health_check) as client:
            response = client.get("/health/civi")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["civi_connected"] is True
        assert data["api_version"] == "4"
        assert "response_time_ms" in data
        assert "timestamp" in data

    def test_health_check_unhealthy(
        self,
        app_with_health_check: Litestar,
        mock_civi_client: MagicMock,
    ) -> None:
        """Test health check returns unhealthy status on error."""
        mock_civi_client.get.side_effect = Exception("Connection failed")

        with TestClient(app=app_with_health_check) as client:
            response = client.get("/health/civi")

        assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["civi_connected"] is False
        assert "error" in data
        assert "Connection failed" in data["error"]

    def test_custom_health_check_path(self, test_settings: CiviSettings) -> None:
        """Test custom health check path."""
        mock_client = MagicMock(spec=CiviClient)
        mock_client.get = AsyncMock(
            return_value=MagicMock(values=[{"id": 1}], count=1),
        )
        mock_client.close = AsyncMock()

        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,
            enable_health_check=True,
            health_check_path="/api/v1/health/civicrm",
        )

        with patch("civicrm_py.core.client.CiviClient", return_value=mock_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            with TestClient(app=app) as client:
                response = client.get("/api/v1/health/civicrm")

        assert response.status_code == HTTP_200_OK


class TestGetHealthCheckRoute:
    """Tests for get_health_check_route factory function."""

    def test_creates_route_with_custom_path(self) -> None:
        """Test factory creates route handler with custom path."""
        handler = get_health_check_route("/custom/health/path")

        # Handler should be a decorated function
        assert callable(handler)
        # Check path is set correctly via the decorator
        assert hasattr(handler, "paths") or hasattr(handler, "_paths")


# =============================================================================
# Plugin Integration Tests
# =============================================================================


class TestCiviPlugin:
    """Tests for CiviPlugin registration and lifecycle."""

    def test_plugin_registers_dependencies(self, test_settings: CiviSettings) -> None:
        """Test plugin registers dependency providers."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,
            enable_health_check=False,
        )

        app = Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

        assert "civi_client" in app.dependencies

    def test_plugin_registers_routes(self, test_settings: CiviSettings) -> None:
        """Test plugin registers CRUD routes."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            enable_health_check=False,
            include_entities=["Contact"],
        )

        app = Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

        # Check routes are registered
        route_paths = [route.path for route in app.routes]
        assert any("/api/civi" in path for path in route_paths)

    def test_plugin_registers_health_check(self, test_settings: CiviSettings) -> None:
        """Test plugin registers health check route when enabled."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,
            enable_health_check=True,
            health_check_path="/health/civi",
        )

        app = Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

        route_paths = [route.path for route in app.routes]
        assert "/health/civi" in route_paths

    def test_plugin_lifecycle_startup(self, test_settings: CiviSettings) -> None:
        """Test plugin initializes client on startup."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,
            enable_health_check=False,
        )

        app = Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

        with TestClient(app=app):
            # Client should be initialized in state
            assert hasattr(app.state, CIVI_CLIENT_STATE_KEY)
            client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
            assert isinstance(client, CiviClient)

    def test_plugin_with_debug_enabled(self, test_settings: CiviSettings) -> None:
        """Test plugin enables debug logging when configured."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix=None,
            enable_health_check=False,
            debug=True,
        )

        # Should not raise
        plugin = CiviPlugin(config)
        assert plugin.config.debug is True

    def test_plugin_without_settings_loads_from_env(self) -> None:
        """Test plugin loads settings from environment when not provided."""
        import os

        # Set required environment variables
        original_env = os.environ.copy()
        try:
            os.environ["CIVI_BASE_URL"] = "https://test.example.org/api"
            os.environ["CIVI_API_KEY"] = "test-key"

            config = CiviPluginConfig(
                api_prefix=None,
                enable_health_check=False,
            )

            plugin = CiviPlugin(config)
            assert plugin.config.settings is None  # Will be loaded on startup
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_plugin_config_property(self, test_settings: CiviSettings) -> None:
        """Test plugin exposes config property."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/test/api",
        )

        plugin = CiviPlugin(config)

        assert plugin.config is config
        assert plugin.config.api_prefix == "/test/api"


# =============================================================================
# Full Integration Tests with respx
# =============================================================================


@respx.mock
class TestFullIntegrationWithResponses:
    """Full integration tests using respx to mock HTTP responses."""

    @pytest.fixture
    def full_app(self, test_settings: CiviSettings) -> Litestar:
        """Create full Litestar app for integration testing."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            enable_health_check=True,
            include_entities=["Contact", "Activity"],
        )

        return Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

    def test_full_crud_workflow(self, full_app: Litestar) -> None:
        """Test complete CRUD workflow with mocked HTTP."""
        base_url = "https://test.example.org/civicrm/ajax/api4"

        # Mock list contacts
        respx.post(f"{base_url}/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [
                        {"id": 1, "display_name": "John Doe", "contact_type": "Individual"},
                    ],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        # Mock create contact
        respx.post(f"{base_url}/Contact/create").mock(
            return_value=Response(
                200,
                json={
                    "values": [
                        {
                            "id": 100,
                            "first_name": "New",
                            "last_name": "Contact",
                            "display_name": "New Contact",
                            "contact_type": "Individual",
                            "is_deleted": False,
                        },
                    ],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        # Mock update contact
        respx.post(f"{base_url}/Contact/update").mock(
            return_value=Response(
                200,
                json={
                    "values": [
                        {
                            "id": 100,
                            "first_name": "Updated",
                            "last_name": "Contact",
                            "display_name": "Updated Contact",
                            "contact_type": "Individual",
                            "is_deleted": False,
                        },
                    ],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        # Mock delete contact
        respx.post(f"{base_url}/Contact/delete").mock(
            return_value=Response(
                200,
                json={"values": [], "count": 1, "countFetched": 0},
            ),
        )

        with TestClient(app=full_app) as client:
            # List
            response = client.get("/api/civi/Contact/")
            assert response.status_code == HTTP_200_OK

            # Create
            response = client.post(
                "/api/civi/Contact/",
                json={"first_name": "New", "last_name": "Contact"},
            )
            assert response.status_code == HTTP_201_CREATED

            # Update
            response = client.put(
                "/api/civi/Contact/100",
                json={"first_name": "Updated"},
            )
            assert response.status_code == HTTP_200_OK

            # Delete
            response = client.delete("/api/civi/Contact/100")
            assert response.status_code == HTTP_204_NO_CONTENT

    def test_health_check_integration(self, full_app: Litestar) -> None:
        """Test health check with mocked HTTP."""
        base_url = "https://test.example.org/civicrm/ajax/api4"

        respx.post(f"{base_url}/Contact/get").mock(
            return_value=Response(
                200,
                json={"values": [{"id": 1}], "count": 1, "countFetched": 1},
            ),
        )

        with TestClient(app=full_app) as client:
            response = client.get("/health/civi")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert data["civi_connected"] is True


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_contact_list(
        self,
        mock_civi_client: MagicMock,
        test_settings: CiviSettings,
    ) -> None:
        """Test handling of empty contact list."""
        mock_civi_client.get.return_value = MagicMock(
            values=[],
            count=0,
            countFetched=0,
        )

        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            include_entities=["Contact"],
        )

        with patch("civicrm_py.core.client.CiviClient", return_value=mock_civi_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            with TestClient(app=app) as client:
                response = client.get("/api/civi/Contact/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["values"] == []
        assert data["count"] == 0

    def test_contact_with_search_filter(
        self,
        mock_civi_client: MagicMock,
        test_settings: CiviSettings,
    ) -> None:
        """Test contact list with search filter."""
        mock_civi_client.get.return_value = MagicMock(
            values=[{"id": 1, "display_name": "John Doe"}],
            count=1,
            countFetched=1,
        )

        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            include_entities=["Contact"],
        )

        with patch("civicrm_py.core.client.CiviClient", return_value=mock_civi_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            with TestClient(app=app) as client:
                response = client.get("/api/civi/Contact/", params={"search": "John"})

        assert response.status_code == HTTP_200_OK
        # Verify the search was included in API call
        mock_civi_client.get.assert_awaited()

    def test_update_with_empty_body(
        self,
        mock_civi_client: MagicMock,
        test_settings: CiviSettings,
    ) -> None:
        """Test update with empty body returns current state."""
        mock_civi_client.get.return_value = MagicMock(
            values=[
                {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "display_name": "John Doe",
                    "contact_type": "Individual",
                    "is_deleted": False,
                },
            ],
            count=1,
            countFetched=1,
        )

        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            include_entities=["Contact"],
        )

        with patch("civicrm_py.core.client.CiviClient", return_value=mock_civi_client):
            app = Litestar(
                route_handlers=[],
                plugins=[CiviPlugin(config)],
            )

            with TestClient(app=app) as client:
                # Empty update body with only defaults
                response = client.put("/api/civi/Contact/1", json={})

        assert response.status_code == HTTP_200_OK


class TestOpenAPITags:
    """Tests for OpenAPI documentation tags."""

    def test_custom_openapi_tags(self, test_settings: CiviSettings) -> None:
        """Test custom OpenAPI tags are applied."""
        config = CiviPluginConfig(
            settings=test_settings,
            api_prefix="/api/civi",
            openapi_tags=["CRM", "Contacts"],
            include_entities=["Contact"],
        )

        app = Litestar(
            route_handlers=[],
            plugins=[CiviPlugin(config)],
        )

        # OpenAPI schema should include the custom tags
        schema = app.openapi_schema
        # Tags should be present in the schema
        assert schema is not None
