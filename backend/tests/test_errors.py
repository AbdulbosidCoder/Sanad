from app.core.errors import AppError
from app.core.modules import module_router


async def test_request_id_is_generated_and_returned(client):
    r = await client.get("/health/live")
    assert len(r.headers["X-Request-Id"]) == 32


async def test_incoming_request_id_is_kept(client):
    r = await client.get("/health/live", headers={"X-Request-Id": "abc123"})
    assert r.headers["X-Request-Id"] == "abc123"


async def test_not_found_is_problem_json(client):
    r = await client.get("/api/v1/nope", headers={"X-Request-Id": "rid-404"})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["request_id"] == "rid-404"


async def test_business_error_names_module_and_code(app, client):
    router = module_router("orders")

    @router.get("/_test/out-of-stock")
    async def boom() -> None:
        raise AppError("orders", "OUT_OF_STOCK", "Not enough stock", status=409)

    app.include_router(router, prefix="/api/v1")
    r = await client.get("/api/v1/_test/out-of-stock")
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "ORDERS.OUT_OF_STOCK"
    assert body["module"] == "orders"
    assert body["request_id"] == r.headers["X-Request-Id"]


async def test_unhandled_error_is_500_with_module(app, client):
    router = module_router("payments")

    @router.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("provider exploded")

    app.include_router(router, prefix="/api/v1")
    r = await client.get("/api/v1/_test/crash")
    assert r.status_code == 500
    body = r.json()
    assert body["module"] == "payments"
    assert body["code"] == "PAYMENTS.INTERNAL_ERROR"
    assert "provider exploded" not in r.text  # internals never leak to clients


async def test_validation_error_names_module(app, client):
    router = module_router("catalog")

    @router.get("/_test/products/{product_id}")
    async def get_product(product_id: int) -> dict[str, int]:
        return {"id": product_id}

    app.include_router(router, prefix="/api/v1")
    r = await client.get("/api/v1/_test/products/not-a-number")
    assert r.status_code == 422
    assert r.json()["module"] == "catalog"
    assert r.json()["code"] == "CATALOG.VALIDATION_ERROR"
