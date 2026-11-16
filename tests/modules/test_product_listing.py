from typing import Any

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce.modules.products.models import Product, ProductVariant
from tests.modules.catalog import ADMIN_PRODUCTS, PRODUCTS, Json, post, variant


class Shop:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.ids: dict[str, str] = {}
        self.refs: dict[str, str] = {}

    async def ref(self, kind: str, name: str, parent: str | None = None) -> str:
        body: Json = {"name": name}
        if parent:
            body["parent_id"] = self.refs[parent]
        self.refs[name] = (await post(self.client, f"/api/v1/admin/{kind}", body))["id"]
        return self.refs[name]

    async def product(
        self, name: str, category: str, *variants: Json, **fields: Any
    ) -> str:
        body = {"name": name, "category_id": self.refs[category], **fields}
        product_id: str = (await post(self.client, ADMIN_PRODUCTS, body))["id"]
        if variants:
            await post(self.client, f"{ADMIN_PRODUCTS}/{product_id}/variants", variants)
        self.ids[name] = product_id
        return product_id

    async def names(self, **params: Any) -> list[str]:
        by_id = {v: k for k, v in self.ids.items()}
        return [by_id[item["id"]] for item in (await self.list(**params))["items"]]

    async def list(self, **params: Any) -> Json:
        response = await self.client.get(PRODUCTS, params=params)
        assert response.status_code == 200, response.text
        data: Json = response.json()
        return data


@pytest.fixture
async def shop(client: AsyncClient) -> Shop:
    shop = Shop(client)
    await shop.ref("categories", "Shoes")
    await shop.ref("categories", "Running", parent="Shoes")
    await shop.ref("categories", "Hats")
    acme = await shop.ref("brands", "Acme")
    await shop.product(
        "Road",
        "Running",
        variant("R-42", 5000, size="42", color="red"),
        variant("R-43", 7000, size="43", color="blue"),
        brand_id=acme,
    )
    await shop.product(
        "Trail", "Shoes", variant("T-42", 3000, size="42", color="blue"), brand_id=acme
    )
    await shop.product("Cap", "Hats", variant("C-M", 1000, size="M"))
    await shop.product("Hidden", "Shoes", variant("H-1", 100), is_active=False)
    await shop.product("Empty", "Shoes")
    return shop


async def test_lists_active_products_with_variants_newest_first(shop: Shop) -> None:
    page = await shop.list()

    assert await shop.names() == ["Cap", "Trail", "Road"]
    assert (page["total"], page["next_cursor"]) == (3, None)
    assert page["items"][2] == {
        "id": shop.ids["Road"],
        "name": "Road",
        "slug": "road",
        "brand_id": shop.refs["Acme"],
        "category_id": shop.refs["Running"],
        "price": 5000,
    }


async def test_category_includes_descendants(shop: Shop) -> None:
    assert await shop.names(category_id=shop.refs["Shoes"]) == ["Trail", "Road"]
    assert await shop.names(category_id=shop.refs["Running"]) == ["Road"]


async def test_brand_filter(shop: Shop) -> None:
    assert await shop.names(brand_id=shop.refs["Acme"]) == ["Trail", "Road"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"min_price": 4000}, ["Road"]),
        ({"min_price": 6000}, []),
        ({"max_price": 3000}, ["Cap", "Trail"]),
        ({"min_price": 1000, "max_price": 1000}, ["Cap"]),
    ],
)
async def test_price_range_applies_to_the_lowest_price(
    shop: Shop, params: Json, expected: list[str]
) -> None:
    assert await shop.names(**params) == expected


async def test_options_must_match_on_one_variant(shop: Shop) -> None:
    both = await shop.names(option=["size:42", "color:blue"])
    size_43 = await shop.list(option="size:43")

    assert both == ["Trail"]
    assert [(i["name"], i["price"]) for i in size_43["items"]] == [("Road", 7000)]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [("price_asc", ["Cap", "Trail", "Road"]), ("price_desc", ["Road", "Trail", "Cap"])],
)
async def test_price_sorts(shop: Shop, sort: str, expected: list[str]) -> None:
    assert await shop.names(sort=sort) == expected


@pytest.mark.parametrize("sort", ["newest", "price_asc", "price_desc"])
async def test_keyset_walk_visits_every_product_once(
    client: AsyncClient, sort: str
) -> None:
    shop = Shop(client)
    await shop.ref("categories", "All")
    for i, price in enumerate([200, 100, 200, 100, 300, 100]):
        await shop.product(f"p{i}", "All", variant(f"S{i}", price))
    full = await shop.names(sort=sort, limit=100)

    seen: list[str] = []
    cursor = None
    while True:
        page = await shop.list(
            sort=sort, limit=2, **({"cursor": cursor} if cursor else {})
        )
        seen += [item["name"] for item in page["items"]]
        if not (cursor := page["next_cursor"]):
            break

    assert seen == full
    assert len(full) == 6


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-a-cursor"},
        {"option": ["size:M", "size:L"]},
        {"option": "size"},
        {"min_price": 5, "max_price": 4},
        {"min_price": -1},
        {"sort": "name"},
    ],
    ids=[
        "bad cursor",
        "repeated option",
        "option without value",
        "min > max",
        "negative price",
        "unknown sort",
    ],
)
async def test_invalid_query_is_422(client: AsyncClient, params: Json) -> None:
    response = await client.get(PRODUCTS, params=params)

    assert response.status_code == 422


async def test_cursor_of_another_sort_is_422(shop: Shop) -> None:
    cursor = (await shop.list(sort="price_asc", limit=1))["next_cursor"]

    response = await shop.client.get(PRODUCTS, params={"cursor": cursor})

    assert response.status_code == 422


async def test_total_is_cached_until_a_catalog_write(
    shop: Shop, db_session: AsyncSession
) -> None:
    await shop.list()
    # Written around the service, so nothing bumps the catalog version.
    sneaked = Product(name="Sneaked", slug="sneaked", category_id=shop.refs["Hats"])
    db_session.add(sneaked)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=sneaked.id, sku="SN", price=1, options={}))
    await db_session.flush()

    cached = await shop.list()
    await shop.product("Bumped", "Hats", variant("B", 1))
    fresh = await shop.list()

    assert (len(cached["items"]), cached["total"]) == (4, 3)
    assert fresh["total"] == 5
