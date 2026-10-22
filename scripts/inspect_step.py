"""Print the structure of STEP files (run inside .venv-cad): assembly tree with names,
solid count, colours and bounding boxes. Used to choose parts and plan defect variants.

Usage: python scripts/inspect_step.py <file.step> [...]
"""

import sys

from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_Color
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool


def name_of(label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return "?"


def count_solids(shape) -> int:
    exp, n = TopExp_Explorer(shape, TopAbs_SOLID), 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def bbox(shape):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b)
    if b.IsVoid():
        return None
    x0, y0, z0, x1, y1, z1 = b.Get()
    return (x1 - x0, y1 - y0, z1 - z0)


def colour(color_tool, label, shape):
    c = Quantity_Color()
    for typ in (XCAFDoc_ColorType.XCAFDoc_ColorSurf, XCAFDoc_ColorType.XCAFDoc_ColorGen):
        if color_tool.GetColor_s(label, typ, c) or color_tool.GetColor(shape, typ, c):
            return f"({c.Red():.2f},{c.Green():.2f},{c.Blue():.2f})"
    return "-"


def walk(shape_tool, color_tool, label, depth, lines):
    shape = shape_tool.GetShape_s(label)
    ref = TDF_Label()
    target = label
    if shape_tool.IsReference_s(label) and shape_tool.GetReferredShape_s(label, ref):
        target = ref
    size = bbox(shape)
    size_txt = "-" if size is None else "x".join(f"{v:.1f}" for v in size)
    kind = "assembly" if shape_tool.IsAssembly_s(target) else "part"
    lines.append(f"{'  ' * depth}- {name_of(label)} [{kind}] solids={count_solids(shape)} "
                 f"size={size_txt} colour={colour(color_tool, target, shape)}")
    if shape_tool.IsAssembly_s(target):
        children = TDF_LabelSequence()
        shape_tool.GetComponents_s(target, children)
        for i in range(1, children.Length() + 1):
            walk(shape_tool, color_tool, children.Value(i), depth + 1, lines)


def inspect(path: str) -> None:
    doc = TDocStd_Document(TCollection_ExtendedString("doc"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(path) != IFSelect_RetDone:
        print(f"{path}: cannot read")
        return
    reader.Transfer(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    lines = []
    for i in range(1, roots.Length() + 1):
        walk(shape_tool, color_tool, roots.Value(i), 0, lines)
    print(f"== {path} (units as stored, usually mm)")
    print("\n".join(lines))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        inspect(p)
