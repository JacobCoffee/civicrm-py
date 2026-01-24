"""Health check endpoint for Litestar CiviCRM integration.

Provides a health check endpoint that verifies CiviCRM API connectivity
and returns status information for monitoring systems.

Example:
    >>> # GET /health/civi
    >>> # Response:
    >>> {
    ...     "status": "healthy",
    ...     "civi_connected": true,
    ...     "response_time_ms": 45.2,
    ...     "api_version": "4",
    ...     "timestamp": "2026-01-22T12:00:00Z",
    ... }
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import msgspec
from litestar import get
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from civicrm_py.core.client import CiviClient

logger = logging.getLogger("civicrm_py.contrib.litestar")


class HealthCheckResponse(msgspec.Struct, kw_only=True):
    """Health check response DTO.

    Attributes:
        status: Overall health status ("healthy" or "unhealthy").
        civi_connected: Whether CiviCRM API is reachable.
        response_time_ms: API response time in milliseconds.
        api_version: CiviCRM API version (typically "4").
        timestamp: ISO timestamp of the health check.
        error: Error message if unhealthy.
    """

    status: str
    civi_connected: bool
    response_time_ms: float | None = None
    api_version: str | None = None
    timestamp: str
    error: str | None = None


@get(
    path="/health/civi",
    summary="CiviCRM Health Check",
    description="Check CiviCRM API connectivity and return status information.",
    tags=["Health"],
    operation_id="civi_health_check",
    signature_types=[CiviClient],
)
async def civi_health_check(civi_client: CiviClient) -> Response[HealthCheckResponse]:
    """Check CiviCRM API health and connectivity.

    Performs a lightweight API call to verify that the CiviCRM API is
    reachable and responding. Returns detailed status information for
    monitoring and alerting systems.

    Args:
        civi_client: Injected CiviClient instance from dependency.

    Returns:
        HealthCheckResponse with status information.
        HTTP 200 if healthy, HTTP 503 if unhealthy.

    Example Response (healthy):
        {
            "status": "healthy",
            "civi_connected": true,
            "response_time_ms": 45.2,
            "api_version": "4",
            "timestamp": "2026-01-22T12:00:00Z"
        }

    Example Response (unhealthy):
        {
            "status": "unhealthy",
            "civi_connected": false,
            "response_time_ms": null,
            "timestamp": "2026-01-22T12:00:00Z",
            "error": "Connection timeout"
        }
    """
    timestamp = datetime.now(UTC).isoformat()
    start_time = time.perf_counter()

    try:
        # Use a lightweight API call to check connectivity
        # Simple Contact get with limit=1 to verify API access
        await civi_client.get("Contact", select=["id"], limit=1)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        health_response = HealthCheckResponse(
            status="healthy",
            civi_connected=True,
            response_time_ms=round(elapsed_ms, 2),
            api_version="4",
            timestamp=timestamp,
        )

        return Response(
            content=health_response,
            status_code=HTTP_200_OK,
        )

    except Exception as e:  # noqa: BLE001 - Health checks must catch all errors
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        error_msg = str(e)
        logger.warning("CiviCRM health check failed: %s", error_msg)

        health_response = HealthCheckResponse(
            status="unhealthy",
            civi_connected=False,
            response_time_ms=round(elapsed_ms, 2) if elapsed_ms else None,
            timestamp=timestamp,
            error=error_msg,
        )

        return Response(
            content=health_response,
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
        )


def get_health_check_route(path: str = "/health/civi") -> Callable[..., Response[HealthCheckResponse]]:
    """Create a health check route handler with custom path.

    Factory function to create a health check endpoint at a custom path.

    Args:
        path: URL path for the health check endpoint.

    Returns:
        Route handler function configured for the specified path.

    Example:
        >>> from civicrm_py.contrib.litestar.health import get_health_check_route
        >>> health_route = get_health_check_route("/api/v1/health/civicrm")
    """

    @get(
        path=path,
        summary="CiviCRM Health Check",
        description="Check CiviCRM API connectivity and return status information.",
        tags=["Health"],
        operation_id="civi_health_check_custom",
        signature_types=[CiviClient],
    )
    async def health_check(civi_client: CiviClient) -> Response[HealthCheckResponse]:
        """Health check endpoint with custom path."""
        timestamp = datetime.now(UTC).isoformat()
        start_time = time.perf_counter()

        try:
            await civi_client.get("Contact", select=["id"], limit=1)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return Response(
                content=HealthCheckResponse(
                    status="healthy",
                    civi_connected=True,
                    response_time_ms=round(elapsed_ms, 2),
                    api_version="4",
                    timestamp=timestamp,
                ),
                status_code=HTTP_200_OK,
            )
        except Exception as e:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return Response(
                content=HealthCheckResponse(
                    status="unhealthy",
                    civi_connected=False,
                    response_time_ms=round(elapsed_ms, 2) if elapsed_ms else None,
                    timestamp=timestamp,
                    error=str(e),
                ),
                status_code=HTTP_503_SERVICE_UNAVAILABLE,
            )

    return health_check  # type: ignore[return-value]


__all__ = [
    "HealthCheckResponse",
    "civi_health_check",
    "get_health_check_route",
]
