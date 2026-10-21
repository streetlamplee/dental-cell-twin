import inspect as pyinspect

import cv2
import numpy as np
import pytest

from core.camera_model import inspection_roi, pixels_per_meter
from core.vision_inspector import DEFECT, GOOD, UNKNOWN, InspectorConfig, VisionInspector, hue_distance

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
