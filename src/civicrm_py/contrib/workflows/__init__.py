"""Litestar Workflows integration for civi-py.

Provides workflow automation for CiviCRM operations using litestar-workflows:

- WorkflowDefinition: Define multi-step CiviCRM workflows
- BaseMachineStep: Automated steps (API calls, data processing)
- BaseHumanStep: Manual approval/review steps
- WorkflowContext: Shared state across workflow execution
- Edge: Define transitions between workflow steps

CiviCRM-Specific Step Primitives:
- CiviFetchStep: Machine step for fetching data from CiviCRM
- CiviMutateStep: Machine step for create/update/delete operations
- CiviApprovalStep: Human step for approval workflows with CiviCRM data
- CiviSyncStep: Machine step for syncing CiviCRM data to local database

Pre-built Workflow Templates:
- ContactSyncWorkflow: Fetch contacts, human review, sync to local database
- BulkUpdateWorkflow: Select entities, approve changes, execute bulk update
- MembershipRenewalWorkflow: Check expiring memberships, notify, process renewals
- DonationProcessingWorkflow: Validate donation, approve (conditional), create contribution

This module requires the optional `workflows` dependency:

    pip install civi-py[workflows]

Quick Start:
    >>> from civicrm_py.contrib.workflows import (
    ...     WORKFLOWS_AVAILABLE,
    ...     require_workflows,
    ...     WorkflowDefinition,
    ...     CiviFetchStep,
    ...     CiviApprovalStep,
    ... )
    >>>
    >>> if WORKFLOWS_AVAILABLE:
    ...     # Define a workflow with CiviCRM steps
    ...     fetch_contacts = CiviFetchStep(
    ...         name="fetch_contacts",
    ...         entity="Contact",
    ...         filters={"is_deleted": False},
    ...         limit=100,
    ...         context_key="contacts",
    ...     )

Graceful Degradation:
    When litestar-workflows is not installed, this module exports placeholder
    values (None) for the workflow types. Use WORKFLOWS_AVAILABLE to check
    availability before using workflow features, or call require_workflows()
    to raise an informative ImportError.

Example with graceful degradation:
    >>> from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE, require_workflows
    >>>
    >>> def setup_workflows():
    ...     require_workflows()  # Raises ImportError if not available
    ...     # ... proceed with workflow setup
"""

from __future__ import annotations

from typing import Any

try:
    from litestar_workflows import (
        BaseHumanStep,
        BaseMachineStep,
        Edge,
        WorkflowContext,
        WorkflowDefinition,
    )

    WORKFLOWS_AVAILABLE = True
except ImportError:
    WORKFLOWS_AVAILABLE = False

    # Provide stub classes for type checking and graceful degradation
    class BaseHumanStep:
        """Stub for BaseHumanStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class BaseMachineStep:
        """Stub for BaseMachineStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class Edge:
        """Stub for Edge when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class WorkflowContext:
        """Stub for WorkflowContext when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class WorkflowDefinition:
        """Stub for WorkflowDefinition when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")


def require_workflows() -> None:
    """Raise ImportError if litestar-workflows is not installed.

    Call this function at the start of any code that requires workflow
    features to provide a clear error message to users.

    Raises:
        ImportError: If litestar-workflows is not installed.

    Example:
        >>> from civicrm_py.contrib.workflows import require_workflows
        >>>
        >>> def my_workflow_function():
        ...     require_workflows()
        ...     # ... workflow code here
    """
    if not WORKFLOWS_AVAILABLE:
        msg = "litestar-workflows is required for workflow features. Install with: pip install civi-py[workflows]"
        raise ImportError(msg)


# Lazy import of step classes to avoid circular imports and allow graceful degradation
def __getattr__(name: str) -> type:
    """Lazy import of CiviCRM workflow step classes.

    Args:
        name: Attribute name to retrieve.

    Returns:
        The requested step class.

    Raises:
        AttributeError: If the attribute is not a valid step class.
    """
    _step_classes = {
        "CiviFetchStep",
        "CiviMutateStep",
        "CiviApprovalStep",
        "CiviSyncStep",
        "CiviWorkflowError",
    }

    _template_classes = {
        "ContactSyncWorkflow",
        "BulkUpdateWorkflow",
        "MembershipRenewalWorkflow",
        "DonationProcessingWorkflow",
    }

    if name in _step_classes:
        from civicrm_py.contrib.workflows.steps import (
            CiviApprovalStep,
            CiviFetchStep,
            CiviMutateStep,
            CiviSyncStep,
            CiviWorkflowError,
        )

        _classes = {
            "CiviFetchStep": CiviFetchStep,
            "CiviMutateStep": CiviMutateStep,
            "CiviApprovalStep": CiviApprovalStep,
            "CiviSyncStep": CiviSyncStep,
            "CiviWorkflowError": CiviWorkflowError,
        }
        return _classes[name]

    if name in _template_classes:
        from civicrm_py.contrib.workflows.templates import (
            BulkUpdateWorkflow,
            ContactSyncWorkflow,
            DonationProcessingWorkflow,
            MembershipRenewalWorkflow,
        )

        _templates = {
            "ContactSyncWorkflow": ContactSyncWorkflow,
            "BulkUpdateWorkflow": BulkUpdateWorkflow,
            "MembershipRenewalWorkflow": MembershipRenewalWorkflow,
            "DonationProcessingWorkflow": DonationProcessingWorkflow,
        }
        return _templates[name]

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "WORKFLOWS_AVAILABLE",
    "BaseHumanStep",
    "BaseMachineStep",
    "BulkUpdateWorkflow",
    "CiviApprovalStep",
    "CiviFetchStep",
    "CiviMutateStep",
    "CiviSyncStep",
    "CiviWorkflowError",
    "ContactSyncWorkflow",
    "DonationProcessingWorkflow",
    "Edge",
    "MembershipRenewalWorkflow",
    "WorkflowContext",
    "WorkflowDefinition",
    "require_workflows",
]
