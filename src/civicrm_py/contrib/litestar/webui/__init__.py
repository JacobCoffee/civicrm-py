"""Litestar Web UI for CiviCRM API exploration.

Provides an interactive web interface for browsing CiviCRM entities,
testing API queries, and exploring the API structure.

Example:
    >>> from litestar import Litestar
    >>> from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    >>> from civicrm_py.contrib.litestar.webui import WebUIConfig
    >>>
    >>> config = CiviPluginConfig(
    ...     enable_webui=True,
    ...     webui_path="/explorer",
    ...     webui_config=WebUIConfig(
    ...         title="CiviCRM Explorer",
    ...         theme="auto",
    ...     ),
    ... )
    >>> app = Litestar(plugins=[CiviPlugin(config)])
"""

from __future__ import annotations

from civicrm_py.contrib.litestar.webui.config import WebUIConfig
from civicrm_py.contrib.litestar.webui.controllers import (
    EntityBrowserController,
    PlaygroundController,
    WebUIController,
    get_webui_controllers,
)

__all__ = [
    "EntityBrowserController",
    "PlaygroundController",
    "WebUIConfig",
    "WebUIController",
    "get_webui_controllers",
]
