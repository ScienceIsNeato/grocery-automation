# Grocery Automation — Session Handoff Status

This file is intended to let a new engineer (or future-you) take over this session with minimal context loss.

## 0) One-sentence goal
Automate “Google Tasks grocery list → Hy-Vee cart” using **small, testable tools** orchestrated by one command, with a **repeatable, idempotent protocol** and a **hard manual gate before checkout**.

### Accomplishments
*   **Robust Cart Orchestration**:
    *   **Idempotency**: Implemented pre-scan logic that checks the cart before adding. Reduced run time from minutes to seconds for re-runs.
    *   **Audit System**: Added "Token Subset Matching" audit that verifies cart contents against the expected list using Name-based matching (handles flavor variations like "Pop-Tarts").
    *   **Hallucination Check**: Explicitly flags items in the cart that were not requested (e.g. "Eggs").
    *   **Resilience**: Added robust session recovery (detects "Log in to add") and "Chrome Quit Unexpectedly" prevention.
*   **Verification**:
    *   Validated logic with user-driven Console JS commands to ensure DOM assumptions matched reality.
*   **Google Tasks Integration**:
    *   Fixed OAuth scope issues (`read-write`) to prevent token expiration.
    *   Seamless sync of Task List -> Dictionary -> Cart.
*   **Foundational Tools**:
    *   `library.py` for product mapping management.
    *   `unavailable.py` for tracking missing items.

### Technical Learnings
*   **Hypothesis Testing**: Guessing DOM structures (like `data-product-id`) failed. Using `page.content()` raw dumps or Analytics tags (`window.svq`) provided the only source of truth.
*   **Fuzzy Matching**: Simple string equality fails on e-commerce titles due to punctuation (",") and inserted words (Flavor variations). **Token Set Intersection** is the required solution.
*   **Hydration Issues**: Next.js client-side rendering caused standard `wait_for_selector` timeouts. Fallback to `page.content()` string scanning was necessary for stability.

### Recent Issues & Fixes
*   **False Positives in Audit**: Audit initially flagged "Pop-Tarts" as unexpected because of extra words in the title.
    *   *Fix*: Implemented `get_tokens()` subset matching to ignore inserted flavor text.
*   **Unknown IDs**: Visual List order did not match Analytics ID order.
    *   *Fix*: Switched to Name-Based Audit which is human-readable and order-independent.

### Immediate Next Steps
1.  **GitHub Actions (CI)**:
    *   Create `.github/workflows/test.yaml` to run `pytest`.
2.  **Scheduling**:
    *   Add to `crontab` for weekly execution.
3.  **Notifications**:
    *   Expand notification system (currently local macOS) to Email/SMS if needed.

### Todo List
*   [ ] **CI Implementation**: Set up GitHub Actions for automated testing.
*   [ ] **Notification**: Add `notify_user()` function (Desktop/Email).
*   [ ] **Unmapped Wizard**: Interactive CLI mode to resolve unmapped items instantly.
*   [ ] **Substitutions**: Handle out-of-stock items with intelligent substitution logic.

### Last Updated
2025-12-16

### Commands
*   **Run**: `python -m grocery.run --list-name "Groceries"`
*   **Test**: `pytest`
*   **Lint**: `ruff check .`
*   **Format**: `ruff format .`
   - Open the provided Hy-Vee search URL.
   - Identify the correct product.
   - Add mapping to `data/products.json`.
   - Re-run step 1.
3. Repeat until it prints: **“All items mapped.”**

### Phase B — Cart population (future)
Once implemented, reruns should be safe:
- For each item:
  - If mapped: check cart; if not present, add; if already present, warn + continue.
  - If unmapped: trigger mapping protocol and exit early (no partial ambiguity).

### Phase C — Hard stop at checkout (future)
- Automation must **never click checkout**.
- Script should stop and instruct the user to complete checkout manually.

### Phase D — Post-checkout reconciliation (future)
- After the user confirms checkout completed successfully, mark corresponding Google Tasks complete.

## 3) Key design principles (non-negotiable)
- **Modular tools**: “one thing well” functions under `src/grocery/tools/`.
- **Idempotency**: re-running should not create duplicates or corrupt state.
- **Exit on unknown**: unmapped item stops the run with explicit next steps.
- **Hard manual gate** before checkout.
- **TDD**: tests first for each tool/behavior.

## 4) Repo layout (what to read first)
### Entry point
- `src/grocery/run.py`: orchestrator CLI (currently: mapping verification + planned cart orchestration).

### Tools
- `src/grocery/tools/gtasks.py`: Google Tasks fetch + normalization.
- `src/grocery/tools/library.py`: `products.json` read/write/verify helpers.
- `src/grocery/tools/hyvee.py`: Hy-Vee helper primitives (e.g., search URL builder; browser automation helpers live/should live here).
- `src/grocery/tools/errors.py`: structured errors with exit codes and “next step” messages.
- `src/grocery/tools/unavailable.py`: logging for not_found/out_of_stock/etc.

### Data
- `data/products.json`: canonical mapping library (normalized name → Hy-Vee product identity).
- `data/substitutions.json`: normalization substitutions.
- `data/unavailable.json`: append-only log for unavailable/out-of-stock/other warnings.

### Tests
- `tests/`: unit tests for each tool + orchestrator dry-run.

## 5) Commands (local)
### Install deps
This repo uses `pyproject.toml` with runtime deps:
- `google-api-python-client`, `google-auth`, `google-auth-oauthlib`, `playwright`

Minimal setup example (one-time):
- Create venv, install deps, install browsers:
  - `python -m venv venv`
  - `source venv/bin/activate`
  - `pip install -e .[dev]`
  - `python -m playwright install`

### Run tests
- `python -m pytest`

### Run orchestrator
- `python -m grocery.run --list-name "Groceries" --dry-run`

## 6) Secrets / auth model (what MUST NOT be committed)
This is intended to be a **public repo**.

Local-only files:
- `credentials.json` (Google OAuth client secrets)
- `token.json` (Google OAuth token cache)
- `.envrc` (recommended location for env vars)

Env vars (names only; values must never be stored in git):
- `HYVEE_EMAIL`
- `HYVEE_PASSWORD`

## 7) Known failure modes + intended behavior
### Browser automation risks
- Hy-Vee site changes, popups/modals, A/B tests.
- Potential CAPTCHA / bot detection.

### Intended error strategy
- Every failure should print:
  - a short description
  - a clear next step
  - an explicit exit code

Baseline exit code expectations (expand as implemented):
- `1`: unknown/unmapped item (requires mapping + re-run)
- `10+`: Hy-Vee login/add-to-cart failures (action required)
- `12`: network timeout / retry exhausted
- `20+`: Google Tasks auth errors
- `99`: unimplemented orchestrator phase (current state)

## 8) What to do next (highest leverage)
1. **Publish repo** (init git, first commit, `gh repo create grocery-automation --public ...`).
2. Confirm `.gitignore` excludes `token.json`, `credentials.json`, `.envrc`.
3. Keep iterating on Phase A until mapping coverage is mature.
4. Only then implement Phase B (cart idempotency) with TDD:
   - “already in cart” detection
   - add-to-cart success verification
   - unavailable/out-of-stock logging
5. Add the Phase C manual checkout gate.
6. Add Phase D (mark tasks complete) after checkout confirmation.

## 9) Session notes / history highlights (why things are this way)
- Early Hy-Vee attempts hit common automation issues (login reliability, popups, selector brittleness). This drove the design toward:
  - deterministic stop points
  - “exit on unknown” mapping loop
  - strict idempotency requirements
  - TDD and modular tooling

## 10) Current session handoff (2025-12-16 01:20)

### What just got implemented (this session)
1. **Mapping loop completed** ✅:
   - All items in "Groceries" list are now mapped
   - `--dry-run` prints: "All items mapped."
   - 9 product mappings added to `data/products.json`

2. **New CLI flags added**:
   - `--show-all-unmapped`: Shows all unmapped items at once (batch mode)
   - `--remove-item "item"`: Marks a task complete (removes from active list)
   - Both flags are repeatable for batch operations

3. **Tasks cleaned up**:
   - Moved to Condo list: ornaments, miracle grove plant food, six long candles
   - Marked complete: yasso bars, jello puddings, vanilla wafers, disposable gloves

4. **OAuth token refreshed**: Regenerated token.json with read-write scope

### Immediate next step
**Run the full cart orchestration**:
```bash
cd /Users/pacey/Documents/SourceCode/grocery-automation && \
source .venv/bin/activate && source .envrc && \
python -m grocery.run --list-name "Groceries"
```
This will:
- Log into Hy-Vee (headful browser)
- Add all mapped items to cart (idempotent)
- Stop before checkout (manual gate)

### Commands to commit this session's work
```bash
cd /Users/pacey/Documents/SourceCode/grocery-automation
git add -A
git commit -m "feat: complete mapping loop + batch CLI flags

- Add --show-all-unmapped flag to display all unmapped items at once
- Add --remove-item flag to mark tasks complete (batch removals)
- Add 9 product mappings to data/products.json
- Clean up tasks: move non-grocery items, mark completed items done
- Regenerate OAuth token with read-write scope
- Update STATUS.md with session handoff"
```

### Files changed this session
- `src/grocery/run.py` (added `--show-all-unmapped`, `--remove-item` flags)
- `data/products.json` (9 product mappings)
- `STATUS.md` (this handoff section)

## 12) TODOs - Future Improvements

### Verification & QA
- [ ] **Cart count sanity check**: Track initial count, items to add, expected final count - verify at end
- [ ] **Per-item verification**: After each add, confirm cart count increased by 1
- [ ] **Debug dump on error**: On any failure, dump screenshot, HTML, URL to `/tmp/hyvee_debug/`
- [ ] **Reverse-map cart items**: At end of session, warn for any items in cart that don't reverse-map to a known product in the list (catches hallucinated adds)
- [ ] **Idempotent retries**: On transient failure, retry with exponential backoff

### CI/CD
- [ ] **Rate limiting**: Add delays between requests to avoid bot detection/blocking
- [ ] **Headless validation**: Periodic headless test runs against staging/test account
- [ ] **Integration tests**: End-to-end tests with mock Playwright responses

### UX Improvements  
- [ ] **Quantity support**: Handle `default_count` to add multiple of same item
- [ ] **Progress bar**: Show X/Y items processed
- [ ] **Dry-run cart preview**: Show what would be added without browser

## 13) Fuzzy Matching Phase (NEW - 2025-12-16 06:38)

### What changed
Added a **two-phase mapping workflow** to reduce unnecessary Hy-Vee searches:

**Phase 1: Fuzzy Match Existing Products** (new)
- Before searching Hy-Vee, check if unmapped items are just different phrasings
- Shows interactive HTML UI with:
  - Top 3 fuzzy matches (scored by similarity)
  - Option to browse all products alphabetically
  - Option to mark as "NEW" if truly new
- Generates `substitutions.json` entries to map new phrases → existing products
- Reduces redundant product mappings

**Phase 2: Hy-Vee Product Search** (existing, now only for "NEW" items)
- Shows HTML UI with Hy-Vee search links
- Only shown for items marked "NEW" in Phase 1
- Or use `--skip-fuzzy` flag to skip straight to this phase

### Implementation
- `src/grocery/tools/library.py`: Added `fuzzy_match_products()` using `difflib`
- `src/grocery/tools/fuzzy_ui.py`: New HTML generator for Phase 1
- `src/grocery/run.py`: Wired fuzzy matching as first step
- `--skip-fuzzy` flag to bypass Phase 1 if already done

### Current state
- Fuzzy match HTML generated: `data/fuzzy_match_items.html`
- 34 unmapped items ready for Phase 1 review
- **Test failures**: 8 tests failing due to `hyvee.py` refactor (old `get_cart_contents` API removed)
  - Tests use old text-matching API
  - Current code uses product ID matching
  - Needs test fixture updates

### Next steps for next agent
1. **Fix 8 failing tests** in `tests/test_hyvee_cart_tools.py`, `tests/test_hyvee_login.py`, `tests/test_hyvee_search.py`
   - Update test fakes to match current `hyvee.py` API (product IDs, not text)
   - Add `.url` attribute to `_FakePage` in login tests
   - Add `.count()` method to `_FakeLocator` in search tests

2. **Complete mapping workflow**:
   - Work through `fuzzy_match_items.html` (already open)
   - Add generated substitutions to `data/substitutions.json`
   - Re-run orchestrator
   - For remaining NEW items, work through Hy-Vee search UI

## 14) Session continuation (2025-12-16 06:50)

### What changed (fuzzy UI improvements)
- Added **editable item names** (click to fix voice-to-text errors)
- Added **quantity field** (pre-populated from gtasks.normalize())
- Quantities forward-propagate to Hy-Vee search UI for NEW items
- Rows stay visible until "Update List Details" is clicked
- Adjudicated rows fade out after button click

### Current blocker
**"Update List Details" button needs backend server**:
- Currently generates downloadable Python script (UX is clunky)
- User wants: Click button → changes execute server-side automatically
- Need to: Add Flask/simple HTTP backend with POST `/apply-mappings` endpoint
- Backend writes substitutions.json, updates Google Tasks, writes new_items.json

### JavaScript syntax issues
- Complex nested template literals causing escaping hell
- Line 363 in generated JS has quote escaping bug
- All clicks work EXCEPT the Update List Details button execution logic

### Next agent todo
1. **Simplify backend approach**: Add Flask + POST endpoint OR use simpler HTTP handler
2. **Fix JavaScript**: Replace complex template literal script generation with simple fetch() POST
3. **Wire backend**: Start server in background when fuzzy UI shown, stop after apply
4. **Fix 8 failing tests**: Old hyvee.py API (get_cart_contents text-based → new product ID-based)
5. **Complete mapping workflow**: User adjudicates 34 items → run full cart orchestration

## 15) Last updated
- 2025-12-16 06:50 (Fuzzy UI improvements, needs backend server for auto-apply)
