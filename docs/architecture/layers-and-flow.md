# Layers & Flow

> Status: partially implemented
>
> Implemented: the generic repository, the Unit of Work, `CRUDService`, and the `brands` and `categories` modules. Planned: domain events published from services.

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
def get_service(uow: UoW) -> BrandService:
    return CRUDService(uow, lambda: uow.brands)


Service = Annotated[BrandService, Depends(get_service)]


@admin_router.post("", response_model=BrandRead, status_code=201)
async def create_brand(service: Service, payload: BrandCreate) -> Brand:
    return await service.create(payload)
```

Each module has a public `router` (`/api/v1/brands`) and an `admin_router` (`/api/v1/admin/brands`) for writes. Admin routes are open until the auth module adds permission checks.

### Service (`modules/{m}/service.py`)

**Business logic**:

- Applies domain rules
- Orchestrates one or more repositories through the UoW
- Raises domain exceptions
- Publishes domain events (planned)
- **Depends only on Protocol abstractions** (UoW, Cache), not on SQLAlchemy

Standard CRUD needs no service class of its own: `core/crud.py::CRUDService[Model, Create, Update]` gives `get`, `list_offset`, `create`, `replace` (PUT), `update` (PATCH, only the fields sent) and `delete`, each in one transaction. A module writes a service only when it has rules, and puts them in the `_before_write` hook, which runs inside the write transaction:

```python
class CategoryUnitOfWork(UnitOfWork, Protocol):
    categories: CategoryRepository


class CategoryService(CRUDService[Category, CategoryCreate, CategoryUpdate]):
    async def _before_write(
        self, entity: Category | None, values: dict[str, Any]
    ) -> None: ...  # cycle and depth checks on parent_id, under a tree lock
```

The service declares the slice of the Unit of Work it needs as a Protocol, so it does not import the app-level UoW.

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

`SQLAlchemyUnitOfWork` owns the session lifecycle. The app-level subclass in `src/fastapi_ecommerce_api/uow.py` (the composition root, so `core/` stays module-agnostic) attaches every module's repository in `_init_repositories()`, and routers get it through the `UoW` dependency:

```python
class AppUnitOfWork(SQLAlchemyUnitOfWork):
    brands: BrandRepository
    categories: CategoryRepository

    def _init_repositories(self) -> None:
        self.brands = BrandRepository(self.session)
        self.categories = CategoryRepository(self.session)
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
