from pathlib import Path

import pytest


class _FakeTasks:
    def __init__(self, items):
        self._items = items
        self.updated: list[tuple[str, str]] = []
        self.inserted: list[tuple[str, dict]] = []
        self.deleted: list[tuple[str, str]] = []

    def list(self, **kwargs):
        assert "tasklist" in kwargs
        return self

    def update(self, *, tasklist: str, task: str, body: dict):
        assert tasklist
        assert task
        assert body.get("status") == "completed"
        self.updated.append((tasklist, task))
        return self

    def insert(self, *, tasklist: str, body: dict):
        assert tasklist
        assert body.get("title")
        self.inserted.append((tasklist, body))
        return self

    def delete(self, *, tasklist: str, task: str):
        assert tasklist
        assert task
        self.deleted.append((tasklist, task))
        return self

    def execute(self):
        # If we are in update path, execute() is called on the same object.
        # We can't distinguish, but for list() we return items:
        return {"items": self._items}


class _FakeTaskLists:
    def __init__(self, items):
        self._items = items

    def list(self):
        return self

    def execute(self):
        return {"items": self._items}


class _FakeService:
    def __init__(self, tasklists, tasks: _FakeTasks):
        self._tasklists = _FakeTaskLists(tasklists)
        self._tasks = tasks

    def tasklists(self):
        return self._tasklists

    def tasks(self):
        return self._tasks


def test_mark_tasks_complete_by_title_marks_matching_titles_case_insensitive(monkeypatch, tmp_path: Path):
    from grocery.tools import gtasks

    fake_tasks = _FakeTasks(
        items=[
            {"id": "1", "title": "Milk"},
            {"id": "2", "title": "Bread"},
            {"id": "3", "title": "Eggs"},
        ]
    )
    fake_service = _FakeService(
        tasklists=[{"title": "Groceries", "id": "g"}],
        tasks=fake_tasks,
    )

    def _fake_build(*, repo_root: Path, scopes: list[str]):
        assert repo_root == tmp_path
        assert scopes == gtasks.DEFAULT_SCOPES_READWRITE
        return fake_service

    monkeypatch.setattr(gtasks, "_build_tasks_service", _fake_build)

    count = gtasks.mark_tasks_complete_by_title(
        repo_root=tmp_path, list_name="Groceries", titles=["milk", "EGGS"]
    )
    assert count == 2
    assert fake_tasks.updated == [("g", "1"), ("g", "3")]


def test_mark_tasks_complete_by_title_missing_list(monkeypatch, tmp_path: Path):
    from grocery.tools import gtasks

    fake_tasks = _FakeTasks(items=[])
    fake_service = _FakeService(tasklists=[{"title": "Other", "id": "x"}], tasks=fake_tasks)

    def _fake_build(*, repo_root: Path, scopes: list[str]):
        return fake_service

    monkeypatch.setattr(gtasks, "_build_tasks_service", _fake_build)

    with pytest.raises(ValueError, match="Task list not found"):
        gtasks.mark_tasks_complete_by_title(repo_root=tmp_path, list_name="Groceries", titles=["milk"])


def test_move_open_tasks_by_title_inserts_into_dest_and_deletes_from_source(monkeypatch, tmp_path: Path):
    from grocery.tools import gtasks

    fake_tasks = _FakeTasks(
        items=[
            {"id": "1", "title": "Ornaments"},
            {"id": "2", "title": "Milk"},
        ]
    )
    fake_service = _FakeService(
        tasklists=[{"title": "Groceries", "id": "g"}, {"title": "To Purchase for Condo", "id": "c"}],
        tasks=fake_tasks,
    )

    def _fake_build(*, repo_root: Path, scopes: list[str]):
        assert repo_root == tmp_path
        assert scopes == gtasks.DEFAULT_SCOPES_READWRITE
        return fake_service

    monkeypatch.setattr(gtasks, "_build_tasks_service", _fake_build)

    moved = gtasks.move_open_tasks_by_title(
        repo_root=tmp_path,
        source_list_name="Groceries",
        dest_list_name="To Purchase for Condo",
        titles=["ornaments"],
    )
    assert moved == 1
    assert fake_tasks.inserted == [("c", {"title": "Ornaments"})]
    assert fake_tasks.deleted == [("g", "1")]


