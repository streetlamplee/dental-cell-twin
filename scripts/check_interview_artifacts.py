"""Check Python syntax and new flat Obsidian note links without launching Kit.

Usage: check_interview_artifacts.py. Prints checked file counts; exits nonzero on invalid artifacts.
"""

import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = list((ROOT / "scripts").glob("*.py")) + list((ROOT / "source/extensions/visiontwin.factory/visiontwin/factory").rglob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    notes = {p.stem for p in (ROOT / "docs").rglob("*.md")}
    checked = 0
    for path in (ROOT / "docs").glob("*.md"):
        if path.name == "00_Index.md":
            continue  # legacy note remains intact
        content = path.read_text(encoding="utf-8-sig")
        assert content.startswith("---\n"), path
        frontmatter = content.split("---", 2)[1]
        for key in ("title", "type", "created", "tags", "related"):
            assert re.search(rf"^{key}:", frontmatter, re.M), (path, key)
        assert re.search(r"^title: (.+)$", frontmatter, re.M).group(1) == path.stem, path
        assert re.search(r"^type: (concept|request|decision|moc)$", frontmatter, re.M), path
        for target in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content):
            assert target.split("#",1)[0] in notes, (path, target)
            assert ":" not in target and "/" not in target and "\\" not in target, (path, target)
        checked += 1
    print(f"PASS: Python syntax for {len(files)} files, frontmatter/wikilinks for {checked} notes")


if __name__ == "__main__":
    main()
