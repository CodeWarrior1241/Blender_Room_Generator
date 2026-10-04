"""Straight line segments (LSD, with FLD and Hough fallbacks) and oriented edge maps."""

from __future__ import annotations

import math

import cv2
import numpy as np


def enhance(rgb: np.ndarray, clip: float = 3.0) -> np.ndarray:
    """Locally contrast-enhanced luminance (CLAHE on CIE L) so faint wall/ceiling
    boundaries reach the line detector's gradient threshold."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(lab[..., 0])


def detect_segments(gray: np.ndarray, min_len: float | None = None) -> np.ndarray:
    """Return (N, 4) float segments x1, y1, x2, y2 in continuous pixel coordinates."""
    h, w = gray.shape[:2]
    min_len = min_len if min_len is not None else 0.025 * max(w, h)
    segs = None
    try:
        lsd = cv2.createLineSegmentDetector()
        segs = lsd.detect(gray)[0]
    except (cv2.error, AttributeError):
        segs = None
    if segs is None or len(segs) == 0:
        try:
            segs = cv2.ximgproc.createFastLineDetector().detect(gray)
        except (cv2.error, AttributeError):
            segs = None
    if segs is None or len(segs) == 0:
        edges = cv2.Canny(gray, 60, 160)
        segs = cv2.HoughLinesP(edges, 1, np.pi / 360, 40, minLineLength=int(min_len), maxLineGap=4)
    if segs is None or len(segs) == 0:
        return np.zeros((0, 4))
    segs = segs.reshape(-1, 4).astype(np.float64) + 0.5
    length = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    return segs[length >= min_len]


def lengths(segs: np.ndarray) -> np.ndarray:
    return np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])


def homogeneous(segs: np.ndarray) -> np.ndarray:
    p1 = np.column_stack([segs[:, 0], segs[:, 1], np.ones(len(segs))])
    p2 = np.column_stack([segs[:, 2], segs[:, 3], np.ones(len(segs))])
    lines = np.cross(p1, p2)
    return lines / np.linalg.norm(lines[:, :2], axis=1, keepdims=True)


def side_contrast(rgb: np.ndarray, segs: np.ndarray, offsets=(3.0, 7.0), samples: int = 24) -> np.ndarray:
    """Colour difference (CIE Lab, Delta E) between thin strips on either side of each segment.

    Boundaries between surfaces (wall/floor, wall/ceiling) have high contrast; texture lines
    such as floor-plank seams have the same colour on both sides.
    """
    if len(segs) == 0:
        return np.zeros(0)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    h, w = lab.shape[:2]
    p1, p2 = segs[:, :2], segs[:, 2:]
    d = p2 - p1
    length = np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    n = np.column_stack([-d[:, 1], d[:, 0]]) / length
    t = np.linspace(0.15, 0.85, samples)
    pts = p1[:, None, :] + d[:, None, :] * t[None, :, None]
    sides = []
    for sign in (1.0, -1.0):
        acc = []
        for off in offsets:
            q = pts + sign * off * n[:, None, :]
            xi = np.clip(q[..., 0].astype(int), 0, w - 1)
            yi = np.clip(q[..., 1].astype(int), 0, h - 1)
            acc.append(lab[yi, xi])
        sides.append(np.median(np.concatenate(acc, axis=1), axis=1))
    return np.linalg.norm(sides[0] - sides[1], axis=1)


class OrientedEdges:
    """Per-orientation distance transforms of rasterised segments (oriented chamfer)."""

    def __init__(self, segs: np.ndarray, shape: tuple[int, int], bins: int = 12, trunc: float = 30.0):
        self.h, self.w = shape
        self.bins = bins
        self.trunc = trunc
        self.maps = []
        ang = np.mod(np.arctan2(segs[:, 3] - segs[:, 1], segs[:, 2] - segs[:, 0]), np.pi) if len(segs) else np.zeros(0)
        width = np.pi / bins
        for b in range(bins):
            centre = (b + 0.5) * width
            diff = np.abs(np.mod(ang - centre + np.pi / 2, np.pi) - np.pi / 2)
            sel = segs[diff <= width * 1.0]
            canvas = np.full((self.h, self.w), 255, np.uint8)
            for x1, y1, x2, y2 in sel:
                cv2.line(canvas, (int(round(x1 - 0.5)), int(round(y1 - 0.5))), (int(round(x2 - 0.5)), int(round(y2 - 0.5))), 0, 1, cv2.LINE_8)
            dist = cv2.distanceTransform(canvas, cv2.DIST_L2, 3)
            self.maps.append(np.minimum(dist, trunc).astype(np.float32))
        self.maps = np.stack(self.maps) if self.maps else np.zeros((bins, self.h, self.w), np.float32)

    def lookup(self, pts: np.ndarray, angles: np.ndarray) -> np.ndarray:
        """Distance to the nearest same-orientation segment for each point (truncated)."""
        if len(pts) == 0:
            return np.zeros(0)
        b = (np.mod(angles, np.pi) / (np.pi / self.bins)).astype(int) % self.bins
        xi = np.clip(pts[:, 0].astype(int), 0, self.w - 1)
        yi = np.clip(pts[:, 1].astype(int), 0, self.h - 1)
        return self.maps[b, yi, xi]


def draw_segments(rgb: np.ndarray, segs: np.ndarray, labels: np.ndarray | None = None) -> np.ndarray:
    out = rgb.copy()
    colors = [(230, 60, 60), (60, 200, 60), (60, 110, 240), (160, 160, 160)]
    for i, (x1, y1, x2, y2) in enumerate(segs):
        c = colors[int(labels[i]) if labels is not None and labels[i] >= 0 else 3]
        cv2.line(out, (int(x1), int(y1)), (int(x2), int(y2)), c, 2, cv2.LINE_AA)
    return out


def angle_of(v: np.ndarray) -> np.ndarray:
    return np.arctan2(v[..., 1], v[..., 0])


def deg(x: float) -> float:
    return math.degrees(x)
