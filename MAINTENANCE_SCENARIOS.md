# MAINTENANCE_SCENARIOS.md — Reproducible failures for a future repair agent

## Why these exist
The real product should be healthy on its default branch. The future **Autonomous Software Maintenance Engineer** must have real maintenance jobs: a changed application that is now broken, evidence of what users observe, and a way to verify whether a proposed fix restores correct behavior.

**We are not building the maintenance agent in this repository.** Codex must build the app, write the normal tests, then prepare isolated broken versions that a separate repair system can later investigate.

## Ground rules
1. **Never leave intentional defects in `main`**. `main` should be a clean, green reference implementation.
2. Create at least **three independent `scenario/*` Git branches** based on the clean baseline, each with one deliberately introduced *application-code* regression.
3. Each scenario should resemble a believable accidental edit (a missing filter, incorrect condition, mishandled retry). Avoid cartoon bugs, disabled tests, or deliberate syntax errors.
4. Each scenario must include a relevant executable regression test that expresses the correct expected behavior. The test passes on `main` and fails on the broken branch. If adding a new test, first add it to `main`, ensure it passes, and only then branch and change application code.
5. Keep secrets and actual user/payment data out of all scenarios. Do not deploy broken branches as production environments.
6. Document each scenario in `docs/maintenance-cases/` with a concise **issue report**: symptom, steps to reproduce, expected vs. actual result, failing command, observable logs/API response, initial healthy commit, broken commit, and branch. **Do not spell out the root-cause fix in the issue report**; keep a maintainer-only answer key in a separate file if useful.
7. Each branch must be independently checked out, started, and tested without changing other scenarios. Provide cleanup commands to return to a healthy checkout.
8. Verify the intended failure with actual command output. Don't claim scenario completeness based only on code inspection.

## Required scenarios

### Scenario 1 — Duplicate payment callback
**Branch:** `scenario/duplicate-payment-webhook`

**User report:** "The payment provider retried a callback. The order looks paid, but its event history shows repeated payment processing or inventory was consumed more than once."

- Create an actual regression in the code path that handles repeated payment-provider events or applies the payment-confirmed transition.
- Test: deliver the **same valid signed event twice**; assert only one consequential transition and exactly one consumption of reserved stock, and no duplicate financial effects.
- Expected red result: the broken branch violates at least one assertion. Expected green result: replaying the event is harmless.
- Make the scenario deterministic; don't require Stripe or a real network provider.

### Scenario 2 — Cross-organization order visibility
**Branch:** `scenario/tenant-order-leak`

**User report:** "A staff member in one merchant account can retrieve another merchant's order by changing the order ID in an API request."

- Introduce a believable regression in the order-detail query's tenant scope or authorization handling (not a blanket disable-auth flag).
- Test: organization A's authenticated staff request organization B's order; expect a non-disclosing `404` or `403`, and confirm authorized access still works.
- Expected red result: the broken branch exposes or permits access to the other organization's order. Expected green result: access is denied.
- Use **synthetic seeded records only**. This scenario is security-sensitive and must never be deployed with real customer data.

### Scenario 3 — Inventory reservation under contention
**Branch:** `scenario/inventory-oversell`

**User report:** "When two customers check out the last unit almost simultaneously, both orders sometimes succeed."

- Introduce a realistic regression in inventory reservation (e.g., remove atomicity or a conditional guard), not artificial return values.
- Test: start from exactly one available unit, coordinate two concurrent order submissions using separate transactions, and assert **exactly one** reserves successfully while inventory remains nonnegative and consistent.
- Expected red result: under a controlled interleaving, the broken branch creates two successful reservations or inconsistent inventory.
- Use PostgreSQL for this test. Make the race repeatable (synchronization/barriers or repeatable stress harness); if deterministic reproduction is not achieved, choose an alternative deterministic inventory invariant and disclose it rather than asserting success.

## Optional scenarios (after the three above work)
- `scenario/discount-rounding`: cents lost due to monetary rounding or incorrect discount order; unit test catches it.
- `scenario/cancel-releases-twice`: repeated cancellation returns inventory twice; integration test catches it.
- `scenario/stale-payment-event`: delayed failure event incorrectly changes a paid order back to failed; integration test catches it.

## Valuable monitoring signals
Provide structured error/transition logs and meaningful HTTP responses. If practical, include a simple `/metrics` endpoint or counters for payment webhook retries, inventory reservation conflicts, and failed order transitions. This lets a future maintenance agent discover issues from observable symptoms—not only a test runner.

## Branch creation workflow
Create a healthy baseline first. Make all tests green on the baseline. Commit it. Then for each scenario:

1. Branch from the same healthy baseline commit.
2. Introduce **one production-code regression** only.
3. Verify the expected check fails. Capture a small excerpt in the issue document.
4. Commit the scenario with a clear label such as `scenario: regression for webhook replay investigation`.
5. Return to the baseline before preparing the next scenario.
6. Push scenario branches only when remote access and permission are available. Never force-push.

On a machine with a remote and Docker, an illustrative workflow might look like:

```bash
# checkout the broken version
 git switch scenario/duplicate-payment-webhook
# use the repository's documented test command
 make test-integration
# inspect docs/maintenance-cases/ for the matching issue report
# return to healthy version
 git switch main
```

Actual commands should be finalized after implementation. Distinguish **expected failure of a deliberately broken branch** from an unrelated environment failure.

## How we will use these later
1. First, a human or Codex can run the existing app's tests to confirm the environment works.
2. Then we give a broken `scenario/*` repository version and its issue report to our **separate** maintenance-agent project.
3. The maintenance agent investigates, edits code in an isolated working copy, reruns checks, and proposes a patch/PR.
4. We assess whether the repair restores intended behavior **without weakening tests, changing requirements, or causing regressions**.

A passing test is evidence, not proof of total correctness. The maintenance agent must also explain its changes and any remaining uncertainty.
