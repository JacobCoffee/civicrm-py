"""Shared Web UI components for civi-py.

This module provides shared templates and utilities for the CiviCRM Web UI
that can be used by both Django and Litestar integrations.

The templates use a framework-agnostic `webui_url()` function for URL generation
that each framework injects into the template context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Path to shared templates
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Default entities to show in the Web UI
DEFAULT_ENTITIES = ["Contact", "Activity", "Contribution", "Event", "Membership", "Participant"]


@dataclass
class WebUIConfig:
    """Configuration for the CiviCRM Web UI.

    This configuration is shared between Django and Litestar integrations.

    Attributes:
        title: Title displayed in the UI header.
        theme: Color theme ('light', 'dark', or 'auto').
        enable_playground: Whether to show the API playground.
        enable_entity_browser: Whether to show the entity browser.
        enable_request_history: Whether to track query history in playground.
        default_entities: List of entity types to show by default.
        items_per_page: Number of items per page in entity lists.
        require_auth: Whether authentication is required.
        debug: Enable debug mode (bypasses auth with warning).

    Example:
        >>> config = WebUIConfig(
        ...     title="My CiviCRM Explorer",
        ...     theme="dark",
        ...     enable_playground=True,
        ... )
    """

    title: str = "CiviCRM Explorer"
    theme: str = "auto"
    enable_playground: bool = True
    enable_entity_browser: bool = True
    enable_request_history: bool = True
    default_entities: Sequence[str] = field(default_factory=lambda: list(DEFAULT_ENTITIES))
    items_per_page: int = 25
    require_auth: bool = True
    debug: bool = False


def get_template_context(
    config: WebUIConfig,
    current_page: str = "index",
    **extra: object,
) -> dict[str, object]:
    """Get base template context for Web UI pages.

    Args:
        config: Web UI configuration.
        current_page: Current page identifier for nav highlighting.
        **extra: Additional context variables.

    Returns:
        Dictionary of template context variables.
    """
    return {
        "title": config.title,
        "theme": config.theme,
        "enable_playground": config.enable_playground,
        "enable_entity_browser": config.enable_entity_browser,
        "enable_history": config.enable_request_history,
        "entities": config.default_entities,
        "current_page": current_page,
        **extra,
    }


__all__ = [
    "DEFAULT_ENTITIES",
    "TEMPLATES_DIR",
    "WebUIConfig",
    "get_template_context",
]
