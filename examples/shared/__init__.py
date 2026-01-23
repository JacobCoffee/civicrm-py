"""Shared showcase services for civi-py examples.

Provides reusable services for demonstrating civi-py capabilities
across different framework examples (Django, Litestar, etc.).

Main Components:
    CiviShowcase: Async showcase service for ASGI frameworks
    SyncCiviShowcase: Sync showcase service for WSGI frameworks
    SampleDataGenerator: Generates sample CiviCRM data for demos
    PaginatedResult: Container for paginated query results
    DashboardStats: Statistics for dashboard overview
    GenerationResult: Result of sample data generation

Jinja2 Environment:
    create_jinja_env: Factory function to create configured Jinja2 environments
    URL_MAP: Mapping of route names to URL patterns
    get_attr: Filter for nested attribute/key access
    get_template_globals: Get template globals for a framework
    get_template_filters: Get template filters
"""

from __future__ import annotations

from examples.shared.jinja_env import (
    URL_MAP,
    create_jinja_env,
    get_attr,
    get_template_filters,
    get_template_globals,
)
from examples.shared.sample_data import GenerationResult, SampleDataGenerator
from examples.shared.showcase import (
    CiviShowcase,
    DashboardStats,
    PaginatedResult,
    SyncCiviShowcase,
)

__all__ = [
    "URL_MAP",
    "CiviShowcase",
    "DashboardStats",
    "GenerationResult",
    "PaginatedResult",
    "SampleDataGenerator",
    "SyncCiviShowcase",
    "create_jinja_env",
    "get_attr",
    "get_template_filters",
    "get_template_globals",
]
