"""Pytest configuration and fixtures for civi-py tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from civi_py import CiviClient, CiviSettings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# -----------------------------------------------------------------------------
# Database Testing Configuration (pytest-databases)
# -----------------------------------------------------------------------------
#
# This section configures pytest-databases for Docker-based database testing.
# These fixtures enable integration testing with real PostgreSQL databases.
# Requires Docker to be running for database container management.
#
# MySQL Support Status:
# MySQL fixtures are not currently available because mysql-connector-python
# (required by pytest-databases[mysql]) does not support Python 3.13+.
# To enable MySQL support when available:
#   1. Add "pytest-databases[mysql]" to pyproject.toml test dependencies
#   2. Add MySQL import and plugin registration below
#   3. Uncomment the mysql_url and mysql_async_url fixtures

try:
    from pytest_databases.docker.postgres import PostgresService

    POSTGRES_AVAILABLE = True
except ImportError:
    PostgresService = None  # type: ignore[misc, assignment]
    POSTGRES_AVAILABLE = False

# MySQL support disabled - see note above
MYSQL_AVAILABLE = False
MySQLService = None  # type: ignore[misc, assignment]

DATABASES_AVAILABLE = POSTGRES_AVAILABLE or MYSQL_AVAILABLE

# Register database plugins if available
# This must be a module-level variable for pytest to discover
pytest_plugins: list[str] = []

if POSTGRES_AVAILABLE:
    pytest_plugins.append("pytest_databases.docker.postgres")


@pytest.fixture
def civi_settings() -> CiviSettings:
    """Create test CiviSettings."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        verify_ssl=False,
    )


@pytest.fixture
def mock_transport(respx_mock: Any) -> Any:
    """Create a mock transport for testing."""
    return respx_mock


@pytest.fixture
async def civi_client(
    civi_settings: CiviSettings,
) -> AsyncGenerator[CiviClient, None]:
    """Create a test CiviClient with mocked HTTP."""
    async with CiviClient(settings=civi_settings) as client:
        yield client


@pytest.fixture
def sample_contact_response() -> dict[str, Any]:
    """Sample contact response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "display_name": "John Doe",
                "first_name": "John",
                "last_name": "Doe",
                "contact_type": "Individual",
                "email_primary.email": "john@example.com",
                "is_deleted": False,
            },
            {
                "id": 2,
                "display_name": "Jane Smith",
                "first_name": "Jane",
                "last_name": "Smith",
                "contact_type": "Individual",
                "email_primary.email": "jane@example.com",
                "is_deleted": False,
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_contact() -> dict[str, Any]:
    """Sample single contact response."""
    return {
        "values": [
            {
                "id": 1,
                "display_name": "John Doe",
                "first_name": "John",
                "last_name": "Doe",
                "contact_type": "Individual",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_create_response() -> dict[str, Any]:
    """Sample response from create action."""
    return {
        "values": [
            {
                "id": 100,
                "display_name": "New Contact",
                "first_name": "New",
                "last_name": "Contact",
                "contact_type": "Individual",
            },
        ],
        "count": 1,
    }


@pytest.fixture
def sample_contact_create_response() -> dict[str, Any]:
    """Sample contact create response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 100,
                "display_name": "New Contact",
                "first_name": "New",
                "last_name": "Contact",
                "contact_type": "Individual",
                "email_primary.email": "new@example.com",
                "is_deleted": False,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Activity Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_activity_response() -> dict[str, Any]:
    """Sample activity list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "activity_type_id": 3,
                "subject": "Follow up call with John",
                "details": "<p>Discussed project requirements and next steps.</p>",
                "activity_date_time": "2024-01-15 10:30:00",
                "duration": 30,
                "location": "Phone",
                "status_id": 2,
                "priority_id": 2,
                "source_contact_id": 1,
                "target_contact_id": [2],
                "assignee_contact_id": [1],
                "is_current_revision": True,
                "is_deleted": False,
                "is_test": False,
                "is_auto": False,
                "medium_id": 2,
                "created_date": "2024-01-15 09:00:00",
                "modified_date": "2024-01-15 11:00:00",
            },
            {
                "id": 2,
                "activity_type_id": 1,
                "subject": "Meeting with stakeholders",
                "details": "<p>Quarterly review meeting.</p>",
                "activity_date_time": "2024-01-16 14:00:00",
                "duration": 60,
                "location": "Conference Room A",
                "status_id": 1,
                "priority_id": 3,
                "source_contact_id": 1,
                "target_contact_id": [2, 3, 4],
                "assignee_contact_id": [1, 5],
                "is_current_revision": True,
                "is_deleted": False,
                "is_test": False,
                "is_auto": False,
                "medium_id": 1,
                "created_date": "2024-01-14 16:00:00",
                "modified_date": "2024-01-14 16:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_activity() -> dict[str, Any]:
    """Sample single activity response."""
    return {
        "values": [
            {
                "id": 1,
                "activity_type_id": 3,
                "subject": "Follow up call with John",
                "details": "<p>Discussed project requirements and next steps.</p>",
                "activity_date_time": "2024-01-15 10:30:00",
                "duration": 30,
                "location": "Phone",
                "status_id": 2,
                "priority_id": 2,
                "source_contact_id": 1,
                "is_deleted": False,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_activity_create_response() -> dict[str, Any]:
    """Sample activity create response."""
    return {
        "values": [
            {
                "id": 100,
                "activity_type_id": 3,
                "subject": "New activity",
                "activity_date_time": "2024-01-20 09:00:00",
                "status_id": 1,
                "source_contact_id": 1,
                "is_deleted": False,
                "created_date": "2024-01-20 08:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Contribution Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_contribution_response() -> dict[str, Any]:
    """Sample contribution list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "financial_type_id": 1,
                "payment_instrument_id": 1,
                "receive_date": "2024-01-10 12:00:00",
                "total_amount": 100.00,
                "fee_amount": 2.50,
                "net_amount": 97.50,
                "trxn_id": "TXN-001-2024",
                "invoice_id": "INV-001",
                "invoice_number": "INV-2024-001",
                "currency": "USD",
                "source": "Online donation",
                "contribution_status_id": 1,
                "is_test": False,
                "is_pay_later": False,
                "is_template": False,
                "created_date": "2024-01-10 12:00:00",
                "modified_date": "2024-01-10 12:00:00",
            },
            {
                "id": 2,
                "contact_id": 2,
                "financial_type_id": 2,
                "payment_instrument_id": 4,
                "receive_date": "2024-01-11 15:30:00",
                "total_amount": 250.00,
                "fee_amount": 0.00,
                "net_amount": 250.00,
                "trxn_id": "CHK-1234",
                "invoice_id": "INV-002",
                "invoice_number": "INV-2024-002",
                "currency": "USD",
                "check_number": "1234",
                "source": "Membership dues",
                "contribution_status_id": 1,
                "is_test": False,
                "is_pay_later": False,
                "is_template": False,
                "created_date": "2024-01-11 15:30:00",
                "modified_date": "2024-01-11 15:30:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_contribution() -> dict[str, Any]:
    """Sample single contribution response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "financial_type_id": 1,
                "total_amount": 100.00,
                "currency": "USD",
                "receive_date": "2024-01-10 12:00:00",
                "contribution_status_id": 1,
                "source": "Online donation",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_contribution_create_response() -> dict[str, Any]:
    """Sample contribution create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 1,
                "financial_type_id": 1,
                "total_amount": 50.00,
                "currency": "USD",
                "receive_date": "2024-01-20 10:00:00",
                "contribution_status_id": 1,
                "source": "API Test",
                "created_date": "2024-01-20 10:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Event Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_event_response() -> dict[str, Any]:
    """Sample event list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "title": "Annual Conference 2024",
                "summary": "Join us for our annual conference.",
                "description": "<p>Full day conference with workshops.</p>",
                "event_type_id": 1,
                "is_public": True,
                "start_date": "2024-06-15 09:00:00",
                "end_date": "2024-06-15 17:00:00",
                "is_online_registration": True,
                "registration_start_date": "2024-01-01 00:00:00",
                "registration_end_date": "2024-06-14 23:59:59",
                "max_participants": 200,
                "is_monetary": True,
                "financial_type_id": 4,
                "currency": "USD",
                "is_active": True,
                "is_template": False,
                "created_date": "2024-01-01 10:00:00",
                "modified_date": "2024-01-05 14:00:00",
            },
            {
                "id": 2,
                "title": "Monthly Networking Meetup",
                "summary": "Casual networking event.",
                "description": "<p>Meet other members.</p>",
                "event_type_id": 2,
                "is_public": True,
                "start_date": "2024-02-10 18:00:00",
                "end_date": "2024-02-10 20:00:00",
                "is_online_registration": True,
                "max_participants": 50,
                "is_monetary": False,
                "is_active": True,
                "is_template": False,
                "created_date": "2024-01-15 09:00:00",
                "modified_date": "2024-01-15 09:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_event() -> dict[str, Any]:
    """Sample single event response."""
    return {
        "values": [
            {
                "id": 1,
                "title": "Annual Conference 2024",
                "summary": "Join us for our annual conference.",
                "event_type_id": 1,
                "is_public": True,
                "start_date": "2024-06-15 09:00:00",
                "end_date": "2024-06-15 17:00:00",
                "is_active": True,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_event_create_response() -> dict[str, Any]:
    """Sample event create response."""
    return {
        "values": [
            {
                "id": 100,
                "title": "New Workshop",
                "event_type_id": 3,
                "is_public": True,
                "start_date": "2024-03-01 10:00:00",
                "end_date": "2024-03-01 12:00:00",
                "is_active": True,
                "is_template": False,
                "created_date": "2024-01-20 08:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Participant Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_participant_response() -> dict[str, Any]:
    """Sample participant list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "event_id": 1,
                "status_id": 1,
                "role_id": 1,
                "register_date": "2024-01-05 10:00:00",
                "source": "Online registration",
                "fee_level": "Early Bird",
                "fee_amount": 75.00,
                "fee_currency": "USD",
                "is_test": False,
                "is_pay_later": False,
                "must_wait": False,
                "created_date": "2024-01-05 10:00:00",
                "modified_date": "2024-01-05 10:00:00",
            },
            {
                "id": 2,
                "contact_id": 2,
                "event_id": 1,
                "status_id": 1,
                "role_id": 2,
                "register_date": "2024-01-06 14:30:00",
                "source": "Admin entry",
                "fee_level": "Regular",
                "fee_amount": 100.00,
                "fee_currency": "USD",
                "is_test": False,
                "is_pay_later": False,
                "must_wait": False,
                "created_date": "2024-01-06 14:30:00",
                "modified_date": "2024-01-06 14:30:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_participant() -> dict[str, Any]:
    """Sample single participant response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "event_id": 1,
                "status_id": 1,
                "role_id": 1,
                "register_date": "2024-01-05 10:00:00",
                "fee_amount": 75.00,
                "fee_currency": "USD",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_participant_create_response() -> dict[str, Any]:
    """Sample participant create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 5,
                "event_id": 1,
                "status_id": 1,
                "role_id": 1,
                "register_date": "2024-01-20 11:00:00",
                "fee_amount": 100.00,
                "fee_currency": "USD",
                "created_date": "2024-01-20 11:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Membership Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_membership_response() -> dict[str, Any]:
    """Sample membership list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "membership_type_id": 1,
                "join_date": "2023-01-01",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "source": "Online signup",
                "status_id": 2,
                "is_override": False,
                "is_test": False,
                "is_pay_later": False,
                "created_date": "2023-01-01 10:00:00",
                "modified_date": "2024-01-01 00:00:00",
            },
            {
                "id": 2,
                "contact_id": 2,
                "membership_type_id": 2,
                "join_date": "2024-01-15",
                "start_date": "2024-01-15",
                "end_date": "2025-01-14",
                "source": "Admin entry",
                "status_id": 1,
                "is_override": False,
                "is_test": False,
                "is_pay_later": False,
                "created_date": "2024-01-15 09:00:00",
                "modified_date": "2024-01-15 09:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_membership() -> dict[str, Any]:
    """Sample single membership response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "membership_type_id": 1,
                "join_date": "2023-01-01",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "status_id": 2,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_membership_create_response() -> dict[str, Any]:
    """Sample membership create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 10,
                "membership_type_id": 1,
                "join_date": "2024-01-20",
                "start_date": "2024-01-20",
                "end_date": "2025-01-19",
                "status_id": 1,
                "created_date": "2024-01-20 10:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Group Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_group_response() -> dict[str, Any]:
    """Sample group list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "name": "newsletter_subscribers",
                "title": "Newsletter Subscribers",
                "description": "Contacts subscribed to our newsletter.",
                "is_active": True,
                "visibility": "User and User Admin",
                "group_type": ["2"],
                "is_hidden": False,
                "is_reserved": False,
                "created_id": 1,
                "created_date": "2023-06-01 10:00:00",
                "modified_date": "2024-01-10 15:00:00",
            },
            {
                "id": 2,
                "name": "volunteers",
                "title": "Volunteers",
                "description": "Active volunteers.",
                "is_active": True,
                "visibility": "User and User Admin",
                "group_type": ["1"],
                "is_hidden": False,
                "is_reserved": False,
                "created_id": 1,
                "created_date": "2023-08-15 09:00:00",
                "modified_date": "2023-12-01 11:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_group() -> dict[str, Any]:
    """Sample single group response."""
    return {
        "values": [
            {
                "id": 1,
                "name": "newsletter_subscribers",
                "title": "Newsletter Subscribers",
                "description": "Contacts subscribed to our newsletter.",
                "is_active": True,
                "visibility": "User and User Admin",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_group_create_response() -> dict[str, Any]:
    """Sample group create response."""
    return {
        "values": [
            {
                "id": 100,
                "name": "new_group",
                "title": "New Group",
                "description": "A newly created group.",
                "is_active": True,
                "visibility": "User and User Admin",
                "created_id": 1,
                "created_date": "2024-01-20 10:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Tag Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_tag_response() -> dict[str, Any]:
    """Sample tag list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "name": "Major Donor",
                "description": "Contacts who have made significant contributions.",
                "is_selectable": True,
                "is_reserved": False,
                "is_tagset": False,
                "used_for": ["civicrm_contact"],
                "color": "#FF5733",
                "created_id": 1,
                "created_date": "2023-01-01 10:00:00",
                "modified_date": "2023-01-01 10:00:00",
            },
            {
                "id": 2,
                "name": "Board Member",
                "description": "Current board members.",
                "is_selectable": True,
                "is_reserved": False,
                "is_tagset": False,
                "used_for": ["civicrm_contact"],
                "color": "#3498DB",
                "created_id": 1,
                "created_date": "2023-02-15 14:00:00",
                "modified_date": "2023-02-15 14:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_tag() -> dict[str, Any]:
    """Sample single tag response."""
    return {
        "values": [
            {
                "id": 1,
                "name": "Major Donor",
                "description": "Contacts who have made significant contributions.",
                "is_selectable": True,
                "color": "#FF5733",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_tag_create_response() -> dict[str, Any]:
    """Sample tag create response."""
    return {
        "values": [
            {
                "id": 100,
                "name": "New Tag",
                "description": "A newly created tag.",
                "is_selectable": True,
                "is_reserved": False,
                "is_tagset": False,
                "color": "#27AE60",
                "created_id": 1,
                "created_date": "2024-01-20 10:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Address Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_address_response() -> dict[str, Any]:
    """Sample address list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "is_primary": True,
                "is_billing": True,
                "street_address": "123 Main Street",
                "street_number": 123,
                "street_name": "Main",
                "street_type": "Street",
                "city": "Anytown",
                "state_province_id": 1042,
                "postal_code": "12345",
                "country_id": 1228,
                "geo_code_1": 40.7128,
                "geo_code_2": -74.0060,
                "timezone": "America/New_York",
                "created_date": "2023-06-01 10:00:00",
                "modified_date": "2023-06-01 10:00:00",
            },
            {
                "id": 2,
                "contact_id": 1,
                "location_type_id": 2,
                "is_primary": False,
                "is_billing": False,
                "street_address": "456 Office Park",
                "supplemental_address_1": "Suite 200",
                "city": "Business City",
                "state_province_id": 1042,
                "postal_code": "54321",
                "country_id": 1228,
                "created_date": "2023-07-15 14:00:00",
                "modified_date": "2023-07-15 14:00:00",
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_address() -> dict[str, Any]:
    """Sample single address response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "is_primary": True,
                "street_address": "123 Main Street",
                "city": "Anytown",
                "state_province_id": 1042,
                "postal_code": "12345",
                "country_id": 1228,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_address_create_response() -> dict[str, Any]:
    """Sample address create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 5,
                "location_type_id": 1,
                "is_primary": True,
                "street_address": "789 New Avenue",
                "city": "New City",
                "state_province_id": 1042,
                "postal_code": "67890",
                "country_id": 1228,
                "created_date": "2024-01-20 10:00:00",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Email Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_email_response() -> dict[str, Any]:
    """Sample email list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "email": "john@example.com",
                "is_primary": True,
                "is_billing": True,
                "is_bulkmail": True,
                "on_hold": 0,
            },
            {
                "id": 2,
                "contact_id": 1,
                "location_type_id": 2,
                "email": "john.work@company.com",
                "is_primary": False,
                "is_billing": False,
                "is_bulkmail": False,
                "on_hold": 0,
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_email() -> dict[str, Any]:
    """Sample single email response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "email": "john@example.com",
                "is_primary": True,
                "on_hold": 0,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_email_create_response() -> dict[str, Any]:
    """Sample email create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 5,
                "location_type_id": 1,
                "email": "newemail@example.com",
                "is_primary": True,
                "on_hold": 0,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Phone Entity Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_phone_response() -> dict[str, Any]:
    """Sample phone list response from CiviCRM API."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "phone": "(555) 123-4567",
                "phone_numeric": "5551234567",
                "phone_type_id": 1,
                "is_primary": True,
                "is_billing": False,
            },
            {
                "id": 2,
                "contact_id": 1,
                "location_type_id": 1,
                "phone": "(555) 987-6543",
                "phone_numeric": "5559876543",
                "phone_type_id": 2,
                "is_primary": False,
                "is_billing": False,
            },
        ],
        "count": 2,
        "countFetched": 2,
    }


@pytest.fixture
def sample_single_phone() -> dict[str, Any]:
    """Sample single phone response."""
    return {
        "values": [
            {
                "id": 1,
                "contact_id": 1,
                "location_type_id": 1,
                "phone": "(555) 123-4567",
                "phone_type_id": 1,
                "is_primary": True,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_phone_create_response() -> dict[str, Any]:
    """Sample phone create response."""
    return {
        "values": [
            {
                "id": 100,
                "contact_id": 5,
                "location_type_id": 1,
                "phone": "(555) 000-0000",
                "phone_numeric": "5550000000",
                "phone_type_id": 1,
                "is_primary": True,
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


# -----------------------------------------------------------------------------
# Error Response Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_error_response() -> dict[str, Any]:
    """Sample generic API error response."""
    return {
        "error_code": "api_error",
        "error_message": "An unexpected error occurred while processing your request.",
    }


@pytest.fixture
def sample_empty_response() -> dict[str, Any]:
    """Sample empty values list response."""
    return {
        "values": [],
        "count": 0,
        "countFetched": 0,
    }


@pytest.fixture
def sample_not_found_response() -> dict[str, Any]:
    """Sample not found error response (404-style)."""
    return {
        "error_code": "not_found",
        "error_message": "Entity not found: No Contact with id = 999 exists.",
    }


@pytest.fixture
def sample_validation_error_response() -> dict[str, Any]:
    """Sample validation error response."""
    return {
        "error_code": "validation_error",
        "error_message": "Validation failed for field 'email': Invalid email format.",
    }


@pytest.fixture
def sample_auth_error_response() -> dict[str, Any]:
    """Sample authentication error response."""
    return {
        "error_code": "unauthorized",
        "error_message": "API key is invalid or expired. Please check your credentials.",
    }


# -----------------------------------------------------------------------------
# Composite / Complex Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sample_contact_with_related() -> dict[str, Any]:
    """Sample contact response with related entities (addresses, emails, phones)."""
    return {
        "values": [
            {
                "id": 1,
                "display_name": "John Doe",
                "first_name": "John",
                "last_name": "Doe",
                "contact_type": "Individual",
                "is_deleted": False,
                "email_primary.email": "john@example.com",
                "address_primary.street_address": "123 Main Street",
                "address_primary.city": "Anytown",
                "address_primary.postal_code": "12345",
                "phone_primary.phone": "(555) 123-4567",
            },
        ],
        "count": 1,
        "countFetched": 1,
    }


@pytest.fixture
def sample_paginated_response() -> dict[str, Any]:
    """Sample paginated response with more results available."""
    return {
        "values": [
            {"id": 1, "display_name": "Contact 1"},
            {"id": 2, "display_name": "Contact 2"},
            {"id": 3, "display_name": "Contact 3"},
            {"id": 4, "display_name": "Contact 4"},
            {"id": 5, "display_name": "Contact 5"},
        ],
        "count": 100,
        "countFetched": 5,
    }


@pytest.fixture
def sample_batch_create_response() -> dict[str, Any]:
    """Sample batch create response with multiple records."""
    return {
        "values": [
            {"id": 100, "display_name": "New Contact 1"},
            {"id": 101, "display_name": "New Contact 2"},
            {"id": 102, "display_name": "New Contact 3"},
        ],
        "count": 3,
        "countFetched": 3,
    }


# -----------------------------------------------------------------------------
# Database Testing Fixtures (requires pytest-databases)
# -----------------------------------------------------------------------------


@pytest.fixture
def postgres_url(postgres_service: PostgresService) -> str:
    """Get PostgreSQL connection URL from the Docker service fixture.

    This fixture provides a connection URL to a PostgreSQL database running
    in a Docker container, managed by pytest-databases.

    Args:
        postgres_service: The pytest-databases PostgreSQL service fixture.

    Returns:
        A PostgreSQL connection URL string.

    Note:
        This fixture is only available when pytest-databases is installed
        and Docker is running. Tests using this fixture should be marked
        with @pytest.mark.db.
    """
    return (
        f"postgresql://{postgres_service.user}:{postgres_service.password}@"
        f"{postgres_service.host}:{postgres_service.port}/{postgres_service.database}"
    )


@pytest.fixture
def postgres_async_url(postgres_service: PostgresService) -> str:
    """Get async PostgreSQL connection URL from the Docker service fixture.

    This fixture provides an async-compatible connection URL (using asyncpg)
    to a PostgreSQL database running in a Docker container.

    Args:
        postgres_service: The pytest-databases PostgreSQL service fixture.

    Returns:
        An async PostgreSQL connection URL string (postgresql+asyncpg://).

    Note:
        This fixture is only available when pytest-databases is installed
        and Docker is running. Tests using this fixture should be marked
        with @pytest.mark.db.
    """
    return (
        f"postgresql+asyncpg://{postgres_service.user}:{postgres_service.password}@"
        f"{postgres_service.host}:{postgres_service.port}/{postgres_service.database}"
    )


def databases_available() -> bool:
    """Check if pytest-databases is available for import.

    Returns:
        True if pytest-databases is installed and can be imported.
    """
    return DATABASES_AVAILABLE


def postgres_available() -> bool:
    """Check if PostgreSQL fixtures are available.

    Returns:
        True if pytest-databases[postgres] is installed.
    """
    return POSTGRES_AVAILABLE


def mysql_available() -> bool:
    """Check if MySQL fixtures are available.

    Returns:
        True if pytest-databases[mysql] is installed.

    Note:
        Currently always returns False due to mysql-connector-python
        not supporting Python 3.13+.
    """
    return MYSQL_AVAILABLE


# Convenience markers for skipping tests when databases are unavailable
skip_without_databases = pytest.mark.skipif(
    not DATABASES_AVAILABLE,
    reason="pytest-databases not installed or Docker not available",
)

skip_without_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="pytest-databases[postgres] not installed or Docker not available",
)

skip_without_mysql = pytest.mark.skipif(
    not MYSQL_AVAILABLE,
    reason="pytest-databases[mysql] not installed (Python 3.13+ not supported)",
)
