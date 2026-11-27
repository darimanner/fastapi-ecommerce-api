from typing import Protocol
from uuid import UUID

from ecommerce.core.exceptions.base import ConflictError, NotFoundError
from ecommerce.interfaces.unit_of_work import UnitOfWork
from ecommerce.modules.cart.repository import CartRepository, Stock
from ecommerce.modules.cart.schemas import (
    CartItemAdd,
    CartItemUpdate,
    CartRead,
    cart_lines,
)


class CartUnitOfWork(UnitOfWork, Protocol):
    # Read-only, so the app UoW may declare the concrete repository type.
    @property
    def carts(self) -> CartRepository: ...


def _over_stock(stock: int) -> ConflictError:
    return ConflictError(f"Only {stock} left", stock=stock)


class CartService:
    def __init__(self, uow: CartUnitOfWork) -> None:
        self._uow = uow

    async def get(self, user_id: UUID) -> CartRead:
        async with self._uow as uow:
            return await self._read(uow, await uow.carts.find(user_id))

    async def add(self, user_id: UUID, payload: CartItemAdd) -> CartRead:
        async with self._uow as uow:
            stock = await self._orderable(uow, payload.variant_id)
            cart_id = await uow.carts.ensure(user_id)
            total = await uow.carts.add_quantity(
                cart_id, payload.variant_id, payload.quantity
            )
            # Soft check: raised before commit, so the upsert is rolled back.
            if total > stock.stock:
                raise _over_stock(stock.stock)
            await uow.commit()
            return await self._read(uow, cart_id)

    async def set_quantity(
        self, user_id: UUID, variant_id: UUID, payload: CartItemUpdate
    ) -> CartRead:
        async with self._uow as uow:
            stock = await self._orderable(uow, variant_id)
            cart_id = await uow.carts.find(user_id)
            if cart_id is None or not await uow.carts.set_quantity(
                cart_id, variant_id, payload.quantity
            ):
                raise NotFoundError("Item not in cart")
            if payload.quantity > stock.stock:
                raise _over_stock(stock.stock)
            await uow.commit()
            return await self._read(uow, cart_id)

    async def remove(self, user_id: UUID, variant_id: UUID) -> None:
        async with self._uow as uow:
            if (cart_id := await uow.carts.find(user_id)) is not None:
                await uow.carts.remove(cart_id, variant_id)
                await uow.commit()

    async def clear(self, user_id: UUID) -> None:
        async with self._uow as uow:
            if (cart_id := await uow.carts.find(user_id)) is not None:
                await uow.carts.clear(cart_id)
                await uow.commit()

    @staticmethod
    async def _orderable(uow: CartUnitOfWork, variant_id: UUID) -> Stock:
        # The stock read the soft check needs; inactive products are hidden as 404.
        stock = await uow.carts.variant(variant_id)
        if stock is None or not stock.is_active:
            raise NotFoundError("Variant not found")
        return stock

    @staticmethod
    async def _read(uow: CartUnitOfWork, cart_id: UUID | None) -> CartRead:
        rows = [] if cart_id is None else await uow.carts.lines(cart_id)
        return CartRead(items=cart_lines.validate_python(rows, from_attributes=True))
