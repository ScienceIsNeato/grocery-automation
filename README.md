# Grocery Automation

This is a standalone grocery automation toolchain (Google Tasks → Hy-Vee cart).

## Design goals

- **Atomic tools**: each module function does one thing.
- **Idempotent**: safe to run repeatedly.
- **Exit on unknown**: unmapped items cause a deterministic stop with clear instructions.
- **Hard stop at checkout**: the program never clicks checkout; a human does.
- **TDD**: tests first for every tool and error scenario.

## Quick start (local)

1. Ensure you have OAuth credentials files in this directory (not committed):
   - `credentials.json`
   - `token.json` (auto-generated)

2. Configure env vars (recommended via `.envrc`, not committed):
   - `HYVEE_EMAIL`
   - `HYVEE_PASSWORD`

3. Run (once implemented):

```bash
# Run the full automation
python -m grocery.run --list-name "Groceries"

# Run in Dry-Run mode (verifies mappings only)
python -m grocery.run --list-name "Groceries" --dry-run
```

## Data files

- `data/products.json`: product library (mappings)
- `data/substitutions.json`: normalization/substitution rules
- `data/unavailable.json`: log of unavailable items (not_found/out_of_stock/etc)


