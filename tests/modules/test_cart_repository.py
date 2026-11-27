from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce.modules.auth.models import User
from ecommerce.modules.brands.models import Brand
from ecommerce.modules.cart.models import Cart, CartItem
from ecommerce.modules.cart.repository import CartRepository
from ecommerce.modules.categories.models import Category
from ecommerce.modules.products.models import Product, ProductVariant


async def _user(session: AsyncSession) -> UUID:
    user = User(email=f"{uuid7()}@example.com", password_hash="x")  # noqa: S106
    session.add(user)
    await session.flush()
    return user.id


async def _variant(
    session: AsyncSession, *, name: str = "Shirt", stock: int = 10, active: bool = True
) -> ProductVariant:
    suffix = uuid7().hex
    category = Category(name="c", slug=f"c-{suffix}")
    brand = Brand(name="b", slug=f"b-{suffix}")
    session.add_all([category, brand])
    await session.flush()
    product = Product(
        name=name,
        slug=f"p-{suffix}",
        category_id=category.id,
        brand_id=brand.id,
        is_active=active,
    )
    session.add(product)
    await session.flush()
    variant = ProductVariant(
        product_id=product.id,
        sku=f"sku-{suffix}",
        price=1500,
        stock=stock,
        options={"size": "M"},
    )
    session.add(variant)
    await session.flush()
    return variant


async def test_ensure_is_idempotent(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    user_id = await _user(db_session)

    first = await repo.ensure(user_id)
    second = await repo.ensure(user_id)

    assert first == second == await repo.find(user_id)
    count = await db_session.scalar(
        select(func.count()).select_from(Cart).where(Cart.user_id == user_id)
    )
    assert count == 1


async def test_find_unknown_user(db_session: AsyncSession) -> None:
    assert await CartRepository(db_session).find(uuid7()) is None


async def test_add_quantity_accumulates(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    variant = await _variant(db_session)

    assert await repo.add_quantity(cart_id, variant.id, 2) == 2
    assert await repo.add_quantity(cart_id, variant.id, 3) == 5


async def test_re_adding_a_line_bumps_updated_at(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    variant = await _variant(db_session)
    await repo.add_quantity(cart_id, variant.id, 1)
    # now() is constant inside the test transaction, so age the row explicitly.
    old = datetime(2020, 1, 1, tzinfo=UTC)
    await db_session.execute(update(CartItem).values(updated_at=old))

    await repo.add_quantity(cart_id, variant.id, 1)

    stamp = await db_session.scalar(
        select(CartItem.updated_at).where(CartItem.cart_id == cart_id)
    )
    assert stamp is not None
    assert stamp > old


async def test_set_quantity(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    variant = await _variant(db_session)

    assert await repo.set_quantity(cart_id, variant.id, 4) is False
    await repo.add_quantity(cart_id, variant.id, 1)
    assert await repo.set_quantity(cart_id, variant.id, 4) is True
    assert (await repo.lines(cart_id))[0].quantity == 4


async def test_lines_joined_in_insertion_order(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    first = await _variant(db_session, name="First", stock=3)
    second = await _variant(db_session, name="Second", active=False)
    await repo.add_quantity(cart_id, first.id, 2)
    await repo.add_quantity(cart_id, second.id, 1)

    rows = await repo.lines(cart_id)

    assert [r.variant_id for r in rows] == [first.id, second.id]
    one = rows[0]
    assert one.product_id == first.product_id
    assert (one.name, one.sku, one.options) == ("First", first.sku, {"size": "M"})
    assert (one.unit_price, one.quantity, one.stock, one.is_active) == (1500, 2, 3, True)
    assert rows[1].is_active is False


async def test_remove_and_clear(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    first, second = await _variant(db_session), await _variant(db_session)
    await repo.add_quantity(cart_id, first.id, 1)
    await repo.add_quantity(cart_id, second.id, 1)

    await repo.remove(cart_id, first.id)
    assert [r.variant_id for r in await repo.lines(cart_id)] == [second.id]
    await repo.clear(cart_id)
    assert await repo.lines(cart_id) == []


async def test_deleting_variant_removes_line(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    cart_id = await repo.ensure(await _user(db_session))
    variant = await _variant(db_session)
    await repo.add_quantity(cart_id, variant.id, 1)

    await db_session.execute(
        delete(ProductVariant).where(ProductVariant.id == variant.id)
    )

    assert await repo.lines(cart_id) == []


async def test_variant_stock_and_activity(db_session: AsyncSession) -> None:
    repo = CartRepository(db_session)
    active = await _variant(db_session, stock=7)
    inactive = await _variant(db_session, active=False)

    found = await repo.variant(active.id)
    assert found is not None
    assert (found.stock, found.is_active) == (7, True)
    hidden = await repo.variant(inactive.id)
    assert hidden is not None
    assert hidden.is_active is False
    assert await repo.variant(uuid7()) is None
