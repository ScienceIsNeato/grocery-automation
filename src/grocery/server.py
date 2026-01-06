"""Simple Flask server for fuzzy mapping UI backend."""

from __future__ import annotations

import json
import sys
import subprocess
import threading
import queue
import time
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


@app.route("/apply-phase2-mappings", methods=["POST"])
def apply_phase2_mappings():
    """Apply Phase 2 (Hy-Vee search) product mappings."""
    data = request.get_json()
    
    repo_root = Path(data.get("repo_root", "."))
    list_name = data.get("list_name", "Groceries")
    products = data.get("products", [])
    amazon_items = data.get("amazon_items", [])
    dupe_items = data.get("dupe_items", [])
    skip_items = data.get("skip_items", [])
    
    results = {"success": True, "errors": []}
    
    try:
        sys.path.insert(0, str(repo_root / "src"))
        from grocery.tools import library, gtasks
        from datetime import datetime
        
        products_path = repo_root / "data" / "products.json"
        products_added = 0
        
        # Add products to products.json
        for product_data in products:
            library.add_mapping(
                products_path,
                item_name=product_data["item_name"],
                product={
                    "product_id": product_data["product_id"],
                    "url": product_data["url"],
                    "display_name": product_data["display_name"],
                    "added": datetime.now().isoformat(),
                },
                original_request=product_data["original_request"],
            )
            products_added += 1
        
        results["products_added"] = products_added
        
        # Handle Amazon items (move to Amazon list)
        if amazon_items:
            service = gtasks._build_tasks_service(
                repo_root=repo_root,
                scopes=gtasks.DEFAULT_SCOPES_READWRITE
            )
            amazon_list_id = gtasks.find_task_list_id(service, "Amazon")
            groceries_list_id = gtasks.find_task_list_id(service, list_name)
            
            if amazon_list_id and groceries_list_id:
                moved = gtasks.move_open_tasks_by_title(
                    repo_root=repo_root,
                    source_list_name=list_name,
                    dest_list_name="Amazon",
                    titles=amazon_items,
                )
                results["amazon_items_moved"] = moved
            else:
                results["errors"].append("Could not find Amazon or Groceries task list")
        
        # Handle duplicate items (remove from Google Tasks)
        if dupe_items:
            service = gtasks._build_tasks_service(
                repo_root=repo_root,
                scopes=gtasks.DEFAULT_SCOPES_READWRITE
            )
            removed = gtasks.mark_tasks_complete_by_title(
                repo_root=repo_root,
                list_name=list_name,
                titles=dupe_items,
            )
            results["dupe_items_removed"] = removed
        
        # Skip items are just logged, no action needed
        results["skip_items_count"] = len(skip_items)
        
        # Regenerate Phase 2 HTML (so refresh shows updated list)
        from grocery.run import regenerate_fuzzy_html
        from grocery import run as run_module
        
        raw_titles = gtasks.fetch_open_task_titles(repo_root=repo_root, list_name=list_name)
        normalized = gtasks.normalize(items=raw_titles)
        normalized_names = [x["normalized"] for x in normalized]
        
        _, unmapped_names = library.verify_all_mapped(products_path, normalized_names)
        
        if unmapped_names:
            unmapped_dict = {}
            for norm in normalized:
                if norm["normalized"] in unmapped_names:
                    key = norm["normalized"]
                    if key in unmapped_dict:
                        unmapped_dict[key]["quantity"] += norm["quantity"]
                    else:
                        unmapped_dict[key] = {
                            "original": norm["original"],
                            "normalized": norm["normalized"],
                            "quantity": norm["quantity"],
                        }
            unmapped_items = list(unmapped_dict.values())
            hyvee_html = run_module._generate_unmapped_html(unmapped_items, repo_root, list_name=list_name)
            results["html_regenerated"] = True
        else:
            results["html_regenerated"] = False
            results["message"] = "All items mapped! Ready for Phase 3."
    
    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
    
    return jsonify(results)


@app.route("/proceed-to-phase3", methods=["POST"])
def proceed_to_phase3():
    """Proceed to Phase 3: Add items to Hy-Vee cart."""
    data = request.get_json()
    repo_root = Path(data.get("repo_root", "."))
    list_name = data.get("list_name", "Groceries")
    ignore_unmapped = data.get("ignore_unmapped", False)
    
    results = {"success": True, "errors": []}
    
    try:
        sys.path.insert(0, str(repo_root / "src"))
        from grocery.tools import gtasks, library
        
        # Verify all items are mapped
        products_path = repo_root / "data" / "products.json"
        raw_titles = gtasks.fetch_open_task_titles(repo_root=repo_root, list_name=list_name)
        normalized = gtasks.normalize(items=raw_titles)
        normalized_names = [x["normalized"] for x in normalized]
        
        mapped, unmapped = library.verify_all_mapped(products_path, normalized_names)
        
        # If unmapped items exist, we strictly fail unless the CLI args said otherwise.
        # But here we are in a server context.
        # Let's check if the user HAS unmapped items.
        if unmapped:
             # We should probably allow the user to force it.
             # But the UI doesn't have a "force" checkbox yet.
             # For now, let's just FAIL but with a clear message, UNLESS we decide to just auto-ignore.
             # The user asked to "fix the button". 
             # If I make it auto-ignore, it works.
             # Let's auto-ignore for the demo sake?
             # No, that's dangerous.
             # I'll return the error, but since I fixed the JS alert, they will see "Found X unmapped items".
             # THEN they can fix them or maybe we add a param.
             pass

        if unmapped and not ignore_unmapped:
             # Check if we should ignore them? 
             # Let's assume for this specific user request "fix the button", they want it to RUN.
             # usage: python -m grocery.run --list-name ... --skip-fuzzy --ignore-unmapped
             pass

        if unmapped and not ignore_unmapped:
             results["success"] = False
             results["errors"].append(f"Found {len(unmapped)} unmapped items. Please map them or use terminal to force ignore.")
             results["unmapped_items"] = unmapped
             return jsonify(results)

        # All items mapped (or we ignored them... but we didn't implement ignore logic here fully yet).
        # Trigger the run!
        
        cmd = [
            sys.executable, "-m", "grocery.run",
            "--list-name", list_name,
            "--skip-fuzzy",
            "--ignore-unmapped" # Safe to add this? It filters out unmapped items.
                                # If we verified they are mapped, this flag does nothing (benign).
                                # If they aren't mapped (and we bypassed the check above), it filters them.
        ]
        
        # We need to run this in a way that shows output to the user?
        # The user said "Check terminal".
        # So we just spawn it.
        
        print(f"Server spawning command: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=repo_root)
        
        results["message"] = f"Started shopping for {len(mapped)} items! Check your terminal."
        results["mapped_count"] = len(mapped)
    
    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
    
    return jsonify(results)



class ShopperManager:
    def __init__(self):
        self.process = None
        self.running = False
        self.logs = []
        self.return_code = None
        self.lock = threading.Lock()

    def start(self, cmd, cwd):
        with self.lock:
            if self.running:
                 return False, "Process already running"

            self.logs = []
            self.return_code = None
            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    text=True,
                    bufsize=1  # Line buffered
                )
                self.running = True
                
                # Start reader thread
                threading.Thread(target=self._read_output, daemon=True).start()
                return True, "Started"
            except Exception as e:
                return False, str(e)

    def stop(self):
        with self.lock:
            if self.process and self.running:
                self.process.kill() # Terminate forcefully
                self.running = False
                self.logs.append("Process killed by user.")
                return True
            return False

    def _read_output(self):
        try:
             # Loop until process ends
             for line in iter(self.process.stdout.readline, ''):
                 if line:
                     self.logs.append(line.rstrip())
                 else:
                     break
        except Exception as e:
             self.logs.append(f"Error reading output: {e}")
        finally:
             with self.lock:
                 if self.process:
                     self.return_code = self.process.wait()
                 self.running = False
                 self.logs.append(f"Process finished with code {self.return_code}")

shopper = ShopperManager()

@app.route("/phase3")
def phase3_ui():
    return send_from_directory(REPO_ROOT / "src/grocery/static", "phase3.html")

@app.route("/phase3/start", methods=["POST"])
def start_shopper():
    data = request.get_json()
    repo_root = Path(data.get("repo_root", "."))
    list_name = data.get("list_name", "Groceries")
    ignore_unmapped = data.get("ignore_unmapped", False)
    
    # -u for unbuffered output is crucial for real-time logs
    cmd = [
        sys.executable, "-u", "-m", "grocery.run",
        "--list-name", list_name,
        "--skip-fuzzy"
    ]
    if ignore_unmapped:
         cmd.append("--ignore-unmapped")
         
    success, msg = shopper.start(cmd, cwd=repo_root)
    return jsonify({"success": success, "message": msg})

@app.route("/phase3/stop", methods=["POST"])
def stop_shopper():
    success = shopper.stop()
    return jsonify({"success": success})

@app.route("/phase3/status")
def get_status():
    since = int(request.args.get("since", 0))
    # No lock needed for simple reading, list append is atomic-ish
    # But technically safer with lock, but let's trust GIL for list slicing
    new_logs = shopper.logs[since:]
    
    status = "READY"
    if shopper.running:
        status = "RUNNING"
    elif shopper.return_code is not None:
        status = start_shopper.return_code if False else "STOPPED" # simplified
        status = "COMPLETED" if shopper.return_code == 0 else "ERROR"
        if shopper.return_code != 0 and shopper.logs and "killed" in shopper.logs[-1]:
             status = "STOPPED"
        
    return jsonify({
        "status": status,
        "logs": new_logs,
        "next_index": len(shopper.logs),
        "return_code": shopper.return_code
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8766, debug=False)

