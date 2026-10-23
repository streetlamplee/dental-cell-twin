"""Download a robot description (URDF + the meshes its visuals use) at a pinned commit.

For assets/robots/sources.json entry <name>: fetches the URDF, the repository LICENSE and
every mesh file referenced by a <visual> into assets/robots/<name>/, keeping the paths
relative to the repository (so the URDF's relative mesh paths still resolve). Records the
SHA256 of every file in sources.json on the first fetch and refuses a mismatch afterwards.
Files are only written, never executed.

Usage: python scripts/fetch_robot.py <name>
"""

import hashlib
import json
import posixpath
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"


def fetch(repo: str, commit: str, path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    sources_path = ROBOTS / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    spec = sources[name]
    dest = (ROBOTS / name).resolve()
    urdf_bytes = fetch(spec["repo"], spec["commit"], spec["urdf"])
    urdf_dir = posixpath.dirname(spec["urdf"])
    meshes = sorted({m.get("filename") for v in ET.fromstring(urdf_bytes).iter("visual") for m in v.iter("mesh")})
    files = [spec["urdf"], spec["license_file"]] + [posixpath.normpath(posixpath.join(urdf_dir, m)) for m in meshes]
    total, recorded = 0, spec.setdefault("sha256", {})
    for rel in files:
        data = urdf_bytes if rel == spec["urdf"] else fetch(spec["repo"], spec["commit"], rel)
        out = (dest / rel).resolve()
        if dest not in out.parents:
            raise ValueError(f"refusing a path outside {dest}: {rel}")
        digest = hashlib.sha256(data).hexdigest()
        if rel in recorded and recorded[rel] != digest:
            raise ValueError(f"sha256 mismatch for {rel}")
        recorded[rel] = digest
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        total += len(data)
    sources_path.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(files)} files ({len(meshes)} meshes), {total / 1e6:.1f} MB -> {dest}")
    print(f"urdf: {dest / spec['urdf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
