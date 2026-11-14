# SOLID & Design Patterns

> Status: planned

## SOLID in practice

### S - Single Responsibility
Each layer solves one task:
- Router - HTTP
- Schema - structure validation
- Service - business rules
- Repository - SQL
- UoW - transactions

When a class with two responsibilities appears (`BrandServiceAndCache`), split it.

### O - Open/Closed
- A new domain is added by creating a `modules/foo/` folder, with no changes to `core/` and `interfaces/`
- A new rate-limiting strategy is a new `RateLimitStrategy`, not an edit of an existing one
- A new payment provider is an implementation of the `PaymentGateway` Protocol

### L - Liskov Substitution
- Any implementation of `CRUDRepository[T]` can be replaced with another (`Fake`, mock) without changing the service
- `UnitOfWork` has a fake implementation for tests
- The behavior of subtypes is compatible with the contract of the base Protocol

### I - Interface Segregation
Repositories are split into narrow protocols:

```python
class ReadRepository[T](Protocol):
    async def get(self, id: int) -> T | None: ...
    async def list(self, **filters: object) -> list[T]: ...


class WriteRepository[T](Protocol):
    async def create(self, data: dict) -> T: ...
    async def update(self, id: int, data: dict) -> T: ...
    async def delete(self, id: int) -> None: ...


class CRUDRepository[T](ReadRepository[T], WriteRepository[T], Protocol): ...
```

A read-only domain (categories) uses only `ReadRepository`. The service does not receive what it does not need.

### D - Dependency Inversion
Services depend on **protocols**, not on concrete implementations:

```python
# bad - depends on SQLAlchemy
class BrandService:
    def __init__(self, session: AsyncSession): ...


# good - depends on an abstraction
class BrandService:
    def __init__(self, uow: UnitOfWork): ...
```

DI is done through FastAPI `Depends`. In tests it is replaced with `FakeUnitOfWork`.

## Design Patterns in the project

| Pattern | Where | Why |
|---------|-------|-----|
| Repository | `infrastructure/repository.py` | Hide DB details from the service |
| Unit of Work | `infrastructure/unit_of_work.py` | Transaction boundary |
| Dependency Injection | `core/deps`, `modules/*/deps.py` | Replaceable in tests |
| Strategy | `core/rate_limiter/strategies.py`, payment gateways | Pluggable algorithms |
| Specification | `core/repository/spec.py` (optional) | Composable filters |
| Factory | `get_service` functions in `*/deps.py` | Assembling dependencies |
| Observer / Event Bus | `core/events/bus.py` | Decoupling modules |
| Decorator | `@cached`, `@rate_limited` | Cross-cutting concerns |
| Middleware Chain | FastAPI middleware stack | Request processing pipeline |
| Adapter | `core/cache/redis.py` to `CacheBackend` | Vendor isolation |
| Protocol (structural typing) | `interfaces/*` | Duck typing checked by mypy |

## Other principles

- **DRY** - mixins for shared columns, a base CRUD repository
- **YAGNI** - do not introduce an abstraction until there is a second implementation (Specification, CQRS are added as needed)
- **Composition over inheritance** - the UoW composes repositories rather than inheriting them
- **Tell, don't ask** - the service tells the UoW to "commit", it does not ask for state
- **Separation of concerns** - each layer is isolated
- **Explicit is better than implicit** - explicit transactions, explicit exceptions, explicit DI
- **Boundaries first, abstractions later** - boundaries (router/service/repo) are drawn right away, shared abstractions are extracted after the second use case
