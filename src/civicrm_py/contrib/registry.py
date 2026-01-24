"""Integration registry for auto-discovery of framework integrations.

Provides a centralized registry for framework integrations that can be
discovered automatically via Python entry points or registered manually.

Example:
    # Auto-discover integrations from entry points
    >>> from civicrm_py.contrib.registry import discover_integrations
    >>> discover_integrations()

    # Get a specific integration
    >>> from civicrm_py.contrib.registry import get_integration
    >>> DjangoIntegration = get_integration("django")
    >>> integration = DjangoIntegration()

    # Register a custom integration
    >>> from civicrm_py.contrib.registry import register_integration
    >>> @register_integration("my_framework")
    ... class MyFrameworkIntegration(BaseIntegration):
    ...     pass
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from civicrm_py.contrib.integration import BaseIntegration


logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """Singleton registry for framework integrations.

    Manages registration and discovery of framework integrations.
    Uses entry points for automatic discovery when packages are installed
    via pip (e.g., `pip install civi-py[django]`).

    Thread-safe singleton implementation ensures only one registry
    exists across the application.

    Example:
        >>> registry = IntegrationRegistry.get_instance()
        >>> registry.auto_discover()
        >>> available = registry.list_integrations()
        >>> print(available)  # ['django', 'litestar', 'flask', ...]
    """

    _instance: IntegrationRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    # Instance attributes declared for type checking
    _integrations: dict[str, type[BaseIntegration]]
    _discovered: bool

    def __new__(cls) -> IntegrationRegistry:  # noqa: PYI034
        """Create or return the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                # Initialize instance attributes in __new__ for thread safety
                instance._integrations = {}
                instance._discovered = False
                cls._instance = instance
            return cls._instance

    def __init__(self) -> None:
        """Initialize the registry.

        Note: Due to singleton pattern, __init__ may be called multiple times
        but the instance attributes are only set once in __new__.
        """
        # Attributes are initialized in __new__ for thread safety

    @classmethod
    def get_instance(cls) -> IntegrationRegistry:
        """Get the singleton registry instance.

        Returns:
            The global IntegrationRegistry instance.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> registry.register("custom", CustomIntegration)
        """
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance.

        Primarily useful for testing to ensure a clean state.

        Warning:
            This method should not be called in production code.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance._integrations.clear()
                cls._instance._discovered = False
            cls._instance = None

    def register(self, name: str, integration_class: type[BaseIntegration]) -> None:
        """Register an integration class.

        Args:
            name: Unique name for the integration (e.g., 'django', 'litestar').
            integration_class: The integration class to register.

        Raises:
            ValueError: If an integration with the same name is already registered.
            TypeError: If integration_class is not a subclass of BaseIntegration.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> registry.register("django", DjangoIntegration)
        """
        # Import here to avoid circular imports
        from civicrm_py.contrib.integration import BaseIntegration

        if not isinstance(integration_class, type):
            msg = f"Expected a class, got {type(integration_class).__name__}"
            raise TypeError(msg)

        if not issubclass(integration_class, BaseIntegration):
            msg = f"{integration_class.__name__} must be a subclass of BaseIntegration"
            raise TypeError(msg)

        with self._lock:
            if name in self._integrations:
                existing = self._integrations[name]
                if existing is not integration_class:
                    logger.warning(
                        "Overwriting existing integration %r (%s) with %s",
                        name,
                        existing.__name__,
                        integration_class.__name__,
                    )
            self._integrations[name] = integration_class
            logger.debug("Registered integration %r: %s", name, integration_class.__name__)

    def unregister(self, name: str) -> bool:
        """Unregister an integration.

        Args:
            name: Name of the integration to remove.

        Returns:
            True if the integration was removed, False if it wasn't registered.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> registry.unregister("old_integration")
            True
        """
        with self._lock:
            if name in self._integrations:
                del self._integrations[name]
                logger.debug("Unregistered integration %r", name)
                return True
            return False

    def get(self, name: str) -> type[BaseIntegration] | None:
        """Get an integration class by name.

        Args:
            name: Name of the integration (e.g., 'django', 'litestar').

        Returns:
            The integration class if found, None otherwise.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> DjangoIntegration = registry.get("django")
            >>> if DjangoIntegration:
            ...     integration = DjangoIntegration()
        """
        return self._integrations.get(name)

    def get_or_raise(self, name: str) -> type[BaseIntegration]:
        """Get an integration class by name or raise an error.

        Args:
            name: Name of the integration.

        Returns:
            The integration class.

        Raises:
            KeyError: If the integration is not registered.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> DjangoIntegration = registry.get_or_raise("django")
        """
        integration = self.get(name)
        if integration is None:
            available = ", ".join(sorted(self._integrations.keys())) or "none"
            msg = f"Integration {name!r} not found. Available: {available}"
            raise KeyError(msg)
        return integration

    def list_integrations(self) -> list[str]:
        """List all registered integration names.

        Returns:
            Sorted list of integration names.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> registry.auto_discover()
            >>> print(registry.list_integrations())
            ['django', 'flask', 'litestar']
        """
        return sorted(self._integrations.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an integration is registered.

        Args:
            name: Name of the integration.

        Returns:
            True if registered, False otherwise.
        """
        return name in self._integrations

    def auto_discover(self, *, force: bool = False) -> int:
        """Discover and register integrations from entry points.

        Looks for entry points in the 'civicrm_py.integrations' group.
        Each entry point should point to a BaseIntegration subclass.

        Entry points are defined in pyproject.toml:
            [project.entry-points."civicrm_py.integrations"]
            django = "civicrm_py.contrib.django:DjangoIntegration"
            litestar = "civicrm_py.contrib.litestar:LitestarIntegration"

        Args:
            force: If True, re-run discovery even if already done.

        Returns:
            Number of integrations discovered.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> count = registry.auto_discover()
            >>> print(f"Discovered {count} integrations")
        """
        if self._discovered and not force:
            logger.debug("Auto-discovery already completed, skipping")
            return 0

        discovered_count = 0

        # Python 3.10+ entry points API (we target 3.10+)
        from importlib.metadata import entry_points

        eps = entry_points(group="civicrm_py.integrations")

        for ep in eps:
            try:
                integration_class = ep.load()
                self.register(ep.name, integration_class)
                discovered_count += 1
                logger.info("Auto-discovered integration %r from %s", ep.name, ep.value)
            except Exception:
                logger.exception("Failed to load integration entry point %r", ep.name)

        self._discovered = True
        logger.debug("Auto-discovery complete: found %d integrations", discovered_count)
        return discovered_count

    def __contains__(self, name: object) -> bool:
        """Check if an integration is registered using 'in' operator.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> if "django" in registry:
            ...     print("Django integration available")
        """
        if not isinstance(name, str):
            return False
        return self.is_registered(name)

    def __iter__(self) -> Iterator[str]:
        """Iterate over registered integration names.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> for name in registry:
            ...     print(name)
        """
        return iter(sorted(self._integrations.keys()))

    def __len__(self) -> int:
        """Return the number of registered integrations.

        Example:
            >>> registry = IntegrationRegistry.get_instance()
            >>> print(f"{len(registry)} integrations available")
        """
        return len(self._integrations)

    def __repr__(self) -> str:
        """String representation of the registry."""
        integrations = ", ".join(sorted(self._integrations.keys())) or "none"
        return f"<IntegrationRegistry integrations=[{integrations}]>"


def register_integration(name: str) -> Callable[[type[BaseIntegration]], type[BaseIntegration]]:
    """Decorator to register an integration class.

    Registers the decorated class with the global IntegrationRegistry
    under the specified name.

    Args:
        name: Name for the integration (e.g., 'django', 'litestar').

    Returns:
        Decorator function that registers the class.

    Example:
        >>> from civicrm_py.contrib.integration import BaseIntegration
        >>> from civicrm_py.contrib.registry import register_integration
        >>>
        >>> @register_integration("my_framework")
        ... class MyFrameworkIntegration(BaseIntegration):
        ...     name = "my_framework"
        ...
        ...     def configure_from_framework(self, settings):
        ...         pass
    """

    def decorator(cls: type[BaseIntegration]) -> type[BaseIntegration]:
        IntegrationRegistry.get_instance().register(name, cls)
        return cls

    return decorator


def get_integration(name: str) -> type[BaseIntegration] | None:
    """Get an integration class by name.

    Convenience function that wraps IntegrationRegistry.get().

    Args:
        name: Name of the integration (e.g., 'django', 'litestar').

    Returns:
        The integration class if found, None otherwise.

    Example:
        >>> from civicrm_py.contrib.registry import get_integration
        >>> DjangoIntegration = get_integration("django")
        >>> if DjangoIntegration:
        ...     integration = DjangoIntegration()
    """
    return IntegrationRegistry.get_instance().get(name)


def discover_integrations(*, force: bool = False) -> int:
    """Discover and register integrations from entry points.

    Convenience function that wraps IntegrationRegistry.auto_discover().

    This should be called early in application startup to ensure
    all installed integrations are available.

    Args:
        force: If True, re-run discovery even if already done.

    Returns:
        Number of integrations discovered.

    Example:
        >>> from civicrm_py.contrib.registry import discover_integrations
        >>> discover_integrations()
        3
    """
    return IntegrationRegistry.get_instance().auto_discover(force=force)


def list_integrations() -> list[str]:
    """List all registered integration names.

    Convenience function that wraps IntegrationRegistry.list_integrations().

    Returns:
        Sorted list of integration names.

    Example:
        >>> from civicrm_py.contrib.registry import list_integrations
        >>> print(list_integrations())
        ['django', 'flask', 'litestar']
    """
    return IntegrationRegistry.get_instance().list_integrations()


__all__ = [
    "IntegrationRegistry",
    "discover_integrations",
    "get_integration",
    "list_integrations",
    "register_integration",
]
