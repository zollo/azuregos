# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Azuregos is a service-desk front end for Azure DevOps (ADO): non-ADO users submit and track tickets through admin-defined **portals**; each ticket becomes an ADO work item.

## Commands

Full stack (Docker; `docker-compose.override.yml` is auto-merged for hot reload):
```bash
make up                      # creates .env from .env.example if missing, then compose up --build
docker compose -f docker-compose.yml up --build   # prod-like, no dev override
```

Backend (`cd backend`):
```bash
pip install ".[dev]"
ruff check .
pytest -q -m "not functional"                          # unit tests
pytest tests/test_ticket_service.py::test_build_tags   # single test
pytest -q -m functional       # live ADO tests; needs ADO_ORG_URL/ADO_PAT in env or backend/.env.test (auto-skipped otherwise)
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app.celery_app worker --beat --loglevel=info
```

Frontend (`cd frontend`):
```bash
npm install
npm run dev                          # Vite on :5173; set VITE_API_BASE_URL=http://localhost:8000
npm run build                        # tsc (strict, noUnused*) + vite build
npm test                             # vitest
npx vitest run src/api/client.test.ts   # single test file
```

The primary dev box (WSL) has no `pip`, `node`, or `docker`, so local checks are limited to `python3 -m compileall`; CI is the real validator for lint, `tsc`, tests, and container builds.

## Architecture

**Services:** `backend` (FastAPI), `worker` (same backend image running Celery + embedded beat), `frontend` (React/Vite SPA served by nginx), Postgres, Redis (Celery broker only — no durable data).

**Ticket lifecycle / offline cache** (`services/ticket_service.py`, `workers/tasks.py`): a submission is always persisted to the `tickets` table first, then pushed to ADO best-effort. If the push fails the row stays `pending` and the beat-scheduled `retry_pending_tickets` task retries it every `ADO_RETRY_INTERVAL_SECONDS`. `SyncStatus`: `pending → syncing → synced`, or `failed` once a non-retryable error (4xx other than 429) occurs or `ADO_MAX_RETRY_ATTEMPTS` is hit. The `tickets` table *is* the offline cache.

**ADO connection** (`services/ado_connection.py`): either the `ADO_*` env vars or a connection an admin saves at `/admin/ado` (singleton `ado_connection` row, PAT Fernet-encrypted with a key derived from `SECRET_KEY`). A saved connection wins and replaces the env vars as a whole; deleting it reverts. It's read per call, so always get a client via `await get_ado_client(db)` and use `client.default_project`, never `settings.ado_*` directly.

**ADO integration** (`services/ado_client.py`): thin httpx client over REST 7.1 with PAT Basic auth; `ADOError.retryable` drives the retry loop. Azuregos metadata lives in ADO **tags**, not custom fields: `azuregos`, `azuregos-portal:<slug>`, `azuregos-submitter:<email>` (lets "my tickets" be recovered via WIQL). Notable conversions:
- Area paths: classification nodes come back as `\Proj\Area\Team`; `System.AreaPath` wants `Proj\Team` (`area_node_to_path`).
- Discussion uses the comments **preview** API (`7.1-preview.4`). Replies are posted under the PAT identity, so the API prepends a `Name (email) via Azuregos:` attribution. ADO HTML is converted to plain text (`html_to_text`) before reaching the UI.

**Portals** are modular forms: `Portal.fields` is JSONB of `FieldDefinition`. Title and Description ("Discussion") are implicit and never stored in `fields`. A field with `ado_field_ref` maps onto a real ADO field; unmapped fields are appended to the work-item description. `build_ado_fields` applies the portal's `area_path` **after** custom mappings so a submitter can't override it. On save, `work_item_type` and `area_path` are validated against live ADO data — skipped when ADO is unconfigured or the error is transient, but a 404 project is rejected.

**Icons & catalog** (`api/routes/portals.py`): an empty `icon` means "inherit/default". `effective_portal_icon` = portal icon → category icon → `ticket`; it's returned as `PortalRead.effective_icon` and as the icon in catalog summaries. The frontend renders names through a curated Lucide map in `components/Icon.tsx` — new icons must be added there. `GET /api/portals/catalog` returns every category (empty ones are greyed out in the UI); the virtual `General` group appears only when uncategorized portals exist. Descriptions are Markdown, rendered with `react-markdown` (raw HTML disabled).

**Frontend ↔ API is same-origin:** the SPA calls relative `/api`; the frontend nginx reverse-proxies `/api`, `/docs`, `/openapi.json` to `backend:8000` using Docker's resolver (`127.0.0.11`) so nginx boots even when the backend is down. `VITE_API_BASE_URL` is only for the Vite dev server. In k8s the ingress routes `/api` to the backend instead.

**Auth:** JWT bearer stored in localStorage. Local accounts, OIDC (stateless — `state` is a short-lived signed JWT), and SAML (python3-saml, imported lazily so the app boots without xmlsec). Federated logins redirect to `<first CORS_ORIGINS entry>/auth/callback#token=…`. A bootstrap super admin is created on startup from `BOOTSTRAP_ADMIN_*`.

**Roles** (`models/user.py`): `super_admin` > `admin` > `portal_admin` > `end_user`. Super admins do everything, and only they can grant `super_admin`, change a super admin's account, or use the ADO connection (`/api/ado/connection*`). Admins manage portals, categories, users and the whole queue. Portal admins are assigned portals via the `portal_admins` table and can list/edit only those portals and see/retry their tickets; they can't create or delete portals. Route deps: `get_current_staff` (any admin role; the route must still check `user.can_manage_portal`), `get_current_admin` (admin or super), `get_current_super_admin`. The last active super admin can't be demoted, disabled or deleted. The frontend mirrors the rules in `src/auth/roles.ts` for what it shows; the API is what enforces them.

**Build info:** `APP_VERSION`/`GIT_COMMIT`/`BUILD_TIME` build-args are baked into both images (backend `AZUREGOS_*` env, frontend `VITE_*`), surfaced by auth-only `GET /api/build-info` and the `/info` page. Keep these ARGs late in the Dockerfiles to avoid busting cached layers.

## Gotchas (each has bitten this repo)

- **FastAPI 0.115:** don't annotate 204 routes with `-> None` — it's inferred as a response model and crashes app startup. `tests/test_app_smoke.py` builds the app + OpenAPI schema to catch this class of bug.
- **Celery tasks** run each invocation in a fresh `asyncio.run`; use `db.create_worker_engine()` (NullPool, disposed per run), never the shared pooled engine.
- **Migrations** are hand-written in `app/migrations/versions/` and chained via `down_revision`. That directory has relaxed ruff rules (E501/I001).
- **Slugs** regenerate only when the name actually changes, and `_unique_slug` must exclude the current row.
- SQLAlchemy relationship forward refs stay quoted; ruff `UP037` is intentionally ignored. `known-first-party = ["app"]`.
- **TypeScript:** import `type FormEvent` / `type ReactNode` from `react`; don't use the `React.*` namespace (it's a UMD global in modules and fails strict `tsc`).
- JSX attribute strings don't process backslash escapes (`"Proj\Team"`, not `"Proj\\Team"`).
- **Healthchecks:** the worker reuses the backend image, so any compose that runs it must override the inherited HTTP healthcheck (it uses `celery inspect ping`). Frontend checks must hit `127.0.0.1`, not `localhost` — busybox wget tries `::1` first and nginx listens IPv4-only. TrueNAS stays "Deploying" until every container is healthy.

## CI, releases & conventions

`.github/workflows/ci.yml`: backend (ruff + pytest), frontend (build + vitest), smoke (base compose boots the backend and asserts `/api/health/ready` reports `database: true`) on every PR and push. **Only on push to `main`:** `version` computes the next semver (seeded at `v1.0.0`; `mathieudutour/github-tag-action` thereafter), tags and creates a GitHub release; `images` builds both images tagged `latest`/`X.Y.Z`/`X.Y`/`sha-<short>`, signs them with cosign (keyless OIDC) and pushes a build-provenance attestation. These two jobs can't be exercised on a PR branch.

The repo is **squash-merge only**, with the squash commit title = PR title, and merged branches are auto-deleted. The PR title therefore drives the version bump and must be a Conventional Commit (enforced by `.github/workflows/pr-title.yml`): `feat:` → minor, `fix:`/other types → patch, `!` or a `BREAKING CHANGE` footer → major. Work happens on a branch with a PR into `main` (see `CONTRIBUTING.md`).

## Deployments

- `docker-compose.yml` (+ dev override) — local/dev; builds images from source.
- `deploy/truenas/` — TrueNAS SCALE compose using the published GHCR images. Only the frontend port (default 30080) is published, Postgres data lives on a host dataset, and every secret is an env var with an insecure placeholder default.
- `charts/azuregos/` — Helm chart, published by CI to `oci://ghcr.io/zollo/charts/azuregos` (version = release). The backend runs `alembic upgrade head` in an init container; the worker stays at 1 replica (beat).
- GHCR packages `ghcr.io/zollo/azuregos-{backend,frontend}` are public (no pull secret needed).
