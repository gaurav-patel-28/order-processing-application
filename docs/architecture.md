# Architecture and invariants

OrderFlow is a modular monolith. React calls the same-origin `/api` proxy; FastAPI owns authentication, authorization, validation, and business transactions. SQLAlchemy writes to PostgreSQL. Alembic versions the schema; schema creation is never an application startup side effect.

## Boundaries

- `auth.py`: Argon2 password hashes, expiring JWTs with issuer/audience validation, current database roles.
- `schemas.py`: request validation and explicit response contracts. Orders reject client prices/totals and repeated product lines.
- `domain.py`: money, permissions, and legal state transitions.
- `services.py`: order transactions, inventory, signed-event effects, refunds, audit trail.
- `providers.py`: deterministic local `PaymentProvider` implementation and HMAC authentication.
- `models.py`: persisted entities, constraints and indexes.

Every user belongs to one organization, including customers. This is a merchant-specific storefront: customers browse only their own merchant's active products. Merchant staff can manage the catalog and fulfill/refund orders. Only admins can change stock, including initial stock. Customers can order, pay in simulation, and cancel their own pending orders. Resource lookups return non-disclosing 404s across boundaries.

## Transactions and concurrency

Every request uses one database transaction, committed before the response is sent through a function-scoped dependency. Errors roll back the whole operation, including reservations on earlier order lines. `POST /orders` locks the customer's user row before checking the persistent idempotency key. A key reused with different items returns 409. Identical retries return the original order, even after its status changes. A single payment attempt per order and a single full refund per order have database unique constraints.

Products are reserved in sorted ID order with a conditional atomic update: available must cover the requested quantity and the product must be active. The update decrements available and increments reserved together. Two transactions cannot both reserve the last unit. Database nonnegative checks provide another layer of protection. Prices and names are snapshotted from the catalog; product edits do not change existing orders.

Payment/cancel/fulfill/refund operations lock the order row first. Verified provider events are persisted with globally unique IDs and a payload digest. An identical replay does nothing; reuse of an ID with a different payload returns 409. Success consumes reservations exactly once. Failure or pending cancellation releases them once. Late events are recorded as ignored and cannot reverse terminal states. Product updates use the same sorted ordering to avoid cross-order lock inversion.

## Money and fulfillment policy

USD integer cents throughout, with PostgreSQL BIGINT aggregate amounts. Demonstration tax is 8.25% of subtotal after discount, rounded once per order to the nearest cent with Decimal `ROUND_HALF_UP`. There is no discount API in this baseline; discount is zero. The arithmetic helper validates discount bounds for future use. Quantities are integers from 1 to 1000 per line, up to 100 different products. Unit prices are capped at $1,000,000 and available-stock edits at 1,000,000 units.

States: PENDING_PAYMENT → PAID → FULFILLED; PENDING_PAYMENT → CANCELED or PAYMENT_FAILED; PAID/FULFILLED → REFUNDED. Failed orders are terminal; create a new order to retry. Fulfillment/refund/cancel repeats are idempotent. Full refunds return exactly the captured amount. Sold goods are not automatically restocked: a financial refund is not evidence of a physical return. Admins can adjust available stock explicitly.

## Provider and operations

The simulator uses stable order-derived intent/refund IDs. The development UI triggers an authenticated server-side simulator action. It generates a signed event and passes it through the same verifier and event processor as `/webhooks/payments`. Webhook signatures cover exact raw bytes and a Unix timestamp, with a five-minute tolerance. Neither the browser nor request JSON can directly set PAID. The development trigger returns 404 in production; seeding is also disabled there. Production rejects default/short secrets.

The provider seam deliberately supports a synchronous local implementation only. A future network payment adapter needs an outbox/reconciliation design, provider idempotency keys, timeouts, and retry handling before deployment. There is no working Stripe adapter and no real charge/card capture in this application.

Audit events persist in the same transaction as order changes. JSON transition logs include order and actor IDs; HTTP logs include generated request IDs, method, route, status and elapsed time. Authentication headers, passwords and webhook payloads are not logged. `/health` tests process liveness. `/ready` checks database connectivity and the migrated schema marker. These public probes disclose no merchant data.

This local baseline does not include user provisioning, password recovery, production hosting, login rate limiting, external tax calculation, partial refunds, returns logistics, or real payment processing. Browser tokens live in memory and expire after one hour; refresh requires sign-in. Orders and catalog lists have bounded pagination; catalog supports name search and orders support status filtering.
