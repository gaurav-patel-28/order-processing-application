import hashlib
import hmac
import json
import time
from typing import Protocol


class PaymentProvider(Protocol):
    def create(self, order_id: str, amount_cents: int) -> str: ...
    def refund(self, provider_id: str, amount_cents: int) -> str: ...


class SimulatedProvider:
    def create(self, order_id: str, amount_cents: int) -> str:
        return f"sim_{order_id}"

    def refund(self, provider_id: str, amount_cents: int) -> str:
        return f"refund_{provider_id}"

    def event(self, provider_id: str, outcome: str, amount_cents: int) -> bytes:
        return json.dumps(
            {
                "id": f"evt_{provider_id}_{outcome}",
                "provider_id": provider_id,
                "outcome": outcome,
                "amount_cents": amount_cents,
                "currency": "USD",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()


provider: PaymentProvider = SimulatedProvider()


def sign(body: bytes, secret: str, timestamp: int | None = None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify(body: bytes, signature: str, secret: str):
    try:
        parts = dict(item.split("=", 1) for item in signature.split(","))
        timestamp = int(parts["t"])
        expected = sign(body, secret, timestamp).split("v1=", 1)[1]
        return abs(int(time.time()) - timestamp) <= 300 and hmac.compare_digest(expected, parts["v1"])
    except (ValueError, KeyError):
        return False
