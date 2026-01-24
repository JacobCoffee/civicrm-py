"""CRUD route factory for Litestar CiviCRM integration.

Provides automatic route generation for CiviCRM entities with full
CRUD operations, filtering, and pagination support.

Example:
    >>> from litestar import Litestar
    >>> from civicrm_py.contrib.litestar import CiviPlugin
    >>>
    >>> # Routes are automatically generated:
    >>> # GET    /api/civi/Contact         - List contacts
    >>> # GET    /api/civi/Contact/{id}    - Get single contact
    >>> # POST   /api/civi/Contact         - Create contact
    >>> # PUT    /api/civi/Contact/{id}    - Update contact
    >>> # DELETE /api/civi/Contact/{id}    - Delete contact
    >>>
    >>> app = Litestar(plugins=[CiviPlugin()])
"""

import logging
from typing import Any

from litestar import Controller, delete, get, post, put
from litestar.exceptions import NotFoundException
from litestar.params import Parameter

from civicrm_py.contrib.litestar.dto import (
    APIResponseDTO,
    ContactCreateDTO,
    ContactFilterDTO,
    ContactResponseDTO,
    ContactUpdateDTO,
)
from civicrm_py.core.client import CiviClient

logger = logging.getLogger("civicrm_py.contrib.litestar")


# =============================================================================
# Contact Controller
# =============================================================================


class ContactController(Controller):
    """Controller for Contact entity CRUD operations.

    Provides REST endpoints for managing CiviCRM Contacts with
    filtering, pagination, and full CRUD support.

    Routes:
        GET    /Contact         - List contacts with filtering
        GET    /Contact/{id}    - Get single contact by ID
        POST   /Contact         - Create new contact
        PUT    /Contact/{id}    - Update existing contact
        DELETE /Contact/{id}    - Delete contact
    """

    path = "/Contact"
    tags = ["Contact"]
    signature_types = [CiviClient]

    @get(
        path="/",
        summary="List Contacts",
        description="Retrieve a paginated list of contacts with optional filtering.",
        operation_id="list_contacts",
    )
    async def list_contacts(
        self,
        civi_client: CiviClient,
        limit: int = Parameter(default=25, ge=1, le=100, description="Max records to return"),
        offset: int = Parameter(default=0, ge=0, description="Records to skip"),
        contact_type: str | None = Parameter(default=None, description="Filter by contact type"),
        is_deleted: bool = Parameter(default=False, description="Include deleted contacts"),  # noqa: FBT001
        search: str | None = Parameter(default=None, description="Search in display_name"),
    ) -> APIResponseDTO:
        """List contacts with filtering and pagination.

        Args:
            civi_client: Injected CiviClient.
            limit: Maximum records to return (1-100).
            offset: Number of records to skip.
            contact_type: Filter by type (Individual, Organization, Household).
            is_deleted: Whether to include deleted contacts.
            search: Search string for display_name.

        Returns:
            APIResponseDTO with list of contacts.
        """
        where: list[list[Any]] = []

        if contact_type:
            where.append(["contact_type", "=", contact_type])
        if not is_deleted:
            where.append(["is_deleted", "=", False])
        if search:
            where.append(["display_name", "CONTAINS", search])

        response = await civi_client.get(
            "Contact",
            where=where if where else None,
            limit=limit,
            offset=offset,
        )

        return APIResponseDTO(
            values=response.values or [],
            count=response.count or 0,
            count_fetched=response.countFetched or 0,
        )

    @get(
        path="/{contact_id:int}",
        summary="Get Contact",
        description="Retrieve a single contact by ID.",
        operation_id="get_contact",
    )
    async def get_contact(
        self,
        civi_client: CiviClient,
        contact_id: int = Parameter(description="Contact ID"),
    ) -> ContactResponseDTO:
        """Get a single contact by ID.

        Args:
            civi_client: Injected CiviClient.
            contact_id: The contact's unique identifier.

        Returns:
            ContactResponseDTO with contact data.

        Raises:
            NotFoundException: If contact does not exist.
        """
        response = await civi_client.get(
            "Contact",
            where=[["id", "=", contact_id]],
            limit=1,
        )

        if not response.values:
            raise NotFoundException(detail=f"Contact with id {contact_id} not found")

        data = response.values[0]
        return ContactResponseDTO(**data)

    @post(
        path="/",
        summary="Create Contact",
        description="Create a new contact.",
        operation_id="create_contact",
    )
    async def create_contact(
        self,
        civi_client: CiviClient,
        data: ContactCreateDTO,
    ) -> ContactResponseDTO:
        """Create a new contact.

        Args:
            civi_client: Injected CiviClient.
            data: Contact creation data.

        Returns:
            ContactResponseDTO with created contact.
        """
        import msgspec

        values = {k: v for k, v in msgspec.to_builtins(data).items() if v is not None}

        response = await civi_client.create("Contact", values)

        if not response.values:
            msg = "Failed to create contact"
            raise RuntimeError(msg)

        return ContactResponseDTO(**response.values[0])

    @put(
        path="/{contact_id:int}",
        summary="Update Contact",
        description="Update an existing contact.",
        operation_id="update_contact",
    )
    async def update_contact(
        self,
        civi_client: CiviClient,
        contact_id: int,
        data: ContactUpdateDTO,
    ) -> ContactResponseDTO:
        """Update an existing contact.

        Args:
            civi_client: Injected CiviClient.
            contact_id: The contact's unique identifier.
            data: Contact update data.

        Returns:
            ContactResponseDTO with updated contact.

        Raises:
            NotFoundException: If contact does not exist.
        """
        import msgspec

        values = {k: v for k, v in msgspec.to_builtins(data).items() if v is not None}

        if not values:
            # No updates provided, just fetch current state
            get_response = await civi_client.get(
                "Contact",
                where=[["id", "=", contact_id]],
                limit=1,
            )
            if not get_response.values:
                raise NotFoundException(detail=f"Contact with id {contact_id} not found")
            return ContactResponseDTO(**get_response.values[0])

        response = await civi_client.update(
            "Contact",
            values=values,
            where=[["id", "=", contact_id]],
        )

        if not response.values:
            raise NotFoundException(detail=f"Contact with id {contact_id} not found")

        return ContactResponseDTO(**response.values[0])

    @delete(
        path="/{contact_id:int}",
        summary="Delete Contact",
        description="Delete a contact (soft delete).",
        operation_id="delete_contact",
    )
    async def delete_contact(
        self,
        civi_client: CiviClient,
        contact_id: int,
    ) -> None:
        """Delete a contact.

        Performs a soft delete by setting is_deleted=True.

        Args:
            civi_client: Injected CiviClient.
            contact_id: The contact's unique identifier.

        Raises:
            NotFoundException: If contact does not exist.
        """
        response = await civi_client.delete(
            "Contact",
            where=[["id", "=", contact_id]],
        )

        if response.count == 0:
            raise NotFoundException(detail=f"Contact with id {contact_id} not found")


# =============================================================================
# Generic Entity Controller Factory
# =============================================================================


def create_entity_controller(
    entity_name: str,
    *,
    path: str | None = None,
    tags: list[str] | None = None,
) -> type[Controller]:
    """Factory to create a generic CRUD controller for any CiviCRM entity.

    Creates a Litestar Controller class with standard CRUD operations
    for the specified CiviCRM entity.

    Args:
        entity_name: CiviCRM entity name (e.g., "Activity", "Contribution").
        path: URL path prefix. Defaults to /{entity_name}.
        tags: OpenAPI tags. Defaults to [entity_name].

    Returns:
        Controller class with CRUD operations.

    Example:
        >>> ActivityController = create_entity_controller("Activity")
        >>> ContributionController = create_entity_controller("Contribution")
    """
    controller_path = path or f"/{entity_name}"
    controller_tags = tags or [entity_name]

    class GenericEntityController(Controller):
        path = controller_path
        tags = controller_tags
        signature_types = [CiviClient]

        @get(
            path="/",
            summary=f"List {entity_name}",
            operation_id=f"list_{entity_name.lower()}",
        )
        async def list_entities(
            self,
            civi_client: CiviClient,
            limit: int = Parameter(default=25, ge=1, le=100),
            offset: int = Parameter(default=0, ge=0),
        ) -> APIResponseDTO:
            response = await civi_client.get(
                entity_name,
                limit=limit,
                offset=offset,
            )
            return APIResponseDTO(
                values=response.values or [],
                count=response.count or 0,
                count_fetched=response.countFetched or 0,
            )

        @get(
            path="/{entity_id:int}",
            summary=f"Get {entity_name}",
            operation_id=f"get_{entity_name.lower()}",
        )
        async def get_entity(
            self,
            civi_client: CiviClient,
            entity_id: int,
        ) -> dict[str, Any]:
            response = await civi_client.get(
                entity_name,
                where=[["id", "=", entity_id]],
                limit=1,
            )
            if not response.values:
                raise NotFoundException(detail=f"{entity_name} with id {entity_id} not found")
            return response.values[0]

        @post(
            path="/",
            summary=f"Create {entity_name}",
            operation_id=f"create_{entity_name.lower()}",
        )
        async def create_entity(
            self,
            civi_client: CiviClient,
            data: dict[str, Any],
        ) -> dict[str, Any]:
            response = await civi_client.create(entity_name, data)
            if not response.values:
                msg = f"Failed to create {entity_name}"
                raise RuntimeError(msg)
            return response.values[0]

        @put(
            path="/{entity_id:int}",
            summary=f"Update {entity_name}",
            operation_id=f"update_{entity_name.lower()}",
        )
        async def update_entity(
            self,
            civi_client: CiviClient,
            entity_id: int,
            data: dict[str, Any],
        ) -> dict[str, Any]:
            response = await civi_client.update(
                entity_name,
                values=data,
                where=[["id", "=", entity_id]],
            )
            if not response.values:
                raise NotFoundException(detail=f"{entity_name} with id {entity_id} not found")
            return response.values[0]

        @delete(
            path="/{entity_id:int}",
            summary=f"Delete {entity_name}",
            operation_id=f"delete_{entity_name.lower()}",
        )
        async def delete_entity(
            self,
            civi_client: CiviClient,
            entity_id: int,
        ) -> None:
            response = await civi_client.delete(
                entity_name,
                where=[["id", "=", entity_id]],
            )
            if response.count == 0:
                raise NotFoundException(detail=f"{entity_name} with id {entity_id} not found")

    GenericEntityController.__name__ = f"{entity_name}Controller"
    GenericEntityController.__qualname__ = f"{entity_name}Controller"
    # Ensure CiviClient is available in the class's module namespace for type resolution
    GenericEntityController.__module__ = __name__

    return GenericEntityController


# Pre-built controllers for common entities
ActivityController = create_entity_controller("Activity")
ContributionController = create_entity_controller("Contribution")
EventController = create_entity_controller("Event")
MembershipController = create_entity_controller("Membership")
ParticipantController = create_entity_controller("Participant")
GroupController = create_entity_controller("Group")


# Default entity controllers to register
DEFAULT_CONTROLLERS: list[type[Controller]] = [
    ContactController,
    ActivityController,
    ContributionController,
    EventController,
    MembershipController,
    ParticipantController,
    GroupController,
]


def get_entity_controllers(
    include_entities: list[str] | None = None,
    exclude_entities: list[str] | None = None,
) -> list[type[Controller]]:
    """Get list of entity controllers based on include/exclude filters.

    Args:
        include_entities: Only include these entities. None means all.
        exclude_entities: Exclude these entities.

    Returns:
        List of Controller classes to register.
    """
    exclude_set = set(exclude_entities or [])

    if include_entities is not None:
        include_set = set(include_entities)
        return [
            ctrl
            for ctrl in DEFAULT_CONTROLLERS
            if ctrl.__name__.replace("Controller", "") in include_set
            and ctrl.__name__.replace("Controller", "") not in exclude_set
        ]

    return [ctrl for ctrl in DEFAULT_CONTROLLERS if ctrl.__name__.replace("Controller", "") not in exclude_set]


__all__ = [
    "DEFAULT_CONTROLLERS",
    "APIResponseDTO",
    "ActivityController",
    "ContactController",
    "ContactCreateDTO",
    "ContactFilterDTO",
    "ContactResponseDTO",
    "ContactUpdateDTO",
    "ContributionController",
    "EventController",
    "GroupController",
    "MembershipController",
    "ParticipantController",
    "create_entity_controller",
    "get_entity_controllers",
]
