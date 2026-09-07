"""Geometric and photometric pre-processing before OCR.

Two stages, both classical CV and both cheap enough to run per-frame at the
edge:

1. Perspective rectification. A camera on a pole sees plates at an oblique
   angle; characters are sheared and foreshortened. A 4-point homography warps
   the detected plate quad back to a fronto-parallel rectangle. This alone
   recovers a large share of "angled shot" failures because the OCR model was
   trained on upright text.

2. Low-light enhancement. CLAHE on the luminance channel lifts night and
   tunnel captures without blowing out the retro-reflective plate surface the
   way a global gamma boost does.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is in requirements
    cv2 = None

# Indian plates are 500x120mm (single row) — warp to that aspect ratio.
PLATE_W, PLATE_H = 240, 58


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 corners as top-left, top-right, bottom-right, bottom-left.

    Sorting by coordinate sums/differences is orientation-independent, so this
    survives a plate detected upside-down on a U-turning vehicle.
    """
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([
        pts[np.argmin(s)],   # top-left  has smallest x+y
        pts[np.argmin(d)],   # top-right has smallest y-x
        pts[np.argmax(s)],   # bottom-right
        pts[np.argmax(d)],   # bottom-left
    ], dtype=np.float32)


def rectify_plate(image: np.ndarray, quad, out_size=(PLATE_W, PLATE_H)) -> np.ndarray:
    """Warp the plate quad to a fronto-parallel crop of fixed size."""
    if cv2 is None:
        raise RuntimeError("OpenCV required for rectification")
    src = order_quad(quad)
    w, h = out_size
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, m, (w, h), flags=cv2.INTER_CUBIC)


def skew_angle(quad) -> float:
    """Approximate horizontal skew of the plate in degrees.

    Fed forward as a quality signal: a heavily skewed crop is a weaker vote in
    multi-frame fusion even after rectification.
    """
    q = order_quad(quad)
    tl, tr = q[0], q[1]
    return float(np.degrees(np.arctan2(tr[1] - tl[1], max(1e-6, tr[0] - tl[0]))))


def enhance_low_light(image: np.ndarray, clip_limit: float = 2.5) -> np.ndarray:
    """CLAHE on luminance only — preserves plate colour, lifts shadow detail."""
    if cv2 is None:
        raise RuntimeError("OpenCV required for enhancement")
    if image.ndim == 2:
        return cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(image)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def sharpness(image: np.ndarray) -> float:
    """Variance of Laplacian — the standard blur metric.

    Used as the per-frame `quality` weight in fusion, so a motion-blurred frame
    automatically counts for less than a sharp one.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV required")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
