"""Google Tasks tools (fetch/normalize/mark complete).

Auth model: OAuth desktop flow with local token storage (token.json).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional


DEFAULT_SCOPES_READONLY = ["https://www.googleapis.com/auth/tasks.readonly"]
DEFAULT_SCOPES_READWRITE = ["https://www.googleapis.com/auth/tasks"]


def _build_tasks_service(
    *,
    repo_root: Path,
    scopes: list[str],
) -> Any:
    # Imports are inside to keep module import lightweight for tests.
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_file = repo_root / "token.json"
    credentials_file = repo_root / "credentials.json"

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Fail fast: if we already have a token.json but refresh fails, do not
                # silently fall back to interactive auth.
                raise RuntimeError(
                    "Token refresh failed. Next step: delete token.json and re-run to re-authorize."
                ) from e

        if not creds:
            if not credentials_file.exists():
                raise FileNotFoundError(f"Missing credentials file: {credentials_file}")
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), scopes)
            creds = flow.run_local_server(port=0)

        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("tasks", "v1", credentials=creds)


def find_task_list_id(service: Any, task_list_name: str) -> Optional[str]:
    results = service.tasklists().list().execute()
    for task_list in results.get("items", []):
        if task_list["title"].lower() == task_list_name.lower():
            return task_list["id"]
    return None


def fetch_open_task_titles(*, repo_root: Path, list_name: str) -> list[str]:
    # Always use read-write scope so token stays valid for all operations
    service = _build_tasks_service(repo_root=repo_root, scopes=DEFAULT_SCOPES_READWRITE)
    task_list_id = find_task_list_id(service, list_name)
    if not task_list_id:
        raise ValueError(f"Task list not found: {list_name}")
    
    # Paginate through all tasks (API returns max 100 per page by default)
    all_tasks = []
    page_token = None
    while True:
        results = service.tasks().list(
            tasklist=task_list_id,
            showCompleted=False,
            showHidden=False,
            maxResults=100,
            pageToken=page_token,
        ).execute()
        all_tasks.extend(results.get("items", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    
    return [t.get("title", "").strip() for t in all_tasks if t.get("title")]


def mark_tasks_complete_by_title(
    *,
    repo_root: Path,
    list_name: str,
    titles: list[str],
) -> int:
    service = _build_tasks_service(repo_root=repo_root, scopes=DEFAULT_SCOPES_READWRITE)
    task_list_id = find_task_list_id(service, list_name)
    if not task_list_id:
        raise ValueError(f"Task list not found: {list_name}")

    # Fetch open tasks once, then complete matches.
    results = service.tasks().list(tasklist=task_list_id, showCompleted=False, showHidden=False).execute()
    tasks = results.get("items", [])

    target = {t.lower().strip() for t in titles}
    completed = 0
    for task in tasks:
        title = task.get("title", "")
        if title.lower().strip() not in target:
            continue
        task["status"] = "completed"
        service.tasks().update(tasklist=task_list_id, task=task["id"], body=task).execute()
        completed += 1

    return completed


def move_open_tasks_by_title(
    *,
    repo_root: Path,
    source_list_name: str,
    dest_list_name: str,
    titles: list[str],
) -> int:
    """
    Move open tasks matching `titles` from one list to another.

    Google Tasks doesn't support "moving a task between lists" directly, so we:
    - list open tasks in the source list
    - insert new tasks in the destination list with the same title (and notes if present)
    - delete the original tasks from the source list
    """
    service = _build_tasks_service(repo_root=repo_root, scopes=DEFAULT_SCOPES_READWRITE)

    source_id = find_task_list_id(service, source_list_name)
    if not source_id:
        raise ValueError(f"Task list not found: {source_list_name}")
    dest_id = find_task_list_id(service, dest_list_name)
    if not dest_id:
        raise ValueError(f"Task list not found: {dest_list_name}")

    wanted = {t.lower().strip() for t in titles}
    if not wanted:
        return 0

    results = service.tasks().list(tasklist=source_id, showCompleted=False, showHidden=False).execute()
    tasks = results.get("items", [])

    moved = 0
    for task in tasks:
        title = (task.get("title") or "").strip()
        if not title:
            continue
        if title.lower().strip() not in wanted:
            continue

        body: dict[str, Any] = {"title": title}
        notes = task.get("notes")
        if notes:
            body["notes"] = notes

        service.tasks().insert(tasklist=dest_id, body=body).execute()
        service.tasks().delete(tasklist=source_id, task=task["id"]).execute()
        moved += 1

    return moved


_LEADING_QTY_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
_DOZEN_RE = re.compile(r"^\s*(?:(\d+)\s+)?dozen\s+(.*)$", re.IGNORECASE)


def normalize(*, items: list[str]) -> list[dict]:
    """
    Normalize raw task titles to structured items.

    Rules (initial, intentionally simple):
    - strip whitespace
    - extract quantity:
      - "2 bananas" => qty=2, text="bananas"
      - "2 dozen eggs" => qty=24, text="eggs"
      - "dozen eggs" => qty=12, text="eggs"
    - lowercase for matching
    
    Product matching is handled by products.json lookup (checks original_requests arrays).
    """
    out: list[dict] = []
    for raw in items:
        if raw is None:
            continue
        original = raw
        s = str(raw).strip()
        if not s:
            continue

        qty = 1

        # "2 dozen eggs" / "dozen eggs"
        dozen_match = _DOZEN_RE.match(s)
        if dozen_match:
            n = dozen_match.group(1)
            qty = (int(n) if n else 1) * 12
            s = dozen_match.group(2).strip()
        else:
            # "2 bananas"
            m = _LEADING_QTY_RE.match(s)
            if m:
                qty = int(m.group(1))
                s = m.group(2).strip()

        normalized = s.lower().strip()
        out.append({"original": original, "normalized": normalized, "quantity": qty})

    return out



