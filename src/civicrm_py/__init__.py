"""civi-py: Modern Python client for CiviCRM API v4.

A type-safe, async-first Python client for CiviCRM with msgspec serialization.

Basic Usage:
    >>> from civicrm_py import CiviClient
    >>> async with CiviClient(base_url="...", api_key="...") as client:
    ...     response = await client.get("Contact", limit=10)
    ...     for contact in response.values:
    ...         print(contact["display_name"])

Sync Usage:
    >>> from civicrm_py import SyncCiviClient
    >>> with SyncCiviClient(base_url="...", api_key="...") as client:
    ...     response = client.get("Contact", limit=10)
"""

from __future__ import annotations

from civicrm_py.core.client import CiviClient, SyncCiviClient
from civicrm_py.core.config import CiviSettings, get_settings
from civicrm_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConfigError,
    CiviConnectionError,
    CiviError,
    CiviNotFoundError,
    CiviPermissionError,
    CiviTimeoutError,
    CiviValidationError,
)
from civicrm_py.core.serialization import APIRequest, APIResponse

__version__ = "0.1.0"

__all__ = [
    "APIRequest",
    "APIResponse",
    "CiviAPIError",
    "CiviAuthError",
    "CiviClient",
    "CiviConfigError",
    "CiviConnectionError",
    "CiviError",
    "CiviNotFoundError",
    "CiviPermissionError",
    "CiviSettings",
    "CiviTimeoutError",
    "CiviValidationError",
    "SyncCiviClient",
    "__version__",
    "get_settings",
]
