"""Product library tools (load/lookup/add/verify).

This is intentionally simple and file-backed (JSON). The goal is predictable,
human-auditable state that supports idempotent runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def normalize_key(text: str) -> str:
    return text.strip().lower()


def load_products(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"products": {}, "version": "1.0", "last_updated": None, "notes": ""}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_products(path: Path, data: dict[str, Any]) -> None:
    data = dict(data)
    data.setdefault("version", "1.0")
    data["last_updated"] = datetime.now().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def lookup(products_path: Path, item_name: str) -> dict[str, Any] | None:
    data = load_products(products_path)
    products = data.get("products", {})
    return products.get(normalize_key(item_name))


def add_mapping(
    products_path: Path,
    *,
    item_name: str,
    product: dict[str, Any],
    original_request: str | None = None,
) -> None:
    """
    Add or update a mapping:
    - key: normalized item_name
    - product: dict containing at least display_name/url/product_id (optional)
    - original_request: appended into product.original_requests
    """
    key = normalize_key(item_name)
    data = load_products(products_path)
    products = data.setdefault("products", {})

    existing = products.get(key)
    if existing is None:
        merged = dict(product)
        merged.setdefault("original_requests", [])
        if original_request:
            merged["original_requests"] = list(
                dict.fromkeys([*merged.get("original_requests", []), original_request])
            )
        merged.setdefault("added", datetime.now().isoformat())
        products[key] = merged
    else:
        existing.update(product)
        if original_request:
            reqs = existing.get("original_requests", [])
            if original_request not in reqs:
                reqs.append(original_request)
            existing["original_requests"] = reqs
        products[key] = existing

    save_products(products_path, data)


def verify_all_mapped(products_path: Path, items: list[str]) -> tuple[list[str], list[str]]:
    """Return (mapped, unmapped) based on keys existing in products.json."""
    data = load_products(products_path)
    products = data.get("products", {})
    mapped: list[str] = []
    unmapped: list[str] = []
    for item in items:
        key = normalize_key(item)
        (mapped if key in products else unmapped).append(item)
    return mapped, unmapped


