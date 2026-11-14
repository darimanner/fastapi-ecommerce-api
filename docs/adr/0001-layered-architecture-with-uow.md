# ADR-0001: Layered architecture with Unit of Work

- **Date:** 2026-05-02
- **Status:** Accepted

## Context

The project needs an architecture that:

- Isolates business logic from HTTP and SQL
- Allows unit-testing services without a database
- Manages transactions explicitly, which matters especially for e-commerce, where placing an order touches several tables (order, order_items, inventory, payment)
- Can be extended with new domains without changing the core
- Can become a template for future projects

In the FastAPI/SQLAlchemy ecosystem, two anti-patterns are common:

1. **Fat router** - all logic lives in the endpoint function, with direct access to the session
2. **Thin service, fat repository** - the repository knows about business rules

Both hurt testability and readability as the project grows.

## Decision

Adopt the **Router -> Service -> Repository -> DB** pattern with an explicit **Unit of Work** as the transaction boundary.

- Services depend on `AbstractUnitOfWork` (a Protocol), not on `AsyncSession`
- The UoW aggregates repositories and manages commit/rollback
- Repositories inherit the generic `SQLAlchemyRepository[Model]` from `infrastructure/`
- Each domain is a self-contained module in `src/fastapi_ecommerce_api/modules/{name}/` with its own router/service/repository/models/schemas

## Consequences

**Positive:**

- Services are tested with `FakeUnitOfWork` without a database: fast and deterministic
- Transactions live in one place, with no scattered `session.begin()` calls across a service
- Multi-repository operations are transparent: `uow.orders.create(); uow.inventory.decrement(); await uow.commit()` is atomic
- The boundary between framework and domain is clean, so the project works as a template
- SQLAlchemy can be replaced with another ORM/storage without changing services (replace `SQLAlchemyRepository`, keep the interface)

**Negative:**

- An extra level of indirection on simple CRUD: overhead on read-only reference data such as `brands`
- A new developer has to understand the pattern before committing
- Slightly more boilerplate per module (router + service + repo + schemas + deps + exceptions + events)

**Neutral:**

- The service does not know about the specific DB engine, which can feel abstract; this is offset by explicit domain exceptions

## Alternatives Considered

1. **Bare `AsyncSession` in services** - rejected: as the project grows, transaction boundaries blur, and unit tests require SQLAlchemy mocks that quickly become inaccurate
2. **CQRS with separate command/query handlers** - rejected as overkill at the current scale; a later migration to CQRS does not require rewriting domain logic (the boundary already exists)
3. **Active Record (models know how to save/delete themselves)** - rejected: it mixes persistence and domain, is hard to test, and scales poorly to multi-table operations
4. **Hexagonal architecture with an explicit domain/application/infrastructure split** - rejected as excessive for a pet project; layered + UoW gives 80% of the benefits at 30% of the complexity
