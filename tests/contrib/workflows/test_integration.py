"""Integration tests for CiviCRM workflow templates and step execution.

These tests verify complete workflow execution with mocked CiviCRM responses,
testing the interaction between multiple steps, human approval flows,
and workflow state management.

Test coverage includes:
- ContactSyncWorkflow execution
- BulkUpdateWorkflow execution
- DonationProcessingWorkflow with conditional approval
- Human task approval/rejection flows
- Step primitive execution with mocked client
- Workflow persistence with real database (when available)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from civi_py.contrib.workflows import WORKFLOWS_AVAILABLE
from tests.conftest import skip_without_postgres

if TYPE_CHECKING:
    from collections.abc import Callable


# Skip all tests if workflows dependency is not available
pytestmark = pytest.mark.skipif(
    not WORKFLOWS_AVAILABLE,
    reason="litestar-workflows not installed",
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_civi_client() -> AsyncMock:
    """Mock CiviClient that returns test data.

    Provides a comprehensive mock of the CiviClient with pre-configured
    responses for common operations.
    """
    client = AsyncMock()

    # Default get response
    get_response = MagicMock()
    get_response.values = [
        {"id": 1, "display_name": "John Doe", "email_primary.email": "john@example.com"},
        {"id": 2, "display_name": "Jane Smith", "email_primary.email": "jane@example.com"},
    ]
    get_response.count = 2
    client.get = AsyncMock(return_value=get_response)

    # Default create response
    create_response = MagicMock()
    create_response.values = [{"id": 100, "display_name": "New Contact"}]
    client.create = AsyncMock(return_value=create_response)

    # Default update response
    update_response = MagicMock()
    update_response.values = [{"id": 1, "display_name": "Updated Contact"}]
    client.update = AsyncMock(return_value=update_response)

    # Default delete response
    delete_response = MagicMock()
    delete_response.values = []
    client.delete = AsyncMock(return_value=delete_response)

    return client


@pytest.fixture
def mock_context_factory(mock_civi_client: AsyncMock) -> Callable[..., MagicMock]:
    """Factory for creating mock WorkflowContext instances.

    Returns a factory function that creates context objects with
    the mock CiviClient pre-configured.
    """

    def _create_context(initial_data: dict[str, Any] | None = None) -> MagicMock:
        context = MagicMock()
        context_data: dict[str, Any] = {"civi_client": mock_civi_client}
        if initial_data:
            context_data.update(initial_data)

        def get_value(key: str, default: Any = None) -> Any:
            return context_data.get(key, default)

        def set_value(key: str, value: Any) -> None:
            context_data[key] = value

        context.get = MagicMock(side_effect=get_value)
        context.set = MagicMock(side_effect=set_value)
        context._data = context_data  # For test inspection
        return context

    return _create_context


@pytest.fixture
def mock_context(mock_context_factory: Callable[..., MagicMock]) -> MagicMock:
    """Create a default mock WorkflowContext."""
    return mock_context_factory()


@pytest.fixture
def workflow_definitions() -> dict[str, Any]:
    """Pre-configured workflow definitions for testing.

    Returns a dictionary of workflow name to definition.
    """
    from civi_py.contrib.workflows.templates import (
        BulkUpdateWorkflow,
        ContactSyncWorkflow,
        DonationProcessingWorkflow,
    )

    return {
        "contact_sync": ContactSyncWorkflow.get_definition(),
        "bulk_update": BulkUpdateWorkflow.get_definition(
            entity="Contact",
            select_filters={"is_deleted": False},
            update_fields={"do_not_email": True},
        ),
        "donation_processing": DonationProcessingWorkflow.get_definition(
            approval_threshold=1000.0,
            default_financial_type_id=1,
        ),
    }


# -----------------------------------------------------------------------------
# ContactSyncWorkflow Tests
# -----------------------------------------------------------------------------


class TestContactSyncWorkflowExecution:
    """Test ContactSyncWorkflow execution with mocked CiviCRM."""

    @pytest.mark.asyncio
    async def test_contact_sync_fetch_step(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test ContactSyncWorkflow fetch step pulls contacts."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition(
            filters={"is_deleted": False},
            limit=50,
        )

        # Get the fetch step
        fetch_step = definition.steps["fetch_contacts"]

        # Execute fetch step
        await fetch_step.execute(mock_context)

        # Verify client was called
        mock_civi_client.get.assert_called_once()
        call_kwargs = mock_civi_client.get.call_args[1]
        assert call_kwargs["where"] == [["is_deleted", "=", False]]
        assert call_kwargs["limit"] == 50

        # Verify data stored in context
        assert mock_context._data.get("contacts_to_sync") is not None
        assert len(mock_context._data["contacts_to_sync"]) == 2

    @pytest.mark.asyncio
    async def test_contact_sync_approval_flow(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test ContactSyncWorkflow approval transitions correctly."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()

        # Simulate workflow after fetch step
        context = mock_context_factory(
            {
                "contacts_to_sync": [
                    {"id": 1, "display_name": "John Doe"},
                    {"id": 2, "display_name": "Jane Smith"},
                ],
            },
        )

        # Get review step
        review_step = definition.steps["review_contacts"]

        # Verify review step has correct form schema
        assert review_step.form_schema["type"] == "object"
        assert "approved" in review_step.form_schema["properties"]

        # Test review data extraction
        review_data = review_step.get_review_data(context)
        assert review_data["_summary"] == "2 records to review"

    @pytest.mark.asyncio
    async def test_contact_sync_sync_step_executes_after_approval(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test ContactSyncWorkflow sync step executes when approved."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()

        # Simulate approved context
        context = mock_context_factory(
            {
                "approved": True,
                "contacts_to_sync": [
                    {"id": 1, "display_name": "John Doe"},
                ],
            },
        )

        # Get sync step
        sync_step = definition.steps["sync_approved"]

        # Execute sync step
        await sync_step.execute(context)

        # Verify client was called for sync
        mock_civi_client.get.assert_called()

        # Verify sync results in context
        assert "sync_results" in context._data

    @pytest.mark.asyncio
    async def test_contact_sync_full_workflow(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test complete ContactSyncWorkflow execution."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()
        context = mock_context_factory()

        # Step 1: Fetch contacts
        fetch_step = definition.steps["fetch_contacts"]
        await fetch_step.execute(context)

        assert "contacts_to_sync" in context._data
        assert len(context._data["contacts_to_sync"]) == 2

        # Step 2: Simulate human approval
        context._data["approved"] = True

        # Check edge condition
        approval_edge = next(e for e in definition.edges if e.source == "review_contacts")
        assert approval_edge.condition(context) is True

        # Step 3: Execute sync
        sync_step = definition.steps["sync_approved"]
        await sync_step.execute(context)

        assert "sync_results" in context._data
        assert context._data["sync_results"]["synced_count"] >= 0


# -----------------------------------------------------------------------------
# BulkUpdateWorkflow Tests
# -----------------------------------------------------------------------------


class TestBulkUpdateWorkflowExecution:
    """Test BulkUpdateWorkflow execution with mocked CiviCRM."""

    @pytest.mark.asyncio
    async def test_bulk_update_select_step(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test BulkUpdateWorkflow select step fetches entities."""
        from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

        definition = BulkUpdateWorkflow.get_definition(
            entity="Contact",
            select_filters={"contact_type": "Individual"},
            select_fields=["id", "display_name", "email_primary.email"],
            limit=100,
        )

        # Execute select step
        select_step = definition.steps["select_entities"]
        await select_step.execute(mock_context)

        # Verify correct entity and filters
        mock_civi_client.get.assert_called_once()
        call_kwargs = mock_civi_client.get.call_args[1]
        assert call_kwargs["where"] == [["contact_type", "=", "Individual"]]

        # Verify data in context
        assert "entities_to_update" in mock_context._data

    @pytest.mark.asyncio
    async def test_bulk_update_approval_prepares_data(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test BulkUpdateWorkflow approval prepares update data."""
        from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

        update_fields = {"do_not_email": True, "do_not_mail": True}
        definition = BulkUpdateWorkflow.get_definition(
            entity="Contact",
            update_fields=update_fields,
        )

        # Simulate context after select
        context = mock_context_factory(
            {
                "entities_to_update": [
                    {"id": 1, "display_name": "John Doe"},
                    {"id": 2, "display_name": "Jane Smith"},
                ],
                "approved": True,
            },
        )

        # Check the approval edge prepares update data
        approval_edge = next(e for e in definition.edges if e.source == "approve_changes")
        result = approval_edge.condition(context)

        assert result is True
        assert "prepared_updates" in context._data
        assert len(context._data["prepared_updates"]) == 2

        # Verify each prepared update has id and update fields
        for update in context._data["prepared_updates"]:
            assert "id" in update
            assert update["do_not_email"] is True
            assert update["do_not_mail"] is True

    @pytest.mark.asyncio
    async def test_bulk_update_execute_step(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test BulkUpdateWorkflow execute step applies updates."""
        from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

        definition = BulkUpdateWorkflow.get_definition(entity="Contact")

        # Simulate context with prepared updates
        context = mock_context_factory(
            {
                "prepared_updates": [
                    {"id": 1, "do_not_email": True},
                    {"id": 2, "do_not_email": True},
                ],
            },
        )

        # Execute update step
        execute_step = definition.steps["execute_update"]
        await execute_step.execute(context)

        # Verify updates were called
        assert mock_civi_client.update.call_count == 2

        # Verify results in context
        assert "update_results" in context._data


# -----------------------------------------------------------------------------
# DonationProcessingWorkflow Tests
# -----------------------------------------------------------------------------


class TestDonationWorkflowSmallAmount:
    """Test DonationProcessingWorkflow for small amounts (skips approval)."""

    @pytest.mark.asyncio
    async def test_donation_small_amount_skips_approval(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test donations below threshold skip human approval."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        definition = DonationProcessingWorkflow.get_definition(
            approval_threshold=1000.0,
            default_financial_type_id=1,
        )

        # Small donation - below threshold
        context = mock_context_factory(
            {
                "donation": {
                    "contact_id": 123,
                    "total_amount": 500.0,
                    "currency": "USD",
                    "source": "Online donation",
                },
            },
        )

        # Check edges from validate step
        validate_edges = [e for e in definition.edges if e.source == "validate_donation"]

        # Find the edge that skips approval
        skip_edge = next(e for e in validate_edges if e.target == "create_contribution")
        requires_approval_edge = next(e for e in validate_edges if e.target == "approve_donation")

        # Small amount should skip approval
        assert skip_edge.condition(context) is True
        assert requires_approval_edge.condition(context) is False

        # Verify contribution data was prepared
        assert "contribution_data" in context._data
        assert context._data["contribution_data"]["total_amount"] == 500.0
        assert context._data["contribution_data"]["financial_type_id"] == 1

    @pytest.mark.asyncio
    async def test_donation_small_amount_creates_contribution(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test small donation workflow creates contribution."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        definition = DonationProcessingWorkflow.get_definition(
            approval_threshold=1000.0,
        )

        # Simulate context after skip_approval edge
        context = mock_context_factory(
            {
                "donation": {
                    "contact_id": 123,
                    "total_amount": 100.0,
                    "currency": "USD",
                },
                "contribution_data": {
                    "contact_id": 123,
                    "total_amount": 100.0,
                    "currency": "USD",
                    "financial_type_id": 1,
                    "receive_date": "now",
                    "contribution_status_id": 1,
                },
            },
        )

        # Execute create contribution step
        create_step = definition.steps["create_contribution"]
        await create_step.execute(context)

        # Verify contribution was created
        mock_civi_client.create.assert_called_once()
        call_args = mock_civi_client.create.call_args
        assert call_args[0][0] == "Contribution"


class TestDonationWorkflowLargeAmount:
    """Test DonationProcessingWorkflow for large amounts (requires approval)."""

    @pytest.mark.asyncio
    async def test_donation_large_amount_requires_approval(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test donations at or above threshold require human approval."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        definition = DonationProcessingWorkflow.get_definition(
            approval_threshold=1000.0,
        )

        # Large donation - at threshold
        context = mock_context_factory(
            {
                "donation": {
                    "contact_id": 123,
                    "total_amount": 1000.0,
                    "currency": "USD",
                },
            },
        )

        # Check edges from validate step
        validate_edges = [e for e in definition.edges if e.source == "validate_donation"]

        requires_approval_edge = next(e for e in validate_edges if e.target == "approve_donation")
        skip_edge = next(e for e in validate_edges if e.target == "create_contribution")

        # Large amount should require approval
        assert requires_approval_edge.condition(context) is True
        assert skip_edge.condition(context) is False

    @pytest.mark.asyncio
    async def test_donation_large_amount_proceeds_after_approval(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test large donation proceeds to contribution creation after approval."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        definition = DonationProcessingWorkflow.get_definition(
            approval_threshold=1000.0,
            default_financial_type_id=1,
        )

        context = mock_context_factory(
            {
                "donation": {
                    "contact_id": 123,
                    "total_amount": 5000.0,
                    "currency": "USD",
                    "source": "Major gift",
                },
                "approved": True,
            },
        )

        # Check approval edge
        approval_edge = next(e for e in definition.edges if e.source == "approve_donation")

        result = approval_edge.condition(context)
        assert result is True

        # Verify contribution data was prepared
        assert "contribution_data" in context._data
        assert context._data["contribution_data"]["total_amount"] == 5000.0
        assert context._data["contribution_data"]["source"] == "Major gift"


# -----------------------------------------------------------------------------
# Human Task Approval Flow Tests
# -----------------------------------------------------------------------------


class TestHumanTaskApproval:
    """Test human task approval flows."""

    @pytest.mark.asyncio
    async def test_human_task_approval_proceeds(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test completing a human approval task allows workflow to proceed."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()

        # Context with approval
        context = mock_context_factory(
            {
                "contacts_to_sync": [{"id": 1}],
                "approved": True,
                "comments": "Looks good",
                "reviewer_id": 42,
            },
        )

        # Get the edge from review to sync
        review_edge = next(e for e in definition.edges if e.source == "review_contacts" and e.target == "sync_approved")

        # Approval should allow transition
        assert review_edge.condition(context) is True

    @pytest.mark.asyncio
    async def test_human_task_rejection_stops_workflow(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test rejecting in a human task stops workflow progression."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()

        # Context with rejection
        context = mock_context_factory(
            {
                "contacts_to_sync": [{"id": 1}],
                "approved": False,
                "comments": "Data needs review",
            },
        )

        # Get the edge from review to sync
        review_edge = next(e for e in definition.edges if e.source == "review_contacts" and e.target == "sync_approved")

        # Rejection should stop transition
        assert review_edge.condition(context) is False

        # Review step should be a terminal step in this case
        assert "review_contacts" in definition.terminal_steps

    @pytest.mark.asyncio
    async def test_approval_with_required_comments_on_reject(
        self,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test approval step with required comments on rejection."""
        from civi_py.contrib.workflows.steps import CiviApprovalStep

        step = CiviApprovalStep(
            name="review_with_comments",
            title="Review Data",
            require_comments_on_reject=True,
        )

        # Verify form schema has conditional requirement
        assert "allOf" in step.form_schema
        conditional = step.form_schema["allOf"][0]
        assert conditional["if"]["properties"]["approved"]["const"] is False
        assert "comments" in conditional["then"]["required"]


# -----------------------------------------------------------------------------
# Step Primitive Execution Tests
# -----------------------------------------------------------------------------


class TestCiviFetchStepExecution:
    """Test CiviFetchStep execution with mocked client."""

    @pytest.mark.asyncio
    async def test_fetch_step_with_complex_filters(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test CiviFetchStep handles complex filter conditions."""
        from civi_py.contrib.workflows.steps import CiviFetchStep

        step = CiviFetchStep(
            name="fetch_filtered",
            entity="Contact",
            filters={
                "is_deleted": False,
                "contact_type": "Individual",
                "created_date": {">=": "2024-01-01"},
            },
            select=["id", "display_name", "email_primary.email"],
            order_by={"created_date": "DESC"},
            limit=25,
            offset=0,
            context_key="filtered_contacts",
        )

        await step.execute(mock_context)

        # Verify API call
        mock_civi_client.get.assert_called_once()
        call_kwargs = mock_civi_client.get.call_args[1]

        # Check where clause includes all filters
        where = call_kwargs["where"]
        assert ["is_deleted", "=", False] in where
        assert ["contact_type", "=", "Individual"] in where
        assert ["created_date", ">=", "2024-01-01"] in where

        # Check other parameters
        assert call_kwargs["select"] == ["id", "display_name", "email_primary.email"]
        assert call_kwargs["order_by"] == {"created_date": "DESC"}
        assert call_kwargs["limit"] == 25

    @pytest.mark.asyncio
    async def test_fetch_step_handles_empty_response(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test CiviFetchStep handles empty API response."""
        from civi_py.contrib.workflows.steps import CiviFetchStep

        # Configure empty response
        empty_response = MagicMock()
        empty_response.values = []
        empty_response.count = 0
        mock_civi_client.get.return_value = empty_response

        step = CiviFetchStep(
            name="fetch_empty",
            entity="Contact",
            context_key="empty_results",
        )

        await step.execute(mock_context)

        # Verify empty results stored
        assert mock_context._data["empty_results"] == []
        assert mock_context._data["empty_results_count"] == 0


class TestCiviMutateStepExecution:
    """Test CiviMutateStep execution with mocked client."""

    @pytest.mark.asyncio
    async def test_mutate_step_create(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviMutateStep creates entities."""
        from civi_py.contrib.workflows.steps import CiviMutateStep

        context = mock_context_factory(
            {
                "new_contacts": [
                    {"display_name": "New Person 1", "email": "new1@example.com"},
                    {"display_name": "New Person 2", "email": "new2@example.com"},
                ],
            },
        )

        step = CiviMutateStep(
            name="create_contacts",
            entity="Contact",
            action="create",
            data_context_key="new_contacts",
            result_context_key="created_contacts",
        )

        await step.execute(context)

        # Verify create was called for each record
        assert mock_civi_client.create.call_count == 2

        # Verify results stored
        assert "created_contacts" in context._data

    @pytest.mark.asyncio
    async def test_mutate_step_update(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviMutateStep updates entities."""
        from civi_py.contrib.workflows.steps import CiviMutateStep

        context = mock_context_factory(
            {
                "updates": [
                    {"id": 1, "first_name": "UpdatedJohn"},
                    {"id": 2, "first_name": "UpdatedJane"},
                ],
            },
        )

        step = CiviMutateStep(
            name="update_contacts",
            entity="Contact",
            action="update",
            data_context_key="updates",
            result_context_key="updated_contacts",
        )

        await step.execute(context)

        # Verify update was called for each record
        assert mock_civi_client.update.call_count == 2

        # Check first update call
        first_call = mock_civi_client.update.call_args_list[0]
        assert first_call[0][0] == "Contact"
        assert first_call[0][2] == [["id", "=", 1]]

    @pytest.mark.asyncio
    async def test_mutate_step_delete(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviMutateStep deletes entities."""
        from civi_py.contrib.workflows.steps import CiviMutateStep

        context = mock_context_factory(
            {
                "to_delete": [{"id": 1}, {"id": 2}],
            },
        )

        step = CiviMutateStep(
            name="delete_contacts",
            entity="Contact",
            action="delete",
            data_context_key="to_delete",
            result_context_key="deleted",
        )

        await step.execute(context)

        # Verify delete was called for each record
        assert mock_civi_client.delete.call_count == 2

        # Verify results
        assert "deleted" in context._data
        assert all(r["deleted"] is True for r in context._data["deleted"])

    @pytest.mark.asyncio
    async def test_mutate_step_handles_empty_data(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviMutateStep handles empty data gracefully."""
        from civi_py.contrib.workflows.steps import CiviMutateStep

        context = mock_context_factory({"empty_data": []})

        step = CiviMutateStep(
            name="empty_create",
            entity="Contact",
            action="create",
            data_context_key="empty_data",
            result_context_key="results",
        )

        await step.execute(context)

        # Should not call client
        mock_civi_client.create.assert_not_called()

        # Should store empty results
        assert context._data["results"] == []


class TestCiviSyncStepExecution:
    """Test CiviSyncStep execution with mocked client."""

    @pytest.mark.asyncio
    async def test_sync_from_civi_stores_in_context(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test CiviSyncStep syncs data to context when no repository."""
        from civi_py.contrib.workflows.steps import CiviSyncStep

        step = CiviSyncStep(
            name="sync_contacts",
            entity="Contact",
            direction="from_civi",
            filters={"is_deleted": False},
            batch_size=100,
            sync_result_key="sync_results",
        )

        await step.execute(mock_context)

        # Verify results
        assert "sync_results" in mock_context._data
        assert mock_context._data["sync_results"]["direction"] == "from_civi"
        assert mock_context._data["sync_results"]["entity"] == "Contact"

        # Verify cache stored
        assert "contact_cache" in mock_context._data

    @pytest.mark.asyncio
    async def test_sync_from_civi_batched_fetch(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test CiviSyncStep fetches in batches."""
        from civi_py.contrib.workflows.steps import CiviSyncStep

        # Configure responses for batched fetching
        batch1 = MagicMock()
        batch1.values = [{"id": i} for i in range(100)]  # Full batch

        batch2 = MagicMock()
        batch2.values = [{"id": i} for i in range(100, 150)]  # Partial batch (end)

        mock_civi_client.get.side_effect = [batch1, batch2]

        step = CiviSyncStep(
            name="sync_large",
            entity="Contact",
            direction="from_civi",
            batch_size=100,
        )

        await step.execute(mock_context)

        # Should have made 2 calls (first full, second partial)
        assert mock_civi_client.get.call_count == 2

        # Verify results
        results = mock_context._data["sync_results"]
        assert results["synced_count"] == 150

    @pytest.mark.asyncio
    async def test_sync_to_civi_from_cache(
        self,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviSyncStep syncs data to CiviCRM from cache."""
        from civi_py.contrib.workflows.steps import CiviSyncStep

        # Pre-populate cache with data to sync
        context = mock_context_factory(
            {
                "contact_cache": [
                    {"id": 1, "display_name": "Updated John"},
                    {"display_name": "New Contact"},  # No ID = create
                ],
            },
        )

        step = CiviSyncStep(
            name="sync_to_civi",
            entity="Contact",
            direction="to_civi",
        )

        await step.execute(context)

        # Verify both update and create were called
        mock_civi_client.update.assert_called_once()
        mock_civi_client.create.assert_called_once()

        # Verify results
        results = context._data["sync_results"]
        assert results["direction"] == "to_civi"
        assert results["updated_count"] == 1
        assert results["created_count"] == 1


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


class TestWorkflowErrorHandling:
    """Test error handling in workflow steps."""

    @pytest.mark.asyncio
    async def test_fetch_step_error_includes_context(
        self,
        mock_civi_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test CiviFetchStep error includes step context."""
        from civi_py.contrib.workflows.steps import CiviFetchStep, CiviWorkflowError

        # Configure client to raise error
        mock_civi_client.get.side_effect = Exception("API connection failed")

        step = CiviFetchStep(
            name="failing_fetch",
            entity="Contact",
            filters={"test": "filter"},
            context_key="results",
        )

        with pytest.raises(CiviWorkflowError) as exc_info:
            await step.execute(mock_context)

        error = exc_info.value
        assert error.step_name == "failing_fetch"
        assert error.details["entity"] == "Contact"
        assert error.details["filters"] == {"test": "filter"}

    @pytest.mark.asyncio
    async def test_mutate_step_missing_data_error(
        self,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviMutateStep raises error for missing data."""
        from civi_py.contrib.workflows.steps import CiviMutateStep, CiviWorkflowError

        context = mock_context_factory()  # No data

        step = CiviMutateStep(
            name="missing_data",
            entity="Contact",
            action="create",
            data_context_key="nonexistent_key",
        )

        with pytest.raises(CiviWorkflowError) as exc_info:
            await step.execute(context)

        assert "No data found" in str(exc_info.value)
        assert "nonexistent_key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_step_without_client_error(
        self,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test steps raise error when CiviClient not in context."""
        from civi_py.contrib.workflows.steps import CiviFetchStep, CiviWorkflowError

        # Create context without client
        context = MagicMock()
        context.get = MagicMock(return_value=None)

        step = CiviFetchStep(name="no_client", entity="Contact")

        with pytest.raises(CiviWorkflowError) as exc_info:
            await step.execute(context)

        assert "CiviClient not found" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Workflow Definition Tests
# -----------------------------------------------------------------------------


class TestWorkflowDefinitions:
    """Test workflow definition structure and configuration."""

    def test_contact_sync_workflow_structure(self) -> None:
        """Test ContactSyncWorkflow has correct structure."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition()

        # Verify metadata
        assert definition.name == "contact_sync"
        assert definition.version == "1.0.0"

        # Verify steps
        assert "fetch_contacts" in definition.steps
        assert "review_contacts" in definition.steps
        assert "sync_approved" in definition.steps

        # Verify initial step
        assert definition.initial_step == "fetch_contacts"

        # Verify terminal steps
        assert "sync_approved" in definition.terminal_steps
        assert "review_contacts" in definition.terminal_steps

        # Verify edges
        assert len(definition.edges) == 2

    def test_bulk_update_workflow_structure(self) -> None:
        """Test BulkUpdateWorkflow has correct structure."""
        from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

        definition = BulkUpdateWorkflow.get_definition(
            entity="Contact",
            update_fields={"do_not_email": True},
        )

        # Verify metadata
        assert definition.name == "bulk_update"

        # Verify steps
        assert "select_entities" in definition.steps
        assert "approve_changes" in definition.steps
        assert "execute_update" in definition.steps
        assert "log_results" in definition.steps

        # Verify initial step
        assert definition.initial_step == "select_entities"

    def test_donation_workflow_structure(self) -> None:
        """Test DonationProcessingWorkflow has correct structure."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        definition = DonationProcessingWorkflow.get_definition(
            approval_threshold=500.0,
        )

        # Verify metadata
        assert definition.name == "donation_processing"

        # Verify steps
        assert "validate_donation" in definition.steps
        assert "approve_donation" in definition.steps
        assert "create_contribution" in definition.steps
        assert "generate_receipt" in definition.steps

        # Verify conditional edges exist
        validate_edges = [e for e in definition.edges if e.source == "validate_donation"]
        assert len(validate_edges) == 2  # One to approve, one to skip


# -----------------------------------------------------------------------------
# Database Persistence Tests (requires pytest-databases)
# -----------------------------------------------------------------------------


@pytest.mark.db
class TestWorkflowPersistence:
    """Test workflow state persistence with real database.

    These tests require pytest-databases and Docker to be available.
    They verify that workflow state can be persisted and recovered
    across step executions.
    """

    @skip_without_postgres
    @pytest.mark.asyncio
    async def test_workflow_persistence_basic(
        self,
        postgres_async_url: str,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test workflow state persists across steps."""
        # This test verifies that workflow context can be serialized
        # and restored when using database persistence.

        # For now, we test the serialization of context data
        context_data = {
            "contacts_to_sync": [
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "Jane Smith"},
            ],
            "sync_config": {
                "batch_size": 100,
                "filters": {"is_deleted": False},
            },
        }

        # Verify data is JSON-serializable (requirement for DB persistence)
        import json

        serialized = json.dumps(context_data)
        deserialized = json.loads(serialized)

        assert deserialized == context_data

    @skip_without_postgres
    @pytest.mark.asyncio
    async def test_sync_step_with_repository(
        self,
        postgres_async_url: str,
        mock_civi_client: AsyncMock,
        mock_context_factory: Callable[..., MagicMock],
    ) -> None:
        """Test CiviSyncStep can use repository for persistence."""
        from civi_py.contrib.workflows.steps import CiviSyncStep

        # Create a mock repository
        mock_repository = AsyncMock()
        mock_repository.upsert_many = AsyncMock()

        context = mock_context_factory(
            {
                "civi_repository": mock_repository,
            },
        )

        step = CiviSyncStep(
            name="sync_with_repo",
            entity="Contact",
            direction="from_civi",
            repository_key="civi_repository",
        )

        await step.execute(context)

        # Verify repository was used
        mock_repository.upsert_many.assert_called_once()


# -----------------------------------------------------------------------------
# Workflow Template Customization Tests
# -----------------------------------------------------------------------------


class TestWorkflowCustomization:
    """Test workflow template customization options."""

    def test_contact_sync_custom_filters(self) -> None:
        """Test ContactSyncWorkflow accepts custom filters."""
        from civi_py.contrib.workflows.templates import ContactSyncWorkflow

        definition = ContactSyncWorkflow.get_definition(
            filters={"contact_type": "Organization", "is_deleted": False},
            select=["id", "organization_name"],
            limit=25,
        )

        fetch_step = definition.steps["fetch_contacts"]
        assert fetch_step.filters == {"contact_type": "Organization", "is_deleted": False}
        assert fetch_step.select == ["id", "organization_name"]
        assert fetch_step.limit == 25

    def test_donation_workflow_custom_threshold(self) -> None:
        """Test DonationProcessingWorkflow custom approval threshold."""
        from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

        # Low threshold
        low_def = DonationProcessingWorkflow.get_definition(approval_threshold=100.0)
        # High threshold
        high_def = DonationProcessingWorkflow.get_definition(approval_threshold=10000.0)

        # Both should have valid definitions
        assert low_def.name == "donation_processing"
        assert high_def.name == "donation_processing"

    def test_bulk_update_custom_entity(self) -> None:
        """Test BulkUpdateWorkflow works with different entities."""
        from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

        # Test with Activity entity
        activity_def = BulkUpdateWorkflow.get_definition(
            entity="Activity",
            select_filters={"activity_type_id": 1},
            update_fields={"status_id": 2},
        )

        select_step = activity_def.steps["select_entities"]
        assert select_step.entity == "Activity"

        execute_step = activity_def.steps["execute_update"]
        assert execute_step.entity == "Activity"
