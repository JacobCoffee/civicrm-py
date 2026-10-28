# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-10-28

### Bug Fixes

- Pin lint/type-check tools and cap drifted integration deps (#2) by @JacobCoffee in #2
- Scope fastapi/litestar version caps to dev tooling, fix dead docs link (#3) by @JacobCoffee in #3
- **auth:** Send site key as X-Civi-Key by @JacobCoffee
- **http:** Raise CiviAPIError for non-JSON responses by @JacobCoffee
- **http:** Don't retry writes after a read timeout by @JacobCoffee

### Features

- **auth:** Add auth_flow to send credentials via X-Civi-Auth by @JacobCoffee
- Add request_v3 for legacy APIv3 calls by @JacobCoffee

### Miscellaneous

- Add .dockerignore by @JacobCoffee
- Bump version to 0.2.0 by @JacobCoffee
## [0.1.4] - 2026-10-11

### Features

- Support Python 3.14 and 3.15 (#1) by @JacobCoffee in #1

### Miscellaneous

- Bump version to 0.1.4 for PyPI release by @JacobCoffee
## [0.1.3] - 2026-10-11

### Bug Fixes

- Update project URLs to renamed civicrm-py repo by @JacobCoffee
## [0.1.2] - 2026-01-24

### Features

- Add sigstore signing and attestation to publish workflow by @JacobCoffee

### Miscellaneous

- Bump version to 0.1.1 for PyPI release by @JacobCoffee
civi-py Changelog
