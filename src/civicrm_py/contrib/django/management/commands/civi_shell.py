"""Interactive CiviCRM shell management command.

Provides an interactive Python shell with CiviCRM client pre-configured
and common entities already imported.

Usage:
    python manage.py civi_shell
    python manage.py civi_shell --notebook  # Use IPython if available
"""

from __future__ import annotations

import code
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand

if TYPE_CHECKING:
    from argparse import ArgumentParser


class Command(BaseCommand):
    """Interactive CiviCRM shell with pre-configured client and entities."""

    help = "Starts an interactive Python shell with CiviCRM client pre-configured."

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command arguments.

        Args:
            parser: Argument parser instance.
        """
        parser.add_argument(
            "--notebook",
            "-n",
            action="store_true",
            default=False,
            help="Use IPython if available for enhanced interactive experience.",
        )
        parser.add_argument(
            "--no-startup",
            action="store_true",
            default=False,
            help="Skip importing CiviCRM entities and client setup.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the shell command.

        Args:
            *args: Positional arguments.
            **options: Command options.
        """
        use_notebook = options["notebook"]
        no_startup = options["no_startup"]

        # Build the namespace with CiviCRM imports
        namespace = self._build_namespace(no_startup)

        # Display startup banner
        banner = self._build_banner(namespace, no_startup)

        if use_notebook:
            self._run_ipython_shell(namespace, banner)
        else:
            self._run_python_shell(namespace, banner)

    def _build_namespace(self, no_startup: bool) -> dict[str, Any]:
        """Build the shell namespace with CiviCRM imports.

        Args:
            no_startup: If True, skip CiviCRM imports.

        Returns:
            Dictionary with imported modules and objects.
        """
        namespace: dict[str, Any] = {}

        if no_startup:
            return namespace

        # Import CiviCRM core
        try:
            from civicrm_py.core.client import CiviClient, SyncCiviClient
            from civicrm_py.core.config import CiviSettings, get_settings

            namespace["CiviClient"] = CiviClient
            namespace["SyncCiviClient"] = SyncCiviClient
            namespace["CiviSettings"] = CiviSettings
            namespace["get_settings"] = get_settings
        except ImportError as e:
            self.stderr.write(
                self.style.WARNING(f"Could not import civicrm_py.core: {e}"),
            )

        # Import entities
        try:
            from civicrm_py.entities import (
                Activity,
                Address,
                BaseEntity,
                Contact,
                Contribution,
                Email,
                EntityDiscovery,
                Event,
                Group,
                GroupContact,
                Household,
                Individual,
                Membership,
                Note,
                Organization,
                Participant,
                Phone,
                Tag,
            )

            namespace["Activity"] = Activity
            namespace["Address"] = Address
            namespace["BaseEntity"] = BaseEntity
            namespace["Contact"] = Contact
            namespace["Contribution"] = Contribution
            namespace["Email"] = Email
            namespace["EntityDiscovery"] = EntityDiscovery
            namespace["Event"] = Event
            namespace["Group"] = Group
            namespace["GroupContact"] = GroupContact
            namespace["Household"] = Household
            namespace["Individual"] = Individual
            namespace["Membership"] = Membership
            namespace["Note"] = Note
            namespace["Organization"] = Organization
            namespace["Participant"] = Participant
            namespace["Phone"] = Phone
            namespace["Tag"] = Tag
        except ImportError as e:
            self.stderr.write(
                self.style.WARNING(f"Could not import civicrm_py.entities: {e}"),
            )

        # Import query components
        try:
            from civicrm_py.query import EntityManager, QuerySet

            namespace["EntityManager"] = EntityManager
            namespace["QuerySet"] = QuerySet
        except ImportError as e:
            self.stderr.write(
                self.style.WARNING(f"Could not import civicrm_py.query: {e}"),
            )

        # Import exceptions
        try:
            from civicrm_py.core.exceptions import (
                CiviAPIError,
                CiviAuthError,
                CiviConfigError,
                CiviConnectionError,
                CiviError,
                DoesNotExist,
                MultipleObjectsReturned,
            )

            namespace["CiviError"] = CiviError
            namespace["CiviAPIError"] = CiviAPIError
            namespace["CiviAuthError"] = CiviAuthError
            namespace["CiviConfigError"] = CiviConfigError
            namespace["CiviConnectionError"] = CiviConnectionError
            namespace["DoesNotExist"] = DoesNotExist
            namespace["MultipleObjectsReturned"] = MultipleObjectsReturned
        except ImportError as e:
            self.stderr.write(
                self.style.WARNING(f"Could not import civicrm_py.core.exceptions: {e}"),
            )

        # Try to create a client from Django settings or environment
        try:
            # First try Django settings
            from django.conf import settings as django_settings

            if hasattr(django_settings, "CIVI_SETTINGS"):
                civi_config = django_settings.CIVI_SETTINGS
                settings_obj = CiviSettings(**civi_config)
                namespace["settings"] = settings_obj
                namespace["client"] = SyncCiviClient(settings_obj)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Created client from Django settings (sync mode)",
                    ),
                )
            else:
                # Fall back to environment variables
                try:
                    settings_obj = get_settings()
                    namespace["settings"] = settings_obj
                    namespace["client"] = SyncCiviClient(settings_obj)
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Created client from environment variables (sync mode)",
                        ),
                    )
                except ValueError as e:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Could not create client from environment: {e}\n"
                            "Use CiviClient(base_url=..., api_key=...) to create manually.",
                        ),
                    )
        except Exception as e:
            self.stderr.write(
                self.style.WARNING(f"Could not auto-configure client: {e}"),
            )

        # Import asyncio for async operations
        import asyncio

        namespace["asyncio"] = asyncio

        return namespace

    def _build_banner(self, namespace: dict[str, Any], no_startup: bool) -> str:
        """Build the shell startup banner.

        Args:
            namespace: The shell namespace with imported objects.
            no_startup: If True, minimal banner.

        Returns:
            Banner string to display.
        """
        if no_startup:
            return "CiviCRM Shell (no auto-imports)"

        lines = [
            "",
            "CiviCRM Interactive Shell",
            "=" * 40,
            "",
        ]

        # List imported entities
        entities = [
            "Activity",
            "Address",
            "Contact",
            "Contribution",
            "Email",
            "Event",
            "Group",
            "Household",
            "Individual",
            "Membership",
            "Note",
            "Organization",
            "Participant",
            "Phone",
            "Tag",
        ]
        available_entities = [e for e in entities if e in namespace]
        if available_entities:
            lines.append("Entities: " + ", ".join(available_entities))

        # List available utilities
        utils = ["CiviClient", "SyncCiviClient", "EntityDiscovery", "QuerySet"]
        available_utils = [u for u in utils if u in namespace]
        if available_utils:
            lines.append("Utilities: " + ", ".join(available_utils))

        # Note about pre-configured client
        if "client" in namespace:
            lines.append("")
            lines.append("A sync client is available as 'client'.")
            lines.append("Use 'settings' to view current configuration.")
        else:
            lines.append("")
            lines.append("No client configured. Create one with:")
            lines.append("  client = SyncCiviClient(base_url=..., api_key=...)")

        lines.extend(
            [
                "",
                "Example usage:",
                "  result = client.get('Contact', limit=10)",
                "  for contact in result.values:",
                "      print(contact['display_name'])",
                "",
                "For async operations:",
                "  async with CiviClient() as async_client:",
                "      result = await async_client.get('Contact')",
                "",
            ],
        )

        return "\n".join(lines)

    def _run_ipython_shell(self, namespace: dict[str, Any], banner: str) -> None:
        """Start IPython shell if available.

        Args:
            namespace: Shell namespace.
            banner: Startup banner.
        """
        try:
            from IPython import start_ipython

            # Print banner before IPython starts
            self.stdout.write(banner)

            # Configure IPython
            config = [
                "--InteractiveShellApp.exec_lines=['import asyncio']",
            ]

            # Start IPython with the namespace
            start_ipython(argv=config, user_ns=namespace)
        except ImportError:
            self.stderr.write(
                self.style.WARNING(
                    "IPython is not installed. Falling back to standard Python shell.\n"
                    "Install IPython with: pip install ipython",
                ),
            )
            self._run_python_shell(namespace, banner)

    def _run_python_shell(self, namespace: dict[str, Any], banner: str) -> None:
        """Start standard Python interactive shell.

        Args:
            namespace: Shell namespace.
            banner: Startup banner.
        """
        # Try to use readline and rlcompleter for tab completion
        try:
            import readline
            import rlcompleter

            readline.set_completer(rlcompleter.Completer(namespace).complete)
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass  # readline not available on all platforms

        # Start the interactive console
        console = code.InteractiveConsole(locals=namespace)
        console.interact(banner=banner, exitmsg="Exiting CiviCRM shell...")
