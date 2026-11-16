# Testing

> Status: partially implemented
>
> Exists today: pytest-asyncio, httpx `AsyncClient`, testcontainers PostgreSQL, schema built by Alembic migrations plus `alembic check`, per-test transaction rollback, `make test` (`pytest --cov`, 85% gate), and CI via `.github/workflows/ci.yml`. Module tests live in `tests/modules/` and go through HTTP; the `client` fixture swaps both `get_db` and `get_uow` for sessions on the test transaction. The category tree rules have SQL in them, so they are tested against Postgres, including a race of two concurrent moves on real commits. Planned: `FakeUnitOfWork` unit tests for services whose rules need no SQL (orders), polyfactory factories.

## Structure

```
tests/
├── conftest.py              # global fixtures
├── factories/               # polyfactory factories
│   ├── brand.py
│   └── product.py
├── unit/                    # services with FakeUnitOfWork
│   ├── modules/
│   │   ├── brands/
│   │   │   └── test_service.py
│   │   └── orders/
│   └── core/
└── integration/             # real DB, real HTTP
    ├── conftest.py          # testcontainers fixture
    └── modules/
        └── brands/
            └── test_api.py
```

## Strategy

A pyramid:

- **Many** unit tests (fast, pure)
- **Fewer** integration tests (slow, but realistic)
- **Minimal** e2e / contract tests (brittle, valuable for critical paths)

### Unit

Planned, for services whose rules need no SQL (the order state machine):

- Services are tested with `FakeUnitOfWork` and `FakeRepository` (in-memory dict)
- No real DB, no FastAPI
- They cover business rules and edge cases
- Uniqueness and references are not unit-tested: the database constraints own them, so they are tested through HTTP against Postgres

```python
async def test_paid_order_cannot_go_back_to_pending(fake_uow: FakeUnitOfWork) -> None:
    order = await fake_uow.orders.add(an_order(status=OrderStatus.PAID))
    service = OrderService(fake_uow)

    with pytest.raises(IllegalTransitionError):
        await service.transition(order.id, OrderStatus.PENDING)
```

### Integration

- HTTP level through `httpx.AsyncClient` with the ASGI transport (no server is started)
- Real Postgres through `testcontainers`
- Migrations are applied to an empty DB at the start of the session
- Each test runs in a transaction with rollback in teardown: isolated and fast

```python
@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
async def engine(postgres_container: PostgresContainer):
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Each test runs in a transaction with rollback at the end."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn) as session:
            yield session
        await trans.rollback()


@pytest.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

### Contract / E2E

Optional:

- `schemathesis`: fuzz testing based on the OpenAPI schema; catches mismatches between the documentation and actual behavior
- `hypothesis`: property-based tests for critical services (for example, Order state machine invariants)

## Test Data

`polyfactory` is a modern alternative to `factory_boy`, with Pydantic + SQLAlchemy support:

```python
from polyfactory.factories.sqlalchemy_factory import SQLAlchemyFactory


class BrandFactory(SQLAlchemyFactory[Brand]):
    __model__ = Brand
    __set_relationships__ = True
```

Usage:

```python
async def test_list_products_filters_by_brand(client, db_session):
    nike = await BrandFactory.create_async(name="nike", session=db_session)
    adidas = await BrandFactory.create_async(name="adidas", session=db_session)
    await ProductFactory.create_batch_async(3, brand_id=nike.id, session=db_session)
    await ProductFactory.create_batch_async(2, brand_id=adidas.id, session=db_session)
    await db_session.commit()

    response = await client.get(f"/api/v1/products?brand_id={nike.id}")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 3
```

## Coverage

`pytest-cov` with a threshold in CI:

```bash
uv run pytest --cov=fastapi_ecommerce_api --cov-fail-under=85 --cov-report=term-missing
```

Targets by layer:

| Layer | Coverage |
|-------|----------|
| Service | 95%+ (all business logic) |
| Repository | 80%+ (via integration) |
| Router | 70-80% (almost no logic there) |
| Core / Infrastructure | 90%+ |

## Anti-patterns

- **Do not mock SQLAlchemy**: a mock is detached from reality ("the test passes, prod fails")
- **Do not use sqlite-in-memory** for tests of Postgres-specific code: dialects diverge (JSONB, ARRAY, UUID)
- **Do not share state between tests**: flaky Fridays; every test must work in any order
- **Do not run integration tests without cleanup**: use a fixture with rollback or truncate

## CI

```yaml
- ruff check .
- ruff format --check .
- mypy src/fastapi_ecommerce_api
- pytest --cov=fastapi_ecommerce_api --cov-fail-under=85
- pip-audit
```

Tests with testcontainers require Docker on the CI runner, which is standard for GitHub Actions Ubuntu.

## Performance & Load

Not part of unit/integration, but lives in `tests/load/` (optional):

- `locust` or `k6` scenarios
- Run manually or once a week in CI
- Check the SLO (p95 < 200ms, error rate < 0.1%)
