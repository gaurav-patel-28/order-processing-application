# Scenario verification

Branch: `scenario/inventory-oversell`.

Healthy baseline: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.

Broken application commit: `53a7031c73e5de4712032e9f04a6b4503ae04f25`.

Focused command: `pytest -q tests/test_integration.py::test_last_unit_contention` from backend, with disposable PostgreSQL configured.

Observed output (exit 1, intentional failure):

```text
E       assert 2 == 1
FAILED tests/test_integration.py::test_last_unit_contention - assert 2 == 1
1 failed, 1 warning in 0.93s
```

Use the issue report in docs/maintenance-cases for symptoms/reproduction. Return to main for the healthy implementation and complete delivery record.
