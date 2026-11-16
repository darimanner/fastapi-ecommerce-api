from typing import Any

from httpx import AsyncClient

PRODUCTS = "/api/v1/products"
ADMIN_PRODUCTS = "/api/v1/admin/products"

type Json = dict[str, Any]


async def post(client: AsyncClient, url: str, body: Any) -> Any:
    response = await client.post(url, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def variant(sku: str, price: int = 1000, **options: str) -> Json:
    return {"sku": sku, "price": price, "stock": 5, "options": options}
