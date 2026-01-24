"""CiviCRM workflow step primitives for litestar-workflows.

Provides reusable workflow steps for common CiviCRM operations:

- CiviFetchStep: Machine step for fetching data from CiviCRM
- CiviMutateStep: Machine step for create/update/delete operations
- CiviApprovalStep: Human step for approval workflows
- CiviSyncStep: Machine step for syncing CiviCRM data to local database

These primitives integrate with litestar-workflows to enable declarative
workflow definitions with CiviCRM backend operations.

Example:
    >>> from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE
    >>> from civicrm_py.contrib.workflows.steps import CiviFetchStep, CiviApprovalStep
    >>>
    >>> if WORKFLOWS_AVAILABLE:
    ...     fetch_contacts = CiviFetchStep(
    ...         name="fetch_contacts",
    ...         entity="Contact",
    ...         filters={"is_deleted": False},
    ...         select=["id", "display_name", "email"],
    ...         limit=100,
    ...         context_key="contacts",
    ...     )
    ...     review_step = CiviApprovalStep(
    ...         name="review_contacts",
    ...         title="Review Contact Updates",
    ...         data_context_key="contacts",
    ...         show_fields=["display_name", "email"],
    ...     )

This module requires the optional `workflows` dependency:

    pip install civi-py[workflows]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE, require_workflows

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient

    # For type checking, always use litestar_workflows types when available
    try:
        from litestar_workflows import (
            BaseHumanStep as _BaseHumanStep,
        )
        from litestar_workflows import (
            BaseMachineStep as _BaseMachineStep,
        )
        from litestar_workflows import (
            WorkflowContext as _WorkflowContext,
        )
    except ImportError:
        # Define protocol-like stubs for type checking when library not installed
        class _BaseMachineStep:
            """Type stub for BaseMachineStep."""

            name: str
            description: str

            async def execute(self, context: Any) -> None: ...

        class _BaseHumanStep:
            """Type stub for BaseHumanStep."""

            name: str
            title: str
            description: str
            form_schema: dict[str, Any]

        class _WorkflowContext:
            """Type stub for WorkflowContext."""

            def get(self, key: str, default: Any = None) -> Any: ...
            def set(self, key: str, value: Any) -> None: ...


# Runtime imports: use real classes or stubs
if WORKFLOWS_AVAILABLE:
    from litestar_workflows import BaseHumanStep, BaseMachineStep, WorkflowContext
else:
    # Provide stub base classes for runtime when litestar-workflows is not installed
    class BaseMachineStep:
        """Stub for BaseMachineStep when litestar-workflows is not installed."""

        name: str
        description: str

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

        async def execute(self, context: Any) -> None:
            """Execute stub."""
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class BaseHumanStep:
        """Stub for BaseHumanStep when litestar-workflows is not installed."""

        name: str
        title: str
        description: str
        form_schema: dict[str, Any]

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class WorkflowContext:
        """Stub for WorkflowContext when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

        def get(self, key: str, default: Any = None) -> Any:
            """Get stub."""
            return default

        def set(self, key: str, value: Any) -> None:
            """Set stub."""


logger = logging.getLogger(__name__)


class CiviWorkflowError(Exception):
    """Base exception for CiviCRM workflow step errors.

    Raised when workflow steps encounter errors during execution,
    such as missing client, invalid configuration, or API failures.
    """

    def __init__(self, message: str, *, step_name: str | None = None, details: dict[str, Any] | None = None) -> None:
        """Initialize CiviWorkflowError.

        Args:
            message: Error description.
            step_name: Name of the workflow step that failed.
            details: Additional error context.
        """
        super().__init__(message)
        self.message = message
        self.step_name = step_name
        self.details = details or {}


def _get_client_from_context(context: WorkflowContext, step_name: str) -> CiviClient:
    """Extract CiviClient from workflow context.

    Args:
        context: The workflow execution context.
        step_name: Name of the step requesting the client (for error messages).

    Returns:
        The CiviClient instance from context.

    Raises:
        CiviWorkflowError: If no client is found in context.
    """
    client = context.get("civi_client")
    if client is None:
        msg = (
            "CiviClient not found in workflow context. "
            "Ensure 'civi_client' is set in the context before executing CiviCRM steps."
        )
        raise CiviWorkflowError(msg, step_name=step_name)
    return client


def _convert_filters_to_where(filters: dict[str, Any]) -> list[list[Any]]:
    """Convert dictionary filters to CiviCRM API v4 where clause format.

    Args:
        filters: Dictionary of field_name: value pairs.

    Returns:
        List of where clause conditions in API v4 format.

    Example:
        >>> _convert_filters_to_where({"is_deleted": False, "contact_type": "Individual"})
        [["is_deleted", "=", False], ["contact_type", "=", "Individual"]]
    """
    where: list[list[Any]] = []
    for field_name, value in filters.items():
        if isinstance(value, dict):
            # Handle operator-based filters: {"age": {">=": 18}}
            for operator, operand in value.items():
                where.append([field_name, operator, operand])
        else:
            # Simple equality filter
            where.append([field_name, "=", value])
    return where


@dataclass
class CiviFetchStep(BaseMachineStep):  # type: ignore[misc]
    """Machine step that fetches data from CiviCRM.

    Executes a CiviCRM API v4 get request and stores the results
    in the workflow context for subsequent steps to use.

    Attributes:
        name: Unique step identifier within the workflow.
        description: Human-readable description of what this step does.
        entity: CiviCRM entity name (e.g., "Contact", "Activity", "Contribution").
        filters: Dictionary of filter conditions. Keys are field names, values
            can be direct values for equality or dicts for operators
            (e.g., {"age": {">=": 18}}).
        select: List of fields to include in the response. If None, returns
            default fields.
        order_by: Dictionary of field names to sort directions ("ASC" or "DESC").
        limit: Maximum number of records to fetch. Defaults to 100.
        offset: Number of records to skip for pagination.
        context_key: Key under which to store results in workflow context.

    Example:
        >>> fetch_contacts = CiviFetchStep(
        ...     name="fetch_active_contacts",
        ...     description="Fetch all active contacts for review",
        ...     entity="Contact",
        ...     filters={"is_deleted": False, "contact_type": "Individual"},
        ...     select=["id", "display_name", "email_primary.email"],
        ...     order_by={"display_name": "ASC"},
        ...     limit=100,
        ...     context_key="contacts_to_review",
        ... )
    """

    name: str
    description: str = ""
    entity: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    select: list[str] | None = None
    order_by: dict[str, str] | None = None
    limit: int = 100
    offset: int = 0
    context_key: str = "fetched_data"

    def __post_init__(self) -> None:
        """Validate step configuration after initialization."""
        require_workflows()
        if not self.entity:
            msg = "entity is required for CiviFetchStep"
            raise ValueError(msg)
        if not self.name:
            msg = "name is required for CiviFetchStep"
            raise ValueError(msg)
        if not self.description:
            self.description = f"Fetch {self.entity} records from CiviCRM"

    async def execute(self, context: WorkflowContext) -> None:
        """Execute the fetch operation against CiviCRM.

        Retrieves data from CiviCRM based on the configured filters
        and stores the results in the workflow context.

        Args:
            context: Workflow execution context containing the CiviClient
                and shared state.

        Raises:
            CiviWorkflowError: If client is not in context or API call fails.
        """
        client = _get_client_from_context(context, self.name)

        logger.debug(
            "CiviFetchStep[%s]: Fetching %s with filters=%s, select=%s, limit=%d",
            self.name,
            self.entity,
            self.filters,
            self.select,
            self.limit,
        )

        try:
            where = _convert_filters_to_where(self.filters) if self.filters else None

            response = await client.get(
                self.entity,
                select=self.select,
                where=where,
                order_by=self.order_by,
                limit=self.limit,
                offset=self.offset,
            )

            # Store results in context
            context.set(self.context_key, response.values)
            context.set(f"{self.context_key}_count", response.count)

            fetched_count = len(response.values) if response.values else 0
            logger.info(
                "CiviFetchStep[%s]: Fetched %d %s records",
                self.name,
                fetched_count,
                self.entity,
            )

        except Exception as e:
            logger.exception("CiviFetchStep[%s]: Failed to fetch %s", self.name, self.entity)
            msg = f"Failed to fetch {self.entity}: {e}"
            raise CiviWorkflowError(
                msg,
                step_name=self.name,
                details={"entity": self.entity, "filters": self.filters},
            ) from e


@dataclass
class CiviMutateStep(BaseMachineStep):  # type: ignore[misc]
    """Machine step for create/update/delete operations on CiviCRM.

    Performs mutation operations on CiviCRM entities using data from
    the workflow context.

    Attributes:
        name: Unique step identifier within the workflow.
        description: Human-readable description of what this step does.
        entity: CiviCRM entity name (e.g., "Contact", "Activity").
        action: Mutation action to perform: "create", "update", or "delete".
        data_context_key: Key in workflow context containing the data to mutate.
            For "create" and "update": expects dict or list of dicts with field values.
            For "delete": expects dict or list of dicts with "id" field.
        result_context_key: Key under which to store mutation results in context.
        batch_size: Number of records to process per API call for batch operations.

    Example:
        >>> # Create new contacts from processed data
        >>> create_contacts = CiviMutateStep(
        ...     name="create_contacts",
        ...     description="Create new contacts from import data",
        ...     entity="Contact",
        ...     action="create",
        ...     data_context_key="contacts_to_create",
        ...     result_context_key="created_contacts",
        ... )
        >>>
        >>> # Update existing contacts
        >>> update_contacts = CiviMutateStep(
        ...     name="update_contacts",
        ...     description="Update contact email addresses",
        ...     entity="Contact",
        ...     action="update",
        ...     data_context_key="contacts_to_update",
        ...     result_context_key="updated_contacts",
        ... )
    """

    name: str
    description: str = ""
    entity: str = ""
    action: Literal["create", "update", "delete"] = "create"
    data_context_key: str = "mutation_data"
    result_context_key: str = "mutation_results"
    batch_size: int = 50

    def __post_init__(self) -> None:
        """Validate step configuration after initialization."""
        require_workflows()
        if not self.entity:
            msg = "entity is required for CiviMutateStep"
            raise ValueError(msg)
        if not self.name:
            msg = "name is required for CiviMutateStep"
            raise ValueError(msg)
        if self.action not in ("create", "update", "delete"):
            msg = f"action must be 'create', 'update', or 'delete', got '{self.action}'"
            raise ValueError(msg)
        if not self.description:
            self.description = f"{self.action.capitalize()} {self.entity} records in CiviCRM"

    async def _process_create(
        self,
        client: CiviClient,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process a create operation for a single record."""
        response = await client.create(self.entity, record)
        return list(response.values) if response.values else []

    async def _process_update(
        self,
        client: CiviClient,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process an update operation for a single record."""
        if "id" not in record:
            msg = f"Record missing 'id' field for update: {record}"
            raise CiviWorkflowError(msg, step_name=self.name)

        record_id = record.pop("id")
        response = await client.update(
            self.entity,
            record,
            [["id", "=", record_id]],
        )
        return list(response.values) if response.values else []

    async def _process_delete(
        self,
        client: CiviClient,
        record: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Process a delete operation for a single record."""
        if "id" not in record:
            msg = f"Record missing 'id' field for delete: {record}"
            raise CiviWorkflowError(msg, step_name=self.name)

        await client.delete(self.entity, [["id", "=", record["id"]]])
        return [{"id": record["id"], "deleted": True}]

    async def execute(self, context: WorkflowContext) -> None:
        """Execute the mutation operation against CiviCRM.

        Retrieves data from context and performs the configured
        mutation action on CiviCRM.

        Args:
            context: Workflow execution context containing the CiviClient
                and shared state.

        Raises:
            CiviWorkflowError: If client is not in context, data is missing,
                or API call fails.
        """
        client = _get_client_from_context(context, self.name)

        data = context.get(self.data_context_key)
        if data is None:
            msg = f"No data found in context at key '{self.data_context_key}'"
            raise CiviWorkflowError(msg, step_name=self.name)

        # Normalize to list for consistent processing
        records = data if isinstance(data, list) else [data]

        if not records:
            logger.info("CiviMutateStep[%s]: No records to %s", self.name, self.action)
            context.set(self.result_context_key, [])
            return

        logger.debug(
            "CiviMutateStep[%s]: Processing %s for %d %s records",
            self.name,
            self.action,
            len(records),
            self.entity,
        )

        try:
            results = await self._process_records(client, records)

            context.set(self.result_context_key, results)
            context.set(f"{self.result_context_key}_count", len(results))

            logger.info(
                "CiviMutateStep[%s]: Successfully %sd %d %s records",
                self.name,
                self.action,
                len(results),
                self.entity,
            )

        except CiviWorkflowError:
            raise
        except Exception as e:
            logger.exception("CiviMutateStep[%s]: Failed to %s %s", self.name, self.action, self.entity)
            msg = f"Failed to {self.action} {self.entity}: {e}"
            raise CiviWorkflowError(
                msg,
                step_name=self.name,
                details={"entity": self.entity, "action": self.action},
            ) from e

    async def _process_records(
        self,
        client: CiviClient,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Process all records according to the configured action.

        Args:
            client: CiviCRM client instance.
            records: List of records to process.

        Returns:
            List of result dictionaries from the operations.
        """
        results: list[dict[str, Any]] = []

        action_handlers = {
            "create": self._process_create,
            "update": self._process_update,
            "delete": self._process_delete,
        }
        handler = action_handlers[self.action]

        for record in records:
            result = await handler(client, record)
            results.extend(result)

        return results


@dataclass
class CiviApprovalStep(BaseHumanStep):  # type: ignore[misc]
    """Human step for approval workflows with CiviCRM data.

    Provides a form for human reviewers to approve or reject
    CiviCRM data changes with optional comments.

    Attributes:
        name: Unique step identifier within the workflow.
        title: Human-readable title displayed to the reviewer.
        description: Detailed description of what needs to be reviewed.
        data_context_key: Key in workflow context containing data to review.
        show_fields: List of field names to display for review. If None,
            displays all fields in the data.
        require_comments_on_reject: Whether to require comments when rejecting.

    The form schema provides:
        - approved (boolean): Whether the data is approved
        - comments (string): Optional reviewer comments
        - reviewer_id (integer): Optional reviewer contact ID

    Example:
        >>> review_step = CiviApprovalStep(
        ...     name="review_contact_merge",
        ...     title="Review Contact Merge",
        ...     description="Review and approve the proposed contact merge",
        ...     data_context_key="merge_proposal",
        ...     show_fields=["display_name", "email_primary", "phone_primary"],
        ...     require_comments_on_reject=True,
        ... )
    """

    name: str
    title: str = ""
    description: str = ""
    data_context_key: str = "data_to_review"
    show_fields: list[str] | None = None
    require_comments_on_reject: bool = False
    form_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize form schema and validate configuration."""
        require_workflows()
        if not self.name:
            msg = "name is required for CiviApprovalStep"
            raise ValueError(msg)
        if not self.title:
            self.title = f"Review {self.name}"
        if not self.description:
            self.description = f"Review and approve data from '{self.data_context_key}'"

        # Build form schema
        self.form_schema = {
            "type": "object",
            "title": self.title,
            "description": self.description,
            "properties": {
                "approved": {
                    "type": "boolean",
                    "title": "Approve?",
                    "description": "Select to approve or leave unchecked to reject",
                    "default": False,
                },
                "comments": {
                    "type": "string",
                    "title": "Comments",
                    "description": "Optional comments about your decision",
                    "maxLength": 2000,
                },
                "reviewer_id": {
                    "type": "integer",
                    "title": "Reviewer Contact ID",
                    "description": "CiviCRM contact ID of the reviewer (optional)",
                },
            },
            "required": ["approved"],
        }

        # Add conditional requirement for comments on rejection
        if self.require_comments_on_reject:
            self.form_schema["allOf"] = [
                {
                    "if": {"properties": {"approved": {"const": False}}},
                    "then": {"required": ["approved", "comments"]},
                },
            ]

    def get_review_data(self, context: WorkflowContext) -> dict[str, Any]:
        """Extract data to display for review from context.

        Args:
            context: Workflow execution context.

        Returns:
            Dictionary containing the data to display, filtered to
            show_fields if specified.
        """
        data = context.get(self.data_context_key, {})

        if not data:
            return {}

        # Handle list of records - show summary
        if isinstance(data, list):
            if not data:
                return {"_summary": "No records to review"}

            if self.show_fields:
                filtered_records = [{k: v for k, v in record.items() if k in self.show_fields} for record in data]
            else:
                filtered_records = data

            return {
                "_summary": f"{len(data)} records to review",
                "_records": filtered_records,
            }

        # Single record
        if self.show_fields:
            return {k: v for k, v in data.items() if k in self.show_fields}

        return data


@dataclass
class CiviSyncStep(BaseMachineStep):  # type: ignore[misc]
    """Machine step for syncing CiviCRM data to/from local database.

    Synchronizes data between CiviCRM and a local database cache
    using the sqlspec repository layer. This enables offline access
    and improved query performance for frequently accessed data.

    Attributes:
        name: Unique step identifier within the workflow.
        description: Human-readable description of what this step does.
        entity: CiviCRM entity to sync (e.g., "Contact", "Activity").
        direction: Sync direction - "from_civi" pulls from CiviCRM to local,
            "to_civi" pushes local changes to CiviCRM.
        filters: Filter conditions to limit which records are synced.
        select: Fields to include in the sync. If None, syncs all fields.
        batch_size: Number of records to process per batch.
        sync_result_key: Key to store sync results in context.
        repository_key: Key in context for the sqlspec repository instance.

    Example:
        >>> # Sync contacts from CiviCRM to local cache
        >>> sync_contacts = CiviSyncStep(
        ...     name="sync_contacts",
        ...     description="Sync active contacts to local database",
        ...     entity="Contact",
        ...     direction="from_civi",
        ...     filters={"is_deleted": False},
        ...     select=["id", "display_name", "email_primary.email"],
        ...     batch_size=500,
        ... )

    Note:
        This step requires both the 'workflows' and 'sqlspec' optional
        dependencies to be installed:

            pip install 'civi-py[workflows,sqlspec]'
    """

    name: str
    description: str = ""
    entity: str = ""
    direction: Literal["from_civi", "to_civi"] = "from_civi"
    filters: dict[str, Any] = field(default_factory=dict)
    select: list[str] | None = None
    batch_size: int = 500
    sync_result_key: str = "sync_results"
    repository_key: str = "civi_repository"

    def __post_init__(self) -> None:
        """Validate step configuration after initialization."""
        require_workflows()
        if not self.entity:
            msg = "entity is required for CiviSyncStep"
            raise ValueError(msg)
        if not self.name:
            msg = "name is required for CiviSyncStep"
            raise ValueError(msg)
        if self.direction not in ("from_civi", "to_civi"):
            msg = f"direction must be 'from_civi' or 'to_civi', got '{self.direction}'"
            raise ValueError(msg)
        if not self.description:
            direction_desc = "from CiviCRM" if self.direction == "from_civi" else "to CiviCRM"
            self.description = f"Sync {self.entity} records {direction_desc}"

    async def execute(self, context: WorkflowContext) -> None:
        """Execute the sync operation.

        Synchronizes data between CiviCRM and the local database
        based on the configured direction.

        Args:
            context: Workflow execution context containing the CiviClient,
                repository, and shared state.

        Raises:
            CiviWorkflowError: If client or repository is not in context,
                or sync operation fails.
        """
        client = _get_client_from_context(context, self.name)

        repository = context.get(self.repository_key)
        if repository is None:
            logger.warning(
                "CiviSyncStep[%s]: No repository found at key '%s'. Falling back to context-only storage.",
                self.name,
                self.repository_key,
            )

        logger.debug(
            "CiviSyncStep[%s]: Syncing %s %s with filters=%s",
            self.name,
            self.entity,
            self.direction,
            self.filters,
        )

        try:
            if self.direction == "from_civi":
                results = await self._sync_from_civi(client, repository, context)
            else:
                results = await self._sync_to_civi(client, repository, context)

            context.set(self.sync_result_key, results)

            logger.info(
                "CiviSyncStep[%s]: Synced %d %s records %s",
                self.name,
                results.get("synced_count", 0),
                self.entity,
                self.direction,
            )

        except CiviWorkflowError:
            raise
        except Exception as e:
            logger.exception("CiviSyncStep[%s]: Failed to sync %s", self.name, self.entity)
            msg = f"Failed to sync {self.entity}: {e}"
            raise CiviWorkflowError(
                msg,
                step_name=self.name,
                details={"entity": self.entity, "direction": self.direction},
            ) from e

    async def _sync_from_civi(
        self,
        client: CiviClient,
        repository: Any,
        context: WorkflowContext,
    ) -> dict[str, Any]:
        """Sync data from CiviCRM to local storage.

        Args:
            client: CiviCRM client instance.
            repository: Optional sqlspec repository for persistence.
            context: Workflow context for fallback storage.

        Returns:
            Dictionary containing sync statistics.
        """
        all_records: list[dict[str, Any]] = []
        offset = 0
        total_fetched = 0

        where = _convert_filters_to_where(self.filters) if self.filters else None

        # Fetch in batches
        while True:
            response = await client.get(
                self.entity,
                select=self.select,
                where=where,
                limit=self.batch_size,
                offset=offset,
            )

            if not response.values:
                break

            all_records.extend(response.values)
            total_fetched += len(response.values)
            offset += self.batch_size

            # Check if we've fetched all available records
            if len(response.values) < self.batch_size:
                break

        # Store to repository if available
        if repository is not None:
            try:
                # Attempt to use repository's batch upsert
                # The exact API depends on sqlspec implementation
                await self._store_to_repository(repository, all_records)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "CiviSyncStep[%s]: Failed to store to repository: %s. Using context storage.",
                    self.name,
                    e,
                )
                context.set(f"{self.entity.lower()}_cache", all_records)
        else:
            # Fallback to context storage
            context.set(f"{self.entity.lower()}_cache", all_records)

        return {
            "synced_count": total_fetched,
            "entity": self.entity,
            "direction": "from_civi",
            "filters_applied": self.filters,
        }

    async def _sync_to_civi(
        self,
        client: CiviClient,
        repository: Any,
        context: WorkflowContext,
    ) -> dict[str, Any]:
        """Sync data from local storage to CiviCRM.

        Args:
            client: CiviCRM client instance.
            repository: Optional sqlspec repository for persistence.
            context: Workflow context for fallback storage.

        Returns:
            Dictionary containing sync statistics.
        """
        # Get records to sync from repository or context
        records_to_sync: list[dict[str, Any]] = []

        if repository is not None:
            try:
                records_to_sync = await self._fetch_from_repository(repository)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "CiviSyncStep[%s]: Failed to fetch from repository: %s. Using context.",
                    self.name,
                    e,
                )
                records_to_sync = context.get(f"{self.entity.lower()}_cache", [])
        else:
            records_to_sync = context.get(f"{self.entity.lower()}_cache", [])

        if not records_to_sync:
            return {
                "synced_count": 0,
                "entity": self.entity,
                "direction": "to_civi",
                "message": "No records to sync",
            }

        # Sync to CiviCRM
        created_count = 0
        updated_count = 0
        errors: list[dict[str, Any]] = []

        for record in records_to_sync:
            try:
                if record.get("id"):
                    # Update existing
                    record_id = record.pop("id")
                    await client.update(self.entity, record, [["id", "=", record_id]])
                    updated_count += 1
                else:
                    # Create new
                    await client.create(self.entity, record)
                    created_count += 1
            except Exception as e:  # noqa: BLE001
                errors.append({"record": record, "error": str(e)})

        return {
            "synced_count": created_count + updated_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": len(errors),
            "errors": errors[:10] if errors else [],  # Limit error details
            "entity": self.entity,
            "direction": "to_civi",
        }

    async def _store_to_repository(
        self,
        repository: Any,
        records: list[dict[str, Any]],
    ) -> None:
        """Store records to sqlspec repository.

        Args:
            repository: sqlspec repository instance.
            records: Records to store.

        Note:
            This method attempts to use common sqlspec repository patterns.
            The exact implementation may need adjustment based on the
            repository interface.
        """
        # Try common repository methods
        if hasattr(repository, "upsert_many"):
            await repository.upsert_many(records)
        elif hasattr(repository, "add_many"):
            await repository.add_many(records)
        elif hasattr(repository, "add"):
            for record in records:
                await repository.add(record)
        else:
            msg = "Repository does not support batch operations"
            raise NotImplementedError(msg)

    async def _fetch_from_repository(
        self,
        repository: Any,
    ) -> list[dict[str, Any]]:
        """Fetch records from sqlspec repository.

        Args:
            repository: sqlspec repository instance.

        Returns:
            List of records from the repository.

        Note:
            This method attempts to use common sqlspec repository patterns.
            The exact implementation may need adjustment based on the
            repository interface.
        """
        # Try common repository methods
        if hasattr(repository, "list"):
            result = await repository.list()
            return list(result) if result else []
        if hasattr(repository, "get_all"):
            result = await repository.get_all()
            return list(result) if result else []
        msg = "Repository does not support list operations"
        raise NotImplementedError(msg)


__all__ = [
    "CiviApprovalStep",
    "CiviFetchStep",
    "CiviMutateStep",
    "CiviSyncStep",
    "CiviWorkflowError",
]
