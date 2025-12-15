"""Unavailable item logging (not_found/out_of_stock/etc)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional


Reason = Literal["not_found", "out_of_stock", "discontinued", "unknown"]


@dataclass(frozen=True)
class UnavailableItem:
    item: str
    reason: Reason
    timestamp: str
    search_term: Optional[str] = None


def load_unavailable(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": []}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def append_unavailable(
    path: Path,
    *,
    item: str,
    reason: Reason,
    search_term: Optional[str] = None,
) -> None:
    data = load_unavailable(path)
    items = data.setdefault("items", [])
    items.append(
        {
            "item": item,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            **({"search_term": search_term} if search_term else {}),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


