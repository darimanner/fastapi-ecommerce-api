# ADR-0005: Variant options as JSONB

- **Date:** 2026-11-17
- **Status:** Accepted

## Context

A product is sold in variants (SKUs) that differ by options: size, color, material. The catalog needs three things from options: two variants of one product must not share the same option set, the storefront filters by option values (`size=M`), and admins enter options freely per product without a schema change. Faceted search (counts per option value) is not needed yet.

## Decision

- `product_variants.options` is a JSONB object of string names to string values, at most 10 pairs, `{}` for a product without options.
- `UNIQUE (product_id, options)`: JSONB equality ignores key order, so `{"size": "M", "color": "red"}` and the same pairs in another order collide, and the database rejects duplicates under concurrency (409).
- A GIN index on `options` serves the containment filter. The listing turns repeated `option=name:value` parameters into one object and matches `options @> :object`, so all pairs must hold on the same variant.

## Consequences

**Positive:**

- One column and one constraint; no join tables for the common case
- Postgres enforces uniqueness and serves filters from an index
- New option names need no migration

**Negative:**

- No referential integrity on names or values: "Size" and "size" are different options; the admin client has to be consistent
- Facet counts (how many products per size) would need `jsonb_each` aggregation over all variants, which does not use the index

**Neutral:**

- If facets or option ordering for the storefront become requirements, options move to `product_options` / `product_option_values` tables with a variant link table; the API shape (`options` as an object) can stay

## Alternatives Considered

1. **Option tables (Shopify-like): `product_options`, `option_values`, `variant_option_values`** - strict and facet-friendly, but four tables, and uniqueness of a variant's option set needs a trigger or a computed key.
2. **Fixed columns (`size`, `color`)** - simplest queries, but every new option is a migration and most columns are null for most products.
3. **EAV table without uniqueness** - flexible, but duplicate variants are only caught in application code, which races.
