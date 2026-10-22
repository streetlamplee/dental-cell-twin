"""Download the CAD parts listed in assets/parts/sources.json (system Python, stdlib only).

Each entry is saved to assets/parts/raw/<name>.step. On first download its SHA256 is
written back into sources.json; later downloads must match it (the source changed
otherwise, and the run stops).

Usage: python scripts/fetch_parts.py [name ...]
  no names: entries with status "selected"; named: those entries (any status, e.g. to
  evaluate a candidate).
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets" / "parts" / "sources.json"
RAW = ROOT / "assets" / "parts" / "raw"


def main() -> int:
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    wanted = set(sys.argv[1:])
    RAW.mkdir(parents=True, exist_ok=True)
    changed, failed = False, 0
    for part in data["parts"]:
        if (part["name"] not in wanted) if wanted else (part.get("status") != "selected"):
            continue
        dest = RAW / f"{part['name']}.step"
        req = urllib.request.Request(part["url"], headers={"User-Agent": "visiontwin-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        digest = hashlib.sha256(body).hexdigest()
        if part.get("sha256") and part["sha256"] != digest:
            print(f"MISMATCH {part['name']}: expected {part['sha256']}, got {digest}")
            failed += 1
            continue
        if not part.get("sha256"):
            part["sha256"] = digest
            changed = True
        dest.write_bytes(body)
        print(f"ok {part['name']}: {len(body)} bytes sha256={digest[:12]}... -> {dest.relative_to(ROOT)}")
    if changed:
        SOURCES.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"recorded new sha256 values in {SOURCES.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
