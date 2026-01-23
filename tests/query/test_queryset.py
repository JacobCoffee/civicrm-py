"""Tests for QuerySet class."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from civi_py.core.exceptions import CiviAPIError, CiviNotFoundError
from civi_py.core.serialization import APIResponse
from civi_py.query.queryset import QuerySet


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock CiviClient."""
    client = Mock()
    client.request = AsyncMock()
    return client


@pytest.fixture
def queryset(mock_client: Mock) -> QuerySet:
    """Create a QuerySet for testing."""
    return QuerySet(mock_client, "Contact")


class TestQuerySetChaining:
    """Test QuerySet chainable methods."""

    def test_filter_returns_new_queryset(self, queryset: QuerySet) -> None:
        """Test filter() returns a new QuerySet instance."""
        qs2 = queryset.filter(first_name="John")
        assert qs2 is not queryset
        assert isinstance(qs2, QuerySet)

    def test_filter_preserves_original(self, queryset: QuerySet) -> None:
        """Test filter() doesn't modify original QuerySet."""
        original_where = queryset._where.copy()
        queryset.filter(first_name="John")
        assert queryset._where == original_where

    def test_chaining_multiple_filters(self, queryset: QuerySet) -> None:
        """Test chaining multiple filter calls."""
        qs = queryset.filter(first_name="John").filter(last_name="Doe").filter(is_deleted=False)
        assert len(qs._where) == 3

    def test_select_fields(self, queryset: QuerySet) -> None:
        """Test select() sets field selection."""
        qs = queryset.select("id", "display_name", "email_primary.email")
        assert qs._select == ["id", "display_name", "email_primary.email"]

    def test_order_by_ascending(self, queryset: QuerySet) -> None:
        """Test order_by() ascending order."""
        qs = queryset.order_by("last_name")
        assert qs._order_by == {"last_name": "ASC"}

    def test_order_by_descending(self, queryset: QuerySet) -> None:
        """Test order_by() descending order with - prefix."""
        qs = queryset.order_by("-created_date")
        assert qs._order_by == {"created_date": "DESC"}

    def test_order_by_multiple_fields(self, queryset: QuerySet) -> None:
        """Test order_by() with multiple fields."""
        qs = queryset.order_by("-created_date", "last_name")
        assert qs._order_by == {"created_date": "DESC", "last_name": "ASC"}

    def test_limit_and_offset(self, queryset: QuerySet) -> None:
        """Test limit() and offset() methods."""
        qs = queryset.limit(10).offset(20)
        assert qs._limit == 10
        assert qs._offset == 20


class TestFieldLookups:
    """Test field lookup parsing."""

    def test_exact_lookup_explicit(self, queryset: QuerySet) -> None:
        """Test exact lookup (explicit)."""
        condition = queryset._parse_lookup("first_name__exact", "John")
        assert condition == ["first_name", "=", "John"]

    def test_exact_lookup_implicit(self, queryset: QuerySet) -> None:
        """Test exact lookup (implicit, no operator)."""
        condition = queryset._parse_lookup("first_name", "John")
        assert condition == ["first_name", "=", "John"]

    def test_contains_lookup(self, queryset: QuerySet) -> None:
        """Test contains lookup."""
        condition = queryset._parse_lookup("last_name__contains", "Smith")
        assert condition == ["last_name", "CONTAINS", "Smith"]

    def test_startswith_lookup(self, queryset: QuerySet) -> None:
        """Test startswith lookup."""
        condition = queryset._parse_lookup("last_name__startswith", "Sm")
        assert condition == ["last_name", "LIKE", "Sm%"]

    def test_endswith_lookup(self, queryset: QuerySet) -> None:
        """Test endswith lookup."""
        condition = queryset._parse_lookup("last_name__endswith", "th")
        assert condition == ["last_name", "LIKE", "%th"]

    def test_gt_lookup(self, queryset: QuerySet) -> None:
        """Test greater than lookup."""
        condition = queryset._parse_lookup("age__gt", 21)
        assert condition == ["age", ">", 21]

    def test_gte_lookup(self, queryset: QuerySet) -> None:
        """Test greater than or equal lookup."""
        condition = queryset._parse_lookup("age__gte", 21)
        assert condition == ["age", ">=", 21]

    def test_lt_lookup(self, queryset: QuerySet) -> None:
        """Test less than lookup."""
        condition = queryset._parse_lookup("age__lt", 65)
        assert condition == ["age", "<", 65]

    def test_lte_lookup(self, queryset: QuerySet) -> None:
        """Test less than or equal lookup."""
        condition = queryset._parse_lookup("age__lte", 65)
        assert condition == ["age", "<=", 65]

    def test_in_lookup(self, queryset: QuerySet) -> None:
        """Test IN lookup."""
        condition = queryset._parse_lookup("id__in", [1, 2, 3])
        assert condition == ["id", "IN", [1, 2, 3]]

    def test_isnull_true(self, queryset: QuerySet) -> None:
        """Test isnull lookup with True."""
        is_null = True
        condition = queryset._parse_lookup("email__isnull", is_null)
        assert condition == ["email", "IS NULL"]

    def test_isnull_false(self, queryset: QuerySet) -> None:
        """Test isnull lookup with False."""
        is_null = False
        condition = queryset._parse_lookup("email__isnull", is_null)
        assert condition == ["email", "IS NOT NULL"]

    def test_not_lookup(self, queryset: QuerySet) -> None:
        """Test not equal lookup."""
        condition = queryset._parse_lookup("status__not", "deleted")
        assert condition == ["status", "!=", "deleted"]


class TestExclude:
    """Test exclude() method."""

    def test_exclude_wraps_in_not(self, queryset: QuerySet) -> None:
        """Test exclude() wraps condition in NOT."""
        qs = queryset.exclude(is_deleted=True)
        assert len(qs._where) == 1
        assert qs._where[0][0] == "NOT"
        assert qs._where[0][1] == [["is_deleted", "=", True]]


class TestJoin:
    """Test join() method."""

    def test_join_without_alias(self, queryset: QuerySet) -> None:
        """Test join() without alias."""
        qs = queryset.join("Email", "email_primary")
        assert qs._join == [["Email", "email_primary"]]

    def test_join_with_alias(self, queryset: QuerySet) -> None:
        """Test join() with alias."""
        qs = queryset.join("Email", "email_primary", "email")
        assert qs._join == [["Email", "email_primary", "email"]]


class TestValues:
    """Test values() and values_list() methods."""

    def test_values_with_fields(self, queryset: QuerySet) -> None:
        """Test values() with specific fields."""
        qs = queryset.values("id", "display_name")
        assert qs._values_fields == ["id", "display_name"]

    def test_values_without_fields(self, queryset: QuerySet) -> None:
        """Test values() without fields returns all."""
        qs = queryset.values()
        assert qs._values_fields == []

    def test_values_list_with_fields(self, queryset: QuerySet) -> None:
        """Test values_list() with specific fields."""
        qs = queryset.values_list("id", "display_name")
        assert qs._values_list_fields == ["id", "display_name"]
        assert not qs._flat

    def test_values_list_flat(self, queryset: QuerySet) -> None:
        """Test values_list() with flat=True."""
        qs = queryset.values_list("id", flat=True)
        assert qs._values_list_fields == ["id"]
        assert qs._flat


class TestExecution:
    """Test query execution methods."""

    @pytest.mark.asyncio
    async def test_all_executes_query(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test all() executes query and returns results."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "Jane Smith"},
            ],
            count=2,
            countFetched=2,
        )

        results = await queryset.all()
        assert len(results) == 2
        assert results[0]["display_name"] == "John Doe"
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_returns_first_result(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test first() returns first result."""
        mock_client.request.return_value = APIResponse(
            values=[{"id": 1, "display_name": "John Doe"}],
            count=1,
            countFetched=1,
        )

        result = await queryset.first()
        assert result is not None
        assert result["display_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_first_returns_none_when_empty(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test first() returns None when no results."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        result = await queryset.first()
        assert result is None

    @pytest.mark.asyncio
    async def test_count_returns_total(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test count() returns total count."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=42,
            countFetched=0,
        )

        count = await queryset.count()
        assert count == 42

    @pytest.mark.asyncio
    async def test_exists_true(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test exists() returns True when results exist."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=1,
            countFetched=0,
        )

        exists = await queryset.exists()
        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test exists() returns False when no results."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        exists = await queryset.exists()
        assert exists is False

    @pytest.mark.asyncio
    async def test_get_single_result(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test get() returns single matching entity."""
        mock_client.request.return_value = APIResponse(
            values=[{"id": 1, "display_name": "John Doe"}],
            count=1,
            countFetched=1,
        )

        result = await queryset.get(id=1)
        assert result["display_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_get_not_found(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test get() raises CiviNotFoundError when not found."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        with pytest.raises(CiviNotFoundError):
            await queryset.get(id=999)

    @pytest.mark.asyncio
    async def test_get_multiple_results(self, mock_client: Mock, queryset: QuerySet) -> None:
        """Test get() raises CiviAPIError when multiple results."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "John Smith"},
            ],
            count=2,
            countFetched=2,
        )

        with pytest.raises(CiviAPIError):
            await queryset.get(first_name="John")

    @pytest.mark.asyncio
    async def test_update_executes_update(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test update() executes update query."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=3,
            countFetched=0,
        )

        count = await queryset.filter(id__in=[1, 2, 3]).update(is_deleted=True)
        assert count == 3
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_executes_delete(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test delete() executes delete query."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=2,
            countFetched=0,
        )

        count = await queryset.filter(is_deleted=True).delete()
        assert count == 2
        mock_client.request.assert_called_once()


class TestValuesProcessing:
    """Test values processing for values() and values_list()."""

    @pytest.mark.asyncio
    async def test_values_returns_dicts_with_selected_fields(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test values() returns dicts with only selected fields."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 1, "display_name": "John Doe", "email": "john@example.com"},
                {"id": 2, "display_name": "Jane Smith", "email": "jane@example.com"},
            ],
            count=2,
            countFetched=2,
        )

        results = await queryset.values("id", "display_name").all()
        assert len(results) == 2
        assert results[0] == {"id": 1, "display_name": "John Doe"}
        assert "email" not in results[0]

    @pytest.mark.asyncio
    async def test_values_list_returns_tuples(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test values_list() returns tuples."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 1, "display_name": "John Doe"},
                {"id": 2, "display_name": "Jane Smith"},
            ],
            count=2,
            countFetched=2,
        )

        results = await queryset.values_list("id", "display_name").all()
        assert len(results) == 2
        assert results[0] == (1, "John Doe")
        assert results[1] == (2, "Jane Smith")

    @pytest.mark.asyncio
    async def test_values_list_flat_returns_list(
        self,
        mock_client: Mock,
        queryset: QuerySet,
    ) -> None:
        """Test values_list() with flat=True returns flat list."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 1},
                {"id": 2},
                {"id": 3},
            ],
            count=3,
            countFetched=3,
        )

        results = await queryset.values_list("id", flat=True).all()
        assert results == [1, 2, 3]


class TestBuildParams:
    """Test _build_params() method."""

    def test_build_params_with_all_options(self, queryset: QuerySet) -> None:
        """Test _build_params() includes all query options."""
        qs = (
            queryset.filter(is_deleted=False)
            .select("id", "display_name")
            .order_by("-created_date")
            .limit(10)
            .offset(20)
        )

        params = qs._build_params()
        assert params.select == ["id", "display_name"]
        assert params.where == [["is_deleted", "=", False]]
        assert params.orderBy == {"created_date": "DESC"}
        assert params.limit == 10
        assert params.offset == 20

    def test_build_params_minimal(self, queryset: QuerySet) -> None:
        """Test _build_params() with minimal options."""
        params = queryset._build_params()
        assert params.select is None
        assert params.where is None
        assert params.orderBy is None
        assert params.limit is None
        assert params.offset is None


class TestRepr:
    """Test string representations."""

    def test_repr(self, queryset: QuerySet) -> None:
        """Test __repr__() output."""
        qs = queryset.filter(first_name="John").limit(10)
        repr_str = repr(qs)
        assert "QuerySet" in repr_str
        assert "Contact" in repr_str
        assert "filters=1" in repr_str
        assert "limit=10" in repr_str

    def test_str(self, queryset: QuerySet) -> None:
        """Test __str__() output."""
        str_repr = str(queryset)
        assert str_repr == "QuerySet(Contact)"
