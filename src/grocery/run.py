"""
Orchestrator entry point (single command interface).

Implementation will be built tool-by-tool via TDD.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from grocery.tools import gtasks, library
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

        _, unmapped = library.verify_all_mapped(products_path, normalized_names)
        if unmapped:
            # Generate clickable HTML file for easy mapping workflow
            unmapped_html = _generate_unmapped_html(unmapped, repo_root)
            
            # Show all unmapped items and exit - user must map before proceeding
            print(f"\n{'='*60}")
            print(f"UNMAPPED ITEMS: {len(unmapped)} item(s) need mapping")
            print(f"{'='*60}\n")
            for i, item in enumerate(unmapped, 1):
                url = build_search_url(item)
                print(f"{i:2}. {item}")
                print(f"    Search: {url}\n")
            print(f"{'='*60}")
            print(f"📋 Clickable list saved to: {unmapped_html}")
            print(f"   Open in browser: file://{unmapped_html}")
            print(f"{'='*60}")
            print("Add product URLs to data/products.json, then re-run.")
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


def _generate_unmapped_html(unmapped: list[str], repo_root: Path) -> Path:
    """Generate an HTML file with clickable search links for unmapped items."""
    from datetime import datetime
    
    output_dir = repo_root / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "unmapped_items.html"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rows = []
    for i, item in enumerate(unmapped):
        search_url = build_search_url(item)
        # Escape HTML special characters and quotes for JS
        safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        js_item = item.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        rows.append(f'''
        <tr data-item="{js_item}">
            <td class="row-num">{i+1}</td>
            <td class="item-name">{safe_item}</td>
            <td><a href="{search_url}" target="_blank" class="search-link">🔍 Search</a></td>
            <td><input type="text" class="url-input" placeholder="Paste product URL..." /></td>
            <td class="status">⏳</td>
        </tr>''')
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unmapped Grocery Items</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }}
        h1 {{ color: #4CAF50; margin-bottom: 5px; }}
        .timestamp {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
        .instructions {{
            background: #16213e;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #4CAF50;
        }}
        .instructions ol {{ margin: 10px 0 0 0; padding-left: 20px; }}
        .instructions li {{ margin: 6px 0; color: #bbb; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #16213e;
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }}
        th {{
            background: #0f3460;
            color: #4CAF50;
            font-weight: 600;
            font-size: 13px;
        }}
        tr:hover {{ background: #1f2f50; }}
        .row-num {{ color: #666; width: 30px; }}
        .item-name {{ font-weight: 500; max-width: 250px; }}
        .search-link {{
            display: inline-block;
            padding: 5px 10px;
            background: #2196F3;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 13px;
        }}
        .search-link:hover {{ background: #1976D2; }}
        .url-input {{
            width: 100%;
            padding: 8px;
            border: 1px solid #3a3a5a;
            border-radius: 4px;
            font-size: 13px;
            background: #0a0a1a;
            color: #eee;
        }}
        .url-input:focus {{ border-color: #4CAF50; outline: none; }}
        .url-input.filled {{ border-color: #4CAF50; background: #0a2a1a; }}
        .status {{ width: 30px; font-size: 18px; }}
        .action-bar {{
            margin-top: 20px;
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .submit-btn {{
            padding: 12px 24px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
        }}
        .submit-btn:hover {{ background: #45a049; }}
        .submit-btn:disabled {{ background: #555; cursor: not-allowed; }}
        .count {{ color: #888; font-size: 14px; }}
        .output-section {{
            margin-top: 20px;
            display: none;
        }}
        .output-section.visible {{ display: block; }}
        .output-section h3 {{ color: #4CAF50; margin-bottom: 10px; }}
        .json-output {{
            width: 100%;
            height: 300px;
            background: #0a0a1a;
            border: 1px solid #3a3a5a;
            border-radius: 8px;
            padding: 12px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
            color: #9cdcfe;
            resize: vertical;
        }}
        .copy-all-btn {{
            margin-top: 10px;
            padding: 10px 20px;
            background: #FF9800;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }}
        .copy-all-btn:hover {{ background: #F57C00; }}
        .copy-all-btn.copied {{ background: #4CAF50; }}
    </style>
</head>
<body>
    <h1>🛒 Unmapped Items ({len(unmapped)})</h1>
    <p class="timestamp">Generated: {timestamp}</p>
    
    <div class="instructions">
        <strong>Workflow:</strong>
        <ol>
            <li>Click "🔍 Search" to find each product on Hy-Vee</li>
            <li>Copy the product page URL and paste it in the input field</li>
            <li>Repeat for all items (or skip items you don't want)</li>
            <li>Click <strong>"Generate JSON"</strong> to create all mappings at once</li>
            <li>Copy and paste the JSON into <code>data/products.json</code></li>
        </ol>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Item Name</th>
                <th>Search</th>
                <th>Product URL</th>
                <th></th>
            </tr>
        </thead>
        <tbody id="items-body">
            {"".join(rows)}
        </tbody>
    </table>
    
    <div class="action-bar">
        <button class="submit-btn" onclick="generateJSON()">📦 Generate JSON</button>
        <span class="count"><span id="filled-count">0</span> / {len(unmapped)} filled</span>
    </div>
    
    <div class="output-section" id="output-section">
        <h3>✅ Generated JSON (paste into products.json)</h3>
        <textarea class="json-output" id="json-output" readonly></textarea>
        <button class="copy-all-btn" onclick="copyAll()">📋 Copy to Clipboard</button>
    </div>
    
    <script>
        // Update count and status on input
        document.querySelectorAll('.url-input').forEach(input => {{
            input.addEventListener('input', function() {{
                const row = this.closest('tr');
                const status = row.querySelector('.status');
                if (this.value.trim()) {{
                    this.classList.add('filled');
                    status.textContent = '✅';
                }} else {{
                    this.classList.remove('filled');
                    status.textContent = '⏳';
                }}
                updateCount();
            }});
        }});
        
        function updateCount() {{
            const filled = document.querySelectorAll('.url-input.filled').length;
            document.getElementById('filled-count').textContent = filled;
        }}
        
        function generateJSON() {{
            const rows = document.querySelectorAll('#items-body tr');
            const mappings = [];
            const timestamp = new Date().toISOString();
            
            rows.forEach(row => {{
                const itemName = row.dataset.item;
                const url = row.querySelector('.url-input').value.trim();
                
                if (!url) return; // Skip empty
                
                // Extract product ID from URL
                const match = url.match(/\\/p\\/(\\d+)/);
                const productId = match ? match[1] : "";
                
                // Extract display name from URL
                const urlParts = url.split('/');
                let displayName = urlParts[urlParts.length - 1] || "";
                displayName = displayName.replace(/-/g, ' ').replace(/\\?.*$/, '').trim();
                // Title case
                displayName = displayName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
                
                const cleanUrl = url.split('?')[0];
                
                mappings.push(`    "${{itemName.toLowerCase()}}": {{
      "product_id": "${{productId}}",
      "url": "${{cleanUrl}}",
      "display_name": "${{displayName}}",
      "original_requests": ["${{itemName}}"],
      "added": "${{timestamp}}"
    }}`);
            }});
            
            if (mappings.length === 0) {{
                alert('Please fill in at least one product URL!');
                return;
            }}
            
            const json = mappings.join(',\\n');
            document.getElementById('json-output').value = json;
            document.getElementById('output-section').classList.add('visible');
            document.getElementById('output-section').scrollIntoView({{ behavior: 'smooth' }});
        }}
        
        function copyAll() {{
            const textarea = document.getElementById('json-output');
            textarea.select();
            navigator.clipboard.writeText(textarea.value).then(() => {{
                const btn = document.querySelector('.copy-all-btn');
                btn.textContent = '✓ Copied!';
                btn.classList.add('copied');
                setTimeout(() => {{
                    btn.textContent = '📋 Copy to Clipboard';
                    btn.classList.remove('copied');
                }}, 2000);
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
