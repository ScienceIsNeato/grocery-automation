import json
from pathlib import Path


def test_run_dry_run_exits_1_on_first_unknown(monkeypatch, tmp_path: Path, capsys):
    # Arrange minimal repo layout
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    (repo_root / "data" / "products.json").write_text(json.dumps({"products": {}}), encoding="utf-8")
    (repo_root / "data" / "substitutions.json").write_text(json.dumps({"corrections": {}, "defaults": {}}), encoding="utf-8")

    from grocery import run

    # Fake tasks fetch to return two items.
    monkeypatch.setattr(run.gtasks, "fetch_open_task_titles", lambda **kwargs: ["milk", "bread"])

    # Fake argv
    monkeypatch.setenv("HYVEE_EMAIL", "x")  # irrelevant for dry-run
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
            "--substitutions",
            str(repo_root / "data" / "substitutions.json"),
            "--dry-run",
        ],
        raising=False,
    )

    code = run.main()
    out = capsys.readouterr().out
    assert code == 1
    assert "ERROR [1]" in out
    assert "Search and add manually" in out


