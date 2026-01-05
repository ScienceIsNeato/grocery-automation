import json
from pathlib import Path


def test_run_shows_fuzzy_ui_on_unmapped_items(monkeypatch, tmp_path: Path, capsys):
    # Arrange minimal repo layout
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    (repo_root / "data" / "products.json").write_text(json.dumps({"products": {}}), encoding="utf-8")

    from grocery import run

    # Fake tasks fetch to return two items.
    monkeypatch.setattr(run.gtasks, "fetch_open_task_titles", lambda **kwargs: ["milk", "bread"])

    # Fake argv
    monkeypatch.setenv("HYVEE_EMAIL", "x")  # irrelevant for fuzzy UI
    monkeypatch.setattr(
        "sys.argv",
        [
            "grocery-run",
            "--list-name",
            "Groceries",
            "--repo-root",
            str(repo_root),
            "--products",
            str(repo_root / "data" / "products.json"),
        ],
        raising=False,
    )

    code = run.main()
    out = capsys.readouterr().out
    # Should show fuzzy match UI, not error
    assert "FUZZY MATCH EXISTING PRODUCTS" in out
    assert "unmapped item" in out.lower()


