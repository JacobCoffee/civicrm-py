"""Contrib module: framework integrations.

Provides base protocols and framework-specific integrations for civi-py:

Base Protocols:
    - IntegrationProtocol: Core interface for framework integrations
    - LifecycleHooks: Application startup/shutdown lifecycle management
    - RequestContext: Request-scoped dependency injection

ASGI Middleware:
    - CiviASGIMiddleware: Generic middleware for Starlette, FastAPI, Litestar, Quart
    - get_civi_client: Helper to retrieve client from ASGI scope

WSGI Middleware:
    - CiviWSGIMiddleware: Generic middleware for Flask, Bottle, Falcon, etc.
    - get_client_from_environ: Helper to retrieve client from WSGI environ

Framework Integrations:
    - django: Django ORM-style integration (sync)
    - litestar: Litestar plugin with dependency injection (async)

Example with ASGI middleware:
    >>> from starlette.applications import Starlette
    >>> from civicrm_py.contrib.asgi import CiviASGIMiddleware
    >>> app = Starlette(...)
    >>> app = CiviASGIMiddleware(app)

Example with WSGI middleware:
    >>> from flask import Flask
    >>> from civicrm_py.contrib.wsgi import CiviWSGIMiddleware
    >>> app = Flask(__name__)
    >>> app.wsgi_app = CiviWSGIMiddleware(app.wsgi_app)

Example with protocol:
    >>> from civicrm_py.contrib import IntegrationProtocol
    >>> class MyIntegration:
    ...     def get_client(self) -> CiviClient:
    ...         return CiviClient.from_env()
"""

from __future__ import annotations

from civicrm_py.contrib.asgi import (
    ASGIApplication,
    CiviASGIMiddleware,
    Message,
    Receive,
    Scope,
    Send,
    get_civi_client,
)
from civicrm_py.contrib.base import IntegrationProtocol, LifecycleHooks, RequestContext
from civicrm_py.contrib.integration import BaseIntegration
from civicrm_py.contrib.registry import (
    IntegrationRegistry,
    discover_integrations,
    get_integration,
    list_integrations,
    register_integration,
)
from civicrm_py.contrib.wsgi import CiviWSGIMiddleware, get_client_from_environ

__all__ = [
    "ASGIApplication",
    "BaseIntegration",
    "CiviASGIMiddleware",
    "CiviWSGIMiddleware",
    "IntegrationProtocol",
    "IntegrationRegistry",
    "LifecycleHooks",
    "Message",
    "Receive",
    "RequestContext",
    "Scope",
    "Send",
    "discover_integrations",
    "get_civi_client",
    "get_client_from_environ",
    "get_integration",
    "list_integrations",
    "register_integration",
]
