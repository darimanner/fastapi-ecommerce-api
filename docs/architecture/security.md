# Security

> Status: partially implemented

Authentication and authorization (RBAC) are built. Security headers, CORS, rate limiting, dependency vulnerability scanning, the audit trail and idempotency are planned; their sections below are design only and are marked so.

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
- There is no rate limit on login and register until the rate limiting stage. Each attempt costs one argon2 hash (about 64 MiB of memory, run in the default thread pool).

### CSRF and enumeration

Refresh and logout read a cookie, so CSRF applies. The cookie is `SameSite=Strict`, the app has no CORS middleware, and a cross-origin page cannot read the token response. A same-site sibling origin could at most trigger a rotation or a logout, which is a nuisance only.

Register answers 409 for a taken email, so it reveals that the email is registered. The dummy hash only equalizes login timing; it does not hide existence at registration.

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
├── permissions.py # Permission, ROLE_PERMISSIONS
└── deps.py        # Principal, get_current_user, CurrentUser, requires
```

`get_current_user` reads the Bearer token, decodes it as an access token and builds a `Principal(id, role)`. A missing header, an expired or foreign token, or a missing or unknown `role` claim all give 401 with `WWW-Authenticate: Bearer`. Emails are lowercased in the schema and in the database (`CHECK (email = lower(email))`); passwords are 8 to 128 characters on registration.

## Authorization

> Status: implemented

### RBAC via permissions

A user has a role, roles have permissions, and the permissions are resolved on the server from the `role` claim (the token carries no permissions). `Principal.permissions` looks the role up in `ROLE_PERMISSIONS`. A change of a user's role applies at the next refresh, because the role is a token claim that refresh re-reads from the database; a change to `ROLE_PERMISSIONS` applies immediately, because the lookup is server-side.

```python
# src/ecommerce/modules/auth/permissions.py
class Permission(StrEnum):
    BRANDS_WRITE = "brands:write"
    CART_MANAGE = "cart:manage"
    CATEGORIES_WRITE = "categories:write"
    PRODUCTS_WRITE = "products:write"


ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.CUSTOMER: frozenset({Permission.CART_MANAGE}),
    Role.ADMIN: frozenset(Permission),
}


# src/ecommerce/modules/auth/deps.py
def requires(*permissions: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    async def check(principal: CurrentUser) -> Principal:
        missing = [p.value for p in permissions if p not in principal.permissions]
        if missing:
            raise ForbiddenError(
                f"Missing permissions: {', '.join(missing)}", missing=missing
            )
        return principal

    return check


# modules/brands/router.py
admin_router = APIRouter(
    prefix="/admin/brands",
    tags=["admin"],
    dependencies=[Depends(requires(Permission.BRANDS_WRITE))],
)
```

The dependency sits on the router, so every write route of the module is covered, including the variant routes of the products `admin_router`. Public `router`s have no dependency. The cart router carries `cart:manage` (granted to `customer`) and every route acts on the caller's own cart: there is no cart id in any URL.

- 401: no token, or an expired, malformed or foreign one (`WWW-Authenticate: Bearer`).
- 403: a valid token whose role lacks a permission; the problem body lists the missing ones in `missing`.

The first admin is created with `make admin email=...` (`python -m ecommerce.cli create-admin EMAIL`, a Typer app). The password comes from `ADMIN_PASSWORD` or a hidden prompt asked twice (again on a mismatch) and is never echoed. There is no `--password` option: a command-line argument would land in shell history and the process list. Tracebacks are plain Python ones, so they never print local variables. Exit code 0: created; 2: invalid input or usage; 1: not created (for example a duplicate email; other failures, such as an unreachable database, print a traceback).

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

> Status: planned

Standard FastAPI middleware configured from `cors_origins` in the application settings (`config/settings.py`). **Do not use `*`** in production: use an explicit list of origins. Credentials are allowed only with an explicit list.

## Secrets Management

| Environment | Where |
|-------------|-------|
| Local | `.env` (not committed), `.env.example` in the repo |
| Production | NOT files. Env vars from AWS Secrets Manager / Parameter Store / HashiCorp Vault / SOPS |

Never log secrets: a structlog processor masks the keys `password|secret|token|authorization`.

## Rate Limiting

> Status: planned

See [Rate Limiting](rate-limiting.md). Applied globally, with stricter limits on auth endpoints (login: 5/min, register: 3/hour).

## Input Validation

- Pydantic schemas on input are mandatory
- Lengths, formats and regexes go in `Field(...)` constraints
- ID parameters use `Annotated[int, Path(gt=0)]` or `Annotated[UUID, Path()]`
- SQL injection is not possible (SQLAlchemy parameterized queries)
- HTML in fields is escaped on the frontend; the backend stores it as-is, or sanitizes it with `bleach` if it ends up in HTML output

## Sensitive Data in Models

`password_hash` never leaves the service:
- `UserRead` has no `password_hash`, and tests assert it is absent from responses
- The models use the default SQLAlchemy `__repr__` (`core/db/model.py` does not override it), which prints no column values
- Separate public and admin user read schemas are planned

## Dependency Vulnerabilities

> Status: planned

CI runs `pip-audit` (or `uv audit` once it stabilizes) and fails on known CVEs.

`dependabot` or `renovate` open automatic PRs to update dependencies.

## Audit Trail

> Status: planned

Via `AuditMixin` (`created_by`, `updated_by`), plus optionally a separate `audit_log` table with a JSON dump of changes to critical entities (Order, Payment, User permissions).

## Idempotency

> Status: planned

Critical POST endpoints (order placement, payment) support the `Idempotency-Key` header. Requests with the same key return the same result, and a second call does not repeat the operation. Implemented with middleware plus a Redis cache of responses.
