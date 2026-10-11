"""Cassette management utilities for VCR-style HTTP recording and replay.

This module provides infrastructure for recording CiviCRM API responses
and replaying them during testing, enabling:
- Offline testing without a live CiviCRM instance
- Version-specific compatibility testing
- Deterministic and fast test execution
- CI-friendly cassette-only mode

Architecture:
    CassetteManager - Handles cassette storage, retrieval, and mode selection
    CassetteRecorder - Records HTTP interactions to cassettes
    CassetteStore - Manages cassette file I/O with version support
    CassetteMode - Enum for record/replay/auto modes

Example:
    manager = CassetteManager(
        cassette_dir=Path("tests/cassettes"),
        civicrm_version="5.74",
        mode=CassetteMode.REPLAY,
    )

    # Use with respx for HTTP mocking
    @manager.use_cassette("Contact_get")
    async def test_contact_get():
        ...
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import msgspec

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    import respx

T = TypeVar("T")


class CassetteMode(Enum):
    """Operating mode for cassette system.

    Attributes:
        RECORD: Record new HTTP interactions, overwrite existing cassettes.
        REPLAY: Replay from existing cassettes, fail if cassette missing.
        AUTO: Replay if cassette exists, record if missing.
        NONE: Disable cassette system, use live requests.
    """

    RECORD = "record"
    REPLAY = "replay"
    AUTO = "auto"
    NONE = "none"


@dataclass
class HTTPInteraction:
    """Represents a single HTTP request/response pair.

    Attributes:
        request: Request details (method, url, headers, body).
        response: Response details (status, headers, body).
        recorded_at: ISO timestamp when interaction was recorded.
    """

    request: HTTPRequest
    response: HTTPResponse
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class HTTPRequest:
    """HTTP request details for cassette storage.

    Attributes:
        method: HTTP method (GET, POST, etc.).
        url: Full request URL.
        headers: Request headers (sensitive values redacted).
        body: Request body (form data or JSON).
    """

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str | dict[str, Any] | None = None

    def signature(self) -> str:
        """Generate a unique signature for request matching.

        Returns:
            Hash string identifying this request pattern.
        """
        # Normalize URL and body for consistent matching
        normalized = f"{self.method}:{self.url}"
        if self.body:
            if isinstance(self.body, dict):
                # Sort keys for consistent hashing
                normalized += f":{json.dumps(self.body, sort_keys=True)}"
            else:
                normalized += f":{self.body}"
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class HTTPResponse:
    """HTTP response details for cassette storage.

    Attributes:
        status_code: HTTP status code.
        headers: Response headers.
        body: Response body (usually JSON).
    """

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | str | None = None


def dataclass_enc_hook(obj: object) -> Any:
    """Encoding hook for dataclass objects."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
    msg = f"Object of type {type(obj).__name__} is not JSON serializable"
    raise TypeError(msg)


# Module-level encoder with custom hook
_cassette_encoder = msgspec.json.Encoder(enc_hook=dataclass_enc_hook)


class Cassette:
    """A collection of HTTP interactions for a specific test scenario.

    Cassettes are stored as JSON files containing recorded HTTP interactions.
    Each cassette can contain multiple request/response pairs.

    Attributes:
        name: Cassette identifier (e.g., "Contact_get").
        version: CiviCRM version this cassette was recorded from.
        interactions: List of HTTP interactions.
        metadata: Additional cassette metadata.
    """

    def __init__(
        self,
        name: str,
        version: str = "unknown",
        interactions: list[HTTPInteraction] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a cassette.

        Args:
            name: Cassette identifier.
            version: CiviCRM version.
            interactions: Pre-existing interactions to load.
            metadata: Additional metadata.
        """
        self.name = name
        self.version = version
        self.interactions: list[HTTPInteraction] = interactions or []
        self.metadata: dict[str, Any] = metadata or {}
        self._interaction_index: dict[str, HTTPInteraction] = {}
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the request signature index."""
        self._interaction_index = {interaction.request.signature(): interaction for interaction in self.interactions}

    def add_interaction(self, interaction: HTTPInteraction) -> None:
        """Add a new HTTP interaction to the cassette.

        Args:
            interaction: HTTP request/response pair to add.
        """
        self.interactions.append(interaction)
        self._interaction_index[interaction.request.signature()] = interaction

    def find_interaction(self, request: HTTPRequest) -> HTTPInteraction | None:
        """Find a matching interaction for a request.

        Args:
            request: HTTP request to match.

        Returns:
            Matching interaction or None if not found.
        """
        return self._interaction_index.get(request.signature())

    def to_dict(self) -> dict[str, Any]:
        """Convert cassette to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the cassette.
        """
        return {
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata,
            "interactions": [
                {
                    "request": {
                        "method": i.request.method,
                        "url": i.request.url,
                        "headers": i.request.headers,
                        "body": i.request.body,
                    },
                    "response": {
                        "status_code": i.response.status_code,
                        "headers": i.response.headers,
                        "body": i.response.body,
                    },
                    "recorded_at": i.recorded_at,
                }
                for i in self.interactions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cassette:
        """Create a cassette from a dictionary.

        Args:
            data: Dictionary with cassette data.

        Returns:
            New Cassette instance.
        """
        interactions = []
        for i in data.get("interactions", []):
            request = HTTPRequest(
                method=i["request"]["method"],
                url=i["request"]["url"],
                headers=i["request"].get("headers", {}),
                body=i["request"].get("body"),
            )
            response = HTTPResponse(
                status_code=i["response"]["status_code"],
                headers=i["response"].get("headers", {}),
                body=i["response"].get("body"),
            )
            interactions.append(
                HTTPInteraction(
                    request=request,
                    response=response,
                    recorded_at=i.get("recorded_at", ""),
                ),
            )

        return cls(
            name=data["name"],
            version=data.get("version", "unknown"),
            interactions=interactions,
            metadata=data.get("metadata", {}),
        )


class CassetteStore:
    """Manages cassette file storage with version support.

    Cassettes are stored in a directory structure:
        {cassette_dir}/{version}/entities/{name}.json

    This allows testing against multiple CiviCRM versions.
    """

    def __init__(
        self,
        cassette_dir: Path,
        version: str = "default",
    ) -> None:
        """Initialize the cassette store.

        Args:
            cassette_dir: Base directory for cassette storage.
            version: CiviCRM version subdirectory.
        """
        self.cassette_dir = Path(cassette_dir)
        self.version = version
        self._version_dir = self.cassette_dir / f"v{version.lstrip('v')}"

    @property
    def entities_dir(self) -> Path:
        """Get the entities subdirectory for this version."""
        return self._version_dir / "entities"

    def cassette_path(self, name: str) -> Path:
        """Get the file path for a cassette.

        Args:
            name: Cassette name (e.g., "Contact_get").

        Returns:
            Path to the cassette JSON file.
        """
        # Sanitize name for filesystem
        safe_name = re.sub(r"[^\w\-_]", "_", name)
        return self.entities_dir / f"{safe_name}.json"

    def exists(self, name: str) -> bool:
        """Check if a cassette exists.

        Args:
            name: Cassette name.

        Returns:
            True if cassette file exists.
        """
        return self.cassette_path(name).exists()

    def load(self, name: str) -> Cassette:
        """Load a cassette from disk.

        Args:
            name: Cassette name.

        Returns:
            Loaded Cassette instance.

        Raises:
            FileNotFoundError: If cassette does not exist.
        """
        path = self.cassette_path(name)
        if not path.exists():
            msg = f"Cassette not found: {path}"
            raise FileNotFoundError(msg)

        with path.open() as f:
            data = json.load(f)

        return Cassette.from_dict(data)

    def save(self, cassette: Cassette) -> Path:
        """Save a cassette to disk.

        Args:
            cassette: Cassette to save.

        Returns:
            Path where cassette was saved.
        """
        path = self.cassette_path(cassette.name)

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w") as f:
            json.dump(cassette.to_dict(), f, indent=2, sort_keys=True)

        return path

    def list_cassettes(self) -> list[str]:
        """List all available cassettes for this version.

        Returns:
            List of cassette names.
        """
        if not self.entities_dir.exists():
            return []

        return [p.stem for p in self.entities_dir.glob("*.json")]


class CassetteRecorder:
    """Records HTTP interactions to cassettes using respx.

    This class integrates with respx to intercept and record HTTP
    traffic during test execution.
    """

    def __init__(
        self,
        store: CassetteStore,
        redact_headers: list[str] | None = None,
    ) -> None:
        """Initialize the recorder.

        Args:
            store: Cassette store for persistence.
            redact_headers: Header names to redact (e.g., Authorization).
        """
        self.store = store
        self.redact_headers = redact_headers or [
            "Authorization",
            "X-Civi-Api-Key",
            "X-Civi-Site-Key",
            "X-Civi-Key",
            "Cookie",
            "Set-Cookie",
        ]
        self._current_cassette: Cassette | None = None

    def start_recording(self, name: str) -> Cassette:
        """Start recording to a new cassette.

        Args:
            name: Cassette name.

        Returns:
            New Cassette instance for recording.
        """
        self._current_cassette = Cassette(
            name=name,
            version=self.store.version,
            metadata={
                "recorded_at": datetime.now(UTC).isoformat(),
                "civicrm_version": self.store.version,
            },
        )
        return self._current_cassette

    def record_interaction(
        self,
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        """Record an HTTP interaction.

        Args:
            request: The HTTP request.
            response: The HTTP response.

        Raises:
            RuntimeError: If recording has not been started.
        """
        if self._current_cassette is None:
            msg = "Recording not started. Call start_recording() first."
            raise RuntimeError(msg)

        # Redact sensitive headers
        req_headers = dict(request.headers)
        for header in self.redact_headers:
            if header.lower() in {h.lower() for h in req_headers}:
                # Find the actual key (case-insensitive)
                for key in list(req_headers.keys()):
                    if key.lower() == header.lower():
                        req_headers[key] = "[REDACTED]"

        # Parse request body
        req_body: str | dict[str, Any] | None = None
        if request.content:
            try:
                req_body = json.loads(request.content.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                req_body = request.content.decode(errors="replace")

        # Parse response body
        resp_body: dict[str, Any] | str | None = None
        if response.content:
            try:
                resp_body = json.loads(response.content.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                resp_body = response.content.decode(errors="replace")

        http_request = HTTPRequest(
            method=request.method,
            url=str(request.url),
            headers=req_headers,
            body=req_body,
        )

        http_response = HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=resp_body,
        )

        interaction = HTTPInteraction(request=http_request, response=http_response)
        self._current_cassette.add_interaction(interaction)

    def stop_recording(self) -> Cassette | None:
        """Stop recording and save the cassette.

        Returns:
            The completed cassette, or None if not recording.
        """
        if self._current_cassette is None:
            return None

        cassette = self._current_cassette
        self._current_cassette = None

        if cassette.interactions:
            self.store.save(cassette)

        return cassette


class CassetteManager:
    """High-level manager for cassette-based testing.

    Coordinates recording, replay, and mode selection for HTTP mocking.

    Example:
        manager = CassetteManager(
            cassette_dir=Path("tests/cassettes"),
            civicrm_version="5.74",
        )

        # In fixture or test setup
        cassette = manager.load_or_create("Contact_get")
        with manager.mock_router(cassette) as router:
            # Run test code
            ...
    """

    def __init__(
        self,
        cassette_dir: Path,
        civicrm_version: str = "default",
        mode: CassetteMode | None = None,
        base_url: str = "https://example.org/civicrm/ajax/api4",
    ) -> None:
        """Initialize the cassette manager.

        Args:
            cassette_dir: Base directory for cassette storage.
            civicrm_version: CiviCRM version for cassette organization.
            mode: Operating mode (auto-detected from env if None).
            base_url: Base URL for CiviCRM API (used for routing).
        """
        self.cassette_dir = Path(cassette_dir)
        self.civicrm_version = civicrm_version
        self.base_url = base_url.rstrip("/")

        # Auto-detect mode from environment
        if mode is None:
            mode = self._detect_mode()
        self.mode = mode

        self.store = CassetteStore(self.cassette_dir, civicrm_version)
        self.recorder = CassetteRecorder(self.store)

    def _detect_mode(self) -> CassetteMode:
        """Detect cassette mode from environment variables.

        Environment variables checked:
            CIVI_CASSETTE_MODE: Explicit mode (record, replay, auto, none)
            CI: If set, defaults to REPLAY mode

        Returns:
            Detected CassetteMode.
        """
        mode_env = os.environ.get("CIVI_CASSETTE_MODE", "").lower()

        if mode_env:
            try:
                return CassetteMode(mode_env)
            except ValueError:
                pass

        # In CI, default to replay-only
        if os.environ.get("CI"):
            return CassetteMode.REPLAY

        return CassetteMode.AUTO

    def load_or_create(self, name: str) -> Cassette:
        """Load an existing cassette or create a new one based on mode.

        Args:
            name: Cassette name.

        Returns:
            Cassette instance.

        Raises:
            FileNotFoundError: In REPLAY mode if cassette doesn't exist.
        """
        if self.mode == CassetteMode.REPLAY:
            return self.store.load(name)

        if self.mode == CassetteMode.RECORD:
            return self.recorder.start_recording(name)

        if self.mode == CassetteMode.AUTO:
            if self.store.exists(name):
                return self.store.load(name)
            return self.recorder.start_recording(name)

        # NONE mode - return empty cassette
        return Cassette(name=name, version=self.civicrm_version)

    def configure_mock(
        self,
        mock: respx.MockRouter,
        cassette: Cassette,
        record_callback: Callable[[httpx.Request, httpx.Response], None] | None = None,
    ) -> None:
        """Configure a respx mock router with cassette data.

        Args:
            mock: respx MockRouter instance.
            cassette: Cassette containing interactions to replay.
            record_callback: Optional callback for recording mode.
        """
        import httpx

        for interaction in cassette.interactions:
            # Build response (for potential future use in logging/debugging)
            if isinstance(interaction.response.body, dict):
                _ = httpx.Response(
                    status_code=interaction.response.status_code,
                    json=interaction.response.body,
                    headers=interaction.response.headers,
                )
            else:
                _ = httpx.Response(
                    status_code=interaction.response.status_code,
                    content=interaction.response.body or "",
                    headers=interaction.response.headers,
                )

            # Route based on URL
            mock.route(
                method=interaction.request.method,
                url=interaction.request.url,
            ).respond(
                status_code=interaction.response.status_code,
                json=interaction.response.body if isinstance(interaction.response.body, dict) else None,
                content=interaction.response.body if isinstance(interaction.response.body, str) else None,
                headers=interaction.response.headers,
            )

    def is_recording(self) -> bool:
        """Check if manager is in recording mode.

        Returns:
            True if recording new interactions.
        """
        return self.mode in (CassetteMode.RECORD, CassetteMode.AUTO)

    def save_current(self) -> None:
        """Save the current recording if any."""
        self.recorder.stop_recording()


def get_cassette_manager(
    cassette_dir: Path | str | None = None,
    civicrm_version: str | None = None,
) -> CassetteManager:
    """Get a configured CassetteManager instance.

    This is a convenience factory that reads configuration from
    environment variables with sensible defaults.

    Args:
        cassette_dir: Override cassette directory.
        civicrm_version: Override CiviCRM version.

    Returns:
        Configured CassetteManager instance.
    """
    if cassette_dir is None:
        # Default to tests/cassettes relative to this file
        cassette_dir = Path(__file__).parent.parent / "cassettes"

    if civicrm_version is None:
        civicrm_version = os.environ.get("CIVI_VERSION", "default")

    return CassetteManager(
        cassette_dir=Path(cassette_dir),
        civicrm_version=civicrm_version,
    )


__all__ = [
    "Cassette",
    "CassetteManager",
    "CassetteMode",
    "CassetteRecorder",
    "CassetteStore",
    "HTTPInteraction",
    "HTTPRequest",
    "HTTPResponse",
    "dataclass_enc_hook",
    "get_cassette_manager",
]
