"""URL configuration for CiviCRM demo project."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from civicrm_py.contrib.django.webui import WebUIConfig, get_urlpatterns

from . import (
    civiadmin,  # noqa: F401 - Import to register entity admins with Django admin
    views,
)

# Configure Web UI for API exploration
webui_config = WebUIConfig(
    title="CiviCRM Explorer",
    theme="auto",
    enable_playground=True,
)

urlpatterns = [
    # Django admin (includes CiviCRM entities)
    path("admin/", admin.site.urls),
    # CiviCRM Web UI - interactive API explorer
    path("explorer/", include(get_urlpatterns(webui_config))),
    # ==========================================================================
    # Dashboard
    # ==========================================================================
    path("", views.index, name="index"),
    # ==========================================================================
    # Contacts (Sync)
    # ==========================================================================
    path("contacts/", views.contact_list, name="contact_list"),
    path("contacts/create/", views.contact_create, name="contact_create"),
    path("contacts/<int:contact_id>/", views.contact_detail, name="contact_detail"),
    path("contacts/<int:contact_id>/edit/", views.contact_edit, name="contact_edit"),
    path("contacts/<int:contact_id>/delete/", views.contact_delete, name="contact_delete"),
    # ==========================================================================
    # Activities (Sync)
    # ==========================================================================
    path("activities/", views.activity_list, name="activity_list"),
    path("activities/create/", views.activity_create, name="activity_create"),
    path("activities/<int:activity_id>/", views.activity_detail, name="activity_detail"),
    path("activities/<int:activity_id>/delete/", views.activity_delete, name="activity_delete"),
    # ==========================================================================
    # Contributions (Sync)
    # ==========================================================================
    path("contributions/", views.contribution_list, name="contribution_list"),
    path("contributions/create/", views.contribution_create, name="contribution_create"),
    path("contributions/<int:contribution_id>/", views.contribution_detail, name="contribution_detail"),
    # ==========================================================================
    # Events (Sync)
    # ==========================================================================
    path("events/", views.event_list, name="event_list"),
    path("events/create/", views.event_create, name="event_create"),
    path("events/<int:event_id>/", views.event_detail, name="event_detail"),
    # ==========================================================================
    # Sample Data Generation
    # ==========================================================================
    path("generate-data/", views.generate_sample_data, name="generate_sample_data"),
    path("sample-data/", RedirectView.as_view(url="/generate-data/", permanent=True)),
    # ==========================================================================
    # API Endpoints (JSON)
    # ==========================================================================
    path("api/contacts/", views.api_contacts, name="api_contacts"),
    path("api/activities/", views.api_activities, name="api_activities"),
    path("api/contributions/", views.api_contributions, name="api_contributions"),
    path("api/events/", views.api_events, name="api_events"),
    # ==========================================================================
    # Async Views (ASGI) - use these with uvicorn/daphne
    # ==========================================================================
    path("async/", views.index_async, name="index_async"),
    path("async/contacts/", views.contact_list_async, name="contact_list_async"),
    path("async/contacts/<int:contact_id>/", views.contact_detail_async, name="contact_detail_async"),
    path("async/activities/", views.activity_list_async, name="activity_list_async"),
    path("async/contributions/", views.contribution_list_async, name="contribution_list_async"),
    path("async/events/", views.event_list_async, name="event_list_async"),
    path("async/api/contacts/", views.api_contacts_async, name="api_contacts_async"),
]
