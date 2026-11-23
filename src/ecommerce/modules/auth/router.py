from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from ecommerce.config.settings import settings
from ecommerce.core.exceptions.base import UnauthorizedError
from ecommerce.core.redis import RedisClient
from ecommerce.core.security.tokens import Token
from ecommerce.modules.auth.deps import CurrentUser
from ecommerce.modules.auth.models import User
from ecommerce.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from ecommerce.modules.auth.service import AuthService
from ecommerce.uow import UoW

REFRESH_COOKIE = "refresh_token"
# Scoped to the auth routes so the refresh token never rides along on other requests.
REFRESH_COOKIE_PATH = "/api/v1/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def get_service(uow: UoW, redis: RedisClient) -> AuthService:
    return AuthService(uow, redis)


Service = Annotated[AuthService, Depends(get_service)]

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: Token) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token.value,
        max_age=token.expires_in,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth.cookie_secure,
        httponly=True,
        samesite="strict",
    )


users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("/me")
async def me(service: Service, principal: CurrentUser) -> UserRead:
    # Stateless token: is_active is not rechecked, a ban applies at the next refresh.
    return UserRead.model_validate(await service.get_user(principal.id))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(service: Service, payload: RegisterRequest) -> User:
    return await service.register(payload)


@router.post("/login")
async def login(
    service: Service, payload: LoginRequest, response: Response
) -> TokenResponse:
    pair = await service.login(payload)
    _set_refresh_cookie(response, pair.refresh)
    return TokenResponse(
        access_token=pair.access.value, expires_in=pair.access.expires_in
    )


@router.post("/refresh")
async def refresh(
    service: Service, response: Response, refresh_token: RefreshCookie = None
) -> TokenResponse:
    if refresh_token is None:
        raise UnauthorizedError("Missing refresh token")
    pair = await service.refresh(refresh_token)
    _set_refresh_cookie(response, pair.refresh)
    return TokenResponse(
        access_token=pair.access.value, expires_in=pair.access.expires_in
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    service: Service, response: Response, refresh_token: RefreshCookie = None
) -> None:
    await service.logout(refresh_token)
    # Same path and flags as the set cookie, or browsers keep the original.
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.auth.cookie_secure,
        httponly=True,
        samesite="strict",
    )
