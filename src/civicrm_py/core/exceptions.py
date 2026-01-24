"""Exception hierarchy for civi-py.

All exceptions inherit from CiviError for easy catching of all library errors.
"""

from __future__ import annotations

from typing import Any


class CiviError(Exception):
    """Base exception for all civi-py errors."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class CiviConfigError(CiviError):
    """Configuration error (missing or invalid settings)."""


class CiviAuthError(CiviError):
    """Authentication failed."""


class CiviConnectionError(CiviError):
    """Network connection failed."""


class CiviTimeoutError(CiviConnectionError):
    """Request timed out."""


class CiviAPIError(CiviError):
    """CiviCRM API returned an error response."""

    def __init__(
        self,
        message: str,
        *,
        error_code: int | str | None = None,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.error_code = error_code
        self.error_message = error_message


class CiviNotFoundError(CiviAPIError):
    """Requested entity was not found."""


class CiviValidationError(CiviAPIError):
    """Request validation failed."""


class CiviPermissionError(CiviAPIError):
    """Permission denied for the requested operation."""


class CiviIntegrationError(CiviError):
    """Framework integration error.

    Raised when there are issues with framework integrations such as:
    - Client not initialized during startup
    - Attempting to use async client in sync mode
    - Integration configuration errors
    """


class DoesNotExist(CiviError):
    """Raised when get() finds no matching records.

    This exception is raised by EntityManager.get() when the query
    matches zero records.

    Example:
        try:
            contact = await Contact.objects.get(id=99999)
        except DoesNotExist:
            print("Contact not found")
    """

    def __init__(
        self,
        entity_name: str,
        lookup_params: dict[str, Any] | None = None,
    ) -> None:
        """Initialize DoesNotExist exception.

        Args:
            entity_name: Name of the entity that was not found.
            lookup_params: The query parameters used in the lookup.
        """
        self.entity_name = entity_name
        self.lookup_params = lookup_params or {}
        message = f"{entity_name} matching query does not exist."
        if lookup_params:
            params_str = ", ".join(f"{k}={v!r}" for k, v in lookup_params.items())
            message = f"{entity_name} matching query ({params_str}) does not exist."
        super().__init__(message, details={"entity": entity_name, "params": lookup_params})


class MultipleObjectsReturned(CiviError):
    """Raised when get() finds multiple matching records.

    This exception is raised by EntityManager.get() when the query
    matches more than one record.

    Example:
        try:
            contact = await Contact.objects.get(last_name="Smith")
        except MultipleObjectsReturned:
            print("Multiple contacts found")
    """

    def __init__(
        self,
        entity_name: str,
        count: int,
        lookup_params: dict[str, Any] | None = None,
    ) -> None:
        """Initialize MultipleObjectsReturned exception.

        Args:
            entity_name: Name of the entity.
            count: Number of records found.
            lookup_params: The query parameters used in the lookup.
        """
        self.entity_name = entity_name
        self.count = count
        self.lookup_params = lookup_params or {}
        message = f"get() returned {count} {entity_name} objects; expected 1."
        if lookup_params:
            params_str = ", ".join(f"{k}={v!r}" for k, v in lookup_params.items())
            message = f"get() returned {count} {entity_name} objects ({params_str}); expected 1."
        super().__init__(
            message,
            details={"entity": entity_name, "count": count, "params": lookup_params},
        )


__all__ = [
    "CiviAPIError",
    "CiviAuthError",
    "CiviConfigError",
    "CiviConnectionError",
    "CiviError",
    "CiviIntegrationError",
    "CiviNotFoundError",
    "CiviPermissionError",
    "CiviTimeoutError",
    "CiviValidationError",
    "DoesNotExist",
    "MultipleObjectsReturned",
]
