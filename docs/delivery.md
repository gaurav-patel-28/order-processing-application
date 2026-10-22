# Delivery verification

The initial healthy implementation and the three isolated scenario branch commits are recorded below after execution. The scenario issue reports describe symptoms and focused checks without disclosing repair instructions.

## Executed baseline checks

- Backend suite against isolated native PostgreSQL 18 on Windows; real migrations and transactions.
- Ruff lint and formatting checks.
- Alembic schema drift check.
- TypeScript checking and production Vite build.
- Three real Chromium browser workflows against the running native API and PostgreSQL database.
- Docker Compose configuration validation and PowerShell developer-script syntax parsing.
- Dependency audits through npm and pip-audit.

Exact final test counts, commit IDs, and intentional failure excerpts are added when branch verification is complete. Docker Desktop's engine has not been available in this environment; full container runtime and GitHub Actions execution are separate checks and are not claimed as locally passed.
