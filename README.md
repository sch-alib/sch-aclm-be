# Certificate Automation Backend

FastAPI backend for DigiCert CertCentral certificate inventory, onboarding, new order submission, issuance checks, offboarding, and jobs. The frontend is maintained separately at `sch-alib/sch-aclm-fe`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Before starting with a **new database**, edit `.env` to set a unique unpredictable `JWT_SECRET` (32+ characters recommended) and a unique `BOOTSTRAP_ADMIN_PASSWORD` (at least 12 characters). Only an `admin` user is created on first startup. Existing databases are not reseeded or migrated; rotate any old demo account passwords before deployment. This repository has no user-management endpoint yet. Do not reuse the bootstrap password for other users. Keep `.env` private and restrict file permissions.

The sample `.env.example` uses `DIGICERT_MODE=mock`. For real DigiCert use, set `DIGICERT_MODE=real`, set the API key **only in `.env`**, and configure your organization's ID. Do not put credentials or the local SQLite database into Git. The existing deployment path remains experimental and requires `PFX_PASSWORD` in `.env`; it does not yet produce a valid PFX from an externally generated CSR. Do not enable production deployment on this basis.

```bash
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Tests

Run tests using a temporary SQLite database and mock DigiCert adapter, **not** a live account:

```bash
DIGICERT_MODE=mock python -m unittest discover -s tests -v
```

The test suite supplies its own temporary bootstrap values and never needs your real `.env` key. Keep the current working directory at the backend root when running the application or tests; paths for the database and artifacts are relative to it.

See the shared project documentation in the sibling `aclm/README.md` for feature-level details.
