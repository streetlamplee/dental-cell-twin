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


def test_variant_files_exist_after_make_part_variants():
    c = ProductCatalog("kfl08", str(PARTS))
    for gt, kind in (("good", None), ("defect", "color"), ("defect", "missing")):
        if not Path(c.variant_path(gt, kind)).exists():
            pytest.skip("run scripts/make_part_variants.ps1 first")
