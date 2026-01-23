"""Msgspec-based serialization for CiviCRM API v4.

Provides high-performance JSON encoding/decoding for API requests and responses.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

import msgspec

T = TypeVar("T")


class APIRequest(msgspec.Struct, kw_only=True):
    """Base structure for CiviCRM API v4 requests.

    Attributes:
        select: Fields to return (default: all).
        where: Filter conditions as list of [field, operator, value].
        orderBy: Sort order as dict of field: direction.
        limit: Maximum number of records to return.
        offset: Number of records to skip.
        join: Related entities to join.
        groupBy: Fields to group by.
        having: Having clause for aggregations.
    """

    select: list[str] | None = None
    where: list[list[Any]] | None = None
    orderBy: dict[str, str] | None = None  # noqa: N815  # CiviCRM API uses camelCase
    limit: int | None = None
    offset: int | None = None
    join: list[list[Any]] | None = None
    groupBy: list[str] | None = None  # noqa: N815  # CiviCRM API uses camelCase
    having: list[list[Any]] | None = None
    values: dict[str, Any] | None = None
    chain: dict[str, Any] | None = None


class APIError(msgspec.Struct):
    """CiviCRM API error response structure.

    Attributes:
        error_code: Error code from CiviCRM (can be int or str).
        error_message: Human-readable error message.
        debug: Debug information (only in debug mode).
    """

    error_code: int | str
    error_message: str
    debug: dict[str, Any] | None = None


class APIResponse(msgspec.Struct, Generic[T]):
    """CiviCRM API v4 response structure.

    Attributes:
        values: List of returned entities.
        count: Total count of matching records.
        countFetched: Number of records actually returned.
        error_code: Error code if request failed.
        error_message: Error message if request failed.
    """

    values: list[T] | None = None
    count: int | None = None
    countFetched: int | None = None  # noqa: N815  # CiviCRM API uses camelCase
    error_code: int | str | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Check if response indicates an error."""
        return self.error_code is not None

    @property
    def first(self) -> T | None:
        """Get first value from response or None."""
        if self.values and len(self.values) > 0:
            return self.values[0]
        return None


class FieldMetadata(msgspec.Struct, kw_only=True):
    """Metadata for a CiviCRM entity field.

    Returned by getFields action.
    """

    name: str
    title: str | None = None
    description: str | None = None
    type: str | None = None
    data_type: str | None = None
    input_type: str | None = None
    required: bool = False
    readonly: bool = False
    options: dict[str, str] | list[dict[str, Any]] | None = None
    fk_entity: str | None = None
    serialize: str | None = None
    default_value: Any = None


class EntityMetadata(msgspec.Struct, kw_only=True):
    """Metadata for a CiviCRM entity.

    Returned by getActions/getFields.
    """

    name: str
    title: str | None = None
    description: str | None = None
    type: str | None = None
    primary_key: list[str] | None = None
    searchable: bool = True


# Encoders and decoders
_encoder = msgspec.json.Encoder()
_decoder = msgspec.json.Decoder()
_response_decoder = msgspec.json.Decoder(APIResponse[dict[str, Any]])


def encode(obj: object) -> bytes:
    """Encode object to JSON bytes.

    Args:
        obj: Object to encode (must be msgspec-compatible).

    Returns:
        JSON-encoded bytes.
    """
    return _encoder.encode(obj)


def decode(data: bytes | str, type_: type[T] | None = None) -> T:
    """Decode JSON to object.

    Args:
        data: JSON bytes or string to decode.
        type_: Optional type to decode into.

    Returns:
        Decoded object.
    """
    if isinstance(data, str):
        data = data.encode()
    if type_ is not None:
        return msgspec.json.decode(data, type=type_)
    return _decoder.decode(data)


def decode_response(data: bytes | str) -> APIResponse[dict[str, Any]]:
    """Decode API response JSON.

    Args:
        data: JSON response bytes or string.

    Returns:
        Decoded APIResponse.
    """
    if isinstance(data, str):
        data = data.encode()
    return _response_decoder.decode(data)


def to_dict(obj: msgspec.Struct) -> dict[str, Any]:
    """Convert msgspec Struct to dictionary.

    Args:
        obj: Struct instance to convert.

    Returns:
        Dictionary representation (excludes None values).
    """
    return {k: v for k, v in msgspec.structs.asdict(obj).items() if v is not None}


__all__ = [
    "APIError",
    "APIRequest",
    "APIResponse",
    "EntityMetadata",
    "FieldMetadata",
    "decode",
    "decode_response",
    "encode",
    "to_dict",
]
