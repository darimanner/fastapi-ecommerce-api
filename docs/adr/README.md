# Architecture Decision Records

A log of significant architectural decisions. Format: Michael Nygard's ADR.

Each decision is documented once, at the moment it is made. If a decision is revisited, a new ADR is written with the status `Supersedes ADR-XXXX`, and the old one is marked `Superseded by ADR-YYYY`.

## Why

- Your future self (or a new developer) understands **why** the code is the way it is, and not some other way
- Alternatives that were considered stay in the history, so nobody has to go through the same debate again
- Discipline: writing a decision down makes you understand it more deeply
- For a portfolio, it is a strong signal of the ability to think architecturally

## Format

See [template.md](template.md). An ADR is short: 1 page, 2 at most.

## When to write an ADR

- Choosing between several approaches with long-term consequences
- Introducing a new pattern into the codebase
- Changing an existing architectural decision
- Deliberately choosing a "bad" option with a justification (technical debt with open eyes)

Not every decision is an ADR. There is no need for an ADR for "chose PyJWT over a hand-written encode" - there is no long-term alternative there. An ADR is needed for "chose PyJWT over python-jose, and not authlib" - that is a deliberate choice between close options.

## Index

- [0001 - Layered architecture with Unit of Work](0001-layered-architecture-with-uow.md)

## Candidates

Decisions worth recording as they are made:

- Custom rate limiting middleware instead of slowapi
- In-process domain events with a migration path to a broker
- Modular monolith (modules by domain, not global layers)
- Argon2id for password hashing (instead of bcrypt)
- Taskiq instead of Celery for background tasks
- RFC 7807 for the error response format
- Soft delete by default for core e-commerce entities
