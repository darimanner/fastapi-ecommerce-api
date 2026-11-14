# Security

> Status: planned

## Authentication

### JWT: PyJWT

`PyJWT`, **not `python-jose`**: the latter is abandoned and has CVEs.

```python
# src/fastapi_ecommerce_api/core/security/jwt.py
def encode_token(payload: dict, expires_in: timedelta) -> str: ...
def decode_token(
    token: str,
) -> dict: ...  # raises UnauthorizedError if the token is invalid
```

Claims structure:

```json
{
  "sub": "<user_uuid>",
  "iat": 1700000000,
  "exp": 1700003600,
  "jti": "<token_uuid>",
  "scope": "access | refresh",
  "permissions": ["orders:read", "orders:write"]
}
```

### Access + Refresh tokens

- **Access**: short-lived (15 minutes), sent in `Authorization: Bearer`
- **Refresh**: long-lived (30 days), kept in an HttpOnly cookie or the client's secure storage
- `jti` is stored in Redis so that tokens can be revoked (logout, ban, password change)

### Password Hashing: Argon2

`passlib[argon2]` or `argon2-cffi` directly.

```python
# src/fastapi_ecommerce_api/core/security/passwords.py
from argon2 import PasswordHasher

hasher = PasswordHasher()  # argon2id, sane defaults


def hash_password(plain: str) -> str:
    return hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, plain)
    except VerifyMismatchError, InvalidHash:
        return False
```

Argon2id is the current OWASP standard. Not bcrypt (old), not PBKDF2 (slow with no benefit), not sha256 (not suitable for passwords at all).

### Auth Module

```
src/fastapi_ecommerce_api/modules/auth/
├── router.py      # POST /auth/register, /auth/login, /auth/refresh, /auth/logout
├── service.py     # AuthService.login, register, refresh, logout
├── models.py      # User
├── schemas.py     # RegisterRequest, LoginRequest, TokenResponse
├── repository.py  # UserRepository
├── deps.py        # get_current_user(), get_current_user_optional()
├── exceptions.py  # InvalidCredentialsError, TokenExpiredError, etc.
└── events.py      # UserRegistered, UserLoggedIn
```

## Authorization

### RBAC via permissions

A user has roles, roles have permissions, and permissions go into the JWT claims.

```python
# src/fastapi_ecommerce_api/modules/auth/deps.py
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

Middleware (`src/fastapi_ecommerce_api/core/security/headers.py`) adds:

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

Via `AuditMixin` (`created_by`, `updated_by`), plus optionally a separate `audit_log` table with a JSON dump of changes to critical entities (Order, Payment, User permissions).

## Idempotency

Critical POST endpoints (order placement, payment) support the `Idempotency-Key` header. Requests with the same key return the same result, and a second call does not repeat the operation. Implemented with middleware plus a Redis cache of responses.
