import hashlib
import json
import logging

from fastapi import HTTPException
from sqlalchemy import select, update

from .domain import can_access, totals, transition_allowed
from .models import Order, OrderEvent, OrderLine, PaymentAttempt, Product, ProviderEvent, Refund, User
from .providers import provider

log = logging.getLogger("orderflow")


def scoped_order(db, user, order_id, lock=False):
    query = select(Order).where(Order.id == order_id)
    if lock:
        query = query.with_for_update()
    order = db.scalar(query)
    if order is None or not can_access(user.role, user.org_id, user.id, order.org_id, order.customer_id):
        raise HTTPException(404, "Order not found")
    return order


def scoped_product(db, user, product_id, lock=False):
    query = select(Product).where(Product.id == product_id, Product.org_id == user.org_id)
    if lock:
        query = query.with_for_update()
    product = db.scalar(query)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


def audit(db, order, kind, actor, **details):
    event = OrderEvent(order_id=order.id, kind=kind, actor=actor, details=details)
    db.add(event)
    log.info(json.dumps({"event": kind, "order_id": order.id, "actor": actor, **details}))


def change_status(db, order, target, actor):
    if not transition_allowed(order.status, target):
        raise HTTPException(409, f"Cannot transition {order.status} to {target}")
    previous = order.status
    order.status = target
    audit(db, order, target, actor, previous=previous)


def reserve(db, product, quantity):
    if not product.active or product.available < quantity:
        raise HTTPException(409, f"Insufficient stock for {product.name}")
    db.execute(
        update(Product)
        .where(Product.id == product.id)
        .values(available=product.available - quantity, reserved=product.reserved + quantity)
        .execution_options(synchronize_session=False)
    )


def create_order(db, user, data, key):
    if user.role != "customer":
        raise HTTPException(403, "Customer permission required")
    # Serialize a customer's retries before inspecting the idempotency record.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    normalized = sorted([item.model_dump() for item in data.items], key=lambda x: x["product_id"])
    request_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
    existing = db.scalar(select(Order).where(Order.customer_id == user.id, Order.idempotency_key == key))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "Idempotency key already used for a different request")
        return existing
    lines, subtotal = [], 0
    for item in normalized:
        product = scoped_product(db, user, item["product_id"])
        quantity = item["quantity"]
        reserve(db, product, quantity)
        subtotal += product.price_cents * quantity
        lines.append(
            OrderLine(
                product_id=product.id,
                name=product.name,
                quantity=quantity,
                unit_price_cents=product.price_cents,
            )
        )
    tax, total = totals(subtotal)
    order = Order(
        org_id=user.org_id,
        customer_id=user.id,
        idempotency_key=key,
        request_hash=request_hash,
        subtotal_cents=subtotal,
        tax_cents=tax,
        total_cents=total,
        lines=lines,
    )
    db.add(order)
    db.flush()
    audit(db, order, "PENDING_PAYMENT", user.id)
    create_attempt(db, order)
    db.flush()
    db.expire(order, ["events"])
    return order


def create_attempt(db, order):
    attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id == order.id))
    if attempt:
        return attempt
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(409, "Only pending orders can start payment")
    attempt = PaymentAttempt(
        order_id=order.id,
        provider_id=provider.create(order.id, order.total_cents),
        amount_cents=order.total_cents,
    )
    db.add(attempt)
    db.flush()
    return attempt


def move_inventory(db, order, disposition):
    for line in sorted(order.lines, key=lambda x: x.product_id):
        values = {"reserved": Product.reserved - line.quantity}
        if disposition == "consume":
            values["sold"] = Product.sold + line.quantity
        else:
            values["available"] = Product.available + line.quantity
        result = db.execute(
            update(Product)
            .where(Product.id == line.product_id, Product.reserved >= line.quantity)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "Inventory reservation inconsistent; contact merchant")


def process_webhook(db, event, body):
    attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.provider_id == event.provider_id))
    if attempt is None:
        raise HTTPException(404, "Payment attempt not found")
    # All lifecycle paths lock the order first, avoiding payment/order lock inversion.
    order = db.scalar(select(Order).where(Order.id == attempt.order_id).with_for_update())
    payload_hash = hashlib.sha256(body).hexdigest()
    previous = db.get(ProviderEvent, event.id)
    if previous:
        if previous.payload_hash != payload_hash or previous.attempt_id != attempt.id:
            raise HTTPException(409, "Provider event ID reused with different contents")
        log.info(json.dumps({"event": "webhook_duplicate", "order_id": order.id, "provider_event": event.id}))
        return {"status": "duplicate"}
    if event.amount_cents != attempt.amount_cents:
        raise HTTPException(409, "Provider amount does not match payment attempt")
    db.add(ProviderEvent(id=event.id, attempt_id=attempt.id, payload_hash=payload_hash))
    if order.status != "PENDING_PAYMENT":
        audit(db, order, "PAYMENT_EVENT_IGNORED", "simulator", outcome=event.outcome)
        return {"status": "ignored"}
    target = "PAID" if event.outcome == "success" else "PAYMENT_FAILED"
    move_inventory(db, order, "consume" if target == "PAID" else "release")
    attempt.status = "SUCCEEDED" if target == "PAID" else "FAILED"
    change_status(db, order, target, "simulator")
    return {"status": "processed"}


def cancel(db, order, actor):
    if order.status == "CANCELED":
        return order
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(409, "Only unpaid pending orders can be canceled")
    move_inventory(db, order, "release")
    attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id == order.id))
    if attempt:
        attempt.status = "CANCELED"
    change_status(db, order, "CANCELED", actor)
    return order


def refund(db, order, actor):
    existing = db.scalar(select(Refund).where(Refund.order_id == order.id))
    if existing:
        return existing
    if order.status not in {"PAID", "FULFILLED"}:
        raise HTTPException(409, "Only paid or fulfilled orders can be refunded")
    attempt = db.scalar(select(PaymentAttempt).where(PaymentAttempt.order_id == order.id))
    if attempt is None or attempt.status != "SUCCEEDED" or attempt.amount_cents != order.total_cents:
        raise HTTPException(409, "No matching captured payment")
    record = Refund(
        order_id=order.id,
        amount_cents=attempt.amount_cents,
        provider_id=provider.refund(attempt.provider_id, attempt.amount_cents),
    )
    db.add(record)
    attempt.status = "REFUNDED"
    # Financial refunds do not imply goods have been physically returned.
    change_status(db, order, "REFUNDED", actor)
    db.flush()
    return record
