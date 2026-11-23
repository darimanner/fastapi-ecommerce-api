from typing import Protocol

from redis.asyncio import Redis

from ecommerce.core.security.passwords import hash_password
from ecommerce.interfaces.repository import Repository
from ecommerce.interfaces.unit_of_work import UnitOfWork
from ecommerce.modules.auth.models import Role, User
from ecommerce.modules.auth.schemas import RegisterRequest


class Users(Repository[User], Protocol):
    async def get_by_email(self, email: str) -> User | None: ...


class AuthUnitOfWork(UnitOfWork, Protocol):
    # Read-only, so the app UoW may declare the concrete repository type.
    @property
    def users(self) -> Users: ...


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
