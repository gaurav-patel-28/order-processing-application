# Scenario verification

Branch: `scenario/duplicate-payment-webhook`.

Healthy baseline: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.

Broken application commit: `b43e730af2291759049a15fb7604326372fe4b06`.

Focused command: `pytest -q tests/test_integration.py::test_duplicate_webhook` from backend, with disposable PostgreSQL configured.

Observed output (exit 1, intentional failure):

```text
E           AssertionError: assert 2 == 1
FAILED tests/test_integration.py::test_duplicate_webhook - AssertionError: as...
1 failed, 1 warning in 1.42s
```

Use the issue report in docs/maintenance-cases for symptoms/reproduction. Return to main for the healthy implementation and complete delivery record.
