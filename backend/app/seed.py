"""Idempotent synthetic development data; never runs in production."""

from sqlalchemy import select

from .auth import passwords
from .config import settings
from .db import SessionLocal
from .models import Organization, Product, User


def seed():
    if settings().app_env == "production":
        raise RuntimeError("Development seed disabled in production")
    with SessionLocal.begin() as db:
        for suffix, name in [("a", "Northstar Supply"), ("b", "Juniper Trading")]:
            org_id = f"org-{suffix}"
            if db.get(Organization, org_id) is None:
                db.add(Organization(id=org_id, name=name))
                db.flush()
            for role in ["admin", "staff", "customer", "customer2"]:
                email = f"{role}.{suffix}@orderflow.test"
                if db.scalar(select(User).where(User.email == email)) is None:
                    db.add(
                        User(
                            id=f"{role}-{suffix}",
                            org_id=org_id,
                            email=email,
                            role="customer" if role.startswith("customer") else role,
                            password_hash=passwords.hash("Orderflow123!"),
                        )
                    )
            catalog = [
                ("FIELD-01", "Field notebook", 1800, 40),
                ("CARRY-02", "Everyday canvas tote", 4200, 18),
                ("DESK-03", "Ceramic desk cup", 2600, 24),
            ]
            for sku, label, price, stock in catalog:
                product_id = f"{suffix}-{sku}"
                if db.get(Product, product_id) is None:
                    db.add(
                        Product(
                            id=product_id,
                            org_id=org_id,
                            sku=sku,
                            name=label if suffix == "a" else f"Juniper {label}",
                            price_cents=price,
                            available=stock,
                        )
                    )
    print("Development seed ready: admin.a@orderflow.test / Orderflow123!")


if __name__ == "__main__":
    seed()
