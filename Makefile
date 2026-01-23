SHELL := /bin/bash
# =============================================================================
# civi-py Makefile
# =============================================================================

.DEFAULT_GOAL := help
.ONESHELL:
UV_OPTS ?=
UV      ?= uv $(UV_OPTS)

# Performance: Don't write .pyc files (faster for dev/CI)
export PYTHONDONTWRITEBYTECODE := 1

.EXPORT_ALL_VARIABLES:

.PHONY: help install install-all sync
.PHONY: lint lint-fix format format-check typecheck check fix
.PHONY: test test-cov test-fast test-integration test-watch
.PHONY: docs docs-serve docs-clean
.PHONY: build build-check publish-test publish changelog changelog-preview
.PHONY: clean prek prek-install dev-setup
.PHONY: infra infra-up infra-down infra-logs infra-install infra-setup infra-shell infra-status infra-clean infra-tools
.PHONY: example-django example-django-wsgi example-django-shell example-django-check example-django-sync example-django-migrate
.PHONY: example-litestar example-fastapi example-setup
.PHONY: outdated tree version

help: ## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# =============================================================================
# Setup & Installation
# =============================================================================

##@ Setup & Installation

install: ## Install dependencies (default groups)
	@echo "=> Installing dependencies"
	@$(UV) sync
	@echo "=> Installation complete"

install-all: ## Install all dependencies including all extras
	@echo "=> Installing all dependencies and extras"
	@$(UV) sync --all-groups --all-extras
	@echo "=> Full installation complete"

sync: ## Sync dependencies and lock file
	@echo "=> Syncing dependencies"
	@$(UV) lock && $(UV) sync
	@echo "=> Sync complete"

dev-setup: install prek-install ## Setup development environment
	@echo "=> Development environment ready!"

# =============================================================================
# Code Quality
# =============================================================================

##@ Code Quality

lint: ## Run linter (ruff check)
	@$(UV) run ruff check src tests

lint-fix: ## Run linter with auto-fix
	@$(UV) run ruff check src tests --fix

format: ## Check code formatting
	@$(UV) run ruff format --check src tests

typecheck: ## Run type checker (ty)
	@$(UV) run ty check src

check: lint format-check typecheck ## Run all checks (lint, format, typecheck)

fix: lint-fix format ## Fix all auto-fixable issues

prek: ## Run prek hooks
	@prek run --all-files

prek-install: ## Install prek hooks
	@prek install

# =============================================================================
# Testing
# =============================================================================

##@ Testing

test: ## Run tests
	@$(UV) run pytest tests -v

test-cov: ## Run tests with coverage
	@$(UV) run pytest tests \
		--cov=src/civi_py \
		--cov-report=html \
		--cov-report=term-missing

test-fast: ## Run tests without slow/integration markers
	@$(UV) run pytest tests -v -m "not slow and not integration"

test-integration: ## Run integration tests only
	@$(UV) run pytest tests -v -m integration

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@$(UV) run --with pytest-watch ptw tests -- -v

# =============================================================================
# Documentation
# =============================================================================

##@ Documentation

docs: ## Build documentation
	@echo "=> Building documentation"
	@$(UV) run --group docs sphinx-build -b html docs docs/_build/html -W

docs-serve: ## Serve documentation with auto-reload
	@$(UV) run --group docs sphinx-autobuild docs docs/_build/html --port 0 --open-browser

docs-clean: ## Clean documentation build
	@echo "=> Cleaning documentation build"
	@rm -rf docs/_build

# =============================================================================
# Build & Release
# =============================================================================

##@ Build & Release

build: clean ## Build package
	@echo "=> Building package"
	@$(UV) build

build-check: build ## Build and check package
	@$(UV) run --with twine twine check dist/*

publish-test: build ## Publish to TestPyPI
	@$(UV) run --with twine twine upload --repository testpypi dist/*

publish: build ## Publish to PyPI
	@$(UV) run --with twine twine upload dist/*

changelog: ## Generate changelog with git-cliff
	@git cliff --output CHANGELOG.md

changelog-preview: ## Preview changelog (unreleased)
	@git cliff --unreleased

clean: ## Clean build artifacts
	@echo "=> Cleaning build artifacts"
	@rm -rf dist/ build/ *.egg-info/ src/*.egg-info/
	@rm -rf .pytest_cache/ .ruff_cache/ .coverage htmlcov/ .ty_cache/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	$(MAKE) docs-clean
	@echo "=> Clean complete"

version: ## Show current version
	@grep '^version' pyproject.toml | head -1 | cut -d'"' -f2

# =============================================================================
# Infrastructure (CiviCRM Docker)
# =============================================================================

##@ Infrastructure (CiviCRM Docker)

infra: infra-up ## Alias for infra-up

infra-up: ## Start CiviCRM infrastructure
	@echo "=> Starting CiviCRM Standalone infrastructure..."
	@docker compose up -d
	@echo "=> Infrastructure starting. Run 'make infra-logs' to monitor."
	@echo "=> First time? Run 'make infra-install' after containers are healthy."

infra-down: ## Stop CiviCRM infrastructure
	@echo "=> Stopping CiviCRM infrastructure..."
	@docker compose down

infra-logs: ## View CiviCRM container logs
	@docker compose logs -f

infra-install: ## Install CiviCRM (first time setup)
	@echo "=> Installing CiviCRM Standalone..."
	@docker compose exec -u www-data civicrm cv core:install \
		--db=mysql://civicrm:civicrm@db:3306/civicrm \
		-l http://localhost:8080 \
		-m extras.adminUser=admin \
		-m extras.adminPass=admin123 \
		--force
	@echo "=> CiviCRM installed! Login: admin / admin123"
	@echo "=> Run 'make infra-setup' to configure API key for testing."

infra-setup: ## Setup API key and permissions for testing (run after infra-install)
	@echo "=> Setting up CiviCRM for API testing..."
	@echo ""
	@echo "Step 1: Enabling authx extension..."
	@docker compose exec -u www-data civicrm cv ext:enable authx 2>/dev/null || \
		(echo "=> CiviCRM not ready. Run 'make infra-install' first." && exit 1)
	@echo ""
	@echo "Step 2: Removing any existing API key from Contact 1 (Default Org)..."
	@docker compose exec -u www-data civicrm cv ev 'civicrm_api4("Contact","update",["values"=>["api_key"=>""],"where"=>[["id","=",1]],"checkPermissions"=>false]);' 2>/dev/null || true
	@echo ""
	@echo "Step 3: Setting API key on admin user (Contact 2)..."
	@docker compose exec -u www-data civicrm cv api4 Contact.update \
		+w 'id=2' +v 'api_key=test-api-key-civi-py' 2>/dev/null
	@echo ""
	@echo "Step 4: Configuring authx for API key authentication..."
	@docker compose exec -u www-data civicrm cv ev 'Civi::settings()->set("authx_guards", []);' 2>/dev/null
	@docker compose exec -u www-data civicrm cv ev 'Civi::settings()->set("authx_header_cred", ["jwt","api_key"]);' 2>/dev/null
	@docker compose exec -u www-data civicrm cv ev 'Civi::settings()->set("authx_xheader_cred", ["jwt","api_key"]);' 2>/dev/null
	@echo ""
	@echo "Step 5: Adding 'authenticate with api key' permission to everyone role..."
	@docker compose exec -u www-data civicrm cv api4 Role.update \
		+w 'name="everyone"' \
		+v 'permissions=["access CiviMail subscribe/unsubscribe pages","make online contributions","view event info","register for events","access password resets","authenticate with password","authenticate with api key"]' 2>/dev/null
	@echo ""
	@echo "Step 6: Adding admin contact to Administrators group for ACL..."
	@docker compose exec -u www-data civicrm cv api4 GroupContact.create \
		+v 'group_id=1' +v 'contact_id=2' +v 'status="Added"' 2>/dev/null || true
	@echo ""
	@echo "Step 7: Adding staff role to admin user for full permissions..."
	@docker compose exec -u www-data civicrm cv api4 User.update \
		+w 'id=1' +v 'roles=["2","3"]' 2>/dev/null
	@echo ""
	@echo "Step 8: Flushing caches..."
	@docker compose exec -u www-data civicrm cv flush 2>/dev/null
	@echo ""
	@echo "=> CiviCRM API configured!"
	@echo ""
	@echo "Test configuration (add to .env):"
	@echo "  CIVI_BASE_URL=http://localhost:8080/civicrm/ajax/api4"
	@echo "  CIVI_API_KEY=test-api-key-civi-py"
	@echo ""
	@echo "Test with curl:"
	@echo '  curl -s -X POST "http://localhost:8080/civicrm/ajax/api4/Contact/get" \'
	@echo '    -H "Authorization: Bearer test-api-key-civi-py" \'
	@echo '    -H "X-Requested-With: XMLHttpRequest" \'
	@echo '    -H "Content-Type: application/json" \'
	@echo '    -d '"'"'{"limit":1}'"'"''

infra-shell: ## Open shell in CiviCRM container
	@docker compose exec civicrm bash

infra-status: ## Show infrastructure status
	@echo "CiviCRM Standalone Infrastructure Status"
	@echo "========================================"
	@docker compose ps
	@echo ""
	@echo "URLs:"
	@echo "  CiviCRM:    http://localhost:8080/civicrm (admin/admin123)"
	@echo "  phpMyAdmin: http://localhost:8081 (with --profile tools)"
	@echo "  MariaDB:    localhost:3307"
	@echo ""
	@echo "API Endpoint:"
	@echo "  http://localhost:8080/civicrm/ajax/api4"

infra-clean: ## Remove all infrastructure data
	@echo "WARNING: This will delete all CiviCRM data!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker compose down -v
	@echo "=> Infrastructure data cleaned."

infra-tools: ## Start infrastructure with phpMyAdmin
	@docker compose --profile tools up -d

# =============================================================================
# Examples
# =============================================================================

##@ Examples

example-setup: install-all ## Install all extras for running examples
	@echo "=> Examples ready! Use 'make example-django', 'make example-litestar', or 'make example-fastapi'"

example-django: example-django-migrate ## Run Django example (ASGI on port 8000)
	@echo "=> Starting Django example on http://localhost:8000"
	@test -f .env && echo "=> Loading .env" || echo "=> No .env found. Copy .env.example to .env"
	@echo ""
	@echo "Endpoints:"
	@echo "  http://localhost:8000/           - Home"
	@echo "  http://localhost:8000/contacts/  - Contact list"
	@echo "  http://localhost:8000/civiadmin/ - CiviCRM Admin (admin/admin123)"
	@echo ""
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example DJANGO_SETTINGS_MODULE=civicrm_demo.settings \
		$(UV) run --extra django --with 'uvicorn[standard]' --with whitenoise uvicorn civicrm_demo.asgi:application \
		--reload --port 8000

example-django-wsgi: ## Run Django example (WSGI on port 8000)
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py runserver 8000

example-django-shell: ## Open Django CiviCRM interactive shell
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py civi_shell

example-django-check: ## Check Django CiviCRM connection
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py civi_check

example-django-sync: ## List available CiviCRM entities
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py sync_civi --list-entities

example-django-migrate: ## Run Django migrations and create admin user
	@echo "=> Running Django migrations..."
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py migrate
	@echo "=> Creating Django admin user (admin/admin123)..."
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:examples/django_example $(UV) run --extra django python examples/django_example/manage.py shell -c "\
from django.contrib.auth.models import User; \
u, created = User.objects.get_or_create(username='admin', defaults={'email':'admin@example.com','is_superuser':True,'is_staff':True}); \
u.set_password('admin123') if created else None; \
u.is_superuser=True; u.is_staff=True; u.save(); \
print('Created admin user' if created else 'Admin user exists')"
	@echo "=> Django setup complete! Login: admin / admin123"

example-litestar: ## Run Litestar example (port 8001)
	@echo "=> Starting Litestar example on http://localhost:8001"
	@test -f .env && echo "=> Loading .env" || echo "=> No .env found. Copy .env.example to .env"
	@echo ""
	@echo "Endpoints:"
	@echo "  http://localhost:8001/             - API index"
	@echo "  http://localhost:8001/docs/scalar  - Scalar docs"
	@echo "  http://localhost:8001/docs/swagger - Swagger UI"
	@echo "  http://localhost:8001/health/civi  - Health check"
	@echo "  http://localhost:8001/api/dashboard - Dashboard stats"
	@echo "  http://localhost:8001/api/contacts - Contacts CRUD"
	@echo ""
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:. $(UV) run --extra litestar --with 'uvicorn[standard]' python examples/litestar_example/app.py

example-fastapi: ## Run FastAPI example (port 8002)
	@echo "=> Starting FastAPI example on http://localhost:8002"
	@test -f .env && echo "=> Loading .env" || echo "=> No .env found. Copy .env.example to .env"
	@echo ""
	@echo "Endpoints:"
	@echo "  http://localhost:8002/             - API index"
	@echo "  http://localhost:8002/docs         - Swagger UI"
	@echo "  http://localhost:8002/redoc        - ReDoc"
	@echo "  http://localhost:8002/health/civi  - Health check"
	@echo "  http://localhost:8002/api/dashboard - Dashboard stats"
	@echo "  http://localhost:8002/api/contacts - Contacts CRUD"
	@echo ""
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src:. $(UV) run --extra fastapi --with 'uvicorn[standard]' python examples/fastapi_example/app.py

# =============================================================================
# Cassette Recording
# =============================================================================

##@ Cassette Recording

.PHONY: record-cassettes record-cassettes-entity record-cassettes-errors record-cassettes-edge

record-cassettes: ## Record all API cassettes (requires running infra)
	@echo "=> Recording all API cassettes..."
	@echo "=> Ensure CiviCRM is running (make infra && make infra-setup)"
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src $(UV) run python scripts/record_cassettes.py

record-cassettes-entity: ## Record cassettes for specific entity (ENTITY=Contact)
	@echo "=> Recording cassettes for entity: $(ENTITY)"
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src $(UV) run python scripts/record_cassettes.py --entity $(ENTITY)

record-cassettes-errors: ## Record error scenario cassettes only
	@echo "=> Recording error scenario cassettes..."
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src $(UV) run python scripts/record_cassettes.py --errors-only

record-cassettes-edge: ## Record edge case cassettes only
	@echo "=> Recording edge case cassettes..."
	@set -a && test -f .env && . ./.env; set +a && \
		PYTHONPATH=src $(UV) run python scripts/record_cassettes.py --edge-cases

# =============================================================================
# Utilities
# =============================================================================

##@ Utilities

outdated: ## Show outdated dependencies
	@$(UV) pip list --outdated

tree: ## Show project structure
	@tree -I '__pycache__|*.egg-info|.git|.ruff_cache|.pytest_cache|htmlcov|dist|build|.ty_cache|_build' -a
