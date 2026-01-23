"""Query module: QuerySet and Manager implementations."""

from __future__ import annotations

# Re-export exceptions from core for convenience
from civi_py.core.exceptions import DoesNotExist, MultipleObjectsReturned
from civi_py.query.manager import (
    EntityManager,
    ManagerDescriptor,
    SyncEntityManager,
)
from civi_py.query.queryset import QuerySet

__all__ = [
    "DoesNotExist",
    "EntityManager",
    "ManagerDescriptor",
    "MultipleObjectsReturned",
    "QuerySet",
    "SyncEntityManager",
]
