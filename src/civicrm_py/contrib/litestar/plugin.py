"""Litestar CiviCRM Plugin implementation.

Provides the main CiviPlugin class that integrates civi-py with Litestar
applications, handling client lifecycle, dependency injection, and route
registration.

Example:
    >>> from litestar import Litestar
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    >>>
    >>> # Basic usage with defaults
    >>> app = Litestar(plugins=[CiviPlugin()])
    >>>
    >>> # With custom configuration
    >>> config = CiviPluginConfig(
    ...     api_prefix="/api/v1/civi",
    ...     enable_health_check=True,
    ...     include_entities=["Contact", "Activity"],
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from civicrm_py.contrib.litestar.config import CiviPluginConfig
from civicrm_py.contrib.litestar.dependencies import (
    CIVI_CLIENT_STATE_KEY,
    cleanup_client,
    get_dependency_providers,
)

if TYPE_CHECKING:
    from click import Group
    from litestar import Litestar
    from litestar.config.app import AppConfig
    from litestar.types import ControllerRouterHandler

logger = logging.getLogger("civicrm_py.contrib.litestar")


class CiviPlugin(InitPluginProtocol, CLIPluginProtocol):
    """Litestar plugin for CiviCRM API integration.

    Provides automatic client lifecycle management, dependency injection,
    route generation, and health checks for CiviCRM API access in Litestar
    applications.

    The plugin:
    - Initializes CiviClient on application startup
    - Registers dependency providers for handler injection
    - Optionally generates CRUD routes for CiviCRM entities
    - Optionally adds health check endpoint
    - Cleans up client on application shutdown

    Attributes:
        config: Plugin configuration instance.

    Example:
        Basic usage:

        >>> from litestar import Litestar, get
        >>> from civicrm_py.core.client import CiviClient
        >>> from civicrm_py.contrib.litestar import CiviPlugin
        >>>
        >>> @get("/my-contacts")
        ... async def my_handler(civi_client: CiviClient) -> dict:
        ...     response = await civi_client.get("Contact", limit=5)
        ...     return {"contacts": response.values}
        >>>
        >>> app = Litestar(
        ...     route_handlers=[my_handler],
        ...     plugins=[CiviPlugin()],
        ... )

        With custom configuration:

        >>> from civicrm_py.contrib.litestar import CiviPluginConfig
        >>>
        >>> config = CiviPluginConfig(
        ...     api_prefix="/api/crm",
        ...     enable_health_check=True,
        ...     health_check_path="/health/crm",
        ...     include_entities=["Contact", "Activity", "Contribution"],
        ...     debug=True,
        ... )
        >>> app = Litestar(plugins=[CiviPlugin(config)])

        Disable automatic routes (use only DI):

        >>> config = CiviPluginConfig(api_prefix=None, enable_health_check=False)
        >>> app = Litestar(
        ...     route_handlers=[my_custom_handler],
        ...     plugins=[CiviPlugin(config)],
        ... )
    """

    __slots__ = ("_config",)

    def __init__(self, config: CiviPluginConfig | None = None) -> None:
        """Initialize the CiviPlugin.

        Args:
            config: Plugin configuration. If None, uses default configuration
                which loads settings from environment variables.
        """
        self._config = config or CiviPluginConfig()

        if self._config.debug:
            logging.getLogger("civicrm_py").setLevel(logging.DEBUG)

    @property
    def config(self) -> CiviPluginConfig:
        """Get the plugin configuration."""
        return self._config

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure Litestar application with CiviCRM integration.

        Called by Litestar during application initialization. Sets up:
        - Lifecycle handlers for client initialization and cleanup
        - Dependency providers for CiviClient injection
        - Route handlers for CRUD operations (if enabled)
        - Health check endpoint (if enabled)
        - SQLSpec integration (if enabled)
        - Workflow integration (if enabled)

        Args:
            app_config: Litestar application configuration.

        Returns:
            Modified AppConfig with CiviCRM integration configured.
        """
        logger.info("Initializing CiviPlugin")

        # Add lifecycle handlers
        app_config.on_startup.append(self._on_startup)
        app_config.on_shutdown.append(self._on_shutdown)

        # Register dependency providers
        existing_deps = dict(app_config.dependencies) if app_config.dependencies else {}
        existing_deps.update(get_dependency_providers())

        # Configure SQLSpec integration if enabled
        if self._config.sqlspec is not None and self._config.sqlspec.enabled:
            app_config = self._configure_sqlspec(app_config, existing_deps)
        else:
            app_config.dependencies = existing_deps

        # Configure workflow integration if enabled
        if self._config.workflows is not None and self._config.workflows.enabled:
            app_config = self._configure_workflows(app_config)

        # Collect route handlers to add
        route_handlers: list[ControllerRouterHandler] = list(app_config.route_handlers or [])

        # Add CRUD routes if enabled
        if self._config.api_prefix is not None:
            from litestar import Router

            from civicrm_py.contrib.litestar.routes import get_entity_controllers

            controllers = get_entity_controllers(
                include_entities=self._config.include_entities,
                exclude_entities=self._config.exclude_entities,
            )

            if controllers:
                civi_router = Router(
                    path=self._config.api_prefix,
                    route_handlers=controllers,
                    tags=self._config.openapi_tags,
                )
                route_handlers.append(civi_router)
                logger.debug(
                    "Registered %d entity controllers at %s",
                    len(controllers),
                    self._config.api_prefix,
                )

        # Add health check if enabled
        if self._config.enable_health_check:
            from civicrm_py.contrib.litestar.health import get_health_check_route

            health_handler = get_health_check_route(self._config.health_check_path)
            route_handlers.append(health_handler)
            logger.debug("Registered health check at %s", self._config.health_check_path)

        # Add Web UI if enabled
        if self._config.enable_webui:
            from dataclasses import replace
            from pathlib import Path

            from litestar import Router
            from litestar.contrib.jinja import JinjaTemplateEngine
            from litestar.template import TemplateConfig

            from civicrm_py.contrib.litestar.webui import WebUIConfig, get_webui_controllers
            from civicrm_py.webui import TEMPLATES_DIR

            # Create or update webui config with debug flag from plugin
            webui_cfg = self._config.webui_config
            if webui_cfg is None:
                webui_cfg = WebUIConfig(debug=self._config.debug)
            elif self._config.debug and not webui_cfg.debug:
                # Plugin debug is on, propagate to webui if not explicitly set
                webui_cfg = replace(webui_cfg, debug=True)

            webui_controllers = get_webui_controllers(
                config=webui_cfg,
                base_path=self._config.webui_path,
            )
            route_handlers.extend(webui_controllers)

            # Handle template config - merge directories if already set
            if app_config.template_config is None:
                app_config.template_config = TemplateConfig(  # type: ignore[assignment]
                    directory=TEMPLATES_DIR,
                    engine=JinjaTemplateEngine,
                )
            elif app_config.template_config.instance is not None:
                # An instance is already configured - add our templates to its loader
                existing_engine = app_config.template_config.instance
                if hasattr(existing_engine, "engine") and hasattr(existing_engine.engine, "loader"):
                    loader = existing_engine.engine.loader
                    if hasattr(loader, "searchpath"):
                        templates_str = str(TEMPLATES_DIR)
                        if templates_str not in loader.searchpath:
                            loader.searchpath.append(templates_str)
                            logger.debug("Added Web UI templates to existing loader")
            else:
                # Merge webui templates with existing directories
                raw_dirs = app_config.template_config.directory
                merged_dirs: list[Path | str]
                if isinstance(raw_dirs, (str, Path)):
                    merged_dirs = [Path(raw_dirs)]
                elif raw_dirs is None:
                    merged_dirs = []
                elif isinstance(raw_dirs, list):
                    merged_dirs = list(raw_dirs)  # type: ignore[arg-type]
                else:
                    # PathLike object - convert to Path
                    merged_dirs = [Path(raw_dirs)]

                if TEMPLATES_DIR not in merged_dirs:
                    merged_dirs.append(TEMPLATES_DIR)
                    # Cast to expected type for TemplateConfig
                    app_config.template_config = TemplateConfig(
                        directory=merged_dirs,  # type: ignore[arg-type]
                        engine=app_config.template_config.engine or JinjaTemplateEngine,
                    )

            logger.debug("Registered Web UI at %s", self._config.webui_path)

        # Add Workflow routes if enabled
        if self._config.workflows is not None and self._config.workflows.enabled:
            from civicrm_py.contrib.litestar.workflows_integration import (
                get_workflow_router,
            )
            from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE

            if WORKFLOWS_AVAILABLE:
                workflow_router = get_workflow_router(self._config.workflows)
                route_handlers.append(workflow_router)
                logger.debug(
                    "Registered workflow routes at %s",
                    self._config.workflows.api_prefix,
                )
            else:
                logger.warning(
                    "Workflow integration enabled but litestar-workflows not installed. "
                    "Install with: pip install 'civi-py[workflows]'",
                )

        app_config.route_handlers = route_handlers

        return app_config

    def _configure_sqlspec(
        self,
        app_config: AppConfig,
        existing_deps: dict,
    ) -> AppConfig:
        """Configure SQLSpec integration.

        Sets up lifecycle handlers and dependency providers for SQLSpec
        repository layer.

        Args:
            app_config: Litestar application configuration.
            existing_deps: Existing dependency providers dict to update.

        Returns:
            Modified AppConfig with SQLSpec configured.
        """
        from civicrm_py.contrib.litestar.sqlspec_integration import (
            SQLSPEC_AVAILABLE,
            cleanup_sqlspec,
            get_sqlspec_dependency_providers,
            initialize_sqlspec,
        )

        if not SQLSPEC_AVAILABLE:
            logger.warning(
                "SQLSpec integration enabled but sqlspec not installed. Install with: pip install 'civi-py[sqlspec]'",
            )
            app_config.dependencies = existing_deps
            return app_config

        sqlspec_config = self._config.sqlspec
        assert sqlspec_config is not None  # Checked by caller

        # Add SQLSpec lifecycle handlers
        async def sqlspec_startup(app: Litestar) -> None:
            await initialize_sqlspec(app, sqlspec_config)

        async def sqlspec_shutdown(app: Litestar) -> None:
            await cleanup_sqlspec(app)

        app_config.on_startup.append(sqlspec_startup)
        app_config.on_shutdown.insert(0, sqlspec_shutdown)  # Cleanup before CiviClient

        # Register SQLSpec dependency providers if enabled
        if sqlspec_config.provide_repositories:
            existing_deps.update(get_sqlspec_dependency_providers())
            logger.debug("Registered SQLSpec dependency providers")

        app_config.dependencies = existing_deps

        logger.info("SQLSpec integration configured")
        return app_config

    def _configure_workflows(
        self,
        app_config: AppConfig,
    ) -> AppConfig:
        """Configure workflow integration.

        Sets up lifecycle handlers for workflow automation features
        including registry and execution engine initialization.

        Args:
            app_config: Litestar application configuration.

        Returns:
            Modified AppConfig with workflows configured.
        """
        from civicrm_py.contrib.litestar.workflows_integration import (
            cleanup_workflows,
            initialize_workflows,
        )
        from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE

        if not WORKFLOWS_AVAILABLE:
            logger.warning(
                "Workflow integration enabled but litestar-workflows not installed. "
                "Install with: pip install 'civi-py[workflows]'",
            )
            return app_config

        workflows_config = self._config.workflows
        assert workflows_config is not None  # Checked by caller

        # Add workflow lifecycle handlers
        async def workflows_startup(app: Litestar) -> None:
            await initialize_workflows(app, workflows_config)

        async def workflows_shutdown(app: Litestar) -> None:
            await cleanup_workflows(app)

        app_config.on_startup.append(workflows_startup)
        app_config.on_shutdown.insert(0, workflows_shutdown)  # Cleanup before CiviClient

        logger.info("Workflow integration configured")
        return app_config

    async def _on_startup(self, app: Litestar) -> None:
        """Initialize CiviClient on application startup.

        Creates the CiviClient instance and stores it in application state
        for dependency injection.

        Args:
            app: The Litestar application instance.
        """
        from civicrm_py.core.client import CiviClient
        from civicrm_py.core.config import CiviSettings

        settings = self._config.settings
        if settings is None:
            logger.debug("Loading CiviSettings from environment")
            settings = CiviSettings.from_env()

        client = CiviClient(settings)
        setattr(app.state, CIVI_CLIENT_STATE_KEY, client)

        logger.info(
            "CiviClient initialized for %s",
            settings.base_url,
        )

    async def _on_shutdown(self, app: Litestar) -> None:
        """Clean up CiviClient on application shutdown.

        Closes the CiviClient and releases resources.

        Args:
            app: The Litestar application instance.
        """
        await cleanup_client(app)
        logger.info("CiviPlugin shutdown complete")

    def on_cli_init(self, cli: Group) -> None:
        """Register CLI commands with the Litestar CLI.

        Adds the ``civi`` command group with subcommands:
        - ``litestar civi check`` - Verify CiviCRM connection
        - ``litestar civi shell`` - Interactive Python shell
        - ``litestar civi sync`` - Entity discovery and stub generation

        Args:
            cli: The Click command group to add commands to.
        """
        from civicrm_py.contrib.litestar.cli import civi_group

        cli.add_command(civi_group)
        logger.debug("Registered CiviCRM CLI commands")


__all__ = ["CiviPlugin"]
