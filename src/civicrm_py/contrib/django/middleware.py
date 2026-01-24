"""Django middleware for request-scoped CiviCRM client.

Provides CiviMiddleware that attaches a CiviCRM client to each Django request,
making it available via request.civi_client in views.

The middleware supports both WSGI (sync) and ASGI (async) Django deployments:

- WSGI mode: Uses SyncCiviClient for traditional Django applications
- ASGI mode: Uses CiviClient (async) for Django 5+ async views

Example WSGI usage:

    # settings.py
    MIDDLEWARE = [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        ...
        'civicrm_py.contrib.django.middleware.CiviMiddleware',
    ]

    CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
    CIVICRM_API_KEY = "your-api-key"

    # views.py
    def contact_list(request):
        client = request.civi_client
        response = client.get("Contact", limit=10)
        return JsonResponse({"contacts": response.values})

Example ASGI usage with async views:

    # settings.py (same middleware configuration)
    MIDDLEWARE = [
        ...
        'civicrm_py.contrib.django.middleware.CiviMiddleware',
    ]

    # views.py
    async def contact_list(request):
        client = request.civi_client
        response = await client.get("Contact", limit=10)
        return JsonResponse({"contacts": response.values})
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from civicrm_py.core.exceptions import CiviConfigError, CiviIntegrationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

    from civicrm_py.core.client import CiviClient, SyncCiviClient

logger = logging.getLogger(__name__)

# Thread-local storage for sync clients
_local = threading.local()

# Module-level async client (for ASGI)
_async_client: CiviClient | None = None
_async_client_lock = asyncio.Lock()


def _get_sync_client() -> SyncCiviClient:
    """Get or create a thread-local sync client.

    Creates a SyncCiviClient instance for the current thread using
    thread-local storage. The client is lazily initialized on first
    access and reused for subsequent requests in the same thread.

    Returns:
        SyncCiviClient instance for the current thread.

    Raises:
        CiviIntegrationError: If Django is not configured.
        CiviConfigError: If CiviCRM settings are missing.
    """
    client: SyncCiviClient | None = getattr(_local, "client", None)

    if client is None:
        from civicrm_py.contrib.django.settings import get_civi_settings
        from civicrm_py.core.client import SyncCiviClient

        settings = get_civi_settings()
        client = SyncCiviClient(settings=settings)
        _local.client = client
        logger.debug(
            "Created thread-local CiviCRM client for thread %s",
            threading.current_thread().name,
        )

    return client


async def _get_async_client() -> CiviClient:
    """Get or create the async client.

    Creates a CiviClient instance for async operations. The client
    is shared across all async requests (coroutines run in a single thread).

    Returns:
        CiviClient instance for async operations.

    Raises:
        CiviIntegrationError: If Django is not configured.
        CiviConfigError: If CiviCRM settings are missing.
    """
    global _async_client  # noqa: PLW0603

    if _async_client is None:
        async with _async_client_lock:
            # Double-check after acquiring lock
            if _async_client is None:
                from civicrm_py.contrib.django.settings import get_civi_settings
                from civicrm_py.core.client import CiviClient

                settings = get_civi_settings()
                _async_client = CiviClient(settings=settings)
                logger.debug("Created async CiviCRM client")

    return _async_client


class CiviMiddleware:
    """Django middleware for request-scoped CiviCRM client.

    This middleware attaches a CiviCRM client to each request object,
    making it available via `request.civi_client` in views.

    The middleware automatically detects whether the request is being
    handled synchronously (WSGI) or asynchronously (ASGI) and provides
    the appropriate client type:

    - Sync requests: SyncCiviClient (thread-safe via thread-local storage)
    - Async requests: CiviClient (shared async client)

    Thread Safety:
        For sync (WSGI) requests, each thread gets its own SyncCiviClient
        instance stored in thread-local storage. This is safe for
        multi-threaded WSGI servers like Gunicorn with sync workers.

        For async (ASGI) requests, a single async CiviClient is shared
        across all requests since coroutines run in a single thread.

    Configuration:
        The middleware reads configuration from Django settings:

        - CIVICRM_URL (required): Base URL for CiviCRM API v4
        - CIVICRM_API_KEY: API key for authentication
        - CIVICRM_SITE_KEY: Optional site key
        - CIVICRM_TIMEOUT: Request timeout (default: 30)
        - CIVICRM_VERIFY_SSL: SSL verification (default: True)
        - CIVICRM_DEBUG: Debug mode (default: False)
        - CIVICRM_MAX_RETRIES: Max retries (default: 3)

    Error Handling:
        If CiviCRM is not configured (missing CIVICRM_URL), the middleware
        logs a warning but does not raise an exception. The request.civi_client
        attribute will not be set, allowing graceful degradation.

    Attributes:
        get_response: The next middleware or view in the chain.
        sync_capable: True, this middleware supports sync mode.
        async_capable: True, this middleware supports async mode.

    Example:
        # settings.py
        MIDDLEWARE = [
            ...
            'civicrm_py.contrib.django.middleware.CiviMiddleware',
        ]

        # views.py (sync)
        def list_contacts(request):
            client = request.civi_client
            response = client.get("Contact", limit=10)
            return JsonResponse({"contacts": response.values})

        # views.py (async)
        async def list_contacts_async(request):
            client = request.civi_client
            response = await client.get("Contact", limit=10)
            return JsonResponse({"contacts": response.values})
    """

    # Django 3.1+ middleware markers
    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        """Initialize the middleware.

        Args:
            get_response: The next middleware or view callable in the chain.
                May be a sync or async callable depending on Django's
                middleware configuration.

        Note:
            Django passes a sync callable for WSGI deployments and an
            async callable for ASGI deployments. The middleware adapts
            its behavior based on whether get_response is a coroutine.
        """
        self.get_response = get_response
        self._configuration_valid: bool | None = None

        # Mark this middleware as async if get_response is async
        # This tells Django to call __acall__ instead of __call__
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

        logger.debug("CiviMiddleware initialized (async=%s)", iscoroutinefunction(self))

    def _check_configuration(self) -> bool:
        """Check if CiviCRM is properly configured.

        Returns:
            True if configuration is valid, False otherwise.
        """
        if self._configuration_valid is not None:
            return self._configuration_valid

        try:
            from civicrm_py.contrib.django.settings import get_civi_settings

            get_civi_settings()
            self._configuration_valid = True
            logger.debug("CiviCRM configuration validated")
        except (CiviConfigError, CiviIntegrationError) as e:
            logger.warning(
                "CiviCRM not configured, middleware will not attach client: %s",
                e,
            )
            self._configuration_valid = False

        return self._configuration_valid

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Handle synchronous request (WSGI mode).

        Attaches a SyncCiviClient to the request object and passes
        the request to the next middleware or view.

        Args:
            request: The Django HttpRequest object.

        Returns:
            The HttpResponse from the view or next middleware.
        """
        if self._check_configuration():
            try:
                client = _get_sync_client()
                request.civi_client = client  # type: ignore[attr-defined]
                logger.debug("Attached sync CiviCRM client to request")
            except Exception:
                logger.exception("Failed to create CiviCRM client")

        return self.get_response(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        """Handle asynchronous request (ASGI mode).

        Attaches an async CiviClient to the request object and passes
        the request to the next middleware or view.

        This method is called by Django when running in ASGI mode with
        async views.

        Args:
            request: The Django HttpRequest object.

        Returns:
            The HttpResponse from the view or next middleware.
        """
        if self._check_configuration():
            try:
                client = await _get_async_client()
                request.civi_client = client  # type: ignore[attr-defined]
                logger.debug("Attached async CiviCRM client to request")
            except Exception:
                logger.exception("Failed to create async CiviCRM client")

        return await self.get_response(request)


def get_client_from_request(request: HttpRequest) -> SyncCiviClient | CiviClient:
    """Get the CiviCRM client from a Django request.

    Retrieves the client attached by CiviMiddleware. This is a helper
    function for cases where you need to verify the client exists or
    want clearer error messages.

    Args:
        request: The Django HttpRequest object.

    Returns:
        The CiviCRM client (sync or async depending on mode).

    Raises:
        AttributeError: If civi_client is not attached to the request.
            This typically means CiviMiddleware is not in MIDDLEWARE
            or CiviCRM is not configured.

    Example:
        from civicrm_py.contrib.django.middleware import get_client_from_request

        def my_view(request):
            try:
                client = get_client_from_request(request)
            except AttributeError:
                return JsonResponse({"error": "CiviCRM not available"}, status=503)
            return JsonResponse({"contacts": client.get("Contact").values})
    """
    client: SyncCiviClient | CiviClient | None = getattr(
        request,
        "civi_client",
        None,
    )

    if client is None:
        msg = (
            "CiviCRM client not found on request. Ensure CiviMiddleware is "
            "in MIDDLEWARE and CiviCRM is properly configured."
        )
        raise AttributeError(msg)

    return client


def close_clients() -> None:
    """Close all CiviCRM clients.

    Closes the thread-local sync client (if any) and the shared async
    client. This function should be called during application shutdown
    to properly release resources.

    For most Django deployments, this is not necessary as clients will
    be cleaned up when the process exits. However, it can be useful in
    testing scenarios or when you need to explicitly release connections.

    Note:
        This only closes the client in the current thread's local storage.
        Other threads will still have their clients until they are closed
        or the threads terminate.

    Example:
        import atexit
        from civicrm_py.contrib.django.middleware import close_clients

        atexit.register(close_clients)
    """
    # Close thread-local sync client
    client: SyncCiviClient | None = getattr(_local, "client", None)
    if client is not None:
        try:
            client.close()
            logger.debug(
                "Closed thread-local CiviCRM client for thread %s",
                threading.current_thread().name,
            )
        except Exception:
            logger.exception("Error closing thread-local CiviCRM client")
        finally:
            _local.client = None

    # Close async client (note: this is sync close, use close_clients_async for async)
    if _async_client is not None:
        logger.warning(
            "Async client exists but close_clients() is a sync function. Use close_clients_async() in async contexts.",
        )


async def close_clients_async() -> None:
    """Close all CiviCRM clients (async version).

    Async version of close_clients that properly closes the async client.
    Call this in ASGI application shutdown hooks.

    Example:
        # In ASGI application
        async def lifespan(scope, receive, send):
            ...
            await close_clients_async()
    """
    global _async_client  # noqa: PLW0603

    # Close async client
    if _async_client is not None:
        async with _async_client_lock:
            if _async_client is not None:
                try:
                    await _async_client.close()
                    logger.debug("Closed async CiviCRM client")
                except Exception:
                    logger.exception("Error closing async CiviCRM client")
                finally:
                    _async_client = None


__all__ = [
    "CiviMiddleware",
    "close_clients",
    "close_clients_async",
    "get_client_from_request",
]
