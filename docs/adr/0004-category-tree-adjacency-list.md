# ADR-0004: Category tree as an adjacency list with a locked guard

- **Date:** 2026-11-15
- **Status:** Accepted

## Context

Categories form a tree: "Shoes > Running > Trail". Admins create nodes and move them under other parents with POST, PUT and PATCH. Two things must never happen: a node ending up under itself or its own descendant (a cycle, which breaks every tree query), and a tree deeper than the shop wants to show. The depth limit must be configurable: a shop that needs 3 levels today may need 5 later without a migration. The tree is small (hundreds or thousands of rows) and written rarely; reads are by id or by subtree.

## Decision

- `categories.parent_id` is a nullable self-referencing foreign key (adjacency list). No `ON DELETE` action: deleting a node that has children is a 409.
- The depth limit is the `catalog.max_category_depth` setting (default 5), checked in `CategoryService`, not encoded in the schema.
- When a write sets a new parent, the service, inside the write transaction:
  1. takes `pg_advisory_xact_lock` on one constant key for the tree;
  2. walks from the new parent to the root with a recursive CTE (`UNION`, so it terminates even on bad data);
  3. rejects with 409 if the node is on that path (cycle), or if the path length plus the node's subtree height exceeds the limit (depth), naming the ids involved.
- Writes that do not change the parent skip the guard, so renaming a node in a tree that is already at the limit still works.

## Consequences

**Positive:**

- One column and plain foreign keys; inserts and moves touch one row
- The depth limit changes through configuration
- The lock closes the race where two concurrent moves (A under B, B under A) each pass the check on a snapshot that does not see the other; a test reproduces that race with real commits

**Negative:**

- The guard lives in the service: a write that bypasses `CategoryService` (raw SQL, a migration) is not checked
- All tree moves are serialized through one lock; fine for a small admin-written table, not for a hot one
- Subtree reads need a recursive CTE

## Alternatives Considered

1. **`ltree` path column** - fast subtree queries and cheap depth checks, but a move rewrites the paths of the whole subtree, and the extension and path upkeep cost more than this table needs.
2. **Nested sets** - fast reads, but inserts and moves renumber a large part of the table.
3. **Closure table** - fast reads and easy cycle checks, but a second table whose rows grow with depth times size and must be rewritten on every move.
4. **A trigger that checks cycles** - also catches raw SQL, but moves rules into PL/pgSQL, away from the typed code and its tests, and still needs the lock against concurrent moves.
