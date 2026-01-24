"""Integration tests for EntityManager and SyncEntityManager.

Tests CRUD operations, query conversion, error handling, and the ManagerDescriptor
with mocked HTTP responses using respx.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import pytest
import respx

from civicrm_py.core.client import CiviClient, SyncCiviClient
from civicrm_py.core.config import CiviSettings
from civicrm_py.core.context import ClientContext, set_current_client
from civicrm_py.core.exceptions import DoesNotExist, MultipleObjectsReturned
from civicrm_py.query.manager import EntityManager, ManagerDescriptor, SyncEntityManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def test_settings() -> CiviSettings:
    """Create test CiviSettings."""
    return CiviSettings(
        base_url="https://test.example.org/civicrm/ajax/api4",
        api_key="test-api-key",
        site_key="test-site-key",
        timeout=10,
        verify_ssl=False,
    )


@pytest.fixture
async def async_client(test_settings: CiviSettings) -> AsyncGenerator[CiviClient, None]:
    """Create an async CiviClient for testing."""
    async with CiviClient(settings=test_settings) as client:
        yield client


@pytest.fixture
def sync_client(test_settings: CiviSettings) -> Generator[SyncCiviClient, None, None]:
    """Create a sync CiviClient for testing."""
    with SyncCiviClient(settings=test_settings) as client:
        yield client


@pytest.fixture
def entity_manager(async_client: CiviClient) -> EntityManager[dict[str, Any]]:
    """Create an EntityManager for testing."""
    return EntityManager(async_client, "Contact")


@pytest.fixture
def sync_entity_manager(sync_client: SyncCiviClient) -> SyncEntityManager[dict[str, Any]]:
    """Create a SyncEntityManager for testing."""
    return SyncEntityManager(sync_client, "Contact")


# =============================================================================
# Sample Response Data
# =============================================================================


def make_contact_response(contacts: list[dict[str, Any]], count: int | None = None) -> dict[str, Any]:
    """Create a contact response structure."""
    return {
        "values": contacts,
        "count": count if count is not None else len(contacts),
        "countFetched": len(contacts),
    }


def make_single_contact(
    contact_id: int = 1,
    first_name: str = "John",
    last_name: str = "Doe",
    email: str = "john@example.com",
) -> dict[str, Any]:
    """Create a single contact record."""
    return {
        "id": contact_id,
        "first_name": first_name,
        "last_name": last_name,
        "display_name": f"{first_name} {last_name}",
        "email_primary.email": email,
        "contact_type": "Individual",
        "is_deleted": False,
    }


def make_field_metadata_response() -> dict[str, Any]:
    """Create field metadata response."""
    return {
        "values": [
            {
                "name": "id",
                "title": "Contact ID",
                "type": "Integer",
                "required": True,
                "readonly": True,
            },
            {
                "name": "first_name",
                "title": "First Name",
                "type": "String",
                "required": False,
                "readonly": False,
            },
            {
                "name": "last_name",
                "title": "Last Name",
                "type": "String",
                "required": False,
                "readonly": False,
            },
            {
                "name": "email_primary.email",
                "title": "Primary Email",
                "type": "String",
                "required": False,
                "readonly": False,
            },
        ],
        "count": 4,
        "countFetched": 4,
    }


# =============================================================================
# Test _kwargs_to_where Conversion
# =============================================================================


class TestKwargsToWhereConversion:
    """Test conversion of Django-style kwargs to CiviCRM where clauses."""

    def test_simple_equality(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test simple field=value conversion."""
        where = entity_manager._kwargs_to_where(first_name="John")
        assert where == [["first_name", "=", "John"]]

    def test_multiple_equality(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test multiple field=value conversions."""
        where = entity_manager._kwargs_to_where(first_name="John", last_name="Doe")
        assert len(where) == 2
        assert ["first_name", "=", "John"] in where
        assert ["last_name", "=", "Doe"] in where

    def test_gt_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test greater than operator."""
        where = entity_manager._kwargs_to_where(age__gt=21)
        assert where == [["age", ">", 21]]

    def test_gte_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test greater than or equal operator."""
        where = entity_manager._kwargs_to_where(age__gte=21)
        assert where == [["age", ">=", 21]]

    def test_lt_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test less than operator."""
        where = entity_manager._kwargs_to_where(age__lt=65)
        assert where == [["age", "<", 65]]

    def test_lte_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test less than or equal operator."""
        where = entity_manager._kwargs_to_where(age__lte=65)
        assert where == [["age", "<=", 65]]

    def test_ne_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test not equal operator."""
        where = entity_manager._kwargs_to_where(status__ne="deleted")
        assert where == [["status", "!=", "deleted"]]

    def test_in_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test IN operator with list."""
        where = entity_manager._kwargs_to_where(id__in=[1, 2, 3])
        assert where == [["id", "IN", [1, 2, 3]]]

    def test_not_in_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test NOT IN operator with list."""
        where = entity_manager._kwargs_to_where(status__not_in=["deleted", "archived"])
        assert where == [["status", "NOT IN", ["deleted", "archived"]]]

    def test_like_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test LIKE operator."""
        where = entity_manager._kwargs_to_where(last_name__like="Smith%")
        assert where == [["last_name", "LIKE", "Smith%"]]

    def test_not_like_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test NOT LIKE operator."""
        where = entity_manager._kwargs_to_where(email__not_like="%@spam.com")
        assert where == [["email", "NOT LIKE", "%@spam.com"]]

    def test_contains_operator(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test CONTAINS operator."""
        where = entity_manager._kwargs_to_where(description__contains="important")
        assert where == [["description", "CONTAINS", "important"]]

    def test_is_null_true(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test IS NULL operator with True value."""
        where = entity_manager._kwargs_to_where(email__is_null=True)
        assert where == [["email", "IS NULL"]]

    def test_is_not_null_true(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test IS NOT NULL operator with True value."""
        where = entity_manager._kwargs_to_where(email__is_not_null=True)
        assert where == [["email", "IS NOT NULL"]]

    def test_unrecognized_operator_treated_as_field(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test unrecognized operator is treated as part of field name."""
        where = entity_manager._kwargs_to_where(custom_field__custom="value")
        assert where == [["custom_field__custom", "=", "value"]]

    def test_combined_operators(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test multiple different operators combined."""
        where = entity_manager._kwargs_to_where(
            first_name="John",
            age__gte=21,
            status__ne="deleted",
        )
        assert len(where) == 3


class TestSyncKwargsToWhereConversion:
    """Test sync manager's kwargs to where conversion."""

    def test_sync_simple_equality(
        self,
        sync_entity_manager: SyncEntityManager[dict[str, Any]],
    ) -> None:
        """Test sync manager simple equality conversion."""
        where = sync_entity_manager._kwargs_to_where(first_name="John")
        assert where == [["first_name", "=", "John"]]

    def test_sync_all_operators(
        self,
        sync_entity_manager: SyncEntityManager[dict[str, Any]],
    ) -> None:
        """Test sync manager supports all operators."""
        # Test a sampling of operators to ensure parity with async
        assert sync_entity_manager._kwargs_to_where(age__gt=21) == [["age", ">", 21]]
        assert sync_entity_manager._kwargs_to_where(age__lte=65) == [["age", "<=", 65]]
        assert sync_entity_manager._kwargs_to_where(id__in=[1, 2]) == [["id", "IN", [1, 2]]]
        assert sync_entity_manager._kwargs_to_where(email__is_null=True) == [["email", "IS NULL"]]


# =============================================================================
# Test QuerySet Factory Methods
# =============================================================================


class TestQuerySetFactoryMethods:
    """Test EntityManager QuerySet factory methods."""

    def test_all_returns_queryset(self, entity_manager: EntityManager[dict[str, Any]]) -> None:
        """Test all() returns a fresh QuerySet."""
        qs = entity_manager.all()
        from civicrm_py.query.queryset import QuerySet

        assert isinstance(qs, QuerySet)
        assert qs._entity == "Contact"

    def test_filter_returns_filtered_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test filter() returns a filtered QuerySet."""
        qs = entity_manager.filter(first_name="John", is_deleted=False)
        assert len(qs._where) == 2

    def test_filter_with_operator_lookups(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test filter() with operator lookups converts to where conditions."""
        qs = entity_manager.filter(created_date__gte="2024-01-01")
        assert ["created_date", ">=", "2024-01-01"] in qs._where

    def test_exclude_returns_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test exclude() returns a QuerySet with NOT condition."""
        qs = entity_manager.exclude(is_deleted=True)
        assert len(qs._where) == 1
        assert qs._where[0][0] == "NOT"

    def test_select_returns_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test select() returns a QuerySet with field selection."""
        qs = entity_manager.select("id", "display_name", "email_primary.email")
        assert qs._select == ["id", "display_name", "email_primary.email"]

    def test_order_by_returns_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test order_by() returns an ordered QuerySet."""
        qs = entity_manager.order_by("-created_date", "last_name")
        assert qs._order_by == {"created_date": "DESC", "last_name": "ASC"}

    def test_limit_returns_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test limit() returns a limited QuerySet."""
        qs = entity_manager.limit(10)
        assert qs._limit == 10

    def test_offset_returns_queryset(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test offset() returns an offset QuerySet."""
        qs = entity_manager.offset(20)
        assert qs._offset == 20

    def test_chained_factory_methods(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test chaining multiple factory methods."""
        qs = (
            entity_manager.filter(is_deleted=False)
            .select("id", "display_name")
            .order_by("-created_date")
            .limit(10)
            .offset(0)
        )
        assert len(qs._where) == 1
        assert qs._select == ["id", "display_name"]
        assert qs._order_by == {"created_date": "DESC"}
        assert qs._limit == 10
        assert qs._offset == 0


# =============================================================================
# Test CRUD Operations - Async
# =============================================================================


@pytest.mark.integration
class TestAsyncGetOperation:
    """Test async EntityManager.get() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_single_record(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get() returns single matching record."""
        manager = EntityManager(async_client, "Contact")
        contact = make_single_contact(contact_id=123, first_name="John", last_name="Doe")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([contact])),
        )

        result = await manager.get(id=123)

        assert result["id"] == 123
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_raises_does_not_exist(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get() raises DoesNotExist when no records found."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )

        with pytest.raises(DoesNotExist) as exc_info:
            await manager.get(id=99999)

        assert exc_info.value.entity_name == "Contact"
        assert "id" in exc_info.value.lookup_params

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_raises_multiple_objects_returned(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get() raises MultipleObjectsReturned when multiple records found."""
        manager = EntityManager(async_client, "Contact")
        contacts = [
            make_single_contact(contact_id=1, first_name="John", last_name="Smith"),
            make_single_contact(contact_id=2, first_name="John", last_name="Doe"),
        ]

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response(contacts)),
        )

        with pytest.raises(MultipleObjectsReturned) as exc_info:
            await manager.get(first_name="John")

        assert exc_info.value.entity_name == "Contact"
        assert exc_info.value.count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_with_operator_lookups(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get() with operator lookups."""
        manager = EntityManager(async_client, "Contact")
        contact = make_single_contact(contact_id=1, email="john@example.com")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([contact])),
        )

        result = await manager.get(email_primary__email="john@example.com")

        assert result["email_primary.email"] == "john@example.com"


@pytest.mark.integration
class TestAsyncCreateOperation:
    """Test async EntityManager.create() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_returns_created_entity(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test create() returns the created entity."""
        manager = EntityManager(async_client, "Contact")
        created = make_single_contact(contact_id=100, first_name="New", last_name="Contact")

        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([created])),
        )

        result = await manager.create(
            first_name="New",
            last_name="Contact",
            email_primary={"email": "new@example.com"},
        )

        assert result["id"] == 100
        assert result["first_name"] == "New"
        assert result["last_name"] == "Contact"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_with_nested_data(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test create() with nested data structures."""
        manager = EntityManager(async_client, "Contact")
        created = make_single_contact(contact_id=101)

        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([created])),
        )

        result = await manager.create(
            first_name="Test",
            last_name="User",
            email_primary={"email": "test@example.com"},
            address_primary={
                "street_address": "123 Main St",
                "city": "Anytown",
                "postal_code": "12345",
            },
        )

        assert result["id"] == 101


@pytest.mark.integration
class TestAsyncUpdateOperation:
    """Test async EntityManager.update() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_with_kwargs(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update() with kwargs filter."""
        manager = EntityManager(async_client, "Contact")
        updated = make_single_contact(contact_id=1, first_name="Updated")

        respx.post(f"{test_settings.base_url}/Contact/update").mock(
            return_value=httpx.Response(200, json=make_contact_response([updated])),
        )

        response = await manager.update({"first_name": "Updated"}, id=1)

        assert response.values is not None
        assert len(response.values) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_with_where(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update() with raw where clause."""
        manager = EntityManager(async_client, "Contact")
        updated_contacts = [
            make_single_contact(contact_id=1),
            make_single_contact(contact_id=2),
        ]

        respx.post(f"{test_settings.base_url}/Contact/update").mock(
            return_value=httpx.Response(200, json=make_contact_response(updated_contacts)),
        )

        response = await manager.update(
            {"is_opt_out": True},
            where=[["email_primary.email", "LIKE", "%@spam.com"]],
        )

        assert response.values is not None
        assert len(response.values) == 2

    @pytest.mark.asyncio
    async def test_update_requires_filter(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test update() raises ValueError without filter criteria."""
        manager = EntityManager(async_client, "Contact")

        with pytest.raises(ValueError, match="update\\(\\) requires filter criteria"):
            await manager.update({"first_name": "Test"})

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_with_combined_where_and_kwargs(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update() combines where and kwargs."""
        manager = EntityManager(async_client, "Contact")
        updated = make_single_contact(contact_id=1)

        respx.post(f"{test_settings.base_url}/Contact/update").mock(
            return_value=httpx.Response(200, json=make_contact_response([updated])),
        )

        response = await manager.update(
            {"job_title": "Developer"},
            where=[["contact_type", "=", "Individual"]],
            is_deleted=False,
        )

        assert response.values is not None


@pytest.mark.integration
class TestAsyncDeleteOperation:
    """Test async EntityManager.delete() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_with_kwargs(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test delete() with kwargs filter."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 1}),
        )

        response = await manager.delete(id=123)

        assert response.count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_with_where(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test delete() with raw where clause."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 5}),
        )

        response = await manager.delete(
            where=[["is_deleted", "=", True], ["modified_date", "<", "2020-01-01"]],
        )

        assert response.count == 5

    @pytest.mark.asyncio
    async def test_delete_requires_filter(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test delete() raises ValueError without filter criteria."""
        manager = EntityManager(async_client, "Contact")

        with pytest.raises(ValueError, match="delete\\(\\) requires filter criteria"):
            await manager.delete()


@pytest.mark.integration
class TestAsyncGetOrCreate:
    """Test async EntityManager.get_or_create() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_or_create_gets_existing(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_or_create() returns existing record."""
        manager = EntityManager(async_client, "Contact")
        existing = make_single_contact(contact_id=1, email="existing@example.com")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([existing])),
        )

        result, created = await manager.get_or_create(
            email_primary__email="existing@example.com",
            defaults={"first_name": "New", "last_name": "User"},
        )

        assert created is False
        assert result["id"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_or_create_creates_new(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_or_create() creates new record when not found."""
        manager = EntityManager(async_client, "Contact")
        new_contact = make_single_contact(contact_id=100, first_name="New", last_name="User")

        # First request returns no results
        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )
        # Second request creates new contact
        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([new_contact])),
        )

        result, created = await manager.get_or_create(
            email_primary__email="new@example.com",
            defaults={"first_name": "New", "last_name": "User"},
        )

        assert created is True
        assert result["id"] == 100
        assert result["first_name"] == "New"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_or_create_raises_multiple_objects(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_or_create() raises MultipleObjectsReturned."""
        manager = EntityManager(async_client, "Contact")
        contacts = [
            make_single_contact(contact_id=1),
            make_single_contact(contact_id=2),
        ]

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response(contacts)),
        )

        with pytest.raises(MultipleObjectsReturned):
            await manager.get_or_create(last_name="Smith")


@pytest.mark.integration
class TestAsyncUpdateOrCreate:
    """Test async EntityManager.update_or_create() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_or_create_updates_existing(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update_or_create() updates existing record."""
        manager = EntityManager(async_client, "Contact")
        existing = make_single_contact(contact_id=1, first_name="John")
        updated = make_single_contact(contact_id=1, first_name="John")
        updated["job_title"] = "Developer"

        # First get finds existing
        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([existing])),
        )
        # Update the record
        respx.post(f"{test_settings.base_url}/Contact/update").mock(
            return_value=httpx.Response(200, json=make_contact_response([updated])),
        )

        _result, created = await manager.update_or_create(
            id=1,
            defaults={"job_title": "Developer"},
        )

        assert created is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_or_create_creates_new(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update_or_create() creates new record when not found."""
        manager = EntityManager(async_client, "Contact")
        new_contact = make_single_contact(contact_id=100, first_name="New", last_name="User")
        new_contact["job_title"] = "Developer"

        # First get returns no results
        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )
        # Create new contact
        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([new_contact])),
        )

        result, created = await manager.update_or_create(
            email_primary__email="new@example.com",
            defaults={"first_name": "New", "last_name": "User", "job_title": "Developer"},
        )

        assert created is True
        assert result["id"] == 100


@pytest.mark.integration
class TestAsyncBulkCreate:
    """Test async EntityManager.bulk_create() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_bulk_create_with_dicts(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test bulk_create() with list of dictionaries."""
        manager = EntityManager(async_client, "Contact")

        contacts_to_create = [
            {"first_name": "John", "last_name": "Doe"},
            {"first_name": "Jane", "last_name": "Smith"},
            {"first_name": "Bob", "last_name": "Johnson"},
        ]

        # Mock individual create calls
        for i, contact in enumerate(contacts_to_create, start=100):
            created = make_single_contact(
                contact_id=i,
                first_name=contact["first_name"],
                last_name=contact["last_name"],
            )
            respx.post(f"{test_settings.base_url}/Contact/create").mock(
                return_value=httpx.Response(200, json=make_contact_response([created])),
            )

        results = await manager.bulk_create(contacts_to_create)

        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

    @pytest.mark.asyncio
    @respx.mock
    async def test_bulk_create_empty_list(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test bulk_create() with empty list."""
        manager = EntityManager(async_client, "Contact")

        results = await manager.bulk_create([])

        assert results == []


@pytest.mark.integration
class TestAsyncCountAndExists:
    """Test async EntityManager.count() and exists() operations."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_count_all(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test count() without filters."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 42, "countFetched": 0}),
        )

        count = await manager.count()

        assert count == 42

    @pytest.mark.asyncio
    @respx.mock
    async def test_count_with_filter(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test count() with filters."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 10, "countFetched": 0}),
        )

        count = await manager.count(is_deleted=False)

        assert count == 10

    @pytest.mark.asyncio
    @respx.mock
    async def test_exists_true(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test exists() returns True when records exist."""
        manager = EntityManager(async_client, "Contact")
        contact = make_single_contact(contact_id=1)

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([contact])),
        )

        exists = await manager.exists(email_primary__email="john@example.com")

        assert exists is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_exists_false(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test exists() returns False when no records exist."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )

        exists = await manager.exists(email_primary__email="nonexistent@example.com")

        assert exists is False


@pytest.mark.integration
class TestAsyncGetFields:
    """Test async EntityManager.get_fields() operation."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_fields(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_fields() returns field metadata."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/getFields").mock(
            return_value=httpx.Response(200, json=make_field_metadata_response()),
        )

        fields = await manager.get_fields()

        assert len(fields) == 4
        assert any(f["name"] == "id" for f in fields)
        assert any(f["name"] == "first_name" for f in fields)


# =============================================================================
# Test CRUD Operations - Sync
# =============================================================================


@pytest.mark.integration
class TestSyncGetOperation:
    """Test sync SyncEntityManager.get() operation."""

    @respx.mock
    def test_sync_get_single_record(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync get() returns single matching record."""
        manager = SyncEntityManager(sync_client, "Contact")
        contact = make_single_contact(contact_id=123, first_name="John", last_name="Doe")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([contact])),
        )

        result = manager.get(id=123)

        assert result["id"] == 123
        assert result["first_name"] == "John"

    @respx.mock
    def test_sync_get_raises_does_not_exist(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync get() raises DoesNotExist when no records found."""
        manager = SyncEntityManager(sync_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )

        with pytest.raises(DoesNotExist) as exc_info:
            manager.get(id=99999)

        assert exc_info.value.entity_name == "Contact"

    @respx.mock
    def test_sync_get_raises_multiple_objects_returned(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync get() raises MultipleObjectsReturned when multiple records found."""
        manager = SyncEntityManager(sync_client, "Contact")
        contacts = [
            make_single_contact(contact_id=1, first_name="John", last_name="Smith"),
            make_single_contact(contact_id=2, first_name="John", last_name="Doe"),
        ]

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response(contacts)),
        )

        with pytest.raises(MultipleObjectsReturned) as exc_info:
            manager.get(first_name="John")

        assert exc_info.value.count == 2


@pytest.mark.integration
class TestSyncCreateOperation:
    """Test sync SyncEntityManager.create() operation."""

    @respx.mock
    def test_sync_create_returns_created_entity(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync create() returns the created entity."""
        manager = SyncEntityManager(sync_client, "Contact")
        created = make_single_contact(contact_id=100, first_name="New", last_name="Contact")

        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([created])),
        )

        result = manager.create(first_name="New", last_name="Contact")

        assert result["id"] == 100
        assert result["first_name"] == "New"


@pytest.mark.integration
class TestSyncUpdateOperation:
    """Test sync SyncEntityManager.update() operation."""

    @respx.mock
    def test_sync_update_with_kwargs(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync update() with kwargs filter."""
        manager = SyncEntityManager(sync_client, "Contact")
        updated = make_single_contact(contact_id=1, first_name="Updated")

        respx.post(f"{test_settings.base_url}/Contact/update").mock(
            return_value=httpx.Response(200, json=make_contact_response([updated])),
        )

        response = manager.update({"first_name": "Updated"}, id=1)

        assert response.values is not None
        assert len(response.values) == 1

    def test_sync_update_requires_filter(
        self,
        sync_client: SyncCiviClient,
    ) -> None:
        """Test sync update() raises ValueError without filter criteria."""
        manager = SyncEntityManager(sync_client, "Contact")

        with pytest.raises(ValueError, match="update\\(\\) requires filter criteria"):
            manager.update({"first_name": "Test"})


@pytest.mark.integration
class TestSyncDeleteOperation:
    """Test sync SyncEntityManager.delete() operation."""

    @respx.mock
    def test_sync_delete_with_kwargs(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync delete() with kwargs filter."""
        manager = SyncEntityManager(sync_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/delete").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 1}),
        )

        response = manager.delete(id=123)

        assert response.count == 1

    def test_sync_delete_requires_filter(
        self,
        sync_client: SyncCiviClient,
    ) -> None:
        """Test sync delete() raises ValueError without filter criteria."""
        manager = SyncEntityManager(sync_client, "Contact")

        with pytest.raises(ValueError, match="delete\\(\\) requires filter criteria"):
            manager.delete()


@pytest.mark.integration
class TestSyncCountAndExists:
    """Test sync SyncEntityManager.count() and exists() operations."""

    @respx.mock
    def test_sync_count(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync count()."""
        manager = SyncEntityManager(sync_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 42, "countFetched": 0}),
        )

        count = manager.count()

        assert count == 42

    @respx.mock
    def test_sync_exists_true(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync exists() returns True when records exist."""
        manager = SyncEntityManager(sync_client, "Contact")
        contact = make_single_contact(contact_id=1)

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([contact])),
        )

        exists = manager.exists(email_primary__email="john@example.com")

        assert exists is True

    @respx.mock
    def test_sync_exists_false(
        self,
        sync_client: SyncCiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test sync exists() returns False when no records exist."""
        manager = SyncEntityManager(sync_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )

        exists = manager.exists(email_primary__email="nonexistent@example.com")

        assert exists is False


# =============================================================================
# Test ManagerDescriptor
# =============================================================================


class TestManagerDescriptor:
    """Test ManagerDescriptor for .objects pattern."""

    def test_descriptor_set_name(self) -> None:
        """Test descriptor __set_name__ captures class info."""

        class TestEntity:
            __entity_name__ = "TestEntity"
            objects: ClassVar[EntityManager[TestEntity]] = ManagerDescriptor()

        # The descriptor should have captured the entity name
        descriptor = TestEntity.__dict__["objects"]
        assert descriptor._entity_name == "TestEntity"
        assert descriptor._model_class is TestEntity

    def test_descriptor_uses_class_name_as_fallback(self) -> None:
        """Test descriptor uses class name when __entity_name__ not set."""

        class Contact:
            objects: ClassVar[EntityManager[Contact]] = ManagerDescriptor()

        descriptor = Contact.__dict__["objects"]
        assert descriptor._entity_name == "Contact"

    @pytest.mark.asyncio
    async def test_descriptor_with_context_client(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test descriptor uses client from context."""

        class Contact:
            __entity_name__ = "Contact"
            objects: ClassVar[EntityManager[Contact]] = ManagerDescriptor()

        with ClientContext(async_client):
            manager = Contact.objects
            assert isinstance(manager, EntityManager)
            assert manager.entity_name == "Contact"

    def test_descriptor_raises_without_client(self) -> None:
        """Test descriptor raises RuntimeError when no client configured."""

        class Contact:
            __entity_name__ = "Contact"
            objects: ClassVar[EntityManager[Contact]] = ManagerDescriptor()

        # Clear any existing context

        token = set_current_client(None)

        try:
            with pytest.raises(RuntimeError, match="No client configured"):
                _ = Contact.objects
        finally:
            from civicrm_py.core.context import reset_current_client

            reset_current_client(token)

    @pytest.mark.asyncio
    async def test_descriptor_with_class_level_client(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test descriptor uses _client attribute on class."""

        class Contact:
            __entity_name__ = "Contact"
            _client: CiviClient | None = None
            objects: ClassVar[EntityManager[Contact]] = ManagerDescriptor()

        Contact._client = async_client
        try:
            manager = Contact.objects
            assert isinstance(manager, EntityManager)
            assert manager.entity_name == "Contact"
        finally:
            Contact._client = None


# =============================================================================
# Test Manager Properties
# =============================================================================


class TestManagerProperties:
    """Test EntityManager and SyncEntityManager properties."""

    def test_async_manager_client_property(
        self,
        entity_manager: EntityManager[dict[str, Any]],
        async_client: CiviClient,
    ) -> None:
        """Test async manager client property."""
        assert entity_manager.client is async_client

    def test_async_manager_entity_name_property(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test async manager entity_name property."""
        assert entity_manager.entity_name == "Contact"

    def test_async_manager_model_class_property(
        self,
        async_client: CiviClient,
    ) -> None:
        """Test async manager model_class property."""
        manager = EntityManager(async_client, "Contact", model_class=dict)
        assert manager.model_class is dict

    def test_sync_manager_client_property(
        self,
        sync_entity_manager: SyncEntityManager[dict[str, Any]],
        sync_client: SyncCiviClient,
    ) -> None:
        """Test sync manager client property."""
        assert sync_entity_manager.client is sync_client

    def test_sync_manager_entity_name_property(
        self,
        sync_entity_manager: SyncEntityManager[dict[str, Any]],
    ) -> None:
        """Test sync manager entity_name property."""
        assert sync_entity_manager.entity_name == "Contact"


# =============================================================================
# Test Edge Cases and Error Handling
# =============================================================================


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_or_create_cleans_operator_lookups(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_or_create() removes operator lookups from create kwargs."""
        manager = EntityManager(async_client, "Contact")
        new_contact = make_single_contact(contact_id=100, first_name="Test", last_name="User")

        # First get returns empty
        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([])),
        )
        # Create should be called without the operator suffix
        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json=make_contact_response([new_contact])),
        )

        # Using operator lookup that should be cleaned
        _result, created = await manager.get_or_create(
            age__gte=18,  # This should be skipped in create
            defaults={"first_name": "Test", "last_name": "User"},
        )

        assert created is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_handles_empty_response(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test create() handles empty response gracefully."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/create").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        result = await manager.create(first_name="Test")

        assert result == {}

    @pytest.mark.asyncio
    @respx.mock
    async def test_count_handles_none_response(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test count() handles None count gracefully."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json={"values": []}),
        )

        count = await manager.count()

        assert count == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_fields_handles_empty_response(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test get_fields() handles empty response."""
        manager = EntityManager(async_client, "Contact")

        respx.post(f"{test_settings.base_url}/Contact/getFields").mock(
            return_value=httpx.Response(200, json={"values": [], "count": 0}),
        )

        fields = await manager.get_fields()

        assert fields == []

    def test_kwargs_to_where_empty_kwargs(
        self,
        entity_manager: EntityManager[dict[str, Any]],
    ) -> None:
        """Test _kwargs_to_where with empty kwargs."""
        where = entity_manager._kwargs_to_where()
        assert where == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_update_or_create_with_no_id_in_result(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test update_or_create() when existing entity has no id field."""
        manager = EntityManager(async_client, "Contact")
        # Entity without id field (unusual but possible)
        existing = {"first_name": "John", "last_name": "Doe"}

        respx.post(f"{test_settings.base_url}/Contact/get").mock(
            return_value=httpx.Response(200, json=make_contact_response([existing])),
        )

        result, created = await manager.update_or_create(
            first_name="John",
            defaults={"job_title": "Developer"},
        )

        # Should return existing without update since no id
        assert created is False
        assert result["first_name"] == "John"


# =============================================================================
# Test Different Entities
# =============================================================================


@pytest.mark.integration
class TestDifferentEntities:
    """Test manager works with different entity types."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_activity_entity(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test manager with Activity entity."""
        manager = EntityManager(async_client, "Activity")
        activity = {
            "id": 1,
            "activity_type_id": 3,
            "subject": "Test Activity",
            "status_id": 1,
        }

        respx.post(f"{test_settings.base_url}/Activity/get").mock(
            return_value=httpx.Response(200, json={"values": [activity], "count": 1}),
        )

        result = await manager.get(id=1)

        assert result["subject"] == "Test Activity"

    @pytest.mark.asyncio
    @respx.mock
    async def test_contribution_entity(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test manager with Contribution entity."""
        manager = EntityManager(async_client, "Contribution")
        contribution = {
            "id": 1,
            "contact_id": 1,
            "total_amount": 100.00,
            "currency": "USD",
        }

        respx.post(f"{test_settings.base_url}/Contribution/get").mock(
            return_value=httpx.Response(200, json={"values": [contribution], "count": 1}),
        )

        result = await manager.get(id=1)

        assert result["total_amount"] == 100.00

    @pytest.mark.asyncio
    @respx.mock
    async def test_event_entity(
        self,
        async_client: CiviClient,
        test_settings: CiviSettings,
    ) -> None:
        """Test manager with Event entity."""
        manager = EntityManager(async_client, "Event")
        event = {
            "id": 1,
            "title": "Annual Conference",
            "event_type_id": 1,
            "is_active": True,
        }

        respx.post(f"{test_settings.base_url}/Event/get").mock(
            return_value=httpx.Response(200, json={"values": [event], "count": 1}),
        )

        result = await manager.get(id=1)

        assert result["title"] == "Annual Conference"
