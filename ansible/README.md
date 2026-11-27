# Ansible collection: how it's built

This directory holds the `zollo.azuregos` collection and the generator that writes most of it.
For using the collection, see its
[README](ansible_collections/zollo/azuregos/README.md).

```
ansible/
  openapi.json                 snapshot of the API's OpenAPI spec (generated, committed)
  generator/
    generate.py                spec + resources.yml -> modules, role task files, docs
    resources.yml              which API operations make up which module (hand-written)
  ansible_collections/zollo/azuregos/
    plugins/modules/*.py       GENERATED: one per resource / info / action
    plugins/module_utils/      hand-written runtime: auth, HTTP, schema checks, idempotency
    plugins/doc_fragments/     hand-written: connection options, attributes
    plugins/filter/            hand-written: export_config (used by the export role)
    roles/configure/           tasks/main.yml hand-written; per-resource tasks + argument_specs GENERATED
    roles/export/              tasks hand-written; vars/main.yml GENERATED
    playbooks/                 configure.yml, export.yml
    meta/runtime.yml           GENERATED (action group `all` for module_defaults)
  tests/
    unit/                      pytest: generator vs. spec, runtime helpers, export filter
    e2e/ + run-e2e.sh          playbooks against a live API with an empty database
```

## Why a generator of our own

Off-the-shelf OpenAPI-to-Ansible generators exist, but they don't fit well: Red Hat's
(gouttelette / the vmware_rest tooling) is built around one vendor's API conventions, and the
generic OpenAPI client generators produce SDKs, not idempotent modules. What makes an Ansible
module good (find the existing object, compare, change only what differs, support check and diff
mode, never echo secrets) needs a few facts the spec doesn't carry: which field identifies an
object, which fields are write-only, and that PATCH bodies are partial. So the split is:

- **From the spec, automatically:** every option and suboption, its type, choices, required
  suboptions, the API's defaults, length/pattern/format constraints, descriptions, and the
  `RETURN` docs. The request schemas are also embedded in each module so values are checked
  against them before anything is sent.
- **From `resources.yml`, by hand, a few lines per module:** the operations, the identity key,
  write-only and unordered fields, and examples.

`DOCUMENTATION` and the argument spec are written from the same data, and `ansible-test sanity`
(validate-modules) checks that they agree.

## After an API change

```bash
pip install ./backend ansible-core
python ansible/generator/generate.py --export-spec
git add ansible/ backend/
```

CI runs `generate.py --export-spec --check`, which fails when:

- `openapi.json` or any generated file is stale, or
- an operation under `/api` is neither used by a module nor listed under `ignore` in
  `resources.yml` (with a reason), or
- an API field would clash with a connection option (`api_url`, `api_token`, `api_username`,
  `api_password`, `validate_certs`, `api_timeout`).

So a new endpoint can't land without deciding what the collection does with it. A new field
on an existing schema needs nothing beyond regenerating: it shows up in the module, the
configure role's argument spec and task files, and the export role.

Describe fields with `Field(description=...)` in `backend/app/schemas/`; that text is the module
documentation.

## Tests

```bash
ruff check ansible
pytest -q ansible/tests/unit
(cd ansible/ansible_collections/zollo/azuregos && ansible-test sanity --venv --python 3.12)

# against a running API with an empty database and a bootstrap super admin
AZUREGOS_URL=http://localhost:8000 AZUREGOS_USERNAME=admin@example.com \
  AZUREGOS_PASSWORD=... ansible/tests/run-e2e.sh
```

The e2e script runs every module (idempotency, check mode, diff, client-side validation, API
errors), then the configure role in check mode, for real, and again (the second run must
report no changes), then exports the instance and re-applies the export (again no changes).
CI runs it against a fresh Postgres service.

## Releases

On every merge to `main`, after the server release `vX.Y.Z` is created, the `collection` job in
`.github/workflows/ci.yml` checks whether anything under `ansible/` changed since the last
`collection/*` tag. Because the drift check forces every API change into `openapi.json`, every
API change counts. If so it stamps `version: X.Y.Z` into `galaxy.yml`, builds
`zollo-azuregos-X.Y.Z.tar.gz`, attaches it to the `vX.Y.Z` GitHub release, adds an install line
to the release notes and pushes the tag `collection/X.Y.Z`. Collection versions therefore match
the server version they were built from, with gaps where the API didn't change.

The collection is never published to Ansible Galaxy.
