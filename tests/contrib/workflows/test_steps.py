"""Tests for CiviCRM workflow step primitives.

These tests verify the workflow step classes work correctly without
requiring litestar-workflows to be installed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from civicrm_py.contrib.workflows import WORKFLOWS_AVAILABLE

# Skip all tests if workflows dependency is not available
pytestmark = pytest.mark.skipif(
    not WORKFLOWS_AVAILABLE,
    reason="litestar-workflows not installed",
)


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock CiviClient."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.create = AsyncMock()
    client.update = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_context(mock_client: AsyncMock) -> MagicMock:
    """Create a mock WorkflowContext."""
    context = MagicMock()
    context_data: dict[str, Any] = {"civi_client": mock_client}

    def get_value(key: str, default: Any = None) -> Any:
        return context_data.get(key, default)

    def set_value(key: str, value: Any) -> None:
        context_data[key] = value

    context.get = MagicMock(side_effect=get_value)
    context.set = MagicMock(side_effect=set_value)
    context._data = context_data  # For test inspection
    return context


class TestCiviFetchStep:
    """Tests for CiviFetchStep."""

    def test_init_requires_entity(self) -> None:
        """Test that entity is required."""
        from civicrm_py.contrib.workflows.steps import CiviFetchStep

        with pytest.raises(ValueError, match="entity is required"):
            CiviFetchStep(name="test", entity="")

    def test_init_requires_name(self) -> None:
        """Test that name is required."""
        from civicrm_py.contrib.workflows.steps import CiviFetchStep

        with pytest.raises(ValueError, match="name is required"):
            CiviFetchStep(name="", entity="Contact")

    def test_init_sets_default_description(self) -> None:
        """Test that description is auto-generated."""
        from civicrm_py.contrib.workflows.steps import CiviFetchStep

        step = CiviFetchStep(name="test", entity="Contact")
        assert step.description == "Fetch Contact records from CiviCRM"

    @pytest.mark.asyncio
    async def test_execute_fetches_data(
        self,
        mock_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test that execute fetches data and stores in context."""
        from civicrm_py.contrib.workflows.steps import CiviFetchStep

        # Setup mock response
        mock_response = MagicMock()
        mock_response.values = [{"id": 1, "display_name": "John Doe"}]
        mock_response.count = 1
        mock_client.get.return_value = mock_response

        step = CiviFetchStep(
            name="fetch_contacts",
            entity="Contact",
            filters={"is_deleted": False},
            context_key="contacts",
        )

        await step.execute(mock_context)

        # Verify client was called correctly
        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["where"] == [["is_deleted", "=", False]]

        # Verify results stored in context
        mock_context.set.assert_any_call("contacts", mock_response.values)
        mock_context.set.assert_any_call("contacts_count", mock_response.count)

    @pytest.mark.asyncio
    async def test_execute_raises_without_client(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Test that execute raises error if no client in context."""
        from civicrm_py.contrib.workflows.steps import CiviFetchStep, CiviWorkflowError

        # Remove client from context
        mock_context._data.pop("civi_client")

        step = CiviFetchStep(name="test", entity="Contact")

        with pytest.raises(CiviWorkflowError, match="CiviClient not found"):
            await step.execute(mock_context)


class TestCiviMutateStep:
    """Tests for CiviMutateStep."""

    def test_init_requires_entity(self) -> None:
        """Test that entity is required."""
        from civicrm_py.contrib.workflows.steps import CiviMutateStep

        with pytest.raises(ValueError, match="entity is required"):
            CiviMutateStep(name="test", entity="")

    def test_init_validates_action(self) -> None:
        """Test that action is validated."""
        from civicrm_py.contrib.workflows.steps import CiviMutateStep

        with pytest.raises(ValueError, match="action must be"):
            CiviMutateStep(name="test", entity="Contact", action="invalid")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_execute_create(
        self,
        mock_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test create action."""
        from civicrm_py.contrib.workflows.steps import CiviMutateStep

        # Setup mock response
        mock_response = MagicMock()
        mock_response.values = [{"id": 1, "display_name": "New Contact"}]
        mock_client.create.return_value = mock_response

        # Add data to context
        mock_context._data["new_contacts"] = [{"display_name": "New Contact"}]

        step = CiviMutateStep(
            name="create_contacts",
            entity="Contact",
            action="create",
            data_context_key="new_contacts",
            result_context_key="created",
        )

        await step.execute(mock_context)

        mock_client.create.assert_called_once()
        # Check result was stored
        assert "created" in mock_context._data

    @pytest.mark.asyncio
    async def test_execute_update_requires_id(
        self,
        mock_context: MagicMock,
    ) -> None:
        """Test that update requires id in records."""
        from civicrm_py.contrib.workflows.steps import CiviMutateStep, CiviWorkflowError

        # Add data without id
        mock_context._data["contacts"] = [{"display_name": "Test"}]

        step = CiviMutateStep(
            name="update_contacts",
            entity="Contact",
            action="update",
            data_context_key="contacts",
        )

        with pytest.raises(CiviWorkflowError, match="missing 'id' field"):
            await step.execute(mock_context)

    @pytest.mark.asyncio
    async def test_execute_delete(
        self,
        mock_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test delete action."""
        from civicrm_py.contrib.workflows.steps import CiviMutateStep

        mock_client.delete.return_value = MagicMock()

        # Add data to context
        mock_context._data["to_delete"] = [{"id": 1}]

        step = CiviMutateStep(
            name="delete_contacts",
            entity="Contact",
            action="delete",
            data_context_key="to_delete",
            result_context_key="deleted",
        )

        await step.execute(mock_context)

        mock_client.delete.assert_called_once_with("Contact", [["id", "=", 1]])


class TestCiviApprovalStep:
    """Tests for CiviApprovalStep."""

    def test_init_requires_name(self) -> None:
        """Test that name is required."""
        from civicrm_py.contrib.workflows.steps import CiviApprovalStep

        with pytest.raises(ValueError, match="name is required"):
            CiviApprovalStep(name="")

    def test_init_creates_form_schema(self) -> None:
        """Test that form schema is created."""
        from civicrm_py.contrib.workflows.steps import CiviApprovalStep

        step = CiviApprovalStep(
            name="review",
            title="Review Data",
            description="Please review",
        )

        assert step.form_schema["type"] == "object"
        assert "approved" in step.form_schema["properties"]
        assert "comments" in step.form_schema["properties"]
        assert "approved" in step.form_schema["required"]

    def test_form_schema_requires_comments_on_reject(self) -> None:
        """Test conditional comments requirement."""
        from civicrm_py.contrib.workflows.steps import CiviApprovalStep

        step = CiviApprovalStep(
            name="review",
            require_comments_on_reject=True,
        )

        assert "allOf" in step.form_schema

    def test_get_review_data_filters_fields(self) -> None:
        """Test that get_review_data filters to show_fields."""
        from civicrm_py.contrib.workflows.steps import CiviApprovalStep

        step = CiviApprovalStep(
            name="review",
            data_context_key="data",
            show_fields=["name", "email"],
        )

        context = MagicMock()
        context.get.return_value = {"name": "John", "email": "john@example.com", "secret": "hidden"}

        result = step.get_review_data(context)

        assert "name" in result
        assert "email" in result
        assert "secret" not in result


class TestCiviSyncStep:
    """Tests for CiviSyncStep."""

    def test_init_requires_entity(self) -> None:
        """Test that entity is required."""
        from civicrm_py.contrib.workflows.steps import CiviSyncStep

        with pytest.raises(ValueError, match="entity is required"):
            CiviSyncStep(name="test", entity="")

    def test_init_validates_direction(self) -> None:
        """Test that direction is validated."""
        from civicrm_py.contrib.workflows.steps import CiviSyncStep

        with pytest.raises(ValueError, match="direction must be"):
            CiviSyncStep(name="test", entity="Contact", direction="invalid")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_sync_from_civi(
        self,
        mock_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Test syncing data from CiviCRM."""
        from civicrm_py.contrib.workflows.steps import CiviSyncStep

        # Setup mock response
        mock_response = MagicMock()
        mock_response.values = [{"id": 1, "display_name": "Test"}]
        mock_client.get.return_value = mock_response

        step = CiviSyncStep(
            name="sync_contacts",
            entity="Contact",
            direction="from_civi",
            batch_size=100,
        )

        await step.execute(mock_context)

        # Should have fetched data
        mock_client.get.assert_called()

        # Results should be in context
        assert "sync_results" in mock_context._data


class TestCiviWorkflowError:
    """Tests for CiviWorkflowError."""

    def test_error_attributes(self) -> None:
        """Test error has correct attributes."""
        from civicrm_py.contrib.workflows.steps import CiviWorkflowError

        error = CiviWorkflowError(
            "Test error",
            step_name="test_step",
            details={"key": "value"},
        )

        assert error.message == "Test error"
        assert error.step_name == "test_step"
        assert error.details == {"key": "value"}


class TestFilterConversion:
    """Tests for filter conversion helper."""

    def test_simple_equality_filter(self) -> None:
        """Test simple equality filters."""
        from civicrm_py.contrib.workflows.steps import _convert_filters_to_where

        filters = {"is_deleted": False, "contact_type": "Individual"}
        result = _convert_filters_to_where(filters)

        assert ["is_deleted", "=", False] in result
        assert ["contact_type", "=", "Individual"] in result

    def test_operator_filter(self) -> None:
        """Test operator-based filters."""
        from civicrm_py.contrib.workflows.steps import _convert_filters_to_where

        filters = {"age": {">=": 18, "<=": 65}}
        result = _convert_filters_to_where(filters)

        assert ["age", ">=", 18] in result
        assert ["age", "<=", 65] in result
