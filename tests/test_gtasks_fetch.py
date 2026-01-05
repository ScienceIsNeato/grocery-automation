from pathlib import Path

import pytest


class _FakeTaskLists:
    def __init__(self, items):
        self._items = items

    def list(self):
        return self

    def execute(self):
        return {"items": self._items}


class _FakeTasks:
    def __init__(self, items):
        self._items = items

    def list(self, **kwargs):
        # Ensure basic params are passed (smoke check)
        assert "tasklist" in kwargs
        return self

    def execute(self):
        return {"items": self._items}


class _FakeService:
    def __init__(self, tasklists, tasks):
        self._tasklists = _FakeTaskLists(tasklists)
        self._tasks = _FakeTasks(tasks)

    def tasklists(self):
        return self._tasklists

    def tasks(self):
        return self._tasks


def test_fetch_open_task_titles_happy_path(monkeypatch, tmp_path: Path):
    from grocery.tools import gtasks

    fake = _FakeService(
        tasklists=[
            {"title": "Other", "id": "x"},
            {"title": "Groceries", "id": "g"},
        ],
        tasks=[
            {"title": "milk"},
            {"title": " bread "},
            {"title": ""},  # ignored
            {},  # ignored
        ],
    )

    def _fake_build(*, repo_root: Path, scopes: list[str]):
        assert repo_root == tmp_path
        assert scopes == gtasks.DEFAULT_SCOPES_READWRITE
        return fake

    monkeypatch.setattr(gtasks, "_build_tasks_service", _fake_build)

    titles = gtasks.fetch_open_task_titles(repo_root=tmp_path, list_name="Groceries")
    assert titles == ["milk", "bread"]


def test_fetch_open_task_titles_missing_list(monkeypatch, tmp_path: Path):
    from grocery.tools import gtasks

    fake = _FakeService(tasklists=[{"title": "Other", "id": "x"}], tasks=[])

    def _fake_build(*, repo_root: Path, scopes: list[str]):
        return fake

    monkeypatch.setattr(gtasks, "_build_tasks_service", _fake_build)

    with pytest.raises(ValueError, match="Task list not found"):
        gtasks.fetch_open_task_titles(repo_root=tmp_path, list_name="Groceries")


