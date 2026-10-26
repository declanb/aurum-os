"""Paper copy-book smoke: open, mark, close. No network and no broker order.

Usage (from the repo root):
    python scripts/copy_book_smoke.py
    python -m api.services.copy_book smoke
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.services.copy_book import smoke


def main() -> int:
    json.dump(smoke(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
