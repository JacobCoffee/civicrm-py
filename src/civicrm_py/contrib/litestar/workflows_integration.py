"""Workflow integration for the Litestar CiviCRM plugin.

Enables workflow automation features within the Litestar application,
providing REST API endpoints for managing workflow definitions and instances.

This module integrates litestar-workflows with the CiviPlugin, allowing
users to execute CiviCRM workflow steps (CiviFetchStep, CiviMutateStep, etc.)
through a web API.

Example:
    >>> from litestar import Litestar
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

This module requires the optional `workflows` dependency:

    pip install civi-py[workflows]

When litestar-workflows is not installed, the module degrades gracefully
and workflow features are simply not available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import msgspec
from litestar import Controller, Router, get, post
from litestar.datastructures import State  # noqa: TC002 - used in function signatures
from litestar.di import Provide
from litestar.exceptions import HTTPException, NotFoundException
from litestar.params import Parameter
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from civicrm_py.contrib.litestar.dto import BaseDTO
from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE

if TYPE_CHECKING:
    from litestar import Litestar

    from civicrm_py.core.client import CiviClient

logger = logging.getLogger("civicrm_py.contrib.litestar.workflows")

# State keys for workflow components
WORKFLOW_REGISTRY_STATE_KEY = "civi_workflow_registry"
WORKFLOW_ENGINE_STATE_KEY = "civi_workflow_engine"


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class WorkflowPluginConfig:
    """Configuration for workflow integration with CiviPlugin.

    Controls whether workflow features are enabled and how they are
    exposed through the Litestar application.

    Attributes:
        enabled: Whether workflow integration is enabled. When False,
            no workflow routes or dependencies are registered.
        api_prefix: URL prefix for workflow routes (e.g., "/api/workflows").
            All workflow endpoints are mounted under this prefix.
        register_builtins: Register built-in CiviCRM workflow templates
            (ContactImportWorkflow, etc.) automatically on startup.
        custom_workflows: Additional workflow classes to register with
            the workflow registry on startup.
        openapi_tags: Tags to apply to workflow routes in OpenAPI docs.
        execution_timeout: Default timeout in seconds for workflow execution.

    Example:
        Basic usage with defaults:

        >>> config = WorkflowPluginConfig(enabled=True)

        With custom workflows:

        >>> from my_app.workflows import MyCustomWorkflow
        >>>
        >>> config = WorkflowPluginConfig(
        ...     enabled=True,
        ...     api_prefix="/api/crm/workflows",
        ...     register_builtins=True,
        ...     custom_workflows=[MyCustomWorkflow],
        ... )

    Note:
        When `enabled=False`, all workflow-related features are disabled
        and no routes or dependencies are registered, regardless of
        other configuration values.
    """

    enabled: bool = False
    api_prefix: str = "/api/civi/workflows"
    register_builtins: bool = True
    custom_workflows: list[type] = field(default_factory=list)
    openapi_tags: list[str] = field(default_factory=lambda: ["CiviCRM Workflows"])
    execution_timeout: int = 300  # 5 minutes default

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.api_prefix.startswith("/"):
            self.api_prefix = f"/{self.api_prefix}"


# =============================================================================
# DTOs for Workflow API
# =============================================================================


class WorkflowDefinitionDTO(BaseDTO):
    """DTO for workflow definition information.

    Attributes:
        name: Unique workflow name/identifier.
        description: Human-readable description.
        steps: List of step names in execution order.
        human_steps: List of human step names requiring manual completion.
    """

    name: str
    description: str | None = None
    steps: list[str] = msgspec.field(default_factory=list)
    human_steps: list[str] = msgspec.field(default_factory=list)


class WorkflowDefinitionsResponseDTO(BaseDTO):
    """DTO for listing workflow definitions."""

    workflows: list[WorkflowDefinitionDTO]
    count: int


class WorkflowInstanceDTO(BaseDTO, kw_only=True):
    """DTO for workflow instance information.

    Attributes:
        instance_id: Unique instance identifier.
        workflow_name: Name of the workflow definition.
        status: Current instance status (pending, running, completed, failed, paused).
        current_step: Name of the currently executing step, if any.
        started_at: Timestamp when the workflow started.
        completed_at: Timestamp when the workflow completed, if finished.
        context_data: Subset of workflow context data (non-sensitive).
    """

    instance_id: str
    workflow_name: str
    status: str
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    context_data: dict[str, Any] = msgspec.field(default_factory=dict)


class WorkflowInstancesResponseDTO(BaseDTO):
    """DTO for listing workflow instances."""

    instances: list[WorkflowInstanceDTO]
    count: int


class StartWorkflowRequestDTO(BaseDTO):
    """DTO for starting a new workflow instance.

    Attributes:
        initial_context: Initial context data for the workflow.
    """

    initial_context: dict[str, Any] = msgspec.field(default_factory=dict)


class StartWorkflowResponseDTO(BaseDTO, kw_only=True):
    """DTO for workflow start response.

    Attributes:
        instance_id: Unique identifier for the created instance.
        workflow_name: Name of the workflow that was started.
        status: Initial status of the workflow.
    """

    instance_id: str
    workflow_name: str
    status: str


class CompleteTaskRequestDTO(BaseDTO):
    """DTO for completing a human task.

    Attributes:
        form_data: Form data submitted by the user for the human step.
    """

    form_data: dict[str, Any] = msgspec.field(default_factory=dict)


class HumanTaskDTO(BaseDTO, kw_only=True):
    """DTO for pending human task information.

    Attributes:
        instance_id: Workflow instance ID.
        step_name: Name of the human step.
        title: Human-readable title for the task.
        description: Task description.
        form_schema: JSON Schema for the form input.
        review_data: Data to display for review, if applicable.
        created_at: When the task was created.
    """

    instance_id: str
    step_name: str
    title: str
    description: str | None = None
    form_schema: dict[str, Any] = msgspec.field(default_factory=dict)
    review_data: dict[str, Any] = msgspec.field(default_factory=dict)
    created_at: datetime | None = None


class HumanTasksResponseDTO(BaseDTO):
    """DTO for listing pending human tasks."""

    tasks: list[HumanTaskDTO]
    count: int


class WorkflowStepHistoryDTO(BaseDTO, kw_only=True):
    """DTO for workflow step execution history.

    Attributes:
        step_name: Name of the executed step.
        step_type: Type of step (machine, human).
        status: Execution status (completed, failed, skipped).
        started_at: When step execution started.
        completed_at: When step execution completed.
        error: Error message if step failed.
    """

    step_name: str
    step_type: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class WorkflowInstanceDetailDTO(BaseDTO, kw_only=True):
    """DTO for detailed workflow instance information.

    Attributes:
        instance_id: Unique instance identifier.
        workflow_name: Name of the workflow definition.
        status: Current instance status.
        current_step: Name of the currently executing step.
        started_at: Timestamp when the workflow started.
        completed_at: Timestamp when the workflow completed.
        context_data: Workflow context data (filtered for sensitivity).
        step_history: History of step executions.
        pending_tasks: List of pending human tasks for this instance.
    """

    instance_id: str
    workflow_name: str
    status: str
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    context_data: dict[str, Any] = msgspec.field(default_factory=dict)
    step_history: list[WorkflowStepHistoryDTO] = msgspec.field(default_factory=list)
    pending_tasks: list[HumanTaskDTO] = msgspec.field(default_factory=list)


# =============================================================================
# Dependency Providers
# =============================================================================


async def provide_workflow_registry(state: State) -> Any:  # noqa: ANN401
    """Provide the workflow registry from application state.

    The workflow registry contains all registered workflow definitions
    that can be instantiated and executed.

    Args:
        state: Litestar application state.

    Returns:
        The WorkflowRegistry instance.

    Raises:
        RuntimeError: If workflow registry is not found in state,
            indicating workflows are not properly initialized.
    """
    registry = state.get(WORKFLOW_REGISTRY_STATE_KEY)
    if registry is None:
        msg = (
            "Workflow registry not found in application state. "
            "Ensure WorkflowPluginConfig.enabled=True and litestar-workflows is installed."
        )
        raise RuntimeError(msg)
    return registry


async def provide_workflow_engine(state: State) -> Any:  # noqa: ANN401
    """Provide the workflow execution engine from application state.

    The workflow engine handles the actual execution of workflow
    instances, managing step transitions and context.

    Args:
        state: Litestar application state.

    Returns:
        The LocalExecutionEngine instance.

    Raises:
        RuntimeError: If workflow engine is not found in state,
            indicating workflows are not properly initialized.
    """
    engine = state.get(WORKFLOW_ENGINE_STATE_KEY)
    if engine is None:
        msg = (
            "Workflow engine not found in application state. "
            "Ensure WorkflowPluginConfig.enabled=True and litestar-workflows is installed."
        )
        raise RuntimeError(msg)
    return engine


def get_workflow_dependency_providers() -> dict[str, Any]:
    """Get dependency provider mappings for workflow components.

    Returns a dictionary mapping dependency names to their provider
    callables for use with Litestar's dependency injection.

    Returns:
        Dictionary with workflow dependency providers.
    """
    return {
        "workflow_registry": Provide(provide_workflow_registry),
        "workflow_engine": Provide(provide_workflow_engine),
    }


# =============================================================================
# In-Memory Instance Store (for demonstration/dev)
# =============================================================================


class WorkflowInstanceStore:
    """Simple in-memory store for workflow instances.

    This is a basic implementation for development and testing.
    In production, you would typically use a database-backed store
    provided by litestar-workflows.

    Attributes:
        instances: Dictionary mapping instance IDs to instance data.
        step_history: Dictionary mapping instance IDs to step execution history.
        pending_tasks: Dictionary mapping instance IDs to pending human tasks.
    """

    def __init__(self) -> None:
        """Initialize the instance store."""
        self.instances: dict[str, dict[str, Any]] = {}
        self.step_history: dict[str, list[dict[str, Any]]] = {}
        self.pending_tasks: dict[str, list[dict[str, Any]]] = {}

    def create_instance(
        self,
        instance_id: str,
        workflow_name: str,
        initial_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new workflow instance record.

        Args:
            instance_id: Unique instance identifier.
            workflow_name: Name of the workflow definition.
            initial_context: Initial context data.

        Returns:
            The created instance record.
        """
        instance = {
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "status": "pending",
            "current_step": None,
            "started_at": datetime.now(tz=UTC),
            "completed_at": None,
            "context_data": initial_context or {},
        }
        self.instances[instance_id] = instance
        self.step_history[instance_id] = []
        self.pending_tasks[instance_id] = []
        return instance

    def get_instance(self, instance_id: str) -> dict[str, Any] | None:
        """Get an instance by ID.

        Args:
            instance_id: Instance identifier.

        Returns:
            Instance record or None if not found.
        """
        return self.instances.get(instance_id)

    def update_instance(self, instance_id: str, updates: dict[str, Any]) -> None:
        """Update an instance record.

        Args:
            instance_id: Instance identifier.
            updates: Fields to update.
        """
        if instance_id in self.instances:
            self.instances[instance_id].update(updates)

    def list_instances(
        self,
        workflow_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List instances with optional filtering.

        Args:
            workflow_name: Filter by workflow name.
            status: Filter by status.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching instance records.
        """
        results = list(self.instances.values())

        if workflow_name:
            results = [i for i in results if i["workflow_name"] == workflow_name]
        if status:
            results = [i for i in results if i["status"] == status]

        # Sort by started_at descending
        results.sort(key=lambda x: x.get("started_at") or datetime.min.replace(tzinfo=UTC), reverse=True)

        return results[offset : offset + limit]

    def add_step_history(self, instance_id: str, step_record: dict[str, Any]) -> None:
        """Add a step execution record to history.

        Args:
            instance_id: Instance identifier.
            step_record: Step execution record.
        """
        if instance_id in self.step_history:
            self.step_history[instance_id].append(step_record)

    def get_step_history(self, instance_id: str) -> list[dict[str, Any]]:
        """Get step history for an instance.

        Args:
            instance_id: Instance identifier.

        Returns:
            List of step execution records.
        """
        return self.step_history.get(instance_id, [])

    def add_pending_task(self, instance_id: str, task: dict[str, Any]) -> None:
        """Add a pending human task.

        Args:
            instance_id: Instance identifier.
            task: Task record.
        """
        if instance_id in self.pending_tasks:
            self.pending_tasks[instance_id].append(task)

    def get_pending_tasks(self, instance_id: str | None = None) -> list[dict[str, Any]]:
        """Get pending human tasks.

        Args:
            instance_id: Optional instance ID to filter by.

        Returns:
            List of pending task records.
        """
        if instance_id:
            return self.pending_tasks.get(instance_id, [])
        # Return all pending tasks across instances
        all_tasks = []
        for tasks in self.pending_tasks.values():
            all_tasks.extend(tasks)
        return all_tasks

    def complete_task(self, instance_id: str, step_name: str) -> dict[str, Any] | None:
        """Mark a task as completed and remove from pending.

        Args:
            instance_id: Instance identifier.
            step_name: Name of the step to complete.

        Returns:
            The completed task record or None if not found.
        """
        if instance_id not in self.pending_tasks:
            return None

        tasks = self.pending_tasks[instance_id]
        for i, task in enumerate(tasks):
            if task.get("step_name") == step_name:
                return tasks.pop(i)
        return None


# Global instance store (would be replaced with proper persistence in production)
_instance_store = WorkflowInstanceStore()


async def provide_instance_store(state: State) -> WorkflowInstanceStore:  # noqa: ARG001
    """Provide the workflow instance store.

    Args:
        state: Litestar application state (unused, for DI signature).

    Returns:
        The workflow instance store.
    """
    return _instance_store


# =============================================================================
# Controller
# =============================================================================


class CiviWorkflowController(Controller):
    """Litestar controller for CiviCRM workflow management.

    Provides REST API endpoints for managing workflow definitions and
    instances, including listing, starting, monitoring, and completing
    human tasks.

    Routes:
        GET  /                      - List available workflow definitions
        POST /{name}/start          - Start a new workflow instance
        GET  /instances             - List workflow instances
        GET  /instances/{id}        - Get instance status and details
        POST /instances/{id}/complete - Complete a human task
        GET  /tasks                 - List pending human tasks

    Example:
        >>> # List available workflows
        >>> GET /api/civi/workflows/
        >>>
        >>> # Start a new workflow
        >>> POST /api/civi/workflows/contact-import/start
        >>> {"initial_context": {"file_path": "/tmp/contacts.csv"}}
        >>>
        >>> # Check instance status
        >>> GET / api / civi / workflows / instances / abc123
        >>>
        >>> # Complete a human task
        >>> POST / api / civi / workflows / instances / abc123 / complete
        >>> {"form_data": {"approved": true, "comments": "Looks good"}}
    """

    path = "/"
    tags = ["CiviCRM Workflows"]

    @get(
        path="/",
        summary="List Workflow Definitions",
        description="Retrieve all available workflow definitions that can be started.",
        operation_id="list_workflow_definitions",
        status_code=HTTP_200_OK,
    )
    async def list_definitions(
        self,
        workflow_registry: Any,  # noqa: ANN401
    ) -> WorkflowDefinitionsResponseDTO:
        """List all registered workflow definitions.

        Args:
            workflow_registry: Injected workflow registry.

        Returns:
            Response containing list of workflow definitions.
        """
        if not WORKFLOWS_AVAILABLE:
            return WorkflowDefinitionsResponseDTO(workflows=[], count=0)

        workflows: list[WorkflowDefinitionDTO] = []

        # Get registered workflows from registry
        if hasattr(workflow_registry, "get_all") or hasattr(workflow_registry, "list"):
            # Attempt to list workflows using common patterns
            try:
                if hasattr(workflow_registry, "get_all"):
                    registered = workflow_registry.get_all()
                else:
                    registered = workflow_registry.list()

                for name, workflow_def in registered.items():
                    steps = []
                    human_steps = []

                    # Extract step information from workflow definition
                    if hasattr(workflow_def, "steps"):
                        for step in workflow_def.steps:
                            step_name = getattr(step, "name", str(step))
                            steps.append(step_name)

                            # Check if it's a human step
                            if hasattr(step, "form_schema") or hasattr(step, "title"):
                                human_steps.append(step_name)

                    workflows.append(
                        WorkflowDefinitionDTO(
                            name=name,
                            description=getattr(workflow_def, "description", None),
                            steps=steps,
                            human_steps=human_steps,
                        ),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to list workflows from registry: %s", e)

        return WorkflowDefinitionsResponseDTO(
            workflows=workflows,
            count=len(workflows),
        )

    @post(
        path="/{workflow_name:str}/start",
        summary="Start Workflow",
        description="Start a new instance of the specified workflow.",
        operation_id="start_workflow",
        status_code=HTTP_201_CREATED,
    )
    async def start_workflow(
        self,
        workflow_name: str,
        workflow_registry: Any,  # noqa: ANN401
        workflow_engine: Any,  # noqa: ANN401
        civi_client: CiviClient,
        instance_store: WorkflowInstanceStore,
        data: StartWorkflowRequestDTO | None = None,
    ) -> StartWorkflowResponseDTO:
        """Start a new workflow instance.

        Creates a new instance of the specified workflow and begins
        execution. The workflow will run until it completes, fails,
        or reaches a human step requiring manual completion.

        Args:
            workflow_name: Name of the workflow to start.
            workflow_registry: Injected workflow registry.
            workflow_engine: Injected workflow execution engine.
            civi_client: Injected CiviClient for API operations.
            instance_store: Injected instance store.
            data: Optional initial context data.

        Returns:
            Response containing the new instance ID and status.

        Raises:
            NotFoundException: If workflow name is not found.
            HTTPException: If workflow execution fails to start.
        """
        if not WORKFLOWS_AVAILABLE:
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail="Workflow features are not available. Install litestar-workflows.",
            )

        # Get workflow definition from registry
        import contextlib

        workflow_def = None
        if hasattr(workflow_registry, "get"):
            workflow_def = workflow_registry.get(workflow_name)
        elif hasattr(workflow_registry, "__getitem__"):
            with contextlib.suppress(KeyError):
                workflow_def = workflow_registry[workflow_name]

        if workflow_def is None:
            raise NotFoundException(detail=f"Workflow '{workflow_name}' not found")

        # Create instance record
        import uuid

        instance_id = str(uuid.uuid4())
        initial_context = data.initial_context if data else {}

        instance_store.create_instance(
            instance_id=instance_id,
            workflow_name=workflow_name,
            initial_context=initial_context,
        )

        try:
            # Prepare execution context with CiviClient
            execution_context = {
                "civi_client": civi_client,
                **initial_context,
            }

            # Start workflow execution
            if hasattr(workflow_engine, "start"):
                await workflow_engine.start(
                    workflow_def,
                    instance_id=instance_id,
                    context=execution_context,
                )
            elif hasattr(workflow_engine, "execute"):
                # Some engines use execute instead of start
                await workflow_engine.execute(
                    workflow_def,
                    instance_id=instance_id,
                    context=execution_context,
                )

            instance_store.update_instance(instance_id, {"status": "running"})

            return StartWorkflowResponseDTO(
                instance_id=instance_id,
                workflow_name=workflow_name,
                status="running",
            )

        except Exception as e:
            logger.exception("Failed to start workflow '%s'", workflow_name)
            instance_store.update_instance(instance_id, {"status": "failed"})
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Failed to start workflow: {e}",
            ) from e

    @get(
        path="/instances",
        summary="List Workflow Instances",
        description="List workflow instances with optional filtering.",
        operation_id="list_workflow_instances",
        status_code=HTTP_200_OK,
    )
    async def list_instances(
        self,
        instance_store: WorkflowInstanceStore,
        workflow_name: str | None = Parameter(default=None, description="Filter by workflow name"),
        status: str | None = Parameter(default=None, description="Filter by status"),
        limit: int = Parameter(default=100, ge=1, le=500, description="Max results"),
        offset: int = Parameter(default=0, ge=0, description="Results to skip"),
    ) -> WorkflowInstancesResponseDTO:
        """List workflow instances with filtering.

        Args:
            instance_store: Injected instance store.
            workflow_name: Optional workflow name filter.
            status: Optional status filter.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            Response containing list of instances.
        """
        instances = instance_store.list_instances(
            workflow_name=workflow_name,
            status=status,
            limit=limit,
            offset=offset,
        )

        instance_dtos = [
            WorkflowInstanceDTO(
                instance_id=inst["instance_id"],
                workflow_name=inst["workflow_name"],
                status=inst["status"],
                current_step=inst.get("current_step"),
                started_at=inst.get("started_at"),
                completed_at=inst.get("completed_at"),
                context_data=_filter_sensitive_context(inst.get("context_data", {})),
            )
            for inst in instances
        ]

        return WorkflowInstancesResponseDTO(
            instances=instance_dtos,
            count=len(instance_dtos),
        )

    @get(
        path="/instances/{instance_id:str}",
        summary="Get Workflow Instance",
        description="Get detailed status and history for a workflow instance.",
        operation_id="get_workflow_instance",
        status_code=HTTP_200_OK,
    )
    async def get_instance(
        self,
        instance_id: str,
        instance_store: WorkflowInstanceStore,
    ) -> WorkflowInstanceDetailDTO:
        """Get detailed workflow instance information.

        Includes step execution history and any pending human tasks.

        Args:
            instance_id: Unique instance identifier.
            instance_store: Injected instance store.

        Returns:
            Detailed instance information.

        Raises:
            NotFoundException: If instance is not found.
        """
        instance = instance_store.get_instance(instance_id)
        if instance is None:
            raise NotFoundException(detail=f"Workflow instance '{instance_id}' not found")

        # Get step history
        history = instance_store.get_step_history(instance_id)
        history_dtos = [
            WorkflowStepHistoryDTO(
                step_name=h["step_name"],
                step_type=h.get("step_type", "machine"),
                status=h.get("status", "completed"),
                started_at=h.get("started_at"),
                completed_at=h.get("completed_at"),
                error=h.get("error"),
            )
            for h in history
        ]

        # Get pending tasks
        pending = instance_store.get_pending_tasks(instance_id)
        task_dtos = [
            HumanTaskDTO(
                instance_id=instance_id,
                step_name=t["step_name"],
                title=t.get("title", t["step_name"]),
                description=t.get("description"),
                form_schema=t.get("form_schema", {}),
                review_data=t.get("review_data", {}),
                created_at=t.get("created_at"),
            )
            for t in pending
        ]

        return WorkflowInstanceDetailDTO(
            instance_id=instance["instance_id"],
            workflow_name=instance["workflow_name"],
            status=instance["status"],
            current_step=instance.get("current_step"),
            started_at=instance.get("started_at"),
            completed_at=instance.get("completed_at"),
            context_data=_filter_sensitive_context(instance.get("context_data", {})),
            step_history=history_dtos,
            pending_tasks=task_dtos,
        )

    @post(
        path="/instances/{instance_id:str}/complete",
        summary="Complete Human Task",
        description="Submit form data to complete a pending human task.",
        operation_id="complete_workflow_task",
        status_code=HTTP_200_OK,
    )
    async def complete_task(
        self,
        instance_id: str,
        workflow_engine: Any,  # noqa: ANN401
        instance_store: WorkflowInstanceStore,
        data: CompleteTaskRequestDTO,
        step_name: str | None = Parameter(default=None, description="Specific step to complete"),
    ) -> WorkflowInstanceDTO:
        """Complete a pending human task.

        Submits form data for a human step and resumes workflow execution.

        Args:
            instance_id: Workflow instance identifier.
            workflow_engine: Injected workflow engine.
            instance_store: Injected instance store.
            data: Form data for the human step.
            step_name: Optional specific step name to complete.

        Returns:
            Updated instance status.

        Raises:
            NotFoundException: If instance or task is not found.
            HTTPException: If task completion fails.
        """
        if not WORKFLOWS_AVAILABLE:
            raise HTTPException(
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
                detail="Workflow features are not available.",
            )

        instance = instance_store.get_instance(instance_id)
        if instance is None:
            raise NotFoundException(detail=f"Workflow instance '{instance_id}' not found")

        # Get pending tasks
        pending = instance_store.get_pending_tasks(instance_id)
        if not pending:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="No pending human tasks for this instance",
            )

        # Find the task to complete
        task_to_complete = None
        if step_name:
            for task in pending:
                if task.get("step_name") == step_name:
                    task_to_complete = task
                    break
            if not task_to_complete:
                raise NotFoundException(detail=f"Task '{step_name}' not found for instance")
        else:
            # Complete the first pending task
            task_to_complete = pending[0]

        target_step = task_to_complete["step_name"]

        try:
            # Complete the task in the engine
            if hasattr(workflow_engine, "complete_human_step"):
                await workflow_engine.complete_human_step(
                    instance_id=instance_id,
                    step_name=target_step,
                    form_data=data.form_data,
                )
            elif hasattr(workflow_engine, "resume"):
                await workflow_engine.resume(
                    instance_id=instance_id,
                    step_data=data.form_data,
                )

            # Remove from pending
            instance_store.complete_task(instance_id, target_step)

            # Add to step history
            instance_store.add_step_history(
                instance_id,
                {
                    "step_name": target_step,
                    "step_type": "human",
                    "status": "completed",
                    "completed_at": datetime.now(tz=UTC),
                },
            )

            # Get updated instance (should exist since we verified it above)
            updated_instance = instance_store.get_instance(instance_id)
            assert updated_instance is not None  # Instance was verified at start of method

            return WorkflowInstanceDTO(
                instance_id=updated_instance["instance_id"],
                workflow_name=updated_instance["workflow_name"],
                status=updated_instance["status"],
                current_step=updated_instance.get("current_step"),
                started_at=updated_instance.get("started_at"),
                completed_at=updated_instance.get("completed_at"),
                context_data=_filter_sensitive_context(updated_instance.get("context_data", {})),
            )

        except Exception as e:
            logger.exception("Failed to complete task '%s' for instance '%s'", target_step, instance_id)
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Failed to complete task: {e}",
            ) from e

    @get(
        path="/tasks",
        summary="List Pending Tasks",
        description="List all pending human tasks across workflow instances.",
        operation_id="list_pending_tasks",
        status_code=HTTP_200_OK,
    )
    async def list_pending_tasks(
        self,
        instance_store: WorkflowInstanceStore,
        instance_id: str | None = Parameter(default=None, description="Filter by instance ID"),
    ) -> HumanTasksResponseDTO:
        """List pending human tasks.

        Args:
            instance_store: Injected instance store.
            instance_id: Optional instance ID filter.

        Returns:
            Response containing list of pending tasks.
        """
        tasks = instance_store.get_pending_tasks(instance_id)

        task_dtos = [
            HumanTaskDTO(
                instance_id=t.get("instance_id", instance_id or "unknown"),
                step_name=t["step_name"],
                title=t.get("title", t["step_name"]),
                description=t.get("description"),
                form_schema=t.get("form_schema", {}),
                review_data=t.get("review_data", {}),
                created_at=t.get("created_at"),
            )
            for t in tasks
        ]

        return HumanTasksResponseDTO(
            tasks=task_dtos,
            count=len(task_dtos),
        )


# =============================================================================
# Helper Functions
# =============================================================================


def _filter_sensitive_context(context: dict[str, Any]) -> dict[str, Any]:
    """Filter sensitive data from workflow context for API responses.

    Removes or masks fields that may contain sensitive information
    like API keys, credentials, or client instances.

    Args:
        context: Raw workflow context data.

    Returns:
        Filtered context safe for API response.
    """
    sensitive_keys = {
        "civi_client",
        "client",
        "api_key",
        "password",
        "secret",
        "token",
        "credential",
        "auth",
    }

    filtered = {}
    for key, value in context.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            filtered[key] = "[FILTERED]"
        elif isinstance(value, dict):
            filtered[key] = _filter_sensitive_context(value)
        else:
            # Only include serializable values
            try:
                msgspec.json.encode(value)
                filtered[key] = value
            except (TypeError, ValueError):
                filtered[key] = f"[{type(value).__name__}]"

    return filtered


# =============================================================================
# Router Factory
# =============================================================================


def get_workflow_router(
    config: WorkflowPluginConfig,
) -> Router:
    """Create a Litestar Router for workflow endpoints.

    Builds a router with the workflow controller and appropriate
    dependency providers based on the configuration.

    Args:
        config: Workflow plugin configuration.

    Returns:
        Configured Litestar Router.
    """
    # Combine workflow and instance store dependencies
    dependencies = {
        **get_workflow_dependency_providers(),
        "instance_store": Provide(provide_instance_store),
    }

    return Router(
        path=config.api_prefix,
        route_handlers=[CiviWorkflowController],
        tags=config.openapi_tags,
        dependencies=dependencies,
    )


# =============================================================================
# Initialization Functions
# =============================================================================


async def initialize_workflows(
    app: Litestar,
    config: WorkflowPluginConfig,
) -> None:
    """Initialize workflow registry and engine on application startup.

    Creates the workflow registry and execution engine, registers
    built-in workflows if configured, and stores them in app state.

    Args:
        app: Litestar application instance.
        config: Workflow plugin configuration.
    """
    if not WORKFLOWS_AVAILABLE:
        logger.warning(
            "litestar-workflows is not installed. Workflow features will not be available. "
            "Install with: pip install civi-py[workflows]",
        )
        return

    logger.info("Initializing CiviCRM workflow integration")

    try:
        from litestar_workflows import LocalExecutionEngine, WorkflowRegistry

        # Create registry
        registry = WorkflowRegistry()

        # Register built-in CiviCRM workflows if enabled
        if config.register_builtins:
            _register_builtin_workflows(registry)

        # Register custom workflows
        for workflow_class in config.custom_workflows:
            registry.register(workflow_class)
            name = getattr(workflow_class, "__workflow_name__", workflow_class.__name__)
            logger.debug("Registered custom workflow: %s", name)

        # Create execution engine
        engine = LocalExecutionEngine(registry=registry)

        # Store in app state
        setattr(app.state, WORKFLOW_REGISTRY_STATE_KEY, registry)
        setattr(app.state, WORKFLOW_ENGINE_STATE_KEY, engine)

        workflow_count = len(registry._workflow_classes) if hasattr(registry, "_workflow_classes") else 0
        logger.info("Workflow integration initialized with %d workflows", workflow_count)

    except ImportError:
        logger.exception("Failed to import litestar-workflows components")
    except Exception:
        logger.exception("Failed to initialize workflow integration")


async def cleanup_workflows(app: Litestar) -> None:
    """Clean up workflow resources on application shutdown.

    Args:
        app: Litestar application instance.
    """
    engine = getattr(app.state, WORKFLOW_ENGINE_STATE_KEY, None)
    if engine is not None:
        # Clean up engine if it has a close method
        if hasattr(engine, "close"):
            await engine.close()
        elif hasattr(engine, "shutdown"):
            await engine.shutdown()

        delattr(app.state, WORKFLOW_ENGINE_STATE_KEY)

    if hasattr(app.state, WORKFLOW_REGISTRY_STATE_KEY):
        delattr(app.state, WORKFLOW_REGISTRY_STATE_KEY)

    logger.info("Workflow integration cleanup complete")


def _register_builtin_workflows(registry: Any) -> None:  # noqa: ANN401, ARG001
    """Register built-in CiviCRM workflow templates.

    Args:
        registry: WorkflowRegistry instance.
    """
    # Note: Built-in workflow templates would be imported from
    # civicrm_py.contrib.workflows.templates once implemented
    # For now, this is a placeholder for future expansion

    logger.debug("Built-in workflow registration placeholder")


__all__ = [
    "WORKFLOW_ENGINE_STATE_KEY",
    "WORKFLOW_REGISTRY_STATE_KEY",
    "CiviWorkflowController",
    "CompleteTaskRequestDTO",
    "HumanTaskDTO",
    "HumanTasksResponseDTO",
    "StartWorkflowRequestDTO",
    "StartWorkflowResponseDTO",
    "WorkflowDefinitionDTO",
    "WorkflowDefinitionsResponseDTO",
    "WorkflowInstanceDTO",
    "WorkflowInstanceDetailDTO",
    "WorkflowInstanceStore",
    "WorkflowInstancesResponseDTO",
    "WorkflowPluginConfig",
    "WorkflowStepHistoryDTO",
    "cleanup_workflows",
    "get_workflow_dependency_providers",
    "get_workflow_router",
    "initialize_workflows",
    "provide_instance_store",
    "provide_workflow_engine",
    "provide_workflow_registry",
]
