"""Tests for msgspec-based serialization module."""

from __future__ import annotations

from typing import Any

import pytest

from civi_py.core.serialization import (
    APIError,
    APIRequest,
    APIResponse,
    EntityMetadata,
    FieldMetadata,
    decode,
    decode_response,
    encode,
    to_dict,
)


class TestAPIRequest:
    """Tests for APIRequest struct."""

    def test_create_empty_request(self) -> None:
        """Test creating an APIRequest with no fields set."""
        request = APIRequest()

        assert request.select is None
        assert request.where is None
        assert request.orderBy is None
        assert request.limit is None
        assert request.offset is None
        assert request.join is None
        assert request.groupBy is None
        assert request.having is None
        assert request.values is None
        assert request.chain is None

    def test_create_request_with_select(self) -> None:
        """Test creating an APIRequest with select fields."""
        request = APIRequest(select=["id", "display_name", "email_primary.email"])

        assert request.select == ["id", "display_name", "email_primary.email"]
        assert request.where is None

    def test_create_request_with_where_clauses(self) -> None:
        """Test creating an APIRequest with where conditions."""
        where = [
            ["is_deleted", "=", False],
            ["first_name", "LIKE", "John%"],
            ["id", "IN", [1, 2, 3]],
        ]
        request = APIRequest(where=where)

        assert request.where == where
        assert len(request.where) == 3

    def test_create_request_with_order_by(self) -> None:
        """Test creating an APIRequest with orderBy."""
        request = APIRequest(orderBy={"last_name": "ASC", "first_name": "ASC"})

        assert request.orderBy == {"last_name": "ASC", "first_name": "ASC"}

    def test_create_request_with_pagination(self) -> None:
        """Test creating an APIRequest with limit and offset."""
        request = APIRequest(limit=25, offset=50)

        assert request.limit == 25
        assert request.offset == 50

    def test_create_request_with_join(self) -> None:
        """Test creating an APIRequest with join."""
        joins = [
            ["Email AS emails", "LEFT", ["id", "=", "emails.contact_id"]],
        ]
        request = APIRequest(join=joins)

        assert request.join == joins

    def test_create_request_with_group_by(self) -> None:
        """Test creating an APIRequest with groupBy."""
        request = APIRequest(groupBy=["contact_type", "is_deleted"])

        assert request.groupBy == ["contact_type", "is_deleted"]

    def test_create_request_with_having(self) -> None:
        """Test creating an APIRequest with having clause."""
        having = [["COUNT(id)", ">", 5]]
        request = APIRequest(having=having)

        assert request.having == having

    def test_create_request_with_values(self) -> None:
        """Test creating an APIRequest with values for create/update."""
        values = {
            "first_name": "John",
            "last_name": "Doe",
            "contact_type": "Individual",
        }
        request = APIRequest(values=values)

        assert request.values == values

    def test_create_request_with_chain(self) -> None:
        """Test creating an APIRequest with chained API calls."""
        chain = {
            "emails": ["Email", "get", {"where": [["contact_id", "=", "$id"]]}],
        }
        request = APIRequest(chain=chain)

        assert request.chain == chain

    def test_create_full_request(self) -> None:
        """Test creating an APIRequest with all fields populated."""
        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            orderBy={"display_name": "ASC"},
            limit=10,
            offset=0,
            join=[["Email AS e", "LEFT", ["id", "=", "e.contact_id"]]],
            groupBy=["contact_type"],
            having=[["COUNT(id)", ">", 1]],
            values={"modified_date": "2024-01-01"},
            chain={"activities": ["Activity", "get", {}]},
        )

        assert request.select == ["id", "display_name"]
        assert request.where == [["is_deleted", "=", False]]
        assert request.orderBy == {"display_name": "ASC"}
        assert request.limit == 10
        assert request.offset == 0
        assert request.join is not None
        assert request.groupBy == ["contact_type"]
        assert request.having is not None
        assert request.values is not None
        assert request.chain is not None


class TestAPIResponse:
    """Tests for APIResponse struct."""

    def test_create_success_response(self) -> None:
        """Test creating a successful APIResponse."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1, "name": "Test"}],
            count=1,
            countFetched=1,
        )

        assert response.values == [{"id": 1, "name": "Test"}]
        assert response.count == 1
        assert response.countFetched == 1
        assert response.error_code is None
        assert response.error_message is None

    def test_create_error_response_with_int_code(self) -> None:
        """Test creating an error APIResponse with integer error code."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_code=500,
            error_message="Internal Server Error",
        )

        assert response.values is None
        assert response.error_code == 500
        assert response.error_message == "Internal Server Error"

    def test_create_error_response_with_str_code(self) -> None:
        """Test creating an error APIResponse with string error code."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_code="unauthorized",
            error_message="API key is invalid",
        )

        assert response.error_code == "unauthorized"
        assert response.error_message == "API key is invalid"

    def test_create_empty_response(self) -> None:
        """Test creating an empty APIResponse."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        assert response.values == []
        assert response.count == 0
        assert response.countFetched == 0

    def test_is_error_false_on_success(self) -> None:
        """Test is_error property returns False for successful responses."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}],
            count=1,
            countFetched=1,
        )

        assert response.is_error is False

    def test_is_error_true_on_error(self) -> None:
        """Test is_error property returns True for error responses."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_code="not_found",
            error_message="Entity not found",
        )

        assert response.is_error is True

    def test_is_error_true_with_int_code(self) -> None:
        """Test is_error property returns True for integer error codes."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            error_code=404,
            error_message="Not found",
        )

        assert response.is_error is True

    def test_first_returns_first_value(self) -> None:
        """Test first property returns first value from response."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[
                {"id": 1, "name": "First"},
                {"id": 2, "name": "Second"},
            ],
            count=2,
            countFetched=2,
        )

        assert response.first == {"id": 1, "name": "First"}

    def test_first_returns_none_on_empty_values(self) -> None:
        """Test first property returns None when values is empty."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        assert response.first is None

    def test_first_returns_none_when_values_is_none(self) -> None:
        """Test first property returns None when values is None."""
        response: APIResponse[dict[str, Any]] = APIResponse()

        assert response.first is None

    def test_response_with_multiple_values(self) -> None:
        """Test APIResponse with multiple values."""
        values = [{"id": i, "name": f"Item {i}"} for i in range(1, 11)]
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=values,
            count=100,
            countFetched=10,
        )

        assert len(response.values) == 10
        assert response.count == 100
        assert response.countFetched == 10
        assert response.first == {"id": 1, "name": "Item 1"}


class TestAPIError:
    """Tests for APIError struct."""

    def test_create_error_with_int_code(self) -> None:
        """Test creating an APIError with integer code."""
        error = APIError(
            error_code=500,
            error_message="Internal Server Error",
        )

        assert error.error_code == 500
        assert error.error_message == "Internal Server Error"
        assert error.debug is None

    def test_create_error_with_str_code(self) -> None:
        """Test creating an APIError with string code."""
        error = APIError(
            error_code="validation_error",
            error_message="Invalid field value",
        )

        assert error.error_code == "validation_error"
        assert error.error_message == "Invalid field value"

    def test_create_error_with_debug(self) -> None:
        """Test creating an APIError with debug information."""
        debug_info = {
            "trace": ["file1.php:100", "file2.php:200"],
            "query": "SELECT * FROM civicrm_contact",
        }
        error = APIError(
            error_code=500,
            error_message="Database error",
            debug=debug_info,
        )

        assert error.debug == debug_info


class TestFieldMetadata:
    """Tests for FieldMetadata struct."""

    def test_create_minimal_field(self) -> None:
        """Test creating FieldMetadata with only required field."""
        field = FieldMetadata(name="id")

        assert field.name == "id"
        assert field.title is None
        assert field.description is None
        assert field.type is None
        assert field.data_type is None
        assert field.input_type is None
        assert field.required is False
        assert field.readonly is False
        assert field.options is None
        assert field.fk_entity is None
        assert field.serialize is None
        assert field.default_value is None

    def test_create_full_field(self) -> None:
        """Test creating FieldMetadata with all fields."""
        field = FieldMetadata(
            name="contact_type",
            title="Contact Type",
            description="Type of contact",
            type="Field",
            data_type="String",
            input_type="Select",
            required=True,
            readonly=False,
            options={"Individual": "Individual", "Organization": "Organization"},
            fk_entity=None,
            serialize="JSON",
            default_value="Individual",
        )

        assert field.name == "contact_type"
        assert field.title == "Contact Type"
        assert field.description == "Type of contact"
        assert field.data_type == "String"
        assert field.input_type == "Select"
        assert field.required is True
        assert field.readonly is False
        assert field.options == {"Individual": "Individual", "Organization": "Organization"}
        assert field.default_value == "Individual"

    def test_create_field_with_fk(self) -> None:
        """Test creating FieldMetadata with foreign key."""
        field = FieldMetadata(
            name="contact_id",
            title="Contact",
            data_type="Integer",
            required=True,
            fk_entity="Contact",
        )

        assert field.name == "contact_id"
        assert field.fk_entity == "Contact"

    def test_create_field_with_list_options(self) -> None:
        """Test creating FieldMetadata with list-style options."""
        options = [
            {"id": "1", "name": "Option A", "label": "Option A"},
            {"id": "2", "name": "Option B", "label": "Option B"},
        ]
        field = FieldMetadata(
            name="status_id",
            options=options,
        )

        assert field.options == options


class TestEntityMetadata:
    """Tests for EntityMetadata struct."""

    def test_create_minimal_entity(self) -> None:
        """Test creating EntityMetadata with only required field."""
        entity = EntityMetadata(name="Contact")

        assert entity.name == "Contact"
        assert entity.title is None
        assert entity.description is None
        assert entity.type is None
        assert entity.primary_key is None
        assert entity.searchable is True

    def test_create_full_entity(self) -> None:
        """Test creating EntityMetadata with all fields."""
        entity = EntityMetadata(
            name="Contact",
            title="Contacts",
            description="CiviCRM contact records",
            type="Entity",
            primary_key=["id"],
            searchable=True,
        )

        assert entity.name == "Contact"
        assert entity.title == "Contacts"
        assert entity.description == "CiviCRM contact records"
        assert entity.type == "Entity"
        assert entity.primary_key == ["id"]
        assert entity.searchable is True

    def test_create_non_searchable_entity(self) -> None:
        """Test creating non-searchable EntityMetadata."""
        entity = EntityMetadata(
            name="Setting",
            searchable=False,
        )

        assert entity.name == "Setting"
        assert entity.searchable is False


class TestEncode:
    """Tests for encode function."""

    def test_encode_api_request(self) -> None:
        """Test encoding APIRequest to JSON bytes."""
        request = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=10,
        )

        encoded = encode(request)

        assert isinstance(encoded, bytes)
        assert b'"select":["id","display_name"]' in encoded
        assert b'"limit":10' in encoded

    def test_encode_dict(self) -> None:
        """Test encoding plain dict to JSON bytes."""
        data = {"key": "value", "number": 42, "flag": True}

        encoded = encode(data)

        assert isinstance(encoded, bytes)
        assert b'"key":"value"' in encoded
        assert b'"number":42' in encoded
        assert b'"flag":true' in encoded

    def test_encode_list(self) -> None:
        """Test encoding list to JSON bytes."""
        data = [1, 2, 3, "four", None]

        encoded = encode(data)

        assert isinstance(encoded, bytes)
        assert encoded == b'[1,2,3,"four",null]'

    def test_encode_nested_structure(self) -> None:
        """Test encoding nested structures."""
        data = {
            "outer": {
                "inner": {
                    "values": [1, 2, 3],
                },
            },
        }

        encoded = encode(data)

        assert isinstance(encoded, bytes)
        assert b'"outer":{' in encoded
        assert b'"inner":{' in encoded
        assert b'"values":[1,2,3]' in encoded

    def test_encode_api_request_includes_none_values(self) -> None:
        """Test that encoding APIRequest includes None values.

        Note: msgspec's default encoder includes None values. Use to_dict()
        to get a dict without None values before encoding if needed.
        """
        request = APIRequest(select=["id"])

        encoded = encode(request)

        # msgspec includes None values by default
        assert b'"select":["id"]' in encoded
        assert b'"where":null' in encoded
        assert b'"limit":null' in encoded


class TestDecode:
    """Tests for decode function."""

    def test_decode_bytes_without_type(self) -> None:
        """Test decoding JSON bytes without type hint."""
        data = b'{"key": "value", "number": 42}'

        decoded = decode(data)

        assert decoded == {"key": "value", "number": 42}

    def test_decode_string_without_type(self) -> None:
        """Test decoding JSON string without type hint."""
        data = '{"key": "value"}'

        decoded = decode(data)

        assert decoded == {"key": "value"}

    def test_decode_with_type(self) -> None:
        """Test decoding JSON with type hint."""
        data = b'{"name": "contact_type", "required": true}'

        decoded = decode(data, FieldMetadata)

        assert isinstance(decoded, FieldMetadata)
        assert decoded.name == "contact_type"
        assert decoded.required is True

    def test_decode_api_request(self) -> None:
        """Test decoding JSON to APIRequest."""
        data = b'{"select": ["id", "name"], "limit": 25}'

        decoded = decode(data, APIRequest)

        assert isinstance(decoded, APIRequest)
        assert decoded.select == ["id", "name"]
        assert decoded.limit == 25

    def test_decode_list(self) -> None:
        """Test decoding JSON array."""
        data = b'[1, 2, 3, "four"]'

        decoded = decode(data)

        assert decoded == [1, 2, 3, "four"]

    def test_decode_nested_structure(self) -> None:
        """Test decoding nested JSON structure."""
        data = b'{"level1": {"level2": {"level3": "value"}}}'

        decoded = decode(data)

        assert decoded == {"level1": {"level2": {"level3": "value"}}}

    def test_decode_empty_object(self) -> None:
        """Test decoding empty JSON object."""
        data = b"{}"

        decoded = decode(data)

        assert decoded == {}

    def test_decode_empty_array(self) -> None:
        """Test decoding empty JSON array."""
        data = b"[]"

        decoded = decode(data)

        assert decoded == []


class TestDecodeResponse:
    """Tests for decode_response function."""

    def test_decode_success_response(self) -> None:
        """Test decoding successful API response."""
        data = b"""{
            "values": [{"id": 1, "name": "Test"}],
            "count": 1,
            "countFetched": 1
        }"""

        response = decode_response(data)

        assert isinstance(response, APIResponse)
        assert response.values == [{"id": 1, "name": "Test"}]
        assert response.count == 1
        assert response.countFetched == 1
        assert response.is_error is False

    def test_decode_success_response_from_string(self) -> None:
        """Test decoding successful API response from string."""
        data = '{"values": [{"id": 1}], "count": 1, "countFetched": 1}'

        response = decode_response(data)

        assert isinstance(response, APIResponse)
        assert response.values == [{"id": 1}]

    def test_decode_error_response(self) -> None:
        """Test decoding error API response."""
        data = b"""{
            "error_code": "unauthorized",
            "error_message": "API key is invalid"
        }"""

        response = decode_response(data)

        assert isinstance(response, APIResponse)
        assert response.is_error is True
        assert response.error_code == "unauthorized"
        assert response.error_message == "API key is invalid"
        assert response.values is None

    def test_decode_error_response_with_int_code(self) -> None:
        """Test decoding error API response with integer code."""
        data = b"""{
            "error_code": 500,
            "error_message": "Internal Server Error"
        }"""

        response = decode_response(data)

        assert response.is_error is True
        assert response.error_code == 500
        assert response.error_message == "Internal Server Error"

    def test_decode_empty_response(self) -> None:
        """Test decoding empty values response."""
        data = b"""{
            "values": [],
            "count": 0,
            "countFetched": 0
        }"""

        response = decode_response(data)

        assert response.values == []
        assert response.count == 0
        assert response.first is None
        assert response.is_error is False

    def test_decode_multiple_values_response(self) -> None:
        """Test decoding response with multiple values."""
        data = b"""{
            "values": [
                {"id": 1, "name": "First"},
                {"id": 2, "name": "Second"},
                {"id": 3, "name": "Third"}
            ],
            "count": 100,
            "countFetched": 3
        }"""

        response = decode_response(data)

        assert len(response.values) == 3
        assert response.count == 100
        assert response.countFetched == 3
        assert response.first == {"id": 1, "name": "First"}

    def test_decode_response_with_nested_values(self) -> None:
        """Test decoding response with nested value structures."""
        data = b"""{
            "values": [
                {
                    "id": 1,
                    "contact_type": "Individual",
                    "email_primary.email": "test@example.com",
                    "phones": [{"id": 1, "phone": "123-456-7890"}]
                }
            ],
            "count": 1,
            "countFetched": 1
        }"""

        response = decode_response(data)

        first = response.first
        assert first is not None
        assert first["id"] == 1
        assert first["email_primary.email"] == "test@example.com"
        assert first["phones"] == [{"id": 1, "phone": "123-456-7890"}]


class TestToDict:
    """Tests for to_dict function."""

    def test_to_dict_excludes_none_values(self) -> None:
        """Test that to_dict excludes None values."""
        request = APIRequest(select=["id", "name"], limit=10)

        result = to_dict(request)

        assert "select" in result
        assert "limit" in result
        assert "where" not in result
        assert "orderBy" not in result
        assert "offset" not in result

    def test_to_dict_full_request(self) -> None:
        """Test to_dict with all fields populated."""
        request = APIRequest(
            select=["id"],
            where=[["is_deleted", "=", False]],
            orderBy={"id": "ASC"},
            limit=10,
            offset=5,
            groupBy=["contact_type"],
            having=[["COUNT(id)", ">", 1]],
            values={"field": "value"},
            chain={"related": ["Entity", "get", {}]},
        )

        result = to_dict(request)

        assert result["select"] == ["id"]
        assert result["where"] == [["is_deleted", "=", False]]
        assert result["orderBy"] == {"id": "ASC"}
        assert result["limit"] == 10
        assert result["offset"] == 5
        assert result["groupBy"] == ["contact_type"]
        assert result["having"] == [["COUNT(id)", ">", 1]]
        assert result["values"] == {"field": "value"}
        assert result["chain"] == {"related": ["Entity", "get", {}]}

    def test_to_dict_empty_request(self) -> None:
        """Test to_dict with empty request returns empty dict."""
        request = APIRequest()

        result = to_dict(request)

        assert result == {}

    def test_to_dict_field_metadata(self) -> None:
        """Test to_dict with FieldMetadata."""
        field = FieldMetadata(
            name="contact_id",
            title="Contact",
            required=True,
        )

        result = to_dict(field)

        assert result["name"] == "contact_id"
        assert result["title"] == "Contact"
        assert result["required"] is True
        # Default False values are included
        assert result["readonly"] is False
        # None values are excluded
        assert "description" not in result
        assert "options" not in result

    def test_to_dict_entity_metadata(self) -> None:
        """Test to_dict with EntityMetadata."""
        entity = EntityMetadata(
            name="Contact",
            title="Contacts",
            primary_key=["id"],
        )

        result = to_dict(entity)

        assert result["name"] == "Contact"
        assert result["title"] == "Contacts"
        assert result["primary_key"] == ["id"]
        assert result["searchable"] is True  # Default value
        assert "description" not in result  # None excluded

    def test_to_dict_api_error(self) -> None:
        """Test to_dict with APIError."""
        error = APIError(
            error_code=500,
            error_message="Server Error",
        )

        result = to_dict(error)

        assert result["error_code"] == 500
        assert result["error_message"] == "Server Error"
        assert "debug" not in result  # None excluded


class TestEncodeDecodeRoundtrip:
    """Tests for encode/decode roundtrip consistency."""

    def test_roundtrip_api_request(self) -> None:
        """Test encoding and decoding APIRequest preserves data."""
        original = APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=25,
            offset=0,
        )

        encoded = encode(original)
        decoded = decode(encoded, APIRequest)

        assert decoded.select == original.select
        assert decoded.where == original.where
        assert decoded.limit == original.limit
        assert decoded.offset == original.offset

    def test_roundtrip_field_metadata(self) -> None:
        """Test encoding and decoding FieldMetadata preserves data."""
        original = FieldMetadata(
            name="email",
            title="Email Address",
            data_type="String",
            required=True,
        )

        encoded = encode(original)
        decoded = decode(encoded, FieldMetadata)

        assert decoded.name == original.name
        assert decoded.title == original.title
        assert decoded.data_type == original.data_type
        assert decoded.required == original.required

    def test_roundtrip_entity_metadata(self) -> None:
        """Test encoding and decoding EntityMetadata preserves data."""
        original = EntityMetadata(
            name="Contact",
            title="Contacts",
            description="Contact records",
            primary_key=["id"],
            searchable=True,
        )

        encoded = encode(original)
        decoded = decode(encoded, EntityMetadata)

        assert decoded.name == original.name
        assert decoded.title == original.title
        assert decoded.description == original.description
        assert decoded.primary_key == original.primary_key
        assert decoded.searchable == original.searchable

    def test_roundtrip_complex_nested_data(self) -> None:
        """Test encoding and decoding complex nested structures."""
        original = {
            "entity": "Contact",
            "action": "get",
            "params": {
                "select": ["id", "display_name"],
                "where": [
                    ["is_deleted", "=", False],
                    ["contact_type", "IN", ["Individual", "Organization"]],
                ],
                "join": [
                    ["Email AS e", "LEFT", ["id", "=", "e.contact_id"]],
                ],
                "orderBy": {"modified_date": "DESC"},
                "limit": 50,
            },
        }

        encoded = encode(original)
        decoded = decode(encoded)

        assert decoded == original

    def test_roundtrip_with_special_characters(self) -> None:
        """Test encoding and decoding with special characters."""
        original = {
            "name": "Test O'Brien",
            "description": 'Contains "quotes" and \\ backslashes',
            "notes": "Unicode: \u00e9\u00e8\u00ea",
        }

        encoded = encode(original)
        decoded = decode(encoded)

        assert decoded == original


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_where_list(self) -> None:
        """Test APIRequest with empty where list."""
        request = APIRequest(where=[])

        assert request.where == []

        result = to_dict(request)
        assert result["where"] == []

    def test_empty_select_list(self) -> None:
        """Test APIRequest with empty select list."""
        request = APIRequest(select=[])

        assert request.select == []

    def test_zero_limit(self) -> None:
        """Test APIRequest with zero limit."""
        request = APIRequest(limit=0)

        assert request.limit == 0

        result = to_dict(request)
        assert result["limit"] == 0

    def test_negative_offset(self) -> None:
        """Test APIRequest with negative offset."""
        # msgspec doesn't validate values, just types
        request = APIRequest(offset=-10)

        assert request.offset == -10

    def test_where_with_null_value(self) -> None:
        """Test APIRequest where clause with null value."""
        request = APIRequest(where=[["field", "IS NULL", None]])

        assert request.where == [["field", "IS NULL", None]]

    def test_values_with_nested_objects(self) -> None:
        """Test APIRequest values with deeply nested objects."""
        values = {
            "custom_fields": {
                "custom_1": {
                    "nested": {
                        "deep": "value",
                    },
                },
            },
        }
        request = APIRequest(values=values)

        assert request.values == values

        encoded = encode(request)
        decoded = decode(encoded, APIRequest)
        assert decoded.values == values

    def test_api_response_with_none_count(self) -> None:
        """Test APIResponse where count fields are None."""
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}],
        )

        assert response.values == [{"id": 1}]
        assert response.count is None
        assert response.countFetched is None
        assert response.is_error is False

    def test_decode_response_minimal_json(self) -> None:
        """Test decoding minimal valid JSON response."""
        data = b"{}"

        response = decode_response(data)

        assert response.values is None
        assert response.count is None
        assert response.is_error is False

    def test_to_dict_preserves_false_boolean(self) -> None:
        """Test that to_dict preserves False boolean values."""
        field = FieldMetadata(
            name="is_active",
            required=False,
            readonly=False,
        )

        result = to_dict(field)

        assert result["required"] is False
        assert result["readonly"] is False

    def test_to_dict_preserves_zero_values(self) -> None:
        """Test that to_dict preserves zero numeric values."""
        request = APIRequest(limit=0, offset=0)

        result = to_dict(request)

        assert result["limit"] == 0
        assert result["offset"] == 0

    def test_api_response_generic_type(self) -> None:
        """Test APIResponse works with different generic types."""
        # With dict values
        dict_response: APIResponse[dict[str, Any]] = APIResponse(
            values=[{"id": 1}],
        )
        assert dict_response.first == {"id": 1}

        # Response with any type still works at runtime
        list_response: APIResponse[list[int]] = APIResponse(
            values=[[1, 2, 3], [4, 5, 6]],
        )
        assert list_response.first == [1, 2, 3]

    def test_large_response_values(self) -> None:
        """Test handling responses with many values."""
        values = [{"id": i, "name": f"Item {i}"} for i in range(1000)]
        response: APIResponse[dict[str, Any]] = APIResponse(
            values=values,
            count=10000,
            countFetched=1000,
        )

        assert len(response.values) == 1000
        assert response.first == {"id": 0, "name": "Item 0"}
        assert response.count == 10000


class TestAPIRequestFixtures:
    """Tests using pytest fixtures for common request patterns."""

    @pytest.fixture
    def simple_get_request(self) -> APIRequest:
        """Create a simple get request fixture."""
        return APIRequest(
            select=["id", "display_name"],
            where=[["is_deleted", "=", False]],
            limit=25,
        )

    @pytest.fixture
    def complex_search_request(self) -> APIRequest:
        """Create a complex search request fixture."""
        return APIRequest(
            select=["id", "display_name", "email_primary.email"],
            where=[
                ["is_deleted", "=", False],
                ["contact_type", "IN", ["Individual", "Organization"]],
                ["first_name", "LIKE", "J%"],
            ],
            orderBy={"display_name": "ASC"},
            limit=50,
            offset=0,
            join=[["Email AS e", "LEFT", ["id", "=", "e.contact_id"]]],
        )

    @pytest.fixture
    def create_request(self) -> APIRequest:
        """Create a create/update request fixture."""
        return APIRequest(
            values={
                "first_name": "John",
                "last_name": "Doe",
                "contact_type": "Individual",
                "email_primary.email": "john@example.com",
            },
        )

    def test_simple_request_encoding(self, simple_get_request: APIRequest) -> None:
        """Test encoding simple request fixture."""
        encoded = encode(simple_get_request)

        assert b'"select"' in encoded
        assert b'"where"' in encoded
        assert b'"limit":25' in encoded

    def test_complex_request_to_dict(self, complex_search_request: APIRequest) -> None:
        """Test converting complex request to dict."""
        result = to_dict(complex_search_request)

        assert "select" in result
        assert "where" in result
        assert "orderBy" in result
        assert "join" in result
        assert len(result["where"]) == 3

    def test_create_request_values(self, create_request: APIRequest) -> None:
        """Test create request has correct values."""
        assert create_request.values is not None
        assert create_request.values["first_name"] == "John"
        assert create_request.values["contact_type"] == "Individual"

        result = to_dict(create_request)
        assert "values" in result
        assert "select" not in result


class TestAPIResponseFixtures:
    """Tests using pytest fixtures for common response patterns."""

    @pytest.fixture
    def success_response_data(self) -> bytes:
        """Create success response JSON fixture."""
        return b"""{
            "values": [
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "Jane Smith"}
            ],
            "count": 2,
            "countFetched": 2
        }"""

    @pytest.fixture
    def error_response_data(self) -> bytes:
        """Create error response JSON fixture."""
        return b"""{
            "error_code": "authorization_failed",
            "error_message": "API key is not valid for this site"
        }"""

    @pytest.fixture
    def paginated_response_data(self) -> bytes:
        """Create paginated response JSON fixture."""
        return b"""{
            "values": [{"id": 1}, {"id": 2}, {"id": 3}],
            "count": 100,
            "countFetched": 3
        }"""

    def test_decode_success_fixture(self, success_response_data: bytes) -> None:
        """Test decoding success response fixture."""
        response = decode_response(success_response_data)

        assert response.is_error is False
        assert len(response.values) == 2
        assert response.first["display_name"] == "John Doe"

    def test_decode_error_fixture(self, error_response_data: bytes) -> None:
        """Test decoding error response fixture."""
        response = decode_response(error_response_data)

        assert response.is_error is True
        assert response.error_code == "authorization_failed"
        assert "API key" in response.error_message

    def test_decode_paginated_fixture(self, paginated_response_data: bytes) -> None:
        """Test decoding paginated response fixture."""
        response = decode_response(paginated_response_data)

        assert response.is_error is False
        assert response.count == 100
        assert response.countFetched == 3
        assert len(response.values) == 3
