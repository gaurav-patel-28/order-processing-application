import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select, update

from app.config import settings
from app.models import Order, OrderEvent, PaymentAttempt, Product, Refund, User
from app.providers import SimulatedProvider, sign
from app.schemas import OrderCreate, Webhook
from app.services import create_order, process_webhook

pytestmark = pytest.mark.integration


def signed_event(client, auth, order, outcome="success", event_id=None):
    response = client.post(f"/orders/{order['id']}/payment-attempts", headers=auth())
    assert response.status_code == 200
    attempt = response.json()
    body = SimulatedProvider().event(attempt["provider_id"], outcome, attempt["amount_cents"])
    if event_id:
        payload = json.loads(body)
        payload["id"] = event_id
        body = json.dumps(payload).encode()
    return body, {"X-Payment-Signature": sign(body, settings().webhook_secret)}


def test_persist_catalog_and_permissions(client, auth, database):
    data = {"sku": "NEW", "name": "Travel journal", "price_cents": 1234, "available": 7}
    response = client.post("/products", json=data, headers=auth("admin-a"))
    assert response.status_code == 201
    product = response.json()
    assert product["org_id"] == "a"
    with database() as db:
        assert db.get(Product, product["id"]).price_cents == 1234
    assert (
        client.patch(
            f"/inventory/{product['id']}", json={"available": 8}, headers=auth("staff-a")
        ).status_code
        == 403
    )
    assert client.post("/products", json=data, headers=auth()).status_code == 403
    assert (
        client.patch(f"/products/{product['id']}", json={"name": "Leak"}, headers=auth("staff-b")).status_code
        == 404
    )
    assert (
        client.patch(
            f"/products/{product['id']}", json={"price_cents": -1}, headers=auth("admin-a")
        ).status_code
        == 422
    )
    assert (
        client.patch(f"/products/{product['id']}", json={"name": None}, headers=auth("admin-a")).status_code
        == 422
    )
    listed = client.get("/products", headers=auth("customer-b")).json()
    assert all(p["org_id"] == "b" for p in listed)
    assert client.get("/products").status_code == 401
    assert (
        client.post("/auth/login", json={"email": "unknown@test.local", "password": "bad"}).status_code == 401
    )


def test_order_snapshot_and_idempotency(client, auth, make_order, database):
    order = make_order(quantity=2)
    again = make_order(quantity=2)
    assert again["id"] == order["id"]
    assert order["subtotal_cents"] == 2002
    assert order["tax_cents"] == 165
    assert order["total_cents"] == 2167
    client.patch("/products/product-a", headers=auth("admin-a"), json={"price_cents": 9000})
    detail = client.get(f"/orders/{order['id']}", headers=auth()).json()
    assert detail["lines"][0]["unit_price_cents"] == 1001
    response = client.post(
        "/orders",
        headers={**auth(), "Idempotency-Key": "checkout"},
        json={"items": [{"product_id": "product-a", "quantity": 1}]},
    )
    assert response.status_code == 409
    with database() as db:
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (3, 2, 0)
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.scalar(select(func.count()).select_from(PaymentAttempt)) == 1


def test_duplicate_webhook(client, auth, make_order, database):
    order = make_order(quantity=2)
    body, headers = signed_event(client, auth, order)
    for _ in range(2):
        response = client.post("/webhooks/payments", content=body, headers=headers)
        assert response.status_code == 200, response.text
    with database() as db:
        assert db.get(Order, order["id"]).status == "PAID"
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (3, 0, 2)
        assert (
            db.scalar(
                select(func.count())
                .select_from(OrderEvent)
                .where(OrderEvent.order_id == order["id"], OrderEvent.kind == "PAID")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(OrderEvent)) == 2


def test_tenant_order_isolation(client, auth, make_order):
    foreign = make_order(user="customer-b", product="product-b")
    assert client.get(f"/orders/{foreign['id']}", headers=auth("staff-b")).status_code == 200
    assert client.get(f"/orders/{foreign['id']}", headers=auth("staff-a")).status_code in {403, 404}
    for suffix in ["events"]:
        assert client.get(f"/orders/{foreign['id']}/{suffix}", headers=auth("staff-a")).status_code == 404
    for action in ["cancel", "refund", "fulfill", "payment-attempts"]:
        assert client.post(f"/orders/{foreign['id']}/{action}", headers=auth("staff-a")).status_code == 404
    own = make_order()
    assert client.get(f"/orders/{own['id']}", headers=auth("other-a")).status_code == 404
    assert client.get("/orders", headers=auth("other-a")).json() == []


def test_payment_failure_and_invalid_signature(client, auth, make_order, database):
    order = make_order()
    body, headers = signed_event(client, auth, order, "failure")
    assert (
        client.post("/webhooks/payments", content=body, headers={"X-Payment-Signature": "bad"}).status_code
        == 401
    )
    assert client.post("/webhooks/payments", content=body, headers=headers).status_code == 200
    assert client.post(f"/orders/{order['id']}/fulfill", headers=auth("staff-a")).status_code == 409
    with database() as db:
        assert db.get(Order, order["id"]).status == "PAYMENT_FAILED"
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (5, 0, 0)


def test_cancel_and_delayed_success(client, auth, make_order, database):
    order = make_order()
    body, headers = signed_event(client, auth, order)
    for _ in range(2):
        response = client.post(f"/orders/{order['id']}/cancel", headers=auth())
        assert response.status_code == 200
    assert client.post("/webhooks/payments", content=body, headers=headers).json()["status"] == "ignored"
    assert client.post(f"/orders/{order['id']}/refund", headers=auth("staff-a")).status_code == 409
    with database() as db:
        assert db.get(Order, order["id"]).status == "CANCELED"
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (5, 0, 0)


def test_refund_fulfillment_and_late_failure(client, auth, make_order, database):
    order = make_order()
    assert client.post(f"/orders/{order['id']}/fulfill", headers=auth("staff-a")).status_code == 409
    body, headers = signed_event(client, auth, order)
    assert client.post("/webhooks/payments", content=body, headers=headers).status_code == 200
    late, late_headers = signed_event(client, auth, order, "failure")
    assert client.post("/webhooks/payments", content=late, headers=late_headers).json()["status"] == "ignored"
    assert client.get(f"/orders/{order['id']}", headers=auth()).json()["status"] == "PAID"
    assert client.post(f"/orders/{order['id']}/fulfill", headers=auth()).status_code == 403
    assert (
        client.post(f"/orders/{order['id']}/fulfill", headers=auth("staff-a")).json()["status"] == "FULFILLED"
    )
    for _ in range(2):
        response = client.post(f"/orders/{order['id']}/refund", headers=auth("staff-a"))
        assert response.status_code == 200
        assert response.json()["amount_cents"] == order["total_cents"]
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Refund)) == 1
        assert db.get(Order, order["id"]).status == "REFUNDED"
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (4, 0, 1)


def test_last_unit_contention(database, pg_engine):
    with database.begin() as db:
        db.execute(update(Product).where(Product.id == "product-a").values(available=1))
    barrier = Barrier(2)

    def coordinate(conn, cursor, statement, parameters, context, executemany):
        # Both real transactions reach their inventory UPDATE before either executes it.
        if statement.lstrip().startswith("UPDATE products SET"):
            barrier.wait(timeout=10)

    event.listen(pg_engine, "before_cursor_execute", coordinate)

    def checkout(user_id):
        try:
            with database.begin() as db:
                user = db.get(User, user_id)
                order = create_order(
                    db, user, OrderCreate(items=[{"product_id": "product-a", "quantity": 1}]), user_id
                )
                return order.id
        except HTTPException as exc:
            assert exc.status_code == 409
            return None

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(checkout, ["customer-a", "other-a"]))
    finally:
        event.remove(pg_engine, "before_cursor_execute", coordinate)
    assert sum(result is not None for result in results) == 1
    with database() as db:
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (0, 1, 0)
        assert db.scalar(select(func.count()).select_from(Order)) == 1


def test_rollback_multi_item_order(client, auth, database):
    response = client.post(
        "/orders",
        headers={**auth(), "Idempotency-Key": "rollback"},
        json={
            "items": [{"product_id": "product-a", "quantity": 1}, {"product_id": "product-b", "quantity": 1}]
        },
    )
    assert response.status_code == 404
    with database() as db:
        assert db.get(Product, "product-a").available == 5
        assert db.get(Product, "product-a").reserved == 0
        assert db.scalar(select(func.count()).select_from(Order)) == 0


def test_provider_amount_and_conflicting_replay(client, auth, make_order):
    order = make_order()
    body, headers = signed_event(client, auth, order)
    payload = json.loads(body)
    payload["amount_cents"] += 1
    wrong = json.dumps(payload).encode()
    assert (
        client.post(
            "/webhooks/payments",
            content=wrong,
            headers={"X-Payment-Signature": sign(wrong, settings().webhook_secret)},
        ).status_code
        == 409
    )
    assert client.post("/webhooks/payments", content=body, headers=headers).status_code == 200
    payload = json.loads(body)
    payload["outcome"] = "failure"
    changed = json.dumps(payload).encode()
    assert (
        client.post(
            "/webhooks/payments",
            content=changed,
            headers={"X-Payment-Signature": sign(changed, settings().webhook_secret)},
        ).status_code
        == 409
    )


def test_concurrent_idempotent_checkout(database):
    barrier = Barrier(2)

    def checkout(_):
        barrier.wait(timeout=10)
        with database.begin() as db:
            return create_order(
                db,
                db.get(User, "customer-a"),
                OrderCreate(items=[{"product_id": "product-a", "quantity": 1}]),
                "same-key",
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(checkout, range(2)))
    assert len(set(results)) == 1
    with database() as db:
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved) == (4, 1)
        assert db.scalar(select(func.count()).select_from(Order)) == 1


def test_concurrent_webhook_replay(client, auth, make_order, database):
    order = make_order()
    body, _ = signed_event(client, auth, order)
    parsed = Webhook.model_validate_json(body)
    barrier = Barrier(2)

    def deliver(_):
        barrier.wait(timeout=10)
        with database.begin() as db:
            return process_webhook(db, parsed, body)["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, range(2)))
    assert sorted(results) == ["duplicate", "processed"]
    with database() as db:
        stock = db.get(Product, "product-a")
        assert (stock.available, stock.reserved, stock.sold) == (4, 0, 1)
        assert db.scalar(select(func.count()).select_from(OrderEvent).where(OrderEvent.kind == "PAID")) == 1


def test_large_order_amounts(client, auth, database):
    with database.begin() as db:
        product = db.get(Product, "product-a")
        product.price_cents = 100_000_000
        product.available = 1000
    response = client.post(
        "/orders",
        headers={**auth(), "Idempotency-Key": "large"},
        json={"items": [{"product_id": "product-a", "quantity": 1000}]},
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["total_cents"] == 108_250_000_000
    body, headers = signed_event(client, auth, order)
    assert client.post("/webhooks/payments", content=body, headers=headers).status_code == 200
    response = client.post(f"/orders/{order['id']}/refund", headers=auth("staff-a"))
    assert response.status_code == 200
    assert response.json()["amount_cents"] == order["total_cents"]


def test_production_simulator_is_disabled(client, auth, make_order):
    order = make_order()
    old = settings().app_env
    try:
        settings().app_env = "production"
        response = client.post(
            f"/dev/orders/{order['id']}/simulate", headers=auth(), json={"outcome": "success"}
        )
        assert response.status_code == 404
    finally:
        settings().app_env = old
