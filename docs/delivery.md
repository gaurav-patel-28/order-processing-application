# Scenario verification

Branch: `scenario/tenant-order-leak`.

Healthy baseline: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.

Broken application commit: `e189bc7241547ba30647cdf2921b264bcaa41ce7`.

Focused command: `pytest -q tests/test_integration.py::test_tenant_order_isolation` from backend, with disposable PostgreSQL configured.

Observed output (exit 1, intentional failure):

```text
E       AssertionError: assert 200 in {403, 404}
FAILED tests/test_integration.py::test_tenant_order_isolation - AssertionErro...
1 failed, 1 warning in 1.36s
```

Use the issue report in docs/maintenance-cases for symptoms/reproduction. Return to main for the healthy implementation and complete delivery record.
