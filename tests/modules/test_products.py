from typing import Any
import uuid

from httpx import AsyncClient
import pytest

PRODUCTS = "/api/v1/products"
ADMIN = "/api/v1/admin/products"
VARIANTS = "/api/v1/admin/variants"

type Json = dict[str, Any]


async def post(client: AsyncClient, url: str, body: Any) -> Any:
    response = await client.post(url, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def brand(client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/brands", {"name": "Acme"})
    return data


@pytest.fixture
async def category(client: AsyncClient) -> Json:
    data: Json = await post(client, "/api/v1/admin/categories", {"name": "Shoes"})
    return data


@pytest.fixture
async def product(client: AsyncClient, brand: Json, category: Json) -> Json:
    body = {
        "name": "Trail Runner",
        "brand_id": brand["id"],
        "category_id": category["id"],
    }
    data: Json = await post(client, ADMIN, body)
    return data


def variant(sku: str, price: int = 1000, **options: str) -> Json:
    return {"sku": sku, "price": price, "stock": 5, "options": options}


async def test_create_product_derives_slug(product: Json, brand: Json) -> None:
    assert product["slug"] == "trail-runner"
    assert product["brand_id"] == brand["id"]
    assert product["is_active"] is True
    assert product["description"] == ""


@pytest.mark.parametrize("field", ["brand_id", "category_id"])
async def test_unknown_reference_is_422(
    client: AsyncClient, brand: Json, category: Json, field: str
) -> None:
    body = {"name": "x", "brand_id": brand["id"], "category_id": category["id"]}
    body[field] = str(uuid.uuid7())

    response = await client.post(ADMIN, json=body)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


async def test_product_without_brand(client: AsyncClient, category: Json) -> None:
    created = await post(client, ADMIN, {"name": "Plain", "category_id": category["id"]})

    assert created["brand_id"] is None


async def test_add_variants_in_order(client: AsyncClient, product: Json) -> None:
    body = [variant("TR-42", size="42"), variant("TR-43", 1200, size="43")]

    created = await post(client, f"{ADMIN}/{product['id']}/variants", body)

    assert [v["sku"] for v in created] == ["TR-42", "TR-43"]
    assert created[1] | {"id": None} == {
        "id": None,
        "product_id": product["id"],
        "sku": "TR-43",
        "price": 1200,
        "stock": 5,
        "options": {"size": "43"},
    }


async def test_variants_for_missing_product_is_404(client: AsyncClient) -> None:
    response = await client.post(f"{ADMIN}/{uuid.uuid7()}/variants", json=[variant("A")])

    assert response.status_code == 404


@pytest.mark.parametrize(
    "second",
    [variant("TR-1", size="43"), variant("TR-2", size="42")],
    ids=["duplicate sku", "duplicate options"],
)
async def test_duplicate_variant_is_409(
    client: AsyncClient, product: Json, second: Json
) -> None:
    url = f"{ADMIN}/{product['id']}/variants"
    await post(client, url, [variant("TR-1", size="42")])

    response = await client.post(url, json=[second])

    assert response.status_code == 409


@pytest.mark.parametrize(
    "bad",
    [
        variant("A", price=-1),
        {"sku": "A", "price": 1, "stock": -1},
        {"sku": " ", "price": 1},
        {"sku": "A", "price": 1, "options": {"": "x"}},
    ],
    ids=["negative price", "negative stock", "blank sku", "empty option name"],
)
async def test_invalid_variant_is_422(
    client: AsyncClient, product: Json, bad: Json
) -> None:
    response = await client.post(f"{ADMIN}/{product['id']}/variants", json=[bad])

    assert response.status_code == 422


async def test_patch_and_delete_variant(client: AsyncClient, product: Json) -> None:
    [created] = await post(client, f"{ADMIN}/{product['id']}/variants", [variant("A")])

    patched = await client.patch(f"{VARIANTS}/{created['id']}", json={"price": 1500})
    deleted = await client.delete(f"{VARIANTS}/{created['id']}")
    detail = (await client.get(f"{PRODUCTS}/{product['id']}")).json()

    assert (patched.status_code, patched.json()["price"]) == (200, 1500)
    assert deleted.status_code == 204
    assert detail["variants"] == []


async def test_detail_lists_variants(client: AsyncClient, product: Json) -> None:
    await post(
        client,
        f"{ADMIN}/{product['id']}/variants",
        [variant("A"), variant("B", size="M")],
    )

    detail = (await client.get(f"{PRODUCTS}/{product['id']}")).json()

    assert detail["name"] == "Trail Runner"
    assert sorted(v["sku"] for v in detail["variants"]) == ["A", "B"]


async def test_inactive_product_is_hidden(client: AsyncClient, product: Json) -> None:
    await client.patch(f"{ADMIN}/{product['id']}", json={"is_active": False})

    response = await client.get(f"{PRODUCTS}/{product['id']}")

    assert response.status_code == 404


async def test_delete_product_removes_variants(
    client: AsyncClient, product: Json
) -> None:
    [created] = await post(client, f"{ADMIN}/{product['id']}/variants", [variant("A")])

    deleted = await client.delete(f"{ADMIN}/{product['id']}")
    orphan = await client.patch(f"{VARIANTS}/{created['id']}", json={"price": 1})

    assert (deleted.status_code, orphan.status_code) == (204, 404)


@pytest.mark.parametrize("owner", ["brands", "categories"])
async def test_referenced_brand_or_category_cannot_be_deleted(
    client: AsyncClient, product: Json, owner: str
) -> None:
    owner_id = product["brand_id" if owner == "brands" else "category_id"]

    response = await client.delete(f"/api/v1/admin/{owner}/{owner_id}")

    assert response.status_code == 409
