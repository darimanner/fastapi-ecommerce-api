# Reusability as Template

> Status: planned

The project is designed to become the **base** for the next APIs. This document describes what carries over 1-to-1, what gets adapted, and what gets thrown away.

## What is framework (carries over)

Folders and files that do NOT depend on the ecommerce domain and are boilerplate for any backend:

```
src/fastapi_ecommerce_api/core/            # EVERYTHING
src/fastapi_ecommerce_api/interfaces/      # EVERYTHING
src/fastapi_ecommerce_api/infrastructure/  # EVERYTHING
src/fastapi_ecommerce_api/config/settings.py  # structure carries over; field names are adapted
src/fastapi_ecommerce_api/main.py          # app factory + router registration: the skeleton stays
migrations/env.py          # as is
alembic.ini                # as is
pyproject.toml             # ruff/pytest/mypy configs; revisit deps
.pre-commit-config.yaml    # as is
compose.yaml               # as is
Dockerfile                 # as is
docs/architecture/*        # mostly as is; re-check domain examples
```

## What is domain (thrown away)

```
src/fastapi_ecommerce_api/modules/brands/
src/fastapi_ecommerce_api/modules/categories/
src/fastapi_ecommerce_api/modules/products/
src/fastapi_ecommerce_api/modules/orders/         # once it exists
tests/unit/modules/...
tests/integration/modules/...
migrations/versions/*       # tied to specific tables
```

`auth/`: keep it if the new project needs authentication.

## Steps to adapt for a new project

1. Clone the repo, rename in `pyproject.toml` (`name`, `description`, `authors`)
2. Delete `src/fastapi_ecommerce_api/modules/*` (except `auth/`)
3. Clear `migrations/versions/`
4. Update `compose.yaml`: project name, ports if needed
5. Create the first module from the [template](structure.md#module-template)
6. Set `Settings.app.name`, `Settings.service.namespace/name` for the new project
7. Bring it up locally: `docker compose up -d` + `uv run fastapi dev`
8. Run the tests, check `/health/live`

## Generation scripts

What will improve reusability over time:

- **`scripts/new_module.py`**: generates a module folder with boilerplate (router/service/repo/schemas/deps/exceptions/events/models)
- **Makefile target** `make new-module name=foo`: a wrapper around the script
- **Copier template**: the separate repo [fastapi-service-template](https://github.com/darimanner/fastapi-service-template) holds all of this as a template; generated projects pick up template changes via `uvx copier update`

Example `scripts/new_module.py`:

```bash
uv run python scripts/new_module.py orders
# creates src/fastapi_ecommerce_api/modules/orders/{router,service,repository,models,schemas,deps,exceptions,events,__init__}.py
# adds include_router to main.py
```

## Anti-patterns when adapting

- **Do not keep `brands/` "just in case"**: it is noise, and a recruiter will notice the mismatch
- **Do not copy migrations**: they are tied to specific tables
- **Do not bend `core/` to the needs of a single domain**: this destroys reusability; add an abstraction instead
- **Do not smear domain logic into `core/`**: that is the death of a template

## Sanity checks after adaptation

Checks that can be automated (for example, in CI as a guard):

```bash
# 1. core/, interfaces/, infrastructure/ do not import from modules/
! grep -r "from fastapi_ecommerce_api.modules" src/fastapi_ecommerce_api/core src/fastapi_ecommerce_api/interfaces src/fastapi_ecommerce_api/infrastructure

# 2. Modules do not import each other (except auth)
for module in src/fastapi_ecommerce_api/modules/*/; do
    name=$(basename "$module")
    if [ "$name" = "auth" ]; then continue; fi
    ! grep -r "from fastapi_ecommerce_api.modules\." "$module" | grep -v "from fastapi_ecommerce_api.modules.auth"
done

# 3. Services do not import HTTPException
! grep -r "HTTPException" src/fastapi_ecommerce_api/modules/*/service.py
```

These checks ensure the boundary between domains and the framework does not blur over time.

## Template evolution

Every time a pattern appears in a new project that is **reused across other projects**, it moves into `core/`. Every time code appears in `core/` that is **specific to a single use case**, the architecture is reconsidered.

This is a living process. Do not try to design a template "for every case" up front: it evolves through real use.
