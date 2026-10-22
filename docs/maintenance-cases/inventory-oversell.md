# Two customers can both reserve the last unit

Branch: `scenario/inventory-oversell`. Use synthetic local data only.

## User report

Two customers submit orders for the final unit at nearly the same time and both receive successful reservations. The resulting orders cannot both be fulfilled from the available stock.

## Reproduce

```sh
docker compose --profile test run --build --rm tests pytest -q tests/test_integration.py::test_last_unit_contention
```

Native equivalent, from `backend` with disposable PostgreSQL configured: `pytest -q tests/test_integration.py::test_last_unit_contention`.

The test starts with one unit and coordinates two separate PostgreSQL transactions at the inventory UPDATE boundary. Exactly one order must succeed; the other must receive a stock conflict. Available/reserved/sold must end at 0/1/0 with only one persisted order. On the affected branch both reservations succeed. This is a controlled interleaving, not a probabilistic stress test, and uses actual PostgreSQL locks and transactions. Observe order records, inventory counts, and the missing conflict response/log for the second reservation.

The healthy baseline and broken commit IDs, plus the captured failure, are recorded in [delivery verification](../delivery.md). Stop services, switch to main, rebuild, and rerun the focused check. Do not use SQLite for this exercise.
