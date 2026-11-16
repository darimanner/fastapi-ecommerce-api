# Reusability as Template

> Status: partially implemented
>
> Exists today: the project is generated from the Copier template [fastapi-service-template](https://github.com/darimanner/fastapi-service-template) and pulls its updates with `uvx copier update`.

New services do not clone this repository. They start from the template, which holds the domain-free part: settings, logging, RFC 7807 errors, async SQLAlchemy and Alembic, Docker, CI, quality gates. This project is where generic pieces are proven on a real domain before they move into the template.

## What is framework

Code that does not depend on the e-commerce domain and is a candidate for the template once it settles:

```
src/ecommerce/core/            # cross-cutting framework code
src/ecommerce/interfaces/      # Protocols: repository, Unit of Work, cache
src/ecommerce/infrastructure/  # generic SQLAlchemy implementations
```

## What is domain

Everything under `src/ecommerce/modules/` (brands, categories, products, cart, orders, auth) plus their migrations and tests. It never goes into the template, except `auth` if several services end up needing the same scheme.

## Starting a new service

```bash
uvx copier copy gh:darimanner/fastapi-service-template my-service
cd my-service && git init && make install && make up && make migrate
```

Then add the first module following the [module template](structure.md#module-template).

## Why there is no module generator

A `make new-module` generator would only automate duplication: every module would still carry the same boilerplate files. Instead, generic bases (`SQLAlchemyRepository[Model]`, a CRUD service base) cover standard CRUD, and a module holds only its model, schemas, an explicit router and whatever domain logic it really has. A CRUD router factory was rejected too: it hides logic, produces faceless OpenAPI and breaks on non-trivial domains.

## Anti-patterns

- **Do not copy migrations** between services: they are tied to specific tables
- **Do not bend `core/` to the needs of a single domain**: add a seam in the module instead
- **Do not move code into the template before a second service needs it**: a template designed "for every case" up front grows faster than it proves itself

## Boundary checks

Checks that can be automated (for example, in CI as a guard):

```bash
# 1. core/, interfaces/, infrastructure/ do not import from modules/
! grep -r "from ecommerce.modules" src/ecommerce/core src/ecommerce/interfaces src/ecommerce/infrastructure

# 2. Modules do not import each other (except auth)
for module in src/ecommerce/modules/*/; do
    name=$(basename "$module")
    if [ "$name" = "auth" ]; then continue; fi
    ! grep -r "from ecommerce.modules\." "$module" | grep -v "from ecommerce.modules.auth"
done

# 3. Services do not import HTTPException
! grep -r "HTTPException" src/ecommerce/modules/*/service.py
```

## Template evolution

When a pattern here is needed by another service, it moves into the template and comes back through `uvx copier update`. When code in `core/` turns out to serve a single use case, it moves back into its module.
