# Payment callback retry appears twice in order history

Branch: `scenario/duplicate-payment-webhook`. Use synthetic local data only.

## User report

The payment provider retried a valid callback. The order remains paid, but the history shows repeated processing of that payment. An order's consequential PAID event must appear exactly once, with exactly one stock consumption.

## Reproduce

Switch to the branch with a clean checkout and rebuild the test image:

```sh
docker compose --profile test run --build --rm tests pytest -q tests/test_integration.py::test_duplicate_webhook
```

Native equivalent, from `backend` with a disposable `TEST_DATABASE_URL` configured: `pytest -q tests/test_integration.py::test_duplicate_webhook`.

The check creates an order, obtains a valid signed simulator event, delivers the exact same bytes twice, and inspects persisted stock and events. Both callback requests should be harmless successes, with one PAID event and one reservation consumption. The affected branch instead persists an extra paid-history entry. Inspect `GET /orders/{id}/events` and the API transition logs alongside `webhook_duplicate` logs.

The healthy baseline and broken commit IDs, plus the captured failure, are recorded in [delivery verification](../delivery.md). After investigation run `docker compose down`, `git switch main`, and rebuild the app. The same focused check must pass on main.

## Executed reproduction

Initial healthy commit: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.

Broken application commit: `b43e730af2291759049a15fb7604326372fe4b06`.

Executed against isolated PostgreSQL 18; pytest exited 1 for the expected assertion:

```text
E           AssertionError: assert 2 == 1
FAILED tests/test_integration.py::test_duplicate_webhook - AssertionError: as...
1 failed, 1 warning in 1.42s
```
