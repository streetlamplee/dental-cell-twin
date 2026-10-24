"""Does STEP metadata survive the CAD -> USD conversion? (run inside .venv-cad: OCP + usd-core)

For every asset in config/cad_assets.json:
  STEP side  every product (part/assembly definition) name and every instance (occurrence)
             name in the XCAF assembly tree (OpenCascade)
  USD side   every `omni:hoops:metadata:*` attribute (instance proxies included); the
             `__STEP:ProductName` values are matched against the STEP names
Reports, per asset: STEP names, USD prims with metadata, which metadata keys exist, how many
STEP names are found in USD (preserved), and which are missing. Writes
results/cad_metadata/report.json and report.md.

Usage: python scripts/verify_cad_metadata.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from pxr import Usd

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "omni:hoops:metadata:"


def step_names(path: Path):
    """(product names, instance names): a product is a shape definition, an instance is a
    reference label that places a product in an assembly (STEP NAUO occurrence)."""
    doc = TDocStd_Document(TCollection_ExtendedString("step"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.Transfer(doc):
        raise RuntimeError(f"cannot read {path}")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    products, instances, seen = set(), set(), set()

    def name(lab):
        attr = TDataStd_Name()
        return attr.Get().ToExtString() if lab.FindAttribute(TDataStd_Name.GetID_s(), attr) else ""

    def walk(label):
        target, ref = label, TDF_Label()
        if tool.IsReference_s(label) and tool.GetReferredShape_s(label, ref):
            target = ref
            instances.add(name(label))
        products.add(name(target))
        key = target.Tag()
        if key in seen:
            return
        seen.add(key)
        children = TDF_LabelSequence()
        tool.GetComponents_s(target, children, False)
        for i in range(1, children.Length() + 1):
            walk(children.Value(i))

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i))
    products.discard("")
    instances.discard("")
    return sorted(products), sorted(instances - products)


def usd_metadata(path: Path):
    stage = Usd.Stage.Open(str(path))
    keys, product_names, prims = Counter(), set(), 0
    for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
        attrs = [a for a in prim.GetAttributes() if a.GetName().startswith(PREFIX)]
        if not attrs:
            continue
        prims += 1
        for a in attrs:
            keys[a.GetName()[len(PREFIX):]] += 1
            if a.GetName().endswith("__STEP:ProductName") and a.Get():
                product_names.add(str(a.Get()))
    return prims, dict(keys), product_names


def main() -> int:
    assets = json.loads((ROOT / "config" / "cad_assets.json").read_text(encoding="utf-8"))["assets"]
    rows = []
    for a in assets:
        names, instances = step_names(ROOT / a["step"])
        prims, keys, product_names = usd_metadata(ROOT / a["usd"])
        found = [n for n in names if n in product_names]
        rows.append({"asset": a["name"], "step_names": len(names), "usd_prims_with_metadata": prims,
                     "metadata_keys": keys, "preserved": len(found),
                     "missing": [n for n in names if n not in product_names],
                     "instance_names": instances,
                     "instance_names_in_usd": [n for n in instances if n in product_names]})
        print(f"{a['name']}: STEP products {len(names)}, preserved in USD {len(found)}, prims with metadata {prims}, "
              f"keys {sorted(keys)}, instance-only names {instances} (in USD: {rows[-1]['instance_names_in_usd']})"
              + (f", MISSING {rows[-1]['missing'][:5]}" if rows[-1]["missing"] else ""))
    out = ROOT / "results" / "cad_metadata"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["| asset | STEP product names | preserved in USD | USD prims with metadata | metadata keys | "
             "instance-only names (not kept) |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['asset']} | {r['step_names']} | {r['preserved']} | {r['usd_prims_with_metadata']} | "
              f"{', '.join(sorted(r['metadata_keys']))} | {', '.join(r['instance_names']) or '-'} |" for r in rows]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(r["step_names"] for r in rows)
    kept = sum(r["preserved"] for r in rows)
    print(f"total: {kept}/{total} STEP product names preserved -> {out / 'report.md'}")
    return 0 if kept == total else 1


if __name__ == "__main__":
    sys.exit(main())
