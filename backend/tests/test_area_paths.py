from app.services.ado_client import _flatten_area_paths, area_node_to_path


def test_area_node_to_path_strips_classification_segment():
    assert area_node_to_path("\\dev-test\\Area") == "dev-test"
    assert area_node_to_path("\\dev-test\\Area\\Team\\Sub") == "dev-test\\Team\\Sub"


def test_flatten_area_paths_depth_first():
    tree = {
        "path": "\\p\\Area",
        "children": [
            {
                "path": "\\p\\Area\\A",
                "children": [{"path": "\\p\\Area\\A\\B", "children": []}],
            },
            {"path": "\\p\\Area\\C", "children": []},
        ],
    }
    assert _flatten_area_paths(tree) == ["p", "p\\A", "p\\A\\B", "p\\C"]
