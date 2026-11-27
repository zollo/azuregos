# -*- coding: utf-8 -*-
# Copyright: Azuregos contributors
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)
"""Runtime shared by every zollo.azuregos module.

The modules themselves are generated from the Azuregos OpenAPI spec
(``ansible/generator/generate.py``): each one only declares its argument spec
and a ``RESOURCE`` description (which operations to call, the request schemas,
the identity key). Everything that talks to the API lives here, by hand:
authentication, HTTP, client-side checks against the spec's constraints, and
the idempotent create/update/delete logic.
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import copy
import json
import re

from ansible.module_utils.basic import AnsibleModule, env_fallback
from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils.six.moves.urllib.parse import urlencode
from ansible.module_utils.urls import open_url

# Options every module shares (documented by the zollo.azuregos.connection doc
# fragment). They're prefixed so they can't collide with an API field: a user
# has a `password`, and the generator refuses an API field named like these.
CONNECTION_ARGS = dict(
    api_url=dict(type="str", required=True, fallback=(env_fallback, ["AZUREGOS_URL"])),
    api_token=dict(type="str", no_log=True, fallback=(env_fallback, ["AZUREGOS_TOKEN"])),
    api_username=dict(type="str", fallback=(env_fallback, ["AZUREGOS_USERNAME"])),
    api_password=dict(type="str", no_log=True, fallback=(env_fallback, ["AZUREGOS_PASSWORD"])),
    validate_certs=dict(
        type="bool", default=True, fallback=(env_fallback, ["AZUREGOS_VALIDATE_CERTS"])
    ),
    api_timeout=dict(type="int", default=30),
)

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?([0-9a-fA-F]{4}-?){3}[0-9a-fA-F]{12}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AzuregosError(Exception):
    def __init__(self, message, status=None, body=None):
        super(AzuregosError, self).__init__(message)
        self.status = status
        self.body = body


# ── HTTP client ───────────────────────────────────────────────────────────


class AzuregosClient(object):
    """Minimal JSON client for the Azuregos REST API (bearer-token auth)."""

    def __init__(self, url, token=None, username=None, password=None,
                 validate_certs=True, timeout=30):
        self.base_url = url.rstrip("/")
        self.validate_certs = validate_certs
        self.timeout = timeout
        self.token = token
        if not self.token:
            if not (username and password):
                raise AzuregosError(
                    "Set either api_token, or api_username and api_password "
                    "(or the AZUREGOS_TOKEN / AZUREGOS_USERNAME and AZUREGOS_PASSWORD env vars)."
                )
            self.token = self.login(username, password)

    @classmethod
    def from_module(cls, module):
        p = module.params
        return cls(p["api_url"], p.get("api_token"), p.get("api_username"),
                   p.get("api_password"), p.get("validate_certs", True), p.get("api_timeout", 30))

    def login(self, username, password):
        data = self.request("POST", "/api/auth/login",
                            body={"email": username, "password": password}, auth=False)
        return data["access_token"]

    def request(self, method, path, body=None, query=None, auth=True):
        url = self.base_url + path
        if query:
            query = dict((k, v) for k, v in query.items() if v is not None)
            if query:
                url += "?" + urlencode(query)
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body)
        if auth:
            headers["Authorization"] = "Bearer %s" % self.token
        try:
            resp = open_url(url, method=method, data=data, headers=headers,
                            validate_certs=self.validate_certs, timeout=self.timeout)
            raw = resp.read()
        except HTTPError as exc:
            raw = exc.read() if hasattr(exc, "read") else b""
            detail = _error_detail(raw) or str(exc)
            raise AzuregosError("%s %s failed (HTTP %s): %s" % (method, path, exc.code, detail),
                                status=exc.code, body=raw)
        except URLError as exc:
            raise AzuregosError("Can't reach %s: %s" % (url, exc.reason))
        if not raw:
            return None
        return json.loads(raw)


def _error_detail(raw):
    try:
        detail = json.loads(raw).get("detail")
    except (ValueError, AttributeError):
        return raw.decode("utf-8", "replace") if raw else ""
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(
            "%s: %s" % (".".join(str(x) for x in e.get("loc", [])), e.get("msg")) for e in detail
        )
    return str(detail)


# ── Validation against the OpenAPI request schema ────────────────────────


def schema_errors(schema, value, where):
    """Check ``value`` against a (dereferenced) JSON schema; return error strings.

    Ansible already checks types and choices from the argument spec; this adds
    the constraints the argument spec can't express (lengths, patterns,
    formats, nullability) so a bad value fails before anything is sent.
    """
    if "anyOf" in schema:
        options = schema["anyOf"]
        if value is None:
            if any(o.get("type") == "null" for o in options):
                return []
            return ["%s may not be null" % where]
        non_null = [o for o in options if o.get("type") != "null"]
        best = None
        for option in non_null:
            errs = schema_errors(option, value, where)
            if not errs:
                return []
            best = best or errs
        return best or []
    if value is None:
        return ["%s may not be null" % where]
    errors = []
    kind = schema.get("type")
    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s must be one of %s" % (where, ", ".join(map(str, schema["enum"]))))
    if kind == "string":
        if not isinstance(value, str):
            return ["%s must be a string" % where]
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s must be at least %d characters" % (where, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s must be at most %d characters" % (where, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append("%s must match %s" % (where, schema["pattern"]))
        fmt = schema.get("format")
        if fmt == "uuid" and not UUID_RE.match(value):
            errors.append("%s must be a UUID" % where)
        if fmt == "email" and not EMAIL_RE.match(value):
            errors.append("%s must be an email address" % where)
    elif kind == "array":
        if not isinstance(value, list):
            return ["%s must be a list" % where]
        for i, item in enumerate(value):
            errors.extend(schema_errors(schema.get("items", {}), item, "%s[%d]" % (where, i)))
    elif kind == "object" and "properties" in schema:
        if not isinstance(value, dict):
            return ["%s must be a dict" % where]
        for key in schema.get("required", []):
            if value.get(key) is None:
                errors.append("%s.%s is required" % (where, key))
        for key, sub in schema["properties"].items():
            if value.get(key) is not None:
                errors.extend(schema_errors(sub, value[key], "%s.%s" % (where, key)))
    return errors


def strip_none(value):
    """Drop None entries from nested dicts (unset suboptions) so the API applies defaults."""
    if isinstance(value, dict):
        return dict((k, strip_none(v)) for k, v in value.items() if v is not None)
    if isinstance(value, list):
        return [strip_none(v) for v in value]
    return value


# ── Comparison ────────────────────────────────────────────────────────────


def _norm_scalar(value):
    if isinstance(value, str) and UUID_RE.match(value):
        return value.lower().replace("-", "")
    return value


def values_equal(desired, current, unordered=False):
    """Does the API's ``current`` value already satisfy ``desired``?

    Nested dict keys the user left unset (None) match an empty current value,
    so a suboption the API filled with its default isn't reported as a change.
    """
    if isinstance(desired, dict):
        if not isinstance(current, dict):
            return False
        for key, want in desired.items():
            have = current.get(key)
            if want is None:
                if have not in (None, "", [], {}):
                    return False
            elif not values_equal(want, have):
                return False
        return True
    if isinstance(desired, list):
        if not isinstance(current, list) or len(desired) != len(current):
            return False
        if unordered:
            return sorted(map(_sort_key, desired)) == sorted(map(_sort_key, current))
        return all(values_equal(d, c) for d, c in zip(desired, current))
    return _norm_scalar(desired) == _norm_scalar(current)


def _sort_key(value):
    return json.dumps(_norm_scalar(value), sort_keys=True, default=str)


NORMALIZERS = {
    "rstrip_slash": lambda v: v.rstrip("/") if isinstance(v, str) else v,
    "strip": lambda v: v.strip() if isinstance(v, str) else v,
}


# ── Module runners ────────────────────────────────────────────────────────


def build_argument_spec(options):
    spec = copy.deepcopy(CONNECTION_ARGS)
    spec.update(copy.deepcopy(options))
    return spec


def _fill_path(path, values):
    for key, val in values.items():
        path = path.replace("{%s}" % key, str(val))
    return path


class ResourceRunner(object):
    def __init__(self, module, resource, client=None):
        self.module = module
        self.res = resource
        self.client = client or AzuregosClient.from_module(module)
        self.changed = False
        self.diff = {"before": {}, "after": {}}

    # helpers -------------------------------------------------------------
    def desired(self, fields):
        """The user's values for ``fields``: unset options (None) are left out."""
        params = self.module.params
        out = {}
        for name in fields:
            value = params.get(name)
            if value is None:
                continue
            if value == "" and name in self.res.get("nullable", []):
                value = None  # "" clears a nullable field
            out[name] = strip_none(value)
        return out

    def validate(self, op, payload, require=None):
        """Check ``payload`` against the request schema of operation ``op``.

        Required properties are enforced unless the operation is a partial
        update (PATCH), where everything is optional.
        """
        schema = self.res[op]["schema"]
        errors = []
        if require is None:
            require = self.res[op]["method"] != "patch"
        if require:
            for name in schema.get("required", []):
                if payload.get(name) is None:
                    errors.append("%s is required" % name)
        for name, value in payload.items():
            sub = schema["properties"].get(name)
            if sub is not None:
                errors.extend(schema_errors(sub, value, name))
        if errors:
            self.module.fail_json(msg="Invalid options: " + "; ".join(errors))

    def call(self, op, path_values=None, body=None, query=None):
        spec = self.res[op]
        path = _fill_path(spec["path"], path_values or {})
        try:
            return self.client.request(spec["method"].upper(), path, body=body, query=query)
        except AzuregosError as exc:
            self.module.fail_json(msg=str(exc), status=exc.status)

    def normalize(self, name, value):
        fn = self.res.get("normalize", {}).get(name)
        return NORMALIZERS[fn](value) if fn else value

    def differs(self, name, want, have):
        want = self.normalize(name, want)
        have = self.normalize(name, have)
        return not values_equal(want, have, unordered=name in self.res.get("unordered", []))

    def secret_changes(self, existing):
        """Write-only fields (passwords, tokens) that should be sent on update."""
        out = {}
        for name in self.res.get("write_only", []):
            mode = self.module.params.get("update_%s" % name) or "on_create"
            value = self.module.params.get(name)
            if value is not None and (mode == "always" or not existing):
                out[name] = value
        return out

    # collection resources (list/create/update/delete) --------------------
    def find(self):
        items = self.call("list") or []
        wanted_id = self.module.params.get("id")
        if wanted_id:
            matches = [i for i in items if _norm_scalar(i.get("id")) == _norm_scalar(wanted_id)]
            if not matches:
                self.module.fail_json(msg="No %s with id %s" % (self.res["noun"], wanted_id))
            return matches[0]
        key = self.res["identity"]
        value = self.module.params.get(key)
        if value is None:
            self.module.fail_json(msg="Set %s (or id) to identify the %s" % (key, self.res["noun"]))
        matches = [i for i in items if _norm_scalar(self.normalize(key, i.get(key)))
                   == _norm_scalar(self.normalize(key, value))]
        if len(matches) > 1:
            self.module.fail_json(
                msg="%d %ss have %s %r; use id to pick one" % (len(matches), self.res["noun"],
                                                               key, value))
        return matches[0] if matches else None

    def run_collection(self):
        state = self.module.params["state"]
        current = self.find()
        id_param = self.res["id_param"]
        result_key = self.res["return_key"]

        if state == "absent":
            if current:
                self.changed = True
                self.diff = {"before": current, "after": {}}
                if not self.module.check_mode:
                    self.call("delete", {id_param: current["id"]})
            return {result_key: {}}

        create_fields = list(self.res["create"]["schema"]["properties"])
        update_fields = list(self.res["update"]["schema"]["properties"])
        write_only = self.res.get("write_only", [])

        if current is None:
            payload = self.desired(create_fields)
            self.validate("create", payload)
            # Options only the update operation accepts (e.g. a user's is_active).
            followup = dict((k, v) for k, v in self.desired(update_fields).items()
                            if k not in create_fields)
            self.changed = True
            after = dict(payload, **followup)
            for name in write_only:
                after.pop(name, None)
            self.diff = {"before": {}, "after": after}
            if self.module.check_mode:
                return {result_key: after}
            created = self.call("create", body=payload)
            if followup:
                self.validate("update", followup)
                created = self.call("update", {id_param: created["id"]}, body=followup)
            return {result_key: created}

        wanted = self.desired(update_fields)
        immutable = [k for k, v in self.desired(create_fields).items()
                     if k not in update_fields and k != self.res["identity"]
                     and self.differs(k, v, current.get(k))]
        if immutable:
            self.module.fail_json(msg="Can't change %s of an existing %s"
                                  % (", ".join(immutable), self.res["noun"]))
        changes = dict((k, v) for k, v in wanted.items()
                       if k not in write_only and self.differs(k, v, current.get(k)))
        changes.update(self.secret_changes(existing=True))
        if not changes:
            return {result_key: current}
        self.validate("update", changes)
        self.changed = True
        shown = dict((k, v) for k, v in changes.items() if k not in write_only)
        self.diff = {"before": dict((k, current.get(k)) for k in shown),
                     "after": shown}
        if self.module.check_mode:
            return {result_key: dict(current, **shown)}
        return {result_key: self.call("update", {id_param: current["id"]}, body=changes)}

    # singleton resources (read/write/delete) ------------------------------
    def run_singleton(self):
        state = self.module.params["state"]
        status = self.call("read")
        read_key = self.res.get("read_key")
        current = status.get(read_key) if read_key else status
        result_key = self.res["return_key"]

        if state == "absent":
            if current:
                self.changed = True
                self.diff = {"before": current, "after": {}}
                if not self.module.check_mode:
                    self.call("delete")
                    status = self.call("read")
            return {result_key: status}

        fields = list(self.res["write"]["schema"]["properties"])
        write_only = self.res.get("write_only", [])
        wanted = self.desired(fields)
        visible = dict((k, v) for k, v in wanted.items() if k not in write_only)
        changes = visible if current is None else dict(
            (k, v) for k, v in visible.items() if self.differs(k, v, current.get(k)))
        secrets = self.secret_changes(existing=current is not None)
        if not changes and not secrets:
            return {result_key: status}
        payload = dict(wanted)
        for name in write_only:  # a blank secret keeps the saved one
            if name not in secrets:
                payload.pop(name, None)
        self.validate("write", payload)
        self.changed = True
        self.diff = {"before": dict((k, (current or {}).get(k)) for k in visible) if current
                     else {}, "after": visible}
        if self.module.check_mode:
            return {result_key: status}
        return {result_key: self.call("write", body=payload)}

    # info / action -------------------------------------------------------
    def run_info(self):
        query = dict((k, self.module.params.get(k)) for k in self.res.get("query", []))
        data = self.call("read", query=query)
        filters = dict((k, self.module.params.get(k)) for k in self.res.get("filters", [])
                       if self.module.params.get(k) is not None)
        if filters and isinstance(data, list):
            data = [item for item in data
                    if all(_norm_scalar(item.get(k)) == _norm_scalar(v)
                           for k, v in filters.items())]
        return {self.res["return_key"]: data}

    def run_action(self):
        fields = list(self.res["call"]["schema"]["properties"])
        payload = self.desired(fields)
        self.validate("call", payload)
        return {self.res["return_key"]: self.call("call", body=payload)}

    def run(self):
        kind = self.res["kind"]
        handler = {"collection": self.run_collection, "singleton": self.run_singleton,
                   "info": self.run_info, "action": self.run_action}[kind]
        result = handler()
        out = dict(changed=self.changed, **result)
        if self.module._diff and kind in ("collection", "singleton"):
            out["diff"] = self.diff
        return out


def run_module(options, resource, mutually_exclusive=None):
    """Entry point of every generated module."""
    module = AnsibleModule(
        argument_spec=build_argument_spec(options),
        supports_check_mode=True,
        mutually_exclusive=mutually_exclusive or [],
    )
    try:
        runner = ResourceRunner(module, resource)
        module.exit_json(**runner.run())
    except AzuregosError as exc:
        module.fail_json(msg=str(exc), status=exc.status)
