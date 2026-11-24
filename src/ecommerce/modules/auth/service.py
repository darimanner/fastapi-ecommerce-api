from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis

from ecommerce.config.settings import settings
from ecommerce.core.exceptions.base import UnauthorizedError
from ecommerce.core.security.passwords import DUMMY_HASH, hash_password, verify_password
from ecommerce.core.security.tokens import Token, decode_token, issue_token
from ecommerce.interfaces.repository import Repository
from ecommerce.interfaces.unit_of_work import UnitOfWork
from ecommerce.modules.auth.models import Role, User
from ecommerce.modules.auth.schemas import LoginRequest, RegisterRequest


class Users(Repository[User], Protocol):
    async def get_by_email(self, email: str) -> User | None: ...


class AuthUnitOfWork(UnitOfWork, Protocol):
    # Read-only, so the app UoW may declare the concrete repository type.
    @property
    def users(self) -> Users: ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: Token
    refresh: Token


class InvalidCredentialsError(UnauthorizedError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


def _refresh_key(jti: object) -> str:
    return f"auth:refresh:{jti}"


class AuthService:
    def __init__(self, uow: AuthUnitOfWork, redis: Redis) -> None:
        self._uow = uow
        self._redis = redis

    async def register(self, data: RegisterRequest, role: Role = Role.CUSTOMER) -> User:
        # Hash before opening the transaction: argon2 is slow, keep the connection free.
        password_hash = await hash_password(data.password)
        async with self._uow:
            user = await self._uow.users.add(
                User(email=data.email, password_hash=password_hash, role=role)
            )
            await self._uow.commit()
            return user

    async def login(self, data: LoginRequest) -> TokenPair:
        async with self._uow:
            user = await self._uow.users.get_by_email(data.email)
        # Verify outside the transaction (argon2 is slow); unknown emails burn the same
        # time on the dummy hash and inactive users are rejected only after the check.
        if user is None:
            await verify_password(data.password, DUMMY_HASH)
            raise InvalidCredentialsError
        valid = await verify_password(data.password, user.password_hash)
        if not valid or not user.is_active:
            raise InvalidCredentialsError
        return await self._issue(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = decode_token(refresh_token, "refresh")
        # Consume the token before the DB: of concurrent refreshes only one gets the key.
        if await self._redis.getdel(_refresh_key(claims["jti"])) is None:
            raise UnauthorizedError("Refresh token revoked")
        async with self._uow:
            user = await self._uow.users.get(UUID(claims["sub"]))
        if user is None or not user.is_active:
            raise UnauthorizedError("Refresh token revoked")
        return await self._issue(user)

    async def logout(self, refresh_token: str | None) -> None:
        if refresh_token is None:
            return
        try:
            claims = decode_token(refresh_token, "refresh")
        except UnauthorizedError:
            return  # a dead token is already logged out
        await self._redis.delete(_refresh_key(claims["jti"]))

    async def get_user(self, user_id: UUID) -> User:
        async with self._uow:
            user = await self._uow.users.get(user_id)
        if user is None:
            raise UnauthorizedError("Invalid or expired token")
        return user

    async def _issue(self, user: User) -> TokenPair:
        auth = settings.auth
        access = issue_token(user.id, "access", auth.access_ttl, role=user.role)
        refresh = issue_token(user.id, "refresh", auth.refresh_ttl)
        await self._redis.set(
            _refresh_key(refresh.jti), str(user.id), ex=auth.refresh_ttl
        )
        return TokenPair(access=access, refresh=refresh)
