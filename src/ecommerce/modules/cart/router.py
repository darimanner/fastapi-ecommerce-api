from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from ecommerce.modules.auth.deps import CurrentUser, requires
from ecommerce.modules.auth.permissions import Permission
from ecommerce.modules.cart.schemas import CartItemAdd, CartItemUpdate, CartRead
from ecommerce.modules.cart.service import CartService
from ecommerce.uow import UoW


def get_cart(uow: UoW) -> CartService:
    return CartService(uow)


Cart = Annotated[CartService, Depends(get_cart)]

router = APIRouter(
    prefix="/cart",
    tags=["cart"],
    dependencies=[Depends(requires(Permission.CART_MANAGE))],
)


@router.get("")
async def read_cart(service: Cart, user: CurrentUser) -> CartRead:
    return await service.get(user.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cart(service: Cart, user: CurrentUser) -> None:
    await service.clear(user.id)


@router.post("/items")
async def add_item(service: Cart, user: CurrentUser, payload: CartItemAdd) -> CartRead:
    return await service.add(user.id, payload)


@router.patch("/items/{variant_id}")
async def set_item_quantity(
    service: Cart, user: CurrentUser, variant_id: UUID, payload: CartItemUpdate
) -> CartRead:
    return await service.set_quantity(user.id, variant_id, payload)


@router.delete("/items/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(service: Cart, user: CurrentUser, variant_id: UUID) -> None:
    await service.remove(user.id, variant_id)
