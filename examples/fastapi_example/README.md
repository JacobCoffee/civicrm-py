# FastAPI CiviCRM Example

This example demonstrates how to integrate civi-py with FastAPI to create a complete CiviCRM API application.

## Features

- **FastAPI Lifespan Management**: Uses `civi_lifespan` for proper CiviClient lifecycle management
- **Dependency Injection**: Uses FastAPI's `Depends()` system for CiviClient injection
- **Auto-Generated CRUD Routes**: Uses `create_civi_router()` for automatic endpoint generation
- **Custom Routes**: Demonstrates custom endpoints using CiviShowcase service
- **Health Check**: CiviCRM connectivity monitoring at `/health/civi`
- **OpenAPI Documentation**: Automatic Swagger UI and ReDoc documentation
- **Pydantic Validation**: Request/response validation with Pydantic models

## Prerequisites

1. Python 3.11+
2. CiviCRM infrastructure running (see main project README)

## Quick Start

### From Project Root

```bash
# Start CiviCRM infrastructure (if not already running)
make infra-up
make infra-install
make infra-setup

# Run the FastAPI example
make example-fastapi
```

### Standalone Setup

```bash
cd examples/fastapi_example

# Install dependencies with uv
uv sync

# Set environment variables (or use .env file in project root)
export CIVI_BASE_URL="http://localhost:8080/civicrm/ajax/api4"
export CIVI_API_KEY="your-api-key"
export CIVI_SITE_KEY="your-site-key"  # Optional

# Run the application
uv run python app.py
# Or with uvicorn directly:
uv run uvicorn app:app --reload --port 8002
```

## Available Endpoints

Once running, visit:

- **API Index**: http://localhost:8002/
- **Swagger UI**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc
- **OpenAPI JSON**: http://localhost:8002/openapi.json
- **Health Check**: http://localhost:8002/health/civi

### Custom API Routes (using CiviShowcase)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Dashboard statistics |
| POST | `/api/sample-data` | Generate sample data |
| GET | `/api/contacts` | List contacts |
| GET | `/api/contacts/{id}` | Get contact by ID |
| POST | `/api/contacts` | Create contact |
| PUT | `/api/contacts/{id}` | Update contact |
| DELETE | `/api/contacts/{id}` | Delete contact |
| GET | `/api/activities` | List activities |
| GET | `/api/activities/{id}` | Get activity by ID |
| POST | `/api/activities` | Create activity |
| DELETE | `/api/activities/{id}` | Delete activity |
| GET | `/api/contributions` | List contributions |
| GET | `/api/contributions/{id}` | Get contribution by ID |
| POST | `/api/contributions` | Create contribution |
| GET | `/api/events` | List events |
| GET | `/api/events/{id}` | Get event by ID |
| POST | `/api/events` | Create event |

### Auto-Generated Routes (via create_civi_router)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/civi/contacts` | List contacts |
| GET | `/api/civi/contacts/{id}` | Get contact |
| POST | `/api/civi/contacts` | Create contact |
| PUT | `/api/civi/contacts/{id}` | Update contact |
| DELETE | `/api/civi/contacts/{id}` | Delete contact |
| GET | `/api/civi/activitys` | List activities |
| GET | `/api/civi/activitys/{id}` | Get activity |
| ... | ... | (same pattern for all entities) |

## Code Structure

```
examples/fastapi_example/
    app.py           # Main FastAPI application
    pyproject.toml   # Project dependencies
    README.md        # This file
```

## Key Integration Points

### 1. Lifespan Context Manager

```python
from civi_py.contrib.fastapi import create_civi_lifespan, CiviFastAPIConfig

config = CiviFastAPIConfig(
    api_prefix="/api/civi",
    enable_health_check=True,
    include_entities=["Contact", "Activity"],
)

app = FastAPI(lifespan=create_civi_lifespan(config))
```

### 2. Dependency Injection

```python
from civi_py.contrib.fastapi import get_civi_client, CiviClientDep

@app.get("/contacts")
async def list_contacts(client: CiviClientDep):
    response = await client.get("Contact", limit=10)
    return {"contacts": response.values}
```

### 3. Auto-Generated Router

```python
from civi_py.contrib.fastapi import create_civi_router

router = create_civi_router(config)
app.include_router(router, prefix="/api/civi")
```

### 4. Health Check

```python
from civi_py.contrib.fastapi import civi_health_check

@app.get("/health/civi")
async def health_check(client: CiviClientDep):
    return await civi_health_check(client)
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CIVI_BASE_URL` | Yes | - | CiviCRM API v4 base URL |
| `CIVI_API_KEY` | Yes | - | API key for authentication |
| `CIVI_SITE_KEY` | No | - | Site key (if required) |
| `CIVI_TIMEOUT` | No | 30 | Request timeout in seconds |
| `CIVI_VERIFY_SSL` | No | true | Verify SSL certificates |
| `CIVI_DEBUG` | No | false | Enable debug logging |

## Example Requests

### List Contacts

```bash
curl http://localhost:8002/api/contacts?page=1&per_page=10
```

### Create Contact

```bash
curl -X POST http://localhost:8002/api/contacts \
  -H "Content-Type: application/json" \
  -d '{
    "contact_type": "Individual",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@example.com"
  }'
```

### Get Dashboard

```bash
curl http://localhost:8002/api/dashboard
```

### Generate Sample Data

```bash
curl -X POST http://localhost:8002/api/sample-data \
  -H "Content-Type: application/json" \
  -d '{
    "contacts": 10,
    "activities": 20,
    "contributions": 15,
    "events": 5
  }'
```

### Health Check

```bash
curl http://localhost:8002/health/civi
```

## Comparison with Other Examples

| Feature | FastAPI | Litestar | Django |
|---------|---------|----------|--------|
| Async Support | Native | Native | Via ASGI |
| DI System | Depends() | Provide() | Middleware |
| Validation | Pydantic | msgspec/Pydantic | Forms |
| OpenAPI | Auto-generated | Auto-generated | Manual/drf-spectacular |
| Templates | Optional (Jinja2) | Optional (Jinja2) | Built-in |

## Troubleshooting

### Connection Errors

If you see "Cannot connect to CiviCRM", ensure:
1. CiviCRM infrastructure is running (`make infra-up`)
2. Environment variables are set correctly
3. API key has proper permissions

### Import Errors

If imports fail, ensure you're running from the project root or have installed civi-py:
```bash
# From project root
uv sync
cd examples/fastapi_example
uv sync
```

### Permission Errors

CiviCRM API permissions are controlled server-side. Ensure your API key has access to the entities you're querying.
