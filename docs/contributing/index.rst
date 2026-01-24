.. _contributing:

============
Contributing
============

Thank you for your interest in contributing to civicrm-py! This section covers
development setup, testing practices, and guidelines for submitting changes.

.. toctree::
   :maxdepth: 2
   :caption: Contributing Guides

   compatibility-testing


Quick Start for Contributors
============================

1. Fork and clone the repository
2. Install development dependencies: ``make install``
3. Run tests: ``make test``
4. Run linting and type checks: ``make check``

Development Workflow
--------------------

.. code-block:: bash

    # Clone your fork
    git clone https://github.com/YOUR_USERNAME/civicrm-py.git
    cd civicrm-py

    # Create a virtual environment
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # or .venv\Scripts\activate on Windows

    # Install in development mode with all extras
    make install

    # Create a feature branch
    git checkout -b feature/my-feature

    # Make changes, then run checks
    make check

    # Commit and push
    git add .
    git commit -m "feat: add my feature"
    git push origin feature/my-feature


Testing Overview
================

civicrm-py uses pytest for testing with several test categories:

**Unit Tests** (``tests/unit/``)
    Fast tests that do not require network access. Test individual components
    in isolation with mocked dependencies.

**Integration Tests** (``tests/integration/``)
    Tests that verify components work together correctly. May use fixtures
    to simulate external dependencies.

**Compatibility Tests** (``tests/compat/``)
    Tests that verify civicrm-py works correctly with CiviCRM API. Includes
    schema validation, coverage tracking, and drift detection. See
    :doc:`compatibility-testing` for details.

**Contrib Tests** (``tests/contrib/``)
    Tests for framework integrations (Django, Litestar, Flask, FastAPI).

Running Tests
-------------

.. code-block:: bash

    # Run all tests
    make test

    # Run specific test categories
    pytest tests/unit/ -v
    pytest tests/compat/ -v

    # Run with coverage
    pytest --cov=civicrm_py --cov-report=html

    # Run a specific test file
    pytest tests/compat/test_schema_validation.py -v

    # Run tests matching a pattern
    pytest -k "test_contact" -v


Code Style
==========

civicrm-py uses:

- **ruff** for linting and formatting
- **ty** for type checking
- **Google style docstrings**

Run all checks with:

.. code-block:: bash

    make check

Or individually:

.. code-block:: bash

    # Format code
    make fix

    # Lint
    ruff check src tests

    # Type check
    ty check


Commit Messages
===============

Follow the Conventional Commits specification:

.. code-block:: text

    <type>(<scope>): <description>

    [optional body]

    [optional footer]

Types:

- ``feat``: New feature
- ``fix``: Bug fix
- ``docs``: Documentation only
- ``test``: Adding or updating tests
- ``refactor``: Code change that neither fixes a bug nor adds a feature
- ``perf``: Performance improvement
- ``chore``: Build process or auxiliary tool changes

Examples:

.. code-block:: text

    feat(entities): add Relationship entity model

    fix(query): handle empty where clauses correctly

    docs(readme): add quickstart example

    test(compat): add Contact schema validation tests


Pull Request Checklist
======================

Before submitting a PR, ensure:

- [ ] Tests pass: ``make test``
- [ ] Linting passes: ``make lint``
- [ ] Type checking passes: ``make typecheck``
- [ ] Documentation updated for user facing changes
- [ ] Changelog entry added if applicable
- [ ] Commit messages follow conventional format


Where to Start
==============

Look for issues labeled ``good first issue`` on GitHub. These are specifically
chosen to be approachable for new contributors.

Common contribution areas:

- Adding support for new CiviCRM entities
- Improving documentation
- Adding tests for existing functionality
- Framework integration improvements
- Performance optimizations

Questions?
==========

Open an issue on GitHub or check existing discussions. We welcome questions
and are happy to help new contributors get started.
