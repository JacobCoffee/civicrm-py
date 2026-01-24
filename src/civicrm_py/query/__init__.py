"""Query module: QuerySet and Manager implementations."""

from __future__ import annotations

# Re-export exceptions from core for convenience
from civicrm_py.core.exceptions import DoesNotExist, MultipleObjectsReturned
from civicrm_py.query.manager import (
    EntityManager,
    ManagerDescriptor,
    SyncEntityManager,
)
from civicrm_py.query.queryset import QuerySet

__all__ = [
    "DoesNotExist",
    "EntityManager",
    "ManagerDescriptor",
    "MultipleObjectsReturned",
    "QuerySet",
    "SyncEntityManager",
]
