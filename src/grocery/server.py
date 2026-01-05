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
    substitutions = data.get("substitutions", [])
    task_renames = data.get("task_renames", [])
    new_items = data.get("new_items", [])
    
    results = {"success": True, "errors": []}
    
    try:
        # Write substitutions
        subs_file = repo_root / "data" / "substitutions.json"
        if subs_file.exists():
            with open(subs_file, "r", encoding="utf-8") as f:
                subs_data = json.load(f)
        else:
            subs_data = {"corrections": {}, "defaults": {}}
        
        corrections = subs_data.get("corrections", {})
        for sub in substitutions:
            corrections[sub["key"]] = sub["value"]
        subs_data["corrections"] = corrections
        
        with open(subs_file, "w", encoding="utf-8") as f:
            json.dump(subs_data, f, indent=2)
        
        results["substitutions_written"] = len(substitutions)
        
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8766, debug=False)

