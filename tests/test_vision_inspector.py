import inspect as pyinspect

import cv2
import numpy as np
import pytest

from core.camera_model import inspection_roi, pixels_per_meter
from core.vision_inspector import (DEFECT, GOOD, UNKNOWN, InspectionResult, InspectorConfig, VisionInspector,
                                   combine_views, hue_distance, load_view_configs, save_view_configs)

W, H = 640, 480
BLUE = (40, 110, 220)  # RGB, hue ~108 in OpenCV scale
RED = (220, 70, 40)  # RGB, hue ~5
BELT = (30, 30, 30)
FLOOR = (200, 200, 205)


def scene(product_rgb=None, center=(320, 240), size=90, belt_rows=(100, 380)):
    img = np.full((H, W, 3), FLOOR, np.uint8)
    img[belt_rows[0]:belt_rows[1]] = BELT
    if product_rgb is not None:
        cx, cy = center
        h = size // 2
        img[cy - h:cy + h, cx - h:cx + h] = product_rgb
    return img


def hue_of(rgb):
    return int(cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2HSV)[0, 0, 0])


@pytest.fixture
def inspector():
    return VisionInspector(InspectorConfig(roi=(0, 100, W, 380), reference_hue=hue_of(BLUE)))


def test_good_product_is_good(inspector):
    r = inspector.inspect(scene(BLUE))
    assert r.label == GOOD
    assert r.score > 0.95
    assert r.bbox is not None and r.area_px > 5000


def test_color_defect_is_defect(inspector):
    r = inspector.inspect(scene(RED))
    assert r.label == DEFECT
    assert r.score < 0.05


def test_partial_discoloration_is_defect(inspector):
    img = scene(BLUE)
    img[195:285, 275:320] = RED  # left half of the product discolored
    r = inspector.inspect(img)
    assert r.label == DEFECT
    assert 0.3 < r.score < 0.7


def test_empty_belt_is_unknown(inspector):
    r = inspector.inspect(scene(None))
    assert r.label == UNKNOWN
    assert r.bbox is None


def test_small_noise_is_unknown(inspector):
    img = scene(None)
    img[240:245, 300:305] = BLUE
    assert inspector.inspect(img).label == UNKNOWN


def test_saturated_object_outside_roi_is_ignored(inspector):
    img = scene(None)
    img[20:80, 300:360] = RED  # beside the belt (e.g. a zone marker)
    assert inspector.inspect(img).label == UNKNOWN


def test_dark_lighting_still_classifies(inspector):
    dark_blue = tuple(int(v * 0.45) for v in BLUE)
    r = inspector.inspect(scene(dark_blue))
    assert r.label == GOOD


def test_latency_and_params_recorded(inspector):
    r = inspector.inspect(scene(BLUE))
    assert r.latency_ms >= 0
    assert r.params["roi"] == (0, 100, W, 380)


def test_rgba_input_accepted_and_bad_shape_rejected(inspector):
    rgba = np.dstack([scene(BLUE), np.full((H, W), 255, np.uint8)])
    assert inspector.inspect(rgba).label == GOOD
    with pytest.raises(ValueError):
        inspector.inspect(np.zeros((H, W), np.uint8))


def flange(paint, insert: bool):
    """Synthetic top view of a flange bearing: painted plate with a bore; the insert
    shows a bright ring inside the bore, a missing insert shows the dark belt."""
    img = scene(None)
    cv2.ellipse(img, (320, 240), (95, 55), 0, 0, 360, paint, -1)
    cv2.circle(img, (250, 240), 10, BELT, -1)  # bolt holes
    cv2.circle(img, (390, 240), 10, BELT, -1)
    cv2.circle(img, (320, 240), 40, BELT, -1)  # bore
    if insert:
        cv2.circle(img, (320, 240), 38, (230, 230, 230), -1)  # outer ring (bright, unsaturated)
        cv2.circle(img, (320, 240), 26, (20, 20, 20), -1)  # seal
        cv2.circle(img, (320, 240), 12, (220, 220, 220), -1)  # inner ring
        cv2.circle(img, (320, 240), 6, BELT, -1)  # shaft bore
    return img


@pytest.fixture
def part_inspector():
    return VisionInspector(InspectorConfig(roi=(0, 100, W, 380), reference_hue=hue_of(BLUE),
                                           good_ratio_min=0.85, interior_bright_min=0.3))


def test_part_good_passes_both_checks(part_inspector):
    r = part_inspector.inspect(flange(BLUE, insert=True))
    assert r.label == GOOD and r.defect_reason == ""
    assert r.interior_bright > 0.3


def test_part_missing_insert_is_shape_defect(part_inspector):
    r = part_inspector.inspect(flange(BLUE, insert=False))
    assert r.label == DEFECT and r.defect_reason == "shape"
    assert r.interior_bright < 0.05


def test_part_color_defect_reports_color(part_inspector):
    r = part_inspector.inspect(flange(RED, insert=True))
    assert r.label == DEFECT and r.defect_reason == "color"


def test_box_config_has_shape_check_off(inspector):
    r = inspector.inspect(scene(BLUE))
    assert r.label == GOOD and r.defect_reason == ""
    assert np.isnan(r.interior_bright)


IVORY = (235, 228, 205)
PINK = (232, 150, 165)
BELT_DARK = (100, 100, 104)


def crown(color, remnant=False, dx=0):
    """Top view of a crown on a dark belt, with a cast shadow (darker than the belt)."""
    img = np.full((H, W, 3), BELT_DARK, np.uint8)
    cx, cy = 320 + dx, 240
    cv2.rectangle(img, (cx - 70, cy - 25), (cx - 10, cy + 70), (55, 55, 58), -1)  # shadow
    cv2.rectangle(img, (cx - 40, cy - 36), (cx + 40, cy + 36), color, -1)
    for sx, sy in ((-40, -36), (40, -36), (-40, 36), (40, 36)):  # round the corners
        cv2.rectangle(img, (cx + min(sx, 0) + (0 if sx < 0 else -12), cy + min(sy, 0) + (0 if sy < 0 else -12)),
                      (cx + max(sx, 0) + (12 if sx < 0 else 0), cy + max(sy, 0) + (12 if sy < 0 else 0)),
                      BELT_DARK, -1)
        cv2.circle(img, (cx + sx - 12 * np.sign(sx), cy + sy - 12 * np.sign(sy)), 12, color, -1)
    cv2.line(img, (cx, cy - 30), (cx, cy + 30), tuple(int(v * 0.8) for v in color), 2)  # fissure
    if remnant:
        cv2.rectangle(img, (cx + 5, cy - 50), (cx + 60, cy - 5), (225, 222, 210), -1)  # unmilled corner
    return img


def lab_ab(rgb):
    return tuple(float(v) for v in cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2LAB)[0, 0, 1:])


@pytest.fixture
def crown_inspector():
    base = InspectorConfig(segment="bright", bright_delta=25, color_metric="ab", reference_ab=lab_ab(IVORY),
                           ab_tolerance=8.0, good_ratio_min=0.8)
    golden = VisionInspector(base).inspect(crown(IVORY))
    cfg = InspectorConfig(**{**base.__dict__, "golden_contour": golden.contour,
                             "golden_area_px": float(cv2.contourArea(np.array(golden.contour, np.int32))),
                             "shape_dist_max": 0.05, "area_ratio_tol": 0.1})
    return VisionInspector(cfg)


def test_crown_good_ignores_shadow_and_passes(crown_inspector):
    r = crown_inspector.inspect(crown(IVORY, dx=25))  # translation must not matter
    assert r.label == GOOD, r.reason
    assert r.area_ratio == pytest.approx(1.0, abs=0.05)
    x, y, w, h = r.bbox
    assert w < 110  # the shadow is not part of the silhouette


def test_crown_wrong_shade_is_color_defect(crown_inspector):
    r = crown_inspector.inspect(crown(PINK))
    assert r.label == DEFECT and r.defect_reason == "color", r.reason


def test_crown_unmilled_corner_is_shape_defect(crown_inspector):
    r = crown_inspector.inspect(crown(IVORY, remnant=True))
    assert r.label == DEFECT and "shape" in r.defect_reason, r.reason
    assert r.area_ratio > 1.1 or r.shape_dist > 0.05


def test_inspector_api_takes_only_pixels():
    params = list(pyinspect.signature(VisionInspector.inspect).parameters)
    assert params == ["self", "rgb"]  # no product id / ground truth can be passed


def test_hue_distance_wraps():
    assert hue_distance(np.array([178]), 2.0)[0] == pytest.approx(4.0)


def test_camera_model_roi_matches_geometry():
    ppm = pixels_per_meter(18.0, 20.955, 1.2, 640)
    assert ppm == pytest.approx(640 / (1.2 * 20.955 / 18.0))
    x0, y0, x1, y1 = inspection_roi((640, 480), 18.0, 20.955, 1.2, 0.3, 0.25)
    assert x1 - x0 == pytest.approx(0.5 * ppm, abs=2)
    assert y1 - y0 == pytest.approx(0.6 * ppm, abs=2)
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((320, 240), abs=1)


def test_neighbour_product_outside_inspection_window_is_ignored():
    # Regression (2026-10-21): a saturated neighbour at the image edge was classified
    # instead of the washed-out product in the centre.
    roi = inspection_roi((W, H), 18.0, 20.955, 1.2, 0.28, 0.25)
    insp = VisionInspector(InspectorConfig(roi=roi, reference_hue=hue_of(BLUE)))
    img = scene(BLUE)
    img[200:280, 600:640] = RED  # neighbour entering the frame on the right
    assert insp.inspect(img).label == GOOD
    img = scene(RED)
    img[200:280, 0:40] = BLUE
    assert insp.inspect(img).label == DEFECT


def _res(label, reason=""):
    r = InspectionResult(label, 1.0 if label == GOOD else 0.4, 500, 0.0, None, 1.0, "")
    r.defect_reason = reason
    return r


def test_combine_views_defect_in_any_view_wins():
    names = ["top", "side_a", "side_b"]
    out = combine_views([_res(GOOD), _res(DEFECT, "shape"), _res(UNKNOWN)], names)
    assert out.label == DEFECT and out.defect_reason == "shape"
    assert "side_a: defect shape" in out.reason and out.latency_ms == 3.0


def test_combine_views_unknown_without_defect_and_all_good():
    names = ["top", "side_a"]
    assert combine_views([_res(GOOD), _res(UNKNOWN)], names).label == UNKNOWN
    assert combine_views([_res(GOOD), _res(GOOD)], names).label == GOOD
    out = combine_views([_res(DEFECT, "color"), _res(DEFECT, "color+shape")], names)
    assert out.defect_reason == "color+shape"


def test_view_configs_round_trip_and_flat_file(tmp_path):
    cfgs = [InspectorConfig(reference_ab=(127.0, 133.0)), InspectorConfig(shape_dist_max=0.03)]
    save_view_configs(str(tmp_path / "multi.json"), cfgs, ["top", "side_a"])
    back = load_view_configs(str(tmp_path / "multi.json"))
    assert len(back) == 2 and back[0].reference_ab == (127.0, 133.0) and back[1].shape_dist_max == 0.03
    InspectorConfig(sat_min=33).save(str(tmp_path / "flat.json"))
    assert [c.sat_min for c in load_view_configs(str(tmp_path / "flat.json"))] == [33]


def test_silhouette_diff_finds_a_small_dent_that_hu_moments_miss():
    from core.vision_inspector import silhouette_diff

    def contour(dent):
        img = np.zeros((200, 200), np.uint8)
        cv2.rectangle(img, (60, 70), (140, 130), 1, cv2.FILLED)
        if dent:
            cv2.rectangle(img, (90, 120), (110, 131), 0, cv2.FILLED)  # notch in the lower edge
        cs, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return cs[0]

    good, dented = contour(False), contour(True)
    shifted = good + np.array([[[7, -5]]], np.int32)
    assert silhouette_diff(shifted, good) < 0.01  # centroid alignment: position does not matter
    assert silhouette_diff(dented, good) > 0.04
