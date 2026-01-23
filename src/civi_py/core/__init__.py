"""Core module for civi-py.

Contains client, configuration, authentication, and serialization components.
"""

from __future__ import annotations

from civi_py.core.auth import APIKeyAuth, AuthProvider, BasicAuth, JWTAuth
from civi_py.core.client import CiviClient, SyncCiviClient
from civi_py.core.config import CiviSettings, get_settings
from civi_py.core.context import (
    ClientContext,
    client_context,
    get_current_client,
    reset_current_client,
    set_current_client,
    use_client,
)
from civi_py.core.exceptions import (
    CiviAPIError,
    CiviAuthError,
    CiviConfigError,
    CiviConnectionError,
    CiviError,
    CiviIntegrationError,
    CiviNotFoundError,
    CiviPermissionError,
    CiviTimeoutError,
    CiviValidationError,
    DoesNotExist,
    MultipleObjectsReturned,
)
from civi_py.core.serialization import (
    APIError,
    APIRequest,
    APIResponse,
    EntityMetadata,
    FieldMetadata,
)

__all__ = [
    "APIError",
    "APIKeyAuth",
    "APIRequest",
    "APIResponse",
    "AuthProvider",
    "BasicAuth",
    "CiviAPIError",
    "CiviAuthError",
    "CiviClient",
    "CiviConfigError",
    "CiviConnectionError",
    "CiviError",
    "CiviIntegrationError",
    "CiviNotFoundError",
    "CiviPermissionError",
    "CiviSettings",
    "CiviTimeoutError",
    "CiviValidationError",
    "ClientContext",
    "DoesNotExist",
    "EntityMetadata",
    "FieldMetadata",
    "JWTAuth",
    "MultipleObjectsReturned",
    "SyncCiviClient",
    "client_context",
    "get_current_client",
    "get_settings",
    "reset_current_client",
    "set_current_client",
    "use_client",
]
