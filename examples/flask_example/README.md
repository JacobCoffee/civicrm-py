# Flask CiviCRM Example

A Flask example application demonstrating civi-py integration with CiviCRM API v4.

## Features

- **CiviFlask Extension**: Seamless integration with Flask's application factory pattern
- **Dashboard**: Overview of CiviCRM statistics (contacts, activities, contributions, events)
- **Full CRUD Operations**: Create, read, update, delete for all entity types
- **Pagination & Search**: Built-in pagination and search functionality
- **Sample Data Generation**: Generate test data for demonstration
- **JSON API Endpoints**: RESTful API endpoints for programmatic access
- **CLI Commands**: Flask CLI commands for CiviCRM connectivity checks

## Prerequisites

1. **CiviCRM Instance**: A running CiviCRM instance with API v4 enabled
2. **API Key**: CiviCRM API key for authentication
3. **Python 3.11+**: Required Python version

## Quick Start

### Option 1: Using the Project Makefile (Recommended)

From the project root directory:

```bash
# Start CiviCRM infrastructure (if using local development setup)
make infra-up
make infra-install
make infra-setup

# Run the Flask example
make example-flask
```

### Option 2: Manual Setup

```bash
# Navigate to the example directory
cd examples/flask_example

# Create and activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your CiviCRM settings

# Run the development server
flask run --port 8002
```

## Configuration

Configure the application via environment variables or `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `CIVI_BASE_URL` | CiviCRM API v4 base URL | `http://localhost:8080/civicrm/ajax/api4` |
| `CIVI_API_KEY` | API key for authentication | Required |
| `CIVI_SITE_KEY` | Site key (if required) | Optional |
| `CIVI_AUTH_TYPE` | Authentication type (api_key, jwt, basic) | `api_key` |
| `CIVI_TIMEOUT` | Request timeout in seconds | `30` |
| `CIVI_VERIFY_SSL` | Enable SSL verification | `true` |
| `CIVI_DEBUG` | Enable debug logging | `false` |
| `FLASK_SECRET_KEY` | Flask secret key | Required for production |
| `FLASK_DEBUG` | Enable Flask debug mode | `true` |

## Available Endpoints

### Web UI

| URL | Description |
|-----|-------------|
| `/` | Dashboard with statistics |
| `/contacts` | Contact list with pagination and search |
| `/contacts/<id>` | Contact detail view |
| `/contacts/new` | Create new contact |
| `/activities` | Activity list |
| `/activities/<id>` | Activity detail view |
| `/contributions` | Contribution list |
| `/contributions/<id>` | Contribution detail view |
| `/events` | Event list |
| `/events/<id>` | Event detail view |
| `/generate-data` | Sample data generation |
| `/health` | Health check endpoint |

### JSON API

| URL | Description |
|-----|-------------|
| `/api/contacts` | Get contacts as JSON |
| `/api/activities` | Get activities as JSON |
| `/api/contributions` | Get contributions as JSON |
| `/api/events` | Get events as JSON |
| `/api/dashboard` | Get dashboard statistics as JSON |

Query parameters for API endpoints:
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 10, max: 100)
- `q`: Search query (for contacts, activities, events)

### CLI Commands

```bash
# Check CiviCRM API connectivity
flask civi-check

# Interactive CiviCRM shell
flask civi-shell
```

## Project Structure

```
flask_example/
├── app.py              # Main application (factory pattern)
├── pyproject.toml      # Project dependencies
├── .env.example        # Example environment configuration
└── README.md           # This file
```

The application uses shared templates from `examples/shared/templates/` for consistency with other framework examples.

## Application Factory Pattern

This example uses Flask's application factory pattern for better testability:

```python
from flask import Flask
from civi_py.contrib.flask import CiviFlask

def create_app(config=None):
    app = Flask(__name__)

    # Configure app
    app.config.update(
        CIVI_BASE_URL='https://example.org/civicrm/ajax/api4',
        CIVI_API_KEY='your-api-key',
    )

    # Initialize CiviFlask extension
    civi = CiviFlask()
    civi.init_app(app)

    # Register routes...

    return app
```

## Using CiviFlask in Views

The `CiviFlask` extension provides access to the CiviCRM client via Flask's `g` object:

```python
from flask import g
from civi_py.contrib.flask import get_civi_client

@app.route('/contacts')
def list_contacts():
    # Option 1: Via g object
    client = g.civi_client

    # Option 2: Via helper function (preferred)
    client = get_civi_client()

    # Make API calls
    response = client.get('Contact', limit=10)
    return {'contacts': response.values}
```

## Development

### Running Tests

```bash
# From project root
pytest tests/contrib/flask/
```

### Code Formatting

```bash
# From project root
make fix
```

## Related Examples

- [Django Example](../django_example/) - Django integration example
- [Litestar Example](../litestar_example/) - Litestar (async) integration example

## License

See the main project LICENSE file.
