# civi-py Examples

This directory contains example applications demonstrating civi-py integration with different frameworks.

## Available Examples

| Example | Framework | Description |
|---------|-----------|-------------|
| `django_example/` | Django 5+ | Full Django integration with admin, views, and templates |
| `litestar_example/` | Litestar 2+ | Litestar API with DI, routes, and OpenAPI |

## Prerequisites

1. Start the CiviCRM test infrastructure:
   ```bash
   make infra-up
   make infra-setup
   ```

2. Install example dependencies:
   ```bash
   make example-setup
   ```

## Running Examples

### Django Example
```bash
make example-django
# Open http://localhost:8000
```

Features demonstrated:
- Django settings integration
- CiviCRM admin integration
- Request-scoped client middleware
- Template tags for displaying CiviCRM data
- Management commands

### Litestar Example
```bash
make example-litestar
# Open http://localhost:8001/schema for OpenAPI docs
```

Features demonstrated:
- Litestar plugin configuration
- Dependency injection for CiviClient
- Auto-generated CRUD routes
- OpenAPI schema with CiviCRM entities
- Health check endpoint

## Configuration

Each example uses environment variables for CiviCRM connection:

```bash
# Copy and edit for your setup
cp .env.test examples/django_example/.env
cp .env.test examples/litestar_example/.env
```

## Adding New Examples

To add a new framework example:

1. Create directory: `examples/<framework>_example/`
2. Add `pyproject.toml` with civi-py dependency
3. Implement the integration per the framework's patterns
4. Add make target to root Makefile
5. Document in this README
