"""Configuration for Django Web UI.

Provides configuration dataclass for the Web UI with settings
for theming, features, and display options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class WebUIConfig:
    """Configuration for the CiviCRM Web UI.

    Attributes:
        title: Title displayed in the Web UI header.
        theme: Color theme - "light", "dark", or "auto" (follows system).
        enable_playground: Show the API playground for testing queries.
        enable_entity_browser: Show the entity browser for exploring data.
        default_entities: Entities shown by default in the browser.
        items_per_page: Default pagination size for entity lists.
        enable_request_history: Store and display request history.
        max_history_items: Maximum request history entries to keep.
        require_staff: Require Django staff/superuser login (default True).
        login_url: URL to redirect to for login (default "/admin/login/").

    Example:
        >>> config = WebUIConfig(
        ...     title="My CiviCRM Explorer",
        ...     theme="dark",
        ...     enable_playground=True,
        ...     default_entities=["Contact", "Activity"],
        ... )
    """

    title: str = "CiviCRM Explorer"
    theme: Literal["light", "dark", "auto"] = "auto"
    enable_playground: bool = True
    enable_entity_browser: bool = True
    default_entities: list[str] = field(
        default_factory=lambda: ["Contact", "Activity", "Contribution", "Event"],
    )
    items_per_page: int = 25
    enable_request_history: bool = True
    max_history_items: int = 50
    require_staff: bool = True
    login_url: str = "/admin/login/"
    debug: bool = False  # When True, skips auth with warning (respects Django DEBUG setting)


__all__ = ["WebUIConfig"]
