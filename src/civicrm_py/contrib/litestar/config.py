"""Configuration for Litestar CiviCRM plugin.

Provides configuration dataclass for the CiviPlugin with settings
for API routes, health checks, and OpenAPI documentation.

Example:
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    >>> from litestar import Litestar
    >>>
    >>> config = CiviPluginConfig(
    ...     api_prefix="/api/civi",
    ...     enable_health_check=True,
    ...     health_check_path="/health/civi",
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])

With SQLSpec integration:
    >>> from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
    >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
    >>>
    >>> config = CiviPluginConfig(
    ...     sqlspec=SQLSpecPluginConfig(
    ...         enabled=True,
    ...         sqlspec_config=CiviSQLSpecConfig(
    ...             adapter="aiosqlite",
    ...             database="civi_cache.db",
    ...         ),
    ...     ),
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])

With workflow integration:
    >>> from civicrm_py.contrib.litestar.workflows_integration import WorkflowPluginConfig
    >>>
    >>> config = CiviPluginConfig(
    ...     workflows=WorkflowPluginConfig(
    ...         enabled=True,
    ...         api_prefix="/api/civi/workflows",
    ...         register_builtins=True,
    ...     ),
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
    from civicrm_py.contrib.litestar.webui import WebUIConfig
    from civicrm_py.contrib.litestar.workflows_integration import WorkflowPluginConfig
    from civicrm_py.core.config import CiviSettings


@dataclass
class CiviPluginConfig:
    """Configuration for the Litestar CiviCRM plugin.

    Controls API route generation, health checks, OpenAPI documentation,
    and client configuration for the CiviPlugin.

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
        debug: Enable debug logging for the plugin.
        enable_webui: Whether to enable the Web UI explorer.
        webui_path: URL path for the Web UI.
        webui_config: Configuration for the Web UI.
        sqlspec: Optional SQLSpec integration configuration.
            When enabled, provides local database caching alongside CiviCRM API.
        workflows: Optional workflow integration configuration.
            When enabled, provides workflow automation features with
            REST API endpoints for managing workflow instances.

    Example:
        >>> config = CiviPluginConfig(
        ...     api_prefix="/api/v1/civi",
        ...     enable_health_check=True,
        ...     include_entities=["Contact", "Activity", "Contribution"],
        ... )

        With SQLSpec caching:

        >>> from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
        >>> from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig
        >>>
        >>> config = CiviPluginConfig(
        ...     sqlspec=SQLSpecPluginConfig(
        ...         enabled=True,
        ...         sqlspec_config=CiviSQLSpecConfig(
        ...             adapter="aiosqlite",
        ...             database="civi_cache.db",
        ...         ),
        ...         auto_run_migrations=True,
        ...     ),
        ... )

        With workflow automation:

        >>> from civicrm_py.contrib.litestar.workflows_integration import WorkflowPluginConfig
        >>>
        >>> config = CiviPluginConfig(
        ...     workflows=WorkflowPluginConfig(
        ...         enabled=True,
        ...         api_prefix="/api/civi/workflows",
        ...         register_builtins=True,
        ...     ),
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
    # Web UI options
    enable_webui: bool = False
    webui_path: str = "/explorer"
    webui_config: WebUIConfig | None = None
    # SQLSpec integration
    sqlspec: SQLSpecPluginConfig | None = None
    # Workflow integration
    workflows: WorkflowPluginConfig | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.api_prefix is not None and not self.api_prefix.startswith("/"):
            self.api_prefix = f"/{self.api_prefix}"

        if not self.health_check_path.startswith("/"):
            self.health_check_path = f"/{self.health_check_path}"

        if not self.webui_path.startswith("/"):
            self.webui_path = f"/{self.webui_path}"


__all__ = ["CiviPluginConfig"]
