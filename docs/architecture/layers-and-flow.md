# Layers & Flow

> Status: planned

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
    def __init__(self, uow: AbstractUnitOfWork, events: EventBus) -> None:
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

- Inherits from `SQLAlchemyRepository[Model]` (CRUD out of the box)
- Adds specific methods (`exists_by_name`, `get_with_products`)
- Contains no business logic

```python
class BrandRepository(SQLAlchemyRepository[Brand]):
    model = Brand

    async def exists_by_name(self, name: str) -> bool:
        stmt = select(exists().where(Brand.name == name))
        return bool(await self._session.scalar(stmt))
```

### Unit of Work (`core/db/unit_of_work.py`)

**Transaction boundary**:

- Groups repositories into one transaction
- Rolls back on exception
- The service never works with `session` directly

```python
class SQLAlchemyUnitOfWork:
    brands: BrandRepository
    products: ProductRepository
    orders: OrderRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.brands = BrandRepository(self._session)
        self.products = ProductRepository(self._session)
        self.orders = OrderRepository(self._session)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
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
