"""Product library tools (load/lookup/add/verify).

This is intentionally simple and file-backed (JSON). The goal is predictable,
human-auditable state that supports idempotent runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from difflib import get_close_matches
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
    """
    Look up a product by name.
    
    First checks product keys, then searches original_requests arrays.
    This allows matching variations like "shrmps" → "shrimps" product.
    """
    data = load_products(products_path)
    products = data.get("products", {})
    normalized = normalize_key(item_name)
    
    # First check direct key match
    if normalized in products:
        return products[normalized]
    
    # Then search original_requests arrays
    for product_key, product_data in products.items():
        original_requests = product_data.get("original_requests", [])
        if normalized in [normalize_key(req) for req in original_requests]:
            return product_data
    
    return None


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


def add_variation_to_product(
    products_path: Path,
    *,
    product_key: str,
    variation: str,
) -> bool:
    """
    Add a variation (e.g., corrected spelling) to an existing product's original_requests.
    
    Args:
        products_path: Path to products.json
        product_key: Normalized product key (e.g., "shrimps")
        variation: Variation to add (e.g., "shrmps" or corrected "shrimps")
    
    Returns:
        True if added, False if product not found
    """
    data = load_products(products_path)
    products = data.get("products", {})
    
    normalized_key = normalize_key(product_key)
    if normalized_key not in products:
        return False
    
    product = products[normalized_key]
    original_requests = product.setdefault("original_requests", [])
    
    normalized_variation = normalize_key(variation)
    # Add if not already present (case-insensitive)
    if normalized_variation not in [normalize_key(req) for req in original_requests]:
        original_requests.append(variation)  # Keep original case for display
        product["original_requests"] = original_requests
        products[normalized_key] = product
        save_products(products_path, data)
    
    return True


def verify_all_mapped(products_path: Path, items: list[str]) -> tuple[list[str], list[str]]:
    """
    Return (mapped, unmapped) based on keys OR original_requests in products.json.
    
    Checks both product keys and original_requests arrays to handle variations.
    """
    data = load_products(products_path)
    products = data.get("products", {})
    mapped: list[str] = []
    unmapped: list[str] = []
    
    for item in items:
        normalized = normalize_key(item)
        
        # Check direct key match
        if normalized in products:
            mapped.append(item)
            continue
        
        # Check original_requests arrays
        found = False
        for product_data in products.values():
            original_requests = product_data.get("original_requests", [])
            if normalized in [normalize_key(req) for req in original_requests]:
                mapped.append(item)
                found = True
                break
        
        if not found:
            unmapped.append(item)
    
    return mapped, unmapped


def fuzzy_match_products(products_path: Path, item: str, n: int = 3, cutoff: float = 0.6) -> list[tuple[str, float]]:
    """
    Return top N fuzzy matches for an unmapped item.
    
    Searches both product keys AND original_requests arrays for better matching.
    Returns list of (product_key, similarity_score) tuples, sorted by score descending.
    Uses difflib.get_close_matches with configurable cutoff (default 0.6 = 60% similarity).
    """
    data = load_products(products_path)
    products = data.get("products", {})
    if not products:
        return []
    
    normalized_item = normalize_key(item)
    
    # Build search space: product keys + all original_requests
    search_space = set(products.keys())
    for product_data in products.values():
        original_requests = product_data.get("original_requests", [])
        for req in original_requests:
            search_space.add(normalize_key(req))
    
    all_keys = list(search_space)
    
    # get_close_matches returns sorted by similarity
    matches = get_close_matches(normalized_item, all_keys, n=n, cutoff=cutoff)
    
    # Map matches back to product keys (if match was from original_requests, use product key)
    from difflib import SequenceMatcher
    results = []
    seen_products = set()
    
    for match in matches:
        # Find which product this match belongs to
        product_key = None
        if match in products:
            product_key = match
        else:
            # Match came from original_requests, find the product
            for key, product_data in products.items():
                original_requests = product_data.get("original_requests", [])
                if match in [normalize_key(req) for req in original_requests]:
                    product_key = key
                    break
        
        if product_key and product_key not in seen_products:
            score = SequenceMatcher(None, normalized_item, match).ratio()
            results.append((product_key, score))
            seen_products.add(product_key)
    
    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


