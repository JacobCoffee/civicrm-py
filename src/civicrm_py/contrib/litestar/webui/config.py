"""Configuration for Litestar Web UI.

Provides configuration dataclass for the Web UI with settings
for theming, features, display options, and authentication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from litestar.types import Guard


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
        require_auth: Require authentication for Web UI access (default True).
        guards: Custom Litestar guards for authentication. If None and require_auth
            is True, uses default session-based auth guard.
        auth_exclude_paths: Paths to exclude from authentication (e.g., static files).

    Example:
        >>> config = WebUIConfig(
        ...     title="My CiviCRM Explorer",
        ...     theme="dark",
        ...     enable_playground=True,
        ...     default_entities=["Contact", "Activity"],
        ... )

        With custom auth guard:
        >>> from litestar.connection import ASGIConnection
        >>> from litestar.handlers import BaseRouteHandler
        >>>
        >>> async def my_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
        ...     if not connection.user:
        ...         raise NotAuthorizedException()
        >>>
        >>> config = WebUIConfig(guards=[my_guard])
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
    require_auth: bool = True
    guards: Sequence[Guard] | None = None
    auth_exclude_paths: list[str] = field(default_factory=lambda: ["/static"])
    debug: bool = False  # When True, skips auth with warning


__all__ = ["WebUIConfig"]
