# CiviCRM Docker Setup for Compatibility Testing

This directory contains Docker Compose configurations for testing civi-py
against multiple CiviCRM versions.

## Overview

The Docker setup provides isolated CiviCRM instances for:
- Recording version-specific cassettes
- Validating API behavior across versions
- Testing version-specific features and workarounds

## Available Versions

| Service | CiviCRM Version | Port | PHP Range | Status |
|---------|-----------------|------|-----------|--------|
| civicrm-5.60 | 5.60 LTS | 8560 | 7.4-8.1 | Legacy LTS |
| civicrm-5.68 | 5.68 LTS | 8568 | 8.0-8.2 | Active LTS |
| civicrm-5.76 | 5.76 LTS | 8576 | 8.1-8.3 | Current LTS |
| civicrm-latest | Latest | 8580 | 8.1+ | Bleeding Edge |

## Quick Start

### Start a Specific Version

```bash
# Navigate to project root
cd /path/to/civi-py

# Start CiviCRM 5.76 (current LTS)
docker compose -f docker/civicrm/docker-compose.yml --profile 5.76 up -d

# Wait for health check (about 2 minutes for first start)
docker compose -f docker/civicrm/docker-compose.yml ps

# Verify it's running
curl http://localhost:8576/civicrm/ajax/api4/System/get
```

### Start All LTS Versions

```bash
docker compose -f docker/civicrm/docker-compose.yml --profile lts up -d
```

### Start All Versions

```bash
docker compose -f docker/civicrm/docker-compose.yml --profile all up -d
```

## Recording Cassettes

Once a CiviCRM instance is running, you can record cassettes:

```bash
# Set environment for the version you're testing
export CIVI_VERSION=5.76
export CIVI_BASE_URL=http://localhost:8576/civicrm/ajax/api4
export CIVI_API_KEY=admin-api-key-5.76
export CIVI_SITE_KEY=site-key-5.76
export CIVI_CASSETTE_MODE=record

# Run tests to record cassettes
pytest tests/compat/test_cassettes.py -v

# Cassettes are saved to tests/cassettes/v5.76/
```

## Environment Variables

Each CiviCRM version uses specific credentials:

| Version | API Key | Site Key | Port |
|---------|---------|----------|------|
| 5.60 | admin-api-key-5.60 | site-key-5.60 | 8560 |
| 5.68 | admin-api-key-5.68 | site-key-5.68 | 8568 |
| 5.76 | admin-api-key-5.76 | site-key-5.76 | 8576 |
| latest | admin-api-key-latest | site-key-latest | 8580 |

## Profiles

Docker Compose profiles control which services start:

- `5.60` - CiviCRM 5.60 LTS only
- `5.68` - CiviCRM 5.68 LTS only
- `5.76` - CiviCRM 5.76 LTS only
- `latest` - Latest CiviCRM only
- `lts` - All LTS versions (5.68, 5.76)
- `default` - Default version (5.76)
- `all` - All versions

## Volume Management

Each version has its own data volume. To reset:

```bash
# Stop services
docker compose -f docker/civicrm/docker-compose.yml down

# Remove volumes (WARNING: Deletes all data)
docker volume rm civi-py_civi-5.76-data

# Or remove all
docker compose -f docker/civicrm/docker-compose.yml down -v
```

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker compose -f docker/civicrm/docker-compose.yml logs civicrm-5.76
```

### API Returns 403

Ensure you're using the correct API key for the version.

### Health Check Failing

CiviCRM takes time to initialize. Wait for the health check:
```bash
watch docker compose -f docker/civicrm/docker-compose.yml ps
```

### Port Already in Use

Change ports in docker-compose.yml or stop conflicting services.

## CI Integration

For CI environments, you can use the official CiviCRM Docker images directly:

```yaml
# GitHub Actions example
services:
  civicrm:
    image: civicrm/civicrm:5.76-latest
    ports:
      - 8576:80
    env:
      CIVICRM_API_KEY: test-api-key

steps:
  - name: Wait for CiviCRM
    run: |
      timeout 180 bash -c 'until curl -s http://localhost:8576/civicrm/ajax/api4/System/get; do sleep 5; done'

  - name: Run Compatibility Tests
    run: |
      CIVI_BASE_URL=http://localhost:8576/civicrm/ajax/api4 \
      CIVI_API_KEY=test-api-key \
      pytest tests/compat/
```

## Alternative: Using buildkit-based Images

For advanced users, CiviCRM provides buildkit-based images:

```bash
# Clone CiviCRM buildkit
git clone https://github.com/civicrm/civicrm-buildkit.git
cd civicrm-buildkit

# Build specific version
civibuild create dmaster --civi-ver 5.76 --type drupal-demo

# Access at http://localhost:8001
```

## Version Matrix Reference

The version matrix in `tests/compat/version_matrix.py` defines:
- Supported CiviCRM versions
- PHP compatibility ranges
- Known API differences
- Breaking changes between versions

Use this matrix when deciding which cassettes to record:

```python
from tests.compat.version_matrix import get_version_matrix

matrix = get_version_matrix()

# Get all LTS versions
for version in matrix.get_lts_versions():
    print(f"{version.version}: {version.docker_image}")
```
