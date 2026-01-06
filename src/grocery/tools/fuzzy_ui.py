"""HTML UI generator for fuzzy matching workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from grocery.tools import library


def generate_fuzzy_match_html(
    unmapped_items: list[dict],
    products_path: Path,
    repo_root: Path,
    list_name: str = "Groceries",
) -> Path:
    """
    Generate interactive HTML for fuzzy matching unmapped items to existing products.
    
    Args:
        unmapped_items: List of dicts with keys: original, normalized, quantity
        products_path: Path to products.json
        repo_root: Repo root directory
    
    Returns path to generated HTML file.
    """
    from datetime import datetime
    
    output_dir = repo_root / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "fuzzy_match_items.html"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Load all existing products for the full alphabetized list
    data = library.load_products(products_path)
    products = data.get("products", {})
    all_product_keys = sorted(products.keys())
    
    # Build rows with fuzzy matches
    rows = []
    for i, item_obj in enumerate(unmapped_items):
        item = item_obj["original"]  # Display the original task title
        normalized = item_obj["normalized"]
        quantity = item_obj.get("quantity", 1)
        
        fuzzy_matches = library.fuzzy_match_products(products_path, normalized, n=3, cutoff=0.5)
        
        # Escape for HTML/JS
        safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        js_item = item.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        js_normalized = normalized.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        
        # Build fuzzy match buttons
        match_buttons = []
        for match_key, score in fuzzy_matches:
            product_info = products.get(match_key, {})
            display_name = product_info.get("display_name", match_key)
            safe_display = display_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # For onclick, escape quotes for HTML attribute
            js_match = match_key.replace("&", "&amp;").replace('"', "&quot;").replace("'", "&#39;")
            pct = int(score * 100)
            match_buttons.append(
                f'<button class="match-btn" onclick="selectMatch(this, \'{match_key}\')" '
                f'data-match="{js_match}" title="{safe_display}">'
                f'<span class="match-score">{pct}%</span> <span class="match-name">{safe_display}</span>'
                f'</button>'
            )
        
        # If fewer than 3 matches, fill with empty placeholders
        while len(match_buttons) < 3:
            match_buttons.append('<button class="match-btn empty" disabled>—</button>')
        
        rows.append(f'''
        <tr data-item="{js_normalized}" data-original="{js_item}" data-normalized="{js_normalized}" data-status="pending" data-quantity="{quantity}">
            <td class="row-num">{i+1}</td>
            <td class="item-name"><span class="editable-item" contenteditable="true" spellcheck="false" onblur="trackEdit(this)">{safe_item}</span></td>
            <td class="qty-cell"><input type="number" class="qty-input" value="{quantity}" min="1" max="99" onchange="updateQuantity(this)" /></td>
            <td class="matches-cell">
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    {match_buttons[0]}
                    {match_buttons[1]}
                    {match_buttons[2]}
                </div>
            </td>
            <td class="actions-cell">
                <button class="manual-btn" onclick="showManualSelect(this)">📋 Browse All</button>
                <button class="new-btn active" onclick="markAsNew(this)">✨ NEW</button>
            </td>
            <td class="selection-cell"></td>
            <td class="status-cell">🆕</td>
        </tr>''')
    
    # Build the full product list as JSON for JS
    product_list_json = "[\n"
    for key in all_product_keys:
        product_info = products.get(key, {})
        display_name = product_info.get("display_name", key)
        safe_key = key.replace('"', '\\"')
        safe_display = display_name.replace('"', '\\"')
        product_list_json += f'    {{ "key": "{safe_key}", "display": "{safe_display}" }},\n'
    product_list_json += "  ]"
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fuzzy Matching Tool</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1600px;
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
            background: #8250df;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            cursor: default;
        }}
        .phase-nav {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .phase-btn {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }}
        .phase-btn.active {{
            background: #8250df;
            color: white;
        }}
        .phase-btn.inactive {{
            background: #21262d;
            color: #8b949e;
            border: 1px solid #30363d;
        }}
        .phase-btn.inactive:hover {{
            background: #30363d;
            color: #c9d1d9;
        }}
        .phase-btn.loading {{
            opacity: 0.6;
            cursor: wait;
        }}
        .phase-btn.loading {{
            opacity: 0.6;
            cursor: wait;
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
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid #21262d;
            vertical-align: top;
        }}
        th {{
            background: #21262d;
            color: #8b949e;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
        }}
        tr:hover {{ background: #1c2128; }}
        tr.mapped {{ background: #0d2818; }}
        tr.new {{ background: #1e1a2d; }}
        tr.processed {{ 
            opacity: 0; 
            transition: opacity 0.3s ease-out;
        }}
        tr.processed.hidden {{ display: none; }}
        .row-num {{ color: #8b949e; width: 50px; text-align: center; font-size: 13px; font-weight: 600; }}
        .item-name {{ font-weight: 500; width: 280px; word-break: break-word; font-size: 14px; }}
        .editable-item {{
            padding: 4px 6px;
            border-radius: 3px;
            border: 1px solid transparent;
            display: inline-block;
            min-width: 100px;
        }}
        .editable-item:hover {{ border-color: #30363d; background: #0d1117; }}
        .editable-item:focus {{ 
            border-color: #58a6ff; 
            background: #0d1117; 
            outline: none; 
        }}
        .editable-item.edited {{ 
            border-color: #d29922; 
            background: #2d1b0e;
        }}
        .qty-cell {{ width: 90px; }}
        .qty-input {{
            width: 60px;
            padding: 8px 6px;
            border: 1px solid #30363d;
            border-radius: 4px;
            font-size: 12px;
            background: #0d1117;
            color: #c9d1d9;
            text-align: center;
        }}
        .qty-input:focus {{ border-color: #58a6ff; outline: none; }}
        .matches-cell {{ 
            display: flex; 
            flex-direction: column;
            gap: 8px; 
            min-width: 400px;
            max-width: 600px;
        }}
        .match-btn {{
            padding: 10px 12px;
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            text-align: left;
            width: 100%;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .match-btn:hover {{ 
            background: #30363d; 
            border-color: #58a6ff;
            transform: translateX(2px);
        }}
        .match-btn.active {{ 
            background: #238636; 
            border-color: #2ea043;
            box-shadow: 0 0 0 2px rgba(35, 134, 54, 0.3);
        }}
        .match-btn.empty {{ opacity: 0.3; cursor: not-allowed; }}
        .match-score {{
            font-weight: 600;
            color: #58a6ff;
            min-width: 45px;
            flex-shrink: 0;
        }}
        .match-btn.active .match-score {{
            color: #7ee787;
        }}
        .match-name {{
            flex: 1;
            word-break: break-word;
            line-height: 1.4;
        }}
        .actions-cell {{ 
            display: flex; 
            gap: 6px;
            width: 220px;
        }}
        .manual-btn, .new-btn {{
            padding: 6px 10px;
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            white-space: nowrap;
        }}
        .manual-btn:hover {{ background: #30363d; border-color: #d29922; }}
        .new-btn:hover {{ background: #30363d; border-color: #8250df; }}
        .new-btn.active {{ background: #8250df; border-color: #a371f7; }}
        .selection-cell {{ width: 250px; font-size: 12px; color: #7ee787; }}
        .status-cell {{ width: 30px; font-size: 16px; text-align: center; }}
        .action-bar {{
            margin-top: 15px;
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .generate-btn {{
            padding: 10px 20px;
            background: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
        }}
        .generate-btn:hover {{ background: #2ea043; }}
        .reset-btn:hover {{ background: #21262d; }}
        .output-section {{
            margin-top: 20px;
            padding: 15px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            display: none;
        }}
        .output-section.visible {{ display: block; }}
        .output-section h3 {{ color: #238636; margin-bottom: 10px; font-size: 18px; }}
        .output-section p {{ margin: 8px 0; line-height: 1.6; }}
        .search-hyvee-btn {{
            background: #8250df;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            margin-top: 15px;
        }}
        .search-hyvee-btn:hover {{ background: #6e40c9; }}
        .json-output {{
            width: 100%;
            height: 150px;
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
        .new-items-section {{
            margin-top: 15px;
            padding: 15px;
            background: #161b22;
            border-radius: 6px;
        }}
        .new-items-section h4 {{ margin: 0 0 10px 0; color: #8250df; }}
        .new-items-list {{ color: #7ee787; font-family: 'SF Mono', Monaco, monospace; font-size: 12px; }}
        
        /* Modal for manual selection */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
        }}
        .modal.visible {{ display: flex; align-items: center; justify-content: center; }}
        .modal-content {{
            background: #161b22;
            padding: 20px;
            border-radius: 8px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }}
        .modal-header {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            margin-bottom: 15px;
        }}
        .modal-header h2 {{ margin: 0; color: #58a6ff; font-size: 18px; }}
        .modal-close {{
            background: #da3633;
            border: none;
            color: white;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
        }}
        .modal-close:hover {{ background: #f85149; }}
        .search-box {{
            width: 100%;
            padding: 10px;
            margin-bottom: 15px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            font-size: 14px;
        }}
        .search-box:focus {{ border-color: #58a6ff; outline: none; }}
        .product-list {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .product-item {{
            padding: 10px;
            margin-bottom: 6px;
            background: #21262d;
            border-radius: 4px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .product-item:hover {{ background: #30363d; }}
        .product-item.hidden {{ display: none; }}
        .product-key {{ font-family: 'SF Mono', Monaco, monospace; color: #7ee787; }}
        .product-display {{ color: #8b949e; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Fuzzy Match Existing Products</h1>
        <div class="phase-nav">
            <button class="phase-btn active" onclick="return false;">
                🧠 Phase 1: Match Existing
            </button>
            <button class="phase-btn inactive" onclick="navigateToPhase2()" id="phase2-btn">
                🔍 Phase 2: Hy-Vee Search
            </button>
            <button class="phase-btn inactive" onclick="navigateToPhase3()" id="phase3-btn">
                🛒 Phase 3: Add to Cart
            </button>
        </div>
    </div>
    
    <div class="stats">
        <span class="stat">Remaining: <strong>{len(unmapped_items)} / {len(unmapped_items)}</strong></span>
        <span class="stat">Mapped: <strong id="matched-count">0</strong></span>
        <span class="stat">New: <strong id="new-count">0</strong></span>
    </div>
    
    <p style="color: #8b949e; font-size: 13px; margin-bottom: 15px;">
        Before searching Hy-Vee, let's check if these items already exist in your product library with slightly different names.
        Select a fuzzy match, browse the full list, or mark as NEW to search Hy-Vee.
    </p>
    
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Item from Google Tasks</th>
                <th>Qty</th>
                <th>Top 3 Fuzzy Matches (click to select)</th>
                <th>Actions</th>
                <th>Selection</th>
                <th></th>
            </tr>
        </thead>
        <tbody id="items-body">
            {"".join(rows)}
        </tbody>
    </table>
    
    <div class="action-bar">
        <button class="generate-btn" onclick="updateListDetails()">✨ Update List Details</button>
        <button class="reset-btn" onclick="resetAllSelections()" style="background: #30363d; color: #c9d1d9; border: 1px solid #30363d; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; margin-left: 10px;">↺ Reset All</button>
        <span style="color: #8b949e; font-size: 12px; margin-left: 10px;">
            (Adds variations to products.json, renames tasks, refreshes page)
        </span>
    </div>
    
    <div class="output-section" id="output-section">
        <h3 id="output-title">⏳ Processing...</h3>
        <div id="output-content"></div>
    </div>
    
    <!-- Manual selection modal -->
    <div id="modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Browse All Products</h2>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <input type="text" class="search-box" id="modal-search" placeholder="Type to filter..." onkeyup="filterProducts()">
            <div class="product-list" id="product-list">
                {_generate_product_list_html(all_product_keys, products)}
            </div>
        </div>
    </div>
    
    <script>
        let currentRow = null;
        const allProducts = {product_list_json};
        const repoRoot = '{str(repo_root)}';
        const listName = '{list_name}';
        
        function trackEdit(element) {{
            const row = element.closest('tr');
            const newText = element.textContent.trim();
            const original = row.dataset.original;
            
            if (newText !== original && newText.length > 0) {{
                row.dataset.item = newText;
                row.dataset.edited = 'true';
                element.classList.add('edited');
            }} else {{
                row.dataset.item = row.dataset.normalized;
                row.dataset.edited = 'false';
                element.classList.remove('edited');
            }}
        }}
        
        function updateQuantity(input) {{
            const row = input.closest('tr');
            row.dataset.quantity = input.value;
        }}
        
        function selectMatch(btn, matchKey) {{
            const row = btn.closest('tr');
            
            // Clear other match buttons in this row
            row.querySelectorAll('.match-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Clear NEW button
            row.querySelector('.new-btn').classList.remove('active');
            
            // Update row state
            row.dataset.status = 'mapped';
            row.dataset.matchedTo = matchKey;
            row.classList.add('mapped');
            row.classList.remove('new');
            
            // Update selection display
            const product = allProducts.find(p => p.key === matchKey);
            const display = product ? product.display : matchKey;
            row.querySelector('.selection-cell').textContent = `→ ${{display}}`;
            row.querySelector('.status-cell').textContent = '✅';
            
            updateCounts();
        }}
        
        function markAsNew(btn) {{
            const row = btn.closest('tr');
            
            // Clear all match buttons
            row.querySelectorAll('.match-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Update row state
            row.dataset.status = 'new';
            row.dataset.matchedTo = '';
            row.classList.remove('mapped');
            row.classList.add('new');
            
            row.querySelector('.selection-cell').textContent = '';
            row.querySelector('.status-cell').textContent = '🆕';
            
            updateCounts();
        }}
        
        function fadeOutRow(row) {{
            row.classList.add('processed');
            setTimeout(() => {{
                row.classList.add('hidden');
            }}, 300);
        }}
        
        function showManualSelect(btn) {{
            currentRow = btn.closest('tr');
            document.getElementById('modal').classList.add('visible');
            document.getElementById('modal-search').value = '';
            document.getElementById('modal-search').focus();
            filterProducts();
        }}
        
        function closeModal() {{
            document.getElementById('modal').classList.remove('visible');
            currentRow = null;
        }}
        
        function filterProducts() {{
            const query = document.getElementById('modal-search').value.toLowerCase();
            const items = document.querySelectorAll('.product-item');
            items.forEach(item => {{
                const text = item.textContent.toLowerCase();
                item.classList.toggle('hidden', !text.includes(query));
            }});
        }}
        
        function selectProduct(key) {{
            if (!currentRow) return;
            
            // Clear other selections
            currentRow.querySelectorAll('.match-btn, .new-btn').forEach(b => b.classList.remove('active'));
            
            // Update row state
            currentRow.dataset.status = 'mapped';
            currentRow.dataset.matchedTo = key;
            currentRow.classList.add('mapped');
            currentRow.classList.remove('new');
            
            // Update display
            const product = allProducts.find(p => p.key === key);
            const display = product ? product.display : key;
            currentRow.querySelector('.selection-cell').textContent = `→ ${{display}}`;
            currentRow.querySelector('.status-cell').textContent = '✅';
            
            updateCounts();
            closeModal();
        }}
        
        function updateCounts() {{
            const all = document.querySelectorAll('#items-body tr').length;
            const processed = document.querySelectorAll('tr.processed').length;
            const remaining = all - processed;
            const mapped = document.querySelectorAll('tr[data-status="mapped"]').length;
            const newItems = document.querySelectorAll('tr[data-status="new"]').length;
            
            document.getElementById('matched-count').textContent = mapped;
            document.getElementById('new-count').textContent = newItems;
            
            // Update header stat to show remaining
            const remainingStat = document.querySelector('.stats .stat strong');
            if (remainingStat) {{
                remainingStat.textContent = `${{remaining}} / ${{all}}`;
            }}
        }}
        
        async function updateListDetails() {{
            const btn = document.querySelector('.generate-btn');
            btn.disabled = true;
            btn.textContent = '⏳ Processing...';
            
            const rows = document.querySelectorAll('#items-body tr');
            const substitutions = [];
            const taskRenames = [];
            const newItems = [];
            
            rows.forEach(row => {{
                const originalName = row.dataset.original;
                const currentName = row.dataset.item;
                const quantity = parseInt(row.dataset.quantity) || 1;
                const status = row.dataset.status;
                const matchedTo = row.dataset.matchedTo;
                const wasEdited = row.dataset.edited === 'true';
                
                // Track task renames (edited items)
                if (wasEdited && currentName !== originalName) {{
                    taskRenames.push({{
                        from: originalName,
                        to: currentName
                    }});
                }}
                
                // Track substitutions (mapped items using current name)
                if (status === 'mapped' && matchedTo) {{
                    substitutions.push({{
                        key: currentName,
                        value: matchedTo,
                        quantity: quantity
                    }});
                }} else if (status === 'new') {{
                    newItems.push({{
                        name: currentName,
                        quantity: quantity
                    }});
                }}
            }});
            
            // POST to backend server
            try {{
                const response = await fetch('http://127.0.0.1:8766/apply-mappings', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        repo_root: repoRoot,
                        list_name: listName,
                        substitutions: substitutions,
                        task_renames: taskRenames,
                        new_items: newItems
                    }})
                }});
                
                if (!response.ok) {{
                    throw new Error(`Server returned ${{response.status}}`);
                }}
                
                const result = await response.json();
                
                // Show success with detailed info
                document.getElementById('output-section').classList.add('visible');
                document.getElementById('output-title').textContent = '✅ Changes Applied Successfully!';
                
                const variationsAdded = result.variations_added || substitutions.length;
                const tasksRenamed = result.tasks_renamed || 0;
                const newItemsCount = newItems.length;
                
                const newItemsDisplay = newItems.map(ni => `• ${{ni.name}} (qty: ${{ni.quantity}})`).join('<br>');
                
                let successHtml = `
                    <div style="color: #7ee787; margin-bottom: 15px;">
                        <p style="font-size: 15px; font-weight: 600; margin-bottom: 10px;">Summary:</p>
                        <p>✓ Added <strong>${{variationsAdded}}</strong> variation(s) to products.json original_requests</p>
                        <p>✓ Renamed <strong>${{tasksRenamed}}</strong> task(s) in Google Tasks</p>
                        <p>✓ Saved <strong>${{newItemsCount}}</strong> NEW item(s) for Hy-Vee search</p>
                    </div>
                `;
                
                if (newItemsCount > 0) {{
                    successHtml += `
                        <div style="margin-top: 20px; padding: 15px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px;">
                            <h4 style="color: #8250df; margin: 0 0 12px 0; font-size: 16px;">✨ Items to search on Hy-Vee:</h4>
                            <div style="color: #7ee787; font-size: 14px; margin-bottom: 15px;">
                                ${{newItemsDisplay}}
                            </div>
                            <button class="search-hyvee-btn" onclick="proceedToHyveeSearch()">
                                🔍 Search Hy-Vee for NEW Items
                            </button>
                        </div>
                    `;
                }}
                
                successHtml += `
                    <p style="color: #8b949e; font-size: 13px; margin-top: 20px;">
                        Page will refresh automatically in 7 seconds to show updated list...
                        <button onclick="window.location.reload();" style="background: transparent; border: 1px solid #30363d; color: #58a6ff; padding: 4px 8px; border-radius: 4px; cursor: pointer; margin-left: 10px; font-size: 12px;">Refresh Now</button>
                    </p>
                `;
                
                document.getElementById('output-content').innerHTML = successHtml;
                
                // Fade out all adjudicated rows
                rows.forEach(row => {{
                    const status = row.dataset.status;
                    if (status === 'mapped' || status === 'new') {{
                        fadeOutRow(row);
                    }}
                }});
                
                // Auto-refresh page to show updated list (HTML was regenerated on server)
                // Increased timeout so user can read the success message
                setTimeout(() => {{
                    window.location.reload();
                }}, 7000);
                
            }} catch (error) {{
                document.getElementById('output-section').classList.add('visible');
                document.getElementById('output-title').textContent = '❌ Error';
                document.getElementById('output-content').innerHTML = `
                    <p style="color: #f85149;">
                        Failed to apply changes: ${{error.message}}
                    </p>
                    <p style="color: #8b949e; font-size: 12px; margin-top: 10px;">
                        Make sure the Flask server is running (port 8766)
                    </p>
                `;
            }} finally {{
                btn.disabled = false;
                btn.textContent = '✨ Update List Details';
            }}
        }}
        
        // Navigate to Phase 2 (Hy-Vee search)
        async function navigateToPhase2() {{
            const btn = document.getElementById('phase2-btn');
            if (btn.classList.contains('loading')) return;
            
            btn.classList.add('loading');
            btn.textContent = '⏳ Loading...';
            
            try {{
                const response = await fetch('http://127.0.0.1:8766/proceed-to-hyvee-search', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        repo_root: repoRoot,
                        list_name: listName
                    }})
                }});
                
                const result = await response.json();
                
                if (result.success && result.hyvee_html) {{
                    // Redirect to Hy-Vee search page
                    window.location.href = `http://127.0.0.1:8766/data/unmapped_items.html`;
                }} else {{
                    btn.classList.remove('loading');
                    btn.textContent = '🔍 Phase 2: Hy-Vee Search';
                    alert(result.message || 'No unmapped items found. All items are mapped!');
                }}
            }} catch (error) {{
                btn.classList.remove('loading');
                btn.textContent = '🔍 Phase 2: Hy-Vee Search';
                alert('Failed to proceed to Hy-Vee search: ' + error.message);
            }}
        }}
        
        // Proceed to Hy-Vee search phase (kept for backward compatibility)
        async function proceedToHyveeSearch() {{
            return navigateToPhase2();
        }}
        
        // Navigate to Phase 3 (Add to Cart)
        async function navigateToPhase3() {{
            const btn = document.getElementById('phase3-btn');
            btn.classList.add('loading');
            btn.textContent = '⏳ Loading...';
            
            // Redirect to the new dashboard
            const params = new URLSearchParams({{
                list_name: listName,
                repo_root: repoRoot
            }});
            window.location.href = 'http://127.0.0.1:8766/phase3?' + params.toString();
        }}
        
        // Reset all selections
        function resetAllSelections() {{
            if (!confirm('Reset all selections? This will clear all mappings and mark all items as pending.')) {{
                return;
            }}
            
            const rows = document.querySelectorAll('#items-body tr');
            rows.forEach(row => {{
                row.dataset.status = 'pending';
                row.dataset.matchedTo = '';
                
                // Remove selection badge
                const badge = row.querySelector('.selection-badge');
                if (badge) badge.remove();
                
                // Reset row styling
                row.style.opacity = '1';
                row.style.backgroundColor = '';
                
                // Clear any selection indicators
                const selectionCell = row.querySelector('.selection-cell');
                if (selectionCell) {{
                    selectionCell.innerHTML = '';
                }}
            }});
            
            updateCounts();
            
            // Hide output section if visible
            document.getElementById('output-section').classList.remove('visible');
        }}
        
        // Close modal on escape key
        document.addEventListener('keydown', e => {{
            if (e.key === 'Escape') closeModal();
        }});
        
        // Initial count
        updateCounts();
    </script>
</body>
</html>'''
    
    output_file.write_text(html, encoding="utf-8")
    return output_file


def _generate_product_list_html(keys: list[str], products: dict[str, Any]) -> str:
    """Generate HTML for the full alphabetized product list."""
    items = []
    for key in keys:
        product_info = products.get(key, {})
        display_name = product_info.get("display_name", key)
        safe_key = key.replace('"', '&quot;').replace("&", "&amp;")
        safe_display = display_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        items.append(
            f'<div class="product-item" onclick="selectProduct(\'{key}\')">'
            f'<span class="product-display">{safe_display}</span>'
            f'<span class="product-key">{safe_key}</span>'
            f'</div>'
        )
    
    return "\n".join(items)

