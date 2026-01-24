"""Views for CiviCRM demo application.

Demonstrates using civi-py with Django views using the shared showcase module.
Both sync and async views are supported.

The views use shared Jinja2 templates from examples/shared/templates/ which
require a `request` object with `request.url.path` for navigation highlighting.
We wrap the Django request to provide this Litestar-compatible interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from examples.shared import CiviShowcase, SampleDataGenerator, SyncCiviShowcase
from examples.shared.jinja_env import DjangoRequest

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient, SyncCiviClient


# =============================================================================
# Helper Functions
# =============================================================================


def jinja_render(
    request: HttpRequest,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> HttpResponse:
    """Render a Jinja2 template with a Litestar-compatible request wrapper.

    The shared templates expect `request.url.path` (Litestar style) for
    navigation highlighting. This helper wraps the Django request to provide
    that interface.

    Args:
        request: Django HttpRequest object.
        template_name: Name of the template to render.
        context: Context dictionary for the template.

    Returns:
        HttpResponse with rendered template.
    """
    if context is None:
        context = {}

    # Wrap the Django request to provide request.url.path
    context["request"] = DjangoRequest(request)

    return render(request, template_name, context)


def get_page(request: HttpRequest) -> int:
    """Get page number from request, defaulting to 1."""
    try:
        page = int(request.GET.get("page", "1"))
        return max(1, page)
    except (TypeError, ValueError):
        return 1


def get_search(request: HttpRequest) -> str | None:
    """Get search query from request."""
    search = request.GET.get("q", "").strip()
    return search if search else None


def get_per_page(request: HttpRequest, default: int = 25) -> int:
    """Get items per page from request."""
    try:
        per_page = int(request.GET.get("per_page", str(default)))
        return min(max(1, per_page), 100)  # Clamp between 1 and 100
    except (TypeError, ValueError):
        return default


# =============================================================================
# Dashboard / Home Views
# =============================================================================


def index(request: HttpRequest) -> HttpResponse:
    """Dashboard home page with overview stats."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)
    stats = showcase.get_dashboard_stats()

    return jinja_render(
        request,
        "dashboard.html",
        {
            "title": "CiviCRM Dashboard",
            "stats": stats,
        },
    )


async def index_async(request: HttpRequest) -> HttpResponse:
    """Dashboard home page (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)
    stats = await showcase.get_dashboard_stats()

    return jinja_render(
        request,
        "dashboard.html",
        {
            "title": "CiviCRM Dashboard",
            "stats": stats,
        },
    )


# =============================================================================
# Contact Views (Sync)
# =============================================================================


def contact_list(request: HttpRequest) -> HttpResponse:
    """List CiviCRM contacts with pagination and search."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    contact_type = request.GET.get("type")
    per_page = get_per_page(request)

    result = showcase.list_contacts(
        page=page,
        per_page=per_page,
        search=search,
        contact_type=contact_type,
    )

    return jinja_render(
        request,
        "contacts/list.html",
        {
            "title": "Contacts",
            "result": result,
            "search": search or "",
            "contact_type": contact_type or "",
            "per_page": per_page,
        },
    )


def contact_detail(request: HttpRequest, contact_id: int) -> HttpResponse:
    """Show CiviCRM contact detail."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    contact = showcase.get_contact(contact_id)
    if not contact:
        raise Http404("Contact not found")

    # Get related activities and contributions
    activities = showcase.list_activities(contact_id=contact_id, per_page=5)
    contributions = showcase.list_contributions(contact_id=contact_id, per_page=5)

    return jinja_render(
        request,
        "contacts/detail.html",
        {
            "title": contact.get("display_name", "Contact"),
            "contact": contact,
            "activities": activities,
            "contributions": contributions,
        },
    )


@require_http_methods(["GET", "POST"])
def contact_create(request: HttpRequest) -> HttpResponse:
    """Create a new contact."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    if request.method == "POST":
        data = {
            "contact_type": request.POST.get("contact_type", "Individual"),
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "organization_name": request.POST.get("organization_name", "").strip(),
            "household_name": request.POST.get("household_name", "").strip(),
        }

        # Add email if provided
        email = request.POST.get("email", "").strip()
        if email:
            data["email_primary.email"] = email

        # Add phone if provided
        phone = request.POST.get("phone", "").strip()
        if phone:
            data["phone_primary.phone"] = phone

        # Remove empty fields
        data = {k: v for k, v in data.items() if v}

        contact = showcase.create_contact(data)
        if contact:
            return redirect("contact_detail", contact_id=contact["id"])

        return jinja_render(
            request,
            "contacts/form.html",
            {
                "title": "Create Contact",
                "error": "Failed to create contact. Please try again.",
                "form_data": request.POST,
            },
        )

    return jinja_render(
        request,
        "contacts/form.html",
        {
            "title": "Create Contact",
        },
    )


@require_http_methods(["GET", "POST"])
def contact_edit(request: HttpRequest, contact_id: int) -> HttpResponse:
    """Edit an existing contact."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    contact = showcase.get_contact(contact_id)
    if not contact:
        raise Http404("Contact not found")

    if request.method == "POST":
        data = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "organization_name": request.POST.get("organization_name", "").strip(),
            "household_name": request.POST.get("household_name", "").strip(),
        }

        # Remove empty fields
        data = {k: v for k, v in data.items() if v}

        updated = showcase.update_contact(contact_id, data)
        if updated:
            return redirect("contact_detail", contact_id=contact_id)

        return jinja_render(
            request,
            "contacts/form.html",
            {
                "title": "Edit Contact",
                "contact": contact,
                "error": "Failed to update contact. Please try again.",
            },
        )

    return jinja_render(
        request,
        "contacts/form.html",
        {
            "title": "Edit Contact",
            "contact": contact,
            "editing": True,
        },
    )


@require_http_methods(["GET", "POST"])
def contact_delete(request: HttpRequest, contact_id: int) -> HttpResponse:
    """Delete a contact with confirmation."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    contact = showcase.get_contact(contact_id)
    if not contact:
        raise Http404("Contact not found")

    if request.method == "POST":
        if showcase.delete_contact(contact_id):
            return redirect("contact_list")

        return jinja_render(
            request,
            "contacts/delete.html",
            {
                "title": "Delete Contact",
                "contact": contact,
                "error": "Failed to delete contact. Please try again.",
            },
        )

    return jinja_render(
        request,
        "contacts/delete.html",
        {
            "title": "Delete Contact",
            "contact": contact,
        },
    )


# =============================================================================
# Activity Views (Sync)
# =============================================================================


def activity_list(request: HttpRequest) -> HttpResponse:
    """List activities with pagination and search."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request)

    result = showcase.list_activities(
        page=page,
        per_page=per_page,
        search=search,
    )

    return jinja_render(
        request,
        "activities/list.html",
        {
            "title": "Activities",
            "result": result,
            "search": search or "",
            "per_page": per_page,
        },
    )


def activity_detail(request: HttpRequest, activity_id: int) -> HttpResponse:
    """Show activity detail."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    activity = showcase.get_activity(activity_id)
    if not activity:
        raise Http404("Activity not found")

    return jinja_render(
        request,
        "activities/detail.html",
        {
            "title": activity.get("subject", "Activity"),
            "activity": activity,
        },
    )


@require_http_methods(["GET", "POST"])
def activity_create(request: HttpRequest) -> HttpResponse:
    """Create a new activity."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    if request.method == "POST":
        data = {
            "activity_type_id": int(request.POST.get("activity_type_id", "1")),
            "subject": request.POST.get("subject", "").strip(),
            "status_id": int(request.POST.get("status_id", "1")),
        }

        # Add source contact if provided
        source_contact_id = request.POST.get("source_contact_id", "").strip()
        if source_contact_id:
            data["source_contact_id"] = int(source_contact_id)

        # Add details if provided
        details = request.POST.get("details", "").strip()
        if details:
            data["details"] = details

        activity = showcase.create_activity(data)
        if activity:
            return redirect("activity_detail", activity_id=activity["id"])

        return jinja_render(
            request,
            "activities/form.html",
            {
                "title": "Create Activity",
                "error": "Failed to create activity. Please try again.",
                "form_data": request.POST,
            },
        )

    return jinja_render(
        request,
        "activities/form.html",
        {
            "title": "Create Activity",
        },
    )


@require_http_methods(["GET", "POST"])
def activity_delete(request: HttpRequest, activity_id: int) -> HttpResponse:
    """Delete an activity with confirmation."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    activity = showcase.get_activity(activity_id)
    if not activity:
        raise Http404("Activity not found")

    if request.method == "POST":
        if showcase.delete_activity(activity_id):
            return redirect("activity_list")

        return jinja_render(
            request,
            "activities/delete.html",
            {
                "title": "Delete Activity",
                "activity": activity,
                "error": "Failed to delete activity. Please try again.",
            },
        )

    return jinja_render(
        request,
        "activities/delete.html",
        {
            "title": "Delete Activity",
            "activity": activity,
        },
    )


# =============================================================================
# Contribution Views (Sync)
# =============================================================================


def contribution_list(request: HttpRequest) -> HttpResponse:
    """List contributions with pagination."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    per_page = get_per_page(request)

    result = showcase.list_contributions(
        page=page,
        per_page=per_page,
    )

    return jinja_render(
        request,
        "contributions/list.html",
        {
            "title": "Contributions",
            "result": result,
            "per_page": per_page,
        },
    )


def contribution_detail(request: HttpRequest, contribution_id: int) -> HttpResponse:
    """Show contribution detail."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    contribution = showcase.get_contribution(contribution_id)
    if not contribution:
        raise Http404("Contribution not found")

    return jinja_render(
        request,
        "contributions/detail.html",
        {
            "title": f"Contribution #{contribution.get('id')}",
            "contribution": contribution,
        },
    )


@require_http_methods(["GET", "POST"])
def contribution_create(request: HttpRequest) -> HttpResponse:
    """Create a new contribution."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    if request.method == "POST":
        data = {
            "financial_type_id": int(request.POST.get("financial_type_id", "1")),
            "total_amount": float(request.POST.get("total_amount", "0")),
            "contribution_status_id": int(request.POST.get("contribution_status_id", "1")),
        }

        contact_id = request.POST.get("contact_id", "").strip()
        if contact_id:
            data["contact_id"] = int(contact_id)

        source = request.POST.get("source", "").strip()
        if source:
            data["source"] = source

        contribution = showcase.create_contribution(data)
        if contribution:
            return redirect("contribution_detail", contribution_id=contribution["id"])

        return jinja_render(
            request,
            "contributions/form.html",
            {
                "title": "Record Contribution",
                "error": "Failed to record contribution. Please try again.",
                "form_data": request.POST,
            },
        )

    return jinja_render(
        request,
        "contributions/form.html",
        {
            "title": "Record Contribution",
        },
    )


# =============================================================================
# Event Views (Sync)
# =============================================================================


def event_list(request: HttpRequest) -> HttpResponse:
    """List events with pagination and search."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request)
    active_only = request.GET.get("active", "true").lower() == "true"

    result = showcase.list_events(
        page=page,
        per_page=per_page,
        search=search,
        active_only=active_only,
    )

    return jinja_render(
        request,
        "events/list.html",
        {
            "title": "Events",
            "result": result,
            "search": search or "",
            "per_page": per_page,
            "active_only": active_only,
        },
    )


def event_detail(request: HttpRequest, event_id: int) -> HttpResponse:
    """Show event detail."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    event = showcase.get_event(event_id)
    if not event:
        raise Http404("Event not found")

    return jinja_render(
        request,
        "events/detail.html",
        {
            "title": event.get("title", "Event"),
            "event": event,
        },
    )


@require_http_methods(["GET", "POST"])
def event_create(request: HttpRequest) -> HttpResponse:
    """Create a new event."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    if request.method == "POST":
        data = {
            "title": request.POST.get("title", "").strip(),
            "event_type_id": int(request.POST.get("event_type_id", "1")),
            "start_date": request.POST.get("start_date", "").strip(),
            "is_active": request.POST.get("is_active") == "on",
            "is_public": request.POST.get("is_public") == "on",
        }

        end_date = request.POST.get("end_date", "").strip()
        if end_date:
            data["end_date"] = end_date

        max_participants = request.POST.get("max_participants", "").strip()
        if max_participants:
            data["max_participants"] = int(max_participants)

        summary = request.POST.get("summary", "").strip()
        if summary:
            data["summary"] = summary

        event = showcase.create_event(data)
        if event:
            return redirect("event_detail", event_id=event["id"])

        return jinja_render(
            request,
            "events/form.html",
            {
                "title": "Create Event",
                "error": "Failed to create event. Please try again.",
                "form_data": request.POST,
            },
        )

    return jinja_render(
        request,
        "events/form.html",
        {
            "title": "Create Event",
        },
    )


# =============================================================================
# Sample Data Generation
# =============================================================================


@require_http_methods(["GET", "POST"])
def generate_sample_data(request: HttpRequest) -> HttpResponse:
    """Generate sample CiviCRM data for demonstration."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]

    if request.method == "POST":
        generator = SampleDataGenerator(client)

        contacts = int(request.POST.get("contacts", "10"))
        activities = int(request.POST.get("activities", "20"))
        contributions = int(request.POST.get("contributions", "15"))
        events = int(request.POST.get("events", "5"))

        result = generator.generate_all_sync(
            contacts=contacts,
            activities=activities,
            contributions=contributions,
            events=events,
        )

        return jinja_render(
            request,
            "sample_data.html",
            {
                "title": "Generate Sample Data",
                "result": result,
                "generated": True,
            },
        )

    return jinja_render(
        request,
        "sample_data.html",
        {
            "title": "Generate Sample Data",
        },
    )


# =============================================================================
# API Endpoints (JSON)
# =============================================================================


def api_contacts(request: HttpRequest) -> JsonResponse:
    """API endpoint returning contacts as JSON."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request, default=10)

    result = showcase.list_contacts(
        page=page,
        per_page=per_page,
        search=search,
    )

    return JsonResponse(
        {
            "contacts": result.items,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "error": result.error,
        },
    )


def api_activities(request: HttpRequest) -> JsonResponse:
    """API endpoint returning activities as JSON."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request, default=10)

    result = showcase.list_activities(
        page=page,
        per_page=per_page,
        search=search,
    )

    return JsonResponse(
        {
            "activities": result.items,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "error": result.error,
        },
    )


def api_contributions(request: HttpRequest) -> JsonResponse:
    """API endpoint returning contributions as JSON."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    per_page = get_per_page(request, default=10)

    result = showcase.list_contributions(
        page=page,
        per_page=per_page,
    )

    return JsonResponse(
        {
            "contributions": result.items,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "error": result.error,
        },
    )


def api_events(request: HttpRequest) -> JsonResponse:
    """API endpoint returning events as JSON."""
    client: SyncCiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = SyncCiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request, default=10)

    result = showcase.list_events(
        page=page,
        per_page=per_page,
        search=search,
    )

    return JsonResponse(
        {
            "events": result.items,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "error": result.error,
        },
    )


# =============================================================================
# Async Views (ASGI)
# =============================================================================


async def contact_list_async(request: HttpRequest) -> HttpResponse:
    """List contacts (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    contact_type = request.GET.get("type")
    per_page = get_per_page(request)

    result = await showcase.list_contacts(
        page=page,
        per_page=per_page,
        search=search,
        contact_type=contact_type,
    )

    return jinja_render(
        request,
        "contacts/list.html",
        {
            "title": "Contacts",
            "result": result,
            "search": search or "",
            "contact_type": contact_type or "",
            "per_page": per_page,
        },
    )


async def contact_detail_async(request: HttpRequest, contact_id: int) -> HttpResponse:
    """Show contact detail (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    contact = await showcase.get_contact(contact_id)
    if not contact:
        raise Http404("Contact not found")

    activities = await showcase.list_activities(contact_id=contact_id, per_page=5)
    contributions = await showcase.list_contributions(contact_id=contact_id, per_page=5)

    return jinja_render(
        request,
        "contacts/detail.html",
        {
            "title": contact.get("display_name", "Contact"),
            "contact": contact,
            "activities": activities,
            "contributions": contributions,
        },
    )


async def activity_list_async(request: HttpRequest) -> HttpResponse:
    """List activities (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request)

    result = await showcase.list_activities(
        page=page,
        per_page=per_page,
        search=search,
    )

    return jinja_render(
        request,
        "activities/list.html",
        {
            "title": "Activities",
            "result": result,
            "search": search or "",
            "per_page": per_page,
        },
    )


async def contribution_list_async(request: HttpRequest) -> HttpResponse:
    """List contributions (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    page = get_page(request)
    per_page = get_per_page(request)

    result = await showcase.list_contributions(
        page=page,
        per_page=per_page,
    )

    return jinja_render(
        request,
        "contributions/list.html",
        {
            "title": "Contributions",
            "result": result,
            "per_page": per_page,
        },
    )


async def event_list_async(request: HttpRequest) -> HttpResponse:
    """List events (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request)
    active_only = request.GET.get("active", "true").lower() == "true"

    result = await showcase.list_events(
        page=page,
        per_page=per_page,
        search=search,
        active_only=active_only,
    )

    return jinja_render(
        request,
        "events/list.html",
        {
            "title": "Events",
            "result": result,
            "search": search or "",
            "per_page": per_page,
            "active_only": active_only,
        },
    )


async def api_contacts_async(request: HttpRequest) -> JsonResponse:
    """API endpoint for contacts (async version)."""
    client: CiviClient = request.civi_client  # type: ignore[attr-defined]
    showcase = CiviShowcase(client)

    page = get_page(request)
    search = get_search(request)
    per_page = get_per_page(request, default=10)

    result = await showcase.list_contacts(
        page=page,
        per_page=per_page,
        search=search,
    )

    return JsonResponse(
        {
            "contacts": result.items,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "error": result.error,
        },
    )
