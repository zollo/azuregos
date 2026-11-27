# zollo.azuregos

Ansible modules, roles and playbooks that configure an [Azuregos](https://github.com/zollo/azuregos)
instance through its REST API: the Azure DevOps connection, OIDC and SAML single sign-on,
catalog categories, portals and users.

The modules are **generated from the Azuregos OpenAPI spec**, so their options, types, choices,
constraints and descriptions are the API's own, and a new collection version is released with
every Azuregos release that changes the API. The collection is published as a GitHub release
asset only; it is not on Ansible Galaxy.

## Install

Collection `X.Y.Z` is built for Azuregos server `vX.Y.Z`; pick the release that matches (or is
the newest at or below) your server.

```bash
ansible-galaxy collection install \
  https://github.com/zollo/azuregos/releases/download/vX.Y.Z/zollo-azuregos-X.Y.Z.tar.gz
```

or in `requirements.yml`:

```yaml
collections:
  - name: https://github.com/zollo/azuregos/releases/download/vX.Y.Z/zollo-azuregos-X.Y.Z.tar.gz
    type: url
```

Requires ansible-core 2.15 or later and no Python packages beyond it. The modules call the API
from wherever they run, normally the controller (`connection: local`).

## Configure an instance in one go

Describe the instance in a vars file:

```yaml
# azuregos-config.yml
azuregos_url: https://azuregos.example.com
azuregos_username: admin@example.com
azuregos_password: "{{ vault_azuregos_admin_password }}"

azuregos_ado_connection:
  org_url: https://dev.azure.com/contoso
  pat: "{{ vault_ado_pat }}"
  default_project: IT

azuregos_oidc_settings:
  enabled: true
  discovery_url: https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration
  client_id: 00000000-0000-0000-0000-000000000000
  client_secret: "{{ vault_oidc_client_secret }}"
  button_label: Sign in with Microsoft

azuregos_categories:
  - name: Hardware
    icon: laptop
    sort_order: 10
  - name: Access
    icon: key-round

azuregos_portals:
  - name: Request a laptop
    category: Hardware          # a name; the role looks up category_id
    work_item_type: Issue
    area_path: IT\Hardware
    fields:
      - name: model
        label: Model
        type: select
        options: [MacBook Pro, ThinkPad X1]
        required: true

azuregos_users:
  - email: lead@example.com
    display_name: Help-desk lead
    password: "{{ vault_lead_password }}"
    role: portal_admin
    portals: [Request a laptop]  # names; the role looks up portal_ids
```

and apply it:

```bash
ansible-playbook zollo.azuregos.configure -e @azuregos-config.yml --ask-vault-pass
ansible-playbook zollo.azuregos.configure -e @azuregos-config.yml --check --diff   # preview
```

The `zollo.azuregos.configure` role waits for `/api/health/ready`, signs in once, then applies
the ADO connection, OIDC and SAML settings, categories, portals and users in that order. Every
item takes the options of the module of the same name, and the role's argument spec (generated
from the API schema) rejects unknown keys and bad values before anything is sent. Options you
leave out are left as they are on the server; `state: absent` deletes.

To start from an existing instance, export it:

```bash
ansible-playbook zollo.azuregos.export -e azuregos_url=https://azuregos.example.com \
  -e azuregos_username=admin@example.com -e azuregos_password=... \
  -e azuregos_export_path=./azuregos-config.yml
```

The file uses names instead of IDs and leaves out secrets (passwords, the PAT, the OIDC client
secret, the SAML SP key) because the API never returns them; add those from a vault before
applying it elsewhere.

## Use the modules directly

```yaml
- hosts: localhost
  connection: local
  gather_facts: false
  module_defaults:
    group/zollo.azuregos.all:
      api_url: https://azuregos.example.com
      api_token: "{{ azuregos_token }}"
  tasks:
    - zollo.azuregos.category:
        name: Hardware
        icon: laptop
      register: hw

    - zollo.azuregos.portal:
        name: Request a laptop
        category_id: "{{ hw.category.id }}"
```

Every module takes `api_url` plus either `api_token` or `api_username`/`api_password`; each also
falls back to
the `AZUREGOS_URL`, `AZUREGOS_TOKEN`, `AZUREGOS_USERNAME`, `AZUREGOS_PASSWORD` and
`AZUREGOS_VALIDATE_CERTS` environment variables. All of them support check mode, and the
resource modules support diff mode. `ansible-doc zollo.azuregos.<module>` shows each module's
options.

Resource modules find an object by its natural key (`name`, or `email` for users), or by `id` if
you pass one, which is how you rename. Nullable string fields (a portal's `category_id`,
`ado_project`, `area_path`) are cleared with an empty string. Passwords and the ADO PAT are
write-only, so they're sent on create only unless `update_password` / `update_pat` is `always`
(likewise `update_client_secret` and `update_sp_private_key` for SSO). The singleton modules
(`ado_connection`, `oidc_settings`, `saml_settings`) keep saved values for options you leave
out, so `enabled: false` alone switches a sign-in method off without losing its settings.

## Modules

<!-- BEGIN GENERATED MODULE TABLE -->
| Module | What it does | API operations |
|---|---|---|
| `zollo.azuregos.ado_area_path_info` | List Azure DevOps area paths of a project | `GET /api/ado/area-paths` |
| `zollo.azuregos.ado_connection` | Manage the Azure DevOps connection saved in Azuregos | `GET /api/ado/connection`<br>`PUT /api/ado/connection`<br>`DELETE /api/ado/connection` |
| `zollo.azuregos.ado_connection_info` | Show which Azure DevOps connection Azuregos uses | `GET /api/ado/connection` |
| `zollo.azuregos.ado_connection_test` | Test Azure DevOps connection values without saving them | `POST /api/ado/connection/test` |
| `zollo.azuregos.ado_project_info` | List the Azure DevOps projects Azuregos can see | `GET /api/ado/projects` |
| `zollo.azuregos.ado_work_item_type_info` | List Azure DevOps work item types of a project | `GET /api/ado/work-item-types` |
| `zollo.azuregos.build_info` | Show the Azuregos server's version and build | `GET /api/build-info` |
| `zollo.azuregos.category` | Manage service-catalog categories | `GET /api/categories`<br>`POST /api/categories`<br>`PATCH /api/categories/{category_id}`<br>`DELETE /api/categories/{category_id}` |
| `zollo.azuregos.category_info` | List service-catalog categories | `GET /api/categories` |
| `zollo.azuregos.oidc_settings` | Configure OpenID Connect (OIDC) single sign-on | `GET /api/sso/oidc`<br>`PUT /api/sso/oidc`<br>`DELETE /api/sso/oidc` |
| `zollo.azuregos.oidc_settings_info` | Show the OIDC sign-in configuration | `GET /api/sso/oidc` |
| `zollo.azuregos.oidc_settings_test` | Test OIDC settings without saving them | `POST /api/sso/oidc/test` |
| `zollo.azuregos.portal` | Manage request portals (forms that create ADO work items) | `GET /api/portals`<br>`POST /api/portals`<br>`PATCH /api/portals/{portal_id}`<br>`DELETE /api/portals/{portal_id}` |
| `zollo.azuregos.portal_info` | List portals | `GET /api/portals` |
| `zollo.azuregos.saml_settings` | Configure SAML single sign-on | `GET /api/sso/saml`<br>`PUT /api/sso/saml`<br>`DELETE /api/sso/saml` |
| `zollo.azuregos.saml_settings_info` | Show the SAML sign-in configuration | `GET /api/sso/saml` |
| `zollo.azuregos.saml_settings_test` | Test SAML settings without saving them | `POST /api/sso/saml/test` |
| `zollo.azuregos.user` | Manage Azuregos user accounts and roles | `GET /api/users`<br>`POST /api/users`<br>`PATCH /api/users/{user_id}`<br>`DELETE /api/users/{user_id}` |
| `zollo.azuregos.user_info` | List user accounts | `GET /api/users` |
<!-- END GENERATED MODULE TABLE -->

## Development

See [`ansible/README.md`](https://github.com/zollo/azuregos/tree/main/ansible) in the Azuregos
repository for how the modules are generated and tested.
