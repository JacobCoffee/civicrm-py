"""Custom template tags for CiviCRM Web UI."""

from __future__ import annotations

import json

from django import template

register = template.Library()


@register.filter
def make_range(value: int) -> range:
    """Create a range from 1 to value (inclusive).

    Usage: {% for p in total_pages|make_range %}
    """
    return range(1, value + 1)


@register.filter
def to_json(value: dict | list) -> str:
    """Convert a value to formatted JSON string.

    Usage: {{ item|to_json }}
    """
    return json.dumps(value, indent=2, default=str)


@register.filter
def get_item(dictionary: dict, key: str) -> object:
    """Get an item from a dictionary by key.

    Usage: {{ mydict|get_item:"key" }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
