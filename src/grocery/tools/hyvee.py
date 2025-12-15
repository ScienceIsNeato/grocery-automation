"""Hy-Vee browser automation tools.

Playwright is a hard dependency for this project. We import it normally and
fail fast if it isn't installed.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import sync_playwright


@dataclass(frozen=True)
class ProductCandidate:
    name: str
    price: str
    url: str
    product_id: str
    add_button_label: str


def build_search_url(query: str) -> str:
    return f"https://www.hy-vee.com/aisles-online/search?search={query.replace(' ', '+')}"


def _dismiss_popups(page: Any) -> None:
    # Best-effort; failures are non-fatal.
    time.sleep(0.5)
    try:
        cancel_btn = page.locator('button:has-text("Cancel")').first
        if cancel_btn.is_visible(timeout=1000):
            cancel_btn.click()
            time.sleep(0.2)
    except Exception:
        pass
    try:
        continue_btn = page.locator('button:has-text("Continue to Site")').first
        if continue_btn.is_visible(timeout=1000):
            continue_btn.click()
            time.sleep(0.2)
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
        time.sleep(0.1)
    except Exception:
        pass


def start_browser(*, headless: bool = False) -> tuple[Any, Any, Any]:
    """Return (playwright, browser, page)."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
    )
    page = context.new_page()
    page.set_default_timeout(30000)
    return playwright, browser, page


def stop_browser(playwright: Any, browser: Any, page: Any) -> None:
    try:
        if page:
            page.close()
    finally:
        try:
            if browser:
                browser.close()
        finally:
            if playwright:
                playwright.stop()


def ensure_logged_in(page: Any, *, email: str | None = None, password: str | None = None) -> None:
    """Navigate to Hy-Vee and log in if needed (best-effort)."""
    email = email or os.getenv("HYVEE_EMAIL")
    password = password or os.getenv("HYVEE_PASSWORD")

    page.goto("https://www.hy-vee.com/aisles-online/")
    time.sleep(2)

    # Determine login state by presence of "Log In" control.
    # (The word "Delivery" appears in marketing copy, so it is not a reliable signal.)
    try:
        login_control = page.locator(
            'a:has-text("Log In"), button:has-text("Log In"), a:has-text("Log in"), button:has-text("Log in")'
        ).first
        if not login_control.is_visible(timeout=1000):
            _dismiss_popups(page)
            return
    except Exception:
        # If we can't locate the login control, fall back to attempting login.
        pass

    # Open login modal.
    try:
        login_control = page.locator(
            'a:has-text("Log In"), button:has-text("Log In"), a:has-text("Log in"), button:has-text("Log in")'
        ).first
        login_control.click(timeout=5000)
        time.sleep(1)
    except Exception as e:
        raise RuntimeError("Could not open Hy-Vee login UI.") from e

    if not (email and password):
        raise RuntimeError("Hy-Vee credentials missing (HYVEE_EMAIL/HYVEE_PASSWORD).")

    # Fill login form (modal or page).
    page.wait_for_selector(
        'input[type="email"], input[name="email"], input[name*="email"], input[id*="email"]',
        timeout=15000,
    )
    page.locator('input[type="email"], input[name="email"], input[name*="email"], input[id*="email"]').first.click()
    page.locator('input[type="email"], input[name="email"], input[name*="email"], input[id*="email"]').first.fill(email)
    page.locator('input[type="password"], input[name="password"], input[name*="password"], input[id*="password"]').first.click()
    page.locator('input[type="password"], input[name="password"], input[name*="password"], input[id*="password"]').first.fill(password)
    page.locator('button:has-text("Log In"), button:has-text("Log in")').last.click()
    time.sleep(4)

    # After submit, "Log In" control should disappear when authenticated.
    try:
        login_control = page.locator('a:has-text("Log In"), button:has-text("Log In")').first
        if login_control.is_visible(timeout=1000):
            raise RuntimeError("Hy-Vee login may have failed (Log In still visible).")
    except RuntimeError:
        raise
    except Exception:
        # If DOM probing fails, do not silently assume success.
        raise RuntimeError("Hy-Vee login state could not be verified.")

    _dismiss_popups(page)


def search(page: Any, *, query: str, limit: int = 5) -> list[ProductCandidate]:
    page.goto(build_search_url(query), timeout=15000)
    time.sleep(2)
    try:
        page.keyboard.press("PageDown")
    except Exception:
        pass
    time.sleep(0.8)

    buttons = page.locator('button[aria-label^="Add to cart"]').all()
    results: list[ProductCandidate] = []
    for button in buttons[:limit]:
        aria = button.get_attribute("aria-label") or ""
        if not aria.startswith("Add to cart"):
            continue
        product_info = aria.replace("Add to cart, ", "")
        name = product_info.strip()
        price = ""
        if "$" in product_info:
            parts = product_info.split("$", 1)
            name = parts[0].strip()
            price = "$" + parts[1].split()[0] if parts[1].split() else ""

        url = ""
        try:
            container = button.locator("xpath=ancestor::article").first
            link = container.locator("a").first
            href = link.get_attribute("href")
            if href:
                url = href if href.startswith("http") else f"https://www.hy-vee.com{href}"
        except Exception:
            url = ""

        product_id = ""
        if url and "/p/" in url:
            product_id = url.split("/p/")[-1].split("/")[0]

        results.append(
            ProductCandidate(
                name=name,
                price=price or "N/A",
                url=url,
                product_id=product_id,
                add_button_label=aria,
            )
        )

    return results


def add_to_cart_from_search(page: Any, *, add_button_label: str) -> bool:
    try:
        page.locator(f'button[aria-label="{add_button_label}"]').first.click()
        time.sleep(0.8)
        return True
    except Exception:
        return False


def get_cart_contents(page: Any) -> list[str]:
    # Hy-Vee cart URL behavior has been inconsistent; we try best-effort.
    try:
        page.goto("https://www.hy-vee.com/aisles-online/cart", timeout=15000)
        time.sleep(2)
    except Exception:
        # Fallback: return empty rather than failing hard.
        return []

    items: list[str] = []
    for item in page.locator('article, [data-testid*="cart-item"]').all():
        name = None
        for sel in ["h2", "h3", 'a[href*="/p/"]', '[class*="name"]', '[class*="title"]']:
            try:
                txt = item.locator(sel).first.inner_text(timeout=500).strip()
                if txt:
                    name = txt
                    break
            except Exception:
                continue
        if name:
            items.append(name)
    return items



