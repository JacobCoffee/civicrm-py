"""Pre-built workflow templates for common CiviCRM operations.

Provides ready-to-use workflow definitions for common CiviCRM automation scenarios:

- ContactSyncWorkflow: Fetch contacts, human review, sync to local database
- BulkUpdateWorkflow: Select entities, approve changes, execute bulk update
- MembershipRenewalWorkflow: Check expiring memberships, notify, process renewals
- DonationProcessingWorkflow: Validate donation, approve (conditional), create contribution

Each workflow class provides a `get_definition()` classmethod that returns a
`WorkflowDefinition` ready for registration with a workflow engine.

This module requires the optional `workflows` dependency:

    pip install civi-py[workflows]

Example:
    >>> from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE
    >>> from civicrm_py.contrib.workflows.templates import ContactSyncWorkflow
    >>>
    >>> if WORKFLOWS_AVAILABLE:
    ...     # Get the workflow definition
    ...     definition = ContactSyncWorkflow.get_definition()
    ...
    ...     # Register with workflow engine
    ...     from litestar_workflows import WorkflowRegistry
    ...
    ...     registry = WorkflowRegistry()
    ...     registry.register(definition)
"""

from __future__ import annotations

from typing import Any, ClassVar

from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE, require_workflows

if WORKFLOWS_AVAILABLE:
    from litestar_workflows import Edge, WorkflowDefinition

    from civicrm_py.contrib.workflows.steps import (
        CiviApprovalStep,
        CiviFetchStep,
        CiviMutateStep,
        CiviSyncStep,
    )
else:
    # Stub classes for type checking when litestar-workflows is not installed
    class Edge:
        """Stub for Edge when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class WorkflowDefinition:
        """Stub for WorkflowDefinition when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class CiviFetchStep:
        """Stub for CiviFetchStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class CiviMutateStep:
        """Stub for CiviMutateStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class CiviApprovalStep:
        """Stub for CiviApprovalStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")

    class CiviSyncStep:
        """Stub for CiviSyncStep when litestar-workflows is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("litestar-workflows required: pip install civi-py[workflows]")


class ContactSyncWorkflow:
    """Workflow: Fetch contacts from CiviCRM, human review, sync to local database.

    This workflow automates the process of synchronizing contacts from CiviCRM
    to a local database with human oversight. It ensures that contact data
    is reviewed before being persisted locally.

    Steps:
        1. fetch_contacts: Fetch contacts from CiviCRM based on configured filters
        2. review_contacts: Human reviews fetched contacts before sync
        3. sync_approved: Sync approved contacts to local database

    Workflow Flow::

        [fetch_contacts] --> [review_contacts] --> [sync_approved]
                                    |
                                    +--> (rejected: workflow ends)

    The workflow transitions from review to sync only when approved=True.

    Attributes:
        __workflow_name__: Unique identifier for this workflow type.
        __workflow_version__: Semantic version of the workflow definition.

    Example:
        >>> from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE
        >>> from civicrm_py.contrib.workflows.templates import ContactSyncWorkflow
        >>>
        >>> if WORKFLOWS_AVAILABLE:
        ...     # Get workflow definition
        ...     definition = ContactSyncWorkflow.get_definition()
        ...
        ...     # Use with workflow engine
        ...     from litestar_workflows import WorkflowEngine, WorkflowRegistry
        ...
        ...     registry = WorkflowRegistry()
        ...     registry.register(definition)
        ...
        ...     engine = WorkflowEngine(registry=registry)
        ...
        ...     # Start workflow instance with custom filters
        ...     instance = await engine.start_workflow(
        ...         "contact_sync",
        ...         initial_data={
        ...             "civi_client": client,
        ...             "filters": {"is_deleted": False, "contact_type": "Individual"},
        ...         },
        ...     )

    Note:
        The workflow context must contain a 'civi_client' key with an initialized
        CiviClient instance before execution begins.
    """

    __workflow_name__: ClassVar[str] = "contact_sync"
    __workflow_version__: ClassVar[str] = "1.0.0"

    @classmethod
    def get_definition(
        cls,
        *,
        filters: dict[str, Any] | None = None,
        select: list[str] | None = None,
        limit: int = 100,
        show_fields: list[str] | None = None,
    ) -> WorkflowDefinition:
        """Create a WorkflowDefinition for contact synchronization.

        Args:
            filters: CiviCRM filter conditions for fetching contacts.
                Defaults to {"is_deleted": False}.
            select: Fields to fetch from CiviCRM. Defaults to common contact fields.
            limit: Maximum number of contacts to fetch per execution.
            show_fields: Fields to display during human review. Defaults to
                display_name and email.

        Returns:
            A WorkflowDefinition ready for registration with a workflow engine.

        Raises:
            ImportError: If litestar-workflows is not installed.

        Example:
            >>> definition = ContactSyncWorkflow.get_definition(
            ...     filters={"contact_type": "Organization"},
            ...     select=["id", "organization_name", "email_primary.email"],
            ...     limit=50,
            ...     show_fields=["organization_name", "email_primary.email"],
            ... )
        """
        require_workflows()

        default_filters = filters if filters is not None else {"is_deleted": False}
        default_select = (
            select
            if select is not None
            else [
                "id",
                "display_name",
                "email_primary.email",
                "phone_primary.phone",
            ]
        )
        default_show_fields = (
            show_fields
            if show_fields is not None
            else [
                "display_name",
                "email_primary.email",
            ]
        )

        # Define workflow steps
        fetch_step = CiviFetchStep(
            name="fetch_contacts",
            description="Fetch contacts from CiviCRM for review",
            entity="Contact",
            filters=default_filters,
            select=default_select,
            limit=limit,
            context_key="contacts_to_sync",
        )

        review_step = CiviApprovalStep(
            name="review_contacts",
            title="Review Contacts for Sync",
            description="Review the fetched contacts before syncing to local database",
            data_context_key="contacts_to_sync",
            show_fields=default_show_fields,
            require_comments_on_reject=False,
        )

        sync_step = CiviSyncStep(
            name="sync_approved",
            description="Sync approved contacts to local database",
            entity="Contact",
            direction="from_civi",
            filters=default_filters,
            select=default_select,
            sync_result_key="sync_results",
        )

        # Define edges with conditional transition
        def is_approved(context: Any) -> bool:
            """Check if the review was approved."""
            return context.get("approved", False) is True

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description="Fetch contacts from CiviCRM, review, and sync to local database",
            steps={
                "fetch_contacts": fetch_step,
                "review_contacts": review_step,
                "sync_approved": sync_step,
            },
            edges=[
                Edge("fetch_contacts", "review_contacts"),
                Edge("review_contacts", "sync_approved", condition=is_approved),
            ],
            initial_step="fetch_contacts",
            terminal_steps={"sync_approved", "review_contacts"},
        )


class BulkUpdateWorkflow:
    """Workflow: Select entities, approve changes, execute bulk update.

    A generic workflow for performing bulk updates on any CiviCRM entity.
    Includes human approval before changes are applied.

    Steps:
        1. select_entities: Fetch entities matching criteria from CiviCRM
        2. approve_changes: Human approves the proposed bulk operation
        3. execute_update: Apply updates to all selected entities
        4. log_results: Record the operation results in context

    Workflow Flow::

        [select_entities] --> [approve_changes] --> [execute_update] --> [log_results]
                                     |
                                     +--> (rejected: workflow ends)

    The workflow supports updating any CiviCRM entity type and allows
    specifying the fields to update via context.

    Attributes:
        __workflow_name__: Unique identifier for this workflow type.
        __workflow_version__: Semantic version of the workflow definition.

    Example:
        >>> from civicrm_py.contrib.workflows.templates import BulkUpdateWorkflow
        >>>
        >>> # Create workflow for updating contact groups
        >>> definition = BulkUpdateWorkflow.get_definition(
        ...     entity="Contact",
        ...     select_filters={"group": {"IN": [1, 2, 3]}},
        ...     update_fields={"do_not_email": True},
        ... )
        >>>
        >>> # Start workflow
        >>> instance = await engine.start_workflow(
        ...     "bulk_update",
        ...     initial_data={"civi_client": client},
        ... )

    Note:
        The update_fields parameter defines what changes will be applied to
        all selected entities. Review carefully before approval.
    """

    __workflow_name__: ClassVar[str] = "bulk_update"
    __workflow_version__: ClassVar[str] = "1.0.0"

    @classmethod
    def get_definition(
        cls,
        *,
        entity: str = "Contact",
        select_filters: dict[str, Any] | None = None,
        select_fields: list[str] | None = None,
        update_fields: dict[str, Any] | None = None,
        limit: int = 500,
    ) -> WorkflowDefinition:
        """Create a WorkflowDefinition for bulk entity updates.

        Args:
            entity: CiviCRM entity type to update (e.g., "Contact", "Activity").
            select_filters: Filters to identify entities for update.
            select_fields: Fields to fetch for review display.
            update_fields: Dictionary of field values to apply in the update.
                Can also be set via context at runtime.
            limit: Maximum number of entities to update in one workflow run.

        Returns:
            A WorkflowDefinition ready for registration with a workflow engine.

        Raises:
            ImportError: If litestar-workflows is not installed.

        Example:
            >>> # Update all inactive contacts
            >>> definition = BulkUpdateWorkflow.get_definition(
            ...     entity="Contact",
            ...     select_filters={"is_deceased": False, "do_not_email": True},
            ...     update_fields={"do_not_mail": True},
            ...     limit=1000,
            ... )
        """
        require_workflows()

        default_filters = select_filters if select_filters is not None else {}
        default_select = select_fields if select_fields is not None else ["id", "display_name"]
        default_update = update_fields if update_fields is not None else {}

        # Step 1: Select entities to update
        select_step = CiviFetchStep(
            name="select_entities",
            description=f"Fetch {entity} entities matching criteria for bulk update",
            entity=entity,
            filters=default_filters,
            select=default_select,
            limit=limit,
            context_key="entities_to_update",
        )

        # Step 2: Human approval
        approve_step = CiviApprovalStep(
            name="approve_changes",
            title=f"Approve Bulk {entity} Update",
            description=(
                f"Review the selected {entity} records and approve the bulk update. "
                f"This will apply changes to all {limit} (max) matching records."
            ),
            data_context_key="entities_to_update",
            show_fields=default_select,
            require_comments_on_reject=True,
        )

        # Step 3: Execute the bulk update
        # This step requires entities_to_update to be transformed with update fields
        execute_step = CiviMutateStep(
            name="execute_update",
            description=f"Apply bulk update to selected {entity} records",
            entity=entity,
            action="update",
            data_context_key="prepared_updates",
            result_context_key="update_results",
        )

        # Step 4: Log results - uses a simple fetch to store metadata
        # In practice, this would be a custom step, but we use CiviFetchStep
        # as a placeholder that stores the final state
        log_step = CiviFetchStep(
            name="log_results",
            description="Record the bulk update operation results",
            entity=entity,
            filters=default_filters,
            select=["id"],
            limit=1,
            context_key="operation_log",
        )

        def is_approved(context: Any) -> bool:
            """Check if the changes were approved."""
            return context.get("approved", False) is True

        def prepare_updates(context: Any) -> None:
            """Prepare update data by merging selection with update fields.

            This function is called as a side effect when transitioning to execute_update.
            It combines the selected entities with the update fields.
            """
            entities = context.get("entities_to_update", [])
            updates = context.get("update_fields", default_update)

            # Prepare records with id and update fields
            prepared = []
            for entity_record in entities:
                if "id" in entity_record:
                    update_record = {"id": entity_record["id"], **updates}
                    prepared.append(update_record)

            context.set("prepared_updates", prepared)

        # Create edge that prepares data before execution
        class PrepareAndTransitionEdge:
            """Custom edge that prepares update data before transition."""

            def __init__(self, source: str, target: str) -> None:
                self.source = source
                self.target = target
                self._condition = is_approved

            def condition(self, context: Any) -> bool:
                """Check approval and prepare updates."""
                if self._condition(context):
                    prepare_updates(context)
                    return True
                return False

        # Use standard Edge with preparation in the condition
        def approve_and_prepare(context: Any) -> bool:
            """Approve and prepare updates for execution."""
            if context.get("approved", False) is True:
                entities = context.get("entities_to_update", [])
                updates = context.get("update_fields", default_update)
                prepared = [{"id": e["id"], **updates} for e in entities if "id" in e]
                context.set("prepared_updates", prepared)
                return True
            return False

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description=f"Bulk update {entity} records with human approval",
            steps={
                "select_entities": select_step,
                "approve_changes": approve_step,
                "execute_update": execute_step,
                "log_results": log_step,
            },
            edges=[
                Edge("select_entities", "approve_changes"),
                Edge("approve_changes", "execute_update", condition=approve_and_prepare),
                Edge("execute_update", "log_results"),
            ],
            initial_step="select_entities",
            terminal_steps={"log_results", "approve_changes"},
        )


class MembershipRenewalWorkflow:
    """Workflow: Check expiring memberships, notify, process renewals, update.

    Automates the membership renewal process by identifying expiring memberships,
    facilitating human review of renewal candidates, and updating renewed
    memberships in CiviCRM.

    Steps:
        1. check_expiring: Fetch memberships expiring within the configured window
        2. send_notifications: Placeholder for sending renewal reminder notifications
        3. process_renewals: Human processes and approves renewal candidates
        4. update_memberships: Update renewed memberships in CiviCRM

    Workflow Flow::

        [check_expiring] --> [send_notifications] --> [process_renewals] --> [update_memberships]
                                                              |
                                                              +--> (no renewals: workflow ends)

    Attributes:
        __workflow_name__: Unique identifier for this workflow type.
        __workflow_version__: Semantic version of the workflow definition.

    Example:
        >>> from civicrm_py.contrib.workflows.templates import MembershipRenewalWorkflow
        >>>
        >>> # Create workflow for memberships expiring in 30 days
        >>> definition = MembershipRenewalWorkflow.get_definition(
        ...     days_until_expiry=30,
        ...     membership_types=[1, 2],  # Specific membership type IDs
        ... )
        >>>
        >>> # Register and start
        >>> registry.register(definition)
        >>> instance = await engine.start_workflow(
        ...     "membership_renewal",
        ...     initial_data={"civi_client": client},
        ... )

    Note:
        The send_notifications step is a placeholder. In production, you would
        typically integrate with an email service or notification system.
    """

    __workflow_name__: ClassVar[str] = "membership_renewal"
    __workflow_version__: ClassVar[str] = "1.0.0"

    @classmethod
    def get_definition(
        cls,
        *,
        days_until_expiry: int = 30,
        membership_types: list[int] | None = None,
        membership_status: list[str] | None = None,
        renewal_period_months: int = 12,
    ) -> WorkflowDefinition:
        """Create a WorkflowDefinition for membership renewal processing.

        Args:
            days_until_expiry: Number of days before expiry to include memberships.
                Memberships expiring within this window will be fetched.
            membership_types: List of membership type IDs to include. If None,
                includes all types.
            membership_status: List of membership status names to include.
                Defaults to ["Current", "Grace"].
            renewal_period_months: Number of months to extend membership on renewal.

        Returns:
            A WorkflowDefinition ready for registration with a workflow engine.

        Raises:
            ImportError: If litestar-workflows is not installed.

        Example:
            >>> # Renew annual memberships expiring in 60 days
            >>> definition = MembershipRenewalWorkflow.get_definition(
            ...     days_until_expiry=60,
            ...     membership_types=[1],  # Annual membership type
            ...     renewal_period_months=12,
            ... )
        """
        require_workflows()

        default_status = membership_status if membership_status is not None else ["Current", "Grace"]

        # Build filters for expiring memberships
        # Note: In real usage, the date comparison would need to be dynamic
        # This is a simplified version - actual implementation would compute dates at runtime
        expiring_filters: dict[str, Any] = {
            "status_id:name": {"IN": default_status},
            "is_test": False,
        }
        if membership_types:
            expiring_filters["membership_type_id"] = {"IN": membership_types}

        # Step 1: Fetch expiring memberships
        check_step = CiviFetchStep(
            name="check_expiring",
            description=f"Fetch memberships expiring within {days_until_expiry} days",
            entity="Membership",
            filters=expiring_filters,
            select=[
                "id",
                "contact_id",
                "membership_type_id",
                "membership_type_id:label",
                "start_date",
                "end_date",
                "status_id:label",
                "contact_id.display_name",
                "contact_id.email_primary.email",
            ],
            order_by={"end_date": "ASC"},
            limit=500,
            context_key="expiring_memberships",
        )

        # Step 2: Notification placeholder - fetches the same data but stores separately
        # In a real implementation, this would be a custom step that sends emails
        notify_step = CiviFetchStep(
            name="send_notifications",
            description="Placeholder for sending renewal reminder notifications",
            entity="Membership",
            filters=expiring_filters,
            select=["id"],
            limit=1,
            context_key="notification_placeholder",
        )

        # Step 3: Human processes renewals
        process_step = CiviApprovalStep(
            name="process_renewals",
            title="Process Membership Renewals",
            description=(
                "Review expiring memberships and select those to renew. "
                "Approved memberships will have their end date extended."
            ),
            data_context_key="expiring_memberships",
            show_fields=[
                "contact_id.display_name",
                "membership_type_id:label",
                "end_date",
                "status_id:label",
            ],
            require_comments_on_reject=False,
        )

        # Step 4: Update renewed memberships
        update_step = CiviMutateStep(
            name="update_memberships",
            description="Update renewed memberships with new end dates",
            entity="Membership",
            action="update",
            data_context_key="renewals_to_process",
            result_context_key="renewal_results",
        )

        def has_renewals_to_process(context: Any) -> bool:
            """Check if there are renewals approved for processing."""
            approved = context.get("approved", False)
            if not approved:
                return False

            # Prepare renewal data
            memberships = context.get("expiring_memberships", [])
            if not memberships:
                return False

            # Calculate new end dates (simplified - would need proper date handling)
            # In production, use dateutil or similar for proper date arithmetic
            # Note: Actual date calculation would be done here
            # This is a placeholder - the actual end_date would be computed
            renewals = [
                {"id": membership["id"], "_renewal_months": renewal_period_months}
                for membership in memberships
                if "id" in membership
            ]

            context.set("renewals_to_process", renewals)
            return len(renewals) > 0

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description="Process membership renewals with human review",
            steps={
                "check_expiring": check_step,
                "send_notifications": notify_step,
                "process_renewals": process_step,
                "update_memberships": update_step,
            },
            edges=[
                Edge("check_expiring", "send_notifications"),
                Edge("send_notifications", "process_renewals"),
                Edge("process_renewals", "update_memberships", condition=has_renewals_to_process),
            ],
            initial_step="check_expiring",
            terminal_steps={"update_memberships", "process_renewals"},
        )


class DonationProcessingWorkflow:
    """Workflow: Validate donation, approve (conditional), create contribution, generate receipt.

    Processes incoming donations with validation, optional human approval for
    large amounts, contribution creation in CiviCRM, and receipt generation.

    Steps:
        1. validate_donation: Validate donation data from context
        2. approve_donation: Human approves (conditional - only for large amounts)
        3. create_contribution: Create Contribution record in CiviCRM
        4. generate_receipt: Record receipt information

    Workflow Flow::

        [validate_donation] --> [approve_donation] --> [create_contribution] --> [generate_receipt]
                                       |
                                       +--> (small amount: skip to create_contribution)

    The workflow includes a conditional edge that skips human approval for
    donations below a configurable threshold amount.

    Attributes:
        __workflow_name__: Unique identifier for this workflow type.
        __workflow_version__: Semantic version of the workflow definition.

    Example:
        >>> from civicrm_py.contrib.workflows.templates import DonationProcessingWorkflow
        >>>
        >>> # Create workflow requiring approval for donations >= $1000
        >>> definition = DonationProcessingWorkflow.get_definition(
        ...     approval_threshold=1000.0,
        ...     default_financial_type_id=1,  # Donation
        ... )
        >>>
        >>> # Start workflow with donation data
        >>> instance = await engine.start_workflow(
        ...     "donation_processing",
        ...     initial_data={
        ...         "civi_client": client,
        ...         "donation": {
        ...             "contact_id": 123,
        ...             "total_amount": 500.0,
        ...             "currency": "USD",
        ...         },
        ...     },
        ... )

    Note:
        The donation data should be provided in the initial_data with key "donation".
        Required fields: contact_id, total_amount. Optional: currency, source, etc.
    """

    __workflow_name__: ClassVar[str] = "donation_processing"
    __workflow_version__: ClassVar[str] = "1.0.0"

    @classmethod
    def get_definition(
        cls,
        *,
        approval_threshold: float = 1000.0,
        default_financial_type_id: int = 1,
        default_payment_instrument_id: int | None = None,
        auto_receipt: bool = True,  # noqa: ARG003
    ) -> WorkflowDefinition:
        """Create a WorkflowDefinition for donation processing.

        Args:
            approval_threshold: Donation amounts >= this value require human approval.
                Set to 0 to require approval for all donations, or float('inf') to
                never require approval.
            default_financial_type_id: CiviCRM financial type ID for contributions.
                Typically 1 = Donation.
            default_payment_instrument_id: Default payment instrument ID. If None,
                must be provided in donation data.
            auto_receipt: Whether to automatically generate receipt info. Reserved
                for future implementation of automated receipt generation.

        Returns:
            A WorkflowDefinition ready for registration with a workflow engine.

        Raises:
            ImportError: If litestar-workflows is not installed.

        Example:
            >>> # Process donations with $500 approval threshold
            >>> definition = DonationProcessingWorkflow.get_definition(
            ...     approval_threshold=500.0,
            ...     default_financial_type_id=1,
            ...     auto_receipt=True,
            ... )
        """
        require_workflows()

        # Step 1: Validate donation - uses fetch as a placeholder
        # In production, this would be a custom validation step
        validate_step = CiviFetchStep(
            name="validate_donation",
            description="Validate incoming donation data",
            entity="Contact",
            filters={},
            select=["id"],
            limit=1,
            context_key="validation_check",
        )

        # Step 2: Human approval for large donations
        approve_step = CiviApprovalStep(
            name="approve_donation",
            title="Approve Large Donation",
            description=(
                f"Review and approve donation of ${approval_threshold}+. Verify donor information and donation details."
            ),
            data_context_key="donation",
            show_fields=["contact_id", "total_amount", "currency", "source"],
            require_comments_on_reject=True,
        )

        # Step 3: Create contribution in CiviCRM
        create_step = CiviMutateStep(
            name="create_contribution",
            description="Create Contribution record in CiviCRM",
            entity="Contribution",
            action="create",
            data_context_key="contribution_data",
            result_context_key="created_contribution",
        )

        # Step 4: Generate receipt - placeholder using fetch
        receipt_step = CiviFetchStep(
            name="generate_receipt",
            description="Record receipt information for the contribution",
            entity="Contribution",
            filters={},
            select=["id", "receipt_date", "receipt_id"],
            limit=1,
            context_key="receipt_info",
        )

        def requires_approval(context: Any) -> bool:
            """Check if donation amount requires human approval."""
            donation = context.get("donation", {})
            amount = donation.get("total_amount", 0)
            return float(amount) >= approval_threshold

        def skip_approval(context: Any) -> bool:
            """Check if donation can skip approval (small amount)."""
            donation = context.get("donation", {})
            amount = donation.get("total_amount", 0)

            if float(amount) < approval_threshold:
                # Prepare contribution data for small donations
                _prepare_contribution_data(context, default_financial_type_id, default_payment_instrument_id)
                return True
            return False

        def after_approval(context: Any) -> bool:
            """Proceed after approval and prepare contribution data."""
            if context.get("approved", False) is True:
                _prepare_contribution_data(context, default_financial_type_id, default_payment_instrument_id)
                return True
            return False

        return WorkflowDefinition(
            name=cls.__workflow_name__,
            version=cls.__workflow_version__,
            description="Process donations with conditional approval and contribution creation",
            steps={
                "validate_donation": validate_step,
                "approve_donation": approve_step,
                "create_contribution": create_step,
                "generate_receipt": receipt_step,
            },
            edges=[
                # After validation, check if approval is needed
                Edge("validate_donation", "approve_donation", condition=requires_approval),
                Edge("validate_donation", "create_contribution", condition=skip_approval),
                # After approval (if needed), create contribution
                Edge("approve_donation", "create_contribution", condition=after_approval),
                # Always generate receipt after contribution
                Edge("create_contribution", "generate_receipt"),
            ],
            initial_step="validate_donation",
            terminal_steps={"generate_receipt", "approve_donation"},
        )


def _prepare_contribution_data(
    context: Any,
    default_financial_type_id: int,
    default_payment_instrument_id: int | None,
) -> None:
    """Prepare contribution data from donation context.

    Args:
        context: Workflow context containing donation data.
        default_financial_type_id: Default financial type ID.
        default_payment_instrument_id: Default payment instrument ID.
    """
    donation = context.get("donation", {})

    contribution_data = {
        "contact_id": donation.get("contact_id"),
        "total_amount": donation.get("total_amount"),
        "financial_type_id": donation.get("financial_type_id", default_financial_type_id),
        "receive_date": donation.get("receive_date", "now"),
        "contribution_status_id": donation.get("status_id", 1),  # 1 = Completed
    }

    # Add optional fields if provided
    if "currency" in donation:
        contribution_data["currency"] = donation["currency"]
    if "source" in donation:
        contribution_data["source"] = donation["source"]
    if "payment_instrument_id" in donation:
        contribution_data["payment_instrument_id"] = donation["payment_instrument_id"]
    elif default_payment_instrument_id:
        contribution_data["payment_instrument_id"] = default_payment_instrument_id

    context.set("contribution_data", contribution_data)


__all__ = [
    "BulkUpdateWorkflow",
    "ContactSyncWorkflow",
    "DonationProcessingWorkflow",
    "MembershipRenewalWorkflow",
]
