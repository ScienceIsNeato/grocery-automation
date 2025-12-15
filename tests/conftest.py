import sys
from pathlib import Path


def pytest_configure():
    # Ensure src/ is on the import path for tests without requiring installation.
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


