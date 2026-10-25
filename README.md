# Azuregos

A service-desk front end for **Azure DevOps** — think "Jira Service Management,
but the tickets live as ADO work items." Azuregos lets people who don't have
Azure DevOps access submit and track work items through friendly, admin-defined
forms called **portals**.

## Concepts

- **Portal** — a modular form that fronts an ADO work-item type, exposing only
  the fields an admin chooses. **Title** and **Discussion** (description) are
  always present; everything else is configurable.
- **Category** — portals are grouped for browsing. Uncategorized portals appear
  under a virtual **General** category.
- **Ticket** — a submission through a portal. It's persisted locally first
  (the **offline cache**) and then pushed to ADO. If ADO is unreachable, a
  background worker retries until it succeeds.
- **Metadata as tags** — Azuregos stores its metadata on the ADO work item as
  tags rather than requiring custom fields:
  - `azuregos` — marks the item as Azuregos-managed
  - `azuregos-portal:<slug>` — the originating portal
  - `azuregos-submitter:<email>` — who submitted it

## Personas

- **Admin** — creates and manages portals, categories, and users.
- **End-user** — browses portals by category, submits requests, tracks the
  status of their own tickets.

## Authentication

- Local accounts (email + password)
- OIDC / OAuth2 (Authorization Code flow) — set `OIDC_*`
- SAML 2.0 — set `SAML_*`

Federated users are provisioned on first login as end-users; an admin can
promote them.

## Architecture

```
                 ┌────────────┐        ┌──────────────┐
 Browser ───────▶│  frontend  │        │  Azure DevOps│
                 │ (React/nginx)        └──────▲───────┘
                 └─────┬──────┘               │ REST API
                       │ /api                 │
                 ┌─────▼──────┐   push/retry  │
                 │  backend   │───────────────┘
                 │ (FastAPI)  │
                 └──┬─────┬───┘
        SQLAlchemy  │     │  Celery tasks
                 ┌──▼──┐ ┌▼─────┐   ┌──────────┐
                 │ PG  │ │Redis │◀──│  worker  │ (Celery + beat: retry loop)
                 └─────┘ └──────┘   └──────────┘
```

- **backend** — FastAPI REST API (`backend/app`)
- **worker** — same image, runs Celery + beat; drains the offline cache to ADO
- **frontend** — React + Vite SPA served by nginx
- **postgres** — portals, categories, users, tickets (+ the offline cache)
- **redis** — Celery broker/result backend

## Quick start (Docker)

```bash
make init      # creates .env from .env.example
make up        # builds & starts the full stack (dev mode, hot reload)
```

Then open:

- Frontend: http://localhost:8080
- API docs: http://localhost:8000/docs

Sign in with the bootstrap admin from `.env`
(`admin@azuregos.local` / `admin` by default — **change these**).

> The dev stack uses `docker-compose.override.yml` automatically for hot-reload.
> For a production-like run: `docker compose -f docker-compose.yml up --build`.

### Configure Azure DevOps

There are two ways to connect Azure DevOps:

- **Environment variables:** set `ADO_ORG_URL`, `ADO_PAT`, and
  `ADO_DEFAULT_PROJECT` in `.env` (or your Helm values / TrueNAS env).
- **Admin UI:** sign in as an admin and open **Admin → Azure DevOps**. Enter the
  organization URL, a PAT, and an optional default project, use **Test
  connection**, then **Save**. The values are checked against ADO before saving
  and the PAT is stored encrypted (derived from `SECRET_KEY`); it is never
  shown again.

**Precedence:** a connection saved in the UI wins over the env vars and
replaces them as a whole (they're never mixed field by field). **Remove saved
connection** reverts to the env vars. Changes apply immediately to the API and
the worker, no restart needed. Switching to a *different* organization (by
saving or by removing the saved connection) is refused while any ticket is
linked to a work item, since tickets only store the work-item ID. Rotating `SECRET_KEY` makes a saved PAT
unreadable: the page then shows an error and the PAT must be re-entered.

Until a connection is configured, submissions are cached locally and marked
*Queued*; once ADO is reachable the worker pushes them automatically (retry
every `ADO_RETRY_INTERVAL_SECONDS`).

## Local development without Docker

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install ".[dev]"
export $(grep -v '^#' ../.env | xargs)   # or set vars manually
alembic upgrade head
uvicorn app.main:app --reload
```

Worker:

```bash
cd backend
celery -A app.workers.celery_app.celery_app worker --beat --loglevel=info
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## Testing

```bash
make backend-test     # pytest (unit only)
make frontend-test    # vitest
# or directly:
cd backend && pytest -q -m "not functional"
cd frontend && npm test
```

### Functional tests against a live Azure DevOps instance

`backend/tests/functional/` exercises the real ADO REST API through `ADOClient`
and the Azuregos tag/description conventions (create → fetch → find-by-tag,
mapped fields, error handling). They **require a PAT** and are **skipped**
automatically when one isn't configured, so they're safe to leave in CI.

```bash
cp backend/.env.test.example backend/.env.test   # git-ignored
# edit backend/.env.test: set ADO_ORG_URL and ADO_PAT (use a scoped, disposable token)
make functional-test           # or: cd backend && pytest -q -m functional
```

Every work item the suite creates is deleted in teardown. Use a **dedicated,
short-lived PAT** (Work Items: Read & Write) and revoke it afterward — never
commit it.

## Deploying to TrueNAS SCALE

A ready-made compose tuned for TrueNAS SCALE (Electric Eel 24.10+) lives in
[`deploy/truenas/`](deploy/truenas/). It uses the published GHCR images,
publishes a single port (the frontend reverse-proxies `/api` to the backend),
and keeps Postgres on a host dataset for snapshots. See
[deploy/truenas/README.md](deploy/truenas/README.md).

> The frontend is **origin-portable**: the SPA calls `/api` relatively and the
> frontend's nginx proxies it to the backend, so one image works behind any host
> (TrueNAS, k8s ingress, compose) with no baked API URL and no CORS. Set
> `VITE_API_BASE_URL` only when the API is on a different origin (e.g. Vite dev).

## Deploying to Kubernetes

The Helm chart in `charts/azuregos` deploys the backend (with an
`alembic upgrade head` init container), the worker (Celery + beat, one replica),
the frontend, Postgres (StatefulSet + PVC), Redis, and an Ingress that sends
`/api`, `/docs`, `/redoc` and `/openapi.json` to the backend and everything else
to the SPA. Every release publishes it to GHCR with the same version as the
images, so a chart version always deploys the matching images:

```bash
kubectl create namespace azuregos
kubectl -n azuregos create secret generic azuregos-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD="$(openssl rand -hex 12)" \
  --from-literal=ADO_PAT='<pat>'

helm install azuregos oci://ghcr.io/zollo/charts/azuregos -n azuregos \
  --set existingSecret=azuregos-secrets \
  --set ingress.enabled=true --set ingress.hosts[0]=azuregos.example.com \
  --set config.CORS_ORIGINS=https://azuregos.example.com \
  --set config.ADO_ORG_URL=https://dev.azure.com/<org> --set config.ADO_DEFAULT_PROJECT=<project>
```

See `charts/azuregos/values.yaml` for everything else: external Postgres/Redis,
resources, and `postgresql.backup` (a nightly `pg_dump` CronJob to its own PVC,
e.g. on NFS; restore with `pg_restore --clean --if-exists`). The GHCR packages
are public, so no pull secret is needed.

## CI / releases

`.github/workflows/ci.yml` runs on every PR and every push to `main`:

1. **backend** — ruff lint + pytest
2. **frontend** — type-check, build, vitest
3. **smoke** — boots the backend against ephemeral Postgres/Redis and checks
   `/api/health/ready`

On a **merge to `main`** (after the above pass) two more jobs run:

4. **version** — computes the next **semantic version** from commit history
   (Conventional Commits: `feat:` → minor, `fix:` → patch, `BREAKING CHANGE`
   → major; default patch), creates the `vX.Y.Z` git tag and a GitHub release.
   PRs are squash-merged with the **PR title as the commit subject**, so the
   PR title drives the bump (a `PR Title` check enforces the format — see
   [CONTRIBUTING.md](CONTRIBUTING.md)).
5. **images** — builds & pushes both images to GHCR tagged `latest`, `X.Y.Z`,
   `X.Y`, and `sha-<short>`; then **signs** each image with cosign (keyless,
   via GitHub OIDC — recorded in the Rekor transparency log) and generates a
   **build-provenance attestation** pushed to the registry.

### Verifying an image

```bash
IMAGE=ghcr.io/zollo/azuregos-backend:latest

# Signature (keyless / GitHub OIDC identity)
cosign verify "$IMAGE" \
  --certificate-identity-regexp "https://github.com/zollo/azuregos/.github/workflows/ci.yml@.*" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com

# Build provenance attestation
gh attestation verify "oci://$IMAGE" --repo zollo/azuregos
```

## Project layout

```
backend/            FastAPI app, Celery worker, Alembic migrations
  app/
    api/routes/      auth, users, categories, portals, tickets, health
    core/            security (JWT/passwords), auth providers (OIDC/SAML)
    models/          SQLAlchemy models
    schemas/         Pydantic schemas
    services/        ADO client, ticket + user services
    workers/         Celery app + retry task
    migrations/      Alembic
frontend/           React + Vite SPA
  src/
    api/             typed fetch client
    components/      Layout, guards, field renderer, badges
    context/         auth context
    pages/           catalog, portal form, tickets, admin/*
charts/azuregos/    Helm chart (published to oci://ghcr.io/zollo/charts/azuregos)
```

## License

Provided as-is for internal use. Add your organization's license here.
