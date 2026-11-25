# Tests

- One PostgreSQL container per session (`tests/conftest.py`); the schema is built by the Alembic migrations, then `alembic check` fails the run if a model change has no migration.
- `session_factory` (`tests/conftest.py`) gives sessions that commit into savepoints of one outer transaction rolled back after each test; use it to test real `commit()` behavior. `db_session` is one such session. `client`: an httpx `AsyncClient` on the app with `get_db` and `get_uow` overridden to that transaction and `get_redis` to the `redis` fixture (one Redis container per session, `FLUSHDB` before each test).
- `tests/modules/` tests each module through HTTP with `client`; `brand` and `category` fixtures live in `tests/modules/conftest.py`, request helpers in `tests/modules/catalog.py`. Override settings with `monkeypatch.setattr(settings.<group>, ...)`: dependencies read them per request.
- Concurrency tests need real commits on separate connections: build `async_sessionmaker(engine)` and delete what they created in `finally`.
- Code that calls `asyncio.run` (the CLI commands) cannot use `session_factory` or `db_session`: they are bound to the session-scoped event loop. Test it in a sync test through `typer.testing.CliRunner`, with its own `create_async_engine(postgres_url)`, and clean up in `finally` (see `tests/test_cli.py`).
- `tests/core/` tests the framework layer against scratch tables (`tests/core/scratch.py`) on their own `ScratchBase` metadata, so Alembic never sees them. Do not name such classes `Test*`: pytest would collect them.
- Prefer real Postgres over mocks for anything touching SQL, constraints or transactions; unit tests of services use a fake Unit of Work.
- Produce constraint errors for real (flush a violating row) instead of hand-building `IntegrityError`, except to test the unknown-error path.
