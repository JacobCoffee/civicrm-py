"""Django integration for civi-py.

Provides middleware, template tags, and utilities for using civi-py with Django.

Quick Start:

    1. Add to INSTALLED_APPS and configure middleware in settings.py:

        INSTALLED_APPS = [
            ...
            'civicrm_py.contrib.django',
        ]

        MIDDLEWARE = [
            ...
            'civicrm_py.contrib.django.middleware.CiviMiddleware',
        ]

        CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
        CIVICRM_API_KEY = "your-api-key"

    2. Use in views:

        def my_view(request):
            client = request.civi_client
            contacts = client.get("Contact", limit=10)
            return JsonResponse({"contacts": contacts.values})

    3. Use template tags in templates:

        {% load civi_tags %}

        {% civi_contact id=1 as contact %}
        <h1>{{ contact.display_name }}</h1>
        <p>Email: {{ contact|civi_field:"email_primary.email" }}</p>

        {% civi_contacts filter="contact_type=Individual" limit=5 as contacts %}
        {% civi_contact_list contacts %}

For async views (Django 5+):

    async def my_view(request):
        client = request.civi_client
        contacts = await client.get("Contact", limit=10)
        return JsonResponse({"contacts": contacts.values})

Configuration Settings:

    CIVICRM_URL (str, required): Base URL for CiviCRM API v4
    CIVICRM_API_KEY (str, optional): API key for authentication
    CIVICRM_SITE_KEY (str, optional): Site key for some auth modes
    CIVICRM_AUTH_TYPE (str, default: "api_key"): Authentication type
    CIVICRM_TIMEOUT (int, default: 30): Request timeout in seconds
    CIVICRM_VERIFY_SSL (bool, default: True): SSL certificate verification
    CIVICRM_DEBUG (bool, default: False): Enable debug logging
    CIVICRM_MAX_RETRIES (int, default: 3): Maximum retry attempts

Template Tags ({% load civi_tags %}):

    Simple Tags:
        - {% civi_contact id=1 as contact %} - fetch a contact by ID
        - {% civi_contacts filter="is_deleted=False" limit=10 as contacts %} - fetch multiple
        - {% civi_entity "Activity" id=5 as activity %} - fetch any entity
        - {% civi_entities "Activity" filter="..." as activities %} - fetch multiple entities

    Inclusion Tags:
        - {% civi_contact_card contact %} - render a contact card
        - {% civi_contact_list contacts %} - render a list of contacts

    Filters:
        - {{ contact|civi_field:"email_primary.email" }} - access nested fields
        - {{ date|civi_format_date:"%B %d, %Y" }} - format dates
        - {{ amount|civi_format_currency:"USD" }} - format currency
        - {{ contact.contact_type|civi_contact_type_label }} - human labels
        - {{ value|civi_bool_icon }} - boolean icons
        - {{ text|civi_truncate:50 }} - truncate text

    Block Tags:
        - {% civi_with_client as client %}...{% endcivi_with_client %}

Context Processor:
    Add to TEMPLATES for automatic civi_client availability:

        TEMPLATES = [{
            'OPTIONS': {
                'context_processors': [
                    ...
                    'civicrm_py.contrib.django.templatetags.civi_tags.civi_context_processor',
                ],
            },
        }]

Management Commands:

    python manage.py civi_shell  # Interactive CiviCRM shell with auto-imports

Components:

    CiviAppConfig: Django AppConfig for automatic app initialization
    CiviConfig: Base configuration class (framework-agnostic)
    CiviMiddleware: Django middleware that attaches client to requests
    DjangoIntegration: Integration class for manual lifecycle management
    get_civi_settings: Get CiviSettings from Django settings
    get_client_from_request: Helper to get client from request object

Admin Integration:

    CiviCRM entities can be browsed and edited in Django admin without
    requiring actual Django models. The admin integration uses the CiviCRM
    API for all data operations.

    Quick Start:
        # In your admin.py or civiadmin.py:
        from civicrm_py.contrib.django.admin import CiviModelAdmin, register_entity, civi_admin_site
        from civicrm_py.entities import Contact

        @register_entity(Contact, site=civi_admin_site)
        class ContactAdmin(CiviModelAdmin):
            list_display = ['id', 'display_name', 'email_primary', 'contact_type']
            search_fields = ['display_name', 'first_name', 'last_name']
            list_filter = ['contact_type', 'is_deleted']

        # In urls.py:
        from civicrm_py.contrib.django.admin import civi_admin_site

        urlpatterns = [
            path('admin/', admin.site.urls),
            path('civiadmin/', civi_admin_site.urls),
        ]

    Admin Components:
        CiviModelAdmin: Base admin class for CiviCRM entities
        CiviAdminSite: Custom admin site for CiviCRM data
        CiviInlineAdmin: Inline editing for related entities
        CiviQuerySet: Django QuerySet-like wrapper for API queries
        register_entity: Decorator to register entity admin classes
        civi_admin_site: Default admin site instance
        autodiscover_entities: Auto-discover civiadmin.py modules
"""

from __future__ import annotations

from civicrm_py.contrib.django.admin import (
    CiviAdminSite,
    CiviChangeList,
    CiviField,
    CiviInlineAdmin,
    CiviModelAdmin,
    CiviOptions,
    CiviPaginator,
    CiviQuerySet,
    autodiscover_entities,
    civi_admin_site,
    register_entity,
)
from civicrm_py.contrib.django.apps import CiviAppConfig, CiviConfig
from civicrm_py.contrib.django.middleware import (
    CiviMiddleware,
    close_clients,
    close_clients_async,
    get_client_from_request,
)
from civicrm_py.contrib.django.settings import (
    AuthType,
    DjangoIntegration,
    clear_settings_cache,
    create_settings,
    get_civi_settings,
    get_django_settings,
)
from civicrm_py.contrib.django.webui import WebUIConfig, get_urlpatterns

# Django app configuration - enables 'civicrm_py.contrib.django' in INSTALLED_APPS
# This is the traditional approach for Django < 3.2 compatibility.
# Django 3.2+ will auto-detect the AppConfig from apps.py.
default_app_config = "civicrm_py.contrib.django.apps.CiviAppConfig"

__all__ = [
    "AuthType",
    "CiviAdminSite",
    "CiviAppConfig",
    "CiviChangeList",
    "CiviConfig",
    "CiviField",
    "CiviInlineAdmin",
    "CiviMiddleware",
    "CiviModelAdmin",
    "CiviOptions",
    "CiviPaginator",
    "CiviQuerySet",
    "DjangoIntegration",
    "WebUIConfig",
    "autodiscover_entities",
    "civi_admin_site",
    "clear_settings_cache",
    "close_clients",
    "close_clients_async",
    "create_settings",
    "get_civi_settings",
    "get_client_from_request",
    "get_django_settings",
    "get_urlpatterns",
    "register_entity",
]
