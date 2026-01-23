# CiviCRM Standalone Test Infrastructure

This directory contains Docker infrastructure for running CiviCRM Standalone for integration testing.

## Quick Start

```bash
# Start infrastructure
make infra-up

# Wait for containers, then install CiviCRM (first time only)
make infra-install

# Configure API key for testing
make infra-setup

# Run integration tests
make test-integration

# Stop infrastructure
make infra-down
```

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| CiviCRM Standalone | http://localhost:8080/civicrm | admin / admin123 |
| phpMyAdmin | http://localhost:8081 | civicrm / civicrm |
| MariaDB | localhost:3307 | civicrm / civicrm |

## API Configuration

After running `make infra-setup`, use these settings:

```bash
CIVI_BASE_URL=http://localhost:8080/civicrm/ajax/api4
CIVI_API_KEY=test-api-key-civi-py
```

## Make Commands

```bash
make infra-up       # Start containers
make infra-install  # Install CiviCRM (first time)
make infra-setup    # Configure API key
make infra-down     # Stop containers
make infra-logs     # View logs
make infra-shell    # Shell into container
make infra-status   # Show status
make infra-clean    # Remove all data
make infra-tools    # Start with phpMyAdmin
```

## First Time Setup

1. `make infra-up` - Start the containers
2. Wait for database to be healthy (~10-15 seconds)
3. `make infra-install` - Install CiviCRM Standalone
4. `make infra-setup` - Configure API key for testing
5. Open http://localhost:8080/civicrm

## Troubleshooting

### Container won't start
```bash
make infra-logs
```

### Reset everything
```bash
make infra-clean
make infra-up
make infra-install
make infra-setup
```

## CiviCRM Standalone

This uses [CiviCRM Standalone](https://docs.civicrm.org/installation/en/latest/standalone/) -
a lightweight CiviCRM deployment without requiring Drupal, WordPress, or Joomla.
