from types import SimpleNamespace

from app.api.routes.portals import effective_category_icon, effective_portal_icon


def test_category_icon_default():
    assert effective_category_icon(SimpleNamespace(icon="Server")) == "Server"
    assert effective_category_icon(SimpleNamespace(icon="")) == "folder"
    assert effective_category_icon(None) == "folder"


def test_portal_icon_override():
    cat = SimpleNamespace(icon="Server")
    assert effective_portal_icon(SimpleNamespace(icon="Bug", category=cat)) == "Bug"


def test_portal_icon_trickles_down_from_category():
    cat = SimpleNamespace(icon="Server")
    assert effective_portal_icon(SimpleNamespace(icon="", category=cat)) == "Server"


def test_portal_icon_falls_back_to_default():
    assert effective_portal_icon(SimpleNamespace(icon="", category=None)) == "ticket"
    empty_cat = SimpleNamespace(icon="")
    assert effective_portal_icon(SimpleNamespace(icon="", category=empty_cat)) == "ticket"
