# Layers & Flow

> Status: partially implemented
>
> Implemented: the generic repository and the Unit of Work. Planned: the domain modules (routers, services and module repositories) shown in the examples.

## Request flow

```
HTTP Request
    │
    ▼
Router  ──► Pydantic Schema (validation)
    │
    ▼
Service  ──► Domain rules, exceptions
    │
    ▼
Unit of Work  ──► transaction begin
    │
    ▼
Repository  ──► SQLAlchemy queries
    │
    ▼
DB
    │
    ▼
ORM Model  ──► Pydantic Schema (response)
    │
    ▼
HTTP Response
```

## Responsibilities

### Router (`modules/{m}/router.py`)

**HTTP only**:

- Accepts a Pydantic schema (input validation)
- Calls the service
- Returns a Pydantic schema (response)
- No business logic, no SQL, no `if-else` about domain rules

```python
@router.post("/", response_model=BrandRead, status_code=201)
async def create_brand(
    payload: BrandCreate,
    service: BrandService = Depends(get_brand_service),
) -> Brand:
    return await service.create(payload)
```

### Service (`modules/{m}/service.py`)

**Business logic**:

- Applies domain rules
- Orchestrates one or more repositories through the UoW
- Raises domain exceptions
- Publishes domain events
- **Depends only on Protocol abstractions** (UoW, Cache), not on SQLAlchemy

```python
class BrandService:
    def __init__(self, uow: UnitOfWork, events: EventBus) -> None:
        self._uow = uow
        self._events = events

    async def create(self, data: BrandCreate) -> Brand:
        async with self._uow:
            if await self._uow.brands.exists_by_name(data.name):
                raise BrandAlreadyExistsError(data.name)
            brand = await self._uow.brands.create(data.model_dump())
            await self._uow.commit()
        await self._events.publish(BrandCreated(brand_id=brand.id))
        return brand
```

### Repository (`modules/{m}/repository.py`)

**Database queries only**:

- Inherits from `SQLAlchemyRepository[Model]` (`infrastructure/repository.py`): get, add, bulk add, update, delete and both pagination styles out of the box
- Adds specific queries (`get_by_slug`, filtered listings through `_slice`)
- Contains no business logic, and no pre-check queries for uniqueness: the database constraint decides, and the violation is mapped to 409/422 centrally

```python
class BrandRepository(SQLAlchemyRepository[Brand]):
    model = Brand

    async def get_by_slug(self, slug: str) -> Brand | None:
        return await self.session.scalar(select(Brand).where(Brand.slug == slug))
```

### Unit of Work

**Transaction boundary** (`infrastructure/unit_of_work.py`):

- Groups repositories into one transaction
- Nothing persists without an explicit `commit()`; exit, early return or an exception roll back
- The service never works with `session` directly

`SQLAlchemyUnitOfWork` owns the session lifecycle. The app-level subclass attaches every module's repository in `_init_repositories()`:

```python
class AppUnitOfWork(SQLAlchemyUnitOfWork):
    brands: BrandRepository
    products: ProductRepository

    def _init_repositories(self) -> None:
        self.brands = BrandRepository(self.session)
        self.products = ProductRepository(self.session)
```

```python
async with uow:
    order = await uow.orders.add(Order(...))
    await uow.variants.reserve(items)
    await uow.commit()  # both writes, or neither
```

## Prohibitions

- The router **does not call** a Repository directly
- The service **does not work** with `Session` directly (only through the UoW)
- A repository **does not return** Pydantic schemas (only ORM models)
- ORM models **do not leak** into an HTTP response without a projection through a schema
- The service **does not import** `HTTPException` (only domain exceptions)

## Where the logic lives

| Where | What |
|-------|------|
| Router | HTTP format, status codes |
| Schema | Structural validation (types, lengths, formats) |
| Service | Business rules, orchestration |
| Domain Model / Value Object | Invariants ("price ≥ 0", "order status changes along a graph") |
| Repository | SQL and projections |
| DB constraint | Integrity (FK, unique, check) |

The rule: **duplicated validation beats missing validation**. Pydantic catches "not a number in the price field", the service catches "price ≤ 0", the DB enforces `CHECK (price >= 0)`. Each layer protects itself.
