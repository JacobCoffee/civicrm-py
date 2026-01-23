"""Tests for Django template tags and filters.

This module tests the template tags, filters, and utility functions
defined in civi_py.contrib.django.templatetags.civi_tags.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from civi_py.contrib.django.templatetags.civi_tags import (
    _get_client_from_context,
    _get_nested_field,
    _parse_filter_string,
    civi_bool_icon,
    civi_contact,
    civi_contact_card,
    civi_contact_list,
    civi_contact_type_label,
    civi_contacts,
    civi_entities,
    civi_entity,
    civi_field,
    civi_format_currency,
    civi_format_date,
    civi_truncate,
)

# -----------------------------------------------------------------------------
# Utility Function Tests
# -----------------------------------------------------------------------------


class TestParseFilterString:
    """Tests for _parse_filter_string utility function."""

    def test_empty_string(self) -> None:
        """Test parsing empty string returns empty dict."""
        result = _parse_filter_string("")
        assert result == {}

    def test_single_filter(self) -> None:
        """Test parsing single filter."""
        result = _parse_filter_string("is_deleted=False")
        assert result == {"is_deleted": False}

    def test_multiple_filters(self) -> None:
        """Test parsing multiple filters."""
        result = _parse_filter_string("is_deleted=False,contact_type=Individual")
        assert result == {"is_deleted": False, "contact_type": "Individual"}

    def test_boolean_true(self) -> None:
        """Test parsing boolean True value."""
        result = _parse_filter_string("is_active=True")
        assert result == {"is_active": True}

    def test_boolean_false(self) -> None:
        """Test parsing boolean False value."""
        result = _parse_filter_string("is_deleted=false")
        assert result == {"is_deleted": False}

    def test_integer_value(self) -> None:
        """Test parsing integer value."""
        result = _parse_filter_string("id=123")
        assert result == {"id": 123}

    def test_float_value(self) -> None:
        """Test parsing float value."""
        result = _parse_filter_string("amount=123.45")
        assert result == {"amount": 123.45}

    def test_none_value(self) -> None:
        """Test parsing None/null values."""
        result = _parse_filter_string("field=None")
        assert result == {"field": None}

        result = _parse_filter_string("field=null")
        assert result == {"field": None}

    def test_quoted_value_double(self) -> None:
        """Test parsing double-quoted value."""
        result = _parse_filter_string('name="John Doe"')
        assert result == {"name": "John Doe"}

    def test_quoted_value_single(self) -> None:
        """Test parsing single-quoted value."""
        result = _parse_filter_string("name='Jane Smith'")
        assert result == {"name": "Jane Smith"}


class TestGetNestedField:
    """Tests for _get_nested_field utility function."""

    def test_dict_simple_field(self) -> None:
        """Test accessing simple field on dict."""
        obj = {"name": "John"}
        assert _get_nested_field(obj, "name") == "John"

    def test_dict_nested_field(self) -> None:
        """Test accessing nested field on dict."""
        obj = {"contact": {"email": "john@example.com"}}
        assert _get_nested_field(obj, "contact.email") == "john@example.com"

    def test_dict_civicrm_joined_field(self) -> None:
        """Test accessing CiviCRM-style joined field."""
        obj = {"email_primary.email": "john@example.com"}
        assert _get_nested_field(obj, "email_primary.email") == "john@example.com"

    def test_object_attribute(self) -> None:
        """Test accessing object attribute."""
        obj = MagicMock()
        obj.name = "John"
        assert _get_nested_field(obj, "name") == "John"

    def test_default_value(self) -> None:
        """Test default value for missing field."""
        obj = {"name": "John"}
        assert _get_nested_field(obj, "email", default="N/A") == "N/A"

    def test_none_object(self) -> None:
        """Test handling None object."""
        assert _get_nested_field(None, "field") is None
        assert _get_nested_field(None, "field", default="N/A") == "N/A"


class TestGetClientFromContext:
    """Tests for _get_client_from_context utility function."""

    def test_client_from_request(self) -> None:
        """Test getting client from request.civi_client."""
        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = _get_client_from_context(context)
        assert result is mock_client

    def test_client_from_direct_context(self) -> None:
        """Test getting client directly from context."""
        mock_client = MagicMock()
        context = {"civi_client": mock_client}
        result = _get_client_from_context(context)
        assert result is mock_client

    def test_no_client_available(self) -> None:
        """Test returning None when no client available."""
        context: dict[str, Any] = {}
        result = _get_client_from_context(context)
        assert result is None

    def test_request_without_client(self) -> None:
        """Test handling request without civi_client attribute."""
        mock_request = MagicMock(spec=[])  # No civi_client attribute
        context = {"request": mock_request}
        result = _get_client_from_context(context)
        assert result is None


# -----------------------------------------------------------------------------
# Filter Tests
# -----------------------------------------------------------------------------


class TestCiviFieldFilter:
    """Tests for civi_field template filter."""

    def test_simple_field(self) -> None:
        """Test accessing simple field."""
        contact = {"display_name": "John Doe"}
        assert civi_field(contact, "display_name") == "John Doe"

    def test_nested_field(self) -> None:
        """Test accessing nested field."""
        contact = {"email_primary.email": "john@example.com"}
        assert civi_field(contact, "email_primary.email") == "john@example.com"

    def test_missing_field(self) -> None:
        """Test missing field returns empty string."""
        contact = {"name": "John"}
        assert civi_field(contact, "email") == ""

    def test_none_object(self) -> None:
        """Test None object returns empty string."""
        assert civi_field(None, "field") == ""


class TestCiviFormatDateFilter:
    """Tests for civi_format_date template filter."""

    def test_datetime_format(self) -> None:
        """Test formatting datetime string."""
        result = civi_format_date("2024-01-15 10:30:00", "%Y-%m-%d")
        assert result == "2024-01-15"

    def test_date_only_format(self) -> None:
        """Test formatting date-only string."""
        result = civi_format_date("2024-01-15", "%B %d, %Y")
        assert result == "January 15, 2024"

    def test_iso_format(self) -> None:
        """Test formatting ISO datetime string."""
        result = civi_format_date("2024-01-15T10:30:00", "%Y-%m-%d %H:%M")
        assert result == "2024-01-15 10:30"

    def test_empty_value(self) -> None:
        """Test empty value returns empty string."""
        assert civi_format_date("") == ""

    def test_none_value(self) -> None:
        """Test None value returns empty string."""
        assert civi_format_date(None) == ""  # type: ignore[arg-type]

    def test_field_extraction_from_dict(self) -> None:
        """Test extracting and formatting field from dict."""
        contact = {"created_date": "2024-01-15 10:30:00"}
        result = civi_format_date(contact, "created_date")
        # Should return the date with default format
        assert "2024-01-15" in result


class TestCiviFormatCurrencyFilter:
    """Tests for civi_format_currency template filter."""

    def test_usd_format(self) -> None:
        """Test USD formatting."""
        result = civi_format_currency(1234.56, "USD")
        assert result == "$1,234.56"

    def test_eur_format(self) -> None:
        """Test EUR formatting."""
        result = civi_format_currency(1234.56, "EUR")
        assert "\u20ac1,234.56" in result

    def test_integer_amount(self) -> None:
        """Test formatting integer amount."""
        result = civi_format_currency(100, "USD")
        assert result == "$100.00"

    def test_string_amount(self) -> None:
        """Test formatting string amount."""
        result = civi_format_currency("99.99", "USD")
        assert result == "$99.99"

    def test_decimal_amount(self) -> None:
        """Test formatting Decimal amount."""
        result = civi_format_currency(Decimal("199.99"), "USD")
        assert result == "$199.99"

    def test_none_amount(self) -> None:
        """Test None amount returns empty string."""
        assert civi_format_currency(None) == ""

    def test_large_amount(self) -> None:
        """Test formatting large amount with thousands separator."""
        result = civi_format_currency(1234567.89, "USD")
        assert result == "$1,234,567.89"

    def test_unknown_currency(self) -> None:
        """Test unknown currency uses code as prefix."""
        result = civi_format_currency(100, "XYZ")
        assert "XYZ" in result
        assert "100.00" in result


class TestCiviContactTypeLabelFilter:
    """Tests for civi_contact_type_label template filter."""

    def test_individual(self) -> None:
        """Test Individual label."""
        assert civi_contact_type_label("Individual") == "Person"

    def test_organization(self) -> None:
        """Test Organization label."""
        assert civi_contact_type_label("Organization") == "Organization"

    def test_household(self) -> None:
        """Test Household label."""
        assert civi_contact_type_label("Household") == "Household"

    def test_unknown(self) -> None:
        """Test unknown type returns original."""
        assert civi_contact_type_label("Custom") == "Custom"

    def test_empty(self) -> None:
        """Test empty string returns empty."""
        assert civi_contact_type_label("") == ""

    def test_none(self) -> None:
        """Test None returns empty."""
        assert civi_contact_type_label(None) == ""


class TestCiviBoolIconFilter:
    """Tests for civi_bool_icon template filter."""

    def test_true_value(self) -> None:
        """Test True value shows checkmark."""
        result = civi_bool_icon(True)
        assert "civi-bool-true" in result
        assert "&#10003;" in result  # Checkmark

    def test_false_value(self) -> None:
        """Test False value shows X."""
        result = civi_bool_icon(False)
        assert "civi-bool-false" in result
        assert "&#10007;" in result  # X mark

    def test_none_value(self) -> None:
        """Test None value shows dash."""
        result = civi_bool_icon(None)
        assert "civi-bool-unknown" in result
        assert "-" in result


class TestCiviTruncateFilter:
    """Tests for civi_truncate template filter."""

    def test_short_text(self) -> None:
        """Test short text unchanged."""
        assert civi_truncate("Hello", 10) == "Hello"

    def test_long_text(self) -> None:
        """Test long text truncated with ellipsis."""
        result = civi_truncate("This is a very long text", 15)
        assert result == "This is a ve..."
        assert len(result) == 15

    def test_exact_length(self) -> None:
        """Test text at exact length unchanged."""
        text = "12345"
        assert civi_truncate(text, 5) == "12345"

    def test_empty_string(self) -> None:
        """Test empty string returns empty."""
        assert civi_truncate("") == ""

    def test_none_value(self) -> None:
        """Test None returns empty."""
        assert civi_truncate(None) == ""


# -----------------------------------------------------------------------------
# Simple Tag Tests
# -----------------------------------------------------------------------------


class TestCiviContactTag:
    """Tests for civi_contact simple tag."""

    def test_no_client_returns_none(self) -> None:
        """Test returns None when no client available."""
        context: dict[str, Any] = {}
        result = civi_contact(context, id=1)
        assert result is None

    def test_no_id_returns_none(self) -> None:
        """Test returns None when no id provided."""
        context: dict[str, Any] = {}
        result = civi_contact(context)
        assert result is None

    def test_successful_fetch(self) -> None:
        """Test successful contact fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [{"id": 1, "display_name": "John Doe"}]
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_contact(context, id=1)

        assert result == {"id": 1, "display_name": "John Doe"}
        mock_client.get.assert_called_once()

    def test_not_found_returns_none(self) -> None:
        """Test returns None when contact not found."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = []
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_contact(context, id=999)

        assert result is None

    def test_error_returns_none(self) -> None:
        """Test returns None on error."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("API Error")

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_contact(context, id=1)

        assert result is None


class TestCiviContactsTag:
    """Tests for civi_contacts simple tag."""

    def test_no_client_returns_empty(self) -> None:
        """Test returns empty list when no client available."""
        context: dict[str, Any] = {}
        result = civi_contacts(context)
        assert result == []

    def test_successful_fetch(self) -> None:
        """Test successful contacts fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [
            {"id": 1, "display_name": "John Doe"},
            {"id": 2, "display_name": "Jane Smith"},
        ]
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_contacts(context, limit=10)

        assert len(result) == 2
        mock_client.get.assert_called_once()

    def test_with_filter_string(self) -> None:
        """Test filtering with filter string."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [{"id": 1}]
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        civi_contacts(context, filter="is_deleted=False,contact_type=Individual")

        # Check that where clause was built correctly
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["where"] is not None
        assert len(call_kwargs["where"]) == 2

    def test_error_returns_empty(self) -> None:
        """Test returns empty list on error."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("API Error")

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_contacts(context)

        assert result == []


class TestCiviEntityTag:
    """Tests for civi_entity simple tag."""

    def test_no_entity_name_returns_none(self) -> None:
        """Test returns None when no entity name provided."""
        context: dict[str, Any] = {}
        result = civi_entity(context, "")
        assert result is None

    def test_successful_fetch(self) -> None:
        """Test successful entity fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [{"id": 5, "subject": "Test Activity"}]
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_entity(context, "Activity", id=5)

        assert result == {"id": 5, "subject": "Test Activity"}
        mock_client.get.assert_called_once_with("Activity", where=[["id", "=", 5]], limit=1)


class TestCiviEntitiesTag:
    """Tests for civi_entities simple tag."""

    def test_no_entity_name_returns_empty(self) -> None:
        """Test returns empty list when no entity name provided."""
        context: dict[str, Any] = {}
        result = civi_entities(context, "")
        assert result == []

    def test_successful_fetch(self) -> None:
        """Test successful entities fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.values = [
            {"id": 1, "subject": "Activity 1"},
            {"id": 2, "subject": "Activity 2"},
        ]
        mock_client.get.return_value = mock_response

        mock_request = MagicMock()
        mock_request.civi_client = mock_client

        context = {"request": mock_request}
        result = civi_entities(context, "Activity", limit=10)

        assert len(result) == 2


# -----------------------------------------------------------------------------
# Inclusion Tag Tests
# -----------------------------------------------------------------------------


class TestCiviContactCardTag:
    """Tests for civi_contact_card inclusion tag."""

    def test_with_contact(self) -> None:
        """Test context for contact card with contact."""
        contact = {"id": 1, "display_name": "John Doe", "email_primary": "john@example.com"}
        result = civi_contact_card(contact)

        assert result["contact"] == contact
        assert result["show_email"] is True
        assert result["show_phone"] is True
        assert result["show_address"] is False

    def test_without_contact(self) -> None:
        """Test context for contact card without contact."""
        result = civi_contact_card(None)

        assert result["contact"] is None

    def test_custom_options(self) -> None:
        """Test custom display options."""
        contact = {"id": 1}
        result = civi_contact_card(
            contact,
            show_email=False,
            show_phone=True,
            show_address=True,
            css_class="custom-class",
        )

        assert result["show_email"] is False
        assert result["show_phone"] is True
        assert result["show_address"] is True
        assert result["css_class"] == "custom-class"

    def test_entity_object_conversion(self) -> None:
        """Test entity object is converted to dict."""
        mock_entity = MagicMock()
        mock_entity.to_dict.return_value = {"id": 1, "display_name": "Test"}

        result = civi_contact_card(mock_entity)

        assert result["contact"] == {"id": 1, "display_name": "Test"}
        mock_entity.to_dict.assert_called_once()


class TestCiviContactListTag:
    """Tests for civi_contact_list inclusion tag."""

    def test_with_contacts(self) -> None:
        """Test context for contact list with contacts."""
        contacts = [
            {"id": 1, "display_name": "John Doe"},
            {"id": 2, "display_name": "Jane Smith"},
        ]
        result = civi_contact_list(contacts)

        assert len(result["contacts"]) == 2
        assert result["show_email"] is True
        assert result["show_type"] is True

    def test_empty_list(self) -> None:
        """Test context for empty contact list."""
        result = civi_contact_list([])

        assert result["contacts"] == []
        assert result["empty_message"] == "No contacts found."

    def test_none_list(self) -> None:
        """Test context for None contact list."""
        result = civi_contact_list(None)

        assert result["contacts"] == []

    def test_custom_options(self) -> None:
        """Test custom display options."""
        result = civi_contact_list(
            [],
            show_email=False,
            show_type=False,
            css_class="my-list",
            empty_message="Nothing here",
        )

        assert result["show_email"] is False
        assert result["show_type"] is False
        assert result["css_class"] == "my-list"
        assert result["empty_message"] == "Nothing here"

    def test_entity_objects_conversion(self) -> None:
        """Test entity objects are converted to dicts."""
        mock_entity1 = MagicMock()
        mock_entity1.to_dict.return_value = {"id": 1}
        mock_entity2 = MagicMock()
        mock_entity2.to_dict.return_value = {"id": 2}

        result = civi_contact_list([mock_entity1, mock_entity2])

        assert result["contacts"] == [{"id": 1}, {"id": 2}]
