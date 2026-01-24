"""Django Admin integration for CiviCRM entities.

Provides a Django-admin-like interface for browsing and editing CiviCRM data
without requiring actual Django models. Uses the CiviCRM API for all data
operations while presenting a familiar admin interface.

Example:
    >>> from civicrm_py.contrib.django.admin import CiviModelAdmin, register_entity
    >>> from civicrm_py.entities import Contact
    >>>
    >>> @register_entity(Contact)
    ... class ContactAdmin(CiviModelAdmin):
    ...     list_display = ["id", "display_name", "email_primary"]
    ...     search_fields = ["display_name", "email_primary.email"]
    ...     list_filter = ["contact_type", "is_deleted"]
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from civicrm_py.core.client import SyncCiviClient
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.exceptions import CiviAPIError, CiviError, DoesNotExist

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from civicrm_py.entities.base import BaseEntity

logger = logging.getLogger(__name__)

EntityT = TypeVar("EntityT", bound="BaseEntity")

# Registry for entity-admin class mappings
_entity_admin_registry: dict[type[BaseEntity], type[CiviModelAdmin[Any]]] = {}


def _check_django_available() -> bool:
    """Check if Django is available."""
    try:
        import django  # noqa: F401
    except ImportError:
        return False
    else:
        return True


class CiviQuerySet(Generic[EntityT]):
    """Django QuerySet-like wrapper for CiviCRM API queries.

    Provides a QuerySet interface that Django admin expects while
    translating operations to CiviCRM API calls.

    This class is lazy - queries are not executed until the results
    are actually needed (iteration, slicing, counting).

    Attributes:
        entity_class: The CiviCRM entity class being queried.
        client: SyncCiviClient for API communication.
    """

    def __init__(
        self,
        entity_class: type[EntityT],
        client: SyncCiviClient,
        *,
        _filters: list[list[Any]] | None = None,
        _select: list[str] | None = None,
        _order_by: dict[str, str] | None = None,
        _limit: int | None = None,
        _offset: int | None = None,
        _search_term: str | None = None,
        _search_fields: list[str] | None = None,
    ) -> None:
        """Initialize CiviQuerySet.

        Args:
            entity_class: The entity class to query.
            client: SyncCiviClient for API requests.
            _filters: Internal filter conditions.
            _select: Fields to return.
            _order_by: Sort order.
            _limit: Max records.
            _offset: Skip records.
            _search_term: Search query term.
            _search_fields: Fields to search in.
        """
        self.entity_class = entity_class
        self.client = client
        self._filters = _filters or []
        self._select = _select
        self._order_by = _order_by or {}
        self._limit = _limit
        self._offset = _offset
        self._search_term = _search_term
        self._search_fields = _search_fields or []
        self._result_cache: list[dict[str, Any]] | None = None
        self._count_cache: int | None = None

    @property
    def model(self) -> type[EntityT]:
        """Return entity class (for Django admin compatibility)."""
        return self.entity_class

    @property
    def db(self) -> str:
        """Return database alias (for Django admin compatibility)."""
        return "civicrm"

    def _clone(self, **kwargs: Any) -> CiviQuerySet[EntityT]:
        """Create a copy with updated parameters."""
        return CiviQuerySet(
            entity_class=self.entity_class,
            client=self.client,
            _filters=kwargs.get("_filters", self._filters.copy()),
            _select=kwargs.get("_select", self._select),
            _order_by=kwargs.get("_order_by", self._order_by.copy()),
            _limit=kwargs.get("_limit", self._limit),
            _offset=kwargs.get("_offset", self._offset),
            _search_term=kwargs.get("_search_term", self._search_term),
            _search_fields=kwargs.get("_search_fields", self._search_fields.copy()),
        )

    def _build_where(self) -> list[list[Any]]:
        """Build complete WHERE clause including search."""
        where = self._filters.copy()

        # Add search conditions
        if self._search_term and self._search_fields:
            search_conditions = [[field, "CONTAINS", self._search_term] for field in self._search_fields]
            if search_conditions:
                # OR all search field conditions
                if len(search_conditions) == 1:
                    where.append(search_conditions[0])
                else:
                    where.append(["OR", search_conditions])

        return where

    def _fetch_results(self) -> list[dict[str, Any]]:
        """Execute query and return results."""
        if self._result_cache is not None:
            return self._result_cache

        entity_name = getattr(self.entity_class, "__entity_name__", self.entity_class.__name__)
        where = self._build_where()

        response = self.client.get(
            entity_name,
            select=self._select,
            where=where if where else None,
            order_by=self._order_by if self._order_by else None,
            limit=self._limit,
            offset=self._offset,
        )

        self._result_cache = response.values or []
        return self._result_cache

    def _fetch_count(self) -> int:
        """Get total count of matching records."""
        if self._count_cache is not None:
            return self._count_cache

        entity_name = getattr(self.entity_class, "__entity_name__", self.entity_class.__name__)
        where = self._build_where()

        # Count query - select only id, no limit
        response = self.client.get(
            entity_name,
            select=["id"],
            where=where if where else None,
            limit=0,  # Get count without fetching records
        )

        self._count_cache = response.count or 0
        return self._count_cache

    def filter(self, **kwargs: Any) -> CiviQuerySet[EntityT]:
        """Filter the queryset by field values."""
        filters = self._filters.copy()
        for key, value in kwargs.items():
            if "__" in key:
                field, lookup = key.rsplit("__", 1)
                operator_map = {
                    "exact": "=",
                    "contains": "CONTAINS",
                    "icontains": "CONTAINS",
                    "gt": ">",
                    "gte": ">=",
                    "lt": "<",
                    "lte": "<=",
                    "in": "IN",
                    "isnull": "IS NULL" if value else "IS NOT NULL",
                }
                operator = operator_map.get(lookup, "=")
                if lookup == "isnull":
                    filters.append([field, operator])
                else:
                    filters.append([field, operator, value])
            else:
                filters.append([key, "=", value])
        return self._clone(_filters=filters)

    def exclude(self, **kwargs: Any) -> CiviQuerySet[EntityT]:
        """Exclude records matching the given criteria."""
        filters = self._filters.copy()
        for key, value in kwargs.items():
            if "__" in key:
                field, lookup = key.rsplit("__", 1)
                # Invert operators for exclude
                if lookup == "exact" or key.count("__") == 0:
                    filters.append([key.split("__")[0], "!=", value])
                elif lookup == "in":
                    filters.append([field, "NOT IN", value])
                else:
                    # For other lookups, wrap in NOT
                    filters.append(["NOT", [[field, lookup, value]]])
            else:
                filters.append([key, "!=", value])
        return self._clone(_filters=filters)

    def order_by(self, *fields: str) -> CiviQuerySet[EntityT]:
        """Order results by specified fields."""
        order_by = {}
        for field in fields:
            if field.startswith("-"):
                order_by[field[1:]] = "DESC"
            else:
                order_by[field.lstrip("+")] = "ASC"
        return self._clone(_order_by=order_by)

    def select_related(self, *fields: str) -> CiviQuerySet[EntityT]:
        """No-op for Django compatibility (CiviCRM handles joins differently)."""
        return self

    def prefetch_related(self, *fields: str) -> CiviQuerySet[EntityT]:
        """No-op for Django compatibility."""
        return self

    def only(self, *fields: str) -> CiviQuerySet[EntityT]:
        """Select only specific fields."""
        return self._clone(_select=list(fields))

    def defer(self, *fields: str) -> CiviQuerySet[EntityT]:
        """No-op for Django compatibility."""
        return self

    def values(self, *fields: str) -> CiviQuerySet[EntityT]:
        """Select specific fields (returns dicts)."""
        return self._clone(_select=list(fields))

    def values_list(self, *fields: str, flat: bool = False) -> CiviQuerySet[EntityT]:
        """Select specific fields."""
        return self._clone(_select=list(fields))

    def all(self) -> CiviQuerySet[EntityT]:
        """Return a copy of the queryset."""
        return self._clone()

    def none(self) -> CiviQuerySet[EntityT]:
        """Return an empty queryset."""
        qs = self._clone()
        qs._result_cache = []
        qs._count_cache = 0
        return qs

    def count(self) -> int:
        """Return count of matching records."""
        return self._fetch_count()

    def exists(self) -> bool:
        """Check if any records match."""
        return self.count() > 0

    def first(self) -> dict[str, Any] | None:
        """Return first result or None."""
        qs = self._clone(_limit=1)
        results = qs._fetch_results()
        return results[0] if results else None

    def last(self) -> dict[str, Any] | None:
        """Return last result or None."""
        results = self._fetch_results()
        return results[-1] if results else None

    def get(self, **kwargs: Any) -> dict[str, Any]:
        """Get a single record matching criteria."""
        qs = self.filter(**kwargs) if kwargs else self
        results = qs._clone(_limit=2)._fetch_results()

        if not results:
            entity_name = getattr(self.entity_class, "__entity_name__", self.entity_class.__name__)
            raise DoesNotExist(entity_name, kwargs)

        if len(results) > 1:
            msg = f"get() returned more than one {self.entity_class.__name__}"
            raise CiviAPIError(msg)

        return results[0]

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over results."""
        return iter(self._fetch_results())

    def __len__(self) -> int:
        """Return count of results."""
        return len(self._fetch_results())

    def __getitem__(self, index: int | slice) -> dict[str, Any] | list[dict[str, Any]]:
        """Support indexing and slicing."""
        if isinstance(index, slice):
            start = index.start or 0
            stop = index.stop
            if stop is not None:
                limit = stop - start
                qs = self._clone(_offset=start, _limit=limit)
                return qs._fetch_results()
            qs = self._clone(_offset=start)
            return qs._fetch_results()
        results = self._fetch_results()
        return results[index]

    def __bool__(self) -> bool:
        """Check if queryset has results."""
        return self.exists()

    def _search(self, search_term: str, search_fields: list[str]) -> CiviQuerySet[EntityT]:
        """Apply search filtering."""
        return self._clone(_search_term=search_term, _search_fields=search_fields)

    def using(self, alias: str) -> CiviQuerySet[EntityT]:
        """No-op for Django compatibility."""
        return self

    def distinct(self) -> CiviQuerySet[EntityT]:
        """No-op for Django compatibility."""
        return self


class CiviRecord:
    """Wrapper for CiviCRM API results that mimics Django model instances.

    Django admin expects model instances with _meta attributes. This class
    wraps dict results from the CiviCRM API to provide that interface.
    """

    def __init__(self, data: dict[str, Any], opts: CiviOptions) -> None:
        """Initialize wrapper.

        Args:
            data: The dict data from CiviCRM API.
            opts: CiviOptions for the entity.
        """
        self._data = data
        self._meta = opts

    @property
    def pk(self) -> Any:
        """Return primary key value."""
        return self._data.get("id")

    def __str__(self) -> str:
        """Return string representation."""
        return str(
            self._data.get("display_name")
            or self._data.get("subject")
            or self._data.get("title")
            or self._data.get("id", "")
        )

    def __getattr__(self, name: str) -> Any:
        """Get attribute from data dict, returning None for missing keys."""
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access."""
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value with default."""
        return self._data.get(key, default)

    def serializable_value(self, field_name: str) -> Any:
        """Return serializable value for field (required by Django admin)."""
        return self._data.get(field_name)


class CiviField:
    """Mock Django model field for CiviCRM entity fields.

    Provides all attributes that Django admin utilities expect from a field.
    """

    # Class-level attribute that Django checks
    empty_values = (None, "", [], (), {})

    def __init__(
        self,
        name: str,
        field_type: type,
        *,
        primary_key: bool = False,
        editable: bool = True,
        choices: list[tuple[Any, str]] | None = None,
    ) -> None:
        """Initialize field."""
        self.name = name
        self.attname = name
        self.verbose_name = name.replace("_", " ").title()
        self.field_type = field_type
        self.primary_key = primary_key or name == "id"
        self.editable = editable and not self.primary_key
        self.choices = choices
        self.flatchoices = choices or []
        self.null = True
        self.blank = True
        self.is_relation = False
        self.remote_field = None
        self.related_model = None
        self.many_to_many = False
        self.one_to_many = False
        self.one_to_one = False
        self.auto_created = False
        self.concrete = True
        self.hidden = False
        self.unique = primary_key
        self.db_index = False
        self.serialize = True
        self.help_text = ""
        self.db_column = name
        self.db_tablespace = None
        self.default = None
        self.empty_strings_allowed = True
        self.max_length = None
        self.validators = []
        self.error_messages = {}
        self.db_comment = None
        self.db_default = None

    def formfield(self, **kwargs: Any) -> Any:
        """Return form field for this field."""
        if not _check_django_available():
            return None

        from django import forms

        if self.choices:
            return forms.ChoiceField(choices=self.choices, required=False, **kwargs)

        type_map = {
            int: forms.IntegerField,
            str: forms.CharField,
            bool: forms.BooleanField,
            float: forms.FloatField,
        }

        field_class = type_map.get(self.field_type, forms.CharField)
        return field_class(required=False, **kwargs)

    def value_from_object(self, obj: Any) -> Any:
        """Get field value from object."""
        if isinstance(obj, dict):
            return obj.get(self.name)
        if isinstance(obj, CiviRecord):
            return obj.get(self.name)
        return getattr(obj, self.name, None)

    def get_attname(self) -> str:
        """Return the attribute name."""
        return self.attname

    def get_attname_column(self) -> tuple[str, str]:
        """Return attname and column name."""
        return self.attname, self.db_column

    def has_default(self) -> bool:
        """Check if field has a default value."""
        return self.default is not None

    def get_default(self) -> Any:
        """Return the default value."""
        return self.default

    def contribute_to_class(self, cls: type, name: str) -> None:
        """No-op for compatibility."""

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        """Return deconstructed field for migrations (no-op)."""
        return self.name, f"{self.__class__.__module__}.{self.__class__.__name__}", [], {}


class CiviOptions:
    """Mock Django model _meta options for CiviCRM entities.

    Provides the metadata interface that Django admin expects.
    """

    def __init__(self, entity_class: type[BaseEntity], app_label: str = "civi") -> None:
        """Initialize options from entity class.

        Args:
            entity_class: The CiviCRM entity class.
            app_label: Django app label to use (must be an installed app).
                Defaults to "civi" which matches CiviAppConfig.label.
        """
        self.entity_class = entity_class
        entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
        self.model_name = entity_name.lower()
        self.verbose_name = entity_name
        # Proper English pluralization
        if entity_name.endswith("y") and entity_name[-2:-1].lower() not in "aeiou":
            self.verbose_name_plural = f"{entity_name[:-1]}ies"  # Activity -> Activities
        elif entity_name.endswith(("s", "x", "z", "ch", "sh")):
            self.verbose_name_plural = f"{entity_name}es"
        else:
            self.verbose_name_plural = f"{entity_name}s"
        self.app_label = app_label
        self.object_name = entity_name
        self.pk = CiviField("id", int)
        self.ordering = ["-id"]
        self.default_permissions = ("add", "change", "delete", "view")
        self.swapped = False
        self.abstract = False
        self.managed = False
        self.proxy = False

        # Get the app_config for this app_label (Django admin checks this)
        self.app_config = self._get_app_config(app_label)

        # Build fields from entity
        self._fields: list[CiviField] = []
        self._build_fields()

    def _get_app_config(self, app_label: str) -> Any:
        """Get the AppConfig for the given app_label.

        Args:
            app_label: Django app label.

        Returns:
            AppConfig instance or None if not found.
        """
        try:
            from django.apps import apps

            return apps.get_app_config(app_label)
        except Exception:
            return None

    def _build_fields(self) -> None:
        """Build field list from entity class."""
        # Try to get fields from __annotations__ (works for msgspec, pydantic, dataclasses)
        annotations = {}
        for cls in self.entity_class.__mro__:
            if hasattr(cls, "__annotations__"):
                # Build up annotations from base classes first
                for name, type_hint in cls.__annotations__.items():
                    if name not in annotations and not name.startswith("_"):
                        annotations[name] = type_hint

        if annotations:
            for name, type_hint in annotations.items():
                # Skip private/internal fields
                if name.startswith("_"):
                    continue
                # Determine base type from type hints
                field_type = type_hint
                if hasattr(field_type, "__origin__"):
                    # Handle Optional/Union types - get first non-None arg
                    args = getattr(field_type, "__args__", ())
                    for arg in args:
                        if arg is not type(None):
                            field_type = arg
                            break
                    else:
                        field_type = str
                # Convert type to basic Python type
                if not isinstance(field_type, type):
                    field_type = str
                self._fields.append(CiviField(name, field_type))
        else:
            # Fallback: just add id field
            self._fields.append(CiviField("id", int))

    def get_fields(self) -> list[CiviField]:
        """Return list of fields."""
        return self._fields

    def get_field(self, name: str) -> CiviField:
        """Get field by name."""
        for field in self._fields:
            if field.name == name:
                return field
        # Return a dummy field for unknown fields
        return CiviField(name, str)

    @property
    def label(self) -> str:
        """Return model label."""
        return f"{self.app_label}.{self.model_name}"

    @property
    def label_lower(self) -> str:
        """Return lowercase model label."""
        return self.label.lower()


# Only define Django-dependent classes if Django is available
if _check_django_available():
    from django.contrib import admin, messages
    from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
    from django.contrib.admin.views.main import ChangeList
    from django.core.exceptions import PermissionDenied
    from django.core.paginator import Paginator
    from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
    from django.template.response import TemplateResponse
    from django.urls import path, reverse
    from django.utils.translation import gettext_lazy as _

    class CiviPaginator(Paginator):
        """Custom paginator that works with CiviQuerySet.

        Handles pagination for CiviCRM data in Django admin.
        """

        def __init__(
            self,
            object_list: CiviQuerySet[Any],
            per_page: int,
            orphans: int = 0,
            allow_empty_first_page: bool = True,
        ) -> None:
            """Initialize paginator."""
            super().__init__(object_list, per_page, orphans, allow_empty_first_page)

        @cached_property
        def count(self) -> int:
            """Return total count from CiviQuerySet."""
            if hasattr(self.object_list, "count"):
                return self.object_list.count()
            return len(self.object_list)

    class CiviChangeList(ChangeList):
        """Customized ChangeList for CiviCRM entities.

        Handles the list view in Django admin, adapting it for CiviCRM data.
        """

        def __init__(
            self,
            request: HttpRequest,
            model: type[BaseEntity],
            list_display: Sequence[str],
            list_display_links: Sequence[str] | None,
            list_filter: Sequence[Any],
            date_hierarchy: str | None,
            search_fields: Sequence[str],
            list_select_related: Sequence[str] | bool,
            list_per_page: int,
            list_max_show_all: int,
            list_editable: Sequence[str],
            model_admin: CiviModelAdmin[Any],
            sortable_by: Sequence[str] | None,
            search_help_text: str | None = None,
        ) -> None:
            """Initialize CiviChangeList."""
            self.model = model
            # Use opts from model_admin to preserve app_label
            self.opts = model_admin.opts
            self.lookup_opts = self.opts
            self.root_queryset = model_admin.get_queryset(request)
            self.list_display = list_display
            self.list_display_links = list_display_links
            self.list_filter = list_filter
            self.date_hierarchy = date_hierarchy
            self.search_fields = search_fields
            self.list_select_related = list_select_related
            self.list_per_page = list_per_page
            self.list_max_show_all = list_max_show_all
            self.list_editable = list_editable
            self.model_admin = model_admin
            self.sortable_by = sortable_by
            self.search_help_text = search_help_text
            self.preserved_filters = model_admin.get_preserved_filters(request)
            self.is_popup = IS_POPUP_VAR in request.GET
            self.to_field = request.GET.get(TO_FIELD_VAR)
            self.params = dict(request.GET.items())
            self.filter_specs = []
            self.filter_params = {}  # Required by Django admin templates
            self.has_filters = bool(list_filter)
            self.has_active_filters = False
            self.clear_all_filters_qs = ""
            self.title = model_admin.get_title(request)
            self.pk_attname = "id"
            self.page_num = 0
            self.show_all = False
            self.can_show_all = True
            self.multi_page = False
            self.result_count = 0
            self.result_list = []
            self.full_result_count = 0
            self.formset = None
            self.show_admin_actions = False  # No bulk actions for now
            self.show_full_result_count = True
            self.actions_selection_counter = 0

            # Remove internal params
            for param in (IS_POPUP_VAR, TO_FIELD_VAR, "o", "p", "q"):
                self.params.pop(param, None)

            # Get queryset with filters applied
            self.queryset = self.get_queryset(request)
            self.get_results(request)

        def get_queryset(self, request: HttpRequest) -> CiviQuerySet[Any]:
            """Build and return the filtered queryset."""
            qs = self.root_queryset

            # Apply ordering
            ordering = self.get_ordering(request, qs)
            if ordering:
                qs = qs.order_by(*ordering)

            # Apply search
            search_term = request.GET.get("q", "")
            if search_term and self.search_fields:
                qs = qs._search(search_term, list(self.search_fields))

            # Apply filter params
            for key, value in self.params.items():
                if key not in ("o", "p", "q", "_popup", "_to_field"):
                    qs = qs.filter(**{key: value})

            return qs

        def get_ordering(
            self,
            request: HttpRequest,
            queryset: CiviQuerySet[Any],
        ) -> list[str]:
            """Get ordering from request params or model admin."""
            params = request.GET
            ordering = []

            # Check for ordering parameter
            order_param = params.get("o")
            if order_param:
                try:
                    order_idx = int(order_param.strip("-"))
                    if 0 <= order_idx < len(self.list_display):
                        field = self.list_display[order_idx]
                        if order_param.startswith("-"):
                            field = f"-{field}"
                        ordering.append(field)
                except (ValueError, IndexError):
                    pass

            if not ordering:
                # Use default ordering
                ordering = list(self.model_admin.ordering or ["-id"])

            return ordering

        def get_results(self, request: HttpRequest) -> None:
            """Get paginated results."""
            paginator = CiviPaginator(self.queryset, self.list_per_page)
            self.full_result_count = paginator.count
            self.result_count = paginator.count

            # Get page
            try:
                page_num = int(request.GET.get("p", 0))
            except ValueError:
                page_num = 0

            self.page_num = page_num
            self.show_all = request.GET.get("all") == "1"

            if self.show_all:
                raw_results = list(self.queryset)
            else:
                start = page_num * self.list_per_page
                end = start + self.list_per_page
                raw_results = self.queryset[start:end]

            # Wrap dicts in CiviRecord for Django admin compatibility
            self.result_list = [CiviRecord(r, self.opts) for r in raw_results]

            self.can_show_all = self.result_count <= self.list_max_show_all
            self.multi_page = self.result_count > self.list_per_page

        def url_for_result(self, result: CiviRecord | dict[str, Any]) -> str:
            """Get the change URL for a result."""
            pk = result.get("id") or getattr(result, "pk", None)
            return reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
                args=(pk,),
                current_app=self.model_admin.admin_site.name,
            )

    class CiviModelAdmin(admin.ModelAdmin, Generic[EntityT]):  # type: ignore[type-arg]
        """ModelAdmin base class for CiviCRM entities.

        Provides Django admin interface for CiviCRM entities, connecting
        to the CiviCRM API instead of the database.

        Attributes:
            entity_class: The CiviCRM entity class this admin manages.
            list_display: Fields to display in the list view.
            list_display_links: Fields that link to the change view.
            list_filter: Fields to filter by in the sidebar.
            search_fields: Fields to search in.
            ordering: Default ordering for the list.
            readonly_fields: Fields that cannot be edited.
            fields: Fields to display in the edit form.
            exclude: Fields to exclude from the edit form.
            list_per_page: Number of items per page.
            list_max_show_all: Maximum items for "show all" link.
            actions: Available actions on the list view.

        Example:
            >>> @register_entity(Contact)
            ... class ContactAdmin(CiviModelAdmin):
            ...     list_display = ["id", "display_name", "email_primary", "contact_type"]
            ...     search_fields = ["display_name", "first_name", "last_name"]
            ...     list_filter = ["contact_type", "is_deleted"]
        """

        entity_class: ClassVar[type[EntityT]]
        list_display: Sequence[str] = ("id", "__str__")
        list_display_links: Sequence[str] | None = None
        list_filter: Sequence[str] = ()
        search_fields: Sequence[str] = ()
        ordering: Sequence[str] | None = None
        readonly_fields: Sequence[str] = ()
        fields: Sequence[str] | None = None
        exclude: Sequence[str] | None = None
        list_per_page: int = 100
        list_max_show_all: int = 200
        actions: Sequence[str | Callable[..., Any]] | None = None
        inlines: Sequence[type[CiviInlineAdmin[Any]]] = ()

        _client: ClassVar[SyncCiviClient | None] = None

        def __init__(
            self,
            model: type[EntityT] | None = None,
            admin_site: admin.AdminSite | None = None,
        ) -> None:
            """Initialize CiviModelAdmin.

            Args:
                model: Entity class (may be set by decorator).
                admin_site: Django admin site.
            """
            if model is not None:
                self.entity_class = model
            # Use existing _meta if available (set by register_entity), otherwise create new
            if hasattr(self.entity_class, "_meta") and isinstance(self.entity_class._meta, CiviOptions):
                self.opts = self.entity_class._meta
            else:
                self.opts = CiviOptions(self.entity_class)
            self.model = self.entity_class  # For Django admin compatibility
            self.admin_site = admin_site or admin.site

        @classmethod
        def get_client(cls) -> SyncCiviClient:
            """Get or create the CiviCRM client.

            Override this method to customize client configuration.

            Returns:
                SyncCiviClient instance.
            """
            if cls._client is None:
                try:
                    from django.conf import settings as django_settings

                    # Try to get settings from Django configuration
                    civi_settings = CiviSettings(
                        base_url=getattr(django_settings, "CIVICRM_BASE_URL", None)
                        or getattr(django_settings, "CIVI_BASE_URL", ""),
                        api_key=getattr(django_settings, "CIVICRM_API_KEY", None)
                        or getattr(django_settings, "CIVI_API_KEY", ""),
                        site_key=getattr(django_settings, "CIVICRM_SITE_KEY", None)
                        or getattr(django_settings, "CIVI_SITE_KEY", None),
                        timeout=getattr(django_settings, "CIVICRM_TIMEOUT", 30),
                        verify_ssl=getattr(django_settings, "CIVICRM_VERIFY_SSL", True),
                    )
                except Exception:
                    # Fall back to environment variables
                    civi_settings = CiviSettings.from_env()

                cls._client = SyncCiviClient(settings=civi_settings)
            return cls._client

        def get_queryset(self, request: HttpRequest) -> CiviQuerySet[EntityT]:
            """Return a CiviQuerySet for the entity.

            Args:
                request: Django HTTP request.

            Returns:
                CiviQuerySet for the entity.
            """
            return CiviQuerySet(
                entity_class=self.entity_class,
                client=self.get_client(),
            )

        def get_object(
            self,
            request: HttpRequest,
            object_id: str,
            from_field: str | None = None,
        ) -> dict[str, Any] | None:
            """Retrieve a single entity by ID.

            Args:
                request: Django HTTP request.
                object_id: Entity ID.
                from_field: Field to look up by (defaults to 'id').

            Returns:
                Entity dict or None if not found.
            """
            try:
                queryset = self.get_queryset(request)
                field = from_field or "id"
                return queryset.get(**{field: object_id})
            except (DoesNotExist, CiviError):
                return None

        def get_title(self, request: HttpRequest) -> str:
            """Get page title for the admin view."""
            return self.opts.verbose_name_plural.title()

        def get_urls(self) -> list[Any]:
            """Return URL patterns for this admin."""
            info = self.opts.app_label, self.opts.model_name

            return [
                path("", self.admin_site.admin_view(self.changelist_view), name=f"{info[0]}_{info[1]}_changelist"),
                path("add/", self.admin_site.admin_view(self.add_view), name=f"{info[0]}_{info[1]}_add"),
                path(
                    "<path:object_id>/history/",
                    self.admin_site.admin_view(self.history_view),
                    name=f"{info[0]}_{info[1]}_history",
                ),
                path(
                    "<path:object_id>/delete/",
                    self.admin_site.admin_view(self.delete_view),
                    name=f"{info[0]}_{info[1]}_delete",
                ),
                path(
                    "<path:object_id>/change/",
                    self.admin_site.admin_view(self.change_view),
                    name=f"{info[0]}_{info[1]}_change",
                ),
            ]

        @property
        def urls(self) -> list[Any]:
            """Return URL patterns."""
            return self.get_urls()

        def changelist_view(
            self,
            request: HttpRequest,
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display the list of entities.

            Args:
                request: Django HTTP request.
                extra_context: Additional template context.

            Returns:
                Rendered changelist page.
            """
            try:
                cl = CiviChangeList(
                    request=request,
                    model=self.entity_class,
                    list_display=self.get_list_display(request),
                    list_display_links=self.get_list_display_links(request, self.list_display),
                    list_filter=self.list_filter,
                    date_hierarchy=None,
                    search_fields=self.search_fields,
                    list_select_related=False,
                    list_per_page=self.list_per_page,
                    list_max_show_all=self.list_max_show_all,
                    list_editable=(),
                    model_admin=self,
                    sortable_by=self.get_sortable_by(request),
                )
            except CiviError as e:
                self.message_user(request, f"CiviCRM Error: {e}", messages.ERROR)
                cl = None

            context = {
                **self.admin_site.each_context(request),
                "module_name": self.opts.verbose_name_plural,
                "title": self.get_title(request),
                "subtitle": None,
                "is_popup": cl.is_popup if cl else False,
                "to_field": cl.to_field if cl else None,
                "cl": cl,
                "has_add_permission": self.has_add_permission(request),
                "opts": self.opts,
                "preserved_filters": self.get_preserved_filters(request),
                **(extra_context or {}),
            }

            request.current_app = self.admin_site.name
            return TemplateResponse(request, self.change_list_template or "admin/change_list.html", context)

        def get_list_display(self, request: HttpRequest) -> Sequence[str]:
            """Return list of fields to display."""
            return self.list_display

        def get_list_display_links(
            self,
            request: HttpRequest,
            list_display: Sequence[str],
        ) -> Sequence[str]:
            """Return list of fields that link to change view."""
            if self.list_display_links is not None:
                return self.list_display_links
            # Default: first non-action field links to change view
            for field in list_display:
                if field != "action_checkbox":
                    return (field,)
            return ()

        def get_sortable_by(self, request: HttpRequest) -> Sequence[str]:
            """Return fields that can be sorted."""
            return list(self.list_display)

        def get_preserved_filters(self, request: HttpRequest) -> str:
            """Get preserved filters for navigation."""
            preserved_filters = request.GET.urlencode()
            if preserved_filters:
                return f"_changelist_filters={preserved_filters}"
            return ""

        def add_view(
            self,
            request: HttpRequest,
            form_url: str = "",
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display the add form.

            Args:
                request: Django HTTP request.
                form_url: Form submission URL.
                extra_context: Additional template context.

            Returns:
                Rendered add page or redirect.
            """
            return self._changeform_view(request, None, form_url, extra_context)

        def change_view(
            self,
            request: HttpRequest,
            object_id: str,
            form_url: str = "",
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display the change form.

            Args:
                request: Django HTTP request.
                object_id: Entity ID to change.
                form_url: Form submission URL.
                extra_context: Additional template context.

            Returns:
                Rendered change page or redirect.
            """
            return self._changeform_view(request, object_id, form_url, extra_context)

        def _changeform_view(
            self,
            request: HttpRequest,
            object_id: str | None,
            form_url: str,
            extra_context: dict[str, Any] | None,
        ) -> HttpResponse:
            """Handle add/change form views.

            Args:
                request: Django HTTP request.
                object_id: Entity ID (None for add).
                form_url: Form submission URL.
                extra_context: Additional template context.

            Returns:
                Rendered form page or redirect after save.
            """
            add = object_id is None

            if add:
                if not self.has_add_permission(request):
                    raise PermissionDenied
                obj = None
            else:
                if not self.has_change_permission(request):
                    raise PermissionDenied
                obj = self.get_object(request, object_id)
                if obj is None:
                    msg = f"{self.opts.verbose_name} with ID {object_id!r} not found."
                    raise Http404(msg)

            if request.method == "POST":
                return self._handle_post(request, obj, add)

            # Build form
            form = self._build_form(obj)

            # Wrap obj in CiviRecord for nice string representation in breadcrumbs
            wrapped_obj = CiviRecord(obj, self.opts) if obj else None

            context = {
                **self.admin_site.each_context(request),
                "title": (_("Add %s") if add else _("Change %s")) % self.opts.verbose_name,
                "subtitle": None if add else str(wrapped_obj),
                "form": form,
                "object_id": object_id,
                "original": wrapped_obj,
                "is_popup": IS_POPUP_VAR in request.GET,
                "to_field": request.GET.get(TO_FIELD_VAR),
                "has_add_permission": self.has_add_permission(request),
                "has_change_permission": self.has_change_permission(request, obj),
                "has_delete_permission": self.has_delete_permission(request, obj),
                "has_view_permission": self.has_view_permission(request, obj),
                "add": add,
                "change": not add,
                "opts": self.opts,
                "preserved_filters": self.get_preserved_filters(request),
                "save_as": False,
                "show_save": True,
                "show_save_and_continue": True,
                "show_save_and_add_another": True,
                "show_delete": not add and self.has_delete_permission(request, obj),
                # Required by Django admin change_form.html template
                "has_editable_inline_admin_formsets": False,
                "inline_admin_formsets": [],
                "errors": [],
                "media": form.media if hasattr(form, "media") else "",
                "adminform": self._build_adminform(form, obj),
                "show_close": False,
                "has_absolute_url": False,
                "content_type_id": None,
                "save_on_top": False,
                **(extra_context or {}),
            }

            request.current_app = self.admin_site.name
            return TemplateResponse(
                request,
                self.change_form_template or "admin/change_form.html",
                context,
            )

        def _build_form(self, obj: dict[str, Any] | None) -> Any:
            """Build form for entity.

            Args:
                obj: Entity data dict or None for new entity.

            Returns:
                Django form instance.
            """
            from django import forms

            # Build form fields from entity fields
            form_fields: dict[str, forms.Field] = {}

            for field in self.opts.get_fields():
                if field.name.startswith("_"):
                    continue
                if self.exclude and field.name in self.exclude:
                    continue
                if self.fields and field.name not in self.fields:
                    continue
                if field.name in self.readonly_fields:
                    continue

                form_fields[field.name] = field.formfield()

            # Create form class dynamically
            form_class = type("CiviEntityForm", (forms.Form,), form_fields)

            # Populate with initial data
            initial = obj or {}
            return form_class(initial=initial)

        def _build_adminform(self, form: Any, obj: dict[str, Any] | None) -> Any:
            """Build AdminForm wrapper for Django admin templates.

            Args:
                form: The Django form instance.
                obj: Entity data dict or None for new entity.

            Returns:
                AdminForm-like object for template rendering.
            """
            from django.contrib.admin.helpers import AdminForm

            # Build fieldsets - group all fields together
            fieldsets = [(None, {"fields": list(form.fields.keys())})]

            return AdminForm(
                form,
                fieldsets,
                prepopulated_fields={},
                readonly_fields=self.readonly_fields,
                model_admin=self,
            )

        def _handle_post(
            self,
            request: HttpRequest,
            obj: dict[str, Any] | None,
            add: bool,
        ) -> HttpResponse:
            """Handle POST request for add/change.

            Args:
                request: Django HTTP request.
                obj: Existing entity or None for add.
                add: True if adding new entity.

            Returns:
                Redirect response after save.
            """
            try:
                entity_name = self.opts.object_name
                client = self.get_client()

                # Get field values from POST
                values: dict[str, Any] = {}
                for field in self.opts.get_fields():
                    if field.name in request.POST:
                        value = request.POST.get(field.name)
                        if value:
                            # Type coercion
                            if field.field_type is int:
                                value = int(value)
                            elif field.field_type is bool:
                                value = value.lower() in ("true", "1", "yes", "on")
                            values[field.name] = value

                if add:
                    # Create new entity
                    response = client.create(entity_name, values)
                    if response.values:
                        new_id = response.values[0].get("id")
                        self.message_user(request, f"{entity_name} created successfully.", messages.SUCCESS)
                    else:
                        self.message_user(request, f"{entity_name} created.", messages.SUCCESS)
                        new_id = None
                else:
                    # Update existing entity
                    entity_id = obj.get("id") if obj else None
                    if entity_id:
                        values["id"] = entity_id
                        client.update(entity_name, values, [["id", "=", entity_id]])
                        self.message_user(request, f"{entity_name} updated successfully.", messages.SUCCESS)
                    new_id = entity_id

                # Determine redirect
                if "_addanother" in request.POST:
                    return HttpResponseRedirect(
                        reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_add"),
                    )
                if "_continue" in request.POST and new_id:
                    return HttpResponseRedirect(
                        reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_change", args=(new_id,)),
                    )
                return HttpResponseRedirect(
                    reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"),
                )

            except CiviAPIError as e:
                self.message_user(request, f"CiviCRM API Error: {e}", messages.ERROR)
                return self._changeform_view(request, str(obj.get("id")) if obj else None, "", None)
            except CiviError as e:
                self.message_user(request, f"CiviCRM Error: {e}", messages.ERROR)
                return self._changeform_view(request, str(obj.get("id")) if obj else None, "", None)

        def delete_view(
            self,
            request: HttpRequest,
            object_id: str,
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display delete confirmation or process deletion.

            Args:
                request: Django HTTP request.
                object_id: Entity ID to delete.
                extra_context: Additional template context.

            Returns:
                Rendered delete confirmation or redirect.
            """
            obj = self.get_object(request, object_id)
            if obj is None:
                raise Http404(f"{self.opts.verbose_name} with ID {object_id!r} not found.")

            if not self.has_delete_permission(request, obj):
                raise PermissionDenied

            if request.method == "POST":
                try:
                    entity_name = self.opts.object_name
                    client = self.get_client()
                    client.delete(entity_name, [["id", "=", int(object_id)]])
                    self.message_user(request, f"{entity_name} deleted successfully.", messages.SUCCESS)
                    return HttpResponseRedirect(
                        reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"),
                    )
                except CiviError as e:
                    self.message_user(request, f"CiviCRM Error: {e}", messages.ERROR)

            # Wrap obj in CiviRecord so template can access .pk
            wrapped_obj = CiviRecord(obj, self.opts)

            context = {
                **self.admin_site.each_context(request),
                "title": _("Delete %s") % self.opts.verbose_name,
                "object": wrapped_obj,
                "object_name": self.opts.verbose_name,
                "opts": self.opts,
                "app_label": self.opts.app_label,
                "preserved_filters": self.get_preserved_filters(request),
                "is_popup": IS_POPUP_VAR in request.GET,
                "to_field": request.GET.get(TO_FIELD_VAR),
                "deleted_objects": [str(wrapped_obj)],
                "model_count": [(self.opts.verbose_name, 1)],  # List of (name, count) tuples
                "perms_lacking": [],
                "protected": [],
                **(extra_context or {}),
            }

            request.current_app = self.admin_site.name
            return TemplateResponse(
                request,
                self.delete_confirmation_template or "admin/delete_confirmation.html",
                context,
            )

        def history_view(
            self,
            request: HttpRequest,
            object_id: str,
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display entity history (placeholder).

            CiviCRM doesn't have built-in change history like Django,
            so this displays a message indicating history is unavailable.

            Args:
                request: Django HTTP request.
                object_id: Entity ID.
                extra_context: Additional template context.

            Returns:
                Rendered history page.
            """
            obj = self.get_object(request, object_id)
            if obj is None:
                raise Http404(f"{self.opts.verbose_name} with ID {object_id!r} not found.")

            # Wrap in CiviRecord so template can access .pk
            wrapped_obj = CiviRecord(obj, self.opts)

            context = {
                **self.admin_site.each_context(request),
                "title": _("History: %s") % obj.get("display_name", obj.get("id", object_id)),
                "object": wrapped_obj,
                "opts": self.opts,
                "action_list": [],  # CiviCRM doesn't track admin history
                "module_name": self.opts.verbose_name,
                "preserved_filters": self.get_preserved_filters(request),
                **(extra_context or {}),
            }

            request.current_app = self.admin_site.name
            return TemplateResponse(
                request,
                self.object_history_template or "admin/object_history.html",
                context,
            )

        def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
            """Check if user can add entities.

            CiviCRM handles its own authorization, so we allow all staff/superusers
            to access the admin interface. The actual permission check happens
            at the CiviCRM API level.
            """
            if request.user.is_superuser:
                return True
            if request.user.is_staff:
                return True
            return request.user.has_perm(f"{self.opts.app_label}.add_{self.opts.model_name}")

        def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
            """Check if user can change entities."""
            if request.user.is_superuser:
                return True
            if request.user.is_staff:
                return True
            return request.user.has_perm(f"{self.opts.app_label}.change_{self.opts.model_name}")

        def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
            """Check if user can delete entities."""
            if request.user.is_superuser:
                return True
            if request.user.is_staff:
                return True
            return request.user.has_perm(f"{self.opts.app_label}.delete_{self.opts.model_name}")

        def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
            """Check if user can view entities."""
            if request.user.is_superuser:
                return True
            if request.user.is_staff:
                return True
            return request.user.has_perm(f"{self.opts.app_label}.view_{self.opts.model_name}")

        def has_module_permission(self, request: HttpRequest) -> bool:
            """Check if user can access this module."""
            return request.user.is_active and request.user.is_staff

        def lookup_allowed(self, lookup: str, value: Any) -> bool:
            """Check if a filter lookup is allowed."""
            return True

        def get_changelist(self, request: HttpRequest, **kwargs: Any) -> type[CiviChangeList]:
            """Return the ChangeList class to use."""
            return CiviChangeList

        def message_user(
            self,
            request: HttpRequest,
            message: str,
            level: int = messages.INFO,
            extra_tags: str = "",
            fail_silently: bool = False,
        ) -> None:
            """Send a message to the user."""
            messages.add_message(request, level, message, extra_tags=extra_tags, fail_silently=fail_silently)

    class CiviInlineAdmin(Generic[EntityT]):
        """Inline admin for related CiviCRM entities.

        Allows editing related entities (e.g., Contact's emails, phones)
        directly within the parent entity's change form.

        Attributes:
            entity_class: The related CiviCRM entity class.
            fk_name: Foreign key field linking to parent entity.
            extra: Number of extra blank forms to show.
            max_num: Maximum number of inline items.
            min_num: Minimum number of inline items.
            fields: Fields to display.
            readonly_fields: Read-only fields.

        Example:
            >>> class EmailInline(CiviInlineAdmin):
            ...     entity_class = Email
            ...     fk_name = "contact_id"
            ...     fields = ["email", "is_primary", "location_type_id"]
            >>> class ContactAdmin(CiviModelAdmin):
            ...     inlines = [EmailInline]
        """

        entity_class: type[EntityT]
        fk_name: str = ""
        extra: int = 1
        max_num: int | None = None
        min_num: int | None = None
        fields: Sequence[str] | None = None
        readonly_fields: Sequence[str] = ()
        verbose_name: str | None = None
        verbose_name_plural: str | None = None
        template: str = "admin/edit_inline/tabular.html"

        def __init__(self, parent_model: type[BaseEntity], admin_site: admin.AdminSite) -> None:
            """Initialize inline admin.

            Args:
                parent_model: The parent entity class.
                admin_site: Django admin site.
            """
            self.parent_model = parent_model
            self.admin_site = admin_site
            # Use existing _meta if available
            if hasattr(self.entity_class, "_meta") and isinstance(self.entity_class._meta, CiviOptions):
                self.opts = self.entity_class._meta
            else:
                self.opts = CiviOptions(self.entity_class)

            if self.verbose_name is None:
                self.verbose_name = self.opts.verbose_name
            if self.verbose_name_plural is None:
                self.verbose_name_plural = self.opts.verbose_name_plural

        def get_queryset(self, request: HttpRequest, parent_id: int) -> CiviQuerySet[EntityT]:
            """Get related entities for parent.

            Args:
                request: Django HTTP request.
                parent_id: Parent entity ID.

            Returns:
                CiviQuerySet filtered to related entities.
            """
            client = CiviModelAdmin.get_client()
            return CiviQuerySet(
                entity_class=self.entity_class,
                client=client,
            ).filter(**{self.fk_name: parent_id})

        def get_formset(self, request: HttpRequest, obj: dict[str, Any] | None = None) -> Any:
            """Build formset for inline editing.

            Args:
                request: Django HTTP request.
                obj: Parent entity dict.

            Returns:
                Formset for inline entities.
            """
            from django import forms
            from django.forms import formset_factory

            # Build form fields
            form_fields: dict[str, forms.Field] = {}
            display_fields = self.fields or [f.name for f in self.opts.get_fields() if not f.name.startswith("_")]

            for field_name in display_fields:
                field = self.opts.get_field(field_name)
                if field_name not in self.readonly_fields:
                    form_fields[field_name] = field.formfield()

            # Create inline form class
            InlineForm = type("CiviInlineForm", (forms.Form,), form_fields)

            # Create formset
            FormSet = formset_factory(
                InlineForm,
                extra=self.extra,
                max_num=self.max_num,
                min_num=self.min_num,
            )

            # Get initial data
            initial = []
            if obj:
                parent_id = obj.get("id")
                if parent_id:
                    qs = self.get_queryset(request, parent_id)
                    initial = list(qs)

            if request.method == "POST":
                return FormSet(request.POST, initial=initial, prefix=self.opts.model_name)
            return FormSet(initial=initial, prefix=self.opts.model_name)

    class CiviAdminSite(admin.AdminSite):
        """Custom admin site for CiviCRM entities.

        Provides a separate admin site specifically for CiviCRM data,
        allowing it to coexist with Django's default admin.

        Example:
            >>> civi_admin_site = CiviAdminSite(name="civiadmin")
            >>> civi_admin_site.register(Contact, ContactAdmin)
            >>>
            >>> # In urls.py:
            >>> urlpatterns = [
            ...     path("civiadmin/", civi_admin_site.urls),
            ... ]
        """

        site_header = "CiviCRM Administration"
        site_title = "CiviCRM Admin"
        index_title = "CiviCRM Entities"

        def __init__(self, name: str = "civiadmin") -> None:
            """Initialize CiviAdminSite."""
            super().__init__(name)
            self._entity_registry: dict[type[BaseEntity], type[CiviModelAdmin[Any]]] = {}

        def register(
            self,
            entity_class: type[BaseEntity],
            admin_class: type[CiviModelAdmin[Any]] | None = None,
            **options: Any,
        ) -> None:
            """Register a CiviCRM entity with the admin site.

            Args:
                entity_class: The entity class to register.
                admin_class: Optional custom admin class.
                **options: Additional options for the admin class.
            """
            if admin_class is None:
                admin_class = CiviModelAdmin

            # Create admin instance with entity class bound (validates admin_class is compatible)
            admin_class(model=entity_class, admin_site=self)

            # Store in our custom registry (not Django's _registry which expects model classes)
            self._entity_registry[entity_class] = admin_class

        def unregister(self, entity_class: type[BaseEntity]) -> None:
            """Unregister a CiviCRM entity from the admin site.

            Args:
                entity_class: The entity class to unregister.
            """
            if entity_class in self._entity_registry:
                del self._entity_registry[entity_class]

        def get_urls(self) -> list[Any]:
            """Get URL patterns for all registered entities."""
            urls = [
                path("", self.index, name="index"),
            ]

            # Add URLs for each registered entity directly (no sub-namespaces)
            for entity_class, admin_class in self._entity_registry.items():
                entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
                admin_instance = admin_class(model=entity_class, admin_site=self)
                prefix = f"{entity_name.lower()}/"

                # Add each URL with the entity prefix
                for url_pattern in admin_instance.urls:
                    # Get the route string from the pattern
                    route = (
                        url_pattern.pattern._route
                        if hasattr(url_pattern.pattern, "_route")
                        else str(url_pattern.pattern)
                    )
                    urls.append(
                        path(f"{prefix}{route}", url_pattern.callback, name=url_pattern.name),
                    )

            return urls

        @property
        def urls(self) -> tuple[list[Any], str, str]:
            """Return URL configuration."""
            return self.get_urls(), "civiadmin", self.name

        def index(
            self,
            request: HttpRequest,
            extra_context: dict[str, Any] | None = None,
        ) -> HttpResponse:
            """Display the main admin index page.

            Override Django's default index to properly handle CiviCRM entities
            which don't have Django model _meta attributes.
            """
            # Build app list manually for CiviCRM entities
            app_list = []

            if self._entity_registry:
                model_list = []
                for entity_class, admin_class in self._entity_registry.items():
                    entity_name = getattr(entity_class, "__entity_name__", entity_class.__name__)
                    opts = CiviOptions(entity_class)

                    # Check permissions
                    admin_instance = admin_class(model=entity_class, admin_site=self)
                    perms = {
                        "add": admin_instance.has_add_permission(request),
                        "change": admin_instance.has_change_permission(request),
                        "delete": admin_instance.has_delete_permission(request),
                        "view": admin_instance.has_view_permission(request),
                    }

                    if any(perms.values()):
                        model_list.append(
                            {
                                "model": entity_class,
                                "name": opts.verbose_name,
                                "object_name": entity_name,
                                "perms": perms,
                                "admin_url": reverse(
                                    f"{self.name}:{opts.app_label}_{opts.model_name}_changelist",
                                ),
                                "add_url": reverse(
                                    f"{self.name}:{opts.app_label}_{opts.model_name}_add",
                                )
                                if perms["add"]
                                else None,
                                "view_only": not perms["change"] and not perms["add"],
                            }
                        )

                if model_list:
                    # Use app_label from first model's opts
                    first_opts = model_list[0].get("model")
                    app_lbl = first_opts._meta.app_label if hasattr(first_opts, "_meta") else "civi"
                    app_list.append(
                        {
                            "name": "CiviCRM",
                            "app_label": app_lbl,
                            "app_url": "#",
                            "has_module_perms": True,
                            "models": sorted(model_list, key=lambda x: x["name"]),
                        }
                    )

            context = {
                **self.each_context(request),
                "title": self.index_title,
                "subtitle": None,
                "app_list": app_list,
                **(extra_context or {}),
            }

            request.current_app = self.name
            return TemplateResponse(request, "admin/index.html", context)

    def register_entity(
        entity_class: type[EntityT],
        site: admin.AdminSite | CiviAdminSite | None = None,
        app_label: str | None = None,
    ) -> Callable[[type[CiviModelAdmin[EntityT]]], type[CiviModelAdmin[EntityT]]]:
        """Decorator to register an entity admin class.

        Usage:
            >>> from django.contrib import admin
            >>> @register_entity(Contact, site=admin.site, app_label="myapp")
            ... class ContactAdmin(CiviModelAdmin):
            ...     list_display = ["id", "display_name"]

        Args:
            entity_class: The CiviCRM entity class to register.
            site: Admin site to register with. Can be:
                - django.contrib.admin.site (default Django admin)
                - A CiviAdminSite instance
                - None (just store in registry, don't auto-register)
            app_label: Django app label to use (must be an installed app).
                Required when registering with Django's default admin.site.

        Returns:
            Decorator function.
        """

        def decorator(admin_class: type[CiviModelAdmin[EntityT]]) -> type[CiviModelAdmin[EntityT]]:
            admin_class.entity_class = entity_class
            _entity_admin_registry[entity_class] = admin_class

            # Determine app_label - default to "civi" which matches CiviAppConfig.label
            label = app_label or "civi"

            # Attach _meta to the entity class so Django admin can work with it
            if not hasattr(entity_class, "_meta"):
                entity_class._meta = CiviOptions(entity_class, app_label=label)  # type: ignore[attr-defined]
            elif app_label:
                # Update existing _meta with new app_label
                entity_class._meta.app_label = label  # type: ignore[attr-defined]

            # Also update the admin class opts
            admin_class.opts = CiviOptions(entity_class, app_label=label)  # type: ignore[attr-defined]

            # Register with site if provided
            if site is not None:
                if isinstance(site, CiviAdminSite):
                    site.register(entity_class, admin_class)
                else:
                    # Register with Django's default admin site
                    admin_instance = admin_class(model=entity_class, admin_site=site)
                    admin_instance.opts = CiviOptions(entity_class, app_label=label)
                    site._registry[entity_class] = admin_instance

            return admin_class

        return decorator

    def autodiscover_entities(site: CiviAdminSite | None = None) -> None:
        """Auto-discover and register entity admin classes.

        Similar to Django's admin.autodiscover(), this imports admin modules
        from installed apps looking for CiviCRM entity registrations.

        Args:
            site: Optional CiviAdminSite to register with.
        """
        from django.apps import apps
        from django.utils.module_loading import module_has_submodule

        for app_config in apps.get_app_configs():
            if module_has_submodule(app_config.module, "civiadmin"):
                try:
                    __import__(f"{app_config.name}.civiadmin")
                except ImportError:
                    pass

    # Default admin site instance
    civi_admin_site = CiviAdminSite()

else:
    # Stubs for when Django is not available
    _DJANGO_REQUIRED_MSG = "Django required: pip install civi-py[django]"

    class CiviPaginator:  # type: ignore[no-redef]
        """Stub when Django is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_DJANGO_REQUIRED_MSG)

    class CiviChangeList:  # type: ignore[no-redef]
        """Stub when Django is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_DJANGO_REQUIRED_MSG)

    class CiviModelAdmin(Generic[EntityT]):  # type: ignore[no-redef]
        """Stub when Django is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_DJANGO_REQUIRED_MSG)

    class CiviInlineAdmin(Generic[EntityT]):  # type: ignore[no-redef]
        """Stub when Django is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_DJANGO_REQUIRED_MSG)

    class CiviAdminSite:  # type: ignore[no-redef]
        """Stub when Django is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(_DJANGO_REQUIRED_MSG)

    # Instance is None when Django unavailable since we can't instantiate the stub
    civi_admin_site = None  # type: ignore[assignment]

    def register_entity(
        entity_class: type[EntityT],
        site: Any = None,
        app_label: str | None = None,
    ) -> Callable[[type[Any]], type[Any]]:
        """Stub for register_entity when Django is not available."""

        def decorator(admin_class: type[Any]) -> type[Any]:
            return admin_class

        return decorator

    def autodiscover_entities(site: Any = None) -> None:
        """Stub for autodiscover_entities when Django is not available."""


__all__ = [
    "CiviAdminSite",
    "CiviChangeList",
    "CiviField",
    "CiviInlineAdmin",
    "CiviModelAdmin",
    "CiviOptions",
    "CiviPaginator",
    "CiviQuerySet",
    "autodiscover_entities",
    "civi_admin_site",
    "register_entity",
]
