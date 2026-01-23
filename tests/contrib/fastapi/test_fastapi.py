"""Tests for FastAPI integration module.

Comprehensive tests for:
- CiviFastAPIConfig configuration
- Lifespan management (civi_lifespan, create_civi_lifespan)
- Dependency injection (get_civi_client, CiviClientDep)
- Pydantic models (Contact, Activity, Contribution, Event, Membership)
- Health check endpoint
- Route factories (create_contact_router, create_entity_router, create_civi_router)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from civi_py.contrib.fastapi import (
    CIVI_CLIENT_STATE_KEY,
    DEFAULT_ENTITIES,
    ActivityCreate,
    ActivityResponse,
    APIResponse,
    CiviFastAPIConfig,
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    ContributionCreate,
    ContributionResponse,
    EventCreate,
    EventResponse,
    HealthCheckResponse,
    MembershipCreate,
    MembershipResponse,
    PaginationParams,
    civi_lifespan,
    create_civi_lifespan,
    create_civi_router,
    create_contact_router,
    create_entity_router,
    create_health_check_router,
    get_civi_client,
)
from civi_py.core.client import CiviClient
from civi_py.core.config import CiviSettings


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
def fastapi_config(test_settings: CiviSettings) -> CiviFastAPIConfig:
    """Create FastAPI config with test settings."""
    return CiviFastAPIConfig(
        settings=test_settings,
        api_prefix="/api/civi",
        enable_health_check=True,
        health_check_path="/health/civi",
        debug=False,
    )


@pytest.fixture
def mock_civi_client(test_settings: CiviSettings) -> CiviClient:
    """Create a mock CiviClient."""
    return CiviClient(settings=test_settings)


class TestCiviFastAPIConfig:
    """Tests for CiviFastAPIConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = CiviFastAPIConfig()

        assert config.settings is None
        assert config.api_prefix == "/api/civi"
        assert config.enable_health_check is True
        assert config.health_check_path == "/health/civi"
        assert config.openapi_tags == ["CiviCRM"]
        assert config.include_entities is None
        assert config.exclude_entities == []
        assert config.debug is False

    def test_custom_values(self, test_settings: CiviSettings) -> None:
        """Test configuration with custom values."""
        config = CiviFastAPIConfig(
            settings=test_settings,
            api_prefix="/custom/api",
            enable_health_check=False,
            health_check_path="/custom/health",
            openapi_tags=["Custom", "Tags"],
            include_entities=["Contact", "Activity"],
            exclude_entities=["Event"],
            debug=True,
        )

        assert config.settings is test_settings
        assert config.api_prefix == "/custom/api"
        assert config.enable_health_check is False
        assert config.health_check_path == "/custom/health"
        assert config.openapi_tags == ["Custom", "Tags"]
        assert config.include_entities == ["Contact", "Activity"]
        assert config.exclude_entities == ["Event"]
        assert config.debug is True

    def test_api_prefix_auto_prepends_slash(self) -> None:
        """Test api_prefix automatically prepends slash."""
        config = CiviFastAPIConfig(api_prefix="api/civi")
        assert config.api_prefix == "/api/civi"

    def test_api_prefix_none_allowed(self) -> None:
        """Test api_prefix can be None to disable routes."""
        config = CiviFastAPIConfig(api_prefix=None)
        assert config.api_prefix is None

    def test_health_check_path_auto_prepends_slash(self) -> None:
        """Test health_check_path automatically prepends slash."""
        config = CiviFastAPIConfig(health_check_path="health/check")
        assert config.health_check_path == "/health/check"

    def test_openapi_tags_default_factory(self) -> None:
        """Test openapi_tags uses factory to create new list."""
        config1 = CiviFastAPIConfig()
        config2 = CiviFastAPIConfig()

        # Should be equal but not same object
        assert config1.openapi_tags == config2.openapi_tags
        assert config1.openapi_tags is not config2.openapi_tags

    def test_exclude_entities_default_factory(self) -> None:
        """Test exclude_entities uses factory to create new list."""
        config1 = CiviFastAPIConfig()
        config2 = CiviFastAPIConfig()

        config1.exclude_entities.append("Contact")

        # Should not affect other instance
        assert "Contact" not in config2.exclude_entities


class TestPaginationParams:
    """Tests for PaginationParams model."""

    def test_defaults(self) -> None:
        """Test default pagination values."""
        params = PaginationParams()
        assert params.limit == 25
        assert params.offset == 0

    def test_custom_values(self) -> None:
        """Test custom pagination values."""
        params = PaginationParams(limit=50, offset=100)
        assert params.limit == 50
        assert params.offset == 100

    def test_limit_validation_min(self) -> None:
        """Test limit must be at least 1."""
        with pytest.raises(ValueError):
            PaginationParams(limit=0)

    def test_limit_validation_max(self) -> None:
        """Test limit must be at most 100."""
        with pytest.raises(ValueError):
            PaginationParams(limit=101)

    def test_offset_validation_min(self) -> None:
        """Test offset must be non-negative."""
        with pytest.raises(ValueError):
            PaginationParams(offset=-1)


class TestAPIResponse:
    """Tests for APIResponse model."""

    def test_serialization(self) -> None:
        """Test APIResponse serialization."""
        response = APIResponse(
            values=[{"id": 1, "name": "Test"}],
            count=1,
            count_fetched=1,
        )

        data = response.model_dump()
        assert data["values"] == [{"id": 1, "name": "Test"}]
        assert data["count"] == 1
        assert data["count_fetched"] == 1

    def test_extra_fields_allowed(self) -> None:
        """Test extra fields are allowed."""
        response = APIResponse(
            values=[],
            count=0,
            count_fetched=0,
            custom_field="value",
        )
        assert response.model_extra == {"custom_field": "value"}


class TestHealthCheckResponse:
    """Tests for HealthCheckResponse model."""

    def test_healthy_response(self) -> None:
        """Test healthy response serialization."""
        response = HealthCheckResponse(
            status="healthy",
            civi_connected=True,
            response_time_ms=15.5,
            api_version="4",
            timestamp="2024-01-01T00:00:00Z",
        )

        data = response.model_dump()
        assert data["status"] == "healthy"
        assert data["civi_connected"] is True
        assert data["response_time_ms"] == 15.5
        assert data["api_version"] == "4"
        assert data["error"] is None

    def test_unhealthy_response(self) -> None:
        """Test unhealthy response serialization."""
        response = HealthCheckResponse(
            status="unhealthy",
            civi_connected=False,
            response_time_ms=None,
            timestamp="2024-01-01T00:00:00Z",
            error="Connection refused",
        )

        data = response.model_dump()
        assert data["status"] == "unhealthy"
        assert data["civi_connected"] is False
        assert data["error"] == "Connection refused"


class TestContactModels:
    """Tests for Contact Pydantic models."""

    def test_contact_create_defaults(self) -> None:
        """Test ContactCreate default values."""
        contact = ContactCreate()
        assert contact.contact_type == "Individual"
        assert contact.do_not_email is False
        assert contact.is_opt_out is False

    def test_contact_create_full(self) -> None:
        """Test ContactCreate with all fields."""
        contact = ContactCreate(
            first_name="John",
            last_name="Doe",
            email_primary="john@example.com",
            contact_type="Individual",
        )

        assert contact.first_name == "John"
        assert contact.last_name == "Doe"
        assert contact.email_primary == "john@example.com"

    def test_contact_response_with_id(self) -> None:
        """Test ContactResponse includes required id."""
        response = ContactResponse(
            id=1,
            first_name="John",
            last_name="Doe",
            display_name="John Doe",
            is_deleted=False,
        )

        assert response.id == 1
        assert response.display_name == "John Doe"

    def test_contact_response_serialization(self) -> None:
        """Test ContactResponse serializes correctly."""
        response = ContactResponse(
            id=1,
            first_name="John",
            last_name="Doe",
            created_date=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        data = response.model_dump()
        assert data["id"] == 1
        assert "created_date" in data

    def test_contact_update_partial(self) -> None:
        """Test ContactUpdate allows partial updates."""
        update = ContactUpdate(first_name="Jane")
        data = update.model_dump(exclude_unset=True)
        assert "first_name" in data
        assert "last_name" not in data


class TestActivityModels:
    """Tests for Activity Pydantic models."""

    def test_activity_create_requires_type_id(self) -> None:
        """Test ActivityCreate requires activity_type_id."""
        activity = ActivityCreate(activity_type_id=1, subject="Test")
        assert activity.activity_type_id == 1

    def test_activity_response_serialization(self) -> None:
        """Test ActivityResponse serialization."""
        response = ActivityResponse(
            id=1,
            activity_type_id=3,
            subject="Follow up",
            status_id=2,
        )

        data = response.model_dump()
        assert data["id"] == 1
        assert data["subject"] == "Follow up"


class TestContributionModels:
    """Tests for Contribution Pydantic models."""

    def test_contribution_create_required_fields(self) -> None:
        """Test ContributionCreate required fields."""
        contribution = ContributionCreate(
            contact_id=1,
            financial_type_id=1,
            total_amount=100.00,
        )

        assert contribution.contact_id == 1
        assert contribution.financial_type_id == 1
        assert contribution.total_amount == 100.00
        assert contribution.currency == "USD"

    def test_contribution_response_serialization(self) -> None:
        """Test ContributionResponse serialization."""
        response = ContributionResponse(
            id=1,
            contact_id=1,
            financial_type_id=1,
            total_amount=50.00,
        )

        data = response.model_dump()
        assert data["id"] == 1
        assert data["total_amount"] == 50.00


class TestEventModels:
    """Tests for Event Pydantic models."""

    def test_event_create_required_fields(self) -> None:
        """Test EventCreate required fields."""
        event = EventCreate(
            title="Annual Conference",
            event_type_id=1,
            start_date=datetime(2024, 6, 15, 9, 0, 0, tzinfo=UTC),
        )

        assert event.title == "Annual Conference"
        assert event.event_type_id == 1
        assert event.is_active is True
        assert event.is_public is True

    def test_event_response_serialization(self) -> None:
        """Test EventResponse serialization."""
        response = EventResponse(
            id=1,
            title="Conference",
            event_type_id=1,
        )

        data = response.model_dump()
        assert data["id"] == 1
        assert data["title"] == "Conference"


class TestMembershipModels:
    """Tests for Membership Pydantic models."""

    def test_membership_create_required_fields(self) -> None:
        """Test MembershipCreate required fields."""
        membership = MembershipCreate(
            contact_id=1,
            membership_type_id=1,
        )

        assert membership.contact_id == 1
        assert membership.membership_type_id == 1

    def test_membership_response_serialization(self) -> None:
        """Test MembershipResponse serialization."""
        response = MembershipResponse(
            id=1,
            contact_id=1,
            membership_type_id=1,
            status_id=2,
        )

        data = response.model_dump()
        assert data["id"] == 1
        assert data["status_id"] == 2


class TestGetCiviClient:
    """Tests for get_civi_client dependency."""

    @pytest.mark.asyncio
    async def test_returns_client_from_app_state(
        self,
        mock_civi_client: CiviClient,
    ) -> None:
        """Test get_civi_client returns client from app.state."""
        app = FastAPI()
        setattr(app.state, CIVI_CLIENT_STATE_KEY, mock_civi_client)

        request = Request(
            scope={
                "type": "http",
                "app": app,
                "headers": [],
                "method": "GET",
                "path": "/",
            },
        )

        result = await get_civi_client(request)
        assert result is mock_civi_client

    @pytest.mark.asyncio
    async def test_raises_when_client_not_in_state(self) -> None:
        """Test get_civi_client raises RuntimeError when client missing."""
        app = FastAPI()

        request = Request(
            scope={
                "type": "http",
                "app": app,
                "headers": [],
                "method": "GET",
                "path": "/",
            },
        )

        with pytest.raises(RuntimeError, match="CiviClient not found"):
            await get_civi_client(request)

    @pytest.mark.asyncio
    async def test_error_message_includes_state_key(self) -> None:
        """Test error message includes the expected state key."""
        app = FastAPI()

        request = Request(
            scope={
                "type": "http",
                "app": app,
                "headers": [],
                "method": "GET",
                "path": "/",
            },
        )

        with pytest.raises(RuntimeError, match=CIVI_CLIENT_STATE_KEY):
            await get_civi_client(request)


class TestCiviLifespan:
    """Tests for civi_lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_client(self) -> None:
        """Test civi_lifespan initializes CiviClient on startup."""
        app = FastAPI()

        with patch.dict(
            "os.environ",
            {
                "CIVI_BASE_URL": "https://test.example.org/civicrm/ajax/api4",
                "CIVI_API_KEY": "test-key",
            },
        ):
            async with civi_lifespan(app):
                client = getattr(app.state, CIVI_CLIENT_STATE_KEY, None)
                assert client is not None
                assert isinstance(client, CiviClient)
                assert client.settings.base_url == "https://test.example.org/civicrm/ajax/api4"

    @pytest.mark.asyncio
    async def test_lifespan_closes_client_on_shutdown(self) -> None:
        """Test civi_lifespan closes CiviClient on shutdown."""
        app = FastAPI()

        with patch.dict(
            "os.environ",
            {
                "CIVI_BASE_URL": "https://test.example.org/civicrm/ajax/api4",
                "CIVI_API_KEY": "test-key",
            },
        ):
            async with civi_lifespan(app):
                client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
                # Client should be available during lifespan
                assert client is not None

            # After lifespan ends, verify close was called
            # (Client transport should be None after close)
            assert client._transport is None


class TestCreateCiviLifespan:
    """Tests for create_civi_lifespan factory."""

    @pytest.mark.asyncio
    async def test_creates_lifespan_with_default_config(self) -> None:
        """Test create_civi_lifespan with default config."""
        app = FastAPI()

        with patch.dict(
            "os.environ",
            {
                "CIVI_BASE_URL": "https://default.example.org/civicrm/ajax/api4",
                "CIVI_API_KEY": "default-key",
            },
        ):
            lifespan = create_civi_lifespan()
            async with lifespan(app):
                client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
                assert client is not None
                assert client.settings.base_url == "https://default.example.org/civicrm/ajax/api4"

    @pytest.mark.asyncio
    async def test_creates_lifespan_with_custom_config(
        self,
        test_settings: CiviSettings,
    ) -> None:
        """Test create_civi_lifespan with custom config."""
        app = FastAPI()

        config = CiviFastAPIConfig(settings=test_settings)
        lifespan = create_civi_lifespan(config)

        async with lifespan(app):
            client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
            assert client is not None
            assert client.settings is test_settings

    @pytest.mark.asyncio
    async def test_creates_lifespan_with_debug_enabled(
        self,
        test_settings: CiviSettings,
    ) -> None:
        """Test create_civi_lifespan enables debug logging."""
        app = FastAPI()

        config = CiviFastAPIConfig(settings=test_settings, debug=True)
        lifespan = create_civi_lifespan(config)

        async with lifespan(app):
            client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
            assert client is not None

    @pytest.mark.asyncio
    async def test_lifespan_loads_env_when_settings_none(self) -> None:
        """Test lifespan loads from env when config.settings is None."""
        app = FastAPI()

        config = CiviFastAPIConfig(settings=None)

        with patch.dict(
            "os.environ",
            {
                "CIVI_BASE_URL": "https://env.example.org/civicrm/ajax/api4",
                "CIVI_API_KEY": "env-key",
            },
        ):
            lifespan = create_civi_lifespan(config)
            async with lifespan(app):
                client = getattr(app.state, CIVI_CLIENT_STATE_KEY)
                assert client.settings.base_url == "https://env.example.org/civicrm/ajax/api4"


class TestHealthCheckRouter:
    """Tests for health check router."""

    def test_create_health_check_router_default_path(self) -> None:
        """Test router created with default path."""
        router = create_health_check_router()
        routes = [r.path for r in router.routes]
        assert "/health/civi" in routes

    def test_create_health_check_router_custom_path(self) -> None:
        """Test router created with custom path."""
        router = create_health_check_router(path="/custom/health")
        routes = [r.path for r in router.routes]
        assert "/custom/health" in routes

    def test_create_health_check_router_custom_tags(self) -> None:
        """Test router created with custom tags."""
        router = create_health_check_router(tags=["Custom", "Health"])
        assert router.tags == ["Custom", "Health"]


class TestHealthCheckEndpoint:
    """Tests for health check endpoint with mocked API."""

    @pytest.fixture
    def app_with_health(self, test_settings: CiviSettings) -> FastAPI:
        """Create app with health check endpoint."""
        app = FastAPI()
        client = CiviClient(settings=test_settings)
        setattr(app.state, CIVI_CLIENT_STATE_KEY, client)
        router = create_health_check_router()
        app.include_router(router)
        return app

    @respx.mock
    def test_health_check_healthy(self, app_with_health: FastAPI) -> None:
        """Test health check returns healthy status."""
        respx.post("https://test.example.org/civicrm/ajax/api4/System/check").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_health) as client:
            response = client.get("/health/civi")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["civi_connected"] is True
        assert "response_time_ms" in data
        assert data["api_version"] == "4"

    @respx.mock
    def test_health_check_unhealthy(self, app_with_health: FastAPI) -> None:
        """Test health check returns unhealthy status on API error."""
        respx.post("https://test.example.org/civicrm/ajax/api4/System/check").mock(
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with TestClient(app_with_health) as client:
            response = client.get("/health/civi")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["civi_connected"] is False
        assert "error" in data


class TestContactRouter:
    """Tests for Contact CRUD router."""

    @pytest.fixture
    def app_with_contacts(self, test_settings: CiviSettings) -> FastAPI:
        """Create app with contact router."""
        app = FastAPI()
        client = CiviClient(settings=test_settings)
        setattr(app.state, CIVI_CLIENT_STATE_KEY, client)
        router = create_contact_router()
        app.include_router(router, prefix="/api")
        return app

    @respx.mock
    def test_list_contacts(
        self,
        app_with_contacts: FastAPI,
        sample_contact_response: dict[str, Any],
    ) -> None:
        """Test list contacts endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(200, json=sample_contact_response),
        )

        with TestClient(app_with_contacts) as client:
            response = client.get("/api/contacts")

        assert response.status_code == 200
        data = response.json()
        assert "values" in data
        assert len(data["values"]) == 2
        assert data["count"] == 2

    @respx.mock
    def test_list_contacts_with_filters(
        self,
        app_with_contacts: FastAPI,
        sample_contact_response: dict[str, Any],
    ) -> None:
        """Test list contacts with query parameters."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(200, json=sample_contact_response),
        )

        with TestClient(app_with_contacts) as client:
            response = client.get(
                "/api/contacts",
                params={
                    "limit": 10,
                    "offset": 5,
                    "contact_type": "Individual",
                    "search": "John",
                },
            )

        assert response.status_code == 200

    @respx.mock
    def test_get_contact_success(
        self,
        app_with_contacts: FastAPI,
        sample_single_contact: dict[str, Any],
    ) -> None:
        """Test get single contact by ID."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(200, json=sample_single_contact),
        )

        with TestClient(app_with_contacts) as client:
            response = client.get("/api/contacts/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["display_name"] == "John Doe"

    @respx.mock
    def test_get_contact_not_found(self, app_with_contacts: FastAPI) -> None:
        """Test get contact returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_contacts) as client:
            response = client.get("/api/contacts/999")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]

    @respx.mock
    def test_create_contact_success(
        self,
        app_with_contacts: FastAPI,
        sample_contact_create_response: dict[str, Any],
    ) -> None:
        """Test create contact endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/create").mock(
            return_value=httpx.Response(200, json=sample_contact_create_response),
        )

        with TestClient(app_with_contacts) as client:
            response = client.post(
                "/api/contacts",
                json={
                    "first_name": "New",
                    "last_name": "Contact",
                    "email_primary": "new@example.com",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 100
        assert data["first_name"] == "New"

    @respx.mock
    def test_update_contact_success(
        self,
        app_with_contacts: FastAPI,
    ) -> None:
        """Test update contact endpoint."""
        update_response = {
            "values": [
                {
                    "id": 1,
                    "first_name": "Updated",
                    "last_name": "Contact",
                    "display_name": "Updated Contact",
                    "contact_type": "Individual",
                },
            ],
            "count": 1,
        }

        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/update").mock(
            return_value=httpx.Response(200, json=update_response),
        )

        with TestClient(app_with_contacts) as client:
            response = client.put(
                "/api/contacts/1",
                json={"first_name": "Updated"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"

    @respx.mock
    def test_update_contact_no_changes(
        self,
        app_with_contacts: FastAPI,
        sample_single_contact: dict[str, Any],
    ) -> None:
        """Test update contact with no changes fetches current state."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(200, json=sample_single_contact),
        )

        with TestClient(app_with_contacts) as client:
            response = client.put(
                "/api/contacts/1",
                json={},
            )

        assert response.status_code == 200

    @respx.mock
    def test_update_contact_not_found(self, app_with_contacts: FastAPI) -> None:
        """Test update contact returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/update").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_contacts) as client:
            response = client.put(
                "/api/contacts/999",
                json={"first_name": "Test"},
            )

        assert response.status_code == 404

    @respx.mock
    def test_delete_contact_success(self, app_with_contacts: FastAPI) -> None:
        """Test delete contact endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 1}),
        )

        with TestClient(app_with_contacts) as client:
            response = client.delete("/api/contacts/1")

        assert response.status_code == 204

    @respx.mock
    def test_delete_contact_not_found(self, app_with_contacts: FastAPI) -> None:
        """Test delete contact returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_contacts) as client:
            response = client.delete("/api/contacts/999")

        assert response.status_code == 404


class TestEntityRouter:
    """Tests for generic entity router."""

    @pytest.fixture
    def app_with_entity(self, test_settings: CiviSettings) -> FastAPI:
        """Create app with generic entity router."""
        app = FastAPI()
        client = CiviClient(settings=test_settings)
        setattr(app.state, CIVI_CLIENT_STATE_KEY, client)
        router = create_entity_router("Activity")
        app.include_router(router, prefix="/api")
        return app

    def test_create_entity_router_default_prefix(self) -> None:
        """Test entity router uses default prefix."""
        router = create_entity_router("Activity")
        assert router.prefix == "/activitys"

    def test_create_entity_router_custom_prefix(self) -> None:
        """Test entity router with custom prefix."""
        router = create_entity_router("Activity", prefix="/activities")
        assert router.prefix == "/activities"

    def test_create_entity_router_custom_tags(self) -> None:
        """Test entity router with custom tags."""
        router = create_entity_router("Activity", tags=["Custom"])
        assert router.tags == ["Custom"]

    @respx.mock
    def test_list_entities(
        self,
        app_with_entity: FastAPI,
        sample_activity_response: dict[str, Any],
    ) -> None:
        """Test list entities endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/get").mock(
            return_value=httpx.Response(200, json=sample_activity_response),
        )

        with TestClient(app_with_entity) as client:
            response = client.get("/api/activitys")

        assert response.status_code == 200
        data = response.json()
        assert "values" in data

    @respx.mock
    def test_get_entity_success(
        self,
        app_with_entity: FastAPI,
        sample_single_activity: dict[str, Any],
    ) -> None:
        """Test get single entity by ID."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/get").mock(
            return_value=httpx.Response(200, json=sample_single_activity),
        )

        with TestClient(app_with_entity) as client:
            response = client.get("/api/activitys/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1

    @respx.mock
    def test_get_entity_not_found(self, app_with_entity: FastAPI) -> None:
        """Test get entity returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/get").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_entity) as client:
            response = client.get("/api/activitys/999")

        assert response.status_code == 404

    @respx.mock
    def test_create_entity_success(
        self,
        app_with_entity: FastAPI,
        sample_activity_create_response: dict[str, Any],
    ) -> None:
        """Test create entity endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/create").mock(
            return_value=httpx.Response(200, json=sample_activity_create_response),
        )

        with TestClient(app_with_entity) as client:
            response = client.post(
                "/api/activitys",
                json={"activity_type_id": 3, "subject": "New Activity"},
            )

        assert response.status_code == 201

    @respx.mock
    def test_update_entity_success(self, app_with_entity: FastAPI) -> None:
        """Test update entity endpoint."""
        update_response = {
            "values": [{"id": 1, "subject": "Updated"}],
            "count": 1,
        }

        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/update").mock(
            return_value=httpx.Response(200, json=update_response),
        )

        with TestClient(app_with_entity) as client:
            response = client.put(
                "/api/activitys/1",
                json={"subject": "Updated"},
            )

        assert response.status_code == 200

    @respx.mock
    def test_update_entity_not_found(self, app_with_entity: FastAPI) -> None:
        """Test update entity returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/update").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_entity) as client:
            response = client.put(
                "/api/activitys/999",
                json={"subject": "Test"},
            )

        assert response.status_code == 404

    @respx.mock
    def test_delete_entity_success(self, app_with_entity: FastAPI) -> None:
        """Test delete entity endpoint."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 1}),
        )

        with TestClient(app_with_entity) as client:
            response = client.delete("/api/activitys/1")

        assert response.status_code == 204

    @respx.mock
    def test_delete_entity_not_found(self, app_with_entity: FastAPI) -> None:
        """Test delete entity returns 404 when not found."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Activity/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        with TestClient(app_with_entity) as client:
            response = client.delete("/api/activitys/999")

        assert response.status_code == 404


class TestCiviRouter:
    """Tests for create_civi_router factory."""

    def test_create_router_default_entities(self) -> None:
        """Test router includes default entities."""
        router = create_civi_router()

        # Get all route paths
        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)

        # Should include Contact router paths
        assert "/contacts" in paths or any("/contacts" in p for p in paths)

    def test_create_router_include_entities(self) -> None:
        """Test router includes only specified entities."""
        config = CiviFastAPIConfig(
            include_entities=["Contact", "Activity"],
            enable_health_check=False,
        )
        router = create_civi_router(config)

        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)

        # Should include Contact and Activity
        assert any("contact" in p.lower() for p in paths)
        assert any("activity" in p.lower() for p in paths)

        # Should NOT include others
        assert not any("contribution" in p.lower() for p in paths)
        assert not any("event" in p.lower() for p in paths)

    def test_create_router_exclude_entities(self) -> None:
        """Test router excludes specified entities."""
        config = CiviFastAPIConfig(
            exclude_entities=["Contact", "Activity"],
            enable_health_check=False,
        )
        router = create_civi_router(config)

        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)

        # Should NOT include Contact or Activity
        assert not any("contact" in p.lower() for p in paths)
        assert not any("activity" in p.lower() for p in paths)

    def test_create_router_with_health_check(self) -> None:
        """Test router includes health check when enabled."""
        config = CiviFastAPIConfig(enable_health_check=True)
        router = create_civi_router(config)

        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)

        assert "/health/civi" in paths

    def test_create_router_without_health_check(self) -> None:
        """Test router excludes health check when disabled."""
        config = CiviFastAPIConfig(enable_health_check=False)
        router = create_civi_router(config)

        paths = set()
        for route in router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)

        assert "/health/civi" not in paths

    def test_create_router_custom_tags(self) -> None:
        """Test router uses custom OpenAPI tags."""
        config = CiviFastAPIConfig(openapi_tags=["Custom", "API"])
        router = create_civi_router(config)

        assert router.tags == ["Custom", "API"]


class TestFullAppIntegration:
    """Integration tests with complete FastAPI application."""

    @pytest.fixture
    def full_app(self, test_settings: CiviSettings) -> FastAPI:
        """Create complete FastAPI app with all routes."""
        config = CiviFastAPIConfig(
            settings=test_settings,
            include_entities=["Contact", "Activity"],
            enable_health_check=True,
        )

        lifespan = create_civi_lifespan(config)
        app = FastAPI(lifespan=lifespan)
        router = create_civi_router(config)
        app.include_router(router, prefix="/api")

        return app

    @respx.mock
    def test_full_app_contact_workflow(self, full_app: FastAPI) -> None:
        """Test complete contact CRUD workflow."""
        # Mock create
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/create").mock(
            return_value=httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 1,
                            "first_name": "Test",
                            "last_name": "User",
                            "display_name": "Test User",
                            "contact_type": "Individual",
                        },
                    ],
                    "count": 1,
                },
            ),
        )

        # Mock get
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 1,
                            "first_name": "Test",
                            "last_name": "User",
                            "display_name": "Test User",
                            "contact_type": "Individual",
                        },
                    ],
                    "count": 1,
                },
            ),
        )

        # Mock delete
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 1}),
        )

        with TestClient(full_app) as client:
            # Create
            create_response = client.post(
                "/api/contacts",
                json={"first_name": "Test", "last_name": "User"},
            )
            assert create_response.status_code == 201

            # Read
            get_response = client.get("/api/contacts/1")
            assert get_response.status_code == 200
            assert get_response.json()["first_name"] == "Test"

            # Delete
            delete_response = client.delete("/api/contacts/1")
            assert delete_response.status_code == 204


class TestConstants:
    """Tests for module constants."""

    def test_civi_client_state_key(self) -> None:
        """Test CIVI_CLIENT_STATE_KEY value."""
        assert CIVI_CLIENT_STATE_KEY == "civi_client"

    def test_default_entities(self) -> None:
        """Test DEFAULT_ENTITIES contains expected values."""
        expected = ["Contact", "Activity", "Contribution", "Event", "Membership", "Participant", "Group"]
        assert expected == DEFAULT_ENTITIES

    def test_default_entities_immutable_usage(self) -> None:
        """Test DEFAULT_ENTITIES is used but not mutated."""
        original = list(DEFAULT_ENTITIES)

        # Create router to use the constant
        config = CiviFastAPIConfig(enable_health_check=False)
        create_civi_router(config)

        # Should remain unchanged
        assert original == DEFAULT_ENTITIES
