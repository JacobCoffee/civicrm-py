"""Action mapping between CiviCRM API v4 actions and EntityManager methods.

This module defines the mapping between CiviCRM's API actions and the methods
implemented in civi-py's EntityManager. It also tracks entity-specific custom
actions that require special handling.

Key Components:
    - ACTION_METHOD_MAP: Maps CiviCRM actions to EntityManager methods
    - ENTITY_CUSTOM_ACTIONS: Entity-specific custom actions
    - ActionInfo: Detailed information about an action
    - ActionMapping: Complete mapping with priority and implementation status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

__all__ = [
    "ACTION_METHOD_MAP",
    "ENTITY_CUSTOM_ACTIONS",
    "STANDARD_CIVICRM_ACTIONS",
    "ActionCategory",
    "ActionInfo",
    "ActionMapping",
    "ActionPriority",
    "get_action_info",
    "get_entity_custom_actions",
    "is_action_implemented",
]


class ActionCategory(Enum):
    """Category of CiviCRM actions.

    Used to classify actions by their purpose and implementation complexity.
    """

    CRUD = "crud"  # Basic Create, Read, Update, Delete
    METADATA = "metadata"  # Field/action introspection
    BATCH = "batch"  # Bulk operations
    UTILITY = "utility"  # Helper/utility actions
    SECURITY = "security"  # Access control actions
    CUSTOM = "custom"  # Entity-specific custom actions
    WORKFLOW = "workflow"  # Workflow/state transition actions
    FINANCIAL = "financial"  # Financial processing actions
    COMMUNICATION = "communication"  # Email/SMS actions


class ActionPriority(Enum):
    """Priority for implementing an action.

    Based on common usage patterns and API completeness goals.
    """

    CRITICAL = 1  # Must have for basic functionality
    HIGH = 2  # Important for common use cases
    MEDIUM = 3  # Useful for advanced features
    LOW = 4  # Nice to have
    OPTIONAL = 5  # Rarely needed


@dataclass
class ActionInfo:
    """Information about a CiviCRM action.

    Attributes:
        name: Action name as used in API calls.
        category: Category classification.
        priority: Implementation priority.
        description: Human-readable description.
        entity_methods: Set of EntityManager methods that implement this action.
        is_standard: Whether this is a standard CiviCRM action.
        requires_special_handling: Whether this action needs custom implementation.
        notes: Implementation notes or caveats.
    """

    name: str
    category: ActionCategory
    priority: ActionPriority
    description: str = ""
    entity_methods: set[str] = field(default_factory=set)
    is_standard: bool = True
    requires_special_handling: bool = False
    notes: str = ""

    @property
    def is_implemented(self) -> bool:
        """Check if this action has any implementation."""
        return len(self.entity_methods) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "category": self.category.value,
            "priority": self.priority.name,
            "priority_value": self.priority.value,
            "description": self.description,
            "entity_methods": sorted(self.entity_methods),
            "is_standard": self.is_standard,
            "is_implemented": self.is_implemented,
            "requires_special_handling": self.requires_special_handling,
            "notes": self.notes,
        }


# Standard CiviCRM API v4 actions with their mappings
STANDARD_CIVICRM_ACTIONS: dict[str, ActionInfo] = {
    # CRUD Operations
    "get": ActionInfo(
        name="get",
        category=ActionCategory.CRUD,
        priority=ActionPriority.CRITICAL,
        description="Retrieve records matching criteria",
        entity_methods={"get", "filter", "all", "count", "exists", "select", "limit", "offset", "order_by", "exclude"},
        notes="Fully implemented via QuerySet pattern",
    ),
    "create": ActionInfo(
        name="create",
        category=ActionCategory.CRUD,
        priority=ActionPriority.CRITICAL,
        description="Create a new record",
        entity_methods={"create", "bulk_create", "get_or_create", "update_or_create"},
        notes="Supports single and bulk creation",
    ),
    "update": ActionInfo(
        name="update",
        category=ActionCategory.CRUD,
        priority=ActionPriority.CRITICAL,
        description="Update existing records",
        entity_methods={"update", "update_or_create"},
        notes="Supports conditional updates",
    ),
    "delete": ActionInfo(
        name="delete",
        category=ActionCategory.CRUD,
        priority=ActionPriority.CRITICAL,
        description="Delete records matching criteria",
        entity_methods={"delete"},
        notes="Supports conditional deletion",
    ),
    "save": ActionInfo(
        name="save",
        category=ActionCategory.CRUD,
        priority=ActionPriority.HIGH,
        description="Create or update records (upsert)",
        entity_methods={"update_or_create"},
        notes="Implemented via update_or_create pattern",
    ),
    # Metadata Operations
    "getFields": ActionInfo(
        name="getFields",
        category=ActionCategory.METADATA,
        priority=ActionPriority.HIGH,
        description="Get field metadata for entity",
        entity_methods={"get_fields"},
        notes="Returns field definitions",
    ),
    "getActions": ActionInfo(
        name="getActions",
        category=ActionCategory.METADATA,
        priority=ActionPriority.MEDIUM,
        description="Get available actions for entity",
        entity_methods=set(),
        notes="Used for introspection, not commonly needed in client code",
    ),
    "getLinks": ActionInfo(
        name="getLinks",
        category=ActionCategory.METADATA,
        priority=ActionPriority.LOW,
        description="Get related entity links",
        entity_methods=set(),
        notes="Useful for dynamic UI generation",
    ),
    # Security Operations
    "checkAccess": ActionInfo(
        name="checkAccess",
        category=ActionCategory.SECURITY,
        priority=ActionPriority.MEDIUM,
        description="Check if user has permission for action",
        entity_methods=set(),
        requires_special_handling=True,
        notes="ACL/permission checking",
    ),
    # Batch Operations
    "replace": ActionInfo(
        name="replace",
        category=ActionCategory.BATCH,
        priority=ActionPriority.MEDIUM,
        description="Replace all matching records with new set",
        entity_methods=set(),
        requires_special_handling=True,
        notes="Atomic replace of related records",
    ),
    # Utility Operations
    "refresh": ActionInfo(
        name="refresh",
        category=ActionCategory.UTILITY,
        priority=ActionPriority.LOW,
        description="Refresh cached/computed values",
        entity_methods=set(),
        notes="Entity-specific computed field refresh",
    ),
    "getChecksum": ActionInfo(
        name="getChecksum",
        category=ActionCategory.SECURITY,
        priority=ActionPriority.LOW,
        description="Generate checksum for anonymous links",
        entity_methods=set(),
        requires_special_handling=True,
        notes="Used for secure anonymous access (e.g., contribution pages)",
    ),
    "validateChecksum": ActionInfo(
        name="validateChecksum",
        category=ActionCategory.SECURITY,
        priority=ActionPriority.LOW,
        description="Validate a checksum",
        entity_methods=set(),
        requires_special_handling=True,
        notes="Validates checksums for anonymous access",
    ),
    "autocomplete": ActionInfo(
        name="autocomplete",
        category=ActionCategory.UTILITY,
        priority=ActionPriority.LOW,
        description="Get autocomplete suggestions",
        entity_methods=set(),
        notes="Used for search/typeahead functionality",
    ),
    "export": ActionInfo(
        name="export",
        category=ActionCategory.UTILITY,
        priority=ActionPriority.LOW,
        description="Export records to file format",
        entity_methods=set(),
        requires_special_handling=True,
        notes="CSV/Excel export functionality",
    ),
}

# Entity-specific custom actions
# These are actions unique to certain entities that aren't covered by standard CRUD
ENTITY_CUSTOM_ACTIONS: dict[str, list[ActionInfo]] = {
    "Contact": [
        ActionInfo(
            name="merge",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.HIGH,
            description="Merge duplicate contacts",
            is_standard=False,
            requires_special_handling=True,
            notes="Merges contact records and related data",
        ),
        ActionInfo(
            name="getduplicates",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.MEDIUM,
            description="Find potential duplicate contacts",
            is_standard=False,
            notes="Duplicate detection using dedupe rules",
        ),
        ActionInfo(
            name="findDuplicates",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.MEDIUM,
            description="Find duplicates for a specific contact",
            is_standard=False,
            notes="Alias for getduplicates with contact focus",
        ),
    ],
    "Contribution": [
        ActionInfo(
            name="completetransaction",
            category=ActionCategory.FINANCIAL,
            priority=ActionPriority.HIGH,
            description="Complete a pending contribution transaction",
            is_standard=False,
            requires_special_handling=True,
            notes="Processes pending contributions and triggers post-payment hooks",
        ),
        ActionInfo(
            name="repeattransaction",
            category=ActionCategory.FINANCIAL,
            priority=ActionPriority.MEDIUM,
            description="Create a repeat of an existing transaction",
            is_standard=False,
            requires_special_handling=True,
            notes="For recurring contributions",
        ),
        ActionInfo(
            name="sendconfirmation",
            category=ActionCategory.COMMUNICATION,
            priority=ActionPriority.MEDIUM,
            description="Send contribution confirmation email",
            is_standard=False,
            notes="Triggers email receipt/confirmation",
        ),
        ActionInfo(
            name="updatestatus",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.HIGH,
            description="Update contribution status with proper hooks",
            is_standard=False,
            notes="Handles status transitions properly",
        ),
    ],
    "Activity": [
        ActionInfo(
            name="complete",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.MEDIUM,
            description="Mark activity as completed",
            is_standard=False,
            notes="Sets status to Completed with timestamp",
        ),
        ActionInfo(
            name="sendemail",
            category=ActionCategory.COMMUNICATION,
            priority=ActionPriority.MEDIUM,
            description="Send activity as email",
            is_standard=False,
            notes="Creates email from activity content",
        ),
    ],
    "Event": [
        ActionInfo(
            name="copy",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.MEDIUM,
            description="Clone an event with all settings",
            is_standard=False,
            notes="Deep copy of event configuration",
        ),
        ActionInfo(
            name="getOnlineRegistrationUrl",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.LOW,
            description="Get public registration URL",
            is_standard=False,
            notes="Returns the public-facing registration link",
        ),
    ],
    "Membership": [
        ActionInfo(
            name="renew",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.HIGH,
            description="Renew membership with proper status transitions",
            is_standard=False,
            requires_special_handling=True,
            notes="Handles renewal logic and dates",
        ),
    ],
    "Participant": [
        ActionInfo(
            name="register",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.HIGH,
            description="Register contact for event",
            is_standard=False,
            notes="Creates participant with proper defaults",
        ),
        ActionInfo(
            name="transfer",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.LOW,
            description="Transfer registration to another contact",
            is_standard=False,
            notes="Moves registration between contacts",
        ),
    ],
    "Group": [
        ActionInfo(
            name="addcontact",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.HIGH,
            description="Add contact to group",
            is_standard=False,
            notes="Creates GroupContact record",
        ),
        ActionInfo(
            name="removecontact",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.HIGH,
            description="Remove contact from group",
            is_standard=False,
            notes="Removes GroupContact record",
        ),
        ActionInfo(
            name="rebuild",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.LOW,
            description="Rebuild smart group cache",
            is_standard=False,
            notes="Refreshes smart group membership",
        ),
    ],
    "Tag": [
        ActionInfo(
            name="taggable",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.LOW,
            description="Get entities that can be tagged",
            is_standard=False,
            notes="Returns taggable entity types",
        ),
    ],
    "Note": [
        ActionInfo(
            name="attach",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.MEDIUM,
            description="Attach note to an entity",
            is_standard=False,
            notes="Links note to parent entity",
        ),
    ],
    "Email": [
        ActionInfo(
            name="send",
            category=ActionCategory.COMMUNICATION,
            priority=ActionPriority.HIGH,
            description="Send email to address",
            is_standard=False,
            requires_special_handling=True,
            notes="Sends email via configured MTA",
        ),
    ],
    "Address": [
        ActionInfo(
            name="geocode",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.LOW,
            description="Geocode address to get coordinates",
            is_standard=False,
            notes="Uses configured geocoding provider",
        ),
    ],
    "Case": [
        ActionInfo(
            name="open",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.HIGH,
            description="Open a new case",
            is_standard=False,
            notes="Creates case with initial activities",
        ),
        ActionInfo(
            name="close",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.HIGH,
            description="Close an existing case",
            is_standard=False,
            notes="Sets case status to closed",
        ),
        ActionInfo(
            name="addtimeline",
            category=ActionCategory.CUSTOM,
            priority=ActionPriority.MEDIUM,
            description="Add timeline to case",
            is_standard=False,
            notes="Adds activity timeline",
        ),
    ],
    "Relationship": [
        ActionInfo(
            name="expire",
            category=ActionCategory.WORKFLOW,
            priority=ActionPriority.LOW,
            description="Expire a relationship",
            is_standard=False,
            notes="Sets end date to current date",
        ),
    ],
    "Campaign": [
        ActionInfo(
            name="clone",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.LOW,
            description="Clone campaign with settings",
            is_standard=False,
            notes="Creates copy of campaign",
        ),
    ],
    "Pledge": [
        ActionInfo(
            name="calculatepayments",
            category=ActionCategory.FINANCIAL,
            priority=ActionPriority.MEDIUM,
            description="Calculate pledge payment schedule",
            is_standard=False,
            notes="Generates payment schedule based on pledge terms",
        ),
    ],
    "ContributionRecur": [
        ActionInfo(
            name="cancel",
            category=ActionCategory.FINANCIAL,
            priority=ActionPriority.HIGH,
            description="Cancel recurring contribution",
            is_standard=False,
            requires_special_handling=True,
            notes="Cancels with proper cleanup",
        ),
        ActionInfo(
            name="updateamount",
            category=ActionCategory.FINANCIAL,
            priority=ActionPriority.MEDIUM,
            description="Update recurring amount",
            is_standard=False,
            notes="Changes recurring contribution amount",
        ),
    ],
    "Job": [
        ActionInfo(
            name="execute",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.MEDIUM,
            description="Execute a scheduled job",
            is_standard=False,
            requires_special_handling=True,
            notes="Triggers job execution",
        ),
    ],
    "Mailing": [
        ActionInfo(
            name="submit",
            category=ActionCategory.COMMUNICATION,
            priority=ActionPriority.HIGH,
            description="Submit mailing for sending",
            is_standard=False,
            requires_special_handling=True,
            notes="Queues mailing for delivery",
        ),
        ActionInfo(
            name="preview",
            category=ActionCategory.UTILITY,
            priority=ActionPriority.MEDIUM,
            description="Preview mailing content",
            is_standard=False,
            notes="Returns rendered mailing preview",
        ),
    ],
}


@dataclass
class ActionMapping:
    """Complete action mapping for an entity.

    Provides comprehensive information about which actions are available
    for an entity and how they map to EntityManager methods.

    Attributes:
        entity_name: Name of the CiviCRM entity.
        standard_actions: Standard actions available for this entity.
        custom_actions: Entity-specific custom actions.
        api_actions: Actions actually available from API (if fetched).
    """

    entity_name: str
    standard_actions: dict[str, ActionInfo] = field(default_factory=dict)
    custom_actions: list[ActionInfo] = field(default_factory=list)
    api_actions: set[str] = field(default_factory=set)

    # Manager methods available in EntityManager
    MANAGER_METHODS: ClassVar[set[str]] = {
        "get",
        "create",
        "update",
        "delete",
        "get_fields",
        "count",
        "exists",
        "get_or_create",
        "update_or_create",
        "bulk_create",
        "all",
        "filter",
        "exclude",
        "select",
        "order_by",
        "limit",
        "offset",
    }

    def __post_init__(self) -> None:
        """Initialize with standard actions if not provided."""
        if not self.standard_actions:
            self.standard_actions = dict(STANDARD_CIVICRM_ACTIONS)
        if not self.custom_actions:
            self.custom_actions = list(ENTITY_CUSTOM_ACTIONS.get(self.entity_name, []))

    @property
    def all_actions(self) -> list[ActionInfo]:
        """Get all actions (standard + custom)."""
        return list(self.standard_actions.values()) + self.custom_actions

    @property
    def implemented_actions(self) -> list[ActionInfo]:
        """Get actions that have implementation."""
        return [a for a in self.all_actions if a.is_implemented]

    @property
    def unimplemented_actions(self) -> list[ActionInfo]:
        """Get actions without implementation."""
        return [a for a in self.all_actions if not a.is_implemented]

    @property
    def high_priority_missing(self) -> list[ActionInfo]:
        """Get high-priority unimplemented actions."""
        return [a for a in self.unimplemented_actions if a.priority in (ActionPriority.CRITICAL, ActionPriority.HIGH)]

    def coverage_percentage(self, include_custom: bool = True) -> float:
        """Calculate action coverage percentage.

        Args:
            include_custom: Whether to include custom actions in calculation.

        Returns:
            Percentage of actions that are implemented.
        """
        if include_custom:
            total = len(self.all_actions)
            implemented = len(self.implemented_actions)
        else:
            total = len(self.standard_actions)
            implemented = len([a for a in self.standard_actions.values() if a.is_implemented])

        if total == 0:
            return 0.0
        return (implemented / total) * 100

    def api_coverage_percentage(self) -> float:
        """Calculate coverage against actual API actions.

        Returns:
            Percentage of API actions that are implemented.
        """
        if not self.api_actions:
            return 0.0

        implemented = sum(
            1
            for action_name in self.api_actions
            if action_name in self.standard_actions and self.standard_actions[action_name].is_implemented
        )
        return (implemented / len(self.api_actions)) * 100

    def get_action_status(self, action_name: str) -> dict[str, Any]:
        """Get detailed status for a specific action.

        Args:
            action_name: Name of the action.

        Returns:
            Dict with action status details.
        """
        # Check standard actions first
        if action_name in self.standard_actions:
            action = self.standard_actions[action_name]
            return {
                "action": action_name,
                "status": "implemented" if action.is_implemented else "not_implemented",
                "type": "standard",
                "priority": action.priority.name,
                "methods": sorted(action.entity_methods),
                "notes": action.notes,
            }

        # Check custom actions
        for custom in self.custom_actions:
            if custom.name == action_name:
                return {
                    "action": action_name,
                    "status": "implemented" if custom.is_implemented else "not_implemented",
                    "type": "custom",
                    "priority": custom.priority.name,
                    "methods": sorted(custom.entity_methods),
                    "notes": custom.notes,
                }

        # Unknown action
        return {
            "action": action_name,
            "status": "unknown",
            "type": "unknown",
            "priority": "UNKNOWN",
            "methods": [],
            "notes": "Action not found in mapping",
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_name": self.entity_name,
            "summary": {
                "total_actions": len(self.all_actions),
                "implemented": len(self.implemented_actions),
                "unimplemented": len(self.unimplemented_actions),
                "coverage_percentage": round(self.coverage_percentage(), 2),
                "api_coverage_percentage": round(self.api_coverage_percentage(), 2) if self.api_actions else None,
            },
            "standard_actions": {name: info.to_dict() for name, info in self.standard_actions.items()},
            "custom_actions": [a.to_dict() for a in self.custom_actions],
            "high_priority_missing": [a.to_dict() for a in self.high_priority_missing],
            "api_actions": sorted(self.api_actions) if self.api_actions else None,
        }


# Convenience mapping from CiviCRM action names to EntityManager methods
ACTION_METHOD_MAP: dict[str, set[str]] = {
    action.name: action.entity_methods for action in STANDARD_CIVICRM_ACTIONS.values()
}


def get_action_info(action_name: str) -> ActionInfo | None:
    """Get information about a standard action.

    Args:
        action_name: Name of the CiviCRM action.

    Returns:
        ActionInfo if action is known, None otherwise.
    """
    return STANDARD_CIVICRM_ACTIONS.get(action_name)


def get_entity_custom_actions(entity_name: str) -> list[ActionInfo]:
    """Get custom actions for an entity.

    Args:
        entity_name: Name of the CiviCRM entity.

    Returns:
        List of custom ActionInfo for this entity.
    """
    return list(ENTITY_CUSTOM_ACTIONS.get(entity_name, []))


def is_action_implemented(action_name: str) -> bool:
    """Check if an action has any implementation.

    Args:
        action_name: Name of the CiviCRM action.

    Returns:
        True if action has EntityManager methods, False otherwise.
    """
    action = STANDARD_CIVICRM_ACTIONS.get(action_name)
    return action is not None and action.is_implemented
