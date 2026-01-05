"""
Orchestrator entry point (single command interface).

Implementation will be built tool-by-tool via TDD.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from grocery.tools import gtasks, library, fuzzy_ui
from grocery.tools.errors import GroceryError, hyvee_setup_required
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
        "--remove-item",
        action="append",
        default=[],
        help='Mark a task complete/remove it from --list-name (repeatable). Example: --remove-item "jello pudding"',
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
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--skip-fuzzy",
        action="store_true",
        help="Skip fuzzy matching phase and go straight to Hy-Vee product search for unmapped items",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    products_path = Path(args.products)
    substitutions_path = Path(args.substitutions)
    unavailable_path = Path(args.unavailable)

    try:
        # Handle --remove-item first (mark tasks complete)
        if args.remove_item:
            removed = gtasks.mark_tasks_complete_by_title(
                repo_root=repo_root,
                list_name=args.list_name,
                titles=list(args.remove_item),
            )
            print(f"Removed {removed} task(s) from list: {args.list_name}")
            return 0

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

        _, unmapped_names = library.verify_all_mapped(products_path, normalized_names)
        if unmapped_names:
            # Build rich unmapped items (with quantities from normalize())
            unmapped_items = []
            for norm in normalized:
                if norm["normalized"] in unmapped_names:
                    unmapped_items.append({
                        "original": norm["original"],
                        "normalized": norm["normalized"],
                        "quantity": norm["quantity"],
                    })
            
            if not args.skip_fuzzy:
                # Phase 1: Fuzzy match against existing products (avoids unnecessary Hy-Vee searches)
                fuzzy_html = fuzzy_ui.generate_fuzzy_match_html(unmapped_items, products_path, repo_root)
                
                print(f"\n{'='*60}")
                print(f"STEP 1: FUZZY MATCH EXISTING PRODUCTS")
                print(f"{'='*60}")
                print(f"Found {len(unmapped_items)} unmapped item(s).")
                print(f"\nBefore searching Hy-Vee, let's check if these are just")
                print(f"different phrasings of products you've already mapped.")
                print(f"\n{'='*60}")
                # Use Flask server (port 8766) for both static files and API
                http_url = f"http://127.0.0.1:8766/data/fuzzy_match_items.html"
                
                print(f"📋 Fuzzy match UI: {fuzzy_html}")
                print(f"   Open in browser: {http_url}")
                print(f"{'='*60}")
                print(f"\nINSTRUCTIONS:")
                print(f"  1. Edit item names inline (click to fix voice-to-text errors)")
                print(f"  2. Review fuzzy matches (top 3 shown) and click to map")
                print(f"  3. Or browse full product list, or mark as 'NEW'")
                print(f"  4. Click 'Update List Details' button")
                print(f"  5. Download and run the generated script")
                print(f"\n  The script will:")
                print(f"    - Write substitutions to data/substitutions.json")
                print(f"    - Rename edited tasks in Google Tasks")
                print(f"    - Re-run orchestrator automatically")
                print(f"\n  Items marked 'NEW' will be shown in Hy-Vee search UI next.")
                print(f"  (Or re-run with --skip-fuzzy to go straight to Hy-Vee search)")
                print(f"{'='*60}\n")
                
                # Try to open in browser via HTTP (avoids file:// CORS issues)
                try:
                    subprocess.run(["open", http_url], check=False)
                except Exception:
                    pass  # Silently fail if 'open' isn't available
                
                return 1
            else:
                # Phase 2: Hy-Vee product search for truly new items
                unmapped_html = _generate_unmapped_html(unmapped_items, repo_root)
                
                print(f"\n{'='*60}")
                print(f"STEP 2: HY-VEE PRODUCT SEARCH")
                print(f"{'='*60}")
                print(f"Found {len(unmapped_items)} item(s) that need Hy-Vee product URLs.")
                print(f"\n{'='*60}")
                print(f"📋 Product search UI: {unmapped_html}")
                print(f"   Open in browser: file://{unmapped_html}")
                print(f"{'='*60}")
                print(f"\nINSTRUCTIONS:")
                print(f"  1. Click 🔍 to search Hy-Vee for each item")
                print(f"  2. Paste product page URLs")
                print(f"  3. Generate JSON and paste into:")
                print(f"     data/products.json (under 'products')")
                print(f"  4. Re-run this command")
                print(f"{'='*60}\n")
                
                # Try to open the HTML file automatically
                try:
                    subprocess.run(["open", str(unmapped_html)], check=False)
                except Exception:
                    pass  # Silently fail if 'open' isn't available
                
                return 1

        print(f"All {len(normalized_names)} items mapped. Proceeding to cart...")

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
        except Exception as e:
            # Dump debug info on any error
            _dump_debug_info(page, e)
            raise
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


def _generate_unmapped_html(unmapped: list[dict], repo_root: Path) -> Path:
    """Generate an HTML file with clickable search links for unmapped items.
    
    Args:
        unmapped: List of dicts with keys: original (or name), normalized, quantity
        repo_root: Repo root directory
    """
    from datetime import datetime
    
    output_dir = repo_root / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "unmapped_items.html"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rows = []
    for i, item_obj in enumerate(unmapped):
        item = item_obj.get("name") or item_obj.get("original") or item_obj.get("normalized")
        quantity = item_obj.get("quantity", 1)
        search_url = build_search_url(item)
        # Escape HTML special characters and quotes for JS
        safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        js_item = item.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        rows.append(f'''
        <tr data-item="{js_item}" data-status="pending">
            <td class="row-num">{i+1}</td>
            <td class="item-name">{safe_item}</td>
            <td><a href="{search_url}" target="_blank" class="search-link">🔍</a></td>
            <td class="url-cell"><input type="text" class="url-input" placeholder="Paste URL..." /></td>
            <td class="qty-cell"><input type="number" class="qty-input" value="{quantity}" min="1" max="99" /></td>
            <td class="preview-cell"><div class="preview"></div></td>
            <td class="actions">
                <button class="skip-btn" onclick="markSkip(this)" title="Skip this item">⏭️</button>
                <button class="dupe-btn" onclick="markDupe(this)" title="Duplicate item">🔁</button>
                <button class="amazon-btn" onclick="markAmazon(this)" title="Move to Amazon list">📦</button>
            </td>
            <td class="status-cell">⏳</td>
        </tr>''')
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Product Mapping Tool</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 15px;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 14px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        h1 {{ color: #58a6ff; margin: 0; font-size: 24px; }}
        .source-badge {{
            background: #238636;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
        }}
        .store-badge {{
            background: #da3633;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            margin-left: 8px;
        }}
        .stats {{
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            font-size: 13px;
        }}
        .stat {{ color: #8b949e; }}
        .stat strong {{ color: #58a6ff; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #161b22;
            border-radius: 6px;
            overflow: hidden;
            font-size: 13px;
        }}
        th, td {{
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid #21262d;
        }}
        th {{
            background: #21262d;
            color: #8b949e;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
        }}
        tr:hover {{ background: #1c2128; }}
        tr.skipped {{ opacity: 0.4; }}
        tr.skipped td {{ text-decoration: line-through; }}
        tr.mapped {{ background: #0d2818; }}
        tr.amazon {{ background: #2d1b0e; }}
        tr.dupe {{ background: #1e1232; }}
        .row-num {{ color: #484f58; width: 25px; }}
        .item-name {{ font-weight: 500; max-width: 180px; word-break: break-word; }}
        .search-link {{
            display: inline-block;
            padding: 4px 8px;
            background: #388bfd;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
        .search-link:hover {{ background: #58a6ff; }}
        .url-cell {{ width: 280px; }}
        .url-input {{
            width: 100%;
            padding: 6px 8px;
            border: 1px solid #30363d;
            border-radius: 4px;
            font-size: 12px;
            background: #0d1117;
            color: #c9d1d9;
        }}
        .url-input:focus {{ border-color: #58a6ff; outline: none; }}
        .url-input.filled {{ border-color: #238636; background: #0d2818; }}
        .qty-cell {{ width: 50px; }}
        .qty-input {{
            width: 50px;
            padding: 6px 4px;
            border: 1px solid #30363d;
            border-radius: 4px;
            font-size: 12px;
            background: #0d1117;
            color: #c9d1d9;
            text-align: center;
        }}
        .qty-input:focus {{ border-color: #58a6ff; outline: none; }}
        .preview-cell {{ width: 60px; }}
        .preview {{
            width: 50px;
            height: 50px;
            background: #21262d;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        .preview img {{
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }}
        .actions {{
            white-space: nowrap;
        }}
        .actions button {{
            padding: 4px 6px;
            margin: 0 2px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            background: #21262d;
        }}
        .actions button:hover {{ background: #30363d; }}
        .actions button.active {{ background: #388bfd; }}
        .status-cell {{ width: 30px; font-size: 16px; text-align: center; }}
        .action-bar {{
            margin-top: 15px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .submit-btn {{
            padding: 10px 20px;
            background: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
        }}
        .submit-btn:hover {{ background: #2ea043; }}
        .output-section {{
            margin-top: 15px;
            display: none;
        }}
        .output-section.visible {{ display: block; }}
        .output-section h3 {{ color: #238636; margin-bottom: 10px; font-size: 16px; }}
        .json-output {{
            width: 100%;
            height: 200px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 10px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 11px;
            color: #7ee787;
            resize: vertical;
        }}
        .copy-btn {{
            margin-top: 8px;
            padding: 8px 16px;
            background: #da3633;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }}
        .copy-btn:hover {{ background: #f85149; }}
        .amazon-output, .skip-output {{
            margin-top: 10px;
            padding: 10px;
            background: #161b22;
            border-radius: 6px;
            font-size: 12px;
        }}
        .amazon-output h4, .skip-output h4 {{ margin: 0 0 8px 0; color: #d29922; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛒 Product Mapping Tool</h1>
        <div>
            <span class="source-badge">📋 Google Tasks</span>
            <span class="store-badge">🏪 Hy-Vee</span>
        </div>
    </div>
    
    <div class="stats">
        <span class="stat">Total: <strong>{len(unmapped)}</strong></span>
        <span class="stat">Mapped: <strong id="mapped-count">0</strong></span>
        <span class="stat">Skipped: <strong id="skipped-count">0</strong></span>
        <span class="stat">Amazon: <strong id="amazon-count">0</strong></span>
        <span class="stat">Dupes: <strong id="dupe-count">0</strong></span>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Item</th>
                <th>🔍</th>
                <th>Product URL</th>
                <th>Qty</th>
                <th>Preview</th>
                <th>Actions</th>
                <th></th>
            </tr>
        </thead>
        <tbody id="items-body">
            {"".join(rows)}
        </tbody>
    </table>
    
    <div class="action-bar">
        <button class="submit-btn" onclick="generateJSON()">📦 Generate All JSON</button>
    </div>
    
    <div class="output-section" id="output-section">
        <h3>✅ Product Mappings (paste into products.json)</h3>
        <textarea class="json-output" id="json-output" readonly></textarea>
        <button class="copy-btn" onclick="copyJSON()">📋 Copy to Clipboard</button>
        
        <div class="amazon-output" id="amazon-output" style="display:none">
            <h4>📦 Items to move to Amazon list:</h4>
            <div id="amazon-list"></div>
        </div>
        
        <div class="dupe-output" id="dupe-output" style="display:none">
            <h4>🔁 Duplicate items (will be removed from Google Tasks):</h4>
            <div id="dupe-list"></div>
            <div style="margin-top:8px;">
                <code id="dupe-cmd" style="display:block;background:#0d1117;padding:8px;border-radius:4px;font-size:11px;overflow-x:auto;white-space:nowrap;"></code>
                <button class="copy-btn" onclick="copyDupeCmd()" style="margin-top:4px;">📋 Copy Remove Command</button>
            </div>
        </div>
        
        <div class="skip-output" id="skip-output" style="display:none">
            <h4>⏭️ Skipped items:</h4>
            <div id="skip-list"></div>
        </div>
    </div>
    
    <script>
        // Update preview when URL is pasted
        document.querySelectorAll('.url-input').forEach(input => {{
            input.addEventListener('input', function() {{
                const row = this.closest('tr');
                const preview = row.querySelector('.preview');
                const status = row.querySelector('.status-cell');
                const url = this.value.trim();
                
                if (url && url.includes('/p/')) {{
                    this.classList.add('filled');
                    row.dataset.status = 'mapped';
                    row.classList.add('mapped');
                    status.textContent = '✅';
                    
                    // Extract product ID and build image URL
                    const match = url.match(/\\/p\\/(\\d+)/);
                    if (match) {{
                        const pid = match[1];
                        // Hy-Vee CDN pattern
                        const imgUrl = `https://d2d8wwwkmhfcva.cloudfront.net/100x/d2lnr5mha7bycj.cloudfront.net/product-image/file/${{pid}}.png`;
                        preview.innerHTML = `<img src="${{imgUrl}}" onerror="this.style.display='none'" />`;
                    }}
                }} else {{
                    this.classList.remove('filled');
                    row.classList.remove('mapped');
                    row.dataset.status = 'pending';
                    status.textContent = '⏳';
                    preview.innerHTML = '';
                }}
                updateCounts();
            }});
        }});
        
        function markSkip(btn) {{
            const row = btn.closest('tr');
            toggleStatus(row, 'skipped', btn);
        }}
        
        function markDupe(btn) {{
            const row = btn.closest('tr');
            toggleStatus(row, 'dupe', btn);
        }}
        
        function markAmazon(btn) {{
            const row = btn.closest('tr');
            toggleStatus(row, 'amazon', btn);
        }}
        
        function toggleStatus(row, status, btn) {{
            const wasActive = row.dataset.status === status;
            
            // Clear all statuses
            row.classList.remove('skipped', 'dupe', 'amazon', 'mapped');
            row.querySelectorAll('.actions button').forEach(b => b.classList.remove('active'));
            
            if (wasActive) {{
                row.dataset.status = 'pending';
                row.querySelector('.status-cell').textContent = '⏳';
            }} else {{
                row.dataset.status = status;
                btn.classList.add('active');
                row.classList.add(status);
                const icons = {{ skipped: '⏭️', dupe: '🔁', amazon: '📦' }};
                row.querySelector('.status-cell').textContent = icons[status];
            }}
            updateCounts();
        }}
        
        function updateCounts() {{
            document.getElementById('mapped-count').textContent = document.querySelectorAll('tr[data-status="mapped"]').length;
            document.getElementById('skipped-count').textContent = document.querySelectorAll('tr[data-status="skipped"]').length;
            document.getElementById('amazon-count').textContent = document.querySelectorAll('tr[data-status="amazon"]').length;
            document.getElementById('dupe-count').textContent = document.querySelectorAll('tr[data-status="dupe"]').length;
        }}
        
        function generateJSON() {{
            const rows = document.querySelectorAll('#items-body tr');
            const mappings = [];
            const amazonItems = [];
            const dupeItems = [];
            const skipItems = [];
            const timestamp = new Date().toISOString();
            
            rows.forEach(row => {{
                const itemName = row.dataset.item;
                const status = row.dataset.status;
                const url = row.querySelector('.url-input').value.trim();
                const qty = parseInt(row.querySelector('.qty-input').value) || 1;
                
                if (status === 'amazon') {{
                    amazonItems.push(itemName);
                    return;
                }}
                if (status === 'dupe') {{
                    dupeItems.push(itemName);
                    return;
                }}
                if (status === 'skipped') {{
                    skipItems.push(itemName);
                    return;
                }}
                if (!url || !url.includes('/p/')) return;
                
                const match = url.match(/\\/p\\/(\\d+)/);
                const productId = match ? match[1] : "";
                
                const urlParts = url.split('/');
                let displayName = urlParts[urlParts.length - 1] || "";
                displayName = displayName.replace(/-/g, ' ').replace(/\\?.*$/, '').trim();
                displayName = displayName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
                
                const qtyField = qty > 1 ? `\\n      "quantity": ${{qty}},` : "";
                mappings.push(`    "${{itemName.toLowerCase()}}": {{
      "product_id": "${{productId}}",
      "url": "${{url.split('?')[0]}}",
      "display_name": "${{displayName}}",${{qtyField}}
      "original_requests": ["${{itemName}}"],
      "added": "${{timestamp}}"
    }}`);
            }});
            
            document.getElementById('json-output').value = mappings.join(',\\n') || '// No items mapped';
            document.getElementById('output-section').classList.add('visible');
            
            if (amazonItems.length > 0) {{
                document.getElementById('amazon-output').style.display = 'block';
                document.getElementById('amazon-list').textContent = amazonItems.join('\\n');
            }}
            if (dupeItems.length > 0) {{
                document.getElementById('dupe-output').style.display = 'block';
                document.getElementById('dupe-list').textContent = dupeItems.join('\\n');
                // Generate remove command
                const removeArgs = dupeItems.map(i => `--remove-item "${{i}}"`).join(' ');
                const cmd = `python -m grocery.run --list-name "Groceries" ${{removeArgs}}`;
                document.getElementById('dupe-cmd').textContent = cmd;
            }}
            if (skipItems.length > 0) {{
                document.getElementById('skip-output').style.display = 'block';
                document.getElementById('skip-list').textContent = skipItems.join('\\n');
            }}
            
            document.getElementById('output-section').scrollIntoView({{ behavior: 'smooth' }});
        }}
        
        function copyJSON() {{
            const textarea = document.getElementById('json-output');
            navigator.clipboard.writeText(textarea.value).then(() => {{
                const btn = document.querySelector('.copy-btn');
                btn.textContent = '✓ Copied!';
                setTimeout(() => btn.textContent = '📋 Copy to Clipboard', 2000);
            }});
        }}
        
        function copyDupeCmd() {{
            const cmd = document.getElementById('dupe-cmd').textContent;
            navigator.clipboard.writeText(cmd).then(() => {{
                event.target.textContent = '✓ Copied!';
                setTimeout(() => event.target.textContent = '📋 Copy Remove Command', 2000);
            }});
        }}
    </script>
</body>
</html>'''
    
    output_file.write_text(html, encoding="utf-8")
    return output_file
def _dump_debug_info(page: "Any", error: Exception) -> None:
    """Dump screenshot, HTML, and URL to /tmp/hyvee_debug/ for debugging."""
    import traceback
    from datetime import datetime
    
    debug_dir = Path("/tmp/hyvee_debug")
    debug_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n{'='*60}")
    print("ERROR - Dumping debug info to /tmp/hyvee_debug/")
    print(f"{'='*60}")
    
    # Dump error info
    error_file = debug_dir / f"error_{timestamp}.txt"
    with open(error_file, "w") as f:
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Error: {error}\n\n")
        f.write("Traceback:\n")
        f.write(traceback.format_exc())
    print(f"  Error: {error_file}")
    
    if page:
        try:
            # Dump URL
            url = page.url
            print(f"  URL: {url}")
            
            # Dump screenshot
            screenshot_file = debug_dir / f"screenshot_{timestamp}.png"
            page.screenshot(path=str(screenshot_file))
            print(f"  Screenshot: {screenshot_file}")
            
            # Dump HTML
            html_file = debug_dir / f"page_{timestamp}.html"
            html = page.content()
            with open(html_file, "w") as f:
                f.write(html)
            print(f"  HTML: {html_file}")
            
        except Exception as dump_err:
            print(f"  (Could not dump page info: {dump_err})")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    raise SystemExit(main())
