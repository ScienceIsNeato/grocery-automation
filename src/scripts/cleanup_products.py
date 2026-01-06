
import json
import logging
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def unescape_string(s: str) -> str:
    """Remove double backslashes and unescape quotes."""
    if not isinstance(s, str):
        return s
    # Replace \\' with '
    s = s.replace("\\'", "'")
    # Replace \\" with "
    s = s.replace('\\"', '"')
    # Replace \\ with \ (if standing alone, though simpler to just remove escape chars if we assume mostly text)
    # Actually, let's just use standard python unescape?
    # No, the issue is literal backslashes in the json string value.
    # JSON file: "key": "val\\'ue" -> Python str: "val\\'ue"
    # We want "val'ue".
    return s

def clean_products_file(path: Path):
    logger.info(f"Cleaning {path}...")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    products = data.get("products", {})
    new_products = {}
    cleaned_count = 0
    merged_count = 0

    for key, product in products.items():
        # Clean Key
        clean_key = unescape_string(key)
        
        # Clean Product Data
        product["display_name"] = unescape_string(product.get("display_name", ""))
        
        # Clean Original Requests
        raw_ops = product.get("original_requests", [])
        clean_ops = []
        for op in raw_ops:
            clean_op = unescape_string(op)
            if clean_op not in clean_ops:
                clean_ops.append(clean_op)
        product["original_requests"] = clean_ops

        # Merge check
        if clean_key in new_products:
            logger.warning(f"Merge conflict for key '{clean_key}' (was '{key}'). Merging original_requests.")
            existing = new_products[clean_key]
            # Merge original_requests
            combined_ops = list(set(existing["original_requests"] + product["original_requests"]))
            existing["original_requests"] = combined_ops
            # Keep the newest 'added' date (or oldest? doesn't matter much)
            merged_count += 1
        else:
            new_products[clean_key] = product
            
        if clean_key != key:
            cleaned_count += 1
            logger.info(f"Cleaned key: {key} -> {clean_key}")

    data["products"] = new_products
    
    # Backup
    backup_path = path.with_suffix(".json.bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2) # Dump the OLD data? No, I alrady modified 'data' dict... 
        # Wait, I loaded 'data' at start. 'products' was a reference? 
        # I created 'new_products'.
        pass 
    
    # Re-read for backup to be safe
    with open(path, "r", encoding="utf-8") as f:
        raw_backup = f.read()
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(raw_backup)
        
    logger.info(f"Backup saved to {backup_path}")

    # Save Cleaned
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    logger.info(f"Cleanup complete. Cleaned {cleaned_count} keys, Merged {merged_count} entries.")

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[2]
    products_path = repo_root / "data" / "products.json"
    clean_products_file(products_path)
