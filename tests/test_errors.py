from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from ecommerce.core.exceptions.base import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from ecommerce.main import create_app

app = create_app()


@app.get("/missing")
async def missing() -> None:
    raise NotFoundError("Item 1 not found")


@app.get("/boom")
async def boom() -> None:
    raise RuntimeError("secret internals")


@app.get("/unauthorized")
async def unauthorized() -> None:
    raise UnauthorizedError


@app.get("/forbidden")
async def forbidden() -> None:
    raise ForbiddenError


@app.get("/redis-down")
async def redis_down() -> None:
    raise RedisConnectionError("redis://secret-host")


@app.get("/typed")
async def typed(limit: int) -> int:
    return limit


client = TestClient(app, raise_server_exceptions=False)


def test_app_error_is_a_problem_response() -> None:
    response = client.get("/missing", headers={"X-Request-ID": "r1"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "Item 1 not found",
        "instance": "/missing",
        "request_id": "r1",
    }


def test_validation_error_lists_fields() -> None:
    response = client.get("/typed", params={"limit": "x"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["query.limit"]


def test_unknown_route_is_a_problem_response() -> None:
    response = client.get("/nowhere")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "not-found"


def test_http_error_keeps_headers() -> None:
    response = client.post("/missing")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


def test_unexpected_error_hides_details() -> None:
    response = client.get("/boom", headers={"X-Request-ID": "r2"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "r2"
    assert response.json()["detail"] == "Internal Server Error"
    assert response.json()["request_id"] == "r2"


def test_unauthorized_sets_www_authenticate() -> None:
    response = client.get("/unauthorized")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["title"] == "Unauthorized"


def test_forbidden_is_403() -> None:
    assert client.get("/forbidden").status_code == 403


def test_redis_error_is_service_unavailable() -> None:
    response = client.get("/redis-down")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Service Unavailable"
