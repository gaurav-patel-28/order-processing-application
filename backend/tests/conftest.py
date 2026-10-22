import os

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.auth import passwords
from app.db import Base, get_db
from app.main import app
from app.models import Organization, Product, User


@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "Integration tests require TEST_DATABASE_URL pointing to a disposable PostgreSQL database"
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
        pytest.fail("Safety guard: TEST_DATABASE_URL must be PostgreSQL with database name ending _test")
    test_engine = create_engine(url, pool_size=8)
    # Migrate the actual test database; unit tests never use a SQLite substitute.
    from app.config import settings

    original = settings().database_url
    settings().database_url = url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        settings().database_url = original
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def database(pg_engine):
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    hashed = passwords.hash("Orderflow123!")
    with factory.begin() as db:
        db.add_all([Organization(id="a", name="A"), Organization(id="b", name="B")])
        db.flush()
        for user_id, org_id, role in [
            ("admin-a", "a", "admin"),
            ("staff-a", "a", "staff"),
            ("customer-a", "a", "customer"),
            ("other-a", "a", "customer"),
            ("staff-b", "b", "staff"),
            ("customer-b", "b", "customer"),
        ]:
            db.add(
                User(
                    id=user_id, org_id=org_id, role=role, email=f"{user_id}@test.local", password_hash=hashed
                )
            )
        db.add_all(
            [
                Product(
                    id="product-a", org_id="a", sku="A", name="A notebook", price_cents=1001, available=5
                ),
                Product(id="product-b", org_id="b", sku="B", name="B notebook", price_cents=500, available=5),
            ]
        )
    return factory


@pytest.fixture
def client(database):
    def override_db():
        with database() as db:
            with db.begin():
                yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as result:
        yield result
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    def headers(user="customer-a"):
        response = client.post(
            "/auth/login", json={"email": f"{user}@test.local", "password": "Orderflow123!"}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return headers


@pytest.fixture
def make_order(client, auth):
    def create(user="customer-a", product="product-a", quantity=1, key="checkout"):
        response = client.post(
            "/orders",
            headers={**auth(user), "Idempotency-Key": key},
            json={"items": [{"product_id": product, "quantity": quantity}]},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return create
