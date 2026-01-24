"""Django-ORM-like QuerySet for CiviCRM API v4.

Provides lazy, chainable query building with type-safe execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from civicrm_py.core.exceptions import CiviAPIError, CiviNotFoundError
from civicrm_py.core.serialization import APIRequest, APIResponse

if TYPE_CHECKING:
    from civicrm_py.core.client import CiviClient


# Field lookup operators mapping
LOOKUP_OPERATORS = {
    "exact": "=",
    "contains": "CONTAINS",
    "startswith": "LIKE",
    "endswith": "LIKE",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "in": "IN",
    "isnull": "IS NULL",
    "not": "!=",
}


class QuerySet:
    """Lazy, chainable query builder for CiviCRM entities.

    Inspired by Django's QuerySet API. Queries are not executed until
    consumed by methods like all(), first(), count(), or iteration.

    Example:
        >>> qs = QuerySet(client, "Contact")
        >>> qs = qs.filter(last_name__contains="Smith", is_deleted=False)
        >>> qs = qs.select("id", "display_name", "email_primary.email")
        >>> qs = qs.order_by("-created_date")
        >>> contacts = await qs.all()

    Field Lookups:
        - exact: Exact match (default if no lookup specified)
        - contains: CONTAINS operator
        - startswith: LIKE 'value%'
        - endswith: LIKE '%value'
        - gt: Greater than
        - gte: Greater than or equal
        - lt: Less than
        - lte: Less than or equal
        - in: IN operator (value must be a list)
        - isnull: IS NULL (value must be bool)
        - not: Not equal
    """

    def __init__(
        self,
        client: CiviClient,
        entity: str,
        *,
        _select: list[str] | None = None,
        _where: list[list[Any]] | None = None,
        _order_by: dict[str, str] | None = None,
        _limit: int | None = None,
        _offset: int | None = None,
        _join: list[list[Any]] | None = None,
        _group_by: list[str] | None = None,
        _having: list[list[Any]] | None = None,
        _values_fields: list[str] | None = None,
        _values_list_fields: list[str] | None = None,
        _flat: bool = False,
    ) -> None:
        """Initialize QuerySet.

        Args:
            client: CiviClient instance for executing queries.
            entity: CiviCRM entity name (e.g., 'Contact', 'Activity').
            _select: Fields to return (internal).
            _where: Filter conditions (internal).
            _order_by: Sort order (internal).
            _limit: Max records (internal).
            _offset: Skip records (internal).
            _join: Join clauses (internal).
            _group_by: Group by fields (internal).
            _having: Having clauses (internal).
            _values_fields: Fields for values() (internal).
            _values_list_fields: Fields for values_list() (internal).
            _flat: Flatten values_list to single values (internal).
        """
        self._client = client
        self._entity = entity
        self._select = _select
        self._where = _where or []
        self._order_by = _order_by or {}
        self._limit = _limit
        self._offset = _offset
        self._join = _join or []
        self._group_by = _group_by or []
        self._having = _having or []
        self._values_fields = _values_fields
        self._values_list_fields = _values_list_fields
        self._flat = _flat

    def _clone(self, **kwargs: Any) -> Self:  # noqa: ANN401
        """Create a copy of this QuerySet with updated parameters.

        Args:
            **kwargs: Parameters to update in the clone.

        Returns:
            New QuerySet instance with updated parameters.
        """
        params = {
            "client": self._client,
            "entity": self._entity,
            "_select": self._select,
            "_where": self._where.copy(),
            "_order_by": self._order_by.copy(),
            "_limit": self._limit,
            "_offset": self._offset,
            "_join": self._join.copy(),
            "_group_by": self._group_by.copy(),
            "_having": self._having.copy(),
            "_values_fields": self._values_fields,
            "_values_list_fields": self._values_list_fields,
            "_flat": self._flat,
        }
        params.update(kwargs)
        return self.__class__(**params)  # type: ignore[arg-type]

    def _parse_lookup(self, key: str, value: Any) -> list[Any]:  # noqa: ANN401
        """Parse field lookup into CiviCRM WHERE clause.

        Args:
            key: Field name with optional lookup (e.g., 'age__gt').
            value: Filter value.

        Returns:
            WHERE clause as [field, operator, value].

        Examples:
            >>> _parse_lookup("last_name__contains", "Smith")
            ['last_name', 'CONTAINS', 'Smith']
            >>> _parse_lookup("age__gt", 21)
            ['age', '>', 21]
            >>> _parse_lookup("is_deleted", False)
            ['is_deleted', '=', False]
        """
        parts = key.split("__")
        field = parts[0]

        # No lookup specified, use exact match
        if len(parts) == 1:
            return [field, "=", value]

        lookup = parts[1]

        # Handle special cases
        if lookup == "isnull":
            operator = "IS NULL" if value else "IS NOT NULL"
            return [field, operator]

        if lookup == "startswith":
            return [field, "LIKE", f"{value}%"]

        if lookup == "endswith":
            return [field, "LIKE", f"%{value}"]

        # Standard operators
        operator = LOOKUP_OPERATORS.get(lookup, "=")
        return [field, operator, value]

    def filter(self, **kwargs: Any) -> Self:  # noqa: ANN401
        """Add WHERE conditions (AND logic).

        Args:
            **kwargs: Field lookups (e.g., last_name__contains='Smith').

        Returns:
            New QuerySet with added filters.

        Example:
            >>> qs.filter(last_name__contains="Smith", is_deleted=False)
        """
        where = self._where.copy()
        for key, value in kwargs.items():
            where.append(self._parse_lookup(key, value))
        return self._clone(_where=where)

    def exclude(self, **kwargs: Any) -> Self:  # noqa: ANN401
        """Add NOT WHERE conditions.

        Args:
            **kwargs: Field lookups to exclude.

        Returns:
            New QuerySet with added exclusions.

        Example:
            >>> qs.exclude(is_deleted=True)
        """
        where = self._where.copy()
        for key, value in kwargs.items():
            condition = self._parse_lookup(key, value)
            # Wrap in NOT
            where.append(["NOT", [condition]])
        return self._clone(_where=where)

    def select(self, *fields: str) -> Self:
        """Specify fields to return.

        Args:
            *fields: Field names to select.

        Returns:
            New QuerySet with field selection.

        Example:
            >>> qs.select("id", "display_name", "email_primary.email")
        """
        return self._clone(_select=list(fields) if fields else None)

    def order_by(self, *fields: str) -> Self:
        """Set sort order.

        Args:
            *fields: Field names. Prefix with '-' for descending order.

        Returns:
            New QuerySet with sort order.

        Example:
            >>> qs.order_by("-created_date", "last_name")
        """
        order_by = {}
        for field in fields:
            if field.startswith("-"):
                order_by[field[1:]] = "DESC"
            else:
                order_by[field] = "ASC"
        return self._clone(_order_by=order_by)

    def limit(self, n: int) -> Self:
        """Limit number of records returned.

        Args:
            n: Maximum records to return.

        Returns:
            New QuerySet with limit.

        Example:
            >>> qs.limit(10)
        """
        return self._clone(_limit=n)

    def offset(self, n: int) -> Self:
        """Skip first n records.

        Args:
            n: Number of records to skip.

        Returns:
            New QuerySet with offset.

        Example:
            >>> qs.offset(20)
        """
        return self._clone(_offset=n)

    def join(self, entity: str, on_field: str, alias: str | None = None) -> Self:
        """Add a JOIN clause for related entities.

        Args:
            entity: Entity name to join.
            on_field: Field name for the join relationship.
            alias: Optional alias for the joined entity.

        Returns:
            New QuerySet with join.

        Example:
            >>> qs.join("Email", "email_primary", "email")
        """
        join = self._join.copy()
        join_clause = [entity, on_field]
        if alias:
            join_clause.append(alias)
        join.append(join_clause)
        return self._clone(_join=join)

    def group_by(self, *fields: str) -> Self:
        """Add GROUP BY clause.

        Args:
            *fields: Fields to group by.

        Returns:
            New QuerySet with group by.

        Example:
            >>> qs.group_by("contact_type")
        """
        group_by = self._group_by.copy()
        group_by.extend(fields)
        return self._clone(_group_by=group_by)

    def having(self, **kwargs: Any) -> Self:  # noqa: ANN401
        """Add HAVING conditions for aggregations.

        Args:
            **kwargs: Field lookups for HAVING clause.

        Returns:
            New QuerySet with having conditions.

        Example:
            >>> qs.having(count__gt=5)
        """
        having = self._having.copy()
        for key, value in kwargs.items():
            having.append(self._parse_lookup(key, value))
        return self._clone(_having=having)

    def values(self, *fields: str) -> Self:
        """Return dictionaries instead of entity objects.

        Args:
            *fields: Fields to include in dictionaries.

        Returns:
            New QuerySet that returns dicts.

        Example:
            >>> await qs.values("id", "display_name")
            [{'id': 1, 'display_name': 'John Doe'}, ...]
        """
        return self._clone(_values_fields=list(fields))

    def values_list(self, *fields: str, flat: bool = False) -> Self:
        """Return tuples or flat list instead of entity objects.

        Args:
            *fields: Fields to include in tuples.
            flat: If True and only one field, return flat list of values.

        Returns:
            New QuerySet that returns tuples or list.

        Example:
            >>> await qs.values_list("id", "display_name")
            [(1, 'John Doe'), (2, 'Jane Smith'), ...]
            >>> await qs.values_list("id", flat=True)
            [1, 2, 3, ...]
        """
        return self._clone(
            _values_list_fields=list(fields),
            _flat=flat,
        )

    def _build_params(self) -> APIRequest:
        """Build APIRequest from current QuerySet state.

        Returns:
            APIRequest ready for execution.
        """
        return APIRequest(
            select=self._select,
            where=self._where if self._where else None,
            orderBy=self._order_by if self._order_by else None,
            limit=self._limit,
            offset=self._offset,
            join=self._join if self._join else None,
            groupBy=self._group_by if self._group_by else None,
            having=self._having if self._having else None,
        )

    def _process_values(self, response: APIResponse[dict[str, Any]]) -> list[Any]:  # noqa: PLR0911
        """Process response values based on values()/values_list() mode.

        Args:
            response: API response with values.

        Returns:
            Processed values (dicts, tuples, or flat list).
        """
        if response.values is None:
            return []

        # values() mode - return dicts with selected fields
        if self._values_fields is not None:
            if not self._values_fields:
                # No fields specified, return all
                return response.values
            return [{field: item.get(field) for field in self._values_fields} for item in response.values]

        # values_list() mode - return tuples or flat list
        if self._values_list_fields is not None:
            if not self._values_list_fields:
                # No fields specified, return all as tuples
                return [tuple(item.values()) for item in response.values]

            # Single field with flat=True
            if len(self._values_list_fields) == 1 and self._flat:
                field = self._values_list_fields[0]
                return [item.get(field) for item in response.values]

            # Multiple fields or not flat
            return [tuple(item.get(field) for field in self._values_list_fields) for item in response.values]

        # Standard dict response
        return response.values

    async def all(self) -> list[Any]:
        """Execute query and return all results.

        Returns:
            List of entity dicts, processed according to values()/values_list().

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.
        """
        params = self._build_params()
        response = await self._client.request(self._entity, "get", params)
        return self._process_values(response)

    async def first(self) -> dict[str, Any] | tuple[Any, ...] | Any | None:  # noqa: ANN401
        """Execute query and return first result.

        Returns:
            First entity dict/tuple/value or None if no results.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.
        """
        # Clone with limit=1 to avoid fetching unnecessary records
        qs = self.limit(1)
        params = qs._build_params()  # noqa: SLF001
        response = await self._client.request(self._entity, "get", params)
        values = self._process_values(response)
        return values[0] if values else None

    async def count(self) -> int:
        """Execute query and return count of results.

        Returns:
            Total count of matching records.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.
        """
        # Build params without select/limit/offset for accurate count
        params = APIRequest(
            where=self._where if self._where else None,
            join=self._join if self._join else None,
            groupBy=self._group_by if self._group_by else None,
            having=self._having if self._having else None,
        )
        response = await self._client.request(self._entity, "get", params)
        return response.count or 0

    async def exists(self) -> bool:
        """Check if any results exist.

        Returns:
            True if at least one record matches.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.
        """
        count = await self.count()
        return count > 0

    async def get(self, **kwargs: Any) -> dict[str, Any] | tuple[Any, ...] | Any:  # noqa: ANN401
        """Get a single entity matching the filters.

        Args:
            **kwargs: Filter conditions.

        Returns:
            Single entity dict/tuple/value.

        Raises:
            CiviNotFoundError: If no matching entity found.
            CiviAPIError: If multiple entities found or other API error.
            CiviConnectionError: On network error.

        Example:
            >>> await Contact.objects.get(id=1)
        """
        qs = self.filter(**kwargs).limit(2)
        results = await qs.all()

        if not results:
            message = f"No {self._entity} found matching: {kwargs}"
            raise CiviNotFoundError(message)

        if len(results) > 1:
            message = f"Multiple {self._entity} found matching: {kwargs}. Use filter() instead of get()."
            raise CiviAPIError(message)

        return results[0]

    async def update(self, **values: Any) -> int:  # noqa: ANN401
        """Update all entities matching current filters.

        Args:
            **values: Field values to update.

        Returns:
            Number of entities updated.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> await qs.filter(id=1).update(first_name="John")
        """
        params = APIRequest(
            values=values,
            where=self._where if self._where else None,
        )
        response = await self._client.request(self._entity, "update", params)
        return response.count or 0

    async def delete(self) -> int:
        """Delete all entities matching current filters.

        Returns:
            Number of entities deleted.

        Raises:
            CiviAPIError: On API error.
            CiviConnectionError: On network error.

        Example:
            >>> await qs.filter(is_deleted=True).delete()
        """
        params = APIRequest(
            where=self._where if self._where else None,
        )
        response = await self._client.request(self._entity, "delete", params)
        return response.count or 0

    def __repr__(self) -> str:
        """Return string representation of QuerySet."""
        return (
            f"<QuerySet entity={self._entity!r} filters={len(self._where)} limit={self._limit} offset={self._offset}>"
        )

    def __str__(self) -> str:
        """Return human-readable string."""
        return f"QuerySet({self._entity})"


__all__ = [
    "QuerySet",
]
