#!/usr/bin/env python3
"""Record CiviCRM API cassettes for testing.

This script connects to a live CiviCRM instance and records HTTP interactions
for use in cassette-based testing. It requires a running CiviCRM instance
(e.g., via `make infra`).

Usage:
    # Record all cassettes
    python scripts/record_cassettes.py

    # Record specific entity cassettes
    python scripts/record_cassettes.py --entity Contact

    # Record with specific CiviCRM version tag
    python scripts/record_cassettes.py --version 5.74

    # Record only error cassettes
    python scripts/record_cassettes.py --errors-only

    # Record edge case cassettes
    python scripts/record_cassettes.py --edge-cases

Environment variables:
    CIVI_BASE_URL: CiviCRM API base URL (default: http://localhost:8080/civicrm/ajax/api4)
    CIVI_API_KEY: API key for authentication
    CIVI_VERSION: CiviCRM version for cassette organization (default: "default")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from civicrm_py.core.client import CiviClient
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.exceptions import CiviAPIError, CiviAuthError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class RecordingResult:
    """Result of a single cassette recording."""

    name: str
    success: bool
    interactions_count: int = 0
    error: str | None = None
    path: Path | None = None


@dataclass
class RecordingSession:
    """Tracks overall recording session status."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    results: list[RecordingResult] = field(default_factory=list)
    civicrm_version: str = "unknown"
    civicrm_revision: str = "unknown"

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)


class CassetteRecorder:
    """Records HTTP interactions to cassette files.

    This recorder makes actual API calls and saves the request/response
    pairs for later replay in tests.
    """

    # Headers to redact from cassettes
    REDACT_HEADERS = [
        "Authorization",
        "X-Civi-Api-Key",
        "X-Civi-Site-Key",
        "X-Civi-Key",
        "Cookie",
        "Set-Cookie",
    ]

    def __init__(
        self,
        client: CiviClient,
        cassette_dir: Path,
        version: str = "default",
    ) -> None:
        """Initialize the recorder.

        Args:
            client: CiviClient instance for making API calls.
            cassette_dir: Base directory for cassette storage.
            version: CiviCRM version for subdirectory organization.
        """
        self.client = client
        self.cassette_dir = Path(cassette_dir)
        self.version = version
        self.entities_dir = self.cassette_dir / f"v{version.lstrip('v')}" / "entities"
        self.errors_dir = self.cassette_dir / f"v{version.lstrip('v')}" / "errors"
        self.edge_cases_dir = self.cassette_dir / f"v{version.lstrip('v')}" / "edge_cases"
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for direct requests."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                verify=self.client.settings.verify_ssl,
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Redact sensitive header values."""
        result = dict(headers)
        for header in self.REDACT_HEADERS:
            for key in list(result.keys()):
                if key.lower() == header.lower():
                    result[key] = "[REDACTED]"
        return result

    async def _make_request(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], int, dict[str, str]]:
        """Make raw HTTP request and capture details.

        Returns:
            Tuple of (request_body, response_body, status_code, response_headers)
        """
        settings = self.client.settings
        url = f"{settings.base_url.rstrip('/')}/{entity}/{action}"

        # Build headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Add auth
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        if settings.site_key:
            headers["X-Civi-Key"] = settings.site_key

        # Build form data
        form_data = {"params": json.dumps(params or {})}

        # Make request
        http_client = await self._get_http_client()
        response = await http_client.post(url, data=form_data, headers=headers)

        # Parse response
        try:
            response_body = response.json()
        except json.JSONDecodeError:
            response_body = {"raw": response.text}

        return (
            {"params": json.dumps(params or {})},
            response_body,
            response.status_code,
            dict(response.headers),
        )

    def _build_cassette(
        self,
        name: str,
        entity: str,
        action: str,
        request_body: dict[str, Any],
        response_body: dict[str, Any],
        status_code: int,
        response_headers: dict[str, str],
        description: str = "",
    ) -> dict[str, Any]:
        """Build cassette data structure."""
        settings = self.client.settings
        url = f"{settings.base_url.rstrip('/')}/{entity}/{action}"
        recorded_at = datetime.now(UTC).isoformat()

        return {
            "name": name,
            "version": self.version,
            "metadata": {
                "civicrm_version": self.version,
                "recorded_at": recorded_at,
                "description": description,
                "entity": entity,
                "action": action,
            },
            "interactions": [
                {
                    "request": {
                        "method": "POST",
                        "url": url,
                        "headers": self._redact_headers(
                            {
                                "Accept": "application/json",
                                "Authorization": "[REDACTED]",
                                "Content-Type": "application/x-www-form-urlencoded",
                                "X-Civi-Key": "[REDACTED]",
                                "X-Requested-With": "XMLHttpRequest",
                            }
                        ),
                        "body": request_body,
                    },
                    "response": {
                        "status_code": status_code,
                        "headers": {
                            k: v
                            for k, v in response_headers.items()
                            if k.lower() in ("content-type", "x-civicrm-version")
                        },
                        "body": response_body,
                    },
                    "recorded_at": recorded_at,
                }
            ],
        }

    def _save_cassette(self, cassette: dict[str, Any], directory: Path) -> Path:
        """Save cassette to file."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{cassette['name']}.json"

        with path.open("w") as f:
            json.dump(cassette, f, indent=2, sort_keys=True)

        return path

    async def record_entity_action(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        description: str = "",
    ) -> RecordingResult:
        """Record a single entity action.

        Args:
            entity: CiviCRM entity name.
            action: API action name.
            params: Request parameters.
            description: Human-readable description.

        Returns:
            RecordingResult with success/failure status.
        """
        name = f"{entity}_{action}"
        logger.info("Recording %s...", name)

        try:
            req_body, resp_body, status, resp_headers = await self._make_request(entity, action, params)

            cassette = self._build_cassette(
                name=name,
                entity=entity,
                action=action,
                request_body=req_body,
                response_body=resp_body,
                status_code=status,
                response_headers=resp_headers,
                description=description,
            )

            path = self._save_cassette(cassette, self.entities_dir)

            return RecordingResult(
                name=name,
                success=True,
                interactions_count=1,
                path=path,
            )

        except Exception as e:
            logger.error("Failed to record %s: %s", name, e)
            return RecordingResult(
                name=name,
                success=False,
                error=str(e),
            )

    async def record_error_scenario(
        self,
        name: str,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        description: str = "",
    ) -> RecordingResult:
        """Record an error scenario cassette."""
        logger.info("Recording error scenario: %s...", name)

        try:
            req_body, resp_body, status, resp_headers = await self._make_request(entity, action, params)

            cassette = self._build_cassette(
                name=name,
                entity=entity,
                action=action,
                request_body=req_body,
                response_body=resp_body,
                status_code=status,
                response_headers=resp_headers,
                description=description,
            )

            path = self._save_cassette(cassette, self.errors_dir)

            return RecordingResult(
                name=name,
                success=True,
                interactions_count=1,
                path=path,
            )

        except Exception as e:
            logger.error("Failed to record error scenario %s: %s", name, e)
            return RecordingResult(
                name=name,
                success=False,
                error=str(e),
            )

    async def record_edge_case(
        self,
        name: str,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        description: str = "",
    ) -> RecordingResult:
        """Record an edge case cassette."""
        logger.info("Recording edge case: %s...", name)

        try:
            req_body, resp_body, status, resp_headers = await self._make_request(entity, action, params)

            cassette = self._build_cassette(
                name=name,
                entity=entity,
                action=action,
                request_body=req_body,
                response_body=resp_body,
                status_code=status,
                response_headers=resp_headers,
                description=description,
            )

            path = self._save_cassette(cassette, self.edge_cases_dir)

            return RecordingResult(
                name=name,
                success=True,
                interactions_count=1,
                path=path,
            )

        except Exception as e:
            logger.error("Failed to record edge case %s: %s", name, e)
            return RecordingResult(
                name=name,
                success=False,
                error=str(e),
            )


async def get_civicrm_version(client: CiviClient) -> tuple[str, str]:
    """Get CiviCRM version info from the API.

    Returns:
        Tuple of (version, revision).
    """
    try:
        response = await client.request("System", "get", {"select": ["version", "revision"]})
        if response.values:
            info = response.values[0]
            return info.get("version", "unknown"), info.get("revision", "unknown")
    except Exception as e:
        logger.warning("Could not get CiviCRM version: %s", e)
    return "unknown", "unknown"


async def record_contact_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Contact entity cassettes."""
    logger.info("=== Recording Contact Entity Cassettes ===")

    # Contact.get - basic query
    result = await recorder.record_entity_action(
        "Contact",
        "get",
        params={"select": ["id", "display_name", "contact_type"], "limit": 10},
        description="Basic Contact get with select and limit",
    )
    session.results.append(result)

    # Contact.get - with filters
    result = await recorder.record_entity_action(
        "Contact",
        "get",
        params={
            "select": ["id", "display_name", "first_name", "last_name", "email_primary.email"],
            "where": [["contact_type", "=", "Individual"]],
            "limit": 5,
        },
        description="Contact get with type filter and email join",
    )
    session.results.append(
        RecordingResult(
            name="Contact_get_filtered",
            success=result.success,
            interactions_count=result.interactions_count,
            error=result.error,
            path=result.path,
        )
    )

    # Contact.getFields - schema metadata
    result = await recorder.record_entity_action(
        "Contact",
        "getFields",
        params={"loadOptions": True},
        description="Contact field metadata with options",
    )
    session.results.append(result)

    # Contact.getActions - available actions
    result = await recorder.record_entity_action(
        "Contact",
        "getActions",
        params={},
        description="Available Contact actions",
    )
    session.results.append(result)

    # Contact.create - create new contact
    result = await recorder.record_entity_action(
        "Contact",
        "create",
        params={
            "values": {
                "contact_type": "Individual",
                "first_name": "Test",
                "last_name": "Recording",
                "email_primary.email": "test.recording@example.com",
            }
        },
        description="Create new Individual contact",
    )
    session.results.append(result)

    # Extract created contact ID for update/delete
    created_id = None
    if result.success and result.path:
        with result.path.open() as f:
            cassette = json.load(f)
            resp_body = cassette["interactions"][0]["response"]["body"]
            if resp_body.get("values"):
                created_id = resp_body["values"][0].get("id")

    # Contact.update - update existing contact
    if created_id:
        result = await recorder.record_entity_action(
            "Contact",
            "update",
            params={
                "values": {"nick_name": "TestNick"},
                "where": [["id", "=", created_id]],
            },
            description="Update contact nick_name",
        )
        session.results.append(result)

        # Contact.save - upsert operation
        result = await recorder.record_entity_action(
            "Contact",
            "save",
            params={
                "records": [
                    {"id": created_id, "job_title": "Test Engineer"},
                ],
            },
            description="Save (upsert) contact record",
        )
        session.results.append(result)

        # Contact.delete - delete contact
        result = await recorder.record_entity_action(
            "Contact",
            "delete",
            params={"where": [["id", "=", created_id]]},
            description="Delete contact by ID",
        )
        session.results.append(result)
    else:
        logger.warning("Skipping update/save/delete - no contact ID from create")


async def record_activity_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Activity entity cassettes."""
    logger.info("=== Recording Activity Entity Cassettes ===")

    # Activity.get
    result = await recorder.record_entity_action(
        "Activity",
        "get",
        params={
            "select": ["id", "activity_type_id", "subject", "status_id", "activity_date_time"],
            "limit": 10,
        },
        description="Basic Activity get",
    )
    session.results.append(result)

    # Activity.getFields
    result = await recorder.record_entity_action(
        "Activity",
        "getFields",
        params={"loadOptions": True},
        description="Activity field metadata",
    )
    session.results.append(result)

    # Activity.getActions
    result = await recorder.record_entity_action(
        "Activity",
        "getActions",
        params={},
        description="Available Activity actions",
    )
    session.results.append(result)

    # Activity.create
    result = await recorder.record_entity_action(
        "Activity",
        "create",
        params={
            "values": {
                "activity_type_id": 1,  # Meeting
                "subject": "Test Activity Recording",
                "activity_date_time": datetime.now(UTC).isoformat(),
                "status_id": 1,  # Scheduled
                "source_contact_id": 1,
            }
        },
        description="Create new Activity",
    )
    session.results.append(result)

    # Extract created activity ID
    created_id = None
    if result.success and result.path:
        with result.path.open() as f:
            cassette = json.load(f)
            resp_body = cassette["interactions"][0]["response"]["body"]
            if resp_body.get("values"):
                created_id = resp_body["values"][0].get("id")

    if created_id:
        # Activity.update
        result = await recorder.record_entity_action(
            "Activity",
            "update",
            params={
                "values": {"subject": "Updated Activity Subject"},
                "where": [["id", "=", created_id]],
            },
            description="Update Activity subject",
        )
        session.results.append(result)

        # Activity.delete
        result = await recorder.record_entity_action(
            "Activity",
            "delete",
            params={"where": [["id", "=", created_id]]},
            description="Delete Activity",
        )
        session.results.append(result)


async def record_contribution_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Contribution entity cassettes."""
    logger.info("=== Recording Contribution Entity Cassettes ===")

    # Contribution.get
    result = await recorder.record_entity_action(
        "Contribution",
        "get",
        params={
            "select": [
                "id",
                "contact_id",
                "financial_type_id",
                "total_amount",
                "receive_date",
                "contribution_status_id",
            ],
            "limit": 10,
        },
        description="Basic Contribution get",
    )
    session.results.append(result)

    # Contribution.getFields
    result = await recorder.record_entity_action(
        "Contribution",
        "getFields",
        params={"loadOptions": True},
        description="Contribution field metadata",
    )
    session.results.append(result)

    # Contribution.getActions
    result = await recorder.record_entity_action(
        "Contribution",
        "getActions",
        params={},
        description="Available Contribution actions",
    )
    session.results.append(result)

    # Contribution.create
    result = await recorder.record_entity_action(
        "Contribution",
        "create",
        params={
            "values": {
                "contact_id": 1,
                "financial_type_id": 1,  # Donation
                "total_amount": 100.00,
                "receive_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "contribution_status_id": 1,  # Completed
            }
        },
        description="Create new Contribution",
    )
    session.results.append(result)

    # Extract created ID
    created_id = None
    if result.success and result.path:
        with result.path.open() as f:
            cassette = json.load(f)
            resp_body = cassette["interactions"][0]["response"]["body"]
            if resp_body.get("values"):
                created_id = resp_body["values"][0].get("id")

    if created_id:
        # Contribution.update
        result = await recorder.record_entity_action(
            "Contribution",
            "update",
            params={
                "values": {"invoice_number": "TEST-001"},
                "where": [["id", "=", created_id]],
            },
            description="Update Contribution invoice number",
        )
        session.results.append(result)

        # Contribution.delete
        result = await recorder.record_entity_action(
            "Contribution",
            "delete",
            params={"where": [["id", "=", created_id]]},
            description="Delete Contribution",
        )
        session.results.append(result)


async def record_event_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Event entity cassettes."""
    logger.info("=== Recording Event Entity Cassettes ===")

    # Event.get
    result = await recorder.record_entity_action(
        "Event",
        "get",
        params={
            "select": ["id", "title", "event_type_id", "start_date", "end_date", "is_active"],
            "limit": 10,
        },
        description="Basic Event get",
    )
    session.results.append(result)

    # Event.getFields
    result = await recorder.record_entity_action(
        "Event",
        "getFields",
        params={"loadOptions": True},
        description="Event field metadata",
    )
    session.results.append(result)

    # Event.create
    result = await recorder.record_entity_action(
        "Event",
        "create",
        params={
            "values": {
                "title": "Test Event Recording",
                "event_type_id": 1,  # Conference
                "start_date": datetime.now(UTC).strftime("%Y-%m-%d 09:00:00"),
                "end_date": datetime.now(UTC).strftime("%Y-%m-%d 17:00:00"),
                "is_active": True,
            }
        },
        description="Create new Event",
    )
    session.results.append(result)

    created_id = None
    if result.success and result.path:
        with result.path.open() as f:
            cassette = json.load(f)
            resp_body = cassette["interactions"][0]["response"]["body"]
            if resp_body.get("values"):
                created_id = resp_body["values"][0].get("id")

    if created_id:
        result = await recorder.record_entity_action(
            "Event",
            "update",
            params={
                "values": {"description": "Test event description"},
                "where": [["id", "=", created_id]],
            },
            description="Update Event",
        )
        session.results.append(result)

        result = await recorder.record_entity_action(
            "Event",
            "delete",
            params={"where": [["id", "=", created_id]]},
            description="Delete Event",
        )
        session.results.append(result)


async def record_participant_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Participant entity cassettes."""
    logger.info("=== Recording Participant Entity Cassettes ===")

    # Participant.get
    result = await recorder.record_entity_action(
        "Participant",
        "get",
        params={
            "select": ["id", "contact_id", "event_id", "status_id", "role_id", "register_date"],
            "limit": 10,
        },
        description="Basic Participant get",
    )
    session.results.append(result)

    # Participant.getFields
    result = await recorder.record_entity_action(
        "Participant",
        "getFields",
        params={"loadOptions": True},
        description="Participant field metadata",
    )
    session.results.append(result)


async def record_membership_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record Membership entity cassettes."""
    logger.info("=== Recording Membership Entity Cassettes ===")

    # Membership.get
    result = await recorder.record_entity_action(
        "Membership",
        "get",
        params={
            "select": [
                "id",
                "contact_id",
                "membership_type_id",
                "status_id",
                "start_date",
                "end_date",
            ],
            "limit": 10,
        },
        description="Basic Membership get",
    )
    session.results.append(result)

    # Membership.getFields
    result = await recorder.record_entity_action(
        "Membership",
        "getFields",
        params={"loadOptions": True},
        description="Membership field metadata",
    )
    session.results.append(result)


async def record_supporting_entity_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record supporting entity cassettes (Group, Tag, Note, Address, Email, Phone)."""
    logger.info("=== Recording Supporting Entity Cassettes ===")

    # Group
    result = await recorder.record_entity_action(
        "Group",
        "get",
        params={"select": ["id", "title", "group_type", "is_active"], "limit": 10},
        description="Basic Group get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Group",
        "getFields",
        params={"loadOptions": True},
        description="Group field metadata",
    )
    session.results.append(result)

    # Tag
    result = await recorder.record_entity_action(
        "Tag",
        "get",
        params={"select": ["id", "name", "description", "is_selectable"], "limit": 10},
        description="Basic Tag get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Tag",
        "getFields",
        params={"loadOptions": True},
        description="Tag field metadata",
    )
    session.results.append(result)

    # Note
    result = await recorder.record_entity_action(
        "Note",
        "get",
        params={"select": ["id", "entity_table", "entity_id", "note", "subject"], "limit": 10},
        description="Basic Note get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Note",
        "getFields",
        params={"loadOptions": True},
        description="Note field metadata",
    )
    session.results.append(result)

    # Address
    result = await recorder.record_entity_action(
        "Address",
        "get",
        params={
            "select": [
                "id",
                "contact_id",
                "street_address",
                "city",
                "state_province_id",
                "postal_code",
                "country_id",
            ],
            "limit": 10,
        },
        description="Basic Address get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Address",
        "getFields",
        params={"loadOptions": True},
        description="Address field metadata",
    )
    session.results.append(result)

    # Email
    result = await recorder.record_entity_action(
        "Email",
        "get",
        params={
            "select": ["id", "contact_id", "email", "location_type_id", "is_primary"],
            "limit": 10,
        },
        description="Basic Email get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Email",
        "getFields",
        params={"loadOptions": True},
        description="Email field metadata",
    )
    session.results.append(result)

    # Phone
    result = await recorder.record_entity_action(
        "Phone",
        "get",
        params={
            "select": ["id", "contact_id", "phone", "phone_type_id", "location_type_id"],
            "limit": 10,
        },
        description="Basic Phone get",
    )
    session.results.append(result)

    result = await recorder.record_entity_action(
        "Phone",
        "getFields",
        params={"loadOptions": True},
        description="Phone field metadata",
    )
    session.results.append(result)


async def record_error_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record error response cassettes."""
    logger.info("=== Recording Error Response Cassettes ===")

    # 404 - Entity not found
    result = await recorder.record_error_scenario(
        "error_404_entity_not_found",
        "Contact",
        "get",
        params={"where": [["id", "=", 999999999]]},
        description="Query for non-existent entity (empty result)",
    )
    session.results.append(result)

    # Invalid entity name
    result = await recorder.record_error_scenario(
        "error_invalid_entity",
        "NonExistentEntity",
        "get",
        params={},
        description="Request to non-existent entity type",
    )
    session.results.append(result)

    # Invalid action
    result = await recorder.record_error_scenario(
        "error_invalid_action",
        "Contact",
        "nonExistentAction",
        params={},
        description="Request with invalid action name",
    )
    session.results.append(result)

    # Invalid field in select
    result = await recorder.record_error_scenario(
        "error_invalid_field",
        "Contact",
        "get",
        params={"select": ["nonexistent_field_xyz"]},
        description="Query with invalid field name",
    )
    session.results.append(result)

    # Invalid where clause
    result = await recorder.record_error_scenario(
        "error_invalid_where",
        "Contact",
        "get",
        params={"where": [["invalid_field", "=", "value"]]},
        description="Query with invalid where clause field",
    )
    session.results.append(result)

    # Create with missing required field
    result = await recorder.record_error_scenario(
        "error_missing_required_field",
        "Contact",
        "create",
        params={"values": {}},  # Missing contact_type
        description="Create entity with missing required field",
    )
    session.results.append(result)

    # Update non-existent record
    result = await recorder.record_error_scenario(
        "error_update_nonexistent",
        "Contact",
        "update",
        params={
            "values": {"first_name": "Test"},
            "where": [["id", "=", 999999999]],
        },
        description="Update non-existent record",
    )
    session.results.append(result)

    # Delete non-existent record
    result = await recorder.record_error_scenario(
        "error_delete_nonexistent",
        "Contact",
        "delete",
        params={"where": [["id", "=", 999999999]]},
        description="Delete non-existent record",
    )
    session.results.append(result)

    # Invalid operator in where
    result = await recorder.record_error_scenario(
        "error_invalid_operator",
        "Contact",
        "get",
        params={"where": [["id", "INVALID_OP", 1]]},
        description="Query with invalid comparison operator",
    )
    session.results.append(result)


async def record_edge_case_cassettes(recorder: CassetteRecorder, session: RecordingSession) -> None:
    """Record edge case cassettes."""
    logger.info("=== Recording Edge Case Cassettes ===")

    # Empty result set
    result = await recorder.record_edge_case(
        "empty_result",
        "Contact",
        "get",
        params={
            "where": [
                ["first_name", "=", "NonExistentName_XYZ_12345"],
                ["last_name", "=", "NonExistentName_XYZ_12345"],
            ]
        },
        description="Query returning empty result set",
    )
    session.results.append(result)

    # Pagination - first page
    result = await recorder.record_edge_case(
        "pagination_first_page",
        "Contact",
        "get",
        params={"select": ["id", "display_name"], "limit": 5, "offset": 0},
        description="Paginated query - first page",
    )
    session.results.append(result)

    # Pagination - second page
    result = await recorder.record_edge_case(
        "pagination_second_page",
        "Contact",
        "get",
        params={"select": ["id", "display_name"], "limit": 5, "offset": 5},
        description="Paginated query - second page",
    )
    session.results.append(result)

    # Pagination - beyond data
    result = await recorder.record_edge_case(
        "pagination_beyond_data",
        "Contact",
        "get",
        params={"select": ["id", "display_name"], "limit": 100, "offset": 999999},
        description="Paginated query - offset beyond data",
    )
    session.results.append(result)

    # Large select (many fields)
    result = await recorder.record_edge_case(
        "large_select",
        "Contact",
        "get",
        params={
            "select": [
                "id",
                "display_name",
                "contact_type",
                "first_name",
                "last_name",
                "middle_name",
                "prefix_id",
                "suffix_id",
                "nick_name",
                "sort_name",
                "birth_date",
                "gender_id",
                "job_title",
                "organization_name",
                "legal_name",
                "sic_code",
                "is_deceased",
                "deceased_date",
                "do_not_email",
                "do_not_phone",
                "do_not_mail",
                "do_not_sms",
                "do_not_trade",
                "is_opt_out",
                "legal_identifier",
                "external_identifier",
                "preferred_communication_method",
                "preferred_language",
                "created_date",
                "modified_date",
            ],
            "limit": 3,
        },
        description="Query with many selected fields",
    )
    session.results.append(result)

    # Complex where clause
    result = await recorder.record_edge_case(
        "complex_where",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name"],
            "where": [
                ["contact_type", "=", "Individual"],
                ["is_deleted", "=", False],
                ["OR", [["do_not_email", "=", False], ["do_not_phone", "=", False]]],
            ],
            "limit": 5,
        },
        description="Query with complex nested where clause",
    )
    session.results.append(result)

    # Order by multiple fields
    result = await recorder.record_edge_case(
        "order_by_multiple",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name", "sort_name"],
            "orderBy": {"sort_name": "ASC", "id": "DESC"},
            "limit": 10,
        },
        description="Query with multiple order by fields",
    )
    session.results.append(result)

    # Joins (related fields)
    result = await recorder.record_edge_case(
        "join_related_fields",
        "Contact",
        "get",
        params={
            "select": [
                "id",
                "display_name",
                "email_primary.email",
                "phone_primary.phone",
                "address_primary.city",
            ],
            "limit": 5,
        },
        description="Query with joined related fields",
    )
    session.results.append(result)

    # Limit zero (count-only equivalent)
    result = await recorder.record_edge_case(
        "limit_zero",
        "Contact",
        "get",
        params={"select": ["id"], "limit": 0},
        description="Query with limit 0 (returns count only)",
    )
    session.results.append(result)

    # Single record by ID
    result = await recorder.record_edge_case(
        "single_record_by_id",
        "Contact",
        "get",
        params={"select": ["id", "display_name"], "where": [["id", "=", 1]]},
        description="Query for single record by ID",
    )
    session.results.append(result)

    # LIKE operator
    result = await recorder.record_edge_case(
        "like_operator",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name"],
            "where": [["display_name", "LIKE", "%Test%"]],
            "limit": 5,
        },
        description="Query with LIKE operator",
    )
    session.results.append(result)

    # IN operator
    result = await recorder.record_edge_case(
        "in_operator",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name", "contact_type"],
            "where": [["contact_type", "IN", ["Individual", "Organization"]]],
            "limit": 5,
        },
        description="Query with IN operator",
    )
    session.results.append(result)

    # IS NULL operator
    result = await recorder.record_edge_case(
        "is_null_operator",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name", "nick_name"],
            "where": [["nick_name", "IS NULL"]],
            "limit": 5,
        },
        description="Query with IS NULL operator",
    )
    session.results.append(result)

    # IS NOT NULL operator
    result = await recorder.record_edge_case(
        "is_not_null_operator",
        "Contact",
        "get",
        params={
            "select": ["id", "display_name", "nick_name"],
            "where": [["nick_name", "IS NOT NULL"]],
            "limit": 5,
        },
        description="Query with IS NOT NULL operator",
    )
    session.results.append(result)


async def run_recording_session(args: argparse.Namespace) -> RecordingSession:
    """Run the cassette recording session.

    Args:
        args: Command line arguments.

    Returns:
        RecordingSession with all results.
    """
    session = RecordingSession()

    # Create client
    settings = CiviSettings(
        base_url=args.base_url,
        api_key=args.api_key,
        site_key=args.site_key,
        timeout=30,
        verify_ssl=not args.no_verify_ssl,
        debug=args.debug,
    )

    async with CiviClient(settings=settings) as client:
        # Get version info
        version, revision = await get_civicrm_version(client)
        session.civicrm_version = version
        session.civicrm_revision = revision

        # Use specified version or detected version
        cassette_version = args.version or version

        logger.info("CiviCRM Version: %s (revision: %s)", version, revision)
        logger.info("Recording cassettes for version: %s", cassette_version)

        # Create recorder
        cassette_dir = Path(args.cassette_dir)
        recorder = CassetteRecorder(
            client=client,
            cassette_dir=cassette_dir,
            version=cassette_version,
        )

        try:
            # Record based on options
            if args.errors_only:
                await record_error_cassettes(recorder, session)
            elif args.edge_cases:
                await record_edge_case_cassettes(recorder, session)
            elif args.entity:
                # Record specific entity
                entity_recorders = {
                    "Contact": record_contact_cassettes,
                    "Activity": record_activity_cassettes,
                    "Contribution": record_contribution_cassettes,
                    "Event": record_event_cassettes,
                    "Participant": record_participant_cassettes,
                    "Membership": record_membership_cassettes,
                }
                if args.entity in entity_recorders:
                    await entity_recorders[args.entity](recorder, session)
                else:
                    logger.error("Unknown entity: %s", args.entity)
            else:
                # Record all
                await record_contact_cassettes(recorder, session)
                await record_activity_cassettes(recorder, session)
                await record_contribution_cassettes(recorder, session)
                await record_event_cassettes(recorder, session)
                await record_participant_cassettes(recorder, session)
                await record_membership_cassettes(recorder, session)
                await record_supporting_entity_cassettes(recorder, session)
                await record_error_cassettes(recorder, session)
                await record_edge_case_cassettes(recorder, session)

        finally:
            await recorder.close()

    return session


def print_summary(session: RecordingSession) -> None:
    """Print recording session summary."""
    print("\n" + "=" * 60)
    print("CASSETTE RECORDING SUMMARY")
    print("=" * 60)
    print(f"CiviCRM Version: {session.civicrm_version} (rev: {session.civicrm_revision})")
    print(f"Started: {session.started_at.isoformat()}")
    print(f"Duration: {(datetime.now(UTC) - session.started_at).total_seconds():.1f}s")
    print("-" * 60)
    print(f"Total:      {session.total}")
    print(f"Successful: {session.successful}")
    print(f"Failed:     {session.failed}")
    print("-" * 60)

    if session.failed > 0:
        print("\nFailed recordings:")
        for result in session.results:
            if not result.success:
                print(f"  - {result.name}: {result.error}")

    print("\nRecorded cassettes:")
    for result in session.results:
        if result.success and result.path:
            print(f"  - {result.path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Record CiviCRM API cassettes for testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--base-url",
        default=os.environ.get("CIVI_BASE_URL", "http://localhost:8080/civicrm/ajax/api4"),
        help="CiviCRM API base URL (default: from CIVI_BASE_URL env or localhost)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CIVI_API_KEY", "test-api-key-civi-py"),
        help="API key for authentication (default: from CIVI_API_KEY env)",
    )
    parser.add_argument(
        "--site-key",
        default=os.environ.get("CIVI_SITE_KEY"),
        help="Optional site key (default: from CIVI_SITE_KEY env)",
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("CIVI_VERSION"),
        help="CiviCRM version for cassette organization (auto-detected if not specified)",
    )
    parser.add_argument(
        "--cassette-dir",
        default="tests/cassettes",
        help="Directory to store cassettes (default: tests/cassettes)",
    )
    parser.add_argument(
        "--entity",
        choices=["Contact", "Activity", "Contribution", "Event", "Participant", "Membership"],
        help="Record cassettes for specific entity only",
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Record only error scenario cassettes",
    )
    parser.add_argument(
        "--edge-cases",
        action="store_true",
        help="Record only edge case cassettes",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        session = asyncio.run(run_recording_session(args))
        print_summary(session)

        return 0 if session.failed == 0 else 1

    except CiviAuthError as e:
        logger.error("Authentication failed: %s", e)
        logger.error("Check your CIVI_API_KEY and CIVI_SITE_KEY settings")
        return 1
    except CiviAPIError as e:
        logger.error("API error: %s", e)
        return 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
