from __future__ import annotations

from pathlib import Path

import yaml
from ansible_collections.zollo.azuregos.plugins.filter.export_config import export_config

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[2]
     / "ansible_collections/zollo/azuregos/roles/export/vars/main.yml").read_text()
)["azuregos__export"]


def test_ids_become_names_and_secrets_never_appear():
    results = {
        "ado_connection_info": {"ado_connection": {"stored": {
            "org_url": "https://dev.azure.com/x", "default_project": "IT", "pat_set": True}}},
        "category_info": {"categories": [{"id": "c1", "name": "Hardware", "icon": "laptop",
                                          "slug": "hardware", "portal_count": 1}]},
        "portal_info": {"portals": [{"id": "p1", "name": "Laptop", "category_id": "c1",
                                     "slug": "laptop", "fields": [{"name": "m", "default": None}],
                                     "area_path": None}]},
        "user_info": {"users": [
            {"id": "u1", "email": "a@x.io", "role": "portal_admin", "portal_ids": ["p1"],
             "provider": "local", "is_active": True},
            {"id": "u2", "email": "sso@x.io", "provider": "oidc", "portal_ids": []},
        ]},
    }
    out = export_config(results, SPEC)
    assert out["azuregos_ado_connection"] == {"org_url": "https://dev.azure.com/x",
                                              "default_project": "IT"}
    assert out["azuregos_categories"] == [{"name": "Hardware", "icon": "laptop"}]
    portal = out["azuregos_portals"][0]
    assert portal["category"] == "Hardware" and "category_id" not in portal
    assert "slug" not in portal and "area_path" not in portal
    assert portal["fields"] == [{"name": "m"}]
    assert out["azuregos_users"] == [{"email": "a@x.io", "role": "portal_admin",
                                      "portals": ["Laptop"], "is_active": True}]


def test_no_saved_connection_is_left_out():
    out = export_config({"ado_connection_info": {"ado_connection": {"stored": None}}}, SPEC)
    assert "azuregos_ado_connection" not in out


def test_export_role_reads_every_info_module_it_exports():
    tasks = (Path(__file__).resolve().parents[2]
             / "ansible_collections/zollo/azuregos/roles/export/tasks/main.yml").read_text()
    for entry in SPEC:
        assert f"zollo.azuregos.{entry['info']}:" in tasks, entry["info"]
        assert f"'{entry['info']}': azuregos__{entry['info']}" in tasks, entry["info"]
