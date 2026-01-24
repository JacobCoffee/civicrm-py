"""Dependency injection providers for Litestar CiviCRM integration.

Provides dependency providers for injecting CiviClient into route handlers
using Litestar's dependency injection system.

Example:
    >>> from litestar import Litestar, get
    >>> from civicrm_py.core.client import CiviClient
    >>> from civicrm_py.contrib.litestar import CiviPlugin
    >>>
    >>> @get("/contacts")
    ... async def list_contacts(civi_client: CiviClient) -> dict:
    ...     response = await civi_client.get("Contact", limit=10)
    ...     return {"contacts": response.values}
    >>>
    >>> app = Litestar(routes=[list_contacts], plugins=[CiviPlugin()])
"""

import logging
from typing import TYPE_CHECKING, Any

from litestar.datastructures import State

from civicrm_py.core.client import CiviClient

if TYPE_CHECKING:
    from litestar import Litestar

logger = logging.getLogger("civicrm_py.contrib.litestar")

# Key used to store the CiviClient in app.state
CIVI_CLIENT_STATE_KEY = "civi_client"


async def provide_civi_client(state: State) -> CiviClient:
    """Provide CiviClient instance from application state.

    This dependency provider retrieves the CiviClient instance that was
    initialized by the CiviPlugin during application startup.

    Args:
        state: Litestar application state dictionary.

    Returns:
        The initialized CiviClient instance.

    Raises:
        RuntimeError: If CiviClient is not found in application state,
            indicating that CiviPlugin was not properly configured.

    Example:
        >>> from litestar import get
        >>> from civicrm_py.core.client import CiviClient
        >>>
        >>> @get("/contacts/{contact_id:int}")
        ... async def get_contact(contact_id: int, civi_client: CiviClient) -> dict:
        ...     response = await civi_client.get(
        ...         "Contact",
        ...         where=[["id", "=", contact_id]],
        ...         limit=1,
        ...     )
        ...     if not response.values:
        ...         raise NotFoundException(detail="Contact not found")
        ...     return response.values[0]
    """
    client = state.get(CIVI_CLIENT_STATE_KEY)
    if client is None:
        msg = (
            f"CiviClient not found in application state (key: {CIVI_CLIENT_STATE_KEY!r}). "
            "Ensure CiviPlugin is added to app plugins and startup completed successfully."
        )
        raise RuntimeError(msg)
    return client


def get_dependency_providers() -> dict[str, Any]:
    """Get dependency provider mappings for Litestar.

    Returns a dictionary mapping dependency names to their provider
    callables for use with Litestar's dependency injection.

    Returns:
        Dictionary with 'civi_client' mapped to the provider function.

    Example:
        >>> from litestar import Litestar
        >>> from civicrm_py.contrib.litestar.dependencies import get_dependency_providers
        >>>
        >>> app = Litestar(
        ...     route_handlers=[...],
        ...     dependencies=get_dependency_providers(),
        ... )
    """
    from litestar.di import Provide

    return {
        "civi_client": Provide(provide_civi_client),
    }


async def cleanup_client(app: "Litestar") -> None:
    """Clean up CiviClient on application shutdown.

    Closes the CiviClient and releases any held resources (HTTP connections, etc.).
    Called automatically by CiviPlugin during application shutdown.

    Args:
        app: The Litestar application instance.
    """
    client: CiviClient | None = getattr(app.state, CIVI_CLIENT_STATE_KEY, None)
    if client is not None:
        logger.info("Closing CiviClient")
        await client.close()
        delattr(app.state, CIVI_CLIENT_STATE_KEY)


__all__ = [
    "CIVI_CLIENT_STATE_KEY",
    "cleanup_client",
    "get_dependency_providers",
    "provide_civi_client",
]
