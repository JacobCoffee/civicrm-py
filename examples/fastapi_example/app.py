"""FastAPI CiviCRM demo application.

Demonstrates civi-py FastAPI integration using the shared showcase module:
- CiviShowcase service for high-level operations
- Full CRUD for contacts, activities, contributions, events
- Dashboard statistics endpoint
- Sample data generation endpoint
- Proper error handling with HTTP status codes
- Automatic OpenAPI documentation

Run from project root:
    # Start CiviCRM infrastructure (if needed)
    make infra-up
    make infra-install
    make infra-setup

    # Run the FastAPI example
    make example-fastapi

Then visit:
    - http://localhost:8002/             - API index
    - http://localhost:8002/docs         - Swagger UI (OpenAPI docs)
    - http://localhost:8002/redoc        - ReDoc documentation
    - http://localhost:8002/health/civi  - CiviCRM health check
    - http://localhost:8002/api/dashboard - Dashboard stats
    - http://localhost:8002/api/contacts  - Contacts API
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any

from dotenv import load_dotenv

# Load .env file from project root (auto-discovers parent directories)
load_dotenv()

from examples.shared import (
    CiviShowcase,
    DashboardStats,
    GenerationResult,
    PaginatedResult,
    SampleDataGenerator,
)
from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette import status

from civi_py.contrib.fastapi import (
    CiviFastAPIConfig,
    create_civi_lifespan,
    create_civi_router,
    get_civi_client,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger("fastapi_example")


# =============================================================================
# Pydantic Models (DTOs)
# =============================================================================


class PaginatedResponseDTO(BaseModel):
    """Paginated response DTO."""

    items: list[dict[str, Any]]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool
    has_prev: bool

    model_config = {"extra": "allow"}


class DashboardStatsDTO(BaseModel):
    """Dashboard statistics DTO."""

    total_contacts: int
    total_individuals: int
    total_organizations: int
    total_households: int
    total_activities: int
    total_contributions: int
    total_events: int
    recent_contacts: list[dict[str, Any]]
    recent_activities: list[dict[str, Any]]
    error: str | None = None

    model_config = {"extra": "allow"}


class GenerationResultDTO(BaseModel):
    """Sample data generation result DTO."""

    contacts_created: int
    contacts_updated: int
    activities_created: int
    activities_updated: int
    contributions_created: int
    contributions_updated: int
    events_created: int
    events_updated: int
    total_created: int
    total_updated: int
    total: int
    has_errors: bool
    errors: list[str]

    model_config = {"extra": "allow"}


class GenerationRequestDTO(BaseModel):
    """Sample data generation request DTO."""

    contacts: int = Field(default=10, ge=1, le=100, description="Number of contacts to generate")
    activities: int = Field(default=20, ge=1, le=200, description="Number of activities to generate")
    contributions: int = Field(default=15, ge=1, le=100, description="Number of contributions to generate")
    events: int = Field(default=5, ge=1, le=50, description="Number of events to generate")


class ErrorResponseDTO(BaseModel):
    """Error response DTO."""

    error: str
    detail: str | None = None


class ContactCreateDTO(BaseModel):
    """Contact create request DTO."""

    contact_type: str = Field(default="Individual", description="Contact type: Individual, Organization, or Household")
    first_name: str | None = Field(default=None, description="First name (for Individual)")
    last_name: str | None = Field(default=None, description="Last name (for Individual)")
    organization_name: str | None = Field(default=None, description="Organization name (for Organization)")
    email: str | None = Field(default=None, description="Primary email address")
    phone: str | None = Field(default=None, description="Primary phone number")

    model_config = {"extra": "allow"}


class ContactUpdateDTO(BaseModel):
    """Contact update request DTO."""

    first_name: str | None = None
    last_name: str | None = None
    organization_name: str | None = None
    email: str | None = None
    phone: str | None = None

    model_config = {"extra": "allow"}


class ActivityCreateDTO(BaseModel):
    """Activity create request DTO."""

    activity_type_id: int = Field(..., description="Activity type ID")
    subject: str = Field(..., description="Activity subject")
    source_contact_id: int = Field(..., description="Source contact ID")
    activity_date_time: str | None = Field(default=None, description="Activity date/time (ISO format)")
    status_id: int = Field(default=1, description="Activity status ID")
    details: str | None = Field(default=None, description="Activity details/notes")

    model_config = {"extra": "allow"}


class ContributionCreateDTO(BaseModel):
    """Contribution create request DTO."""

    contact_id: int = Field(..., description="Contact ID")
    total_amount: float = Field(..., description="Total contribution amount")
    financial_type_id: int = Field(default=1, description="Financial type ID")
    receive_date: str | None = Field(default=None, description="Receive date (ISO format)")
    source: str | None = Field(default=None, description="Contribution source")

    model_config = {"extra": "allow"}


class EventCreateDTO(BaseModel):
    """Event create request DTO."""

    title: str = Field(..., description="Event title")
    event_type_id: int = Field(default=1, description="Event type ID")
    start_date: str = Field(..., description="Start date (ISO format)")
    end_date: str | None = Field(default=None, description="End date (ISO format)")
    is_active: bool = Field(default=True, description="Whether the event is active")
    is_public: bool = Field(default=True, description="Whether the event is public")
    max_participants: int | None = Field(default=None, description="Maximum number of participants")

    model_config = {"extra": "allow"}


# =============================================================================
# Dependencies
# =============================================================================


# Dependency for CiviClient - uses the civi-py FastAPI integration
_civi_client_dep = Depends(get_civi_client)


async def get_showcase(
    client: Annotated[Any, _civi_client_dep],
) -> CiviShowcase:
    """Provide CiviShowcase instance."""
    return CiviShowcase(client)


async def get_generator(
    client: Annotated[Any, _civi_client_dep],
) -> SampleDataGenerator:
    """Provide SampleDataGenerator instance."""
    return SampleDataGenerator(client)


# Type aliases for dependency injection
ShowcaseDep = Annotated[CiviShowcase, Depends(get_showcase)]
GeneratorDep = Annotated[SampleDataGenerator, Depends(get_generator)]


# =============================================================================
# Helper Functions
# =============================================================================


def paginated_to_dto(result: PaginatedResult) -> PaginatedResponseDTO:
    """Convert PaginatedResult to DTO."""
    return PaginatedResponseDTO(
        items=result.items,
        total=result.total,
        page=result.page,
        per_page=result.per_page,
        pages=result.pages,
        has_next=result.has_next,
        has_prev=result.has_prev,
    )


def stats_to_dto(stats: DashboardStats) -> DashboardStatsDTO:
    """Convert DashboardStats to DTO."""
    return DashboardStatsDTO(
        total_contacts=stats.total_contacts,
        total_individuals=stats.total_individuals,
        total_organizations=stats.total_organizations,
        total_households=stats.total_households,
        total_activities=stats.total_activities,
        total_contributions=stats.total_contributions,
        total_events=stats.total_events,
        recent_contacts=stats.recent_contacts,
        recent_activities=stats.recent_activities,
        error=stats.error,
    )


def generation_to_dto(result: GenerationResult) -> GenerationResultDTO:
    """Convert GenerationResult to DTO."""
    return GenerationResultDTO(
        contacts_created=result.contacts_created,
        contacts_updated=result.contacts_updated,
        activities_created=result.activities_created,
        activities_updated=result.activities_updated,
        contributions_created=result.contributions_created,
        contributions_updated=result.contributions_updated,
        events_created=result.events_created,
        events_updated=result.events_updated,
        total_created=result.total_created,
        total_updated=result.total_updated,
        total=result.total,
        has_errors=result.has_errors,
        errors=result.errors,
    )


# =============================================================================
# Application Setup with Custom Lifespan
# =============================================================================


# Configure the CiviPlugin
config = CiviFastAPIConfig(
    api_prefix="/api/civi",  # Auto-generated CRUD routes at /api/civi/{entity}
    enable_health_check=True,
    health_check_path="/health/civi",
    include_entities=["Contact", "Activity", "Contribution", "Event"],
    openapi_tags=["CiviCRM Auto-Generated"],
    debug=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Custom lifespan that combines civi-py with example-specific setup."""
    # Use the civi-py lifespan
    async with create_civi_lifespan(config)(app):
        logger.info("FastAPI CiviCRM example started")
        yield
        logger.info("FastAPI CiviCRM example shutting down")


# Create the FastAPI application
app = FastAPI(
    title="CiviCRM FastAPI Demo",
    version="1.0.0",
    description=(
        "Demo API showing civi-py FastAPI integration with CiviShowcase.\n\n"
        "## Features\n"
        "- Dashboard statistics and recent items\n"
        "- Full CRUD for contacts, activities, contributions, events\n"
        "- Sample data generation for testing\n"
        "- Proper error handling with HTTP status codes\n\n"
        "## Auto-Generated Routes\n"
        "The `/api/civi/*` routes are auto-generated by the civi-py FastAPI integration.\n\n"
        "## Custom Routes\n"
        "The `/api/*` routes (dashboard, sample-data, etc.) are custom routes using CiviShowcase.\n\n"
        "## Health Check\n"
        "`GET /health/civi` - Check CiviCRM API connectivity"
    ),
    lifespan=lifespan,
)


# =============================================================================
# Root Endpoint
# =============================================================================


@app.get(
    "/",
    tags=["Root"],
    summary="API Index",
    description="Get API information and available endpoints.",
)
async def root() -> dict[str, Any]:
    """Return API index with links to documentation and key endpoints."""
    return {
        "name": "CiviCRM FastAPI Demo",
        "version": "1.0.0",
        "description": "Demo API showing civi-py FastAPI integration",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
        },
        "endpoints": {
            "health_check": "/health/civi",
            "dashboard": "/api/dashboard",
            "contacts": "/api/contacts",
            "activities": "/api/activities",
            "contributions": "/api/contributions",
            "events": "/api/events",
            "sample_data": "/api/sample-data",
            "auto_generated": "/api/civi/contacts",
        },
    }


# =============================================================================
# Dashboard and Utility Endpoints
# =============================================================================


@app.get(
    "/api/dashboard",
    tags=["Dashboard"],
    summary="Get dashboard statistics",
    description="Get dashboard statistics including contact counts and recent items.",
    response_model=DashboardStatsDTO,
    responses={
        200: {"description": "Dashboard statistics retrieved successfully"},
        503: {"description": "CiviCRM service unavailable", "model": ErrorResponseDTO},
    },
)
async def get_dashboard(showcase: ShowcaseDep) -> JSONResponse:
    """Get dashboard statistics including counts and recent items."""
    stats = await showcase.get_dashboard_stats()

    if stats.error:
        return JSONResponse(
            content=ErrorResponseDTO(error="Service unavailable", detail=stats.error).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(content=stats_to_dto(stats).model_dump(), status_code=status.HTTP_200_OK)


@app.post(
    "/api/sample-data",
    tags=["Utilities"],
    summary="Generate sample data",
    description="Generate sample CiviCRM data for testing and demonstration.",
    response_model=GenerationResultDTO,
    responses={
        201: {"description": "Sample data generated successfully"},
        400: {"description": "No data was created"},
        500: {"description": "Generation failed", "model": ErrorResponseDTO},
    },
)
async def generate_sample_data(
    generator: GeneratorDep,
    data: GenerationRequestDTO,
) -> JSONResponse:
    """Generate sample CiviCRM data for testing."""
    try:
        result = await generator.generate_all(
            contacts=data.contacts,
            activities=data.activities,
            contributions=data.contributions,
            events=data.events,
        )
        status_code = status.HTTP_201_CREATED if result.total_created > 0 else status.HTTP_400_BAD_REQUEST
        return JSONResponse(content=generation_to_dto(result).model_dump(), status_code=status_code)
    except Exception as e:
        return JSONResponse(
            content=ErrorResponseDTO(error="Generation failed", detail=str(e)).model_dump(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# =============================================================================
# Contacts CRUD Endpoints (using CiviShowcase)
# =============================================================================


@app.get(
    "/api/contacts",
    tags=["Contacts"],
    summary="List contacts",
    description="List contacts with pagination and optional filtering.",
    response_model=PaginatedResponseDTO,
    responses={
        200: {"description": "Contacts retrieved successfully"},
        503: {"description": "CiviCRM service unavailable", "model": ErrorResponseDTO},
    },
)
async def list_contacts(
    showcase: ShowcaseDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    search: Annotated[str | None, Query(description="Search in display_name")] = None,
    contact_type: Annotated[str | None, Query(description="Filter by contact type")] = None,
) -> JSONResponse:
    """List contacts with pagination and optional filtering."""
    result = await showcase.list_contacts(
        page=page,
        per_page=per_page,
        search=search,
        contact_type=contact_type,
    )

    if result.error:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to list contacts", detail=result.error).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(content=paginated_to_dto(result).model_dump(), status_code=status.HTTP_200_OK)


@app.get(
    "/api/contacts/{contact_id}",
    tags=["Contacts"],
    summary="Get contact by ID",
    description="Retrieve a single contact by ID.",
    responses={
        200: {"description": "Contact retrieved successfully"},
        404: {"description": "Contact not found", "model": ErrorResponseDTO},
    },
)
async def get_contact(
    showcase: ShowcaseDep,
    contact_id: int,
) -> JSONResponse:
    """Get a single contact by ID."""
    contact = await showcase.get_contact(contact_id)

    if contact is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Contact not found").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content=contact, status_code=status.HTTP_200_OK)


@app.post(
    "/api/contacts",
    tags=["Contacts"],
    summary="Create contact",
    description="Create a new contact.",
    responses={
        201: {"description": "Contact created successfully"},
        400: {"description": "Failed to create contact", "model": ErrorResponseDTO},
    },
)
async def create_contact(
    showcase: ShowcaseDep,
    data: ContactCreateDTO,
) -> JSONResponse:
    """Create a new contact."""
    contact_data: dict[str, Any] = {"contact_type": data.contact_type}
    if data.first_name:
        contact_data["first_name"] = data.first_name
    if data.last_name:
        contact_data["last_name"] = data.last_name
    if data.organization_name:
        contact_data["organization_name"] = data.organization_name
    if data.email:
        contact_data["email_primary.email"] = data.email
    if data.phone:
        contact_data["phone_primary.phone"] = data.phone

    contact = await showcase.create_contact(contact_data)

    if contact is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to create contact").model_dump(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return JSONResponse(content=contact, status_code=status.HTTP_201_CREATED)


@app.put(
    "/api/contacts/{contact_id}",
    tags=["Contacts"],
    summary="Update contact",
    description="Update an existing contact.",
    responses={
        200: {"description": "Contact updated successfully"},
        404: {"description": "Contact not found or update failed", "model": ErrorResponseDTO},
    },
)
async def update_contact(
    showcase: ShowcaseDep,
    contact_id: int,
    data: ContactUpdateDTO,
) -> JSONResponse:
    """Update an existing contact."""
    update_data: dict[str, Any] = {}
    if data.first_name is not None:
        update_data["first_name"] = data.first_name
    if data.last_name is not None:
        update_data["last_name"] = data.last_name
    if data.organization_name is not None:
        update_data["organization_name"] = data.organization_name
    if data.email is not None:
        update_data["email_primary.email"] = data.email
    if data.phone is not None:
        update_data["phone_primary.phone"] = data.phone

    if not update_data:
        return JSONResponse(
            content=ErrorResponseDTO(error="No fields to update").model_dump(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    contact = await showcase.update_contact(contact_id, update_data)

    if contact is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Contact not found or update failed").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content=contact, status_code=status.HTTP_200_OK)


@app.delete(
    "/api/contacts/{contact_id}",
    tags=["Contacts"],
    summary="Delete contact",
    description="Delete a contact (soft delete).",
    responses={
        200: {"description": "Contact deleted successfully"},
        404: {"description": "Contact not found or delete failed", "model": ErrorResponseDTO},
    },
)
async def delete_contact(
    showcase: ShowcaseDep,
    contact_id: int,
) -> JSONResponse:
    """Delete a contact (soft delete)."""
    success = await showcase.delete_contact(contact_id)

    if not success:
        return JSONResponse(
            content=ErrorResponseDTO(error="Contact not found or delete failed").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content={"deleted": True}, status_code=status.HTTP_200_OK)


# =============================================================================
# Activities CRUD Endpoints (using CiviShowcase)
# =============================================================================


@app.get(
    "/api/activities",
    tags=["Activities"],
    summary="List activities",
    description="List activities with pagination and optional filtering.",
    response_model=PaginatedResponseDTO,
    responses={
        200: {"description": "Activities retrieved successfully"},
        503: {"description": "CiviCRM service unavailable", "model": ErrorResponseDTO},
    },
)
async def list_activities(
    showcase: ShowcaseDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    search: Annotated[str | None, Query(description="Search in subject")] = None,
    contact_id: Annotated[int | None, Query(description="Filter by source contact ID")] = None,
) -> JSONResponse:
    """List activities with pagination and optional filtering."""
    result = await showcase.list_activities(
        page=page,
        per_page=per_page,
        search=search,
        contact_id=contact_id,
    )

    if result.error:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to list activities", detail=result.error).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(content=paginated_to_dto(result).model_dump(), status_code=status.HTTP_200_OK)


@app.get(
    "/api/activities/{activity_id}",
    tags=["Activities"],
    summary="Get activity by ID",
    description="Retrieve a single activity by ID.",
    responses={
        200: {"description": "Activity retrieved successfully"},
        404: {"description": "Activity not found", "model": ErrorResponseDTO},
    },
)
async def get_activity(
    showcase: ShowcaseDep,
    activity_id: int,
) -> JSONResponse:
    """Get a single activity by ID."""
    activity = await showcase.get_activity(activity_id)

    if activity is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Activity not found").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content=activity, status_code=status.HTTP_200_OK)


@app.post(
    "/api/activities",
    tags=["Activities"],
    summary="Create activity",
    description="Create a new activity.",
    responses={
        201: {"description": "Activity created successfully"},
        400: {"description": "Failed to create activity", "model": ErrorResponseDTO},
    },
)
async def create_activity(
    showcase: ShowcaseDep,
    data: ActivityCreateDTO,
) -> JSONResponse:
    """Create a new activity."""
    activity_data: dict[str, Any] = {
        "activity_type_id": data.activity_type_id,
        "subject": data.subject,
        "source_contact_id": data.source_contact_id,
        "status_id": data.status_id,
    }
    if data.activity_date_time:
        activity_data["activity_date_time"] = data.activity_date_time
    if data.details:
        activity_data["details"] = data.details

    activity = await showcase.create_activity(activity_data)

    if activity is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to create activity").model_dump(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return JSONResponse(content=activity, status_code=status.HTTP_201_CREATED)


@app.delete(
    "/api/activities/{activity_id}",
    tags=["Activities"],
    summary="Delete activity",
    description="Delete an activity (soft delete).",
    responses={
        200: {"description": "Activity deleted successfully"},
        404: {"description": "Activity not found or delete failed", "model": ErrorResponseDTO},
    },
)
async def delete_activity(
    showcase: ShowcaseDep,
    activity_id: int,
) -> JSONResponse:
    """Delete an activity (soft delete)."""
    success = await showcase.delete_activity(activity_id)

    if not success:
        return JSONResponse(
            content=ErrorResponseDTO(error="Activity not found or delete failed").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content={"deleted": True}, status_code=status.HTTP_200_OK)


# =============================================================================
# Contributions CRUD Endpoints (using CiviShowcase)
# =============================================================================


@app.get(
    "/api/contributions",
    tags=["Contributions"],
    summary="List contributions",
    description="List contributions with pagination and optional filtering.",
    response_model=PaginatedResponseDTO,
    responses={
        200: {"description": "Contributions retrieved successfully"},
        503: {"description": "CiviCRM service unavailable", "model": ErrorResponseDTO},
    },
)
async def list_contributions(
    showcase: ShowcaseDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    contact_id: Annotated[int | None, Query(description="Filter by contact ID")] = None,
) -> JSONResponse:
    """List contributions with pagination and optional filtering."""
    result = await showcase.list_contributions(
        page=page,
        per_page=per_page,
        contact_id=contact_id,
    )

    if result.error:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to list contributions", detail=result.error).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(content=paginated_to_dto(result).model_dump(), status_code=status.HTTP_200_OK)


@app.get(
    "/api/contributions/{contribution_id}",
    tags=["Contributions"],
    summary="Get contribution by ID",
    description="Retrieve a single contribution by ID.",
    responses={
        200: {"description": "Contribution retrieved successfully"},
        404: {"description": "Contribution not found", "model": ErrorResponseDTO},
    },
)
async def get_contribution(
    showcase: ShowcaseDep,
    contribution_id: int,
) -> JSONResponse:
    """Get a single contribution by ID."""
    contribution = await showcase.get_contribution(contribution_id)

    if contribution is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Contribution not found").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content=contribution, status_code=status.HTTP_200_OK)


@app.post(
    "/api/contributions",
    tags=["Contributions"],
    summary="Create contribution",
    description="Create a new contribution.",
    responses={
        201: {"description": "Contribution created successfully"},
        400: {"description": "Failed to create contribution", "model": ErrorResponseDTO},
    },
)
async def create_contribution(
    showcase: ShowcaseDep,
    data: ContributionCreateDTO,
) -> JSONResponse:
    """Create a new contribution."""
    contribution_data: dict[str, Any] = {
        "contact_id": data.contact_id,
        "total_amount": data.total_amount,
        "financial_type_id": data.financial_type_id,
    }
    if data.receive_date:
        contribution_data["receive_date"] = data.receive_date
    if data.source:
        contribution_data["source"] = data.source

    contribution = await showcase.create_contribution(contribution_data)

    if contribution is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to create contribution").model_dump(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return JSONResponse(content=contribution, status_code=status.HTTP_201_CREATED)


# =============================================================================
# Events CRUD Endpoints (using CiviShowcase)
# =============================================================================


@app.get(
    "/api/events",
    tags=["Events"],
    summary="List events",
    description="List events with pagination and optional filtering.",
    response_model=PaginatedResponseDTO,
    responses={
        200: {"description": "Events retrieved successfully"},
        503: {"description": "CiviCRM service unavailable", "model": ErrorResponseDTO},
    },
)
async def list_events(
    showcase: ShowcaseDep,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    search: Annotated[str | None, Query(description="Search in title")] = None,
    active_only: Annotated[bool, Query(description="Show only active events")] = True,
) -> JSONResponse:
    """List events with pagination and optional filtering."""
    result = await showcase.list_events(
        page=page,
        per_page=per_page,
        search=search,
        active_only=active_only,
    )

    if result.error:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to list events", detail=result.error).model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return JSONResponse(content=paginated_to_dto(result).model_dump(), status_code=status.HTTP_200_OK)


@app.get(
    "/api/events/{event_id}",
    tags=["Events"],
    summary="Get event by ID",
    description="Retrieve a single event by ID.",
    responses={
        200: {"description": "Event retrieved successfully"},
        404: {"description": "Event not found", "model": ErrorResponseDTO},
    },
)
async def get_event(
    showcase: ShowcaseDep,
    event_id: int,
) -> JSONResponse:
    """Get a single event by ID."""
    event = await showcase.get_event(event_id)

    if event is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Event not found").model_dump(),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(content=event, status_code=status.HTTP_200_OK)


@app.post(
    "/api/events",
    tags=["Events"],
    summary="Create event",
    description="Create a new event.",
    responses={
        201: {"description": "Event created successfully"},
        400: {"description": "Failed to create event", "model": ErrorResponseDTO},
    },
)
async def create_event(
    showcase: ShowcaseDep,
    data: EventCreateDTO,
) -> JSONResponse:
    """Create a new event."""
    event_data: dict[str, Any] = {
        "title": data.title,
        "event_type_id": data.event_type_id,
        "start_date": data.start_date,
        "is_active": data.is_active,
        "is_public": data.is_public,
    }
    if data.end_date:
        event_data["end_date"] = data.end_date
    if data.max_participants:
        event_data["max_participants"] = data.max_participants

    event = await showcase.create_event(event_data)

    if event is None:
        return JSONResponse(
            content=ErrorResponseDTO(error="Failed to create event").model_dump(),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return JSONResponse(content=event, status_code=status.HTTP_201_CREATED)


# =============================================================================
# Include Auto-Generated CiviCRM Router
# =============================================================================


# Create and include the auto-generated CiviCRM router
# This provides CRUD endpoints at /api/civi/{entity}s
civi_router = create_civi_router(config)
app.include_router(civi_router, prefix=config.api_prefix)


# =============================================================================
# Main Entry Point
# =============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", reload=True, port=8002, lifespan="on")
