from pathlib import Path


def test_append_unavailable_creates_file_and_appends(tmp_path: Path):
    from grocery.tools.unavailable import append_unavailable, load_unavailable

    p = tmp_path / "unavailable.json"
    append_unavailable(p, item="organic kale", reason="not_found", search_term="organic kale")
    append_unavailable(p, item="milk", reason="out_of_stock")

    data = load_unavailable(p)
    assert len(data["items"]) == 2
    assert data["items"][0]["item"] == "organic kale"
    assert data["items"][0]["reason"] == "not_found"
    assert data["items"][0]["search_term"] == "organic kale"
    assert data["items"][1]["item"] == "milk"
    assert data["items"][1]["reason"] == "out_of_stock"


