from pathlib import Path

import pytest

from core.product_catalog import BOX, ProductCatalog

PARTS = Path(__file__).resolve().parents[1] / "assets" / "parts"


def test_box_has_no_variants():
    c = ProductCatalog(BOX)
    assert c.is_box and c.defect_kinds == ("color",)
    assert c.variant_path("defect", "color") is None


def test_kfl08_variants_follow_ground_truth():
    c = ProductCatalog("kfl08", str(PARTS))
    assert c.defect_kinds == ("color", "missing")
    assert c.variant_path("good", None).endswith("kfl08_good.usda")
    assert c.variant_path("defect", "color").endswith("kfl08_color.usda")
    assert c.variant_path("defect", "missing").endswith("kfl08_missing.usda")
    with pytest.raises(KeyError):
        c.variant_path("defect", "scratch")


def test_kfl08_is_not_processed():
    c = ProductCatalog("kfl08", str(PARTS))
    assert c.process is None and c.camera is None and c.spawn_interval is None
    assert c.raw_path("good", None) is None


def test_crown_is_inspected_by_the_cell_with_four_defect_shapes():
    c = ProductCatalog("crown", str(PARTS))
    assert c.process is None and c.camera is None  # no milling, no fixed top camera
    cell = c.cell
    assert [v["name"] for v in cell.views] == ["top", "side_a", "side_b", "side_c", "side_d"]
    assert cell.standoff_m == 0.11 and cell.focal_mm == 24.0
    assert c.defect_kinds == ("chip", "color", "shape")
    assert c.raw_path("defect", "chip") is None
    for gt, kind in (("good", None), ("defect", "color"), ("defect", "shape"), ("defect", "chip")):
        if not Path(c.variant_path(gt, kind)).exists():
            pytest.skip("run scripts/make_part_variants.ps1 -Part crown first")


def test_box_and_kfl08_have_no_cell():
    assert ProductCatalog("box").cell is None
    assert ProductCatalog("kfl08", str(PARTS)).cell is None


def test_variant_files_exist_after_make_part_variants():
    c = ProductCatalog("kfl08", str(PARTS))
    for gt, kind in (("good", None), ("defect", "color"), ("defect", "missing")):
        if not Path(c.variant_path(gt, kind)).exists():
            pytest.skip("run scripts/make_part_variants.ps1 first")
