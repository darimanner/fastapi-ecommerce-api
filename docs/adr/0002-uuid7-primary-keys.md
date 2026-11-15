# ADR-0002: UUIDv7 primary keys

- **Date:** 2026-11-15
- **Status:** Accepted

## Context

Every table needs a primary key, and the ids appear in public URLs (`/api/v1/products/{id}`, `/api/v1/orders/{id}`). Sequential integers leak business volume (order 10432 tells a competitor how many orders exist) and invite enumeration of other users' resources. Random UUIDv4 fixes that but scatters inserts across the B-tree index, which hurts write locality on large tables, and gives no natural order for keyset pagination.

Python 3.14 ships `uuid.uuid7()` in the standard library: a UUID whose first 48 bits are a millisecond timestamp, monotonic within a process.

## Decision

All tables use `UUIDPrimaryKeyMixin` (`core/db/mixins/uuid_pk.py`): `id: Mapped[uuid.UUID]`, primary key, generated in the application with `default=uuid.uuid7`. The generic repository orders by `id` for keyset pagination.

## Consequences

**Positive:**

- Ids are not enumerable and do not leak volume
- Inserts land at the end of the index, like a sequence
- `ORDER BY id` is creation order, so keyset pagination needs no extra column
- Ids are known before the insert, which helps bulk inserts and building related rows

**Negative:**

- 16 bytes per key and per foreign key instead of 8
- The creation time is readable from the id; acceptable here, it is no secret

**Neutral:**

- Generated in Python, not by the database; rows inserted with raw SQL must supply an id

## Alternatives Considered

1. **`bigint` identity** - smallest and fastest, but enumerable and leaks volume in public URLs; a separate public id column would double the keys to maintain.
2. **UUIDv4** - not enumerable, but random inserts fragment the index and give no order for pagination.
3. **Database-generated UUIDv7 (`uuidv7()` in PostgreSQL 18)** - equivalent, but ties the schema to PostgreSQL 18 and hides the id until after the insert; the stdlib generator keeps it in the application.
