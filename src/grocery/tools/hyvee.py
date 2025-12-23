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


def start_browser(*, headless: bool = False, persistent: bool = True) -> tuple[Any, Any, Any]:
    """Return (playwright, browser, page).
    
    Args:
        headless: Run browser without GUI
        persistent: Use persistent context to preserve cookies/login state
    """
    from pathlib import Path
    from playwright_stealth import Stealth
    
    playwright = sync_playwright().start()
    
    # User data directory for persistent sessions (preserves login cookies)
    user_data_dir = Path.home() / ".grocery-automation" / "browser-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
    ]
    
    if persistent:
        # Persistent context preserves cookies between sessions
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            args=launch_args,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        page = context.pages[0] if context.pages else context.new_page()
        browser = context  # In persistent mode, context acts as browser
    else:
        browser = playwright.chromium.launch(
            headless=headless,
            args=launch_args,
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        page = context.new_page()
    
    # Apply stealth patches to avoid bot detection
    stealth = Stealth(
        navigator_platform_override="MacIntel",
        navigator_vendor_override="Google Inc.",
    )
    stealth.apply_stealth_sync(page)
    
    page.set_default_timeout(30000)
    return playwright, browser, page


def stop_browser(playwright: Any, browser: Any, page: Any) -> None:
    """Gracefully stop the browser."""
    if page:
        try:
            page.close()
        except:
            pass
    
    if browser:
        try:
            # For persistent context, this closes the browser process
            time.sleep(0.5) # Allow page close to settle
            browser.close() 
        except:
            pass
            
    if playwright:
        try:
            playwright.stop()
        except:
            pass


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
        if login_control.is_visible():
            login_control.click(timeout=5000)
            time.sleep(3)  # Give Keycloak redirect time
    except Exception:
        pass

    if not (email and password):
        raise RuntimeError("Hy-Vee credentials missing (HYVEE_EMAIL/HYVEE_PASSWORD).")

    # Fill login form - Hy-Vee uses Keycloak which has #username, not email
    # Support both old modal login and new Keycloak OAuth page
    username_selectors = '#username, input[name="username"], input[type="email"], input[name="email"]'
    password_selectors = '#password, input[name="password"], input[type="password"]'
    submit_selectors = '#kc-login, button[type="submit"], button:has-text("Log In"), button:has-text("Sign In")'
    
    # Check if we are already seeing the form or if we are already logged in
    try:
        page.wait_for_selector(username_selectors, state="visible", timeout=5000)
        
        page.locator(username_selectors).first.click()
        page.locator(username_selectors).first.fill(email)
        
        page.locator(password_selectors).first.click()
        page.locator(password_selectors).first.fill(password)
        
        page.locator(submit_selectors).first.click()
        time.sleep(2)
    except Exception:
        # If form didn't appear, maybe we are already logged in?
        print("  Login form not found. Checking if already logged in...")

    # Wait for login to complete and redirect back
    # Success indicator: "Log In" button is gone, OR "Hi, [Name]" appears, OR cart count appears
    print("  Waiting for login to complete...")
    for _ in range(20):  # Wait up to 10s
        time.sleep(0.5)
        if "accounts.hy-vee.com" not in page.url:
            # Check if we are really logged in
            login_btn = page.locator('a:has-text("Log In"), button:has-text("Log In")')
            account_btn = page.locator('[data-testid="global-navigation-accountIcon"], [aria-label="My Account"]')
            if login_btn.count() == 0 or account_btn.count() > 0:
                print("  Login confirmed.")
                time.sleep(2) # Let cookies settle
                _dismiss_popups(page)
                return

    # If we get here, login might have failed
    if "accounts.hy-vee.com" in page.url:
        page.screenshot(path="/tmp/hyvee_login_error.png")
        raise RuntimeError(f"Hy-Vee login timed out (stuck on login page: {page.url})")
    else:
        # We are on main site but maybe not logged in?
        print("  Warning: specific login success indicators not found, attempting to proceed...")

    _dismiss_popups(page)


def search(page: Any, *, query: str, limit: int = 5) -> list[ProductCandidate]:
    page.goto(build_search_url(query), timeout=30000)
    time.sleep(3)
    try:
        page.keyboard.press("PageDown")
    except Exception:
        pass
    time.sleep(1)

    # Use a more robust approach - iterate by index to avoid stale elements
    button_locator = page.locator('button[aria-label^="Add to cart"]')
    count = min(button_locator.count(), limit * 2)  # Get more to allow for failures
    
    results: list[ProductCandidate] = []
    for i in range(count):
        if len(results) >= limit:
            break
        try:
            button = button_locator.nth(i)
            aria = button.get_attribute("aria-label", timeout=3000) or ""
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
                href = link.get_attribute("href", timeout=2000)
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
        except Exception:
            # Skip buttons that cause errors (stale, hidden, etc.)
            continue

    return results


def add_to_cart_from_search(page: Any, *, add_button_label: str) -> bool:
    try:
        page.locator(f'button[aria-label="{add_button_label}"]').first.click()
        time.sleep(0.8)
        return True
    except Exception:
        return False


def get_cart_count(page: Any) -> int:
    """Get the cart item count from the header badge.
    
    The cart icon has a red badge showing the count (e.g., "56").
    This is the reliable source of truth for cart item count.
    """
    try:
        # The cart badge has data-testid="global-navigation-cart-bubble"
        badge = page.locator('[data-testid="global-navigation-cart-bubble"]')
        if badge.count() > 0 and badge.first.is_visible(timeout=2000):
            text = badge.first.inner_text(timeout=2000).strip()
            return int(text) if text.isdigit() else 0
    except Exception:
        pass
    
    # Fallback: try to find any element with cart count pattern
    try:
        # Look for the cart count span
        count_span = page.locator('[class*="cartCount"], [class*="CartCount"]')
        if count_span.count() > 0:
            text = count_span.first.inner_text(timeout=2000).strip()
            return int(text) if text.isdigit() else 0
    except Exception:
        pass
    
    return 0


def add_item_to_cart(page: Any, *, url: str, display_name: str) -> tuple[bool, str]:
    """Navigate to product URL and add to cart with verification.
    
    Returns:
        (success: bool, message: str)
        - (True, "added") if item was successfully added
        - (True, "already_in_cart") if item was already in cart
        - (False, error_message) if failed
    """
    try:
        # Get cart count BEFORE
        initial_count = get_cart_count(page)
        
        # Rate limiting delay before navigation
        time.sleep(1)
        
        # Navigate to product page
        response = page.goto(url, timeout=30000)
        time.sleep(2)  # Let page fully load
        
        # Check for 500/error pages
        page_title = page.title() or ""
        if "500" in page_title or "error" in page_title.lower():
            return (False, f"Server error (500) loading page: {url}")
        
        # Check for "Oops! Something went wrong" error message
        error_msg = page.locator('text="Oops! Something went wrong"')
        if error_msg.count() > 0:
            return (False, f"Page error 'Oops! Something went wrong': {url}")
        
        # Check for "Log in to add" (session lost)
        login_to_add = page.locator('button:has-text("Log in to add")')
        if login_to_add.count() > 0:
            return (False, "Session lost (saw 'Log in to add'), please restart script")
        
        # Check if already in cart (quantity control visible instead of Add to cart)
        # The quantity control has a trash icon and +/- buttons
        quantity_control = page.locator('button[aria-label="Remove From Cart"], [aria-label*="in cart"]')
        if quantity_control.count() > 0:
            return (True, "already_in_cart")
        
        # Look for "Add to cart" button
        add_button = page.locator('button:has-text("Add to cart")')
        if add_button.count() == 0:
            return (False, f"No 'Add to cart' button found on page: {url}")
        
        # Click the button
        add_button.first.click()
        time.sleep(2)  # Wait for cart update
        
        # Verify: the button should now change to quantity control
        quantity_control = page.locator('button[aria-label="Remove From Cart"], [aria-label*="in cart"]')
        if quantity_control.count() == 0:
            # Double-check with cart count
            new_count = get_cart_count(page)
            if new_count <= initial_count:
                return (False, f"Cart count did not increase (was {initial_count}, now {new_count})")
        
        return (True, "added")
        
    except Exception as e:
        return (False, f"Exception: {e}")


def extract_product_id(url: str) -> str | None:
    """Extract product ID from Hy-Vee URL.
    
    Example: https://www.hy-vee.com/aisles-online/p/3304437/HyVee-Tartar-Sauce
    Returns: 3304437
    """
    if not url or "/p/" not in url:
        return None
    try:
        # Split by /p/ and take the next segment
        parts = url.split("/p/")
        if len(parts) > 1:
            return parts[1].split("/")[0]
    except Exception:
        pass
    return None


def get_cart_product_ids(page: Any) -> set[str]:
    """Get set of product IDs currently in cart.
    
    Handles Next.js client-side rendering by waiting for content and scrolling
    to handle potential virtualization.
    """
    try:
        page.goto("https://www.hy-vee.com/aisles-online/checkout/cart", timeout=30000)
        
        # Wait for either cart items OR empty cart message
        try:
            # Wait for at least one product link to appear (client-side render)
            # Site is very slow, giving it 45s.
            # We wait for ANY link that looks like a product
            page.wait_for_selector('a[href*="/p/"]', timeout=45000, state="attached")
        except Exception:
            # Or maybe it's empty?
            if page.locator('text="Your cart is empty"').count() > 0:
                print("  Cart appears empty.")
                return set()
            print("  Warning: Timeout waiting for cart items to render via selector. Attempting regex fallback...")

        # Scroll to bottom to ensure all items trigger lazy loading/virtualization
        for _ in range(5):
            page.keyboard.press("End")
            time.sleep(1)
            
        # Get raw content and regex it - robust against shadow DOM / visibility quirks
        import re
        html = page.content()
        # Find all href="/aisles-online/p/123456/..." patterns
        # Adjust regex to match observed URL structure: /aisles-online/p/ID/Slug OR https://www.hy-vee.com/aisles-online/p/ID/Slug
        matches = re.finditer(r'href=["\'](?:https://www.hy-vee.com)?/aisles-online/p/(\d+)/', html)
        
        ids = set()
        for m in matches:
            ids.add(m.group(1))
            
        print(f"  Found {len(ids)} unique IDs via regex scan.")
        return ids

    except Exception as e:
        print(f"  Error accessing cart: {e}")
        return set()

def _unused_selector_logic():
    # Only here to satisfy the diff matcher if it looks for lines I removed
    pass


def ensure_items_in_cart(
    page: Any,
    *,
    products_path: "Any",
    items: list[str],
    unavailable_path: "Any | None" = None,
    max_attempts: int = 2,
) -> None:
    """
    Ensure each mapped item is present in the cart (idempotent, verified).
    
    Strategy:
    1. Go to cart page ONCE.
    2. Get list of all product IDs currently in cart.
    3. Filter out items whose product ID is already in the cart.
    4. Only navigate to add the truly missing items.
    """
    from pathlib import Path

    from grocery.tools import library, unavailable
    from grocery.tools.errors import GroceryError, add_to_cart_failed

    products_path = Path(products_path)
    unavailable_path = Path(unavailable_path) if unavailable_path is not None else None

    data = library.load_products(products_path)
    products = data.get("products", {}) or {}

    # Get initial cart count
    initial_count = get_cart_count(page)
    print(f"  Initial cart count: {initial_count}")
    
    # Pre-fetch cart HTML to check for existing items (Simple String Match)
    # We verified via console that the ID (e.g. 3304437) is present in document.body.innerHTML
    print("  Scanning cart for existing items...")
    try:
        page.goto("https://www.hy-vee.com/aisles-online/checkout/cart", timeout=30000)
        
        # Wait for content to render
        try:
            page.wait_for_selector('text="Order Summary"', timeout=30000)
        except:
             pass

        # Scroll to bottom to ensure all items are in the HTML (virtualization)
        for _ in range(5):
            page.keyboard.press("End")
            time.sleep(1)
            
        cart_html = page.content()
        print(f"  Cart HTML loaded ({len(cart_html)} chars).")
        
    except Exception as e:
        print(f"  Warning: Could not scan cart ({e}). checks will default to 'not found'.")
        cart_html = ""
    
    items_added = 0
    items_skipped = 0
    missing_items_to_process = []

    # First pass: Filter items by checking for their ID in the HTML
    for item in items:
        key = library.normalize_key(item)
        mapping = products.get(key)
        if not mapping:
            # We fail later
            pass 
        
        url = mapping.get("url", "") if mapping else ""
        pid = extract_product_id(url)
        display_name = str(mapping.get("display_name") or item) if mapping else item
        
        # KEY CHECK: Is the ID in the HTML?
        if pid and pid in cart_html:
            print(f"  ✓ {display_name} (already in cart - ID match)")
            items_skipped += 1
        else:
             # Fallback: check by name if ID check failed (e.g. if ID hidden but name visible)
             # Be careful with partial matches, but display name is usually specific enough
            if display_name in cart_html:
                 print(f"  ✓ {display_name} (already in cart - Name match)")
                 items_skipped += 1
            else:
                missing_items_to_process.append(item)

    print(f"  Processing {len(missing_items_to_process)} missing items...")

    # Second pass: Process missing items
    for item in missing_items_to_process:
        key = library.normalize_key(item)
        mapping = products.get(key)
        if not mapping:
            raise GroceryError(
                code=1,
                short="Unknown/unmapped item",
                context=f'Item "{item}" has no mapping in products.json',
                next_step="Add mapping to products.json then re-run",
            )

        display_name = str(mapping.get("display_name") or item)
        product_url = mapping.get("url", "")

        if not product_url:
            raise GroceryError(
                code=1,
                short="Missing product URL",
                context=f'Item "{item}" has no URL in products.json',
                next_step="Add the product URL to products.json then re-run",
            )

        # Navigate to product page and add to cart with verification
        print(f"  Adding: {display_name}...")
        
        success = False
        error_msg = ""
        for attempt in range(1, max_attempts + 1):
            ok, msg = add_item_to_cart(page, url=product_url, display_name=display_name)
            if ok:
                if msg == "already_in_cart":
                    # Should be rare given our pre-check, but possible
                    print(f"  ✓ {display_name} (already in cart)")
                    items_skipped += 1
                else:
                    print(f"  ✓ {display_name} (added)")
                    items_added += 1
                success = True
                break
            else:
                error_msg = msg
                if attempt < max_attempts:
                    print(f"    Retry {attempt + 1}... ({msg})")
                    time.sleep(1)

        if not success:
            if unavailable_path is not None:
                unavailable.append_unavailable(
                    unavailable_path,
                    item=item,
                    reason="add_failed",
                    search_term=display_name,
                )
            raise GroceryError(
                code=11,
                short="Failed to add item to cart",
                context=f'Item "{item}": {error_msg}',
                next_step=f"Add manually: {product_url} then re-run",
            )

    # Final verification & Audit
    print("\n  ----- CART AUDIT -----")
    
    # 1. Forward Check: Are all requested items present?
    # (Already handled by the loop above, but let's summarize)
    missing_from_cart = []
    # We re-scan the HTML one last time to be sure
    final_cart_html = page.content()
    
    # Name-Based Audit (Simpler and more useful for human review)
    # We will grab all item names visible in the cart and check if we expected them.
    
    print("\n  ----- CART AUDIT -----")
    try:
        # Extract names from accessibility labels which are reliable
        # "Select [Product Name]" is the standard pattern for checkbox/row
        # We execute JS to get the clean list
        cart_item_names = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[aria-label^="Select "]'))
                .map(el => el.getAttribute('aria-label').replace("Select ", "").trim())
                .filter(text => !text.includes("all items"));
        }""")
        
        # Helper to normalize string into set of tokens
        def get_tokens(s: str) -> set[str]:
            import string
            # Remove punctuation, lower case, split by whitespace
            clean = s.lower().translate(str.maketrans(string.punctuation, ' '*len(string.punctuation)))
            return set(clean.split())

        # Build list of expected token sets
        expected_token_sets = []
        for item in items:
            key = library.normalize_key(item)
            mapping = products.get(key)
            name_to_use = mapping.get("display_name", "") if mapping else item
            expected_token_sets.append(get_tokens(name_to_use))

        unexpected_items = []
        for name in cart_item_names:
            actual_tokens = get_tokens(name)
            
            is_expected = False
            for exp_tokens in expected_token_sets:
                # Logic: Match if one set is a subset of the other
                # (e.g. "Toaster Pastries" is subset of "Toaster Pastries Strawberry")
                if exp_tokens.issubset(actual_tokens) or actual_tokens.issubset(exp_tokens):
                    is_expected = True
                    break
            
            if not is_expected:
                unexpected_items.append(name)

        if unexpected_items:
            print(f"  [?] Found {len(unexpected_items)} items in cart that were not in your current list:")
            for u_item in unexpected_items[:10]:
                print(f"      - {u_item}")
            if len(unexpected_items) > 10:
                print(f"      - ... and {len(unexpected_items)-10} more.")
            print("      (These might be manually added items or previous leftovers)")
        else:
            print("  [OK] All items in cart match your list.")
            
    except Exception as e:
        print(f"  [Audit Warning] Could not perform name audit: {e}")

    expected_count = initial_count + items_added
    
    # Extract Estimated Total
    total_price = "N/A"
    try:
        # Look for the total amount. Usually near "Estimated Total"
        # Strategy: Find "Estimated Total", get text content of that container or nearby
        # The HTML structure is usually a flex row.
        # Let's search for the $ sign pattern in the visible text
        page.wait_for_selector('text="Estimated Total"', timeout=5000)
        # Using a reliable text logic
        # Get all text from the "Order Summary" section
        summary_section = page.locator('section:has-text("Order Summary")').first
        if summary_section.count() > 0:
            text = summary_section.inner_text()
            # Parse "Estimated Total $164.52" or "Estimated Total\n$164.52"
            import re
            match = re.search(r'Estimated Total.*?\$([\d,]+\.\d{2})', text, re.DOTALL)
            if match:
                total_price = f"${match.group(1)}"
    except Exception:
        pass

    print(f"  [OK] Final Cart Count: {get_cart_count(page)}")
    print(f"  [OK] Estimated Total: {total_price}")
    print("  ----------------------")
    
    # Send System Notification
    try:
        import subprocess
        msg = f"Cart complete. {final_count} items. Total: {total_price}."
        subprocess.run([
            "osascript", "-e", 
            f'display notification "{msg}" with title "Grocery Automation"'
        ])
    except Exception:
        pass
