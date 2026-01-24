"""CiviCRM Admin configuration for the demo project.

This file is auto-discovered by civicrm_py.contrib.django when you call
autodiscover_entities() or when the app is loaded.

Example admin registrations for CiviCRM entities.
"""

from __future__ import annotations

from django.contrib import admin

from civicrm_py.contrib.django.admin import (
    CiviInlineAdmin,
    CiviModelAdmin,
    register_entity,
)
from civicrm_py.entities import Activity, Contact, Contribution, Email, Event, Phone

# =============================================================================
# Inline Admins for Related Entities
# =============================================================================


class EmailInline(CiviInlineAdmin):
    """Inline admin for editing Contact emails."""

    entity_class = Email
    fk_name = "contact_id"
    fields = ["email", "is_primary", "location_type_id"]
    extra = 1


class PhoneInline(CiviInlineAdmin):
    """Inline admin for editing Contact phones."""

    entity_class = Phone
    fk_name = "contact_id"
    fields = ["phone", "is_primary", "phone_type_id", "location_type_id"]
    extra = 1


# =============================================================================
# Entity Admin Classes
# =============================================================================


@register_entity(Contact, site=admin.site, app_label="civi")
class ContactAdmin(CiviModelAdmin):
    """Admin for CiviCRM Contacts.

    Provides list view with search and filtering, plus inline editing
    of related emails and phones.
    """

    list_display = ["id", "display_name", "contact_type", "email_primary", "is_deleted"]
    list_display_links = ["id", "display_name"]
    list_filter = ["contact_type", "is_deleted"]
    search_fields = ["display_name", "first_name", "last_name", "email_primary.email"]
    ordering = ["-id"]
    inlines = [EmailInline, PhoneInline]


@register_entity(Activity, site=admin.site, app_label="civi")
class ActivityAdmin(CiviModelAdmin):
    """Admin for CiviCRM Activities."""

    list_display = ["id", "subject", "activity_type_id", "status_id", "activity_date_time"]
    list_filter = ["activity_type_id", "status_id"]
    search_fields = ["subject", "details"]
    ordering = ["-activity_date_time"]


@register_entity(Contribution, site=admin.site, app_label="civi")
class ContributionAdmin(CiviModelAdmin):
    """Admin for CiviCRM Contributions (donations)."""

    list_display = ["id", "contact_id", "total_amount", "contribution_status_id", "receive_date"]
    list_filter = ["contribution_status_id", "financial_type_id"]
    search_fields = ["source", "trxn_id"]
    ordering = ["-receive_date"]


@register_entity(Event, site=admin.site, app_label="civi")
class EventAdmin(CiviModelAdmin):
    """Admin for CiviCRM Events."""

    list_display = ["id", "title", "event_type_id", "start_date", "is_active"]
    list_filter = ["event_type_id", "is_active", "is_public"]
    search_fields = ["title", "summary", "description"]
    ordering = ["-start_date"]
