"""Shared Jinja2 environment setup for Django and Litestar examples.

This module provides a unified Jinja2 environment that works across both
Django and Litestar frameworks, enabling template sharing between examples.

Main Components:
    - create_jinja_env: Factory function to create configured Jinja2 environments
    - url_for: URL helper function that works with both frameworks
    - get_attr: Filter for nested attribute/key access (supports CiviCRM field syntax)
    - csrf_input: CSRF token input helper
    - URL_MAP: Mapping of route names to URL patterns

Example:
    from examples.shared.jinja_env import create_jinja_env

    # For Litestar
    env = create_jinja_env(templates_dir, framework='litestar')

    # For Django
    env = create_jinja_env(templates_dir, framework='django')

Usage with Litestar:
    from examples.shared.jinja_env import create_jinja_env, TEMPLATES_DIR
    from litestar.contrib.jinja import JinjaTemplateEngine
    from litestar.template import TemplateConfig

    # Litestar handles url_for natively via its template callables
    template_config = TemplateConfig(
        directory=TEMPLATES_DIR,
        engine=JinjaTemplateEngine,
    )

Usage with Django:
    In settings.py TEMPLATES configuration:

    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.jinja2.Jinja2',
            'DIRS': [BASE_DIR.parent.parent / 'shared' / 'templates'],
            'APP_DIRS': False,
            'OPTIONS': {
                'environment': 'examples.shared.jinja_env.get_django_env',
            },
        },
        # Keep Django templates for admin
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            ...
        },
    ]
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

if TYPE_CHECKING:
    from collections.abc import Callable

    from jinja2 import Environment as JinjaEnvironment


# Path to the shared templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


# =============================================================================
# URL Mapping
# =============================================================================

URL_MAP: dict[str, str] = {
    # Dashboard
    "index": "/",
    "dashboard": "/",
    # Contacts
    "contact_list": "/contacts",
    "contact_detail": "/contacts/{contact_id}",
    "contact_create": "/contacts/new",
    "contact_edit": "/contacts/{contact_id}/edit",
    "contact_delete": "/contacts/{contact_id}/delete",
    # Activities
    "activity_list": "/activities",
    "activity_detail": "/activities/{activity_id}",
    "activity_create": "/activities/new",
    "activity_delete": "/activities/{activity_id}/delete",
    # Contributions
    "contribution_list": "/contributions",
    "contribution_detail": "/contributions/{contribution_id}",
    "contribution_create": "/contributions/new",
    # Events
    "event_list": "/events",
    "event_detail": "/events/{event_id}",
    "event_create": "/events/new",
    # Tools
    "generate_data": "/generate-data",
    "generate_sample_data": "/generate-data",  # Django alias
    # API endpoints
    "api_contacts": "/api/contacts",
    "api_activities": "/api/activities",
    "api_contributions": "/api/contributions",
    "api_events": "/api/events",
    "api_dashboard": "/api/dashboard",
    # Documentation (Litestar only)
    "scalar_docs": "/docs/scalar",
    "swagger_docs": "/docs/swagger",
    # CiviPlugin auto-generated (Litestar only)
    "civi_contact": "/api/civi/Contact",
    "civi_activity": "/api/civi/Activity",
}

# Map Litestar route names to Django URL names for parameter differences
DJANGO_URL_MAP: dict[str, str | None] = {
    # Dashboard
    "dashboard": "index",
    "index": "index",
    # Contacts
    "contact_list": "contact_list",
    "contact_detail": "contact_detail",
    "contact_create": "contact_create",
    "contact_edit": "contact_edit",
    "contact_delete": "contact_delete",
    # Activities
    "activity_list": "activity_list",
    "activity_detail": "activity_detail",
    "activity_create": "activity_create",
    "activity_delete": "activity_delete",
    # Contributions
    "contribution_list": "contribution_list",
    "contribution_detail": "contribution_detail",
    "contribution_create": "contribution_create",
    # Events
    "event_list": "event_list",
    "event_detail": "event_detail",
    "event_create": "event_create",
    # Sample data
    "generate_data": "generate_sample_data",
    "generate_sample_data": "generate_sample_data",
    # API endpoints
    "api_contacts": "api_contacts",
    "api_activities": "api_activities",
    "api_contributions": "api_contributions",
    "api_events": "api_events",
    # Documentation (Django doesn't have these, use placeholder paths)
    "scalar_docs": None,
    "swagger_docs": None,
    # CiviPlugin auto-generated (Django doesn't have these)
    "civi_contact": None,
    "civi_activity": None,
}


# =============================================================================
# URL Helper Functions
# =============================================================================


def _url_for_litestar(name: str, **kwargs: str | int) -> str:
    """URL helper for Litestar framework.

    Uses the URL_MAP to resolve route names to paths, substituting
    any provided kwargs into the path pattern.

    Args:
        name: Route name (e.g., 'contact_detail').
        **kwargs: Path parameters (e.g., contact_id=123).

    Returns:
        Resolved URL path.

    Example:
        >>> _url_for_litestar("contact_detail", contact_id=123)
        '/contacts/123'
    """
    pattern = URL_MAP.get(name)
    if pattern is None:
        # Fall back to returning the name as-is (useful for debugging)
        return f"/{name}"

    # Substitute kwargs into the pattern
    url = pattern
    for key, value in kwargs.items():
        url = url.replace(f"{{{key}}}", str(value))

    return url


def _url_for_django(name: str, **kwargs: str | int) -> str:
    """URL helper for Django framework.

    Uses Django's reverse() function to resolve route names.
    Falls back to URL_MAP if reverse fails.

    Args:
        name: Route name (e.g., 'contact_detail').
        **kwargs: URL arguments.

    Returns:
        Resolved URL path.
    """
    try:
        from django.urls import reverse

        # Map to Django URL name
        django_name = DJANGO_URL_MAP.get(name)
        if django_name is None:
            # Route doesn't exist in Django, return placeholder
            return "#"

        # Templates now use consistent parameter names (contact_id, activity_id, etc.)
        # Both Django and Litestar use these same names, so pass through directly
        django_kwargs = dict(kwargs)

        return reverse(django_name, kwargs=django_kwargs if django_kwargs else None)
    except (ImportError, KeyError, ValueError, TypeError):
        # Fall back to URL_MAP
        return _url_for_litestar(name, **kwargs)


def _url_for_flask(name: str, **kwargs: str | int) -> str:
    """URL helper for Flask framework.

    Uses Flask's url_for function to resolve route names.
    Falls back to URL_MAP if Flask is not available.

    Args:
        name: Route name (e.g., 'contact_detail').
        **kwargs: URL arguments.

    Returns:
        Resolved URL path.
    """
    try:
        from flask import url_for

        # Flask url_for handles the URL building natively
        return url_for(name, **kwargs)
    except (ImportError, RuntimeError):
        # Fall back to URL_MAP (outside of Flask context)
        return _url_for_litestar(name, **kwargs)


def create_url_for(framework: str = "litestar") -> Callable[..., str]:
    """Create a url_for function for the specified framework.

    Args:
        framework: Either 'litestar', 'django', or 'flask'.

    Returns:
        URL helper function appropriate for the framework.
    """
    if framework == "django":
        return _url_for_django
    if framework == "flask":
        return _url_for_flask
    return _url_for_litestar


# =============================================================================
# Template Filters
# =============================================================================


def get_attr(obj: object, path: str, default: object = None) -> object:  # noqa: PLR0911, PLR0912
    """Get a nested attribute/key from an object or dictionary.

    Supports multiple access patterns:
    - Dot notation: "email_primary.email"
    - CiviCRM label syntax: "status_id:label"
    - Direct attribute access: "display_name"
    - Dictionary key access: "some_key"

    The function first tries direct access (for CiviCRM joined fields
    like "email_primary.email" which are single keys), then falls back
    to nested traversal.

    Args:
        obj: The object or dictionary to access.
        path: The attribute path (e.g., "email_primary.email", "status_id:label").
        default: Default value if the attribute is not found.

    Returns:
        The attribute value or default if not found.

    Example:
        >>> contact = {"email_primary.email": "john@example.com", "id": 123}
        >>> get_attr(contact, "email_primary.email")
        'john@example.com'

        >>> activity = {"status_id:label": "Completed"}
        >>> get_attr(activity, "status_id:label")
        'Completed'

        >>> nested = {"address": {"city": "New York"}}
        >>> get_attr(nested, "address.city")
        'New York'
    """
    if obj is None:
        return default

    # First, try direct access for CiviCRM joined fields
    # CiviCRM uses keys like "email_primary.email" and "status_id:label"
    if isinstance(obj, dict) and path in obj:
        return obj[path]
    if hasattr(obj, path) and not callable(getattr(obj, path, None)):
        value = getattr(obj, path, default)
        if value is not None:
            return value

    # Handle colon syntax (CiviCRM label syntax like "status_id:label")
    # This is typically a direct key access, so if we're here it wasn't found
    if ":" in path and "." not in path:
        return default

    # Try nested access via dot notation
    parts = path.split(".")
    current = obj

    for i, part in enumerate(parts):
        if current is None:
            return default

        # Check for colon in this part (e.g., "state_province_id:label")
        # These are always direct keys in CiviCRM responses
        if ":" in part:
            if isinstance(current, dict):
                current = current.get(part, default)
                if current is default:
                    return default
            else:
                return default
            continue

        # Standard dot navigation
        if isinstance(current, dict):
            # Try the part as a key
            if part in current:
                current = current[part]
            else:
                # Try the full remaining path as a single key
                remaining_path = ".".join(parts[i:])
                if remaining_path in current:
                    return current[remaining_path]
                return default
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return default

    return current if current is not None else default


# =============================================================================
# CSRF Helper
# =============================================================================


def _csrf_input_django(request: Any = None) -> Markup:
    """Return CSRF input for Django.

    Args:
        request: Django HttpRequest object. If provided, generates a real
                 CSRF token. Otherwise returns a placeholder.

    Returns:
        HTML markup for CSRF hidden input.
    """
    if request is not None:
        try:
            from django.middleware.csrf import get_token

            token = get_token(request)
            return Markup(
                f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">',
            )
        except (ImportError, TypeError):
            pass

    # Fallback placeholder
    return Markup('<input type="hidden" name="csrfmiddlewaretoken" value="">')


def _csrf_input_litestar(request: Any = None) -> Markup:
    """Return CSRF input for Litestar.

    Litestar handles CSRF differently (typically via middleware or
    by not requiring it for certain endpoints). Returns an empty
    string for compatibility.

    Args:
        request: Optional request object (ignored, for API compatibility).

    Returns:
        Empty markup since Litestar doesn't use hidden CSRF inputs.
    """
    return Markup("")


def _csrf_input_flask(request: Any = None) -> Markup:
    """Return CSRF input for Flask.

    Flask doesn't have built-in CSRF protection. If using Flask-WTF,
    CSRF is handled differently. For simplicity, we return an empty
    string unless Flask-WTF is available.

    Args:
        request: Optional request object (ignored, for API compatibility).

    Returns:
        Empty markup or CSRF token if Flask-WTF is available.
    """
    # Flask doesn't have built-in CSRF; Flask-WTF handles it
    # For this example, we don't use Flask-WTF, so return empty
    return Markup("")


def create_csrf_input(framework: str = "litestar") -> Callable[[Any], Markup]:
    """Create a csrf_input function for the specified framework.

    Args:
        framework: Either 'litestar', 'django', or 'flask'.

    Returns:
        CSRF input helper function appropriate for the framework.
    """
    if framework == "django":
        return _csrf_input_django
    if framework == "flask":
        return _csrf_input_flask
    return _csrf_input_litestar


# =============================================================================
# Additional Utility Filters
# =============================================================================


def format_date(value: str | None, fmt: str = "%Y-%m-%d") -> str:
    """Format a date string.

    Args:
        value: ISO date string or None.
        fmt: strftime format string.

    Returns:
        Formatted date string or empty string if value is None.
    """
    if not value:
        return ""

    from datetime import datetime

    # Common CiviCRM date formats
    input_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for input_fmt in input_formats:
        try:
            dt = datetime.strptime(value, input_fmt)  # noqa: DTZ007
            return dt.strftime(fmt)
        except ValueError:
            continue

    # Return original if no format matches
    return value


def format_currency(amount: float | str | None, currency: str = "USD") -> str:
    """Format a numeric value as currency.

    Args:
        amount: Numeric value to format.
        currency: Currency code (default: USD).

    Returns:
        Formatted currency string.
    """
    if amount is None:
        return ""

    try:
        if isinstance(amount, str):
            amount = float(amount)

        symbols = {
            "USD": "$",
            "EUR": "\u20ac",
            "GBP": "\u00a3",
            "CAD": "C$",
            "AUD": "A$",
            "JPY": "\u00a5",
        }

        symbol = symbols.get(currency.upper(), f"{currency} ")
    except (TypeError, ValueError):
        return str(amount) if amount else ""
    else:
        return f"{symbol}{amount:,.2f}"


def default_if_none(value: object, default: object = "") -> object:
    """Return default value if value is None.

    This is similar to Jinja2's default filter but specifically
    handles None values (not just undefined).

    Args:
        value: The value to check.
        default: The default to return if value is None.

    Returns:
        The value or default.
    """
    return default if value is None else value


# =============================================================================
# Django Integration Helpers
# =============================================================================


class DjangoRequest:
    """Wrapper to make Django request compatible with Litestar template expectations.

    The shared templates use `request.url.path` (Litestar style) for navigation
    highlighting. This wrapper provides that interface for Django requests.
    """

    def __init__(self, django_request: object) -> None:
        """Initialize with a Django HttpRequest.

        Args:
            django_request: The Django HttpRequest object.
        """
        self._request = django_request

    @property
    def url(self) -> DjangoURL:
        """Get the URL object with path attribute.

        Returns:
            DjangoURL wrapper with path attribute.
        """
        return DjangoURL(self._request.path)

    def __getattr__(self, name: str) -> object:
        """Proxy all other attributes to the underlying Django request.

        Args:
            name: Attribute name to access.

        Returns:
            The attribute value from the Django request.
        """
        return getattr(self._request, name)


class DjangoURL:
    """Simple URL wrapper providing path attribute for template compatibility."""

    def __init__(self, path: str) -> None:
        """Initialize with a path string.

        Args:
            path: The URL path.
        """
        self.path = path


def get_request_path(request: Any) -> str:
    """Safely get the request path from any request type.

    Works with:
    - Litestar Request (request.url.path)
    - Django HttpRequest (request.path)
    - DjangoRequest wrapper (request.url.path)

    Args:
        request: Request object from any framework.

    Returns:
        The request path string, or "/" if unable to determine.
    """
    if request is None:
        return "/"

    # Try Litestar style (request.url.path)
    if hasattr(request, "url") and hasattr(request.url, "path"):
        return str(request.url.path)

    # Try Django style (request.path)
    if hasattr(request, "path"):
        return str(request.path)

    # Try get_full_path for Django
    if hasattr(request, "get_full_path"):
        return str(request.get_full_path())

    return "/"


# =============================================================================
# Environment Factory
# =============================================================================


def create_jinja_env(
    templates_dir: str | Path | list[str | Path] | None = None,
    framework: str = "litestar",
    *,
    url_resolver: Callable[[str, dict[str, Any]], str] | None = None,
    autoescape: bool = True,
    auto_reload: bool = True,
) -> JinjaEnvironment:
    """Create a configured Jinja2 Environment for the specified framework.

    This factory function creates a Jinja2 environment with all the
    necessary globals and filters for rendering templates that work
    across both Django and Litestar frameworks.

    Args:
        templates_dir: Path(s) to the templates directory. Can be a single path
                       or a list of paths. Defaults to TEMPLATES_DIR.
        framework: Target framework ('litestar' or 'django').
        url_resolver: Optional custom URL resolver function.
                      Signature: (route_name, kwargs) -> url_path
        autoescape: Enable autoescaping for HTML (default: True).
        auto_reload: Reload templates when they change (default: True).

    Returns:
        Configured Jinja2 Environment.

    Example:
        from examples.shared.jinja_env import create_jinja_env

        # Create environment for Litestar with single directory
        env = create_jinja_env(
            templates_dir="/path/to/templates",
            framework="litestar"
        )

        # Create environment with multiple template directories
        env = create_jinja_env(
            templates_dir=["/path/to/app/templates", "/path/to/webui/templates"],
            framework="litestar"
        )

        # Render a template
        template = env.get_template("contacts/list.html")
        html = template.render(contacts=contacts, request=request)
    """
    # Use default templates directory if not specified
    if templates_dir is None:
        loader_paths: str | Path | list[str | Path] = TEMPLATES_DIR
    elif isinstance(templates_dir, list):
        loader_paths = [Path(p) for p in templates_dir]
    else:
        loader_paths = Path(templates_dir)

    # Create the base environment
    env = Environment(
        loader=FileSystemLoader(loader_paths),
        autoescape=select_autoescape(["html", "xml"]) if autoescape else False,  # noqa: S701
        auto_reload=auto_reload,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Add globals (functions available in templates)
    if url_resolver is not None:
        env.globals["url_for"] = lambda name, **kwargs: url_resolver(name, kwargs)
    else:
        env.globals["url_for"] = create_url_for(framework)

    env.globals["render_csrf"] = create_csrf_input(framework)
    env.globals["URL_MAP"] = URL_MAP
    env.globals["get_attr"] = get_attr  # Also available as a global function
    env.globals["get_request_path"] = get_request_path  # Safe path accessor for any framework

    # Add filters
    env.filters["get_attr"] = get_attr
    env.filters["format_date"] = format_date
    env.filters["format_currency"] = format_currency
    env.filters["default_if_none"] = default_if_none

    # Add framework-specific configuration
    if framework == "django":
        _configure_django_env(env)
    elif framework == "flask":
        _configure_flask_env(env)
    else:
        _configure_litestar_env(env)

    return env


def _configure_django_env(env: JinjaEnvironment) -> None:
    """Apply Django-specific configuration to the Jinja2 environment.

    Args:
        env: The Jinja2 environment to configure.
    """
    # Add Django-specific globals
    env.globals["framework"] = "django"

    # Try to import Django utilities if available
    try:
        from django.utils.html import escape, format_html

        env.globals["escape"] = escape
        env.globals["format_html"] = format_html
    except ImportError:
        pass

    # Add Django static file URL helper
    try:
        from django.templatetags.static import static

        env.globals["static"] = static
    except ImportError:
        pass


def _configure_flask_env(env: JinjaEnvironment) -> None:
    """Apply Flask-specific configuration to the Jinja2 environment.

    Args:
        env: The Jinja2 environment to configure.
    """
    # Add Flask-specific globals
    env.globals["framework"] = "flask"

    # Try to import Flask utilities if available
    try:
        from markupsafe import escape

        env.globals["escape"] = escape
    except ImportError:
        pass


def _configure_litestar_env(env: JinjaEnvironment) -> None:
    """Apply Litestar-specific configuration to the Jinja2 environment.

    Args:
        env: The Jinja2 environment to configure.
    """
    # Add Litestar-specific globals
    env.globals["framework"] = "litestar"


# =============================================================================
# Django Backend Integration
# =============================================================================


def get_django_env(**_options: object) -> JinjaEnvironment:
    """Get a Jinja2 environment configured for Django.

    This function is called by Django's Jinja2 backend to create the environment.
    It must accept **options and return a Jinja2 Environment.

    The options parameter receives the 'OPTIONS' dict from Django's TEMPLATES
    configuration, which may include 'context_processors' and other settings.

    Args:
        **options: Options from Django's template backend configuration.

    Returns:
        Configured Jinja2 Environment for Django.

    Example:
        In Django settings.py:

        TEMPLATES = [
            {
                'BACKEND': 'django.template.backends.jinja2.Jinja2',
                'DIRS': [BASE_DIR / 'templates'],
                'OPTIONS': {
                    'environment': 'examples.shared.jinja_env.get_django_env',
                },
            },
        ]
    """
    env = create_jinja_env(framework="django")

    # Add Django's CSRF token helper that works with request context
    try:
        from django.middleware.csrf import get_token

        def csrf_input_with_request(request: object) -> Markup:
            """Generate a hidden CSRF input field with the actual token.

            Args:
                request: Django HttpRequest object.

            Returns:
                HTML markup for CSRF hidden input.
            """
            token = get_token(request)  # type: ignore[arg-type]
            # Token is validated by Django's CSRF system
            return Markup(
                f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">',
            )

        env.globals["render_csrf"] = csrf_input_with_request
    except ImportError:
        pass

    return env


# =============================================================================
# Convenience Functions for Integration
# =============================================================================


def get_template_globals(framework: str = "litestar") -> dict[str, Any]:
    """Get a dictionary of template globals for the specified framework.

    This is useful when you need to add the globals to an existing
    Jinja2 environment or template context.

    Args:
        framework: Target framework ('litestar' or 'django').

    Returns:
        Dictionary of template globals.
    """
    return {
        "url_for": create_url_for(framework),
        "csrf_input": create_csrf_input(framework),
        "URL_MAP": URL_MAP,
        "framework": framework,
        "get_attr": get_attr,
    }


def get_template_filters() -> dict[str, Any]:
    """Get a dictionary of template filters.

    This is useful when you need to add the filters to an existing
    Jinja2 environment.

    Returns:
        Dictionary of template filters.
    """
    return {
        "get_attr": get_attr,
        "format_date": format_date,
        "format_currency": format_currency,
        "default_if_none": default_if_none,
    }
