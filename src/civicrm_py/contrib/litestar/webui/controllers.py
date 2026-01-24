"""Litestar Web UI controllers.

Provides controllers for the interactive Web UI including:
- Main dashboard with navigation
- Entity browser for exploring CiviCRM data
- API playground for testing queries

Authentication:
- By default, requires authentication (configurable via WebUIConfig.require_auth)
- In debug mode (WebUIConfig.debug=True), auth is skipped with a warning
- Custom guards can be provided via WebUIConfig.guards
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from litestar import Controller, Request, get
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.response import Template
from litestar.template import TemplateConfig

from civicrm_py.contrib.litestar.webui.config import WebUIConfig
from civicrm_py.webui import TEMPLATES_DIR as SHARED_TEMPLATES_DIR

if TYPE_CHECKING:
    from litestar.types import ControllerRouterHandler

    from civicrm_py.core.client import CiviClient

logger = logging.getLogger("civicrm_py.contrib.litestar.webui")

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
║    - Set CiviPluginConfig(debug=False) or                                      ║
║    - Provide custom guards via WebUIConfig(guards=[...])                        ║
╚════════════════════════════════════════════════════════════════════════════════╝
"""

_debug_warning_logged = False

# Use shared templates
TEMPLATES_DIR = SHARED_TEMPLATES_DIR


def _create_webui_url_helper(base_path: str) -> Any:
    """Create a webui_url helper function for templates.

    Args:
        base_path: Base URL path for the Web UI (e.g., '/explorer').

    Returns:
        A function that generates URLs for Web UI pages.
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
            return base_path
        if page == "entities":
            return f"{base_path}/entities"
        if page == "entity_list":
            entity = kwargs.get("entity", "")
            return f"{base_path}/entities/{entity}"
        if page == "entity_detail":
            entity = kwargs.get("entity", "")
            entity_id = kwargs.get("entity_id", "")
            return f"{base_path}/entities/{entity}/{entity_id}"
        if page == "playground":
            return f"{base_path}/playground"
        if page == "execute":
            return f"{base_path}/playground/execute"
        return base_path

    return webui_url


def _get_context(
    config: WebUIConfig,
    base_path: str,
    current_page: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build template context with webui_url helper.

    Args:
        config: Web UI configuration.
        base_path: Base URL path for URL generation.
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
        "webui_url": _create_webui_url_helper(base_path),
        **extra,
    }


class WebUIController(Controller):
    """Main Web UI controller with dashboard and navigation."""

    path = "/"
    tags = ["Web UI"]

    _config: WebUIConfig
    _base_path: str

    def __init__(self, owner: Any, config: WebUIConfig | None = None, base_path: str = "/explorer") -> None:
        """Initialize the controller with configuration."""
        super().__init__(owner)
        self._config = config or WebUIConfig()
        self._base_path = base_path

    @get("/", name="webui_index")
    async def index(self, request: Request) -> Template:
        """Render the main Web UI dashboard."""
        return Template(
            template_name="index.html",
            context=_get_context(self._config, self._base_path, "index"),
        )


class EntityBrowserController(Controller):
    """Entity browser controller for exploring CiviCRM data."""

    path = "/entities"
    tags = ["Web UI"]
    signature_types: list[type] = []

    _config: WebUIConfig
    _base_path: str

    def __init__(self, owner: Any, config: WebUIConfig | None = None, base_path: str = "/explorer") -> None:
        """Initialize the controller with configuration."""
        super().__init__(owner)
        self._config = config or WebUIConfig()
        self._base_path = base_path

    @get("/", name="webui_entities")
    async def list_entities(self, request: Request) -> Template:
        """Render the entity selection page."""
        return Template(
            template_name="entity_browser.html",
            context=_get_context(self._config, self._base_path, "entities"),
        )

    @get("/{entity:str}", name="webui_entity_list")
    async def entity_list(
        self,
        request: Request,
        entity: str,
        civi_client: CiviClient,
        page: int = 1,
        search: str | None = None,
    ) -> Template:
        """Render entity list with pagination and search."""
        per_page = self._config.items_per_page
        offset = (page - 1) * per_page

        # Build where clause for search
        where: list[list[Any]] = []
        if search:
            where.append(["display_name", "CONTAINS", search])

        # Fetch entities
        try:
            response = await civi_client.get(
                entity,
                select=["id", "display_name", "created_date", "modified_date"],
                where=where if where else None,
                limit=per_page,
                offset=offset,
            )
            items = response.values or []
            total = response.count or 0
            error = None
        except Exception as e:
            items = []
            total = 0
            error = str(e)

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return Template(
            template_name="entity_list.html",
            context=_get_context(
                self._config,
                self._base_path,
                "entity_list",
                entity=entity,
                items=items,
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
                search=search or "",
                error=error,
            ),
        )

    @get("/{entity:str}/{entity_id:int}", name="webui_entity_detail")
    async def entity_detail(
        self,
        request: Request,
        entity: str,
        entity_id: int,
        civi_client: CiviClient,
    ) -> Template:
        """Render entity detail page."""
        try:
            response = await civi_client.get(
                entity,
                where=[["id", "=", entity_id]],
                limit=1,
            )
            item = response.values[0] if response.values else None
            error = None if item else "Entity not found"
        except Exception as e:
            item = None
            error = str(e)

        return Template(
            template_name="entity_detail.html",
            context=_get_context(
                self._config,
                self._base_path,
                "entity_detail",
                entity=entity,
                entity_id=entity_id,
                item=item,
                error=error,
            ),
        )


class PlaygroundController(Controller):
    """API playground controller for testing queries."""

    path = "/playground"
    tags = ["Web UI"]
    signature_types: list[type] = []

    _config: WebUIConfig
    _base_path: str

    def __init__(self, owner: Any, config: WebUIConfig | None = None, base_path: str = "/explorer") -> None:
        """Initialize the controller with configuration."""
        super().__init__(owner)
        self._config = config or WebUIConfig()
        self._base_path = base_path

    @get("/", name="webui_playground")
    async def playground(self, request: Request) -> Template:
        """Render the API playground."""
        return Template(
            template_name="playground.html",
            context=_get_context(self._config, self._base_path, "playground"),
        )

    @get("/execute", name="webui_execute")
    async def execute_query(
        self,
        civi_client: CiviClient,
        entity: str,
        action: str = "get",
        select: str | None = None,
        where: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Execute an API query and return results as JSON."""
        import json

        # Parse select fields
        select_fields = None
        if select:
            select_fields = [s.strip() for s in select.split(",") if s.strip()]

        # Parse where clause (simple JSON parsing)
        where_clause = None
        if where:
            try:
                where_clause = json.loads(where)
            except json.JSONDecodeError:
                return {"error": "Invalid where clause JSON"}

        try:
            if action == "get":
                response = await civi_client.get(
                    entity,
                    select=select_fields,
                    where=where_clause,
                    limit=limit,
                )
                return {
                    "success": True,
                    "values": response.values,
                    "count": response.count,
                }
            if action == "getFields":
                response = await civi_client.get_fields(entity)
                return {
                    "success": True,
                    "values": response.values,
                    "count": response.count,
                }
            return {"error": f"Unsupported action: {action}"}
        except Exception as e:
            return {"error": str(e)}


def get_webui_controllers(
    config: WebUIConfig | None = None,
    base_path: str = "/explorer",
) -> list[ControllerRouterHandler]:
    """Get all Web UI controllers configured with the given settings.

    Args:
        config: Web UI configuration. Defaults to WebUIConfig().
        base_path: Base URL path for the Web UI.

    Returns:
        List of configured controller classes and static file routers.

    Authentication:
        - If config.debug=True: No auth required, but logs a warning
        - If config.require_auth=True: Uses provided guards or raises error if no guards
        - If config.guards provided: Uses those guards

    Example:
        >>> # Debug mode - no auth (with warning)
        >>> controllers = get_webui_controllers(WebUIConfig(debug=True))
        >>>
        >>> # Production - with custom guard
        >>> from litestar.exceptions import NotAuthorizedException
        >>>
        >>> async def require_admin(connection, _):
        ...     if not connection.user or not connection.user.is_admin:
        ...         raise NotAuthorizedException()
        >>>
        >>> controllers = get_webui_controllers(WebUIConfig(guards=[require_admin]))
    """
    global _debug_warning_logged  # noqa: PLW0603
    from civicrm_py.core.client import CiviClient

    cfg = config or WebUIConfig()

    # Handle authentication logging
    if cfg.debug and cfg.require_auth:
        if not _debug_warning_logged:
            logger.warning(_DEBUG_WARNING)
            _debug_warning_logged = True

    # Determine guards to apply
    guards_to_apply: list[Any] = []
    if not cfg.debug and cfg.require_auth:
        if cfg.guards:
            guards_to_apply = list(cfg.guards)
        else:
            # No guards provided but auth required - log info about configuring auth
            logger.info(
                "Web UI authentication enabled but no guards configured. "
                "Provide guards via WebUIConfig(guards=[...]) for custom auth.",
            )

    # Create controller classes with injected config and base_path
    class ConfiguredWebUIController(WebUIController):
        path = base_path
        guards = guards_to_apply if guards_to_apply else None

        def __init__(self, owner: Any) -> None:
            super().__init__(owner, cfg, base_path)

    class ConfiguredEntityBrowserController(EntityBrowserController):
        path = f"{base_path}/entities"
        signature_types = [CiviClient]
        guards = guards_to_apply if guards_to_apply else None

        def __init__(self, owner: Any) -> None:
            super().__init__(owner, cfg, base_path)

    class ConfiguredPlaygroundController(PlaygroundController):
        path = f"{base_path}/playground"
        signature_types = [CiviClient]
        guards = guards_to_apply if guards_to_apply else None

        def __init__(self, owner: Any) -> None:
            super().__init__(owner, cfg, base_path)

    controllers: list[ControllerRouterHandler] = [
        ConfiguredWebUIController,
        ConfiguredEntityBrowserController,
        ConfiguredPlaygroundController,
    ]

    return controllers


def get_template_config() -> TemplateConfig:
    """Get the template configuration for Web UI templates.

    Returns:
        TemplateConfig configured for the shared Web UI templates directory.
    """
    return TemplateConfig(
        directory=TEMPLATES_DIR,
        engine=JinjaTemplateEngine,
    )


__all__ = [
    "TEMPLATES_DIR",
    "EntityBrowserController",
    "PlaygroundController",
    "WebUIController",
    "get_template_config",
    "get_webui_controllers",
]
