"""Flask CiviCRM demo application.

Demonstrates civi-py Flask integration using the shared showcase module:
- CiviFlask extension for seamless CiviCRM API integration
- SyncCiviShowcase service for high-level operations
- Full CRUD for contacts, activities, contributions, events
- Dashboard statistics endpoint
- Sample data generation endpoint
- Proper error handling with HTTP status codes

Run from project root:
    # Start CiviCRM infrastructure (if needed)
    make infra-up
    make infra-install
    make infra-setup

    # Run the Flask example
    make example-flask

Then visit:
    - http://localhost:8002/             - Dashboard
    - http://localhost:8002/contacts     - Contacts list
    - http://localhost:8002/health       - Health check
    - http://localhost:8002/api/contacts - Contacts API (JSON)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv
from examples.shared import SampleDataGenerator, SyncCiviShowcase, create_jinja_env
from examples.shared.jinja_env import TEMPLATES_DIR as SHARED_TEMPLATES_DIR
from flask import Flask, jsonify, redirect, render_template, request, url_for

from civicrm_py.contrib.flask import CiviFlask, get_civi_client

if TYPE_CHECKING:
    from flask import Response
    from werkzeug.wrappers import Response as WerkzeugResponse

# Load .env file from project root (auto-discovers parent directories)
load_dotenv()


# =============================================================================
# Helper Functions
# =============================================================================


def _get_page() -> int:
    """Get page number from request, defaulting to 1."""
    try:
        page = int(request.args.get("page", "1"))
        return max(1, page)
    except (TypeError, ValueError):
        return 1


def _get_search() -> str | None:
    """Get search query from request."""
    search = request.args.get("q", "").strip()
    return search if search else None


def _get_per_page(default: int = 25) -> int:
    """Get items per page from request."""
    try:
        per_page = int(request.args.get("per_page", str(default)))
        return min(max(1, per_page), 100)  # Clamp between 1 and 100
    except (TypeError, ValueError):
        return default


# =============================================================================
# Application Factory
# =============================================================================


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application.

    Uses the application factory pattern for better testability and flexibility.

    Args:
        config: Optional configuration dictionary to override defaults.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__, template_folder=str(SHARED_TEMPLATES_DIR))

    # Load configuration
    _configure_app(app, config)

    # Configure Jinja2 environment with shared templates
    _configure_jinja(app)

    # Initialize CiviFlask extension
    civi = CiviFlask()
    civi.init_app(app)

    # Register routes
    _register_health_routes(app)
    _register_dashboard_routes(app)
    _register_contact_routes(app)
    _register_activity_routes(app)
    _register_contribution_routes(app)
    _register_event_routes(app)
    _register_utility_routes(app)
    _register_api_routes(app)

    return app


def _configure_app(app: Flask, config: dict[str, Any] | None = None) -> None:
    """Configure the Flask application with settings.

    Args:
        app: Flask application instance.
        config: Optional configuration overrides.
    """
    # Default configuration
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production"),
        # CiviCRM settings (loaded from environment)
        CIVI_BASE_URL=os.environ.get("CIVI_BASE_URL", "http://localhost:8080/civicrm/ajax/api4"),
        CIVI_API_KEY=os.environ.get("CIVI_API_KEY"),
        CIVI_SITE_KEY=os.environ.get("CIVI_SITE_KEY"),
        CIVI_AUTH_TYPE=os.environ.get("CIVI_AUTH_TYPE", "api_key"),
        CIVI_TIMEOUT=int(os.environ.get("CIVI_TIMEOUT", "30")),
        CIVI_VERIFY_SSL=os.environ.get("CIVI_VERIFY_SSL", "true").lower() == "true",
        CIVI_DEBUG=os.environ.get("CIVI_DEBUG", "false").lower() == "true",
    )

    # Apply any overrides
    if config:
        app.config.update(config)


def _configure_jinja(app: Flask) -> None:
    """Configure Jinja2 environment with shared templates and filters.

    Args:
        app: Flask application instance.
    """
    # Create a custom Jinja2 environment with the shared templates
    jinja_env = create_jinja_env(
        templates_dir=SHARED_TEMPLATES_DIR,
        framework="flask",
    )

    # Copy filters to Flask's Jinja environment
    app.jinja_env.filters.update(jinja_env.filters)

    # Copy globals to Flask's Jinja environment
    app.jinja_env.globals.update(jinja_env.globals)

    # Override url_for with Flask's native url_for
    app.jinja_env.globals["url_for"] = url_for

    # Set framework identifier
    app.jinja_env.globals["framework"] = "flask"


# =============================================================================
# Route Registration Functions
# =============================================================================


def _register_health_routes(app: Flask) -> None:
    """Register health check routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/health")
    def health() -> tuple[dict[str, Any], int]:
        """Health check endpoint."""
        return {"status": "healthy", "framework": "flask"}, 200


def _register_dashboard_routes(app: Flask) -> None:
    """Register dashboard routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/")
    def index() -> str:
        """Dashboard home page with overview stats."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)
        stats = showcase.get_dashboard_stats()

        return render_template(
            "dashboard.html",
            title="CiviCRM Dashboard",
            stats=stats,
        )


def _register_contact_routes(app: Flask) -> None:
    """Register contact-related routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/contacts")
    def contact_list() -> str:
        """List CiviCRM contacts with pagination and search."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        contact_type = request.args.get("type")
        per_page = _get_per_page()

        result = showcase.list_contacts(
            page=page,
            per_page=per_page,
            search=search,
            contact_type=contact_type,
        )

        return render_template(
            "contacts/list.html",
            title="Contacts",
            result=result,
            search=search or "",
            contact_type=contact_type or "",
            per_page=per_page,
        )

    @app.route("/contacts/<int:contact_id>")
    def contact_detail(contact_id: int) -> str | tuple[str, int]:
        """Show CiviCRM contact detail."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        contact = showcase.get_contact(contact_id)
        if not contact:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Contact not found",
                ),
                404,
            )

        # Get related activities and contributions
        activities = showcase.list_activities(contact_id=contact_id, per_page=5)
        contributions = showcase.list_contributions(contact_id=contact_id, per_page=5)

        return render_template(
            "contacts/detail.html",
            title=contact.get("display_name", "Contact"),
            contact=contact,
            activities=activities,
            contributions=contributions,
        )

    @app.route("/contacts/new", methods=["GET", "POST"])
    def contact_create() -> str | Response:
        """Create a new contact."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        if request.method == "POST":
            data = {
                "contact_type": request.form.get("contact_type", "Individual"),
                "first_name": request.form.get("first_name", "").strip(),
                "last_name": request.form.get("last_name", "").strip(),
                "organization_name": request.form.get("organization_name", "").strip(),
                "household_name": request.form.get("household_name", "").strip(),
            }

            # Add email if provided
            email = request.form.get("email", "").strip()
            if email:
                data["email_primary.email"] = email

            # Add phone if provided
            phone = request.form.get("phone", "").strip()
            if phone:
                data["phone_primary.phone"] = phone

            # Remove empty fields
            data = {k: v for k, v in data.items() if v}

            contact = showcase.create_contact(data)
            if contact:
                return redirect(url_for("contact_detail", contact_id=contact["id"]))

            return render_template(
                "contacts/form.html",
                title="Create Contact",
                error="Failed to create contact. Please try again.",
                form_data=request.form,
            )

        return render_template(
            "contacts/form.html",
            title="Create Contact",
        )

    @app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
    def contact_edit(contact_id: int) -> str | tuple[str, int] | Response:
        """Edit an existing contact."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        contact = showcase.get_contact(contact_id)
        if not contact:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Contact not found",
                ),
                404,
            )

        if request.method == "POST":
            data = {
                "first_name": request.form.get("first_name", "").strip(),
                "last_name": request.form.get("last_name", "").strip(),
                "organization_name": request.form.get("organization_name", "").strip(),
                "household_name": request.form.get("household_name", "").strip(),
            }

            # Remove empty fields
            data = {k: v for k, v in data.items() if v}

            updated = showcase.update_contact(contact_id, data)
            if updated:
                return redirect(url_for("contact_detail", contact_id=contact_id))

            return render_template(
                "contacts/form.html",
                title="Edit Contact",
                contact=contact,
                error="Failed to update contact. Please try again.",
            )

        return render_template(
            "contacts/form.html",
            title="Edit Contact",
            contact=contact,
            editing=True,
        )

    @app.route("/contacts/<int:contact_id>/delete", methods=["GET", "POST"])
    def contact_delete(contact_id: int) -> str | tuple[str, int] | Response:
        """Delete a contact with confirmation."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        contact = showcase.get_contact(contact_id)
        if not contact:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Contact not found",
                ),
                404,
            )

        if request.method == "POST":
            if showcase.delete_contact(contact_id):
                return redirect(url_for("contact_list"))

            return render_template(
                "contacts/delete.html",
                title="Delete Contact",
                contact=contact,
                error="Failed to delete contact. Please try again.",
            )

        return render_template(
            "contacts/delete.html",
            title="Delete Contact",
            contact=contact,
        )


def _register_activity_routes(app: Flask) -> None:
    """Register activity-related routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/activities")
    def activity_list() -> str:
        """List activities with pagination and search."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        per_page = _get_per_page()

        result = showcase.list_activities(
            page=page,
            per_page=per_page,
            search=search,
        )

        return render_template(
            "activities/list.html",
            title="Activities",
            result=result,
            search=search or "",
            per_page=per_page,
        )

    @app.route("/activities/<int:activity_id>")
    def activity_detail(activity_id: int) -> str | tuple[str, int]:
        """Show activity detail."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        activity = showcase.get_activity(activity_id)
        if not activity:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Activity not found",
                ),
                404,
            )

        return render_template(
            "activities/detail.html",
            title=activity.get("subject", "Activity"),
            activity=activity,
        )

    @app.route("/activities/new", methods=["GET", "POST"])
    def activity_create() -> str | Response:
        """Create a new activity."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        if request.method == "POST":
            data = {
                "activity_type_id": int(request.form.get("activity_type_id", "1")),
                "subject": request.form.get("subject", "").strip(),
                "status_id": int(request.form.get("status_id", "1")),
            }

            # Add source contact if provided
            source_contact_id = request.form.get("source_contact_id", "").strip()
            if source_contact_id:
                data["source_contact_id"] = int(source_contact_id)

            # Add details if provided
            details = request.form.get("details", "").strip()
            if details:
                data["details"] = details

            activity = showcase.create_activity(data)
            if activity:
                return redirect(url_for("activity_detail", activity_id=activity["id"]))

            return render_template(
                "activities/form.html",
                title="Create Activity",
                error="Failed to create activity. Please try again.",
                form_data=request.form,
            )

        return render_template(
            "activities/form.html",
            title="Create Activity",
        )

    @app.route("/activities/<int:activity_id>/delete", methods=["GET", "POST"])
    def activity_delete(activity_id: int) -> str | tuple[str, int] | Response:
        """Delete an activity with confirmation."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        activity = showcase.get_activity(activity_id)
        if not activity:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Activity not found",
                ),
                404,
            )

        if request.method == "POST":
            if showcase.delete_activity(activity_id):
                return redirect(url_for("activity_list"))

            return render_template(
                "activities/delete.html",
                title="Delete Activity",
                activity=activity,
                error="Failed to delete activity. Please try again.",
            )

        return render_template(
            "activities/delete.html",
            title="Delete Activity",
            activity=activity,
        )


def _register_contribution_routes(app: Flask) -> None:
    """Register contribution-related routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/contributions")
    def contribution_list() -> str:
        """List contributions with pagination."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        per_page = _get_per_page()

        result = showcase.list_contributions(
            page=page,
            per_page=per_page,
        )

        return render_template(
            "contributions/list.html",
            title="Contributions",
            result=result,
            per_page=per_page,
        )

    @app.route("/contributions/<int:contribution_id>")
    def contribution_detail(contribution_id: int) -> str | tuple[str, int]:
        """Show contribution detail."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        contribution = showcase.get_contribution(contribution_id)
        if not contribution:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Contribution not found",
                ),
                404,
            )

        return render_template(
            "contributions/detail.html",
            title=f"Contribution #{contribution.get('id')}",
            contribution=contribution,
        )

    @app.route("/contributions/new", methods=["GET", "POST"])
    def contribution_create() -> str | Response:
        """Create a new contribution."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        if request.method == "POST":
            data = {
                "financial_type_id": int(request.form.get("financial_type_id", "1")),
                "total_amount": float(request.form.get("total_amount", "0")),
                "contribution_status_id": int(request.form.get("contribution_status_id", "1")),
            }

            contact_id = request.form.get("contact_id", "").strip()
            if contact_id:
                data["contact_id"] = int(contact_id)

            source = request.form.get("source", "").strip()
            if source:
                data["source"] = source

            contribution = showcase.create_contribution(data)
            if contribution:
                return redirect(url_for("contribution_detail", contribution_id=contribution["id"]))

            return render_template(
                "contributions/form.html",
                title="Record Contribution",
                error="Failed to record contribution. Please try again.",
                form_data=request.form,
            )

        return render_template(
            "contributions/form.html",
            title="Record Contribution",
        )


def _register_event_routes(app: Flask) -> None:
    """Register event-related routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/events")
    def event_list() -> str:
        """List events with pagination and search."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        per_page = _get_per_page()
        active_only = request.args.get("active", "true").lower() == "true"

        result = showcase.list_events(
            page=page,
            per_page=per_page,
            search=search,
            active_only=active_only,
        )

        return render_template(
            "events/list.html",
            title="Events",
            result=result,
            search=search or "",
            per_page=per_page,
            active_only=active_only,
        )

    @app.route("/events/<int:event_id>")
    def event_detail(event_id: int) -> str | tuple[str, int]:
        """Show event detail."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        event = showcase.get_event(event_id)
        if not event:
            return (
                render_template(
                    "error.html",
                    title="Not Found",
                    message="Event not found",
                ),
                404,
            )

        return render_template(
            "events/detail.html",
            title=event.get("title", "Event"),
            event=event,
        )

    @app.route("/events/new", methods=["GET", "POST"])
    def event_create() -> str | Response:
        """Create a new event."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        if request.method == "POST":
            data = {
                "title": request.form.get("title", "").strip(),
                "event_type_id": int(request.form.get("event_type_id", "1")),
                "start_date": request.form.get("start_date", "").strip(),
                "is_active": request.form.get("is_active") == "on",
                "is_public": request.form.get("is_public") == "on",
            }

            end_date = request.form.get("end_date", "").strip()
            if end_date:
                data["end_date"] = end_date

            max_participants = request.form.get("max_participants", "").strip()
            if max_participants:
                data["max_participants"] = int(max_participants)

            summary = request.form.get("summary", "").strip()
            if summary:
                data["summary"] = summary

            event = showcase.create_event(data)
            if event:
                return redirect(url_for("event_detail", event_id=event["id"]))

            return render_template(
                "events/form.html",
                title="Create Event",
                error="Failed to create event. Please try again.",
                form_data=request.form,
            )

        return render_template(
            "events/form.html",
            title="Create Event",
        )


def _register_utility_routes(app: Flask) -> None:
    """Register utility routes (sample data generation).

    Args:
        app: Flask application instance.
    """

    @app.route("/generate-data", methods=["GET", "POST"])
    def generate_sample_data() -> str:
        """Generate sample CiviCRM data for demonstration."""
        client = get_civi_client()

        if request.method == "POST":
            generator = SampleDataGenerator(client)

            contacts = int(request.form.get("contacts", "10"))
            activities = int(request.form.get("activities", "20"))
            contributions = int(request.form.get("contributions", "15"))
            events = int(request.form.get("events", "5"))

            result = generator.generate_all_sync(
                contacts=contacts,
                activities=activities,
                contributions=contributions,
                events=events,
            )

            return render_template(
                "sample_data.html",
                title="Generate Sample Data",
                result=result,
                generated=True,
            )

        return render_template(
            "sample_data.html",
            title="Generate Sample Data",
        )


def _register_api_routes(app: Flask) -> None:
    """Register JSON API routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/api/contacts")
    def api_contacts() -> WerkzeugResponse:
        """API endpoint returning contacts as JSON."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        per_page = _get_per_page(default=10)

        result = showcase.list_contacts(
            page=page,
            per_page=per_page,
            search=search,
        )

        return jsonify(
            {
                "contacts": result.items,
                "total": result.total,
                "page": result.page,
                "pages": result.pages,
                "error": result.error,
            }
        )

    @app.route("/api/activities")
    def api_activities() -> WerkzeugResponse:
        """API endpoint returning activities as JSON."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        per_page = _get_per_page(default=10)

        result = showcase.list_activities(
            page=page,
            per_page=per_page,
            search=search,
        )

        return jsonify(
            {
                "activities": result.items,
                "total": result.total,
                "page": result.page,
                "pages": result.pages,
                "error": result.error,
            }
        )

    @app.route("/api/contributions")
    def api_contributions() -> WerkzeugResponse:
        """API endpoint returning contributions as JSON."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        per_page = _get_per_page(default=10)

        result = showcase.list_contributions(
            page=page,
            per_page=per_page,
        )

        return jsonify(
            {
                "contributions": result.items,
                "total": result.total,
                "page": result.page,
                "pages": result.pages,
                "error": result.error,
            }
        )

    @app.route("/api/events")
    def api_events() -> WerkzeugResponse:
        """API endpoint returning events as JSON."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        page = _get_page()
        search = _get_search()
        per_page = _get_per_page(default=10)

        result = showcase.list_events(
            page=page,
            per_page=per_page,
            search=search,
        )

        return jsonify(
            {
                "events": result.items,
                "total": result.total,
                "page": result.page,
                "pages": result.pages,
                "error": result.error,
            }
        )

    @app.route("/api/dashboard")
    def api_dashboard() -> WerkzeugResponse:
        """API endpoint returning dashboard statistics."""
        client = get_civi_client()
        showcase = SyncCiviShowcase(client)

        stats = showcase.get_dashboard_stats()

        return jsonify(
            {
                "total_contacts": stats.total_contacts,
                "total_individuals": stats.total_individuals,
                "total_organizations": stats.total_organizations,
                "total_households": stats.total_households,
                "total_activities": stats.total_activities,
                "total_contributions": stats.total_contributions,
                "total_events": stats.total_events,
                "recent_contacts": stats.recent_contacts,
                "recent_activities": stats.recent_activities,
                "error": stats.error,
            }
        )


# =============================================================================
# Application Entry Point
# =============================================================================


# Create the application instance for the development server
app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=8002)
