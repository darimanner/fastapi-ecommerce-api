from typing import Any

from httpx import AsyncClient

BRANDS = "/api/v1/brands"
ADMIN = "/api/v1/admin/brands"


async def create(client: AsyncClient, **body: object) -> dict[str, Any]:
    response = await client.post(ADMIN, json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def test_create_derives_slug(client: AsyncClient) -> None:
    brand = await create(client, name="North Face")

    assert brand["slug"] == "north-face"
    assert brand["id"]
    assert brand["created_at"]


async def test_list_and_get(client: AsyncClient) -> None:
    brand = await create(client, name="Acme")

    page = (await client.get(BRANDS)).json()
    fetched = (await client.get(f"{BRANDS}/{brand['id']}")).json()

    assert [b["id"] for b in page["items"]] == [brand["id"]]
    assert page["has_next"] is False
    assert fetched == brand


async def test_patch_keeps_slug(client: AsyncClient) -> None:
    brand = await create(client, name="Acme")

    response = await client.patch(f"{ADMIN}/{brand['id']}", json={"name": "Acme Inc"})

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["slug"]) == ("Acme Inc", "acme")


async def test_put_rederives_slug(client: AsyncClient) -> None:
    brand = await create(client, name="Acme")

    response = await client.put(f"{ADMIN}/{brand['id']}", json={"name": "Acme Inc"})

    assert response.json()["slug"] == "acme-inc"


async def test_duplicate_slug_is_409(client: AsyncClient) -> None:
    await create(client, name="Acme")

    response = await client.post(ADMIN, json={"name": "ACME"})

    assert response.status_code == 409
    assert response.json()["errors"][0]["field"] == "slug"


async def test_unknown_brand_is_404(client: AsyncClient) -> None:
    response = await client.get(f"{BRANDS}/019a0000-0000-7000-8000-000000000000")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


async def test_delete(client: AsyncClient) -> None:
    brand = await create(client, name="Acme")

    deleted = await client.delete(f"{ADMIN}/{brand['id']}")
    after = await client.get(f"{BRANDS}/{brand['id']}")

    assert (deleted.status_code, after.status_code) == (204, 404)


async def test_invalid_limit_is_422(client: AsyncClient) -> None:
    response = await client.get(BRANDS, params={"limit": 0})

    assert response.status_code == 422
