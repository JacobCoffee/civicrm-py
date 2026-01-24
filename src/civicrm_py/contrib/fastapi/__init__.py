"""FastAPI integration for civi-py.

Provides idiomatic FastAPI support with:
- Lifespan context manager for client lifecycle management
- Dependency injection via FastAPI's Depends() system
- Auto-generated CRUD routes via APIRouter factory
- Pydantic models for request/response validation
- Health check endpoint for monitoring

Quick Start:
    >>> from fastapi import FastAPI, Depends
    >>> from civicrm_py.core.client import CiviClient
    >>> from civicrm_py.contrib.fastapi import civi_lifespan, get_civi_client
    >>>
    >>> app = FastAPI(lifespan=civi_lifespan)
    >>>
    >>> @app.get("/contacts")
    ... async def list_contacts(client: CiviClient = Depends(get_civi_client)):
    ...     response = await client.get("Contact", limit=10)
    ...     return {"contacts": response.values}

With Configuration:
    >>> from civicrm_py.contrib.fastapi import CiviFastAPIConfig, create_civi_lifespan
    >>> from civicrm_py import CiviSettings
    >>>
    >>> config = CiviFastAPIConfig(
    ...     settings=CiviSettings.from_env(),
    ...     api_prefix="/api/v1/civi",
    ...     enable_health_check=True,
    ... )
    >>> app = FastAPI(lifespan=create_civi_lifespan(config))

Using Router Factory:
    >>> from civicrm_py.contrib.fastapi import create_civi_router, CiviFastAPIConfig
    >>>
    >>> config = CiviFastAPIConfig(include_entities=["Contact", "Activity"])
    >>> router = create_civi_router(config)
    >>> app.include_router(router)

Environment Variables:
    Set these environment variables for automatic configuration:
    - CIVI_BASE_URL: CiviCRM API base URL
    - CIVI_API_KEY: API key for authentication
    - CIVI_SITE_KEY: Optional site key
    - CIVI_TIMEOUT: Request timeout (default: 30)
    - CIVI_VERIFY_SSL: Verify SSL certificates (default: true)

Generated Routes (when using create_civi_router):
    GET    {api_prefix}/contacts         - List contacts
    GET    {api_prefix}/contacts/{id}    - Get single contact
    POST   {api_prefix}/contacts         - Create contact
    PUT    {api_prefix}/contacts/{id}    - Update contact
    DELETE {api_prefix}/contacts/{id}    - Delete contact
    (Same pattern for activities, contributions, events, memberships, etc.)

Health Check:
    GET /health/civi - Returns CiviCRM connectivity status
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

# Check if FastAPI is available
try:
    from fastapi import APIRouter, Depends, HTTPException, Query, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    from starlette import status

    FASTAPI_AVAILABLE = True
except ImportError as _import_error:
    FASTAPI_AVAILABLE = False
    _FASTAPI_IMPORT_ERROR = _import_error

    # Raise immediately on import if FastAPI is not available
    # This module requires FastAPI to function - the Pydantic models are defined at module level
    raise ImportError(
        "FastAPI is required for civicrm_py.contrib.fastapi. Install with: pip install civi-py[fastapi]"
    ) from _import_error

from civicrm_py.core.client import CiviClient
from civicrm_py.core.config import CiviSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

logger = logging.getLogger("civicrm_py.contrib.fastapi")

# Key used to store CiviClient in app.state
CIVI_CLIENT_STATE_KEY = "civi_client"


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class CiviFastAPIConfig:
    """Configuration for FastAPI CiviCRM integration.

    Controls API route generation, health checks, OpenAPI documentation,
    and client configuration.

    Attributes:
        settings: Optional CiviSettings instance. If not provided,
            settings will be loaded from environment variables.
        api_prefix: URL prefix for auto-generated CRUD routes.
            Set to None to disable automatic route generation.
        enable_health_check: Whether to register the health check endpoint.
        health_check_path: URL path for the health check endpoint.
        openapi_tags: Tags to apply to generated routes in OpenAPI docs.
        include_entities: List of entity names to include in route generation.
            If None, all supported entities are included.
        exclude_entities: List of entity names to exclude from route generation.
        debug: Enable debug logging for the integration.

    Example:
        >>> config = CiviFastAPIConfig(
        ...     api_prefix="/api/v1/civi",
        ...     enable_health_check=True,
        ...     include_entities=["Contact", "Activity", "Contribution"],
        ... )
    """

    settings: CiviSettings | None = None
    api_prefix: str | None = "/api/civi"
    enable_health_check: bool = True
    health_check_path: str = "/health/civi"
    openapi_tags: list[str] = field(default_factory=lambda: ["CiviCRM"])
    include_entities: list[str] | None = None
    exclude_entities: list[str] = field(default_factory=list)
    debug: bool = False

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.api_prefix is not None and not self.api_prefix.startswith("/"):
            self.api_prefix = f"/{self.api_prefix}"

        if not self.health_check_path.startswith("/"):
            self.health_check_path = f"/{self.health_check_path}"


# =============================================================================
# Pydantic Models (DTOs)
# =============================================================================


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints.

    Attributes:
        limit: Maximum number of records to return.
        offset: Number of records to skip.
    """

    limit: int = Field(default=25, ge=1, le=100, description="Maximum records to return")
    offset: int = Field(default=0, ge=0, description="Records to skip")


class APIResponse(BaseModel):
    """Standard API response wrapper.

    Attributes:
        values: List of returned records.
        count: Total number of records matching the query.
        count_fetched: Number of records actually returned.
    """

    values: list[dict[str, Any]]
    count: int
    count_fetched: int

    model_config = {"extra": "allow"}


class HealthCheckResponse(BaseModel):
    """Health check response model.

    Attributes:
        status: Overall health status ("healthy" or "unhealthy").
        civi_connected: Whether CiviCRM API is reachable.
        response_time_ms: API response time in milliseconds.
        api_version: CiviCRM API version (typically "4").
        timestamp: ISO timestamp of the health check.
        error: Error message if unhealthy.
    """

    status: str
    civi_connected: bool
    response_time_ms: float | None = None
    api_version: str | None = None
    timestamp: str
    error: str | None = None


# --- Contact Models ---


class ContactBase(BaseModel):
    """Base fields shared by Contact create/update/response models."""

    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    display_name: str | None = None
    sort_name: str | None = None
    nick_name: str | None = None
    contact_type: str = "Individual"
    contact_sub_type: list[str] | None = None
    prefix_id: int | None = None
    suffix_id: int | None = None
    email_primary: str | None = None
    phone_primary: str | None = None
    do_not_email: bool = False
    do_not_phone: bool = False
    do_not_mail: bool = False
    do_not_sms: bool = False
    do_not_trade: bool = False
    is_opt_out: bool = False
    preferred_communication_method: list[str] | None = None
    preferred_language: str | None = None
    source: str | None = None
    external_identifier: str | None = None

    model_config = {"extra": "allow"}


class ContactCreate(ContactBase):
    """Model for creating a new Contact.

    Example:
        >>> contact = ContactCreate(
        ...     first_name="Jane",
        ...     last_name="Smith",
        ...     email_primary="jane@example.com",
        ... )
    """


class ContactUpdate(ContactBase):
    """Model for updating an existing Contact.

    All fields are optional - only provided fields will be updated.
    """


class ContactResponse(ContactBase):
    """Model for Contact response data.

    Includes read-only fields like id, created_date, and modified_date.
    """

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


# --- Activity Models ---


class ActivityBase(BaseModel):
    """Base fields shared by Activity create/update/response models."""

    activity_type_id: int | None = None
    subject: str | None = None
    details: str | None = None
    activity_date_time: datetime | None = None
    duration: int | None = None
    location: str | None = None
    status_id: int | None = None
    priority_id: int | None = None
    source_contact_id: int | None = None
    target_contact_id: list[int] | None = None
    assignee_contact_id: list[int] | None = None

    model_config = {"extra": "allow"}


class ActivityCreate(ActivityBase):
    """Model for creating a new Activity."""

    activity_type_id: int  # Required


class ActivityUpdate(ActivityBase):
    """Model for updating an existing Activity."""


class ActivityResponse(ActivityBase):
    """Model for Activity response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


# --- Contribution Models ---


class ContributionBase(BaseModel):
    """Base fields shared by Contribution create/update/response models."""

    contact_id: int | None = None
    financial_type_id: int | None = None
    total_amount: float | None = None
    currency: str = "USD"
    contribution_status_id: int | None = None
    receive_date: datetime | None = None
    receipt_date: datetime | None = None
    thankyou_date: datetime | None = None
    source: str | None = None
    trxn_id: str | None = None
    invoice_id: str | None = None
    check_number: str | None = None
    note: str | None = None

    model_config = {"extra": "allow"}


class ContributionCreate(ContributionBase):
    """Model for creating a new Contribution."""

    contact_id: int  # Required
    financial_type_id: int  # Required
    total_amount: float  # Required


class ContributionUpdate(ContributionBase):
    """Model for updating an existing Contribution."""


class ContributionResponse(ContributionBase):
    """Model for Contribution response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


# --- Event Models ---


class EventBase(BaseModel):
    """Base fields shared by Event create/update/response models."""

    title: str | None = None
    summary: str | None = None
    description: str | None = None
    event_type_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_active: bool = True
    is_public: bool = True
    is_online_registration: bool = False
    max_participants: int | None = None
    event_full_text: str | None = None
    waitlist_text: str | None = None

    model_config = {"extra": "allow"}


class EventCreate(EventBase):
    """Model for creating a new Event."""

    title: str  # Required
    event_type_id: int  # Required
    start_date: datetime  # Required


class EventUpdate(EventBase):
    """Model for updating an existing Event."""


class EventResponse(EventBase):
    """Model for Event response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


# --- Membership Models ---


class MembershipBase(BaseModel):
    """Base fields shared by Membership create/update/response models."""

    contact_id: int | None = None
    membership_type_id: int | None = None
    status_id: int | None = None
    join_date: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    source: str | None = None
    owner_membership_id: int | None = None

    model_config = {"extra": "allow"}


class MembershipCreate(MembershipBase):
    """Model for creating a new Membership."""

    contact_id: int  # Required
    membership_type_id: int  # Required


class MembershipUpdate(MembershipBase):
    """Model for updating an existing Membership."""


class MembershipResponse(MembershipBase):
    """Model for Membership response data."""

    id: int
    is_deleted: bool = False
    created_date: datetime | None = None
    modified_date: datetime | None = None


# =============================================================================
# Dependency Injection
# =============================================================================


async def get_civi_client(request: Request) -> CiviClient:
    """FastAPI dependency to get CiviClient from request state.

    Use with FastAPI's Depends() for automatic injection.

    Args:
        request: FastAPI Request object.

    Returns:
        The initialized CiviClient instance.

    Raises:
        RuntimeError: If CiviClient is not found in application state,
            indicating that the lifespan handler was not configured.

    Example:
        >>> from fastapi import FastAPI, Depends
        >>> from civicrm_py.contrib.fastapi import get_civi_client, civi_lifespan
        >>> from civicrm_py.core.client import CiviClient
        >>>
        >>> app = FastAPI(lifespan=civi_lifespan)
        >>>
        >>> @app.get("/contacts/{contact_id}")
        ... async def get_contact(
        ...     contact_id: int,
        ...     client: CiviClient = Depends(get_civi_client),
        ... ):
        ...     response = await client.get(
        ...         "Contact",
        ...         where=[["id", "=", contact_id]],
        ...         limit=1,
        ...     )
        ...     if not response.values:
        ...         raise HTTPException(status_code=404, detail="Contact not found")
        ...     return response.values[0]
    """
    client = getattr(request.app.state, CIVI_CLIENT_STATE_KEY, None)
    if client is None:
        msg = (
            f"CiviClient not found in application state (key: {CIVI_CLIENT_STATE_KEY!r}). "
            "Ensure civi_lifespan or create_civi_lifespan() is set as the app's lifespan handler."
        )
        raise RuntimeError(msg)
    return client


# Type alias for dependency injection
CiviClientDep = Annotated[CiviClient, Depends(get_civi_client)]


# =============================================================================
# Lifespan Management
# =============================================================================


@asynccontextmanager
async def civi_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Default lifespan context manager for CiviClient lifecycle.

    Initializes CiviClient on startup using environment variables
    and closes it on shutdown.

    Args:
        app: FastAPI application instance.

    Yields:
        None after client is initialized.

    Example:
        >>> from fastapi import FastAPI
        >>> from civicrm_py.contrib.fastapi import civi_lifespan
        >>>
        >>> app = FastAPI(lifespan=civi_lifespan)
    """
    # Startup
    logger.debug("Loading CiviSettings from environment")
    settings = CiviSettings.from_env()
    client = CiviClient(settings)
    setattr(app.state, CIVI_CLIENT_STATE_KEY, client)
    logger.info("CiviClient initialized for %s", settings.base_url)

    yield

    # Shutdown
    logger.info("Closing CiviClient")
    await client.close()


def create_civi_lifespan(
    config: CiviFastAPIConfig | None = None,
) -> Any:  # noqa: ANN401 - Returns Callable that FastAPI expects
    """Create a lifespan context manager with custom configuration.

    Factory function to create a lifespan handler with custom settings.

    Args:
        config: CiviFastAPIConfig instance. If None, uses defaults.

    Returns:
        Async context manager suitable for FastAPI's lifespan parameter.

    Example:
        >>> from fastapi import FastAPI
        >>> from civicrm_py.contrib.fastapi import create_civi_lifespan, CiviFastAPIConfig
        >>> from civicrm_py import CiviSettings
        >>>
        >>> config = CiviFastAPIConfig(
        ...     settings=CiviSettings(
        ...         base_url="https://example.org/civicrm/ajax/api4", api_key="..."
        ...     ),
        ...     debug=True,
        ... )
        >>> app = FastAPI(lifespan=create_civi_lifespan(config))
    """
    config = config or CiviFastAPIConfig()

    if config.debug:
        logging.getLogger("civicrm_py").setLevel(logging.DEBUG)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup
        settings = config.settings
        if settings is None:
            logger.debug("Loading CiviSettings from environment")
            settings = CiviSettings.from_env()

        client = CiviClient(settings)
        setattr(app.state, CIVI_CLIENT_STATE_KEY, client)
        logger.info("CiviClient initialized for %s", settings.base_url)

        yield

        # Shutdown
        logger.info("Closing CiviClient")
        await client.close()

    return lifespan


# =============================================================================
# Health Check
# =============================================================================


async def civi_health_check(
    client: CiviClientDep,
) -> HealthCheckResponse:
    """Check CiviCRM API health and connectivity.

    Performs a lightweight API call to verify that the CiviCRM API is
    reachable and responding.

    Args:
        client: Injected CiviClient instance.

    Returns:
        HealthCheckResponse with status information.
    """
    timestamp = datetime.now(UTC).isoformat()
    start_time = time.perf_counter()

    try:
        await client.request("System", "check", {})
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return HealthCheckResponse(
            status="healthy",
            civi_connected=True,
            response_time_ms=round(elapsed_ms, 2),
            api_version="4",
            timestamp=timestamp,
        )
    except Exception as e:  # noqa: BLE001 - Health checks must catch all errors
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        error_msg = str(e)
        logger.warning("CiviCRM health check failed: %s", error_msg)

        return HealthCheckResponse(
            status="unhealthy",
            civi_connected=False,
            response_time_ms=round(elapsed_ms, 2) if elapsed_ms else None,
            timestamp=timestamp,
            error=error_msg,
        )


def create_health_check_router(
    path: str = "/health/civi",
    tags: list[str] | None = None,
) -> APIRouter:
    """Create a router with health check endpoint.

    Args:
        path: URL path for the health check endpoint.
        tags: OpenAPI tags for the endpoint.

    Returns:
        APIRouter with health check endpoint.

    Example:
        >>> from fastapi import FastAPI
        >>> from civicrm_py.contrib.fastapi import create_health_check_router
        >>>
        >>> app = FastAPI()
        >>> app.include_router(create_health_check_router())
    """
    router = APIRouter(tags=tags or ["Health"])

    @router.get(
        path,
        summary="CiviCRM Health Check",
        description="Check CiviCRM API connectivity and return status information.",
        response_model=HealthCheckResponse,
        responses={
            200: {"description": "CiviCRM is healthy"},
            503: {"description": "CiviCRM is unhealthy"},
        },
    )
    async def health_check(
        client: CiviClientDep,
    ) -> JSONResponse:
        response = await civi_health_check(client)
        status_code = status.HTTP_200_OK if response.civi_connected else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(content=response.model_dump(), status_code=status_code)

    return router


# =============================================================================
# Route Factory
# =============================================================================


def create_contact_router(tags: list[str] | None = None) -> APIRouter:  # noqa: C901
    """Create a router with Contact CRUD endpoints.

    Args:
        tags: OpenAPI tags for the endpoints.

    Returns:
        APIRouter with Contact CRUD endpoints.
    """
    router = APIRouter(prefix="/contacts", tags=tags or ["Contact"])

    @router.get(
        "",
        summary="List Contacts",
        description="Retrieve a paginated list of contacts with optional filtering.",
        response_model=APIResponse,
    )
    async def list_contacts(
        client: CiviClientDep,
        limit: Annotated[int, Query(ge=1, le=100, description="Max records to return")] = 25,
        offset: Annotated[int, Query(ge=0, description="Records to skip")] = 0,
        contact_type: Annotated[str | None, Query(description="Filter by contact type")] = None,
        is_deleted: Annotated[bool, Query(description="Include deleted contacts")] = False,  # noqa: FBT002
        search: Annotated[str | None, Query(description="Search in display_name")] = None,
    ) -> APIResponse:
        where: list[list[Any]] = []

        if contact_type:
            where.append(["contact_type", "=", contact_type])
        if not is_deleted:
            where.append(["is_deleted", "=", False])
        if search:
            where.append(["display_name", "CONTAINS", search])

        response = await client.get(
            "Contact",
            where=where if where else None,
            limit=limit,
            offset=offset,
        )

        return APIResponse(
            values=response.values or [],
            count=response.count or 0,
            count_fetched=response.countFetched or 0,
        )

    @router.get(
        "/{contact_id}",
        summary="Get Contact",
        description="Retrieve a single contact by ID.",
        response_model=ContactResponse,
    )
    async def get_contact(
        client: CiviClientDep,
        contact_id: int,
    ) -> ContactResponse:
        response = await client.get(
            "Contact",
            where=[["id", "=", contact_id]],
            limit=1,
        )

        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with id {contact_id} not found",
            )

        return ContactResponse(**response.values[0])

    @router.post(
        "",
        summary="Create Contact",
        description="Create a new contact.",
        response_model=ContactResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_contact(
        client: CiviClientDep,
        data: ContactCreate,
    ) -> ContactResponse:
        values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

        response = await client.create("Contact", values)

        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create contact",
            )

        return ContactResponse(**response.values[0])

    @router.put(
        "/{contact_id}",
        summary="Update Contact",
        description="Update an existing contact.",
        response_model=ContactResponse,
    )
    async def update_contact(
        client: CiviClientDep,
        contact_id: int,
        data: ContactUpdate,
    ) -> ContactResponse:
        values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

        if not values:
            # No updates provided, just fetch current state
            get_response = await client.get(
                "Contact",
                where=[["id", "=", contact_id]],
                limit=1,
            )
            if not get_response.values:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Contact with id {contact_id} not found",
                )
            return ContactResponse(**get_response.values[0])

        response = await client.update(
            "Contact",
            values=values,
            where=[["id", "=", contact_id]],
        )

        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with id {contact_id} not found",
            )

        return ContactResponse(**response.values[0])

    @router.delete(
        "/{contact_id}",
        summary="Delete Contact",
        description="Delete a contact (soft delete).",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_contact(
        client: CiviClientDep,
        contact_id: int,
    ) -> None:
        response = await client.delete(
            "Contact",
            where=[["id", "=", contact_id]],
        )

        if response.count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact with id {contact_id} not found",
            )

    return router


def create_entity_router(
    entity_name: str,
    *,
    prefix: str | None = None,
    tags: list[str] | None = None,
) -> APIRouter:
    """Factory to create a generic CRUD router for any CiviCRM entity.

    Creates a FastAPI APIRouter with standard CRUD operations for the
    specified CiviCRM entity.

    Args:
        entity_name: CiviCRM entity name (e.g., "Activity", "Contribution").
        prefix: URL prefix. Defaults to /{entity_name.lower()}s.
        tags: OpenAPI tags. Defaults to [entity_name].

    Returns:
        APIRouter with CRUD endpoints.

    Example:
        >>> activity_router = create_entity_router("Activity")
        >>> contribution_router = create_entity_router("Contribution")
        >>> app.include_router(activity_router, prefix="/api/civi")
    """
    router_prefix = prefix or f"/{entity_name.lower()}s"
    router_tags = tags or [entity_name]
    router = APIRouter(prefix=router_prefix, tags=router_tags)

    @router.get(
        "",
        summary=f"List {entity_name}",
        response_model=APIResponse,
    )
    async def list_entities(
        client: CiviClientDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> APIResponse:
        response = await client.get(
            entity_name,
            limit=limit,
            offset=offset,
        )
        return APIResponse(
            values=response.values or [],
            count=response.count or 0,
            count_fetched=response.countFetched or 0,
        )

    @router.get(
        "/{entity_id}",
        summary=f"Get {entity_name}",
    )
    async def get_entity(
        client: CiviClientDep,
        entity_id: int,
    ) -> dict[str, Any]:
        response = await client.get(
            entity_name,
            where=[["id", "=", entity_id]],
            limit=1,
        )
        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{entity_name} with id {entity_id} not found",
            )
        return response.values[0]

    @router.post(
        "",
        summary=f"Create {entity_name}",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_entity(
        client: CiviClientDep,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.create(entity_name, data)
        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create {entity_name}",
            )
        return response.values[0]

    @router.put(
        "/{entity_id}",
        summary=f"Update {entity_name}",
    )
    async def update_entity(
        client: CiviClientDep,
        entity_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.update(
            entity_name,
            values=data,
            where=[["id", "=", entity_id]],
        )
        if not response.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{entity_name} with id {entity_id} not found",
            )
        return response.values[0]

    @router.delete(
        "/{entity_id}",
        summary=f"Delete {entity_name}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_entity(
        client: CiviClientDep,
        entity_id: int,
    ) -> None:
        response = await client.delete(
            entity_name,
            where=[["id", "=", entity_id]],
        )
        if response.count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{entity_name} with id {entity_id} not found",
            )

    return router


# Default entity configurations
DEFAULT_ENTITIES = ["Contact", "Activity", "Contribution", "Event", "Membership", "Participant", "Group"]


def create_civi_router(
    config: CiviFastAPIConfig | None = None,
) -> APIRouter:
    """Create a comprehensive CiviCRM router with all entity endpoints.

    Creates an APIRouter with CRUD routes for CiviCRM entities based on
    the provided configuration.

    Args:
        config: CiviFastAPIConfig instance. If None, uses defaults.

    Returns:
        APIRouter with entity CRUD endpoints and optional health check.

    Example:
        >>> from fastapi import FastAPI
        >>> from civicrm_py.contrib.fastapi import create_civi_router, CiviFastAPIConfig
        >>>
        >>> config = CiviFastAPIConfig(
        ...     api_prefix="/api/civi",
        ...     include_entities=["Contact", "Activity"],
        ... )
        >>> router = create_civi_router(config)
        >>> app.include_router(router)
    """
    config = config or CiviFastAPIConfig()
    router = APIRouter(tags=config.openapi_tags)

    # Determine which entities to include
    include_set = set(config.include_entities) if config.include_entities else set(DEFAULT_ENTITIES)
    exclude_set = set(config.exclude_entities)
    entities = [e for e in DEFAULT_ENTITIES if e in include_set and e not in exclude_set]

    # Add Contact router with typed models (special handling)
    if "Contact" in entities:
        router.include_router(create_contact_router(tags=config.openapi_tags))
        entities.remove("Contact")

    # Add generic routers for other entities
    for entity in entities:
        entity_router = create_entity_router(entity, tags=config.openapi_tags)
        router.include_router(entity_router)

    # Add health check if enabled
    if config.enable_health_check:
        health_router = create_health_check_router(
            path=config.health_check_path,
            tags=["Health"],
        )
        router.include_router(health_router)

    return router


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    "CIVI_CLIENT_STATE_KEY",
    "DEFAULT_ENTITIES",
    "APIResponse",
    "ActivityBase",
    "ActivityCreate",
    "ActivityResponse",
    "ActivityUpdate",
    "CiviClientDep",
    "CiviFastAPIConfig",
    "ContactBase",
    "ContactCreate",
    "ContactResponse",
    "ContactUpdate",
    "ContributionBase",
    "ContributionCreate",
    "ContributionResponse",
    "ContributionUpdate",
    "EventBase",
    "EventCreate",
    "EventResponse",
    "EventUpdate",
    "HealthCheckResponse",
    "MembershipBase",
    "MembershipCreate",
    "MembershipResponse",
    "MembershipUpdate",
    "PaginationParams",
    "civi_health_check",
    "civi_lifespan",
    "create_civi_lifespan",
    "create_civi_router",
    "create_contact_router",
    "create_entity_router",
    "create_health_check_router",
    "get_civi_client",
]
