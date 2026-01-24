"""Pytest configuration and fixtures for integration tests.

Provides Docker CiviCRM fixtures for testing against a real CiviCRM instance.
"""

from __future__ import annotations

import contextlib
import os
import socket
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
import pytest

from civicrm_py import CiviClient, CiviSettings, SyncCiviClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

# -----------------------------------------------------------------------------
# Docker CiviCRM Configuration
# -----------------------------------------------------------------------------

# Default settings for Docker CiviCRM container (from docker-compose.yml)
DEFAULT_CIVICRM_HOST = "localhost"
DEFAULT_CIVICRM_PORT = 8080
DEFAULT_CIVICRM_BASE_URL = "http://localhost:8080/civicrm/ajax/api4"

# API credentials - these should be set via environment or generated on setup
DEFAULT_API_KEY = os.environ.get("CIVI_API_KEY", "")
DEFAULT_SITE_KEY = os.environ.get("CIVI_SITE_KEY", "")


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open.

    Args:
        host: Hostname or IP address.
        port: Port number to check.
        timeout: Connection timeout in seconds.

    Returns:
        True if port is open, False otherwise.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def is_civicrm_healthy(base_url: str, timeout: float = 5.0) -> bool:
    """Check if CiviCRM is responding to API requests.

    Args:
        base_url: CiviCRM API base URL.
        timeout: Request timeout in seconds.

    Returns:
        True if CiviCRM is healthy, False otherwise.
    """
    try:
        # Try a simple health check - just verify the server responds
        # We'll try the root path first, then the API path
        parsed = urlparse(base_url)
        health_url = f"{parsed.scheme}://{parsed.netloc}"

        with httpx.Client(timeout=timeout, verify=False) as client:  # noqa: S501
            response = client.get(health_url, follow_redirects=True)
            # Accept any 2xx or 3xx response as healthy
            return response.status_code < 400
    except (httpx.HTTPError, httpx.TimeoutException, OSError):
        return False


def is_docker_civicrm_available() -> bool:
    """Check if Docker CiviCRM container is available and healthy.

    This checks both that the port is open and that CiviCRM is responding.

    Returns:
        True if Docker CiviCRM is available, False otherwise.
    """
    base_url = os.environ.get("CIVI_BASE_URL", DEFAULT_CIVICRM_BASE_URL)
    parsed = urlparse(base_url)
    host = parsed.hostname or DEFAULT_CIVICRM_HOST
    port = parsed.port or DEFAULT_CIVICRM_PORT

    # First check if port is open (quick check)
    if not is_port_open(host, port):
        return False

    # Then check if CiviCRM is healthy (slower but more reliable)
    return is_civicrm_healthy(base_url)


# Skip marker for tests requiring Docker CiviCRM
docker_available = pytest.mark.skipif(
    not is_docker_civicrm_available(),
    reason="Docker CiviCRM not available - run 'make infra-up' to start",
)


# -----------------------------------------------------------------------------
# Settings Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="session")
def docker_civi_settings() -> CiviSettings:
    """Create CiviSettings configured for Docker CiviCRM.

    This is a session-scoped fixture to avoid recreating settings
    for every test.

    Returns:
        CiviSettings configured for Docker CiviCRM container.

    Raises:
        ValueError: If required credentials are not set.
    """
    base_url = os.environ.get("CIVI_BASE_URL", DEFAULT_CIVICRM_BASE_URL)
    api_key = os.environ.get("CIVI_API_KEY", DEFAULT_API_KEY)
    site_key = os.environ.get("CIVI_SITE_KEY", DEFAULT_SITE_KEY)

    if not api_key:
        pytest.skip(
            "CIVI_API_KEY environment variable not set. Set up API credentials in CiviCRM Docker container.",
        )

    return CiviSettings(
        base_url=base_url,
        api_key=api_key,
        site_key=site_key if site_key else None,
        timeout=30,
        verify_ssl=False,  # Docker container uses self-signed cert
        debug=os.environ.get("CIVI_DEBUG", "").lower() in ("true", "1", "yes"),
        max_retries=3,
    )


# -----------------------------------------------------------------------------
# Client Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
async def integration_client(
    docker_civi_settings: CiviSettings,
) -> AsyncGenerator[CiviClient, None]:
    """Create an async CiviClient for integration testing.

    This fixture creates a new client for each test and ensures
    proper cleanup after the test completes.

    Args:
        docker_civi_settings: Settings for Docker CiviCRM.

    Yields:
        Async CiviClient instance.
    """
    async with CiviClient(settings=docker_civi_settings) as client:
        yield client


@pytest.fixture
def sync_integration_client(
    docker_civi_settings: CiviSettings,
) -> Generator[SyncCiviClient, None, None]:
    """Create a sync CiviClient for integration testing.

    This fixture creates a new sync client for each test and ensures
    proper cleanup after the test completes.

    Args:
        docker_civi_settings: Settings for Docker CiviCRM.

    Yields:
        Sync CiviClient instance.
    """
    with SyncCiviClient(settings=docker_civi_settings) as client:
        yield client


# -----------------------------------------------------------------------------
# Test Data Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
async def test_contact(
    integration_client: CiviClient,
) -> AsyncGenerator[dict[str, Any], None]:
    """Create a test contact and clean up after test.

    Creates a unique test contact that can be used in tests,
    then deletes it after the test completes.

    Args:
        integration_client: Async CiviClient instance.

    Yields:
        Dictionary containing created contact data.
    """
    import uuid

    # Create unique test contact
    unique_id = uuid.uuid4().hex[:8]
    contact_data = {
        "contact_type": "Individual",
        "first_name": f"Test_{unique_id}",
        "last_name": f"Integration_{unique_id}",
        "source": "civi-py integration test",
    }

    response = await integration_client.create("Contact", contact_data)
    assert response.values, "Failed to create test contact"

    created_contact = response.values[0]
    contact_id = created_contact["id"]

    yield created_contact

    # Cleanup: delete the test contact
    with contextlib.suppress(Exception):
        await integration_client.delete("Contact", [["id", "=", contact_id]])


@pytest.fixture
async def test_activity(
    integration_client: CiviClient,
    test_contact: dict[str, Any],
) -> AsyncGenerator[dict[str, Any], None]:
    """Create a test activity and clean up after test.

    Creates a test activity associated with the test contact,
    then deletes it after the test completes.

    Args:
        integration_client: Async CiviClient instance.
        test_contact: Test contact fixture.

    Yields:
        Dictionary containing created activity data.
    """
    import uuid

    unique_id = uuid.uuid4().hex[:8]
    activity_data = {
        "activity_type_id": 1,  # Meeting (typically activity_type_id 1)
        "subject": f"Test Activity {unique_id}",
        "activity_date_time": datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "source_contact_id": test_contact["id"],
        "status_id": 1,  # Scheduled
    }

    response = await integration_client.create("Activity", activity_data)
    assert response.values, "Failed to create test activity"

    created_activity = response.values[0]
    activity_id = created_activity["id"]

    yield created_activity

    # Cleanup: delete the test activity
    with contextlib.suppress(Exception):
        await integration_client.delete("Activity", [["id", "=", activity_id]])


@pytest.fixture
def sync_test_contact(
    sync_integration_client: SyncCiviClient,
) -> Generator[dict[str, Any], None, None]:
    """Create a test contact using sync client and clean up after test.

    Args:
        sync_integration_client: Sync CiviClient instance.

    Yields:
        Dictionary containing created contact data.
    """
    import uuid

    unique_id = uuid.uuid4().hex[:8]
    contact_data = {
        "contact_type": "Individual",
        "first_name": f"SyncTest_{unique_id}",
        "last_name": f"Integration_{unique_id}",
        "source": "civi-py sync integration test",
    }

    response = sync_integration_client.create("Contact", contact_data)
    assert response.values, "Failed to create test contact"

    created_contact = response.values[0]
    contact_id = created_contact["id"]

    yield created_contact

    # Cleanup
    with contextlib.suppress(Exception):
        sync_integration_client.delete("Contact", [["id", "=", contact_id]])


# -----------------------------------------------------------------------------
# Utility Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def unique_id() -> str:
    """Generate a unique identifier for test data.

    Returns:
        Unique 8-character hex string.
    """
    import uuid

    return uuid.uuid4().hex[:8]


@pytest.fixture
async def cleanup_contacts(
    integration_client: CiviClient,
) -> AsyncGenerator[list[int], None]:
    """Fixture to track and clean up created contacts.

    Use this fixture to register contact IDs that should be
    cleaned up after the test, even if the test fails.

    Yields:
        List to append contact IDs for cleanup.
    """
    contact_ids: list[int] = []
    yield contact_ids

    # Cleanup all registered contacts
    for contact_id in contact_ids:
        with contextlib.suppress(Exception):
            await integration_client.delete("Contact", [["id", "=", contact_id]])


@pytest.fixture
async def cleanup_activities(
    integration_client: CiviClient,
) -> AsyncGenerator[list[int], None]:
    """Fixture to track and clean up created activities.

    Yields:
        List to append activity IDs for cleanup.
    """
    activity_ids: list[int] = []
    yield activity_ids

    # Cleanup all registered activities
    for activity_id in activity_ids:
        with contextlib.suppress(Exception):
            await integration_client.delete("Activity", [["id", "=", activity_id]])
