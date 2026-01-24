"""CiviCRM connection check management command.

Verifies CiviCRM connection and settings, tests API connectivity,
shows configured entities and available actions, and reports configuration issues.

Usage:
    python manage.py civi_check
    python manage.py civi_check --verbose
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser


class Command(BaseCommand):
    """Verify CiviCRM connection and configuration."""

    help = "Verify CiviCRM connection, settings, and API connectivity."

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command arguments.

        Args:
            parser: Argument parser instance.
        """
        parser.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="Increase verbosity. Use -vv for more detail.",
        )
        parser.add_argument(
            "--quiet",
            "-q",
            action="store_true",
            default=False,
            help="Only show errors and final status.",
        )
        parser.add_argument(
            "--test-entity",
            type=str,
            default="Contact",
            help="Entity to use for API test (default: Contact).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the check command.

        Args:
            *args: Positional arguments.
            **options: Command options.
        """
        verbosity = options["verbosity"]
        quiet = options["quiet"]
        test_entity = options["test_entity"]

        if not quiet:
            self.stdout.write("")
            self.stdout.write(self.style.HTTP_INFO("CiviCRM Configuration Check"))
            self.stdout.write("=" * 40)
            self.stdout.write("")

        issues: list[str] = []
        warnings: list[str] = []

        # Step 1: Check configuration
        settings = self._check_configuration(issues, warnings, verbosity, quiet)

        # Step 2: Check connection if settings are available
        if settings is not None:
            self._check_connection(
                settings,
                test_entity,
                issues,
                warnings,
                verbosity,
                quiet,
            )

        # Summary
        self._print_summary(issues, warnings, quiet)

    def _check_configuration(
        self,
        issues: list[str],
        warnings: list[str],
        verbosity: int,
        quiet: bool,
    ) -> Any:
        """Check CiviCRM configuration.

        Args:
            issues: List to append critical issues.
            warnings: List to append warnings.
            verbosity: Verbosity level.
            quiet: If True, suppress normal output.

        Returns:
            CiviSettings instance or None if configuration is invalid.
        """
        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING("1. Configuration"))

        settings = None

        # Try Django settings first
        try:
            from django.conf import settings as django_settings

            if hasattr(django_settings, "CIVI_SETTINGS"):
                civi_config = django_settings.CIVI_SETTINGS
                if not quiet:
                    self.stdout.write(
                        self.style.SUCCESS("   [OK] Django CIVI_SETTINGS found"),
                    )

                # Validate required fields
                required_fields = ["base_url"]
                missing = [f for f in required_fields if f not in civi_config]
                if missing:
                    issues.append(
                        f"Missing required settings: {', '.join(missing)}",
                    )
                    if not quiet:
                        self.stdout.write(
                            self.style.ERROR(
                                f"   [FAIL] Missing: {', '.join(missing)}",
                            ),
                        )
                else:
                    # Try to create settings object
                    try:
                        from civicrm_py.core.config import CiviSettings

                        settings = CiviSettings(**civi_config)
                        if not quiet and verbosity > 0:
                            self._display_settings(settings, verbosity)
                    except ValueError as e:
                        issues.append(f"Invalid settings: {e}")
                        if not quiet:
                            self.stdout.write(
                                self.style.ERROR(f"   [FAIL] {e}"),
                            )
            else:
                if not quiet:
                    self.stdout.write(
                        self.style.WARNING(
                            "   [WARN] Django CIVI_SETTINGS not found, trying environment",
                        ),
                    )
                warnings.append("No Django CIVI_SETTINGS configured")

        except Exception as e:
            if not quiet:
                self.stdout.write(
                    self.style.WARNING(f"   [WARN] Could not check Django settings: {e}"),
                )
            warnings.append(f"Django settings check failed: {e}")

        # Fall back to environment variables if Django settings not found
        if settings is None:
            try:
                from civicrm_py.core.config import CiviSettings

                settings = CiviSettings.from_env()
                if not quiet:
                    self.stdout.write(
                        self.style.SUCCESS("   [OK] Loaded from environment variables"),
                    )
                    if verbosity > 0:
                        self._display_settings(settings, verbosity)
            except ValueError as e:
                issues.append(f"Environment configuration error: {e}")
                if not quiet:
                    self.stdout.write(
                        self.style.ERROR(f"   [FAIL] {e}"),
                    )

        if not quiet:
            self.stdout.write("")

        return settings

    def _display_settings(self, settings: Any, verbosity: int) -> None:
        """Display settings information.

        Args:
            settings: CiviSettings instance.
            verbosity: Verbosity level.
        """
        # Mask sensitive values
        api_key_display = "****" if settings.api_key else "(not set)"
        site_key_display = "****" if settings.site_key else "(not set)"

        self.stdout.write(f"   Base URL: {settings.base_url}")
        self.stdout.write(f"   Auth Type: {settings.auth_type}")
        self.stdout.write(f"   API Key: {api_key_display}")
        self.stdout.write(f"   Site Key: {site_key_display}")

        if verbosity > 1:
            self.stdout.write(f"   Timeout: {settings.timeout}s")
            self.stdout.write(f"   Verify SSL: {settings.verify_ssl}")
            self.stdout.write(f"   Max Retries: {settings.max_retries}")
            self.stdout.write(f"   Debug: {settings.debug}")

    def _check_connection(
        self,
        settings: Any,
        test_entity: str,
        issues: list[str],
        warnings: list[str],
        verbosity: int,
        quiet: bool,
    ) -> None:
        """Check API connection.

        Args:
            settings: CiviSettings instance.
            test_entity: Entity to use for testing.
            issues: List to append critical issues.
            warnings: List to append warnings.
            verbosity: Verbosity level.
            quiet: If True, suppress normal output.
        """
        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING("2. API Connection"))

        try:
            from civicrm_py.core.client import SyncCiviClient

            # Use sync client for simplicity in management command
            with SyncCiviClient(settings) as client:
                # Test basic connectivity with a simple request
                if not quiet:
                    self.stdout.write(
                        f"   Testing connection to: {settings.base_url}",
                    )

                # Try to get entity metadata
                try:
                    response = client.get_fields(test_entity)
                    field_count = len(response.values or [])

                    if not quiet:
                        self.stdout.write(
                            self.style.SUCCESS(
                                "   [OK] Connected successfully",
                            ),
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"   [OK] {test_entity} entity accessible ({field_count} fields)",
                            ),
                        )

                    # Optionally list some fields
                    if verbosity > 1 and response.values:
                        self.stdout.write("")
                        self.stdout.write(f"   Sample fields from {test_entity}:")
                        for field in (response.values or [])[:5]:
                            field_name = field.get("name", "unknown")
                            field_type = field.get("data_type", "unknown")
                            self.stdout.write(f"     - {field_name}: {field_type}")
                        if field_count > 5:
                            self.stdout.write(f"     ... and {field_count - 5} more")

                except Exception as e:
                    issues.append(f"Failed to query {test_entity}: {e}")
                    if not quiet:
                        self.stdout.write(
                            self.style.ERROR(f"   [FAIL] {e}"),
                        )
                    return

                # Test listing available entities
                if verbosity > 0:
                    self._check_available_entities(client, warnings, verbosity, quiet)

        except ImportError as e:
            issues.append(f"Could not import civicrm_py: {e}")
            if not quiet:
                self.stdout.write(
                    self.style.ERROR(f"   [FAIL] Import error: {e}"),
                )

        except Exception as e:
            error_msg = str(e)

            # Check for specific error types
            if "connection" in error_msg.lower() or "connect" in error_msg.lower():
                issues.append(f"Connection failed: {error_msg}")
            elif "auth" in error_msg.lower() or "401" in error_msg:
                issues.append(f"Authentication failed: {error_msg}")
            elif "403" in error_msg:
                issues.append(f"Permission denied: {error_msg}")
            elif "404" in error_msg:
                issues.append(f"API endpoint not found: {error_msg}")
            else:
                issues.append(f"API error: {error_msg}")

            if not quiet:
                self.stdout.write(
                    self.style.ERROR(f"   [FAIL] {error_msg}"),
                )

        if not quiet:
            self.stdout.write("")

    def _check_available_entities(
        self,
        client: Any,
        warnings: list[str],
        verbosity: int,
        quiet: bool,
    ) -> None:
        """Check and list available entities.

        Args:
            client: SyncCiviClient instance.
            warnings: List to append warnings.
            verbosity: Verbosity level.
            quiet: If True, suppress normal output.
        """
        if not quiet:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("3. Available Entities"))

        try:
            response = client.request("Entity", "get", {})
            entities = response.values or []

            if not quiet:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   [OK] Found {len(entities)} entities",
                    ),
                )

            if verbosity > 1:
                # Group entities by type
                by_type: dict[str, list[str]] = {}
                for entity in entities:
                    etype = entity.get("type", "other")
                    name = entity.get("name", "unknown")
                    if etype not in by_type:
                        by_type[etype] = []
                    by_type[etype].append(name)

                for etype, names in sorted(by_type.items()):
                    self.stdout.write(f"   {etype.title()} ({len(names)}):")
                    if verbosity > 2:
                        for name in sorted(names)[:10]:
                            self.stdout.write(f"     - {name}")
                        if len(names) > 10:
                            self.stdout.write(f"     ... and {len(names) - 10} more")
                    else:
                        preview = ", ".join(sorted(names)[:5])
                        if len(names) > 5:
                            preview += f", ... ({len(names)} total)"
                        self.stdout.write(f"     {preview}")

        except Exception as e:
            warnings.append(f"Could not list entities: {e}")
            if not quiet:
                self.stdout.write(
                    self.style.WARNING(f"   [WARN] Could not list entities: {e}"),
                )

    def _print_summary(
        self,
        issues: list[str],
        warnings: list[str],
        quiet: bool,
    ) -> None:
        """Print check summary.

        Args:
            issues: List of critical issues.
            warnings: List of warnings.
            quiet: If True, only show if there are issues.
        """
        if quiet and not issues:
            self.stdout.write(self.style.SUCCESS("CiviCRM configuration OK"))
            return

        if not quiet:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Summary"))

        if issues:
            self.stdout.write(
                self.style.ERROR(f"   {len(issues)} issue(s) found:"),
            )
            for issue in issues:
                self.stdout.write(self.style.ERROR(f"     - {issue}"))
            self.stdout.write("")
            msg = f"CiviCRM configuration check failed with {len(issues)} issue(s)"
            raise CommandError(msg)

        if warnings:
            self.stdout.write(
                self.style.WARNING(f"   {len(warnings)} warning(s):"),
            )
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"     - {warning}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("   All checks passed!"))
