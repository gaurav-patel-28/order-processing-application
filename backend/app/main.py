import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import schemas as s
from . import services
from .auth import admin, current_user, merchant, passwords, token_for
from .config import settings
from .db import engine, get_db
from .models import Order, Product, User
from .providers import SimulatedProvider, sign, verify

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("orderflow")


@asynccontextmanager
async def lifespan(app):
    settings().validate_runtime()
    yield
    engine.dispose()


app = FastAPI(title="OrderFlow", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def correlation(request: Request, call_next):
    correlation_id = str(uuid4())
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    log.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        status_code=409, content={"detail": "Conflict with an existing record or inventory constraint"}
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM alembic_version LIMIT 1"))
        return {"status": "ready"}
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})


@app.post("/auth/login")
def login(data: s.Login, db: Session = Depends(get_db, scope="function")):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    # A dummy verification keeps unknown-user requests on the same hashing path.
    candidate_hash = user.password_hash if user else DUMMY_HASH
    valid = passwords.verify(data.password, candidate_hash)
    if user is None or not valid:
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": token_for(user), "token_type": "bearer", "user": s.UserOut.model_validate(user)}


DUMMY_HASH = passwords.hash("not-a-real-user-password")


@app.get("/auth/me", response_model=s.UserOut)
def me(user=Depends(current_user)):
    return user


@app.get("/products", response_model=list[s.ProductOut])
def products(
    user=Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    q: str = Query("", max_length=100),
):
    query = select(Product).where(Product.org_id == user.org_id)
    if user.role == "customer":
        query = query.where(Product.active.is_(True))
    if q:
        query = query.where(Product.name.ilike(f"%{q}%"))
    return db.scalars(query.order_by(Product.name, Product.id).offset(offset).limit(limit)).all()


@app.post("/products", response_model=s.ProductOut, status_code=201)
def add_product(
    data: s.ProductCreate, user=Depends(merchant), db: Session = Depends(get_db, scope="function")
):
    if user.role != "admin" and data.available:
        raise HTTPException(403, "Only admins can set initial stock")
    product = Product(org_id=user.org_id, **data.model_dump())
    db.add(product)
    db.flush()
    return product


@app.patch("/products/{product_id}", response_model=s.ProductOut)
def edit_product(
    product_id: str,
    data: s.ProductEdit,
    user=Depends(merchant),
    db: Session = Depends(get_db, scope="function"),
):
    if "available" in data.model_fields_set and user.role != "admin":
        raise HTTPException(403, "Only admins can adjust stock")
    product = services.scoped_product(db, user, product_id, lock=True)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.flush()
    return product


@app.get("/inventory", response_model=list[s.ProductOut])
def inventory(
    user=Depends(merchant),
    db: Session = Depends(get_db, scope="function"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    return products(user, db, offset, limit, "")


@app.patch("/inventory/{product_id}", response_model=s.ProductOut)
def adjust_inventory(
    product_id: str,
    data: s.InventoryEdit,
    user=Depends(admin),
    db: Session = Depends(get_db, scope="function"),
):
    product = services.scoped_product(db, user, product_id, lock=True)
    product.available = data.available
    db.flush()
    log.info(
        json.dumps(
            {
                "event": "inventory_adjusted",
                "actor": user.id,
                "product_id": product.id,
                "available": product.available,
            }
        )
    )
    return product


@app.post("/orders", response_model=s.OrderOut, status_code=201)
def add_order(
    data: s.OrderCreate,
    user=Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
    idempotency_key: str = Header(min_length=1, max_length=128),
):
    return services.create_order(db, user, data, idempotency_key)


@app.get("/orders", response_model=list[s.OrderOut])
def orders(
    user=Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, max_length=30),
):
    query = select(Order).where(Order.org_id == user.org_id)
    if user.role == "customer":
        query = query.where(Order.customer_id == user.id)
    if status:
        query = query.where(Order.status == status)
    return db.scalars(query.order_by(Order.created_at.desc(), Order.id).offset(offset).limit(limit)).all()


@app.get("/orders/{order_id}", response_model=s.OrderOut)
def order_detail(order_id: str, user=Depends(current_user), db: Session = Depends(get_db, scope="function")):
    return services.scoped_order(db, user, order_id)


@app.get("/orders/{order_id}/events", response_model=list[s.EventOut])
def order_events(order_id: str, user=Depends(current_user), db: Session = Depends(get_db, scope="function")):
    return services.scoped_order(db, user, order_id).events


@app.post("/orders/{order_id}/cancel", response_model=s.OrderOut)
def cancel_order(order_id: str, user=Depends(current_user), db: Session = Depends(get_db, scope="function")):
    order = services.scoped_order(db, user, order_id, lock=True)
    services.cancel(db, order, user.id)
    db.flush()
    db.expire(order, ["events"])
    return order


@app.post("/orders/{order_id}/payment-attempts", response_model=s.AttemptOut)
def payment_attempt(
    order_id: str, user=Depends(current_user), db: Session = Depends(get_db, scope="function")
):
    return services.create_attempt(db, services.scoped_order(db, user, order_id, lock=True))


@app.post("/orders/{order_id}/fulfill", response_model=s.OrderOut)
def fulfill(order_id: str, user=Depends(merchant), db: Session = Depends(get_db, scope="function")):
    order = services.scoped_order(db, user, order_id, lock=True)
    if order.status != "FULFILLED":
        services.change_status(db, order, "FULFILLED", user.id)
    db.flush()
    db.expire(order, ["events"])
    return order


@app.post("/orders/{order_id}/refund", response_model=s.RefundOut)
def refund_order(order_id: str, user=Depends(merchant), db: Session = Depends(get_db, scope="function")):
    return services.refund(db, services.scoped_order(db, user, order_id, lock=True), user.id)


@app.post("/webhooks/payments")
async def webhook(
    request: Request, x_payment_signature: str = Header(""), db: Session = Depends(get_db, scope="function")
):
    body = await request.body()
    if len(body) > 8192:
        raise HTTPException(413, "Event too large")
    if not verify(body, x_payment_signature, settings().webhook_secret):
        raise HTTPException(401, "Invalid payment signature")
    try:
        event = s.Webhook.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Invalid provider event")
    return services.process_webhook(db, event, body)


@app.post("/dev/orders/{order_id}/simulate")
def simulate(
    order_id: str,
    data: s.Simulate,
    user=Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
):
    if settings().app_env == "production":
        raise HTTPException(404, "Not found")
    order = services.scoped_order(db, user, order_id, lock=True)
    attempt = services.create_attempt(db, order)
    body = SimulatedProvider().event(attempt.provider_id, data.outcome, attempt.amount_cents)
    signature = sign(body, settings().webhook_secret)
    if not verify(body, signature, settings().webhook_secret):
        raise HTTPException(502, "Simulator signature verification failed")
    return services.process_webhook(db, s.Webhook.model_validate_json(body), body)
