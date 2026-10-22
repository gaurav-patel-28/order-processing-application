from decimal import ROUND_HALF_UP, Decimal

TRANSITIONS = {
    "PENDING_PAYMENT": {"PAID", "PAYMENT_FAILED", "CANCELED"},
    "PAID": {"FULFILLED", "REFUNDED"},
    "FULFILLED": {"REFUNDED"},
    "PAYMENT_FAILED": set(),
    "CANCELED": set(),
    "REFUNDED": set(),
}


def totals(subtotal: int, discount: int = 0):
    if subtotal < 0 or not 0 <= discount <= subtotal:
        raise ValueError("Discount must be between zero and subtotal")
    taxable = subtotal - discount
    tax = int((Decimal(taxable) * Decimal("0.0825")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return tax, taxable + tax


def can_access(role, user_org, user_id, order_org, customer_id):
    return user_org == order_org and (role in {"admin", "staff"} or user_id == customer_id)


def transition_allowed(current, target):
    return target in TRANSITIONS.get(current, set())
