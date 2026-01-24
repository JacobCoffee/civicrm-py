"""Litestar integration for civi-py.

Provides first-class Litestar 2+ support with:
- CiviPlugin for automatic client lifecycle management
- Dependency injection for CiviClient in route handlers
- Auto-generated CRUD routes for CiviCRM entities
- Health check endpoint for monitoring
- Msgspec DTOs for request/response validation
- CLI commands for CiviCRM management
- Optional SQLSpec integration for local database caching
- Optional workflow automation with litestar-workflows

Quick Start:
    >>> from litestar import Litestar, get
    >>> from civicrm_py.core.client import CiviClient
    >>> from civicrm_py.contrib.litestar import CiviPlugin
    >>>
    >>> @get("/my-contacts")
    ... async def list_my_contacts(civi_client: CiviClient) -> dict:
    ...     response = await civi_client.get("Contact", limit=10)
    ...     return {"contacts": response.values}
    >>>
    >>> app = Litestar(
    ...     route_handlers=[list_my_contacts],
    ...     plugins=[CiviPlugin()],
    ... )

With Configuration:
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    >>>
    >>> config = CiviPluginConfig(
    ...     api_prefix="/api/v1/civi",  # CRUD routes prefix
    ...     enable_health_check=True,  # Enable /health/civi endpoint
    ...     include_entities=["Contact", "Activity"],  # Limit routes
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])

With SQLSpec Caching:
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
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
    >>> app = Litestar(plugins=[CiviPlugin(config)])

With Workflow Automation:
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
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

Environment Variables:
    Set these environment variables for automatic configuration:
    - CIVI_BASE_URL: CiviCRM API base URL
    - CIVI_API_KEY: API key for authentication
    - CIVI_SITE_KEY: Optional site key
    - CIVI_TIMEOUT: Request timeout (default: 30)
    - CIVI_VERIFY_SSL: Verify SSL certificates (default: true)

Generated Routes (when api_prefix is set):
    GET    {api_prefix}/Contact         - List contacts
    GET    {api_prefix}/Contact/{id}    - Get single contact
    POST   {api_prefix}/Contact         - Create contact
    PUT    {api_prefix}/Contact/{id}    - Update contact
    DELETE {api_prefix}/Contact/{id}    - Delete contact
    (Same pattern for Activity, Contribution, Event, Membership, etc.)

Health Check:
    GET /health/civi - Returns CiviCRM connectivity status

CLI Commands (when using ``litestar`` CLI):
    litestar civi check          - Verify CiviCRM connection and configuration
    litestar civi shell          - Interactive Python shell with CiviCRM client
    litestar civi sync           - Discover entities and generate Python stubs

Workflow Routes (when workflows enabled):
    GET    {workflow_prefix}/                    - List workflow definitions
    POST   {workflow_prefix}/{name}/start        - Start a workflow instance
    GET    {workflow_prefix}/instances           - List workflow instances
    GET    {workflow_prefix}/instances/{id}      - Get instance details
    POST   {workflow_prefix}/instances/{id}/complete - Complete human task
    GET    {workflow_prefix}/tasks               - List pending human tasks
"""

from __future__ import annotations

from civicrm_py.contrib.litestar.cli import (
    civi_check,
    civi_group,
    civi_shell,
    civi_sync,
)
from civicrm_py.contrib.litestar.config import CiviPluginConfig
from civicrm_py.contrib.litestar.dependencies import (
    CIVI_CLIENT_STATE_KEY,
    cleanup_client,
    get_dependency_providers,
    provide_civi_client,
)
from civicrm_py.contrib.litestar.dto import (
    ActivityCreateDTO,
    ActivityFilterDTO,
    ActivityResponseDTO,
    ActivityUpdateDTO,
    APIResponseDTO,
    BaseDTO,
    ContactCreateDTO,
    ContactFilterDTO,
    ContactResponseDTO,
    ContactUpdateDTO,
    ContributionCreateDTO,
    ContributionFilterDTO,
    ContributionResponseDTO,
    ContributionUpdateDTO,
    EntityCreateDTO,
    EntityUpdateDTO,
    EventCreateDTO,
    EventFilterDTO,
    EventResponseDTO,
    EventUpdateDTO,
    MembershipCreateDTO,
    MembershipFilterDTO,
    MembershipResponseDTO,
    MembershipUpdateDTO,
    PaginationDTO,
)
from civicrm_py.contrib.litestar.health import (
    HealthCheckResponse,
    civi_health_check,
    get_health_check_route,
)
from civicrm_py.contrib.litestar.plugin import CiviPlugin
from civicrm_py.contrib.litestar.routes import (
    DEFAULT_CONTROLLERS,
    ActivityController,
    ContactController,
    ContributionController,
    EventController,
    GroupController,
    MembershipController,
    ParticipantController,
    create_entity_controller,
    get_entity_controllers,
)
from civicrm_py.contrib.litestar.sqlspec_integration import (
    CORRELATION_ID_KEY,
    SQLSPEC_AVAILABLE,
    SQLSPEC_STATE_KEY,
    SQLSpecPlugin,
    SQLSpecPluginConfig,
    SQLSpecState,
    cleanup_sqlspec,
    generate_correlation_id,
    get_correlation_id,
    get_sqlspec_dependency_providers,
    initialize_sqlspec,
    provide_activity_repository,
    provide_contact_repository,
    provide_contribution_repository,
    provide_event_repository,
    provide_membership_repository,
    provide_sqlspec_session,
    set_correlation_id,
)
from civicrm_py.contrib.litestar.webui import WebUIConfig
from civicrm_py.contrib.litestar.workflows_integration import (
    WORKFLOW_ENGINE_STATE_KEY,
    WORKFLOW_REGISTRY_STATE_KEY,
    CiviWorkflowController,
    CompleteTaskRequestDTO,
    HumanTaskDTO,
    HumanTasksResponseDTO,
    StartWorkflowRequestDTO,
    StartWorkflowResponseDTO,
    WorkflowDefinitionDTO,
    WorkflowDefinitionsResponseDTO,
    WorkflowInstanceDetailDTO,
    WorkflowInstanceDTO,
    WorkflowInstancesResponseDTO,
    WorkflowPluginConfig,
    WorkflowStepHistoryDTO,
    cleanup_workflows,
    get_workflow_dependency_providers,
    get_workflow_router,
    initialize_workflows,
    provide_workflow_engine,
    provide_workflow_registry,
)

__all__ = [
    "CIVI_CLIENT_STATE_KEY",
    "CORRELATION_ID_KEY",
    "DEFAULT_CONTROLLERS",
    "SQLSPEC_AVAILABLE",
    "SQLSPEC_STATE_KEY",
    "WORKFLOW_ENGINE_STATE_KEY",
    "WORKFLOW_REGISTRY_STATE_KEY",
    "APIResponseDTO",
    "ActivityController",
    "ActivityCreateDTO",
    "ActivityFilterDTO",
    "ActivityResponseDTO",
    "ActivityUpdateDTO",
    "BaseDTO",
    "CiviPlugin",
    "CiviPluginConfig",
    "CiviWorkflowController",
    "CompleteTaskRequestDTO",
    "ContactController",
    "ContactCreateDTO",
    "ContactFilterDTO",
    "ContactResponseDTO",
    "ContactUpdateDTO",
    "ContributionController",
    "ContributionCreateDTO",
    "ContributionFilterDTO",
    "ContributionResponseDTO",
    "ContributionUpdateDTO",
    "EntityCreateDTO",
    "EntityUpdateDTO",
    "EventController",
    "EventCreateDTO",
    "EventFilterDTO",
    "EventResponseDTO",
    "EventUpdateDTO",
    "GroupController",
    "HealthCheckResponse",
    "HumanTaskDTO",
    "HumanTasksResponseDTO",
    "MembershipController",
    "MembershipCreateDTO",
    "MembershipFilterDTO",
    "MembershipResponseDTO",
    "MembershipUpdateDTO",
    "PaginationDTO",
    "ParticipantController",
    "SQLSpecPlugin",
    "SQLSpecPluginConfig",
    "SQLSpecState",
    "StartWorkflowRequestDTO",
    "StartWorkflowResponseDTO",
    "WebUIConfig",
    "WorkflowDefinitionDTO",
    "WorkflowDefinitionsResponseDTO",
    "WorkflowInstanceDTO",
    "WorkflowInstanceDetailDTO",
    "WorkflowInstancesResponseDTO",
    "WorkflowPluginConfig",
    "WorkflowStepHistoryDTO",
    "civi_check",
    "civi_group",
    "civi_health_check",
    "civi_shell",
    "civi_sync",
    "cleanup_client",
    "cleanup_sqlspec",
    "cleanup_workflows",
    "create_entity_controller",
    "generate_correlation_id",
    "get_correlation_id",
    "get_dependency_providers",
    "get_entity_controllers",
    "get_health_check_route",
    "get_sqlspec_dependency_providers",
    "get_workflow_dependency_providers",
    "get_workflow_router",
    "initialize_sqlspec",
    "initialize_workflows",
    "provide_activity_repository",
    "provide_civi_client",
    "provide_contact_repository",
    "provide_contribution_repository",
    "provide_event_repository",
    "provide_membership_repository",
    "provide_sqlspec_session",
    "provide_workflow_engine",
    "provide_workflow_registry",
    "set_correlation_id",
]
