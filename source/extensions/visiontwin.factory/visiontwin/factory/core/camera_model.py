"""Pinhole model for the top-down inspection camera (pure Python).

Used to turn known geometry (belt width, camera height) into a pixel ROI, so the
inspector gets "camera calibration info" instead of hard-coded pixel numbers.
"""

from typing import Tuple


def pixels_per_meter(focal_mm: float, h_aperture_mm: float, distance_m: float, width_px: int) -> float:
    """Image scale on a plane `distance_m` in front of the camera."""
    if distance_m <= 0:
        raise ValueError("distance must be > 0")
    visible_width_m = distance_m * h_aperture_mm / focal_mm
    return width_px / visible_width_m


def inspection_roi(resolution: Tuple[int, int], focal_mm: float, h_aperture_mm: float,
                   distance_m: float, half_width_m: float, half_length_m: float) -> Tuple[int, int, int, int]:
    """ROI (x0, y0, x1, y1) for a camera centered over the inspection line, image x along
    the belt. Keeps |y| <= half_width_m (belt lane, excludes zone markers) and
    |x| <= half_length_m (inspection window, excludes neighbouring products)."""
    w, h = resolution
    ppm = pixels_per_meter(focal_mm, h_aperture_mm, distance_m, w)
    half_w_px, half_l_px = half_width_m * ppm, half_length_m * ppm
    x0 = max(0, int(round(w / 2 - half_l_px)))
    x1 = min(w, int(round(w / 2 + half_l_px)))
    y0 = max(0, int(round(h / 2 - half_w_px)))
    y1 = min(h, int(round(h / 2 + half_w_px)))
    return x0, y0, x1, y1
