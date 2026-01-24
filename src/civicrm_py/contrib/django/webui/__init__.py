"""Django Web UI for CiviCRM API exploration.

Provides an interactive web interface for browsing CiviCRM entities,
testing API queries, and exploring the API structure.

Example:
    In your Django settings.py, add the shared templates directory:

    >>> from civicrm_py.contrib.django.webui import TEMPLATES_DIR
    >>>
    >>> TEMPLATES = [
    ...     {
    ...         "BACKEND": "django.template.backends.django.DjangoTemplates",
    ...         "DIRS": [TEMPLATES_DIR],  # Add shared WebUI templates
    ...         ...
    ...     },
    ... ]

    In your Django urls.py:

    >>> from django.urls import include, path
    >>> from civicrm_py.contrib.django.webui import WebUIConfig, get_urlpatterns
    >>>
    >>> webui_config = WebUIConfig(
    ...     title="CiviCRM Explorer",
    ...     theme="auto",
    ... )
    >>>
    >>> urlpatterns = [
    ...     path("explorer/", include(get_urlpatterns(webui_config))),
    ... ]
"""

from __future__ import annotations

from civicrm_py.contrib.django.webui.config import WebUIConfig
from civicrm_py.contrib.django.webui.urls import get_urlpatterns
from civicrm_py.webui import TEMPLATES_DIR

__all__ = [
    "TEMPLATES_DIR",
    "WebUIConfig",
    "get_urlpatterns",
]
