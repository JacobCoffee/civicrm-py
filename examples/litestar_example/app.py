"""Litestar CiviCRM demo application.

Demonstrates civi-py Litestar integration using the shared showcase module:
- CiviShowcase service for high-level operations
- Full CRUD for contacts, activities, contributions, events
- Dashboard statistics endpoint
- Sample data generation endpoint
- Proper error handling with HTTP status codes

Run from project root:
    # Start CiviCRM infrastructure (if needed)
    make infra-up
    make infra-install
    make infra-setup

    # Run the Litestar example
    make example-litestar

Then visit:
    - http://localhost:8001/             - API index
    - http://localhost:8001/docs/scalar  - Scalar docs
    - http://localhost:8001/docs/swagger - Swagger UI
    - http://localhost:8001/health/civi  - CiviCRM health check
    - http://localhost:8001/api/dashboard - Dashboard stats
    - http://localhost:8001/api/contacts  - Contacts API
    - http://localhost:8001/explorer/    - Web UI for API exploration
"""

import warnings
from typing import Any

# Suppress Litestar's pydantic v1 warning (we don't use pydantic)
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible",
    category=UserWarning,
)

from dotenv import load_dotenv

# Load .env file from project root (auto-discovers parent directories)
load_dotenv()

import msgspec
from examples.shared import (
    CiviShowcase,
    DashboardStats,
    GenerationResult,
    PaginatedResult,
    SampleDataGenerator,
)
from examples.shared.jinja_env import TEMPLATES_DIR as SHARED_TEMPLATES_DIR
from examples.shared.jinja_env import create_jinja_env
from litestar import Controller, Litestar, Request, delete, get, post, put
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.di import Provide
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin, SwaggerRenderPlugin
from litestar.response import Response, Template
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)
from litestar.template import TemplateConfig

from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig, WebUIConfig
from civi_py.core.client import CiviClient
from civi_py.webui import TEMPLATES_DIR as WEBUI_TEMPLATES_DIR

# =============================================================================
# DTOs (msgspec Structs for serialization)
# =============================================================================


class PaginatedResponseDTO(msgspec.Struct, kw_only=True):
    """Paginated response DTO."""

    items: list[dict[str, Any]]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool
    has_prev: bool


class DashboardStatsDTO(msgspec.Struct, kw_only=True):
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


class GenerationResultDTO(msgspec.Struct, kw_only=True):
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


class GenerationRequestDTO(msgspec.Struct, kw_only=True):
    """Sample data generation request DTO."""

    contacts: int = 10
    activities: int = 20
    contributions: int = 15
    events: int = 5


class ErrorResponseDTO(msgspec.Struct, kw_only=True):
    """Error response DTO."""

    error: str
    detail: str | None = None


class ContactCreateDTO(msgspec.Struct, kw_only=True):
    """Contact create request DTO."""

    contact_type: str = "Individual"
    first_name: str | None = None
    last_name: str | None = None
    organization_name: str | None = None
    email: str | None = None
    phone: str | None = None


class ContactUpdateDTO(msgspec.Struct, kw_only=True):
    """Contact update request DTO."""

    first_name: str | None = None
    last_name: str | None = None
    organization_name: str | None = None
    email: str | None = None
    phone: str | None = None


class ActivityCreateDTO(msgspec.Struct, kw_only=True):
    """Activity create request DTO."""

    activity_type_id: int
    subject: str
    source_contact_id: int
    activity_date_time: str | None = None
    status_id: int = 1
    details: str | None = None


class ContributionCreateDTO(msgspec.Struct, kw_only=True):
    """Contribution create request DTO."""

    contact_id: int
    total_amount: float
    financial_type_id: int = 1
    receive_date: str | None = None
    source: str | None = None


class EventCreateDTO(msgspec.Struct, kw_only=True):
    """Event create request DTO."""

    title: str
    event_type_id: int = 1
    start_date: str
    end_date: str | None = None
    is_active: bool = True
    is_public: bool = True
    max_participants: int | None = None


# =============================================================================
# Dependencies
# =============================================================================


async def provide_showcase(civi_client: CiviClient) -> CiviShowcase:
    """Provide CiviShowcase instance."""
    return CiviShowcase(civi_client)


async def provide_generator(civi_client: CiviClient) -> SampleDataGenerator:
    """Provide SampleDataGenerator instance."""
    return SampleDataGenerator(civi_client)


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
# Controllers
# =============================================================================


class DashboardController(Controller):
    """Dashboard and utility endpoints."""

    path = "/api"
    tags = ["Dashboard"]
    signature_types = [CiviClient]
    dependencies = {
        "showcase": Provide(provide_showcase),
        "generator": Provide(provide_generator),
    }

    @get("/dashboard", summary="Get dashboard statistics")
    async def get_dashboard(
        self,
        showcase: CiviShowcase,
    ) -> Response[DashboardStatsDTO | ErrorResponseDTO]:
        """Get dashboard statistics including counts and recent items."""
        stats = await showcase.get_dashboard_stats()

        if stats.error:
            return Response(
                content=ErrorResponseDTO(error="Service unavailable", detail=stats.error),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(content=stats_to_dto(stats), status_code=HTTP_200_OK)

    @post("/sample-data", summary="Generate sample data")
    async def generate_sample_data(
        self,
        generator: SampleDataGenerator,
        data: GenerationRequestDTO,
    ) -> Response[GenerationResultDTO | ErrorResponseDTO]:
        """Generate sample CiviCRM data for testing."""
        try:
            result = await generator.generate_all(
                contacts=data.contacts,
                activities=data.activities,
                contributions=data.contributions,
                events=data.events,
            )
            status = HTTP_201_CREATED if result.total_created > 0 else HTTP_400_BAD_REQUEST
            return Response(content=generation_to_dto(result), status_code=status)
        except Exception as e:
            return Response(
                content=ErrorResponseDTO(error="Generation failed", detail=str(e)),
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ContactsController(Controller):
    """Contacts CRUD endpoints using CiviShowcase."""

    path = "/api/contacts"
    tags = ["Contacts"]
    signature_types = [CiviClient]
    dependencies = {"showcase": Provide(provide_showcase)}

    @get("/", summary="List contacts")
    async def list_contacts(
        self,
        showcase: CiviShowcase,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_type: str | None = None,
    ) -> Response[PaginatedResponseDTO | ErrorResponseDTO]:
        """List contacts with pagination and optional filtering."""
        result = await showcase.list_contacts(
            page=page,
            per_page=per_page,
            search=search,
            contact_type=contact_type,
        )

        if result.error:
            return Response(
                content=ErrorResponseDTO(error="Failed to list contacts", detail=result.error),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(content=paginated_to_dto(result), status_code=HTTP_200_OK)

    @get("/{contact_id:int}", summary="Get contact by ID")
    async def get_contact(
        self,
        showcase: CiviShowcase,
        contact_id: int,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
        """Get a single contact by ID."""
        contact = await showcase.get_contact(contact_id)

        if contact is None:
            return Response(
                content=ErrorResponseDTO(error="Contact not found"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content=contact, status_code=HTTP_200_OK)

    @post("/", summary="Create contact")
    async def create_contact(
        self,
        showcase: CiviShowcase,
        data: ContactCreateDTO,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
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
            return Response(
                content=ErrorResponseDTO(error="Failed to create contact"),
                status_code=HTTP_400_BAD_REQUEST,
            )

        return Response(content=contact, status_code=HTTP_201_CREATED)

    @put("/{contact_id:int}", summary="Update contact")
    async def update_contact(
        self,
        showcase: CiviShowcase,
        contact_id: int,
        data: ContactUpdateDTO,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
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
            return Response(
                content=ErrorResponseDTO(error="No fields to update"),
                status_code=HTTP_400_BAD_REQUEST,
            )

        contact = await showcase.update_contact(contact_id, update_data)

        if contact is None:
            return Response(
                content=ErrorResponseDTO(error="Contact not found or update failed"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content=contact, status_code=HTTP_200_OK)

    @delete("/{contact_id:int}", summary="Delete contact", status_code=HTTP_200_OK)
    async def delete_contact(
        self,
        showcase: CiviShowcase,
        contact_id: int,
    ) -> Response[dict[str, bool] | ErrorResponseDTO]:
        """Delete a contact (soft delete)."""
        success = await showcase.delete_contact(contact_id)

        if not success:
            return Response(
                content=ErrorResponseDTO(error="Contact not found or delete failed"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content={"deleted": True}, status_code=HTTP_200_OK)


class ActivitiesController(Controller):
    """Activities CRUD endpoints using CiviShowcase."""

    path = "/api/activities"
    tags = ["Activities"]
    signature_types = [CiviClient]
    dependencies = {"showcase": Provide(provide_showcase)}

    @get("/", summary="List activities")
    async def list_activities(
        self,
        showcase: CiviShowcase,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        contact_id: int | None = None,
    ) -> Response[PaginatedResponseDTO | ErrorResponseDTO]:
        """List activities with pagination and optional filtering."""
        result = await showcase.list_activities(
            page=page,
            per_page=per_page,
            search=search,
            contact_id=contact_id,
        )

        if result.error:
            return Response(
                content=ErrorResponseDTO(error="Failed to list activities", detail=result.error),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(content=paginated_to_dto(result), status_code=HTTP_200_OK)

    @get("/{activity_id:int}", summary="Get activity by ID")
    async def get_activity(
        self,
        showcase: CiviShowcase,
        activity_id: int,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
        """Get a single activity by ID."""
        activity = await showcase.get_activity(activity_id)

        if activity is None:
            return Response(
                content=ErrorResponseDTO(error="Activity not found"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content=activity, status_code=HTTP_200_OK)

    @post("/", summary="Create activity")
    async def create_activity(
        self,
        showcase: CiviShowcase,
        data: ActivityCreateDTO,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
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
            return Response(
                content=ErrorResponseDTO(error="Failed to create activity"),
                status_code=HTTP_400_BAD_REQUEST,
            )

        return Response(content=activity, status_code=HTTP_201_CREATED)

    @delete("/{activity_id:int}", summary="Delete activity", status_code=HTTP_200_OK)
    async def delete_activity(
        self,
        showcase: CiviShowcase,
        activity_id: int,
    ) -> Response[dict[str, bool] | ErrorResponseDTO]:
        """Delete an activity (soft delete)."""
        success = await showcase.delete_activity(activity_id)

        if not success:
            return Response(
                content=ErrorResponseDTO(error="Activity not found or delete failed"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content={"deleted": True}, status_code=HTTP_200_OK)


class ContributionsController(Controller):
    """Contributions CRUD endpoints using CiviShowcase."""

    path = "/api/contributions"
    tags = ["Contributions"]
    signature_types = [CiviClient]
    dependencies = {"showcase": Provide(provide_showcase)}

    @get("/", summary="List contributions")
    async def list_contributions(
        self,
        showcase: CiviShowcase,
        page: int = 1,
        per_page: int = 25,
        contact_id: int | None = None,
    ) -> Response[PaginatedResponseDTO | ErrorResponseDTO]:
        """List contributions with pagination and optional filtering."""
        result = await showcase.list_contributions(
            page=page,
            per_page=per_page,
            contact_id=contact_id,
        )

        if result.error:
            return Response(
                content=ErrorResponseDTO(error="Failed to list contributions", detail=result.error),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(content=paginated_to_dto(result), status_code=HTTP_200_OK)

    @get("/{contribution_id:int}", summary="Get contribution by ID")
    async def get_contribution(
        self,
        showcase: CiviShowcase,
        contribution_id: int,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
        """Get a single contribution by ID."""
        contribution = await showcase.get_contribution(contribution_id)

        if contribution is None:
            return Response(
                content=ErrorResponseDTO(error="Contribution not found"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content=contribution, status_code=HTTP_200_OK)

    @post("/", summary="Create contribution")
    async def create_contribution(
        self,
        showcase: CiviShowcase,
        data: ContributionCreateDTO,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
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
            return Response(
                content=ErrorResponseDTO(error="Failed to create contribution"),
                status_code=HTTP_400_BAD_REQUEST,
            )

        return Response(content=contribution, status_code=HTTP_201_CREATED)


class EventsController(Controller):
    """Events CRUD endpoints using CiviShowcase."""

    path = "/api/events"
    tags = ["Events"]
    signature_types = [CiviClient]
    dependencies = {"showcase": Provide(provide_showcase)}

    @get("/", summary="List events")
    async def list_events(
        self,
        showcase: CiviShowcase,
        page: int = 1,
        per_page: int = 25,
        search: str | None = None,
        active_only: bool = True,
    ) -> Response[PaginatedResponseDTO | ErrorResponseDTO]:
        """List events with pagination and optional filtering."""
        result = await showcase.list_events(
            page=page,
            per_page=per_page,
            search=search,
            active_only=active_only,
        )

        if result.error:
            return Response(
                content=ErrorResponseDTO(error="Failed to list events", detail=result.error),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(content=paginated_to_dto(result), status_code=HTTP_200_OK)

    @get("/{event_id:int}", summary="Get event by ID")
    async def get_event(
        self,
        showcase: CiviShowcase,
        event_id: int,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
        """Get a single event by ID."""
        event = await showcase.get_event(event_id)

        if event is None:
            return Response(
                content=ErrorResponseDTO(error="Event not found"),
                status_code=HTTP_404_NOT_FOUND,
            )

        return Response(content=event, status_code=HTTP_200_OK)

    @post("/", summary="Create event")
    async def create_event(
        self,
        showcase: CiviShowcase,
        data: EventCreateDTO,
    ) -> Response[dict[str, Any] | ErrorResponseDTO]:
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
            return Response(
                content=ErrorResponseDTO(error="Failed to create event"),
                status_code=HTTP_400_BAD_REQUEST,
            )

        return Response(content=event, status_code=HTTP_201_CREATED)


# =============================================================================
# Views Controller (Template-based UI)
# =============================================================================


class ViewsController(Controller):
    """Template-based UI views matching Django example."""

    path = "/"
    tags = ["Views"]
    include_in_schema = False
    signature_types = [CiviClient]
    dependencies = {
        "showcase": Provide(provide_showcase),
        "generator": Provide(provide_generator),
    }

    @get("/", name="index")
    async def dashboard(self, request: Request, showcase: CiviShowcase) -> Template:
        """Dashboard view with stats and recent items."""
        stats = await showcase.get_dashboard_stats()
        return Template(
            template_name="dashboard.html",
            context={"request": request, "stats": stats},
        )

    @get("/contacts", name="contact_list")
    async def contact_list(
        self,
        request: Request,
        showcase: CiviShowcase,
        page: int = 1,
        q: str | None = None,
        type: str | None = None,
    ) -> Template:
        """Contact list view with search and filtering."""
        result = await showcase.list_contacts(page=page, per_page=25, search=q, contact_type=type)
        return Template(
            template_name="contacts/list.html",
            context={
                "request": request,
                "title": "Contacts",
                "result": result,
                "search": q or "",
                "contact_type": type or "",
            },
        )

    @get("/contacts/new", name="contact_create")
    async def contact_create_form(self, request: Request) -> Template:
        """Contact create form."""
        return Template(
            template_name="contacts/form.html",
            context={
                "request": request,
                "title": "Add Contact",
                "contact": None,
                "is_edit": False,
            },
        )

    @post("/contacts/new", name="contact_create_submit")
    async def contact_create_submit(
        self,
        request: Request,
        showcase: CiviShowcase,
        data: ContactCreateDTO,
    ) -> Response[Any]:
        """Handle contact create form submission."""
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
        if contact:
            from litestar.response import Redirect

            return Redirect(path=f"/contacts/{contact['id']}")
        return Template(
            template_name="contacts/form.html",
            context={
                "request": request,
                "title": "Add Contact",
                "contact": None,
                "is_edit": False,
                "error": "Failed to create contact",
            },
        )

    @get("/contacts/{contact_id:int}", name="contact_detail")
    async def contact_detail(self, request: Request, showcase: CiviShowcase, contact_id: int) -> Template:
        """Contact detail view."""
        contact = await showcase.get_contact(contact_id)
        if not contact:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Contact not found",
                },
            )

        activities = await showcase.list_activities(page=1, per_page=5, contact_id=contact_id)
        contributions = await showcase.list_contributions(page=1, per_page=5, contact_id=contact_id)

        return Template(
            template_name="contacts/detail.html",
            context={
                "request": request,
                "title": contact.get("display_name", "Contact"),
                "contact": contact,
                "activities": activities,
                "contributions": contributions,
            },
        )

    @get("/contacts/{contact_id:int}/edit", name="contact_edit")
    async def contact_edit_form(self, request: Request, showcase: CiviShowcase, contact_id: int) -> Template:
        """Contact edit form."""
        contact = await showcase.get_contact(contact_id)
        if not contact:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Contact not found",
                },
            )
        return Template(
            template_name="contacts/form.html",
            context={
                "request": request,
                "title": f"Edit {contact.get('display_name', 'Contact')}",
                "contact": contact,
                "is_edit": True,
            },
        )

    @get("/contacts/{contact_id:int}/delete", name="contact_delete")
    async def contact_delete_confirm(self, request: Request, showcase: CiviShowcase, contact_id: int) -> Template:
        """Contact delete confirmation page."""
        contact = await showcase.get_contact(contact_id)
        if not contact:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Contact not found",
                },
            )
        return Template(
            template_name="contacts/delete.html",
            context={
                "request": request,
                "title": f"Delete {contact.get('display_name', 'Contact')}",
                "contact": contact,
            },
        )

    @post("/contacts/{contact_id:int}/delete", name="contact_delete_submit")
    async def contact_delete_submit(self, request: Request, showcase: CiviShowcase, contact_id: int) -> Response[Any]:
        """Handle contact delete."""
        from litestar.response import Redirect

        await showcase.delete_contact(contact_id)
        return Redirect(path="/contacts")

    # Activities views
    @get("/activities", name="activity_list")
    async def activity_list(
        self,
        request: Request,
        showcase: CiviShowcase,
        page: int = 1,
        q: str | None = None,
    ) -> Template:
        """Activity list view."""
        result = await showcase.list_activities(page=page, per_page=25, search=q)
        return Template(
            template_name="activities/list.html",
            context={
                "request": request,
                "title": "Activities",
                "result": result,
                "search": q or "",
            },
        )

    @get("/activities/new", name="activity_create")
    async def activity_create_form(self, request: Request, showcase: CiviShowcase) -> Template:
        """Activity create form."""
        contacts = await showcase.list_contacts(page=1, per_page=100)
        return Template(
            template_name="activities/form.html",
            context={
                "request": request,
                "title": "Add Activity",
                "activity": None,
                "is_edit": False,
                "contacts": contacts.items,
            },
        )

    @get("/activities/{activity_id:int}", name="activity_detail")
    async def activity_detail(self, request: Request, showcase: CiviShowcase, activity_id: int) -> Template:
        """Activity detail view."""
        activity = await showcase.get_activity(activity_id)
        if not activity:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Activity not found",
                },
            )
        return Template(
            template_name="activities/detail.html",
            context={
                "request": request,
                "title": activity.get("subject", "Activity"),
                "activity": activity,
            },
        )

    @get("/activities/{activity_id:int}/delete", name="activity_delete")
    async def activity_delete_confirm(self, request: Request, showcase: CiviShowcase, activity_id: int) -> Template:
        """Activity delete confirmation."""
        activity = await showcase.get_activity(activity_id)
        if not activity:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Activity not found",
                },
            )
        return Template(
            template_name="activities/delete.html",
            context={
                "request": request,
                "title": "Delete Activity",
                "activity": activity,
            },
        )

    @post("/activities/{activity_id:int}/delete", name="activity_delete_submit")
    async def activity_delete_submit(self, request: Request, showcase: CiviShowcase, activity_id: int) -> Response[Any]:
        """Handle activity delete."""
        from litestar.response import Redirect

        await showcase.delete_activity(activity_id)
        return Redirect(path="/activities")

    # Contributions views
    @get("/contributions", name="contribution_list")
    async def contribution_list(self, request: Request, showcase: CiviShowcase, page: int = 1) -> Template:
        """Contribution list view."""
        result = await showcase.list_contributions(page=page, per_page=25)
        return Template(
            template_name="contributions/list.html",
            context={
                "request": request,
                "title": "Contributions",
                "result": result,
            },
        )

    @get("/contributions/new", name="contribution_create")
    async def contribution_create_form(self, request: Request, showcase: CiviShowcase) -> Template:
        """Contribution create form."""
        contacts = await showcase.list_contacts(page=1, per_page=100)
        return Template(
            template_name="contributions/form.html",
            context={
                "request": request,
                "title": "Record Contribution",
                "contribution": None,
                "is_edit": False,
                "contacts": contacts.items,
            },
        )

    @get("/contributions/{contribution_id:int}", name="contribution_detail")
    async def contribution_detail(self, request: Request, showcase: CiviShowcase, contribution_id: int) -> Template:
        """Contribution detail view."""
        contribution = await showcase.get_contribution(contribution_id)
        if not contribution:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Contribution not found",
                },
            )
        return Template(
            template_name="contributions/detail.html",
            context={
                "request": request,
                "title": f"Contribution #{contribution_id}",
                "contribution": contribution,
            },
        )

    # Events views
    @get("/events", name="event_list")
    async def event_list(
        self,
        request: Request,
        showcase: CiviShowcase,
        page: int = 1,
        q: str | None = None,
    ) -> Template:
        """Event list view."""
        result = await showcase.list_events(page=page, per_page=25, search=q)
        return Template(
            template_name="events/list.html",
            context={
                "request": request,
                "title": "Events",
                "result": result,
                "search": q or "",
            },
        )

    @get("/events/new", name="event_create")
    async def event_create_form(self, request: Request) -> Template:
        """Event create form."""
        return Template(
            template_name="events/form.html",
            context={
                "request": request,
                "title": "Create Event",
                "event": None,
                "is_edit": False,
            },
        )

    @get("/events/{event_id:int}", name="event_detail")
    async def event_detail(self, request: Request, showcase: CiviShowcase, event_id: int) -> Template:
        """Event detail view."""
        event = await showcase.get_event(event_id)
        if not event:
            return Template(
                template_name="error.html",
                context={
                    "request": request,
                    "title": "Not Found",
                    "message": "Event not found",
                },
            )
        return Template(
            template_name="events/detail.html",
            context={
                "request": request,
                "title": event.get("title", "Event"),
                "event": event,
            },
        )

    # Generate sample data
    @get("/generate-data", name="generate_data")
    async def generate_data_form(self, request: Request) -> Template:
        """Sample data generation form."""
        return Template(
            template_name="sample_data.html",
            context={
                "request": request,
                "title": "Generate Sample Data",
                "generated": False,
            },
        )

    @post("/generate-data", name="generate_data_submit")
    async def generate_data_submit(
        self,
        request: Request,
        generator: SampleDataGenerator,
    ) -> Template:
        """Handle sample data generation from form submission."""
        # Parse form data
        form_data = await request.form()
        contacts = int(form_data.get("contacts", 10))
        activities = int(form_data.get("activities", 20))
        contributions = int(form_data.get("contributions", 15))
        events = int(form_data.get("events", 5))

        result = await generator.generate_all(
            contacts=contacts,
            activities=activities,
            contributions=contributions,
            events=events,
        )
        return Template(
            template_name="sample_data.html",
            context={
                "request": request,
                "title": "Generate Sample Data",
                "generated": True,
                "result": result,
            },
        )


@get("/favicon.ico", status_code=HTTP_204_NO_CONTENT, include_in_schema=False)
async def favicon() -> None:
    """Return empty response for favicon requests to prevent 404 spam."""
    return


# =============================================================================
# Application Setup
# =============================================================================


# Configure the CiviPlugin
# Auto-generated routes at /api/civi/{Entity} + custom showcase routes at /api/{entity}
plugin_config = CiviPluginConfig(
    api_prefix="/api/civi",  # Auto-generated CRUD routes
    enable_health_check=True,
    health_check_path="/health/civi",
    include_entities=["Contact", "Activity", "Contribution", "Event"],
    openapi_tags=["CiviCRM Auto-Generated"],
    debug=True,
    # Enable Web UI for API exploration
    enable_webui=True,
    webui_path="/explorer",
    webui_config=WebUIConfig(
        title="CiviCRM Explorer",
        theme="auto",
        enable_playground=True,
    ),
)

# Template configuration - include both shared templates and WebUI templates
# Create a custom Jinja2 environment with the get_attr filter
_jinja_env = create_jinja_env([SHARED_TEMPLATES_DIR, WEBUI_TEMPLATES_DIR])

# Create engine from the shared environment
_template_engine = JinjaTemplateEngine.from_environment(_jinja_env)

app = Litestar(
    route_handlers=[
        favicon,
        ViewsController,
        DashboardController,
        ContactsController,
        ActivitiesController,
        ContributionsController,
        EventsController,
    ],
    plugins=[
        CiviPlugin(plugin_config),
    ],
    signature_types=[CiviClient],
    template_config=TemplateConfig(
        instance=_template_engine,
    ),
    openapi_config=OpenAPIConfig(
        title="CiviCRM Litestar Demo",
        version="1.0.0",
        description=(
            "Demo API showing civi-py Litestar integration with CiviShowcase.\n\n"
            "## Features\n"
            "- Dashboard statistics and recent items\n"
            "- Full CRUD for contacts, activities, contributions, events\n"
            "- Sample data generation for testing\n"
            "- Proper error handling with HTTP status codes\n\n"
            "## Health Check\n"
            "`GET /health/civi` - Check CiviCRM API connectivity"
        ),
        path="/docs",
        render_plugins=[
            ScalarRenderPlugin(),  # /docs/scalar
            SwaggerRenderPlugin(),  # /docs/swagger
        ],
    ),
    debug=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", reload=True, port=8001, lifespan="on")
