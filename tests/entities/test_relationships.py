"""Tests for entity relationship handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from civi_py.core.serialization import APIResponse
from civi_py.entities.activity import Activity
from civi_py.entities.base import BaseEntity
from civi_py.entities.contact import Contact
from civi_py.entities.contribution import Contribution
from civi_py.entities.event import Event
from civi_py.entities.participant import Participant
from civi_py.entities.relationships import (
    ForeignKey,
    ForeignKeyAccessor,
    ManyToManyField,
    ManyToManyManager,
    RelatedField,
    RelatedManager,
    get_relationships,
    get_reverse_relationships,
    register_relationship,
)


# Test entities for relationship testing
class TestContact(BaseEntity, kw_only=True):
    """Test contact entity."""

    __entity_name__ = "TestContact"
    id: int | None = None
    display_name: str | None = None
    employer_id: int | None = None


class TestActivity(BaseEntity, kw_only=True):
    """Test activity entity."""

    __entity_name__ = "TestActivity"
    id: int | None = None
    subject: str | None = None
    source_contact_id: int | None = None


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock CiviClient."""
    client = Mock()
    client.request = AsyncMock()
    return client


@pytest.fixture
def contact_with_client(mock_client: Mock) -> TestContact:
    """Create a TestContact with a mock client bound."""
    contact = TestContact(id=1, display_name="John Doe")
    object.__setattr__(contact, "_client", mock_client)
    return contact


@pytest.fixture
def activity_with_client(mock_client: Mock) -> TestActivity:
    """Create a TestActivity with a mock client bound."""
    activity = TestActivity(id=100, subject="Test Activity", source_contact_id=1)
    object.__setattr__(activity, "_client", mock_client)
    return activity


class TestRelatedManager:
    """Test RelatedManager class."""

    def test_init(self, contact_with_client: TestContact) -> None:
        """Test RelatedManager initialization."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        assert manager._parent is contact_with_client
        assert manager._related_entity == "TestActivity"
        assert manager._foreign_key == "source_contact_id"

    def test_get_client_success(self, contact_with_client: TestContact) -> None:
        """Test _get_client() returns bound client."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        client = manager._get_client()
        assert client is not None

    def test_get_client_no_client_raises(self) -> None:
        """Test _get_client() raises when no client bound."""
        contact = TestContact(id=1, display_name="John Doe")
        manager = RelatedManager(
            parent=contact,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        with pytest.raises(RuntimeError, match="has no client bound"):
            manager._get_client()

    def test_get_parent_id_success(self, contact_with_client: TestContact) -> None:
        """Test _get_parent_id() returns parent ID."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        assert manager._get_parent_id() == 1

    def test_get_parent_id_no_id_raises(self, mock_client: Mock) -> None:
        """Test _get_parent_id() raises when parent has no ID."""
        contact = TestContact(display_name="John Doe")
        object.__setattr__(contact, "_client", mock_client)
        manager = RelatedManager(
            parent=contact,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        with pytest.raises(RuntimeError, match="has no ID"):
            manager._get_parent_id()

    def test_filter_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test filter() returns a QuerySet."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.filter(status_id=2)
        assert hasattr(qs, "filter")  # Check it's QuerySet-like

    def test_exclude_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test exclude() returns a QuerySet."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.exclude(is_deleted=True)
        assert hasattr(qs, "filter")

    def test_select_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test select() returns a QuerySet with field selection."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.select("id", "subject")
        assert hasattr(qs, "filter")

    def test_order_by_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test order_by() returns a QuerySet with sort order."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.order_by("-created_date")
        assert hasattr(qs, "filter")

    def test_limit_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test limit() returns a QuerySet with limit."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.limit(10)
        assert hasattr(qs, "filter")

    def test_offset_returns_queryset(
        self,
        contact_with_client: TestContact,
    ) -> None:
        """Test offset() returns a QuerySet with offset."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        qs = manager.offset(20)
        assert hasattr(qs, "filter")

    @pytest.mark.asyncio
    async def test_all_returns_related_entities(
        self,
        mock_client: Mock,
        contact_with_client: TestContact,
    ) -> None:
        """Test all() returns list of related entities."""
        mock_client.request.return_value = APIResponse(
            values=[
                {"id": 100, "subject": "Activity 1", "source_contact_id": 1},
                {"id": 101, "subject": "Activity 2", "source_contact_id": 1},
            ],
            count=2,
            countFetched=2,
        )

        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        results = await manager.all()

        assert len(results) == 2
        assert results[0]["subject"] == "Activity 1"
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_returns_single_entity(
        self,
        mock_client: Mock,
        contact_with_client: TestContact,
    ) -> None:
        """Test first() returns first related entity."""
        mock_client.request.return_value = APIResponse(
            values=[{"id": 100, "subject": "Activity 1"}],
            count=1,
            countFetched=1,
        )

        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        result = await manager.first()

        assert result is not None
        assert result["subject"] == "Activity 1"

    @pytest.mark.asyncio
    async def test_count_returns_total(
        self,
        mock_client: Mock,
        contact_with_client: TestContact,
    ) -> None:
        """Test count() returns count of related entities."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=5,
            countFetched=0,
        )

        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        count = await manager.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_exists_returns_true(
        self,
        mock_client: Mock,
        contact_with_client: TestContact,
    ) -> None:
        """Test exists() returns True when entities exist."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=1,
            countFetched=0,
        )

        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        result = await manager.exists()

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false(
        self,
        mock_client: Mock,
        contact_with_client: TestContact,
    ) -> None:
        """Test exists() returns False when no entities exist."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        result = await manager.exists()

        assert result is False

    def test_repr(self, contact_with_client: TestContact) -> None:
        """Test __repr__() output."""
        manager = RelatedManager(
            parent=contact_with_client,
            related_entity="TestActivity",
            foreign_key="source_contact_id",
        )
        repr_str = repr(manager)
        assert "RelatedManager" in repr_str
        assert "TestContact" in repr_str
        assert "TestActivity" in repr_str


class TestForeignKey:
    """Test ForeignKey descriptor."""

    def test_class_access_returns_descriptor(self) -> None:
        """Test accessing ForeignKey on class returns descriptor."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        assert isinstance(EntityWithFK.related, ForeignKey)

    def test_instance_access_returns_accessor(self, mock_client: Mock) -> None:
        """Test accessing ForeignKey on instance returns accessor."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        accessor = entity.related
        assert isinstance(accessor, ForeignKeyAccessor)

    def test_set_name(self) -> None:
        """Test __set_name__() sets attribute name."""
        fk = ForeignKey["TestContact"]("TestContact", "related_id")

        class Owner:
            my_relation = fk

        assert fk._attr_name == "my_relation"

    def test_repr(self) -> None:
        """Test __repr__() output."""
        fk = ForeignKey["TestContact"]("TestContact", "related_id")
        repr_str = repr(fk)
        assert "ForeignKey" in repr_str
        assert "TestContact" in repr_str
        assert "related_id" in repr_str


class TestForeignKeyAccessor:
    """Test ForeignKeyAccessor class."""

    def test_init(self, mock_client: Mock) -> None:
        """Test ForeignKeyAccessor initialization."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        accessor = entity.related
        assert accessor._entity_name == "TestContact"
        assert accessor._fk_field == "related_id"

    @pytest.mark.asyncio
    async def test_await_loads_related_entity(self, mock_client: Mock) -> None:
        """Test awaiting accessor loads related entity."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        mock_client.request.return_value = APIResponse(
            values=[{"id": 10, "display_name": "Related Contact"}],
            count=1,
            countFetched=1,
        )

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        result = await entity.related
        assert result is not None
        assert result["display_name"] == "Related Contact"

    @pytest.mark.asyncio
    async def test_await_returns_none_when_fk_is_none(self, mock_client: Mock) -> None:
        """Test awaiting accessor returns None when FK is None."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        entity = EntityWithFK(id=1, related_id=None)
        object.__setattr__(entity, "_client", mock_client)

        result = await entity.related
        assert result is None
        # Should not have made any request
        mock_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_await_caches_result(self, mock_client: Mock) -> None:
        """Test awaiting accessor caches the result."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        mock_client.request.return_value = APIResponse(
            values=[{"id": 10, "display_name": "Related Contact"}],
            count=1,
            countFetched=1,
        )

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        # First access
        result1 = await entity.related
        # Second access
        result2 = await entity.related

        assert result1 == result2
        # Should have only made one request due to caching
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self, mock_client: Mock) -> None:
        """Test clear_cache() invalidates cached result."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        mock_client.request.return_value = APIResponse(
            values=[{"id": 10, "display_name": "Related Contact"}],
            count=1,
            countFetched=1,
        )

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        # First access (cached)
        await entity.related
        # Clear cache
        entity.related.clear_cache()
        # Second access (should make new request)
        await entity.related

        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_no_client_raises(self) -> None:
        """Test awaiting accessor raises when no client bound."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        entity = EntityWithFK(id=1, related_id=10)

        with pytest.raises(RuntimeError, match="has no client bound"):
            await entity.related

    def test_repr(self, mock_client: Mock) -> None:
        """Test __repr__() output."""

        class EntityWithFK(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithFK"
            id: int | None = None
            related_id: int | None = None
            related = ForeignKey["TestContact"]("TestContact", "related_id")

        entity = EntityWithFK(id=1, related_id=10)
        object.__setattr__(entity, "_client", mock_client)

        accessor = entity.related
        repr_str = repr(accessor)
        assert "ForeignKeyAccessor" in repr_str
        assert "TestContact" in repr_str


class TestRelatedField:
    """Test RelatedField descriptor."""

    def test_class_access_returns_descriptor(self) -> None:
        """Test accessing RelatedField on class returns descriptor."""

        class EntityWithRelated(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithRelated"
            id: int | None = None
            activities = RelatedField("TestActivity", "parent_id")

        assert isinstance(EntityWithRelated.activities, RelatedField)

    def test_instance_access_returns_manager(self, mock_client: Mock) -> None:
        """Test accessing RelatedField on instance returns RelatedManager."""

        class EntityWithRelated(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithRelated"
            id: int | None = None
            activities = RelatedField("TestActivity", "parent_id")

        entity = EntityWithRelated(id=1)
        object.__setattr__(entity, "_client", mock_client)

        manager = entity.activities
        assert isinstance(manager, RelatedManager)

    def test_repr(self) -> None:
        """Test __repr__() output."""
        field = RelatedField("TestActivity", "parent_id")
        repr_str = repr(field)
        assert "RelatedField" in repr_str
        assert "TestActivity" in repr_str
        assert "parent_id" in repr_str


class TestManyToManyField:
    """Test ManyToManyField descriptor."""

    def test_class_access_returns_descriptor(self) -> None:
        """Test accessing ManyToManyField on class returns descriptor."""

        class EntityWithM2M(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithM2M"
            id: int | None = None
            groups = ManyToManyField(
                "Group",
                through="GroupMember",
                through_fk="entity_id",
                target_fk="group_id",
            )

        assert isinstance(EntityWithM2M.groups, ManyToManyField)

    def test_instance_access_returns_manager(self, mock_client: Mock) -> None:
        """Test accessing ManyToManyField on instance returns ManyToManyManager."""

        class EntityWithM2M(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithM2M"
            id: int | None = None
            groups = ManyToManyField(
                "Group",
                through="GroupMember",
                through_fk="entity_id",
                target_fk="group_id",
            )

        entity = EntityWithM2M(id=1)
        object.__setattr__(entity, "_client", mock_client)

        manager = entity.groups
        assert isinstance(manager, ManyToManyManager)

    def test_repr(self) -> None:
        """Test __repr__() output."""
        field = ManyToManyField(
            "Group",
            through="GroupMember",
            through_fk="entity_id",
            target_fk="group_id",
        )
        repr_str = repr(field)
        assert "ManyToManyField" in repr_str
        assert "Group" in repr_str
        assert "GroupMember" in repr_str


class TestManyToManyManager:
    """Test ManyToManyManager class."""

    @pytest.fixture
    def entity_with_m2m(self, mock_client: Mock) -> BaseEntity:
        """Create an entity with ManyToManyField."""

        class EntityWithM2M(BaseEntity, kw_only=True):
            __entity_name__ = "EntityWithM2M"
            id: int | None = None
            groups = ManyToManyField(
                "Group",
                through="GroupMember",
                through_fk="entity_id",
                target_fk="group_id",
            )

        entity = EntityWithM2M(id=1)
        object.__setattr__(entity, "_client", mock_client)
        return entity

    @pytest.mark.asyncio
    async def test_all_returns_related_through_junction(
        self,
        mock_client: Mock,
        entity_with_m2m: BaseEntity,
    ) -> None:
        """Test all() returns related entities through junction table."""
        # First call: get junction records
        # Second call: get target entities
        mock_client.request.side_effect = [
            APIResponse(
                values=[
                    {"group_id": 10},
                    {"group_id": 20},
                ],
                count=2,
                countFetched=2,
            ),
            APIResponse(
                values=[
                    {"id": 10, "name": "Group A"},
                    {"id": 20, "name": "Group B"},
                ],
                count=2,
                countFetched=2,
            ),
        ]

        manager = entity_with_m2m.groups
        results = await manager.all()

        assert len(results) == 2
        assert results[0]["name"] == "Group A"
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_all_returns_empty_when_no_junction_records(
        self,
        mock_client: Mock,
        entity_with_m2m: BaseEntity,
    ) -> None:
        """Test all() returns empty list when no junction records."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        manager = entity_with_m2m.groups
        results = await manager.all()

        assert results == []
        # Only one call for junction records
        assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_count_returns_junction_count(
        self,
        mock_client: Mock,
        entity_with_m2m: BaseEntity,
    ) -> None:
        """Test count() returns count from junction table."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=3,
            countFetched=0,
        )

        manager = entity_with_m2m.groups
        count = await manager.count()

        assert count == 3

    @pytest.mark.asyncio
    async def test_exists_true(
        self,
        mock_client: Mock,
        entity_with_m2m: BaseEntity,
    ) -> None:
        """Test exists() returns True when relations exist."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=1,
            countFetched=0,
        )

        manager = entity_with_m2m.groups
        result = await manager.exists()

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(
        self,
        mock_client: Mock,
        entity_with_m2m: BaseEntity,
    ) -> None:
        """Test exists() returns False when no relations."""
        mock_client.request.return_value = APIResponse(
            values=[],
            count=0,
            countFetched=0,
        )

        manager = entity_with_m2m.groups
        result = await manager.exists()

        assert result is False

    def test_repr(self, entity_with_m2m: BaseEntity) -> None:
        """Test __repr__() output."""
        manager = entity_with_m2m.groups
        repr_str = repr(manager)
        assert "ManyToManyManager" in repr_str
        assert "Group" in repr_str
        assert "GroupMember" in repr_str


class TestRelationshipRegistry:
    """Test relationship registry functions."""

    def test_register_relationship(self) -> None:
        """Test registering a relationship."""
        register_relationship(
            entity_name="TestEntity",
            field_name="items",
            relationship_type="related",
            related_entity="Item",
            foreign_key="test_entity_id",
        )

        relationships = get_relationships("TestEntity")
        assert "items" in relationships
        assert relationships["items"]["related_entity"] == "Item"

    def test_get_relationships_returns_empty_for_unknown(self) -> None:
        """Test get_relationships returns empty dict for unknown entity."""
        relationships = get_relationships("UnknownEntity123")
        assert relationships == {}

    def test_get_reverse_relationships(self) -> None:
        """Test getting reverse relationships."""
        register_relationship(
            entity_name="Parent",
            field_name="children",
            relationship_type="related",
            related_entity="Child",
            foreign_key="parent_id",
        )

        reverse = get_reverse_relationships("Child")
        assert len(reverse) >= 1
        parent_rel = next((r for r in reverse if r["source_entity"] == "Parent"), None)
        assert parent_rel is not None
        assert parent_rel["field_name"] == "children"


class TestEntityRelationships:
    """Test relationships defined on actual entity classes."""

    def test_contact_has_activities_relationship(self) -> None:
        """Test Contact has activities RelatedField."""
        assert hasattr(Contact, "activities")
        assert isinstance(Contact.activities, RelatedField)

    def test_contact_has_contributions_relationship(self) -> None:
        """Test Contact has contributions RelatedField."""
        assert hasattr(Contact, "contributions")
        assert isinstance(Contact.contributions, RelatedField)

    def test_contact_has_employer_relationship(self) -> None:
        """Test Contact has employer ForeignKey."""
        assert hasattr(Contact, "employer")
        assert isinstance(Contact.employer, ForeignKey)

    def test_activity_has_source_contact_relationship(self) -> None:
        """Test Activity has source_contact ForeignKey."""
        assert hasattr(Activity, "source_contact")
        assert isinstance(Activity.source_contact, ForeignKey)

    def test_contribution_has_contact_relationship(self) -> None:
        """Test Contribution has contact ForeignKey."""
        assert hasattr(Contribution, "contact")
        assert isinstance(Contribution.contact, ForeignKey)

    def test_event_has_participants_relationship(self) -> None:
        """Test Event has participants RelatedField."""
        assert hasattr(Event, "participants")
        assert isinstance(Event.participants, RelatedField)

    def test_participant_has_event_relationship(self) -> None:
        """Test Participant has event ForeignKey."""
        assert hasattr(Participant, "event")
        assert isinstance(Participant.event, ForeignKey)
