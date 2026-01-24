"""URL patterns for Django Web UI.

Provides URL patterns for the interactive Web UI.
"""

from __future__ import annotations

from django.urls import path

from civicrm_py.contrib.django.webui.config import WebUIConfig
from civicrm_py.contrib.django.webui.views import (
    EntityBrowserView,
    EntityDetailView,
    EntityListView,
    PlaygroundExecuteView,
    PlaygroundView,
    WebUIIndexView,
)


def get_urlpatterns(config: WebUIConfig | None = None) -> list:
    """Get URL patterns for the Web UI.

    Args:
        config: Web UI configuration. Defaults to WebUIConfig().

    Returns:
        List of URL patterns for the Web UI.

    Example:
        >>> from django.urls import include, path
        >>> from civicrm_py.contrib.django.webui import WebUIConfig, get_urlpatterns
        >>>
        >>> urlpatterns = [
        ...     path("explorer/", include(get_urlpatterns(WebUIConfig()))),
        ... ]
    """
    cfg = config or WebUIConfig()

    return [
        path("", WebUIIndexView.as_view(config=cfg), name="civi_webui_index"),
        path("entities/", EntityBrowserView.as_view(config=cfg), name="civi_webui_entities"),
        path(
            "entities/<str:entity>/",
            EntityListView.as_view(config=cfg),
            name="civi_webui_entity_list",
        ),
        path(
            "entities/<str:entity>/<int:entity_id>/",
            EntityDetailView.as_view(config=cfg),
            name="civi_webui_entity_detail",
        ),
        path("playground/", PlaygroundView.as_view(config=cfg), name="civi_webui_playground"),
        path(
            "playground/execute/",
            PlaygroundExecuteView.as_view(config=cfg),
            name="civi_webui_execute",
        ),
    ]


__all__ = ["get_urlpatterns"]
