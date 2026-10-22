# Delivery verification

Verification completed October 22, 2026. Working baseline: `bde8d76306793b46ccdffeab1e29a50a7492bf02`. Later main-branch documentation commits record these results without changing the tested application. All three scenarios branch independently from that same healthy baseline.

## Executed results

The implementation was tested natively on Windows with Python 3.14.7, Node.js 22.19.0, and an isolated PostgreSQL 18 cluster bound to 127.0.0.1:55432. The existing PostgreSQL service/data was not modified. CI and Compose target Python 3.12, Node 22 and PostgreSQL 16.

From `backend`, with the project requirements installed:

```powershell
$env:DATABASE_URL='postgresql+psycopg://orderflow@127.0.0.1:55432/orderflow'
$env:TEST_DATABASE_URL='postgresql+psycopg://orderflow@127.0.0.1:55432/orderflow_test'
alembic upgrade head
python -m app.seed
pytest -q
ruff check .
ruff format --check .
alembic check
```

Observed: both schema migrations applied, synthetic seed loaded, **30 tests passed**, Ruff passed, all 17 Python files formatted, and Alembic reported `No new upgrade operations detected.` The full suite passed again after switching back from the deliberate regression branches. Tests cover rounding/discount bounds, input validation, tenant and customer isolation, product persistence, price snapshots, sequential/concurrent checkout idempotency, last-unit contention, authenticated callbacks, sequential/concurrent event replay, failed/late/mismatched events, rollback, cancellation, fulfillment, refunds, large totals, and production simulator restrictions.

From `frontend`:

```sh
npm ci
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
npm audit --audit-level=moderate
```

Observed: Prettier passed, TypeScript and production build passed, **3 browser tests passed** in Chromium against the real running API and PostgreSQL. Journeys: product creation → checkout → payment → fulfillment → full refund; failed payment with released stock; another customer's order hidden in UI and denied through direct API access. Initial test run exposed an icon/accessible-name locator mismatch; the navigation now has an explicit accessible label. An editing-triggered Vite reload interrupted a separate attempt; all journeys subsequently passed against a stable app. A later desktop/mobile visual inspection reported no browser JavaScript errors and no horizontal overflow at 390px.

`npm audit` and `pip-audit --local` both reported no known vulnerabilities in the tested environments. Vite was updated to 7.3.7 before final verification. A non-failing Starlette warning recommends httpx2 for future test-client integration; this baseline's pinned httpx tests run successfully.

`docker compose config --quiet` passed. PowerShell developer script syntax parsing passed. Docker Desktop's Linux engine remained unavailable (`dockerDesktopLinuxEngine` pipe missing), including after attempted startup. **The full Docker image build/Compose startup was not executed successfully locally.** The checked-in CI workflow performs that container-level and PostgreSQL 16/browser verification when GitHub Actions runs. Local results are not a claim that remote CI passed.

## Independently verified maintenance regressions

Each focused test passes on the healthy baseline. Each scenario adds one application-code regression, then a documentation-only commit recording actual expected failure. No tests were weakened or changed on scenario branches. Exact failure excerpts intentionally omit expanded expressions containing synthetic test credentials.

### scenario/duplicate-payment-webhook

- Initial healthy commit: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.
- Broken application commit: `b43e730af2291759049a15fb7604326372fe4b06`.
- Branch tip including its issue/reproduction report: `a00483f81bfe2bfe3ecfb539cced2d07ee67fbd2`.
- Command from backend with disposable PostgreSQL configured: `pytest -q tests/test_integration.py::test_duplicate_webhook`.
- Exit code: 1, expected application assertion failure.

```text
E           AssertionError: assert 2 == 1
FAILED tests/test_integration.py::test_duplicate_webhook - AssertionError: as...
1 failed, 1 warning in 1.42s
```

### scenario/tenant-order-leak

- Initial healthy commit: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.
- Broken application commit: `e189bc7241547ba30647cdf2921b264bcaa41ce7`.
- Branch tip including its issue/reproduction report: `5a3c5f0adea7e7b0d917aed2193cba63dfb44279`.
- Command from backend with disposable PostgreSQL configured: `pytest -q tests/test_integration.py::test_tenant_order_isolation`.
- Exit code: 1, expected application assertion failure.

```text
E       AssertionError: assert 200 in {403, 404}
FAILED tests/test_integration.py::test_tenant_order_isolation - AssertionErro...
1 failed, 1 warning in 1.36s
```

### scenario/inventory-oversell

- Initial healthy commit: `bde8d76306793b46ccdffeab1e29a50a7492bf02`.
- Broken application commit: `53a7031c73e5de4712032e9f04a6b4503ae04f25`.
- Branch tip including its issue/reproduction report: `558874d11a8927cdd1a66d6480d911508cf2fae0`.
- Command from backend with disposable PostgreSQL configured: `pytest -q tests/test_integration.py::test_last_unit_contention`.
- Exit code: 1, expected application assertion failure.

```text
E       assert 2 == 1
FAILED tests/test_integration.py::test_last_unit_contention - assert 2 == 1
1 failed, 1 warning in 0.93s
```

## Handoff and limits

The main branch is the working reference. Stop the app, ensure a clean checkout, switch to a scenario branch, rebuild, and run its focused check. Return to main and rebuild before ordinary demonstrations. Issue reports in `docs/maintenance-cases` describe symptoms and observations without providing repair instructions.

The app intentionally supports local simulated payments, full refunds, one merchant membership per user, and a fixed demonstration tax rate. There is no Stripe adapter, real money processing, user provisioning, production hosting setup, physical returns workflow, or autonomous maintenance agent. A future real provider adapter needs durable reconciliation/outbox handling before it can be deployed safely.

## GitHub delivery status

Local implementation and scenario commits are complete. Pushing on October 22, 2026 returned HTTP 403: Git authenticated as `Gaurav23p24`, which does not have write access to `gaurav-patel-28/order-processing-application`. The connected GitHub integration also reports `permissions.push = false`. Remote CI has therefore not run. No remote history was replaced.

The completed checkout and all four local branches are in `G:\Projects\order-processing-application`. After granting the signed-in account write access or signing Git into an authorized account, run:

```powershell
git -C G:\Projects\order-processing-application push -u origin main scenario/duplicate-payment-webhook scenario/tenant-order-leak scenario/inventory-oversell
```
