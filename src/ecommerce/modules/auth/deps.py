from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ecommerce.core.exceptions.base import ForbiddenError, UnauthorizedError
from ecommerce.core.security.tokens import decode_token
from ecommerce.modules.auth.models import Role
from ecommerce.modules.auth.permissions import ROLE_PERMISSIONS, Permission

# auto_error=False so a missing header goes through our 401 problem+json handler.
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    id: UUID
    role: Role

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    claims = decode_token(credentials.credentials, "access")
    try:
        return Principal(id=UUID(claims["sub"]), role=Role(claims["role"]))
    except KeyError, ValueError:
        raise UnauthorizedError("Invalid or expired token") from None


CurrentUser = Annotated[Principal, Depends(get_current_user)]


def requires(*permissions: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    async def check(principal: CurrentUser) -> Principal:
        missing = [p.value for p in permissions if p not in principal.permissions]
        if missing:
            raise ForbiddenError(
                f"Missing permissions: {', '.join(missing)}", missing=missing
            )
        return principal

    return check
