# PROJECT.md — OrderFlow Product and Build Specification

## 1. The product
**OrderFlow** is a small but credible multi-tenant order management platform for merchants. It is a real web application and HTTP API, not a calculator or an AI wrapper. A merchant manages products and stock. A customer places an order. The platform reserves inventory, computes a trustworthy total, simulates a payment provider, responds to a webhook, and updates the order. Staff can inspect and cancel/refund orders. These workflows persist through a real relational database and enforce user and organization permissions.

**Primary goal:** Make software with enough real behavior, cross-component interactions, and operational failure modes to be a useful maintenance target.

**Secondary goal:** Make it straightforward for a future external maintenance engineer to clone, run, diagnose, modify, test, and propose fixes.

This repository does **not** contain the autonomous maintenance agent.

## 2. Scope: the end-to-end product
Implement these capabilities with actual persistence and coherent API/UI behavior:

### A. Identity and organization boundaries
- Users log in with local development credentials (passwords securely hashed) and receive an authenticated session or short-lived token. Distinguish merchant admin, merchant staff, and customer roles.
- Every merchant-owned product, inventory record, and order belongs to an organization. Merchant staff may operate only on their organization's records. Customers may see only their own orders. Never trust an organization ID supplied by the browser without checking access.
- Seed at least two organizations, with different users and products, so tenant-boundary tests are meaningful.

### B. Product catalog and inventory
- Merchant can create/list/edit products with SKU, name, price, active status, and stock count. Disallow negative prices or stock.
- Track **available**, **reserved**, and **sold** inventory correctly. Reserve stock when an order is submitted; release it when payment fails or an eligible order is canceled; consume reservation when payment is confirmed.
- Ensure a product with one remaining unit cannot be successfully reserved by two competing orders. Use PostgreSQL transactions and locking or a correct atomic conditional update.

### C. Order lifecycle
- Customer creates an order with line items and quantities; server fetches current product prices rather than trusting client-submitted totals.
- Snapshot item prices into order lines and calculate subtotal, discount (if supported), tax, and total using `Decimal` or integer minor currency units. Pick one currency (USD) and document a deterministic rounding rule; keep totals consistent.
- Model explicit statuses. A reasonable flow is `PENDING_PAYMENT → PAID → FULFILLED`, with `CANCELED` and `PAYMENT_FAILED` alternatives. Define allowable transitions and ensure invalid transitions are rejected.
- Provide order history and order detail views, including line items, current status, and event/audit history.
- Admin/staff can mark a paid order fulfilled, with proper permission checks; no fulfillment for unpaid or canceled orders.

### D. Payment gateway boundary
- Build a `PaymentProvider` interface with a deterministic **simulated provider**, selected by default. The simulator returns stable provider identifiers, can report success/failure, and can send a signed development webhook (or equivalent authenticated simulation) to drive order transitions. Make the simulation easy to operate through the UI or documented scripts.
- Use server-side payment intent/attempt records. The platform must handle duplicate create requests or provider callbacks idempotently, preventing duplicate order capture, duplicate inventory consumption, and duplicate refunds.
- Validate provider event authenticity/signature for webhook processing, including the simulator; reject invalid signatures. Persist processed event IDs and reject or safely ignore duplicates.
- **Optional if the complete baseline is stable:** Add a Stripe adapter using official SDK in Stripe test mode only. Credentials are optional and sourced from environment variables. If not implemented, document the integration seam and exact limitations; do not claim a working Stripe integration.
- No real charges, no production payment credentials, and no raw card capture/storage in this application.

### E. Cancellation and refunds
- Customer can cancel an unpaid order; release its reservation. Merchant can issue a permitted refund for a paid order. Persist a refund record and keep order/payment state consistent. If partial refunds add excessive scope, support correct full refunds and document the limitation.
- A refund cannot exceed paid amount; repeat requests cannot create duplicate refunds.

### F. Real web UI
Build a functional React/TypeScript interface, not an image mockup. Minimum screens:
1. Login and an obvious role-aware navigation.
2. Merchant product/inventory list and a form to add/edit a product.
3. Customer catalog, cart/checkout or equivalent order creation flow.
4. Order list and detail page showing items, totals, state, and history.
5. Payment simulation action/status and merchant fulfillment/refund actions as authorized.

Prefer simple, readable UX and clear errors over visual decoration. The user should be able to demonstrate a complete order without writing raw HTTP requests.

### G. Operational characteristics
- PostgreSQL is the source of truth; migrations via Alembic or equivalent. Provide seed/reset procedures clearly marked for **development only**.
- Publish OpenAPI docs through the framework and a small set of copyable curl examples.
- Use configuration from environment. Provide health/readiness endpoints, structured logs with request correlation IDs, and an audit/event trail of meaningful order state changes.
- Include pagination/filtering for order/product lists where straightforward. Return appropriate HTTP errors for authentication, authorization, validation, not found, conflict, and provider failure.
- Provide a real CI workflow that runs fast checks and backend integration tests against a disposable PostgreSQL database; include frontend build/tests if created.

## 3. Concrete implementation defaults
Use these unless the repository already has a coherent, established stack:

| Concern | Default |
|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic |
| Data layer | SQLAlchemy 2.x, Alembic, PostgreSQL |
| Authentication | Secure password hashes and JWT or server sessions with role/tenant validation |
| Frontend | React + TypeScript + Vite, straightforward styling |
| API testing | pytest, httpx, pytest fixtures; real Postgres for database integration checks |
| Browser workflow testing | Playwright (a few critical workflows, not every possible interaction) |
| Local runtime | Docker Compose for Postgres and application services; easy documented commands |
| Quality | Python formatting/linting, TS type-check/build, CI |
| Payment | Local simulator by default; optional Stripe test-only adapter |

Avoid premature Kubernetes, service meshes, event buses, vector databases, LLM calls, and multiple autonomous agents. A modular monolith can be genuinely complex and production-like.

Suggested directories (adapt as useful):

```text
orderflow/
├── AGENTS.md
├── PROJECT.md
├── MAINTENANCE_SCENARIOS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/            # routes, domain/services, auth, providers, database
│   ├── alembic/        # migrations
│   └── tests/          # unit and integration
├── frontend/
│   ├── src/            # web application
│   └── e2e/            # selected browser workflows
├── scripts/             # dev setup, seed, run, scenario helpers
└── .github/workflows/  # CI
```

## 4. Business rules and expected behaviors
Write them down in code and in tests. Minimum invariants:

1. An organization cannot read, alter, fulfill, or refund another organization's orders.
2. A customer cannot see another customer's orders.
3. An order total is derived by the server from price snapshots and documented monetary rules; it never becomes negative.
4. Stock cannot fall below zero; concurrent reservations cannot oversell.
5. Payment confirmation is not based only on a browser saying "success"; it follows a validated provider event.
6. Processing the same provider event twice has the same effect as processing it once.
7. A `PAID` order cannot return to `PENDING_PAYMENT` merely because a delayed failure event arrives.
8. An unpaid order cannot be fulfilled; canceled/failed orders do not consume stock.
9. A refund or cancellation cannot be performed twice to produce two payouts or two stock releases.
10. All critical state changes persist and appear in an auditable event history.

If a detail is not specified, choose a simple documented business rule and test it rather than inventing complicated features.

## 5. Verification: what is actually tested?
These tests validate **OrderFlow**, not the autonomous maintenance engineer (which does not exist yet).

### Unit tests: isolated rules
- Monetary arithmetic and rounding; quantity validation; discount never exceeding the applicable amount.
- Valid and invalid order-status transitions.
- Permission/authorization decision helpers and deterministic payment simulator behavior.

### Integration tests: real connected components
- Create product → persist → query via authenticated API.
- Create order → reserve inventory → persist order lines and payment attempt.
- Confirm payment webhook → exactly one `PAID` transition → inventory state matches.
- Provider failure → order and reservation consistent.
- Two concurrent reservations of the last item → one succeeds; one is rejected.
- Organization A user cannot read/modify organization B resources.
- Duplicate webhook and duplicate idempotency-key requests cause no duplicate financial/inventory effect.
- Cancellation, refund, and illegal transition cases.

### End-to-end tests: user journeys
- Merchant logs in and creates a product; customer logs in, orders it, completes simulated payment, and sees a paid order; merchant fulfills it.
- A second user tries to access a resource they do not own and is rejected (UI behavior plus back-end enforcement).
- Payment failure leaves an informative result and appropriate stock state.

### Manual operational exercise
- Start services with documented commands.
- Inspect API docs, database records, application logs, and order audit history.
- Show a meaningful failure log/event and identify which component emitted it.

Tests must check expected behavior, not assert against predetermined hardcoded response strings that bypass real logic. Ensure test fixtures are isolated and repeatable.

## 6. Suggested API surface (adapt only with equivalent functionality)
- `POST /auth/login`, `GET /auth/me`
- `GET /products`, `POST /products`, `PATCH /products/{id}`
- `GET /inventory`, `PATCH /inventory/{product_id}` (admin-only adjustments)
- `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`
- `POST /orders/{id}/payment-attempts`, `POST /webhooks/payments` (signature validation)
- Development-only payment simulation trigger **never exposed in production mode**
- `POST /orders/{id}/refund`, `POST /orders/{id}/fulfill`
- `GET /orders/{id}/events`, `GET /health`, `GET /ready`

Use request and response schemas and HTTP status codes that match their actual meanings. Protect every route; a convenient UI login is not sufficient authorization.

## 7. Development and user experience
Provide a small `Makefile` or comparable documented commands for:
- initial setup and starting services;
- applying migrations and seeding two organizations;
- unit tests;
- PostgreSQL integration tests;
- browser tests (with prerequisites);
- lint/type-check;
- stopping and resetting development services.

`README.md` must give a developer a **10-minute first-run path**, a workflow demonstration, short architecture explanation, tests and troubleshooting, and test/simulator caveats. Show example roles/users and **development-only** credentials (never production credentials). With Docker prerequisites installed, the baseline should be runnable without payment-provider keys.

## 8. Delivery acceptance criteria
The baseline is complete only when all the following are true:

- [ ] Fresh checkout can be started with documented commands and non-secret defaults.
- [ ] Migrations and realistic demo data load; data persists across service restarts.
- [ ] UI supports a complete product → order → simulated payment → fulfillment workflow.
- [ ] Backend enforces user, role, organization, and ownership boundaries.
- [ ] Inventory, payments, refunds, and monetary totals are transactionally correct under tested conditions.
- [ ] Tests include **real assertions** at unit, integration, and browser-workflow levels.
- [ ] Default branch tests and builds pass **when actually executed**.
- [ ] CI mirrors documented checks without live external accounts.
- [ ] At least three separate broken maintenance scenarios exist and are reproducible as defined in `MAINTENANCE_SCENARIOS.md`.
- [ ] `README.md` explains how to demonstrate normal operation and how to reproduce each failure.

## 9. Execution priorities if time or environment is constrained
Deliver in this order: (1) persistent backend + migrations + auth/org boundaries; (2) correct order/inventory/payment simulator path; (3) usable UI; (4) unit + Postgres integration tests; (5) isolated bug scenarios; (6) browser tests, CI, docs; (7) optional Stripe test adapter and extra polish. **Do not fake completeness.** If a dependency/service is unavailable, implement and verify independently where possible, then report the exact unverified parts.
