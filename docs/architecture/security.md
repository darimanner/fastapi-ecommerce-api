# Security

> Status: partially implemented

Authentication is built. Authorization (RBAC), security headers, the audit trail and idempotency are planned; their sections below are design only and are marked so.

## Authentication

Stateless short-lived access tokens plus rotating refresh tokens whose `jti` lives in Redis. The reasoning is in [ADR-0006](../adr/0006-stateless-access-rotating-refresh.md).

### Libraries

- **PyJWT** (pinned `>=2.15.1`; earlier versions have open 2026 advisories). Not `python-jose`: it is abandoned and has CVEs.
- **argon2-cffi** used directly. Not `passlib` (unmaintained). `pwdlib` would only wrap argon2-cffi here, because there are no legacy hashes to migrate.
- Hardening rule for JWT: the HMAC key is always the plain secret string (never a JWK, a PEM or `PyJWK`), `algorithms=["HS256"]` is passed explicitly on every decode, and `PyJWKClient` is not used. This keeps the code off the key-confusion paths behind most PyJWT advisories.

### Tokens

`src/ecommerce/core/security/tokens.py`: `issue_token(subject, token_type, ttl, **claims)` returns a `Token` (value, `jti`, `expires_in`); `decode_token(value, token_type)` raises `UnauthorizedError("Invalid or expired token")` for a bad signature, an expired token, missing claims or the wrong type. HS256, signed with `AUTH__SECRET_KEY` (required, at least 32 characters).

| Token | Lifetime | Claims |
|-------|----------|--------|
| Access | 15 minutes (`auth.access_ttl`) | `sub` (user id), `role`, `jti`, `type="access"`, `iat`, `exp` |
| Refresh | 30 days (`auth.refresh_ttl`) | `sub`, `jti`, `type="refresh"`, `iat`, `exp` |

There are no permissions in the token. The access token goes in `Authorization: Bearer`. The refresh token travels only in the `refresh_token` cookie: HttpOnly, `Secure` (setting `auth.cookie_secure`, default true), `SameSite=Strict`, `Path=/api/v1/auth`, `Max-Age` equal to the refresh lifetime.

### Refresh rotation

Each refresh token is stored in Redis as `auth:refresh:<jti>` -> user id with the refresh TTL. `POST /auth/refresh` consumes the key with `GETDEL` before it opens the database transaction, so of concurrent refreshes with the same token only one succeeds. A successful refresh issues a new pair and stores the new `jti`. `POST /auth/logout` deletes the key and clears the cookie; it succeeds without a valid cookie.

Redis errors map to 503 through the global handler: authentication fails closed when Redis is down.

### Accepted tradeoffs

- Logout revokes only the refresh token. The access token stays valid for up to 15 minutes.
- A ban (`is_active = false`) or a role change applies at the next refresh, not immediately. `GET /users/me` does not check `is_active`.
- If the database or Redis fails right after `GETDEL`, the old refresh token is already spent and the user logs in again.
- Refresh token reuse detection (revoking the whole token family when a spent token is replayed) is not built.

### Password hashing: Argon2id

`src/ecommerce/core/security/passwords.py`: `hash_password` and `verify_password` are async and run argon2-cffi (argon2id, library defaults) in `asyncio.to_thread`, so hashing never blocks the event loop. The service hashes and verifies outside the database transaction to keep the connection free.

Login for an unknown email runs one verification against `DUMMY_HASH`, so the response time does not reveal whether the email exists. An inactive user is rejected only after the password check. Wrong email, wrong password and inactive user return the same `Invalid email or password`.

Argon2id is the current OWASP recommendation. Not bcrypt (old), not PBKDF2 (slow with no benefit), not sha256 (not suitable for passwords at all).

### Auth module

```
src/ecommerce/modules/auth/
├── router.py      # /auth/register, /auth/login, /auth/refresh, /auth/logout; GET /users/me
├── service.py     # AuthService: register, login, refresh, logout, get_user
├── models.py      # User, Role (customer, admin)
├── schemas.py     # RegisterRequest, LoginRequest, TokenResponse, UserRead
├── repository.py  # UserRepository (get_by_email)
└── deps.py        # Principal, get_current_user, CurrentUser
```

`get_current_user` reads the Bearer token, decodes it as an access token and builds a `Principal(id, role)`. A missing header, an expired or foreign token, or a missing or unknown `role` claim all give 401 with `WWW-Authenticate: Bearer`. Emails are lowercased in the schema and in the database (`CHECK (email = lower(email))`); passwords are 8 to 128 characters on registration.

## Authorization

> Status: planned

### RBAC via permissions

A user has a role, roles have permissions, and the permissions are resolved on the server from the `role` claim (the token carries no permissions).

```python
# src/ecommerce/modules/auth/deps.py
def requires(*permissions: str) -> Callable:
    async def dep(user: User = Depends(get_current_user)) -> User:
        if not all(p in user.permissions for p in permissions):
            raise ForbiddenError(f"Missing permissions: {permissions}")
        return user

    return dep


@router.delete("/{id}")
async def delete_brand(id: int, _: User = Depends(requires("brands:delete"))): ...
```

For complex rules the alternative is **policy-based** authorization: a separate class such as `BrandPolicy.can_delete(user, brand)` with conditions like "owner or admin".

## Security Headers

> Status: planned

Middleware (`src/ecommerce/core/security/headers.py`) adds:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
Permissions-Policy: ...
```

CSP `default-src 'none'` suits a pure API (no HTML). The admin UI and Swagger UI need separate exceptions.

## CORS

Standard FastAPI middleware configured from `cors_origins` in the application settings (`config/settings.py`). **Do not use `*`** in production: use an explicit list of origins. Credentials are allowed only with an explicit list.

## Secrets Management

| Environment | Where |
|-------------|-------|
| Local | `.env` (not committed), `.env.example` in the repo |
| Production | NOT files. Env vars from AWS Secrets Manager / Parameter Store / HashiCorp Vault / SOPS |

Never log secrets: a structlog processor masks the keys `password|secret|token|authorization`.

## Rate Limiting

See [Rate Limiting](rate-limiting.md). Applied globally, with stricter limits on auth endpoints (login: 5/min, register: 3/hour).

## Input Validation

- Pydantic schemas on input are mandatory
- Lengths, formats and regexes go in `Field(...)` constraints
- ID parameters use `Annotated[int, Path(gt=0)]` or `Annotated[UUID, Path()]`
- SQL injection is not possible (SQLAlchemy parameterized queries)
- HTML in fields is escaped on the frontend; the backend stores it as-is, or sanitizes it with `bleach` if it ends up in HTML output

## Sensitive Data in Models

Fields such as `password_hash`:
- `repr=False` in the SQLAlchemy mapper, so they do not end up in `__repr__`
- Not included in Pydantic Read schemas
- Separate `UserPublicRead` (no secrets) and `UserAdminRead` (with email, etc.) for different contexts

## Dependency Vulnerabilities

CI runs `pip-audit` (or `uv audit` once it stabilizes) and fails on known CVEs.

`dependabot` or `renovate` open automatic PRs to update dependencies.

## Audit Trail

> Status: planned

Via `AuditMixin` (`created_by`, `updated_by`), plus optionally a separate `audit_log` table with a JSON dump of changes to critical entities (Order, Payment, User permissions).

## Idempotency

> Status: planned

Critical POST endpoints (order placement, payment) support the `Idempotency-Key` header. Requests with the same key return the same result, and a second call does not repeat the operation. Implemented with middleware plus a Redis cache of responses.
