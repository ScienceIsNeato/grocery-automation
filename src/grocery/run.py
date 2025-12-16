"""
Orchestrator entry point (single command interface).

Implementation will be built tool-by-tool via TDD.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from grocery.tools import gtasks, library
from grocery.tools.errors import GroceryError, hyvee_setup_required, unknown_item
from grocery.tools.hyvee import build_search_url
from grocery.tools import hyvee


def main() -> int:
    parser = argparse.ArgumentParser(prog="grocery-run")
    parser.add_argument("--list-name", required=True, help="Google Tasks list name (e.g., Groceries)")
    parser.add_argument(
        "--move-item",
        action="append",
        default=[],
        help='Move a non-grocery item title from --list-name to --move-to-list (repeatable). Example: --move-item "ornaments"',
    )
    parser.add_argument(
        "--move-to-list",
        default=None,
        help='Destination list name for --move-item (e.g., "To Purchase for Condo")',
    )
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
    parser.add_argument(
        "--unavailable",
        default=str(Path(__file__).resolve().parents[2] / "data" / "unavailable.json"),
        help="Path to unavailable.json log",
    )
    parser.add_argument("--dry-run", action="store_true", help="Verify mappings only; do not open Hy-Vee")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    products_path = Path(args.products)
    substitutions_path = Path(args.substitutions)
    unavailable_path = Path(args.unavailable)

    try:
        if args.move_item:
            if not args.move_to_list:
                raise GroceryError(
                    code=2,
                    short="Missing destination list",
                    context="--move-item requires --move-to-list",
                    next_step='Re-run with: --move-to-list "To Purchase for Condo"',
                )
            moved = gtasks.move_open_tasks_by_title(
                repo_root=repo_root,
                source_list_name=args.list_name,
                dest_list_name=args.move_to_list,
                titles=list(args.move_item),
            )
            print(f"Moved {moved} task(s) to list: {args.move_to_list}")
            return 0

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

        playwright = browser = page = None
        try:
            try:
                playwright, browser, page = hyvee.start_browser(headless=args.headless)
            except Exception as e:
                raise hyvee_setup_required(str(e)) from e

            hyvee.ensure_logged_in(page)
            hyvee.ensure_items_in_cart(
                page,
                products_path=products_path,
                items=normalized_names,
                unavailable_path=unavailable_path,
            )
            print("Cart update complete. Hard stop before checkout.")
            return 0
        finally:
            try:
                if playwright or browser or page:
                    hyvee.stop_browser(playwright, browser, page)
            except Exception:
                # Cleanup errors shouldn't mask the primary result.
                pass
    except GroceryError as e:
        print(e.format())
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())


