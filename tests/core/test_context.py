"""Comprehensive integration tests for CiviCRM client context management.

Tests cover:
- get_current_client() returns None when no client set
- set_current_client() and get_current_client() roundtrip
- reset_current_client() restores previous value
- ClientContext sync context manager (with)
- ClientContext async context manager (async with)
- ClientContext as decorator on sync function
- ClientContext as decorator on async function
- use_client generator context manager
- Nested contexts work correctly
- Context isolation across async tasks
"""

# ruff: noqa: EM101, TRY003, PT012, SIM105, SIM117

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
import respx
from httpx import Response

from civicrm_py import CiviClient, CiviSettings
from civicrm_py.core.context import (
    ClientContext,
    client_context,
    get_current_client,
    reset_current_client,
    set_current_client,
    use_client,
)

# Filter out the asyncio.iscoroutinefunction deprecation warning from Python 3.14+
# This is a known issue in the context module that uses asyncio.iscoroutinefunction
pytestmark = pytest.mark.filterwarnings(
    "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning",
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


def _wrapped_use_client(c: CiviClient) -> Generator[CiviClient, None, None]:
    """Wrap use_client with contextmanager for context manager protocol support."""
    yield from use_client(c)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> CiviSettings:
    """Create test CiviSettings."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        verify_ssl=False,
    )


@pytest.fixture
def alternate_settings() -> CiviSettings:
    """Create alternate CiviSettings for nested context tests."""
    return CiviSettings(
        base_url="https://alternate.example.org/civicrm/ajax/api4",
        api_key="alternate-api-key",
        site_key="alternate-site-key",
        timeout=15,
        verify_ssl=False,
    )


@pytest.fixture
def mock_api_response() -> dict:
    """Sample API response for mocking."""
    return {
        "values": [{"id": 1, "display_name": "Test Contact"}],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
async def test_client(test_settings: CiviSettings) -> AsyncGenerator[CiviClient, None]:
    """Create a test CiviClient."""
    async with CiviClient(settings=test_settings) as client:
        yield client


@pytest.fixture
async def alternate_client(alternate_settings: CiviSettings) -> AsyncGenerator[CiviClient, None]:
    """Create an alternate test CiviClient."""
    async with CiviClient(settings=alternate_settings) as client:
        yield client


# -----------------------------------------------------------------------------
# Basic Context Variable Tests
# -----------------------------------------------------------------------------


class TestGetCurrentClient:
    """Tests for get_current_client()."""

    def test_returns_none_when_no_client_set(self) -> None:
        """Test get_current_client returns None when no client is set."""
        # Ensure clean state by resetting any existing client
        token = set_current_client(None)
        try:
            result = get_current_client()
            assert result is None
        finally:
            reset_current_client(token)

    async def test_returns_none_in_fresh_async_context(self) -> None:
        """Test get_current_client returns None in a fresh async context."""
        token = set_current_client(None)
        try:
            result = get_current_client()
            assert result is None
        finally:
            reset_current_client(token)


class TestSetAndGetCurrentClient:
    """Tests for set_current_client() and get_current_client() roundtrip."""

    async def test_set_and_get_roundtrip(self, test_client: CiviClient) -> None:
        """Test setting and getting client works correctly."""
        token = set_current_client(test_client)
        try:
            retrieved = get_current_client()
            assert retrieved is test_client
            assert retrieved.settings.base_url == "https://test.example.org/civicrm/ajax/api4"
        finally:
            reset_current_client(token)

    async def test_set_none_clears_client(self, test_client: CiviClient) -> None:
        """Test setting None clears the current client."""
        token1 = set_current_client(test_client)
        try:
            assert get_current_client() is test_client

            token2 = set_current_client(None)
            try:
                assert get_current_client() is None
            finally:
                reset_current_client(token2)
        finally:
            reset_current_client(token1)

    async def test_set_returns_token(self, test_client: CiviClient) -> None:
        """Test set_current_client returns a valid token."""
        token = set_current_client(test_client)
        try:
            assert token is not None
            # Token should be usable for reset
            reset_current_client(token)
            # After reset, should be back to previous state (None)
            assert get_current_client() is None
        except Exception:
            reset_current_client(token)
            raise


class TestResetCurrentClient:
    """Tests for reset_current_client()."""

    async def test_reset_restores_previous_value(
        self,
        test_client: CiviClient,
        alternate_client: CiviClient,
    ) -> None:
        """Test reset_current_client restores the previous client value."""
        # Set first client
        token1 = set_current_client(test_client)
        try:
            assert get_current_client() is test_client

            # Set second client
            token2 = set_current_client(alternate_client)
            assert get_current_client() is alternate_client

            # Reset to first client
            reset_current_client(token2)
            assert get_current_client() is test_client
        finally:
            reset_current_client(token1)

    async def test_reset_to_none(self, test_client: CiviClient) -> None:
        """Test reset_current_client can restore to None."""
        original_token = set_current_client(None)
        try:
            token = set_current_client(test_client)
            assert get_current_client() is test_client

            reset_current_client(token)
            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_multiple_resets_in_order(self, test_settings: CiviSettings) -> None:
        """Test multiple resets work correctly in order."""
        clients = []
        tokens = []

        # Create multiple clients and set them in sequence
        for i in range(3):
            settings = CiviSettings(
                base_url=f"https://client{i}.example.org/api4",
                api_key=f"key-{i}",
            )
            client = CiviClient(settings=settings)
            clients.append(client)
            tokens.append(set_current_client(client))
            assert get_current_client() is client

        # Reset in reverse order
        for i in range(2, -1, -1):
            reset_current_client(tokens[i])
            if i > 0:
                assert get_current_client() is clients[i - 1]
            else:
                assert get_current_client() is None


# -----------------------------------------------------------------------------
# ClientContext Sync Context Manager Tests
# -----------------------------------------------------------------------------


class TestClientContextSyncContextManager:
    """Tests for ClientContext used as sync context manager."""

    def test_sync_context_manager_sets_client(self, test_settings: CiviSettings) -> None:
        """Test sync context manager sets the client."""
        client = CiviClient(settings=test_settings)

        with ClientContext(client) as ctx_client:
            assert get_current_client() is client
            assert ctx_client is client

    def test_sync_context_manager_resets_after_exit(self, test_settings: CiviSettings) -> None:
        """Test sync context manager resets client after exit."""
        client = CiviClient(settings=test_settings)

        # Ensure clean state
        original_token = set_current_client(None)
        try:
            with ClientContext(client):
                assert get_current_client() is client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_sync_context_manager_resets_on_exception(self, test_settings: CiviSettings) -> None:
        """Test sync context manager resets client even on exception."""
        client = CiviClient(settings=test_settings)

        original_token = set_current_client(None)
        try:
            with pytest.raises(ValueError, match="test error"), ClientContext(client):
                assert get_current_client() is client
                raise ValueError("test error")

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_sync_nested_contexts(self, test_settings: CiviSettings, alternate_settings: CiviSettings) -> None:
        """Test nested sync context managers work correctly."""
        client1 = CiviClient(settings=test_settings)
        client2 = CiviClient(settings=alternate_settings)

        original_token = set_current_client(None)
        try:
            with ClientContext(client1):
                assert get_current_client() is client1

                with ClientContext(client2):
                    assert get_current_client() is client2

                assert get_current_client() is client1

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)


# -----------------------------------------------------------------------------
# ClientContext Async Context Manager Tests
# -----------------------------------------------------------------------------


class TestClientContextAsyncContextManager:
    """Tests for ClientContext used as async context manager."""

    async def test_async_context_manager_sets_client(self, test_client: CiviClient) -> None:
        """Test async context manager sets the client."""
        async with ClientContext(test_client) as ctx_client:
            assert get_current_client() is test_client
            assert ctx_client is test_client

    async def test_async_context_manager_resets_after_exit(self, test_client: CiviClient) -> None:
        """Test async context manager resets client after exit."""
        original_token = set_current_client(None)
        try:
            async with ClientContext(test_client):
                assert get_current_client() is test_client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_async_context_manager_resets_on_exception(self, test_client: CiviClient) -> None:
        """Test async context manager resets client even on exception."""
        original_token = set_current_client(None)
        try:
            with pytest.raises(ValueError, match="async test error"):
                async with ClientContext(test_client):
                    assert get_current_client() is test_client
                    raise ValueError("async test error")

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_async_nested_contexts(
        self,
        test_client: CiviClient,
        alternate_client: CiviClient,
    ) -> None:
        """Test nested async context managers work correctly."""
        original_token = set_current_client(None)
        try:
            async with ClientContext(test_client):
                assert get_current_client() is test_client

                async with ClientContext(alternate_client):
                    assert get_current_client() is alternate_client

                assert get_current_client() is test_client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    @respx.mock
    async def test_async_context_with_api_request(
        self,
        test_settings: CiviSettings,
        mock_api_response: dict,
    ) -> None:
        """Test async context manager works with actual API requests."""
        # Mock the API endpoint
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(200, json=mock_api_response),
        )

        async with CiviClient(settings=test_settings) as client, ClientContext(client):
            current = get_current_client()
            assert current is client

            # Make an API request through the context client
            response = await current.get("Contact", limit=1)
            assert response.count == 1
            assert response.values[0]["id"] == 1


# -----------------------------------------------------------------------------
# ClientContext as Decorator Tests
# -----------------------------------------------------------------------------


class TestClientContextAsDecorator:
    """Tests for ClientContext used as a decorator."""

    def test_decorator_on_sync_function(self, test_settings: CiviSettings) -> None:
        """Test ClientContext as decorator on sync function."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:

            @ClientContext(client)
            def sync_function() -> CiviClient | None:
                return get_current_client()

            result = sync_function()
            assert result is client

            # After function returns, context should be reset
            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_decorator_on_sync_function_with_args(self, test_settings: CiviSettings) -> None:
        """Test ClientContext decorator on sync function with arguments."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:

            @ClientContext(client)
            def sync_function_with_args(x: int, y: int, *, multiplier: int = 1) -> tuple:
                current = get_current_client()
                return (current is client, x + y * multiplier)

            result = sync_function_with_args(1, 2, multiplier=3)
            assert result == (True, 7)

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_decorator_on_sync_function_preserves_metadata(self, test_settings: CiviSettings) -> None:
        """Test ClientContext decorator preserves function metadata."""
        client = CiviClient(settings=test_settings)

        @ClientContext(client)
        def documented_function() -> str:
            """This is the docstring."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is the docstring."

    def test_decorator_on_sync_function_handles_exception(self, test_settings: CiviSettings) -> None:
        """Test ClientContext decorator handles exception in sync function."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:

            @ClientContext(client)
            def sync_function_raises() -> None:
                assert get_current_client() is client
                raise RuntimeError("sync error")

            with pytest.raises(RuntimeError, match="sync error"):
                sync_function_raises()

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_decorator_on_async_function(self, test_client: CiviClient) -> None:
        """Test ClientContext as decorator on async function."""
        original_token = set_current_client(None)

        try:

            @ClientContext(test_client)
            async def async_function() -> CiviClient | None:
                return get_current_client()

            result = await async_function()
            assert result is test_client

            # After function returns, context should be reset
            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_decorator_on_async_function_with_args(self, test_client: CiviClient) -> None:
        """Test ClientContext decorator on async function with arguments."""
        original_token = set_current_client(None)

        try:

            @ClientContext(test_client)
            async def async_function_with_args(x: int, y: int, *, multiplier: int = 1) -> tuple:
                current = get_current_client()
                await asyncio.sleep(0)  # Simulate async operation
                return (current is test_client, x + y * multiplier)

            result = await async_function_with_args(2, 3, multiplier=4)
            assert result == (True, 14)

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_decorator_on_async_function_preserves_metadata(self, test_client: CiviClient) -> None:
        """Test ClientContext decorator preserves async function metadata."""

        @ClientContext(test_client)
        async def documented_async_function() -> str:
            """Async docstring."""
            return "async result"

        assert documented_async_function.__name__ == "documented_async_function"
        assert documented_async_function.__doc__ == "Async docstring."

    async def test_decorator_on_async_function_handles_exception(self, test_client: CiviClient) -> None:
        """Test ClientContext decorator handles exception in async function."""
        original_token = set_current_client(None)

        try:

            @ClientContext(test_client)
            async def async_function_raises() -> None:
                assert get_current_client() is test_client
                raise RuntimeError("async error")

            with pytest.raises(RuntimeError, match="async error"):
                await async_function_raises()

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    @respx.mock
    async def test_decorator_with_api_call(
        self,
        test_settings: CiviSettings,
        mock_api_response: dict,
    ) -> None:
        """Test decorator allows API calls within decorated function."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(200, json=mock_api_response),
        )

        async with CiviClient(settings=test_settings) as client:

            @ClientContext(client)
            async def fetch_contacts() -> list:
                current = get_current_client()
                response = await current.get("Contact", limit=1)
                return response.values

            result = await fetch_contacts()
            assert len(result) == 1
            assert result[0]["display_name"] == "Test Contact"


# -----------------------------------------------------------------------------
# use_client Generator Context Manager Tests
# -----------------------------------------------------------------------------


class TestUseClientContextManager:
    """Tests for use_client generator-based context manager.

    Note: use_client is a generator that needs to be wrapped with
    contextlib.contextmanager to be used as a context manager.
    These tests demonstrate both the raw generator usage and wrapped usage.
    """

    def test_use_client_as_raw_generator(self, test_settings: CiviSettings) -> None:
        """Test use_client as raw generator (manual iteration)."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:
            gen = use_client(client)
            ctx_client = next(gen)

            assert get_current_client() is client
            assert ctx_client is client

            # Clean up by exhausting the generator
            try:
                next(gen)
            except StopIteration:
                pass

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_use_client_wrapped_with_contextmanager(self, test_settings: CiviSettings) -> None:
        """Test use_client wrapped with contextlib.contextmanager."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:
            with contextmanager(_wrapped_use_client)(client) as ctx_client:
                assert get_current_client() is client
                assert ctx_client is client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_use_client_generator_cleanup_on_exception(self, test_settings: CiviSettings) -> None:
        """Test use_client generator cleans up properly on exception."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:
            with pytest.raises(ValueError, match="use_client error"), contextmanager(_wrapped_use_client)(client):
                assert get_current_client() is client
                raise ValueError("use_client error")

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_use_client_generator_nested(
        self,
        test_settings: CiviSettings,
        alternate_settings: CiviSettings,
    ) -> None:
        """Test nested use_client generators."""
        client1 = CiviClient(settings=test_settings)
        client2 = CiviClient(settings=alternate_settings)
        original_token = set_current_client(None)

        try:
            with contextmanager(_wrapped_use_client)(client1):
                assert get_current_client() is client1

                with contextmanager(_wrapped_use_client)(client2):
                    assert get_current_client() is client2

                assert get_current_client() is client1

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_use_client_generator_in_async_context(self, test_client: CiviClient) -> None:
        """Test use_client generator works in async context."""
        original_token = set_current_client(None)

        try:
            with contextmanager(_wrapped_use_client)(test_client):
                assert get_current_client() is test_client
                await asyncio.sleep(0)  # Yield to event loop
                assert get_current_client() is test_client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_use_client_generator_yields_client(self, test_settings: CiviSettings) -> None:
        """Test that use_client generator yields the same client passed in."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:
            gen = use_client(client)
            yielded_client = next(gen)

            # The yielded client should be the same instance
            assert yielded_client is client
            assert yielded_client.settings is client.settings

            # Clean up
            try:
                next(gen)
            except StopIteration:
                pass
        finally:
            reset_current_client(original_token)


# -----------------------------------------------------------------------------
# Nested Context Tests
# -----------------------------------------------------------------------------


class TestNestedContexts:
    """Tests for deeply nested context scenarios."""

    async def test_deeply_nested_contexts(self, test_settings: CiviSettings) -> None:
        """Test multiple levels of nested contexts."""
        clients = []
        original_token = set_current_client(None)

        try:
            for i in range(5):
                settings = CiviSettings(
                    base_url=f"https://nested{i}.example.org/api4",
                    api_key=f"key-{i}",
                )
                clients.append(CiviClient(settings=settings))

            # Create nested contexts manually
            token0 = set_current_client(clients[0])
            assert get_current_client() is clients[0]

            token1 = set_current_client(clients[1])
            assert get_current_client() is clients[1]

            token2 = set_current_client(clients[2])
            assert get_current_client() is clients[2]

            # Unwind
            reset_current_client(token2)
            assert get_current_client() is clients[1]

            reset_current_client(token1)
            assert get_current_client() is clients[0]

            reset_current_client(token0)
            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_mixed_context_managers(
        self,
        test_settings: CiviSettings,
        alternate_settings: CiviSettings,
    ) -> None:
        """Test mixing ClientContext and use_client generator."""
        client1 = CiviClient(settings=test_settings)
        client2 = CiviClient(settings=alternate_settings)
        original_token = set_current_client(None)

        try:
            with ClientContext(client1):
                assert get_current_client() is client1

                with contextmanager(_wrapped_use_client)(client2):
                    assert get_current_client() is client2

                assert get_current_client() is client1

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_context_with_await_between_operations(
        self,
        test_client: CiviClient,
        alternate_client: CiviClient,
    ) -> None:
        """Test context survives across await points."""
        original_token = set_current_client(None)

        try:
            async with ClientContext(test_client):
                assert get_current_client() is test_client

                await asyncio.sleep(0.01)
                assert get_current_client() is test_client

                async with ClientContext(alternate_client):
                    assert get_current_client() is alternate_client
                    await asyncio.sleep(0.01)
                    assert get_current_client() is alternate_client

                await asyncio.sleep(0.01)
                assert get_current_client() is test_client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)


# -----------------------------------------------------------------------------
# Context Isolation Across Async Tasks Tests
# -----------------------------------------------------------------------------


class TestContextIsolationAcrossAsyncTasks:
    """Tests for context variable isolation across async tasks."""

    async def test_context_isolated_between_concurrent_tasks(
        self,
        test_settings: CiviSettings,
        alternate_settings: CiviSettings,
    ) -> None:
        """Test context variables are isolated between concurrent async tasks."""
        client1 = CiviClient(settings=test_settings)
        client2 = CiviClient(settings=alternate_settings)

        results: dict[str, CiviClient | None] = {}

        async def task1() -> None:
            with ClientContext(client1):
                results["task1_start"] = get_current_client()
                await asyncio.sleep(0.05)  # Allow interleaving
                results["task1_end"] = get_current_client()

        async def task2() -> None:
            await asyncio.sleep(0.02)  # Start slightly after task1
            with ClientContext(client2):
                results["task2_start"] = get_current_client()
                await asyncio.sleep(0.05)  # Allow interleaving
                results["task2_end"] = get_current_client()

        await asyncio.gather(task1(), task2())

        # Each task should see its own client throughout
        assert results["task1_start"] is client1
        assert results["task1_end"] is client1
        assert results["task2_start"] is client2
        assert results["task2_end"] is client2

    async def test_context_not_shared_between_tasks(self, test_settings: CiviSettings) -> None:
        """Test setting context in one task doesn't affect another."""
        client = CiviClient(settings=test_settings)
        results: dict[str, CiviClient | None] = {}

        async def task_with_context() -> None:
            with ClientContext(client):
                results["with_context"] = get_current_client()
                await asyncio.sleep(0.05)

        async def task_without_context() -> None:
            await asyncio.sleep(0.02)
            results["without_context"] = get_current_client()

        await asyncio.gather(task_with_context(), task_without_context())

        assert results["with_context"] is client
        assert results["without_context"] is None

    async def test_many_concurrent_tasks_with_different_clients(self) -> None:
        """Test many concurrent tasks each with their own client."""
        num_tasks = 10
        results: dict[int, bool] = {}

        async def task(task_id: int) -> None:
            settings = CiviSettings(
                base_url=f"https://task{task_id}.example.org/api4",
                api_key=f"key-{task_id}",
            )
            client = CiviClient(settings=settings)

            with ClientContext(client):
                # Random sleep to encourage interleaving
                await asyncio.sleep(0.01 * (task_id % 3))

                current = get_current_client()
                # Verify we have our own client
                results[task_id] = current is client and current.settings.api_key == f"key-{task_id}"

        await asyncio.gather(*[task(i) for i in range(num_tasks)])

        # All tasks should have seen their own client
        assert all(results.values())
        assert len(results) == num_tasks

    async def test_task_inherits_parent_context(self, test_client: CiviClient) -> None:
        """Test that a task created within a context inherits the context."""
        result: dict[str, CiviClient | None] = {}

        async def child_task() -> None:
            result["child"] = get_current_client()

        with ClientContext(test_client):
            # Create and run child task within context
            result["parent_before"] = get_current_client()
            await child_task()
            result["parent_after"] = get_current_client()

        # Child should inherit parent's context
        assert result["parent_before"] is test_client
        assert result["child"] is test_client
        assert result["parent_after"] is test_client

    async def test_task_context_modification_doesnt_affect_parent(
        self,
        test_client: CiviClient,
        alternate_client: CiviClient,
    ) -> None:
        """Test child task modifying context doesn't affect parent."""
        results: dict[str, CiviClient | None] = {}

        async def child_task_modifies_context() -> None:
            results["child_before"] = get_current_client()
            with ClientContext(alternate_client):
                results["child_during"] = get_current_client()
                await asyncio.sleep(0.01)
            results["child_after"] = get_current_client()

        with ClientContext(test_client):
            results["parent_before"] = get_current_client()
            await child_task_modifies_context()
            results["parent_after"] = get_current_client()

        # Parent should maintain its context
        assert results["parent_before"] is test_client
        assert results["parent_after"] is test_client

        # Child should see its own modifications
        assert results["child_before"] is test_client  # Inherited from parent
        assert results["child_during"] is alternate_client  # Modified by child
        assert results["child_after"] is test_client  # Restored after context exit


# -----------------------------------------------------------------------------
# Alias and Backward Compatibility Tests
# -----------------------------------------------------------------------------


class TestAliasAndBackwardCompatibility:
    """Tests for client_context alias and backward compatibility."""

    def test_client_context_alias_exists(self) -> None:
        """Test client_context alias is the same as ClientContext."""
        assert client_context is ClientContext

    def test_client_context_alias_works(self, test_settings: CiviSettings) -> None:
        """Test client_context alias works as context manager."""
        client = CiviClient(settings=test_settings)
        original_token = set_current_client(None)

        try:
            with client_context(client):
                assert get_current_client() is client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)


# -----------------------------------------------------------------------------
# Integration Tests with HTTP Mocking
# -----------------------------------------------------------------------------


class TestContextIntegrationWithHTTP:
    """Integration tests combining context with HTTP operations."""

    @respx.mock
    async def test_context_manager_with_real_request(
        self,
        test_settings: CiviSettings,
        mock_api_response: dict,
    ) -> None:
        """Test context manager works with real HTTP requests."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(200, json=mock_api_response),
        )

        async with CiviClient(settings=test_settings) as client:
            with ClientContext(client):
                current = get_current_client()
                assert current is client

                response = await current.get("Contact", limit=1)
                assert response.count == 1

    @respx.mock
    async def test_decorated_function_with_request(
        self,
        test_settings: CiviSettings,
        mock_api_response: dict,
    ) -> None:
        """Test decorated function can make HTTP requests."""
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(200, json=mock_api_response),
        )

        async with CiviClient(settings=test_settings) as client:

            @ClientContext(client)
            async def fetch_first_contact() -> dict:
                current = get_current_client()
                response = await current.get("Contact", limit=1)
                return response.values[0]

            result = await fetch_first_contact()
            assert result["id"] == 1
            assert result["display_name"] == "Test Contact"

    @respx.mock
    async def test_nested_context_with_different_endpoints(
        self,
        test_settings: CiviSettings,
        alternate_settings: CiviSettings,
    ) -> None:
        """Test nested contexts hitting different API endpoints."""
        # Mock both endpoints
        respx.post("https://test.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 1, "source": "primary"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )
        respx.post("https://alternate.example.org/civicrm/ajax/api4/Contact/get").mock(
            return_value=Response(
                200,
                json={
                    "values": [{"id": 2, "source": "alternate"}],
                    "count": 1,
                    "countFetched": 1,
                },
            ),
        )

        async with CiviClient(settings=test_settings) as client1:
            async with CiviClient(settings=alternate_settings) as client2:
                async with ClientContext(client1):
                    response1 = await get_current_client().get("Contact", limit=1)
                    assert response1.values[0]["source"] == "primary"

                    async with ClientContext(client2):
                        response2 = await get_current_client().get("Contact", limit=1)
                        assert response2.values[0]["source"] == "alternate"

                    # Back to client1
                    response3 = await get_current_client().get("Contact", limit=1)
                    assert response3.values[0]["source"] == "primary"


# -----------------------------------------------------------------------------
# Edge Cases and Error Handling
# -----------------------------------------------------------------------------


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling."""

    def test_reusing_client_context_instance(self, test_settings: CiviSettings) -> None:
        """Test that ClientContext instance can be reused."""
        client = CiviClient(settings=test_settings)
        ctx = ClientContext(client)
        original_token = set_current_client(None)

        try:
            # First use
            with ctx:
                assert get_current_client() is client

            assert get_current_client() is None

            # Second use (reuse same instance)
            with ctx:
                assert get_current_client() is client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    async def test_async_reusing_client_context_instance(self, test_client: CiviClient) -> None:
        """Test that ClientContext instance can be reused in async context."""
        ctx = ClientContext(test_client)
        original_token = set_current_client(None)

        try:
            # First use
            async with ctx:
                assert get_current_client() is test_client

            assert get_current_client() is None

            # Second use (reuse same instance)
            async with ctx:
                assert get_current_client() is test_client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)

    def test_context_with_none_client(self) -> None:
        """Test behavior when setting None as client in context."""
        # This is technically valid - allows temporarily clearing context
        original_token = set_current_client(None)

        try:
            # Note: ClientContext expects a CiviClient, but we test the edge case
            token = set_current_client(None)
            assert get_current_client() is None
            reset_current_client(token)
        finally:
            reset_current_client(original_token)

    async def test_generator_exit_called_properly(self, test_settings: CiviSettings) -> None:
        """Test use_client generator cleanup is called properly."""
        client = CiviClient(settings=test_settings)
        cleanup_called = False
        original_token = set_current_client(None)

        try:
            gen = use_client(client)
            yielded_client = next(gen)
            assert yielded_client is client
            assert get_current_client() is client

            try:
                gen.send(None)
            except StopIteration:
                cleanup_called = True

            # After generator completes, context should be reset
            assert get_current_client() is None
            assert cleanup_called
        finally:
            reset_current_client(original_token)

    async def test_rapid_context_switching(self, test_settings: CiviSettings) -> None:
        """Test rapid context switching doesn't cause issues."""
        clients = [
            CiviClient(settings=CiviSettings(base_url=f"https://rapid{i}.example.org/api4", api_key=f"key-{i}"))
            for i in range(100)
        ]

        original_token = set_current_client(None)

        try:
            for client in clients:
                with ClientContext(client):
                    assert get_current_client() is client

            assert get_current_client() is None
        finally:
            reset_current_client(original_token)
