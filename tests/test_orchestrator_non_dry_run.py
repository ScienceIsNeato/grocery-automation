import json
from pathlib import Path


def test_run_non_dry_run_wires_hyvee_orchestration(monkeypatch, tmp_path: Path, capsys):
    repo_root = tmp_path
    (repo_root / "data").mkdir()
    (repo_root / "data" / "products.json").write_text(
        json.dumps({"products": {"milk": {"display_name": "Hy-Vee Vitamin D Milk"}}}),
        encoding="utf-8",
    )

    from grocery import run

    monkeypatch.setattr(run.gtasks, "fetch_open_task_titles", lambda **kwargs: ["milk"])

    calls: list[tuple] = []

    class _Page:
        pass

    def fake_start_browser(*, headless: bool = False):
        calls.append(("start_browser", headless))
        return object(), object(), _Page()

    def fake_stop_browser(*args, **kwargs):
        calls.append(("stop_browser",))

    monkeypatch.setattr(run.hyvee, "start_browser", fake_start_browser)
    monkeypatch.setattr(run.hyvee, "stop_browser", fake_stop_browser)
    monkeypatch.setattr(run.hyvee, "ensure_logged_in", lambda page: calls.append(("ensure_logged_in",)))
    monkeypatch.setattr(
        run.hyvee,
        "ensure_items_in_cart",
        lambda page, **kwargs: calls.append(("ensure_items_in_cart", kwargs["items"])),
    )

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
    assert code == 0
    assert "Hard stop before checkout" in out
    assert ("start_browser", False) in calls
    assert ("ensure_logged_in",) in calls
    assert ("ensure_items_in_cart", ["milk"]) in calls
    assert ("stop_browser",) in calls



