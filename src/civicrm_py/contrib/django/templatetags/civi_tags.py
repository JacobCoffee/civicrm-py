"""Django template tags for CiviCRM data display.

This module provides template tags and filters for rendering CiviCRM data
in Django templates. It requires the Django middleware to be configured
to provide request.civi_client.

Simple Tags:
    - {% civi_contact id=1 as contact %} - fetch a contact by ID
    - {% civi_contacts filter="is_deleted=False" limit=10 as contacts %} - fetch multiple contacts
    - {% civi_entity "Activity" id=5 as activity %} - fetch any entity by name and ID

Inclusion Tags:
    - {% civi_contact_card contact %} - render a contact card
    - {% civi_contact_list contacts %} - render a list of contacts

Filters:
    - {{ contact|civi_field:"email_primary.email" }} - access nested fields safely
    - {{ contact|civi_format_date:"modified_date" }} - format CiviCRM dates
    - {{ amount|civi_format_currency }} - format currency values

Example:
    {% load civi_tags %}

    {% civi_contact id=request.user.civicrm_contact_id as contact %}
    <h1>{{ contact.display_name }}</h1>
    <p>Email: {{ contact|civi_field:"email_primary.email" }}</p>

    {% civi_contacts filter="contact_type=Individual" limit=5 as contacts %}
    {% civi_contact_list contacts %}
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django import template
from django.utils.safestring import mark_safe

if TYPE_CHECKING:
    from django.http import HttpRequest

    from civicrm_py.core.client import SyncCiviClient
    from civicrm_py.entities.base import BaseEntity

logger = logging.getLogger(__name__)
register = template.Library()


# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------


def _get_client_from_context(context: dict[str, Any]) -> SyncCiviClient | None:
    """Extract CiviCRM client from template context.

    Looks for the client in the following locations:
    1. context['request'].civi_client (set by middleware)
    2. context['civi_client'] (manually passed)

    Args:
        context: Django template context dictionary.

    Returns:
        SyncCiviClient instance or None if not found.
    """
    # Try request.civi_client (middleware pattern)
    request: HttpRequest | None = context.get("request")
    if request is not None:
        client = getattr(request, "civi_client", None)
        if client is not None:
            return client

    # Try direct context
    return context.get("civi_client")


def _parse_filter_string(filter_string: str) -> dict[str, Any]:
    """Parse a filter string into a dictionary of filter parameters.

    Supports:
    - Simple equality: "field=value"
    - Multiple filters: "field1=value1,field2=value2"
    - Quoted values: 'field="value with spaces"'
    - Boolean values: "is_deleted=False"
    - Numeric values: "id=123"

    Args:
        filter_string: Filter specification string.

    Returns:
        Dictionary of filter parameters.

    Example:
        >>> _parse_filter_string("is_deleted=False,contact_type=Individual")
        {'is_deleted': False, 'contact_type': 'Individual'}
    """
    if not filter_string:
        return {}

    filters: dict[str, Any] = {}

    # Split on comma, but respect quoted values
    # This regex handles "key=value" patterns, including quoted strings
    pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)=(?:"([^"]*)"|\'([^\']*)\'|([^,]*))'
    matches = re.findall(pattern, filter_string)

    for match in matches:
        key = match[0]
        # Value is in one of the capture groups (double-quoted, single-quoted, or unquoted)
        value: Any = match[1] or match[2] or match[3]
        value = value.strip()

        # Type coercion
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.lower() in ("none", "null"):
            value = None
        else:
            # Try numeric conversion (keep as string if conversion fails)
            with contextlib.suppress(ValueError):
                value = float(value) if "." in value else int(value)

        filters[key] = value

    return filters


def _get_nested_field(
    obj: Any,
    field_path: str,
    default: Any = None,
) -> Any:
    """Safely access nested fields on an object or dictionary.

    Supports:
    - Object attribute access: obj.field
    - Dictionary key access: obj['field']
    - Dot notation for nesting: obj.related.field
    - CiviCRM API joined fields: obj['email_primary.email']

    Args:
        obj: Object or dictionary to access.
        field_path: Dot-separated field path.
        default: Default value if field not found.

    Returns:
        Field value or default.

    Example:
        >>> _get_nested_field(contact, "email_primary.email")
        'john@example.com'
    """
    if obj is None:
        return default

    # First try direct access (for CiviCRM joined fields like "email_primary.email")
    if isinstance(obj, dict) and field_path in obj:
        return obj[field_path]
    if hasattr(obj, field_path):
        return getattr(obj, field_path)

    # Then try nested access
    parts = field_path.split(".")
    current = obj

    for part in parts:
        if current is None:
            return default

        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return default

    return current if current is not None else default


# -----------------------------------------------------------------------------
# Simple Tags
# -----------------------------------------------------------------------------


@register.simple_tag(takes_context=True)
def civi_contact(
    context: dict[str, Any],
    *,
    id: int | None = None,  # noqa: A002 - Django template tag convention
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Fetch a single contact by ID.

    Usage:
        {% civi_contact id=1 as contact %}
        {% civi_contact id=request.user.civicrm_contact_id as contact %}

    Args:
        context: Template context (automatic).
        id: Contact ID to fetch.
        **kwargs: Additional filter parameters.

    Returns:
        Contact dictionary or None if not found.
    """
    if id is None and not kwargs:
        logger.warning("civi_contact: No id or filters provided")
        return None

    client = _get_client_from_context(context)
    if client is None:
        logger.warning("civi_contact: No CiviCRM client available in context")
        return None

    try:
        where = []
        if id is not None:
            where.append(["id", "=", id])
        for key, value in kwargs.items():
            where.append([key, "=", value])

        response = client.get("Contact", where=where, limit=1)
    except Exception:
        logger.exception("civi_contact: Failed to fetch contact id=%s", id)
        return None
    else:
        return response.values[0] if response.values else None


@register.simple_tag(takes_context=True)
def civi_contacts(
    context: dict[str, Any],
    *,
    filter: str = "",  # noqa: A002 - Django template tag convention
    limit: int = 25,
    offset: int = 0,
    order_by: str = "",
    select: str = "",
) -> list[dict[str, Any]]:
    """Fetch multiple contacts with filtering.

    Usage:
        {% civi_contacts filter="is_deleted=False" limit=10 as contacts %}
        {% civi_contacts filter="contact_type=Individual,is_deleted=False" limit=5 order_by="-created_date" as contacts %}

    Args:
        context: Template context (automatic).
        filter: Filter string (e.g., "is_deleted=False,contact_type=Individual").
        limit: Maximum number of contacts to return.
        offset: Number of contacts to skip.
        order_by: Sort order (prefix with - for descending).
        select: Comma-separated fields to select.

    Returns:
        List of contact dictionaries.
    """
    client = _get_client_from_context(context)
    if client is None:
        logger.warning("civi_contacts: No CiviCRM client available in context")
        return []

    try:
        # Parse filter string
        filters = _parse_filter_string(filter)

        # Build where clause
        where = [[key, "=", value] for key, value in filters.items()] if filters else None

        # Parse order_by
        order_by_dict = None
        if order_by:
            order_by_dict = {}
            for raw_field in order_by.split(","):
                stripped_field = raw_field.strip()
                if stripped_field.startswith("-"):
                    order_by_dict[stripped_field[1:]] = "DESC"
                else:
                    order_by_dict[stripped_field] = "ASC"

        # Parse select
        select_list = [s.strip() for s in select.split(",") if s.strip()] if select else None

        response = client.get(
            "Contact",
            where=where,
            limit=limit,
            offset=offset,
            order_by=order_by_dict,
            select=select_list,
        )
    except Exception:
        logger.exception("civi_contacts: Failed to fetch contacts")
        return []
    else:
        return response.values or []


@register.simple_tag(takes_context=True)
def civi_entity(
    context: dict[str, Any],
    entity_name: str,
    *,
    id: int | None = None,  # noqa: A002 - Django template tag convention
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Fetch any CiviCRM entity by name and ID.

    Usage:
        {% civi_entity "Activity" id=5 as activity %}
        {% civi_entity "Contribution" id=100 as contribution %}
        {% civi_entity "Contact" email="john@example.com" as contact %}

    Args:
        context: Template context (automatic).
        entity_name: CiviCRM entity name (e.g., "Activity", "Contact", "Contribution").
        id: Entity ID to fetch.
        **kwargs: Additional filter parameters.

    Returns:
        Entity dictionary or None if not found.
    """
    if not entity_name:
        logger.warning("civi_entity: No entity_name provided")
        return None

    if id is None and not kwargs:
        logger.warning("civi_entity: No id or filters provided for %s", entity_name)
        return None

    client = _get_client_from_context(context)
    if client is None:
        logger.warning("civi_entity: No CiviCRM client available in context")
        return None

    try:
        where = []
        if id is not None:
            where.append(["id", "=", id])
        for key, value in kwargs.items():
            where.append([key, "=", value])

        response = client.get(entity_name, where=where, limit=1)
    except Exception:
        logger.exception("civi_entity: Failed to fetch %s id=%s", entity_name, id)
        return None
    else:
        return response.values[0] if response.values else None


@register.simple_tag(takes_context=True)
def civi_entities(
    context: dict[str, Any],
    entity_name: str,
    *,
    filter: str = "",  # noqa: A002 - Django template tag convention
    limit: int = 25,
    offset: int = 0,
    order_by: str = "",
    select: str = "",
) -> list[dict[str, Any]]:
    """Fetch multiple entities of any type with filtering.

    Usage:
        {% civi_entities "Activity" filter="is_deleted=False" limit=10 as activities %}
        {% civi_entities "Contribution" filter="contact_id=1" order_by="-receive_date" as contributions %}

    Args:
        context: Template context (automatic).
        entity_name: CiviCRM entity name (e.g., "Activity", "Contribution").
        filter: Filter string (e.g., "is_deleted=False").
        limit: Maximum number of entities to return.
        offset: Number of entities to skip.
        order_by: Sort order (prefix with - for descending).
        select: Comma-separated fields to select.

    Returns:
        List of entity dictionaries.
    """
    if not entity_name:
        logger.warning("civi_entities: No entity_name provided")
        return []

    client = _get_client_from_context(context)
    if client is None:
        logger.warning("civi_entities: No CiviCRM client available in context")
        return []

    try:
        # Parse filter string
        filters = _parse_filter_string(filter)

        # Build where clause
        where = [[key, "=", value] for key, value in filters.items()] if filters else None

        # Parse order_by
        order_by_dict = None
        if order_by:
            order_by_dict = {}
            for raw_field in order_by.split(","):
                stripped_field = raw_field.strip()
                if stripped_field.startswith("-"):
                    order_by_dict[stripped_field[1:]] = "DESC"
                else:
                    order_by_dict[stripped_field] = "ASC"

        # Parse select
        select_list = [s.strip() for s in select.split(",") if s.strip()] if select else None

        response = client.get(
            entity_name,
            where=where,
            limit=limit,
            offset=offset,
            order_by=order_by_dict,
            select=select_list,
        )
    except Exception:
        logger.exception("civi_entities: Failed to fetch %s entities", entity_name)
        return []
    else:
        return response.values or []


# -----------------------------------------------------------------------------
# Inclusion Tags
# -----------------------------------------------------------------------------


@register.inclusion_tag("civicrm_py/contact_card.html")
def civi_contact_card(
    contact: dict[str, Any] | BaseEntity | None,
    *,
    show_email: bool = True,
    show_phone: bool = True,
    show_address: bool = False,
    css_class: str = "",
) -> dict[str, Any]:
    """Render a contact card using an inclusion template.

    Usage:
        {% civi_contact_card contact %}
        {% civi_contact_card contact show_email=True show_phone=False %}
        {% civi_contact_card contact css_class="my-card-class" %}

    Args:
        contact: Contact dictionary or entity object.
        show_email: Whether to display email.
        show_phone: Whether to display phone.
        show_address: Whether to display address.
        css_class: Additional CSS class for the card.

    Returns:
        Context dictionary for the inclusion template.
    """
    if contact is None:
        return {
            "contact": None,
            "show_email": show_email,
            "show_phone": show_phone,
            "show_address": show_address,
            "css_class": css_class,
        }

    # Convert entity to dict if needed
    if hasattr(contact, "to_dict"):
        contact_data = contact.to_dict()
    elif isinstance(contact, dict):
        contact_data = contact
    else:
        contact_data = {}

    return {
        "contact": contact_data,
        "show_email": show_email,
        "show_phone": show_phone,
        "show_address": show_address,
        "css_class": css_class,
    }


@register.inclusion_tag("civicrm_py/contact_list.html")
def civi_contact_list(
    contacts: list[dict[str, Any] | BaseEntity] | None,
    *,
    show_email: bool = True,
    show_type: bool = True,
    css_class: str = "",
    empty_message: str = "No contacts found.",
) -> dict[str, Any]:
    """Render a list of contacts using an inclusion template.

    Usage:
        {% civi_contact_list contacts %}
        {% civi_contact_list contacts show_email=False %}
        {% civi_contact_list contacts css_class="my-list" empty_message="Nothing here" %}

    Args:
        contacts: List of contact dictionaries or entity objects.
        show_email: Whether to display email for each contact.
        show_type: Whether to display contact type.
        css_class: Additional CSS class for the list.
        empty_message: Message to display when list is empty.

    Returns:
        Context dictionary for the inclusion template.
    """
    if contacts is None:
        contacts = []

    # Convert entities to dicts if needed
    contact_list = []
    for contact in contacts:
        if hasattr(contact, "to_dict"):
            contact_list.append(contact.to_dict())
        elif isinstance(contact, dict):
            contact_list.append(contact)

    return {
        "contacts": contact_list,
        "show_email": show_email,
        "show_type": show_type,
        "css_class": css_class,
        "empty_message": empty_message,
    }


# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------


@register.filter(name="civi_field")
def civi_field(obj: Any, field_path: str) -> Any:
    """Safely access nested fields on a CiviCRM entity or dictionary.

    Supports dot notation for nested access and handles CiviCRM's joined
    field naming convention (e.g., "email_primary.email").

    Usage:
        {{ contact|civi_field:"email_primary.email" }}
        {{ contact|civi_field:"display_name" }}
        {{ activity|civi_field:"source_contact.display_name" }}

    Args:
        obj: Entity object or dictionary.
        field_path: Dot-separated field path.

    Returns:
        Field value or empty string if not found.
    """
    return _get_nested_field(obj, field_path, default="")


@register.filter(name="civi_format_date")
def civi_format_date(
    obj: Any,
    field_or_format: str = "%Y-%m-%d %H:%M",
) -> str:
    """Format a CiviCRM date field.

    If obj is a string (date value), formats it directly.
    If obj is a dict/entity and field_or_format contains a dot, treats it as a field path.
    Otherwise, treats field_or_format as a strftime format string.

    Usage:
        {{ contact.modified_date|civi_format_date }}
        {{ contact.modified_date|civi_format_date:"%B %d, %Y" }}
        {{ contact|civi_format_date:"created_date" }}

    Args:
        obj: Date string, or entity/dict containing the date field.
        field_or_format: Either a field path or a strftime format string.

    Returns:
        Formatted date string or empty string on error.
    """
    # Determine if we're working with a date value or need to extract it
    date_value: str | None = None
    date_format = "%Y-%m-%d %H:%M"

    if isinstance(obj, str):
        # obj is the date value itself
        date_value = obj
        # field_or_format is the format string
        if field_or_format and "." not in field_or_format and "_" not in field_or_format:
            date_format = field_or_format
    elif isinstance(obj, dict) or hasattr(obj, "__dict__"):
        # obj is an entity/dict, extract the field
        # Check if field_or_format looks like a field name (contains underscore or dot)
        if "_" in field_or_format or "." in field_or_format:
            date_value = _get_nested_field(obj, field_or_format)
        else:
            # It's a format string, but we don't have a field path
            # This shouldn't happen in normal usage
            return ""

    if not date_value:
        return ""

    # Parse CiviCRM date formats (datetime, date only, ISO format)
    civicrm_date_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in civicrm_date_formats:
        try:
            dt = datetime.strptime(date_value, fmt)  # noqa: DTZ007 - CiviCRM dates are naive
            return dt.strftime(date_format)
        except ValueError:
            continue

    # If none of the formats match, return the original
    return date_value


@register.filter(name="civi_format_currency")
def civi_format_currency(
    amount: float | str | Decimal | None,
    currency: str = "USD",
) -> str:
    """Format a numeric value as currency.

    Usage:
        {{ contribution.total_amount|civi_format_currency }}
        {{ contribution.total_amount|civi_format_currency:"EUR" }}
        {{ 1234.56|civi_format_currency }}

    Args:
        amount: Numeric value to format.
        currency: Currency code (default: USD).

    Returns:
        Formatted currency string.
    """
    if amount is None:
        return ""

    try:
        # Convert to Decimal for precise formatting
        if isinstance(amount, str):
            amount = Decimal(amount)
        elif isinstance(amount, (int, float)):
            amount = Decimal(str(amount))

        # Currency symbols
        symbols = {
            "USD": "$",
            "EUR": "\u20ac",
            "GBP": "\u00a3",
            "CAD": "C$",
            "AUD": "A$",
            "JPY": "\u00a5",
            "CNY": "\u00a5",
            "INR": "\u20b9",
            "BRL": "R$",
            "MXN": "MX$",
        }

        symbol = symbols.get(currency.upper(), currency + " ")

        # Format with two decimal places and thousands separator
        formatted = f"{amount:,.2f}"
    except Exception:
        logger.exception("civi_format_currency: Failed to format amount")
        return str(amount) if amount else ""
    else:
        return f"{symbol}{formatted}"


@register.filter(name="civi_contact_type_label")
def civi_contact_type_label(contact_type: str | None) -> str:
    """Convert contact type to a human-readable label.

    Usage:
        {{ contact.contact_type|civi_contact_type_label }}

    Args:
        contact_type: CiviCRM contact type string.

    Returns:
        Human-readable label.
    """
    if not contact_type:
        return ""

    labels = {
        "Individual": "Person",
        "Organization": "Organization",
        "Household": "Household",
    }
    return labels.get(contact_type, contact_type)


@register.filter(name="civi_bool_icon")
def civi_bool_icon(value: bool | None) -> str:
    """Convert boolean value to an icon/symbol.

    Usage:
        {{ contact.is_deleted|civi_bool_icon }}

    Args:
        value: Boolean value.

    Returns:
        HTML-safe icon string.
    """
    if value is None:
        return mark_safe('<span class="civi-bool civi-bool-unknown">-</span>')
    if value:
        return mark_safe('<span class="civi-bool civi-bool-true">&#10003;</span>')
    return mark_safe('<span class="civi-bool civi-bool-false">&#10007;</span>')


@register.filter(name="civi_truncate")
def civi_truncate(value: str | None, length: int = 50) -> str:
    """Truncate text to a maximum length with ellipsis.

    Usage:
        {{ contact.details|civi_truncate:100 }}

    Args:
        value: Text to truncate.
        length: Maximum length (default: 50).

    Returns:
        Truncated text with ellipsis if needed.
    """
    if not value:
        return ""
    if len(value) <= length:
        return value
    return value[: length - 3] + "..."


@register.filter(name="get_attr")
def get_attr(obj: Any, attr: str) -> Any:
    """Get an attribute from an object or dictionary.

    Supports dot notation for nested access and handles CiviCRM's joined
    field naming convention (e.g., "email_primary.email").

    Usage:
        {{ contact|get_attr:"email_primary.email" }}
        {{ contact|get_attr:"status_id:label" }}

    Args:
        obj: Entity object or dictionary.
        attr: Attribute name (can use dot notation).

    Returns:
        Attribute value or None if not found.
    """
    return _get_nested_field(obj, attr, default=None)


@register.filter(name="make_range")
def make_range(value: int) -> range:
    """Create a range from 1 to value (inclusive).

    Useful for pagination templates.

    Usage:
        {% for p in result.pages|make_range %}

    Args:
        value: Upper bound (inclusive).

    Returns:
        Range from 1 to value.
    """
    if not value or value < 1:
        return range(0)
    return range(1, value + 1)


# -----------------------------------------------------------------------------
# Block Tags
# -----------------------------------------------------------------------------


class CiviWithClientNode(template.Node):
    """Template node for civi_with_client block tag.

    Provides access to the CiviCRM client within a block, useful for
    templates that need to make multiple API calls.
    """

    def __init__(
        self,
        nodelist: template.NodeList,
        var_name: str,
    ) -> None:
        """Initialize the node.

        Args:
            nodelist: Template nodes within the block.
            var_name: Variable name to store the client.
        """
        self.nodelist = nodelist
        self.var_name = var_name

    def render(self, context: template.Context) -> str:
        """Render the block with client available.

        Args:
            context: Template context.

        Returns:
            Rendered content.
        """
        client = _get_client_from_context(context.flatten())

        with context.push():
            context[self.var_name] = client
            return self.nodelist.render(context)


@register.tag(name="civi_with_client")
def do_civi_with_client(parser: template.Parser, token: template.Token) -> CiviWithClientNode:
    """Block tag to access the CiviCRM client.

    Usage:
        {% civi_with_client as client %}
            ... use client directly for advanced operations ...
        {% endcivi_with_client %}

    Args:
        parser: Template parser.
        token: Template token.

    Returns:
        CiviWithClientNode instance.

    Raises:
        TemplateSyntaxError: If syntax is invalid.
    """
    expected_parts = 3  # tag_name, "as", var_name
    bits = token.split_contents()
    if len(bits) != expected_parts or bits[1] != "as":
        msg = f"{bits[0]} tag requires syntax: {{% {bits[0]} as varname %}}"
        raise template.TemplateSyntaxError(msg)

    var_name = bits[2]
    nodelist = parser.parse(("endcivi_with_client",))
    parser.delete_first_token()

    return CiviWithClientNode(nodelist, var_name)


# -----------------------------------------------------------------------------
# Context Processor (for use with Django settings)
# -----------------------------------------------------------------------------


def civi_context_processor(request: HttpRequest) -> dict[str, Any]:
    """Django context processor for CiviCRM data.

    Add this to TEMPLATES['OPTIONS']['context_processors'] in Django settings
    to automatically include CiviCRM utilities in all template contexts.

    Provides:
        - civi_client: The CiviCRM client (if available on request)
        - civi_connected: Boolean indicating if client is available

    Args:
        request: Django HttpRequest.

    Returns:
        Context dictionary with CiviCRM utilities.
    """
    client = getattr(request, "civi_client", None)
    return {
        "civi_client": client,
        "civi_connected": client is not None,
    }


# =============================================================================
# Web UI Filters
# =============================================================================


@register.filter
def to_json(value: dict | list) -> str:
    """Convert a value to formatted JSON string.

    Usage: {{ item|to_json }}
    """
    import json

    return json.dumps(value, indent=2, default=str)
