import json
import time

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import can_access, totals, transition_allowed
from app.providers import SimulatedProvider, sign, verify
from app.schemas import OrderCreate, ProductCreate


@pytest.mark.parametrize(
    "subtotal,discount,tax,total",
    [(100, 0, 8, 108), (200, 0, 17, 217), (1000, 1000, 0, 0), (999, 99, 74, 974)],
)
def test_money(subtotal, discount, tax, total):
    assert totals(subtotal, discount) == (tax, total)


@pytest.mark.parametrize("subtotal,discount", [(100, 101), (100, -1), (-1, 0)])
def test_discount_bounds(subtotal, discount):
    with pytest.raises(ValueError):
        totals(subtotal, discount)


def test_transitions_and_permissions():
    assert transition_allowed("PENDING_PAYMENT", "PAID")
    assert transition_allowed("PAID", "FULFILLED")
    assert not transition_allowed("CANCELED", "PAID")
    assert not transition_allowed("PAID", "PAYMENT_FAILED")
    assert not transition_allowed("PENDING_PAYMENT", "FULFILLED")
    assert can_access("staff", "a", "u1", "a", "u2")
    assert not can_access("staff", "a", "u1", "b", "u2")
    assert not can_access("customer", "a", "u1", "a", "u2")
    assert can_access("customer", "a", "u1", "a", "u1")


def test_simulator_and_signature():
    provider = SimulatedProvider()
    assert provider.create("order", 100) == provider.create("order", 100)
    assert provider.refund("sim_order", 100) == provider.refund("sim_order", 100)
    body = provider.event("sim_order", "success", 100)
    assert json.loads(body)["amount_cents"] == 100
    signature = sign(body, "secret")
    assert verify(body, signature, "secret")
    assert not verify(body + b" ", signature, "secret")
    assert not verify(body, signature, "wrong")
    assert not verify(body, sign(body, "secret", int(time.time()) - 301), "secret")
    assert not verify(body, "malformed", "secret")


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, 1001])
def test_quantity_validation(quantity):
    with pytest.raises(ValidationError):
        OrderCreate(items=[{"product_id": "p", "quantity": quantity}])


def test_api_boundary_validation():
    with pytest.raises(ValidationError):
        ProductCreate(sku="x", name="X", price_cents=-1)
    with pytest.raises(ValidationError):
        ProductCreate(sku="x", name="X", price_cents=1, available=-1)
    with pytest.raises(ValidationError):
        OrderCreate(items=[{"product_id": "p", "quantity": 1}] * 2)
    with pytest.raises(ValidationError):
        OrderCreate(items=[{"product_id": "p", "quantity": 1}], total_cents=1)


def test_production_rejects_development_secrets():
    with pytest.raises(ValueError):
        Settings(app_env="production", _env_file=None).validate_runtime()
