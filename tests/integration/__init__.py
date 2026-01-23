"""Integration tests for civi-py.

These tests require a running CiviCRM instance (typically via Docker) and
perform actual API calls to verify client functionality.

Usage:
    # Run with Docker CiviCRM (default)
    make infra-up
    pytest tests/integration -v

    # Skip if Docker unavailable
    pytest tests/integration -v  # Auto-skips if CiviCRM not running

Configuration:
    Set environment variables or use defaults for Docker container:
    - CIVI_BASE_URL: http://localhost:8080/civicrm/ajax/api4
    - CIVI_API_KEY: Generated during container setup
    - CIVI_SITE_KEY: Generated during container setup (optional)
"""
