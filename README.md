# OrderFlow

A multi-tenant merchant workspace with a FastAPI API, PostgreSQL persistence, and React/TypeScript UI. Create products, reserve inventory, place orders, simulate a signed payment callback, fulfill orders, and issue full simulated refunds. No payment account or external API key is required.

## First run in about ten minutes

Prerequisites: Git, Docker Desktop with its Linux engine running, and Docker Compose v2. Node.js 22.12+ is needed only for local frontend work/browser tests. Python 3.12+ is needed only for native backend development.

```sh
git clone https://github.com/gaurav-patel-28/order-processing-application.git
cd order-processing-application
cp .env.example .env
docker compose up --build -d --wait
docker compose exec api python -m app.seed
```

PowerShell equivalent: `Copy-Item .env.example .env`, then `./scripts/dev.ps1 setup`. GNU Make users can use `make setup`. Downloads on a cold Docker installation can take longer than ten minutes.

Open [the UI](http://localhost:8080), [interactive API documentation](http://localhost:8000/docs), and [readiness](http://localhost:8000/ready). Application data persists in the `postgres-data` Docker volume. Restarting services does not reset it. Seeding is idempotent and preserves existing products, stock and orders.

Development-only password for all demo accounts: **`Orderflow123!`**.

- Northstar Supply: `admin.a@orderflow.test`, `staff.a@orderflow.test`, `customer.a@orderflow.test`, `customer2.a@orderflow.test`.
- Juniper Trading: the same account names with `.b` instead of `.a`.
- Admins manage products and stock. Staff manage catalog information and fulfill/refund merchant orders. Customers browse their merchant, create orders, simulate payment, and cancel their own pending orders.

The default secrets and seeded accounts are for local development only. Seeding and payment simulation triggers are disabled in production mode. There is no real payment processing or card-entry form.

## Walk through a complete order

1. Sign in as `admin.a`. Add a product with price and available stock, or edit an existing one. Inventory shows available, reserved and sold separately.
2. Sign out; sign in as `customer.a`. Choose a quantity and create an order. The server snapshots catalog prices, calculates tax, reserves stock, and creates a payment attempt in one transaction.
3. In order detail, select **Simulate successful payment**. The server produces and verifies a signed provider event, marks the order PAID, consumes the reservation, and appends an audit event.
4. Sign out; sign in as `staff.a`. Open Orders, select the order, then **Fulfill order**. A full simulated refund is also available for paid/fulfilled orders.
5. To demonstrate failure, create another order and select **Simulate failed payment**. It becomes PAYMENT_FAILED and its reservation is released. Pending orders can instead be canceled. Failed orders are terminal; create a new order to retry.
6. Sign in as `staff.b` or `customer2.a`: the first merchant's/other customer's orders do not appear, and direct API access is rejected.

All amounts are USD integer cents. Tax is a demonstration 8.25%, rounded once per order with Decimal ROUND_HALF_UP. Discount is zero; promotions are not exposed. Full refunds never imply a physical inventory return and do not automatically restock sold goods. See [architecture and business policies](docs/architecture.md).

## Developer commands

From the repository root:

```sh
make setup              # build, migrate, start, seed
make migrate            # apply pending migrations
make seed               # add missing synthetic demo data
make test               # unit + PostgreSQL integration checks in disposable test-db
make test-unit
make test-integration
make lint               # Ruff, formatting, TypeScript and production build
make test-browser       # three Playwright workflows against seeded running app
make down               # stop services; keep development data
```

Each task also has a PowerShell equivalent: `./scripts/dev.ps1 test`, `./scripts/dev.ps1 lint`, and so on. **`make reset` / `./scripts/dev.ps1 reset` deletes this Compose project's development database volume and starts over.** Use it only when you intend to discard local demo data.

Browser tests require Node.js 22.12+, a seeded app, and downloadable Playwright Chromium. They use synthetic users/products and add demo orders. Tests are sequential and can be repeated. The unit/integration suite truncates its disposable database before each test; never point it at data you want to keep. `TEST_DATABASE_URL` must use PostgreSQL and a database name ending `_test`; tests refuse unsafe names and do not silently skip database coverage.

### Native development (without containers)

Create two local PostgreSQL databases, `orderflow` and `orderflow_test`, with a local development role. Set `DATABASE_URL` explicitly. Commands below assume port 5432 and the development-only role/password `orderflow`.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On PowerShell, activate with `./.venv/Scripts/Activate.ps1` and use `$env:DATABASE_URL='postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow'`. `APP_ENV` defaults to development. In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [Vite](http://localhost:5173). The `/api` proxy forwards to port 8000, so there is no cross-origin token configuration. Tokens are held only in memory; reloading the app requires sign-in.

Native backend tests, from `backend` with the virtual environment active:

```sh
export TEST_DATABASE_URL=postgresql+psycopg://orderflow:orderflow@localhost:5432/orderflow_test
pytest -q
pytest -q -m 'not integration'
pytest -q -m integration
ruff check .
ruff format --check .
alembic check
```

Use `$env:TEST_DATABASE_URL='...'` in PowerShell. Tests apply real Alembic migrations automatically. `alembic check` checks the database configured by `DATABASE_URL` for schema drift. Frontend checks from `frontend`: `npm run format:check`, `npm run build`, `npx playwright install chromium`, `npm run test:e2e`. For Compose-hosted browser tests set `E2E_BASE_URL=http://localhost:8080`; otherwise Playwright starts Vite automatically against an already-running native API.

## API examples and operational inspection

Copy the access token from login into `TOKEN`. Bash examples (PowerShell users can use `curl.exe` or the interactive API docs):

```sh
curl -s http://localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"customer.a@orderflow.test","password":"Orderflow123!"}'
curl -s http://localhost:8000/products -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/orders -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-checkout-001' \
  -d '{"items":[{"product_id":"a-FIELD-01","quantity":1}]}'
curl -s http://localhost:8000/dev/orders/ORDER_ID/simulate \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"outcome":"success"}'
curl -s http://localhost:8000/orders/ORDER_ID/events -H "Authorization: Bearer $TOKEN"
```

The same customer/idempotency key and identical items return the same order. Reusing a key with different items returns 409. A server-generated request ID is returned in `X-Request-ID` and logged with status/duration. Signature failures return 401; insufficient stock and illegal transitions return 409. Merchant stock adjustments require admin; unauthorized resource lookups return non-disclosing 404s.

```sh
docker compose logs -f api
docker compose exec db psql -U orderflow -d orderflow -c \
  "SELECT id,status,total_cents FROM orders ORDER BY created_at DESC LIMIT 10;"
docker compose exec db psql -U orderflow -d orderflow -c \
  "SELECT sku,available,reserved,sold FROM products;"
```

Select failed payment in the UI and inspect its PAYMENT_FAILED event in order history and API JSON transition logs. Audit records and state changes commit together. The public `/health` endpoint reports process liveness; `/ready` checks PostgreSQL and the migration marker. `/webhooks/payments` accepts only valid HMAC-SHA256 signatures over `timestamp + '.' + exact_raw_body`, in `X-Payment-Signature: t=UNIX_SECONDS,v1=HEX_DIGEST`, within five minutes. Invalid/tampered/stale signatures are rejected; duplicate event IDs have no repeat financial effect. The executable signed-event examples are in `backend/tests/test_integration.py`.

## Maintenance exercises

`main` is the healthy application. Three independent branches intentionally contain regressions and must be used with synthetic local data only:

- `scenario/duplicate-payment-webhook`: [callback retry issue](docs/maintenance-cases/duplicate-payment-webhook.md).
- `scenario/tenant-order-leak`: [merchant visibility issue](docs/maintenance-cases/tenant-order-leak.md).
- `scenario/inventory-oversell`: [last-unit contention issue](docs/maintenance-cases/inventory-oversell.md).

Each issue provides a focused failing command and observed output. [Delivery verification](docs/delivery.md) records the healthy and broken commit IDs. No autonomous maintenance agent is included.

To investigate, stop the app, ensure `git status --short` is clean, switch to one scenario branch, and rebuild. Example:

```sh
docker compose down
git switch scenario/duplicate-payment-webhook
docker compose --profile test run --build --rm tests pytest -q tests/test_integration.py::test_duplicate_webhook
docker compose down
git switch main
docker compose up --build -d --wait
```

The focused check is expected to fail on the scenario branch and pass on `main`. Rebuilding prevents accidentally testing stale container code. Container integration tests use their separate ephemeral test database and never modify the development catalog.

## CI, troubleshooting, and limits

GitHub Actions runs Ruff and backend tests against a disposable PostgreSQL 16 service, checks schema drift, builds/types-checks/formats the frontend, and runs browser journeys against the full Compose stack. Deliberately broken scenario branches are excluded from push CI; their issue reports give the expected red checks. Pull requests targeting main still run the normal suite.

- Docker engine unavailable: start Docker Desktop and wait for the Linux engine. On this implementation machine Docker did not become available, so actual runtime verification used an isolated native PostgreSQL 18 instance. Compose configuration was validated; the full container build/start awaits CI/a running engine.
- Port conflict: change Compose host ports and use the matching UI/API URLs; PostgreSQL inside Compose still uses port 5432. Native Vite expects API on port 8000.
- Authentication expired: sign in again. Accounts and memberships are seeded development data; there is no registration/password recovery UI.
- Browser command missing: install Node.js and run `npm ci` in `frontend`; install Chromium with the command above.
- A payment failure or stock conflict is expected behavior: inspect the visible error, order history, and request ID in logs. Failed/canceled orders cannot be paid or fulfilled.
- No Stripe integration, real tax jurisdiction logic, partial refunds, returns logistics, user provisioning, or production deployment is provided. External provider integration needs reconciliation/outbox handling; see the architecture notes.

See [delivery verification](docs/delivery.md) for commands actually executed, outcomes, and remaining environment limits.
