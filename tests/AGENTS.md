# Tests

- One PostgreSQL container per session (`tests/conftest.py`); the schema is built by the Alembic migrations, then `alembic check` fails the run if a model change has no migration.
- `db_session`: a session inside a transaction rolled back after each test. `client`: an httpx `AsyncClient` on the app with `get_db` overridden to that session.
- `tests/core/` tests the framework layer against scratch tables (`tests/core/scratch.py`) on their own `ScratchBase` metadata, so Alembic never sees them. Do not name such classes `Test*`: pytest would collect them.
- `session_factory` (`tests/core/conftest.py`) gives sessions that commit into savepoints of one outer transaction; use it to test real `commit()` behavior.
- Prefer real Postgres over mocks for anything touching SQL, constraints or transactions; unit tests of services use a fake Unit of Work.
- Produce constraint errors for real (flush a violating row) instead of hand-building `IntegrityError`, except to test the unknown-error path.
