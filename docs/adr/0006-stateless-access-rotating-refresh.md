# ADR-0006: Stateless access tokens with rotating refresh tokens

- **Date:** 2026-11-23
- **Status:** Accepted

## Context

The API needs authentication for browser and API clients. Most requests are reads that should not pay for a session lookup, but a user must be able to log out, and a stolen long-lived credential must have a bounded lifetime. Redis is already part of the stack.

## Decision

- The access token is a short-lived (15 minutes) JWT, HS256, with `sub`, `role`, `jti`, `type`, `iat` and `exp`. It is verified from the signature alone, with no database or Redis call.
- The refresh token is a JWT (30 days) whose `jti` is stored in Redis as `auth:refresh:<jti>` with the same TTL. It lives in an HttpOnly, `SameSite=Strict` cookie scoped to `/api/v1/auth`.
- Refresh is rotation: the key is consumed with `GETDEL` before anything else, then a new pair is issued. Logout deletes the key.
- If Redis is unavailable, login, refresh and logout return 503 (fail closed).

## Consequences

**Positive:**

- Authenticated requests need no storage round trip; the API scales horizontally without sticky sessions.
- Concurrent refreshes with one token cannot both succeed: `GETDEL` is atomic.
- Redis holds only live refresh `jti` values, which expire by themselves.

**Negative:**

- Logout revokes only the refresh token; a leaked access token works for up to 15 minutes.
- A ban or a role change applies at the next refresh, so up to 15 minutes late.
- If the database or Redis fails right after `GETDEL`, the old refresh token is spent and the user has to log in again.
- Reuse detection (revoking the whole token family when a spent token is replayed) is not built; a replayed spent token is only rejected.

**Neutral:**

- Access and refresh tokens share one signing key and are told apart by the `type` claim.
- Libraries: PyJWT and argon2-cffi directly. The HMAC key is always the plain secret and `algorithms=["HS256"]` is explicit on every decode.

## Alternatives Considered

1. **Database lookup of the user on every request** - ban and role change apply at once, but every authenticated request pays a query and the token stops being self-contained. Rejected: a 15-minute delay is acceptable here.
2. **Access token denylist in Redis** - gives immediate revocation, but every request needs a Redis read, which removes the point of stateless tokens. Rejected for the same cost reason.
3. **Refresh tokens in PostgreSQL** - durable and auditable, but rotation becomes a write transaction on a hot path and expiry needs cleanup. Redis gives atomic `GETDEL` and TTL expiry for free; losing Redis only forces users to log in again.
