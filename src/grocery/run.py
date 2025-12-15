"""
Orchestrator entry point (single command interface).

Implementation will be built tool-by-tool via TDD.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from grocery.tools import gtasks, library
from grocery.tools.errors import GroceryError, unknown_item
from grocery.tools.hyvee import build_search_url


def main() -> int:
    parser = argparse.ArgumentParser(prog="grocery-run")
    parser.add_argument("--list-name", required=True, help="Google Tasks list name (e.g., Groceries)")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Repo root containing token.json/credentials.json",
    )
    parser.add_argument(
        "--products",
        default=str(Path(__file__).resolve().parents[2] / "data" / "products.json"),
        help="Path to products.json",
    )
    parser.add_argument(
        "--substitutions",
        default=str(Path(__file__).resolve().parents[2] / "data" / "substitutions.json"),
        help="Path to substitutions.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="Verify mappings only; do not open Hy-Vee")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    products_path = Path(args.products)
    substitutions_path = Path(args.substitutions)

    try:
        raw_titles = gtasks.fetch_open_task_titles(repo_root=repo_root, list_name=args.list_name)
        subs = json.loads(substitutions_path.read_text(encoding="utf-8"))
        normalized = gtasks.normalize(items=raw_titles, substitutions=subs)
        normalized_names = [x["normalized"] for x in normalized]

        _, unmapped = library.verify_all_mapped(products_path, normalized_names)
        if unmapped:
            # Exit on first unknown with explicit instruction.
            item = unmapped[0]
            err = unknown_item(item, build_search_url(item))
            print(err.format())
            return err.code

        if args.dry_run:
            print("All items mapped.")
            return 0

        # Next phase: Hy-Vee orchestration will be added next.
        raise GroceryError(
            code=99,
            short="Not implemented",
            context="Hy-Vee orchestration layer not implemented yet",
            next_step="Run with --dry-run for now",
        )
    except GroceryError as e:
        print(e.format())
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())


