# -*- coding: utf-8 -*-
# GNU General Public License v3.0+ (see https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: export_config
short_description: Turn Azuregos info results into configure-role variables
description:
  - Used by the zollo.azuregos.export role. Takes the registered results of the
    C(*_info) modules and returns the variables of the zollo.azuregos.configure
    role, with category and portal names instead of IDs.
  - Write-only values (passwords, the ADO PAT) are never in the input, so they are
    never in the output. Only local accounts are exported.
author: Azuregos contributors (@zollo)
positional: spec
options:
  _input:
    description: Registered info results, keyed by info module name (for example C(category_info)).
    type: dict
    required: true
  spec:
    description: The export description the generator writes to the export role's vars.
    type: list
    elements: dict
    required: true
"""

EXAMPLES = r"""
- ansible.builtin.debug:
    msg: "{{ {'category_info': cats, 'portal_info': portals} | zollo.azuregos.export_config(azuregos__export) }}"
"""

RETURN = r"""
_value:
  description: The variables, for example C(azuregos_categories) and C(azuregos_portals).
  type: dict
"""

from ansible.errors import AnsibleFilterError


def _drop_none(value):
    if isinstance(value, dict):
        return dict((k, _drop_none(v)) for k, v in value.items() if v is not None)
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value


def export_config(results, spec):
    if not isinstance(results, dict):
        raise AnsibleFilterError("export_config expects a dict of info results")
    names = {}
    for entry in spec:
        if entry.get("identity"):
            result = results.get(entry["info"]) or {}
            module = entry["info"][: -len("_info")]
            names[module] = dict(
                (item["id"], item.get(entry["identity"]))
                for item in result.get(entry["return_key"], [])
            )

    out = {}
    for entry in spec:
        result = results.get(entry["info"])
        if result is None:
            continue
        data = result.get(entry["return_key"])
        if entry.get("read_key") is not None or not entry.get("identity"):
            obj = data.get(entry["read_key"]) if entry.get("read_key") else data
            if obj:
                out[entry["var"]] = dict(
                    (f, obj[f]) for f in entry["fields"] if obj.get(f) is not None
                )
            continue
        items = []
        for item in data or []:
            if item.get("provider", "local") != "local":
                continue
            row = {entry["identity"]: item.get(entry["identity"])}
            for field in entry["fields"]:
                value = item.get(field)
                ref = entry.get("references", {}).get(field)
                if ref:
                    lookup = names.get(ref["from"], {})
                    if ref["list"]:
                        row[ref["name"]] = sorted(lookup.get(v, v) for v in value or [])
                    else:
                        row[ref["name"]] = lookup.get(value, value) if value else ""
                elif value is not None and field not in row:
                    row[field] = _drop_none(value)
            items.append(row)
        out[entry["var"]] = items
    return out


class FilterModule(object):
    def filters(self):
        return {"export_config": export_config}
