"""Context management for CiviCRM client instances.

Provides thread-local and async context variables for managing the current
CiviClient instance, enabling the .objects pattern on entity classes.
"""

from __future__ import annotations

import asyncio
import functools
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import TracebackType

    from civicrm_py.core.client import CiviClient

P = ParamSpec("P")
R = TypeVar("R")

# Context variable to hold the current client
# Using cast to satisfy ty's strict type checking for ContextVar default
_current_client: ContextVar[CiviClient | None] = cast(
    "ContextVar[CiviClient | None]",
    ContextVar("civi_client", default=None),
)


def get_current_client() -> CiviClient | None:
    """Get the current CiviClient from context.

    Returns:
        The current CiviClient instance or None if not set.

    Example:
        client = get_current_client()
        if client is not None:
            response = await client.request("Contact", "get")
    """
    return _current_client.get()


def set_current_client(client: CiviClient | None) -> Token[CiviClient | None]:
    """Set the current CiviClient in context.

    Args:
        client: The CiviClient instance to set, or None to clear.

    Returns:
        A token that can be used to reset the context.

    Example:
        token = set_current_client(my_client)
        try:
            # Use client via Contact.objects, etc.
            contacts = await Contact.objects.all().execute()
        finally:
            _current_client.reset(token)
    """
    return _current_client.set(client)


def reset_current_client(token: Token[CiviClient | None]) -> None:
    """Reset the current client context to a previous state.

    Args:
        token: The token returned by set_current_client().
    """
    _current_client.reset(token)


class ClientContext:
    """Context manager for setting the current CiviClient.

    This allows using the .objects pattern on entity classes within
    a specific client context.

    Example:
        async with CiviClient() as client:
            with ClientContext(client):
                # Contact.objects now uses this client
                contacts = await Contact.objects.filter(is_deleted=False).all()

        # Or as a decorator
        @ClientContext(client)
        async def my_function():
            return await Contact.objects.all().execute()
    """

    def __init__(self, client: CiviClient) -> None:
        """Initialize context manager.

        Args:
            client: The CiviClient instance to use.
        """
        self._client = client
        self._token: Token[CiviClient | None] | None = None

    def __enter__(self) -> CiviClient:
        """Enter context and set client."""
        self._token = set_current_client(self._client)
        return self._client

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context and reset client."""
        if self._token is not None:
            reset_current_client(self._token)

    async def __aenter__(self) -> CiviClient:
        """Enter async context and set client."""
        self._token = set_current_client(self._client)
        return self._client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context and reset client."""
        if self._token is not None:
            reset_current_client(self._token)

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """Decorator support.

        Args:
            func: Function to wrap.

        Returns:
            Wrapped function that runs with this client context.
        """
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                async with self:
                    return await func(*args, **kwargs)  # type: ignore[misc]

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with self:
                return func(*args, **kwargs)

        return sync_wrapper


# Alias for backward compatibility / convenience
client_context = ClientContext


def use_client(client: CiviClient) -> Generator[CiviClient, None, None]:
    """Generator-based context manager for setting the current client.

    This is an alternative to ClientContext that works with contextlib.

    Args:
        client: The CiviClient instance to use.

    Yields:
        The client instance.

    Example:
        from contextlib import contextmanager

        async with CiviClient() as client:
            with use_client(client):
                contacts = await Contact.objects.all().execute()
    """
    token = set_current_client(client)
    try:
        yield client
    finally:
        reset_current_client(token)


__all__ = [
    "ClientContext",
    "client_context",
    "get_current_client",
    "reset_current_client",
    "set_current_client",
    "use_client",
]
