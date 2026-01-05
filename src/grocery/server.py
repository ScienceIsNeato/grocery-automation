"""Simple Flask server for fuzzy mapping UI backend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Get repo root for file serving
REPO_ROOT = Path(__file__).resolve().parents[2]

app = Flask(__name__, static_folder=str(REPO_ROOT), static_url_path='')
CORS(app)  # Allow cross-origin requests


@app.route("/apply-mappings", methods=["POST"])
def apply_mappings():
    """Apply fuzzy mapping decisions from UI."""
    data = request.get_json()
    
    repo_root = Path(data.get("repo_root", "."))
    list_name = data.get("list_name", "Groceries")
    substitutions = data.get("substitutions", [])
    task_renames = data.get("task_renames", [])
    new_items = data.get("new_items", [])
    
    results = {"success": True, "errors": []}
    
    try:
        # Add fuzzy matches directly to products.json original_requests (single source of truth)
        sys.path.insert(0, str(repo_root / "src"))
        from grocery.tools import library
        
        products_path = repo_root / "data" / "products.json"
        variations_added = 0
        
        for sub in substitutions:
            # sub["key"] = corrected name from UI (e.g., "shrimps" after editing "shrmps")
            # sub["value"] = product key it was matched to (e.g., "frozen shrimp cocktail")
            corrected_name = sub["key"].strip()
            matched_product_key = sub["value"].strip()
            
            # Add the corrected name to the matched product's original_requests array
            if library.add_variation_to_product(
                products_path,
                product_key=matched_product_key,
                variation=corrected_name,
            ):
                variations_added += 1
        
        results["variations_added"] = variations_added
        if variations_added > 0:
            results["message"] = f"Added {variations_added} variation(s) to products.json original_requests"
        
        # Regenerate fuzzy HTML (so refresh shows updated list)
        sys.path.insert(0, str(repo_root / "src"))
        from grocery.run import regenerate_fuzzy_html
        
        products_path = repo_root / "data" / "products.json"
        regenerated_html = regenerate_fuzzy_html(
            repo_root=repo_root,
            list_name=list_name,
            products_path=products_path,
        )
        results["html_regenerated"] = regenerated_html is not None
        if regenerated_html:
            results["remaining_unmapped"] = "See refreshed page for updated count"
        
        # Rename tasks in Google Tasks
        if task_renames:
            sys.path.insert(0, str(repo_root / "src"))
            from grocery.tools import gtasks
            
            service = gtasks._build_tasks_service(
                repo_root=repo_root,
                scopes=gtasks.DEFAULT_SCOPES_READWRITE
            )
            list_id = gtasks.find_task_list_id(service, "Groceries")
            
            if not list_id:
                results["errors"].append("Could not find 'Groceries' task list")
            else:
                api_results = service.tasks().list(tasklist=list_id, showCompleted=False).execute()
                tasks = api_results.get("items", [])
                
                renamed = 0
                for rename in task_renames:
                    for task in tasks:
                        if task.get("title", "").strip().lower() == rename["from"].lower():
                            task["title"] = rename["to"]
                            service.tasks().update(tasklist=list_id, task=task["id"], body=task).execute()
                            renamed += 1
                            break
                
                results["tasks_renamed"] = renamed
        
        # Write new items for next phase
        if new_items:
            new_items_file = repo_root / "data" / "new_items.json"
            with open(new_items_file, "w", encoding="utf-8") as f:
                json.dump({"items": new_items}, f, indent=2)
            results["new_items_written"] = len(new_items)
        
    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
    
    return jsonify(results)


@app.route("/proceed-to-hyvee-search", methods=["POST"])
def proceed_to_hyvee_search():
    """Regenerate HTML for Hy-Vee search phase (skip fuzzy matching)."""
    data = request.get_json()
    repo_root = Path(data.get("repo_root", "."))
    list_name = data.get("list_name", "Groceries")
    
    results = {"success": True, "errors": []}
    
    try:
        sys.path.insert(0, str(repo_root / "src"))
        from grocery.tools import gtasks, library
        from grocery import run
        
        # Re-run orchestrator logic but skip fuzzy phase
        products_path = repo_root / "data" / "products.json"
        raw_titles = gtasks.fetch_open_task_titles(repo_root=repo_root, list_name=list_name)
        normalized = gtasks.normalize(items=raw_titles)
        normalized_names = [x["normalized"] for x in normalized]
        
        _, unmapped_names = library.verify_all_mapped(products_path, normalized_names)
        
        if unmapped_names:
            # Build unmapped items for Hy-Vee search UI
            # Deduplicate by normalized name, combining quantities
            unmapped_dict = {}
            for norm in normalized:
                if norm["normalized"] in unmapped_names:
                    key = norm["normalized"]
                    if key in unmapped_dict:
                        # Combine quantities and keep the first original name
                        unmapped_dict[key]["quantity"] += norm["quantity"]
                    else:
                        unmapped_dict[key] = {
                            "original": norm["original"],
                            "normalized": norm["normalized"],
                            "quantity": norm["quantity"],
                        }
            unmapped_items = list(unmapped_dict.values())
            
            # Generate Hy-Vee search HTML
            hyvee_html = run._generate_unmapped_html(unmapped_items, repo_root, list_name=list_name)
            results["hyvee_html"] = str(hyvee_html)
            results["unmapped_count"] = len(unmapped_items)
        else:
            results["unmapped_count"] = 0
            results["message"] = "All items are mapped! No Hy-Vee search needed."
    
    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
    
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8766, debug=False)

