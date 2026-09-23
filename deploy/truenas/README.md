# Azuregos on TrueNAS SCALE

A Docker Compose deployment tuned for **TrueNAS SCALE (Electric Eel 24.10+)**,
which runs Docker natively.

## Why this compose is TrueNAS-friendly

- **Prebuilt images** from GHCR — TrueNAS pulls, it doesn't build.
- **One published port.** The frontend reverse-proxies `/api` to the backend,
  so you reach everything on `http://<truenas>:30080` with no CORS and no baked
  API URL. Postgres, Redis, the API, and the worker stay on the internal
  network.
- **Data on a dataset.** Postgres (the source of truth) is bind-mounted to a
  host dataset you can snapshot and replicate. Redis is only the Celery broker,
  so it uses a managed volume.

## 1. Create the dataset

In the TrueNAS UI: **Datasets → Add Dataset**, e.g. `tank/apps/azuregos`
(swap `tank` for your pool). The Postgres data will land in an `postgres`
subfolder created automatically on first run.

> The Postgres container initializes and `chown`s its own data directory, so no
> manual permission changes are usually needed. If you locked the dataset ACL
> down, make sure the app can write to it.

## 2. Configure

Copy `.env.example` to `.env` and fill it in. At minimum set the three secrets:

```bash
cp .env.example .env
# generate values:
openssl rand -hex 32        # SECRET_KEY
openssl rand -hex 16        # POSTGRES_PASSWORD
openssl rand -hex 12        # BOOTSTRAP_ADMIN_PASSWORD
```

Set `AZUREGOS_DATA` to your dataset path, `AZUREGOS_PORT` to the host port, and
`AZUREGOS_PUBLIC_URL` to how users will reach it. Add your `ADO_*` values to
enable Azure DevOps syncing (you can do this later — tickets queue locally and
sync once configured).

## 3. Install

**Option A — Dockge / docker compose (recommended).** Put `docker-compose.yml`
and `.env` in a folder on a dataset and run:

```bash
docker compose up -d
```

**Option B — TrueNAS "Custom App".** Apps → Discover Apps → **Custom App** →
*Install via YAML*. Paste `docker-compose.yml`. Since the Custom App form has no
`.env`, either replace the `${...}` placeholders with literal values first, or
add the variables in the app's environment section.

## 4. First login

Open `http://<truenas-ip>:30080` and sign in with `BOOTSTRAP_ADMIN_EMAIL` /
`BOOTSTRAP_ADMIN_PASSWORD`. Change the password and create your portals.

## 5. Backups

Snapshot (and optionally replicate) the `AZUREGOS_DATA` dataset — it contains
the full Postgres database: portals, users, tickets, and the offline cache.
Redis holds no durable data.

For a portable dump instead:

```bash
docker exec azuregos-postgres pg_dump -U azuregos azuregos > azuregos-$(date +%F).sql
```

## 6. Updating

```bash
# pin a version in .env (AZUREGOS_TAG=<git-sha or tag>) or keep 'latest'
docker compose pull
docker compose up -d
```

Migrations run automatically on backend start (`alembic upgrade head`).

## Notes

- The GHCR images must be pullable. If they're private, either make the
  `azuregos-backend` / `azuregos-frontend` packages public, or
  `docker login ghcr.io` on the TrueNAS host first.
- To put Azuregos behind HTTPS, front it with the TrueNAS reverse proxy / your
  existing proxy (e.g. Traefik, nginx, Caddy) pointing at `AZUREGOS_PORT`, and
  set `AZUREGOS_PUBLIC_URL` to the https URL.
