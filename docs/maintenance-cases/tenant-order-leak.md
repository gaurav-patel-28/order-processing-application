# Staff can retrieve another merchant's order

Branch: `scenario/tenant-order-leak`. This security exercise must use synthetic local records only and must never be deployed with real merchant/customer data.

## User report

A staff member changes the order ID in a detail request and sees another merchant's order. Lists may still look normal. Changing a resource identifier must never cross organization boundaries.

## Reproduce

```sh
docker compose --profile test run --build --rm tests pytest -q tests/test_integration.py::test_tenant_order_isolation
```

Native equivalent, from `backend` with disposable PostgreSQL configured: `pytest -q tests/test_integration.py::test_tenant_order_isolation`.

The test creates an organization B order, confirms that B staff can view it, then requests the same ID with A staff credentials. Expected: a non-disclosing 404 or 403. Actual on the affected branch: 200 with the other merchant's order details. The API's request logs expose the unexpected success status; the test uses only synthetic organizations and accounts.

The healthy baseline and broken commit IDs, plus the captured failure, are recorded in [delivery verification](../delivery.md). Stop services, switch back to main, rebuild, and rerun the check to return to the healthy state. Never reuse real data with this branch.
