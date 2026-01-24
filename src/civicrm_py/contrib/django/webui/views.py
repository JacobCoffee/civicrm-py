"""Django Web UI views.

Provides views for the interactive Web UI including:
- Main dashboard with navigation
- Entity browser for exploring CiviCRM data
- API playground for testing queries

All views require staff authentication by default (configurable via WebUIConfig).
In debug mode, authentication is skipped with a warning.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from civicrm_py.contrib.django.webui.config import WebUIConfig

logger = logging.getLogger("civicrm_py.contrib.django.webui")

# Warning message for unauthenticated debug mode
_DEBUG_WARNING = """
╔════════════════════════════════════════════════════════════════════════════════╗
║  ⚠️  WARNING: CiviCRM Web UI is running WITHOUT AUTHENTICATION                  ║
║                                                                                 ║
║  The Web UI is accessible without login because debug mode is enabled.         ║
║  This exposes CiviCRM data to anyone with network access.                       ║
║                                                                                 ║
║  DO NOT USE IN PRODUCTION!                                                      ║
║                                                                                 ║
║  To enable authentication:                                                      ║
║    - Set WebUIConfig(debug=False) or                                           ║
║    - Set DEBUG=False in Django settings                                         ║
╚════════════════════════════════════════════════════════════════════════════════╝
"""

_debug_warning_logged = False


def _create_webui_url_helper() -> Any:
    """Create a webui_url helper function for templates.

    Returns:
        A function that generates URLs for Web UI pages using Django's reverse().
    """

    def webui_url(page: str, **kwargs: Any) -> str:
        """Generate URL for a Web UI page.

        Args:
            page: Page identifier ('index', 'entities', 'entity_list', 'entity_detail', 'playground', 'execute').
            **kwargs: URL parameters (e.g., entity, entity_id).

        Returns:
            URL string.
        """
        if page == "index":
            return reverse("civi_webui_index")
        if page == "entities":
            return reverse("civi_webui_entities")
        if page == "entity_list":
            entity = kwargs.get("entity", "")
            return reverse("civi_webui_entity_list", kwargs={"entity": entity})
        if page == "entity_detail":
            entity = kwargs.get("entity", "")
            entity_id = kwargs.get("entity_id", "")
            return reverse("civi_webui_entity_detail", kwargs={"entity": entity, "entity_id": entity_id})
        if page == "playground":
            return reverse("civi_webui_playground")
        if page == "execute":
            return reverse("civi_webui_execute")
        return reverse("civi_webui_index")

    return webui_url


def _get_context(
    config: WebUIConfig,
    current_page: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build template context with webui_url helper.

    Args:
        config: Web UI configuration.
        current_page: Current page identifier for nav highlighting.
        **extra: Additional context variables.

    Returns:
        Template context dictionary.
    """
    return {
        "title": config.title,
        "theme": config.theme,
        "enable_playground": config.enable_playground,
        "enable_entity_browser": config.enable_entity_browser,
        "enable_history": config.enable_request_history,
        "entities": config.default_entities,
        "current_page": current_page,
        "webui_url": _create_webui_url_helper(),
        **extra,
    }


class StaffRequiredMixin:
    """Mixin that requires staff authentication for views.

    Uses the WebUIConfig.require_staff setting to determine if
    authentication is required. Redirects to login_url if not authenticated.

    In debug mode (WebUIConfig.debug=True or Django DEBUG=True), authentication
    is skipped but a warning is logged.
    """

    config: WebUIConfig | None = None

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Check authentication before dispatching to the view."""
        global _debug_warning_logged  # noqa: PLW0603
        cfg = self.config or WebUIConfig()

        # Check if we're in debug mode (either config or Django setting)
        from django.conf import settings as django_settings

        is_debug = cfg.debug or getattr(django_settings, "DEBUG", False)

        if cfg.require_staff and not is_debug:
            if not request.user.is_authenticated:
                return redirect(f"{cfg.login_url}?next={request.path}")
            if not (request.user.is_staff or request.user.is_superuser):
                return HttpResponse("Permission denied. Staff access required.", status=403)
        elif is_debug and cfg.require_staff:
            # Debug mode with auth normally required - log warning
            if not _debug_warning_logged:
                logger.warning(_DEBUG_WARNING)
                _debug_warning_logged = True

        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


def get_client(request: HttpRequest) -> Any:
    """Get the CiviClient from the request.

    The middleware provides a sync client for sync views.
    """
    client = getattr(request, "civi_client", None)
    if client is not None:
        return client

    # Fall back to creating a new sync client
    from civicrm_py.core.client import SyncCiviClient
    from civicrm_py.core.config import CiviSettings

    settings = CiviSettings.from_env()
    return SyncCiviClient(settings)


class WebUIIndexView(StaffRequiredMixin, View):
    """Main Web UI dashboard view.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the main dashboard."""
        return render(
            request,
            "index.html",
            _get_context(self.config, "index"),
            using="webui_jinja2",
        )


class EntityBrowserView(StaffRequiredMixin, View):
    """Entity browser view for exploring CiviCRM data.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the entity selection page."""
        return render(
            request,
            "entity_browser.html",
            _get_context(self.config, "entities"),
            using="webui_jinja2",
        )


class EntityListView(StaffRequiredMixin, View):
    """Entity list view with pagination and search.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest, entity: str) -> HttpResponse:
        """Render entity list with pagination and search."""
        page = int(request.GET.get("page", 1))
        search = request.GET.get("search", "")
        per_page = self.config.items_per_page
        offset = (page - 1) * per_page

        # Build where clause for search
        where: list[list[Any]] = []
        if search:
            where.append(["display_name", "CONTAINS", search])

        # Fetch entities using sync client
        error = None
        items: list[dict[str, Any]] = []
        total = 0

        try:
            client = get_client(request)
            response = client.get(
                entity,
                select=["id", "display_name", "created_date", "modified_date"],
                where=where if where else None,
                limit=per_page,
                offset=offset,
            )
            items = response.values or []
            total = response.count or 0
        except Exception as e:
            error = str(e)

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return render(
            request,
            "entity_list.html",
            _get_context(
                self.config,
                "entity_list",
                entity=entity,
                items=items,
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
                search=search,
                error=error,
            ),
            using="webui_jinja2",
        )


class EntityDetailView(StaffRequiredMixin, View):
    """Entity detail view.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest, entity: str, entity_id: int) -> HttpResponse:
        """Render entity detail page."""
        error = None
        item = None

        try:
            client = get_client(request)
            response = client.get(
                entity,
                where=[["id", "=", entity_id]],
                limit=1,
            )
            item = response.values[0] if response.values else None
            if item is None:
                error = "Entity not found"
        except Exception as e:
            error = str(e)

        return render(
            request,
            "entity_detail.html",
            _get_context(
                self.config,
                "entity_detail",
                entity=entity,
                entity_id=entity_id,
                item=item,
                error=error,
            ),
            using="webui_jinja2",
        )


class PlaygroundView(StaffRequiredMixin, View):
    """API playground view for testing queries.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the API playground."""
        return render(
            request,
            "playground.html",
            _get_context(self.config, "playground"),
            using="webui_jinja2",
        )


class PlaygroundExecuteView(StaffRequiredMixin, View):
    """API playground query execution endpoint.

    Requires staff authentication by default (see WebUIConfig.require_staff).
    """

    config: WebUIConfig | None = None

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        """Set up the view with default config if not provided."""
        super().setup(request, *args, **kwargs)
        if self.config is None:
            self.config = WebUIConfig()

    def get(self, request: HttpRequest) -> JsonResponse:
        """Execute an API query and return results as JSON."""
        entity = request.GET.get("entity", "Contact")
        action = request.GET.get("action", "get")
        select_str = request.GET.get("select", "")
        where_str = request.GET.get("where", "")
        limit = int(request.GET.get("limit", 25))

        # Parse select fields
        select_fields = None
        if select_str:
            select_fields = [s.strip() for s in select_str.split(",") if s.strip()]

        # Parse where clause
        where_clause = None
        if where_str:
            try:
                where_clause = json.loads(where_str)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid where clause JSON"})

        try:
            client = get_client(request)

            if action == "get":
                response = client.get(
                    entity,
                    select=select_fields,
                    where=where_clause,
                    limit=limit,
                )
                return JsonResponse(
                    {
                        "success": True,
                        "values": response.values,
                        "count": response.count,
                    }
                )
            if action == "getFields":
                response = client.get_fields(entity)
                return JsonResponse(
                    {
                        "success": True,
                        "values": response.values,
                        "count": response.count,
                    }
                )
            return JsonResponse({"error": f"Unsupported action: {action}"})
        except Exception as e:
            return JsonResponse({"error": str(e)})


__all__ = [
    "EntityBrowserView",
    "EntityDetailView",
    "EntityListView",
    "PlaygroundExecuteView",
    "PlaygroundView",
    "WebUIIndexView",
]
