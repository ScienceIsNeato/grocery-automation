# Grocery Automation — Session Handoff Status

This file is intended to let a new engineer (or future-you) take over this session with minimal context loss.

## 0) One-sentence goal
Automate “Google Tasks grocery list → Hy-Vee cart” using **small, testable tools** orchestrated by one command, with a **repeatable, idempotent protocol** and a **hard manual gate before checkout**.

## 1) Current state (what actually works today)
### ✅ Confirmed working
- **Repo structure + packaging**: Python package under `src/grocery/`.
- **Unit tests**: `pytest` suite exists and is expected to be the primary safety net.
- **Local venv**: project-local `.venv/` exists (created 2025-12-15) and `python -m pytest` passes inside it.
- **Google Tasks toolchain**:
  - Fetch open task titles from a named list.
  - Normalize item text (voice-to-text corrections, quantity parsing) using `data/substitutions.json`.
- **Product library**:
  - Verify which normalized items are mapped in `data/products.json`.
  - Deterministically identify unmapped items.
- **Orchestrator (mapping gate)**:
  - `python -m grocery.run --list-name <name> --dry-run` fetches tasks → normalizes → verifies mappings.
  - If anything is unmapped, it **prints a structured error** with a Hy-Vee search URL and exits with a **non-zero exit code**.

### 🚧 Not implemented yet (by design)
- **Hy-Vee cart orchestration layer** is *not* wired into the orchestrator.
  - Running without `--dry-run` currently exits with:
    - `code=99` and message: “Hy-Vee orchestration layer not implemented yet”.

## 2) Operating protocol (the intended repeatable workflow)
This is the “plain and simple protocol with explicit steps” the project is built around.

### Phase A — Mapping growth loop (safe to repeat)
1. Run:
   - `python -m grocery.run --list-name "Groceries" --dry-run`
2. If it exits with **Unknown/Unmapped Item**:
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

## 10) Current session handoff (2025-12-16)

### What just got implemented (this session)
1. **Phase B cart orchestration (complete)**:
   - `ensure_items_in_cart()` in `src/grocery/tools/hyvee.py`
   - Idempotent: checks cart, adds missing items, logs unavailable when search fails
   - Unit tests with fakes (28 passing tests total)
   - Wired into `grocery.run` main orchestrator for non-`--dry-run` path

2. **Non-grocery routing protocol (complete)**:
   - New CLI mode: `--move-item "item" --move-to-list "To Purchase for Condo"`
   - Moves tasks from Groceries list to Condo list via Google Tasks API
   - Use this when dry-run stops on items that shouldn't be bought at Hy‑Vee
   - Unit tests added to `tests/test_gtasks_complete.py`

3. **Project now installable**:
   - Updated `pyproject.toml` with `[build-system]` + `[project.scripts]`
   - Installed editable in `.venv`: `pip install -e ".[dev]"`
   - CLI works: `python -m grocery.run ...` or `grocery-run ...`

4. **OAuth/auth setup (complete)**:
   - `credentials.json` + `token.json` in repo root (gitignored)
   - `.envrc` contains `HYVEE_EMAIL` / `HYVEE_PASSWORD` (gitignored)
   - Playwright browsers installed in `.venv`

### Where we are in the mapping loop
- Ran `--dry-run` against real "Groceries" task list
- **Mapped so far**:
  - `frozen shrimp cocktail` → Fish Market Shrimp Platter (product_id 61417)
  - `short carrots` → Grimmway Baby Carrots (product_id 46176)
- **Stopped on**: `ornaments` (non-grocery item)

### Immediate next steps (for next agent)
1. **Move "ornaments" out of Groceries list**:
   ```bash
   cd /Users/pacey/Documents/SourceCode/grocery-automation && \
   source .venv/bin/activate && source .envrc && \
   python -m grocery.run --list-name "Groceries" \
     --move-item "ornaments" \
     --move-to-list "To Purchase for Condo"
   ```

2. **Re-run dry-run to find next unmapped item**:
   ```bash
   python -m grocery.run --list-name "Groceries" --dry-run
   ```

3. **Repeat mapping loop** until dry-run prints: `All items mapped.`
   - For each unmapped grocery item:
     - Open Hy‑Vee search URL printed in error
     - Find product page URL
     - Add to `data/products.json` with product_id from URL
   - For each non-grocery item:
     - Use `--move-item` to move to Condo list

4. **Once all mapped, run the full cart orchestration**:
   ```bash
   python -m grocery.run --list-name "Groceries"
   ```
   - This will log into Hy‑Vee (headful browser by default)
   - Add all mapped items to cart (idempotent)
   - Stop before checkout (manual gate)

### Commands to commit this session's work
```bash
cd /Users/pacey/Documents/SourceCode/grocery-automation
git add -A
git commit -m "feat: Phase B cart orchestration + non-grocery routing

- Implement ensure_items_in_cart() with idempotency + unavailable logging
- Add --move-item CLI mode to route non-grocery tasks to Condo list
- Make project installable (pyproject.toml build-system + scripts)
- Wire Phase B into orchestrator main() for non-dry-run path
- Add unit tests for cart tools + task moving (28 passing)
- Map 2 items: frozen shrimp cocktail, short carrots
- Update STATUS.md with session handoff for next agent"
```

### Files changed this session
- `src/grocery/tools/hyvee.py` (added `ensure_items_in_cart()`)
- `src/grocery/tools/gtasks.py` (added `move_open_tasks_by_title()`)
- `src/grocery/tools/errors.py` (added `hyvee_no_search_results()`, `non_grocery_item()`)
- `src/grocery/run.py` (added `--move-item` mode + Phase B wiring)
- `tests/test_hyvee_cart_tools.py` (added idempotency + unavailable tests)
- `tests/test_gtasks_complete.py` (added task moving tests)
- `tests/test_orchestrator_non_dry_run.py` (created)
- `pyproject.toml` (added build-system + scripts)
- `data/products.json` (added 2 product mappings)
- `STATUS.md` (this handoff section)

## 11) Last updated
- 2025-12-16 (Phase B complete, mid-mapping-loop)
