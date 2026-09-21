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

Edit `.env` and set `ADO_ORG_URL`, `ADO_PAT`, and `ADO_DEFAULT_PROJECT`. Until
these are set, submissions are cached locally and marked *Queued*; once ADO is
reachable the worker pushes them automatically (retry every
`ADO_RETRY_INTERVAL_SECONDS`).

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

## Deploying to Kubernetes

Manifests live in `deploy/k8s` (kustomize). They deploy Postgres, Redis, the
backend (with a migration init-container), the worker, the frontend, and an
ingress that routes `/api` to the backend and everything else to the SPA. The
image references point at `ghcr.io/zollo/azuregos-{backend,frontend}`, matching
what CI publishes.

### 1. Make the GHCR packages public (one-time)

The images are published to GHCR. GHCR packages are **private by default**, so
after CI first publishes them, set each package's visibility to **Public** so
the cluster can pull them without credentials:

> github.com/zollo → **Packages** → `azuregos-backend` → **Package settings** →
> **Danger Zone → Change visibility → Public**. Repeat for `azuregos-frontend`.

Because the packages are public, the deployments need no `imagePullSecrets`. If
you'd rather keep them private, create a pull secret instead:

```bash
kubectl create secret docker-registry ghcr-pull \
  --namespace azuregos \
  --docker-server=ghcr.io \
  --docker-username=zollo \
  --docker-password='<GHCR_PAT_with_read:packages>'
```

...and add `imagePullSecrets: [{ name: ghcr-pull }]` to each deployment's pod
spec.

### 2. Deploy

```bash
# Optionally pin image tags for reproducible rollouts, then apply
cd deploy/k8s
kustomize edit set image \
  ghcr.io/zollo/azuregos-backend=ghcr.io/zollo/azuregos-backend:<tag> \
  ghcr.io/zollo/azuregos-frontend=ghcr.io/zollo/azuregos-frontend:<tag>
kubectl apply -k .
```

Before applying, replace the placeholder values in `config.yaml` (the `Secret`
especially) using your secrets manager. Because the ingress serves the API and
SPA on one host, build the frontend image with
`--build-arg VITE_API_BASE_URL=https://<your-host>`.

## CI

`.github/workflows/ci.yml`:

1. **backend** — ruff lint + pytest
2. **frontend** — type-check, build, vitest
3. **images** — on push, build & push both container images to GHCR
   (`ghcr.io/<owner>/azuregos-backend` and `-frontend`) with buildx cache.

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
deploy/k8s/         Kubernetes manifests (kustomize)
```

## License

Provided as-is for internal use. Add your organization's license here.
