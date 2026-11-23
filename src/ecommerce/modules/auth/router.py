from typing import Annotated

from fastapi import APIRouter, Depends, status

from ecommerce.core.redis import RedisClient
from ecommerce.modules.auth.models import User
from ecommerce.modules.auth.schemas import RegisterRequest, UserRead
from ecommerce.modules.auth.service import AuthService
from ecommerce.uow import UoW


def get_service(uow: UoW, redis: RedisClient) -> AuthService:
    return AuthService(uow, redis)


Service = Annotated[AuthService, Depends(get_service)]

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(service: Service, payload: RegisterRequest) -> User:
    return await service.register(payload)
