# ADR-0003: Pagination without count(*)

- **Date:** 2026-11-15
- **Status:** Accepted

## Context

The usual paginated response carries `total`, computed with `SELECT count(*)` next to every page query. In PostgreSQL `count(*)` scans the whole table (or index) under MVCC, so on large tables like products and orders it costs more than the page itself, and it runs on every request, filters included. Offset pagination has a similar problem on deep pages: `OFFSET 100000` still reads and discards 100000 rows.

## Decision

- Repositories fetch `limit + 1` rows and return `Slice(items, has_next)`; responses carry `has_next` instead of a total.
- Large tables use keyset (cursor) pagination: `WHERE (sort_key, id) > (:last_sort_key, :last_id)`, with an opaque cursor; small reference tables may use offset.
- Where a screen really needs an exact total (the storefront product listing), it comes from a Redis count cache keyed by the normalized filter plus a catalog version counter. Every product or variant write increments the version, so a cached total is never stale after a commit. The cache arrives together with the catalog.

## Consequences

**Positive:**

- Page cost does not grow with table size or page depth
- No count query on the hot path
- Exact totals stay possible where they matter, without scanning

**Negative:**

- Clients get "next page exists" instead of a page count by default
- Keyset pagination cannot jump to an arbitrary page number
- The count cache adds invalidation logic and a Redis dependency to the catalog

**Neutral:**

- Response models: `Page[T]` (`items`, `has_next`, optional `total`) and `CursorPage[T]` (`items`, `next_cursor`, optional `total`)

## Alternatives Considered

1. **`count(*)` on every request** - simple and exact, but a full scan per page on large tables.
2. **Estimates from `pg_class.reltuples` or `EXPLAIN`** - cheap, but approximate and useless with filters.
3. **Counter columns maintained by triggers** - exact for unfiltered totals only, and adds write contention on a hot row.
