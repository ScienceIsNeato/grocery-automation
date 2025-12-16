"""Consistent error formatting and exit codes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroceryError(Exception):
    code: int
    short: str
    context: str
    next_step: str

    def format(self) -> str:
        return (
            f"ERROR [{self.code}]: {self.short}\n"
            f"  Context: {self.context}\n"
            f"  Next step: {self.next_step}\n"
        )


def unknown_item(item: str, search_url: str) -> GroceryError:
    return GroceryError(
        code=1,
        short="Unknown/unmapped item",
        context=f'Item "{item}" has no mapping in products.json',
        next_step=(
            f"Search and add manually: {search_url} then re-run. "
            'If this is non-grocery, move it to another list with: '
            f'grocery-run --list-name "Groceries" --move-item "{item}" --move-to-list "To Purchase for Condo"'
        ),
    )


def add_to_cart_failed(item: str, attempts: int, url: str) -> GroceryError:
    return GroceryError(
        code=11,
        short="Failed to add item to cart",
        context=f'Item "{item}", attempted {attempts} times',
        next_step=f"Add manually: {url} then re-run",
    )


def hyvee_no_search_results(item: str, search_url: str) -> GroceryError:
    return GroceryError(
        code=10,
        short="Hy-Vee search returned no results",
        context=f'Item "{item}" did not return any add-to-cart results',
        next_step=f"Search and add manually: {search_url} then re-run",
    )


def hyvee_setup_required(detail: str) -> GroceryError:
    return GroceryError(
        code=10,
        short="Hy-Vee automation setup required",
        context=detail,
        next_step="Run: python -m playwright install (then re-run)",
    )


