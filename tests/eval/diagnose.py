"""Compare layout-objective terms for the true room and the estimate of a benchmark scene."""

from __future__ import annotations

import sys

import numpy as np

from room_gen.vision.calib import calibrate_auto
from room_gen.vision.imageio import load_photo, to_gray
from room_gen.vision.layout import estimate_layout
from room_gen.vision.lines import OrientedEdges, detect_segments, enhance, side_contrast
from room_gen.vision.wireframe import RegionColors, SegmentFamilies, box_room_edges, score, soft_value
from tests.eval.benchmark import truth_camera
from tests.eval.scenes import scene


def terms(edges, fam, reg, cam, p):
    sc = score(edges, cam, box_room_edges(*p, tags=True), tau=4.0)
    tags = [t for *_, t in box_room_edges(*p, tags=True)]
    lines = soft_value(edges, cam, box_room_edges(*p), tau=4.0)
    inc, e = fam.incompatible(cam, p), reg.energy(cam, p)
    total = lines - 0.5 * inc - 0.02 * cam.width * e - (400 * (2.4 - p[4]) if p[4] < 2.4 else 0)
    return {"lines": round(lines), "incompat": round(inc), "region": round(e, 1), "total": round(total),
            "per_edge": {t: (round(a), round(b)) for t, (a, b) in zip(tags, sc.per_segment) if b > 0}}


def main(name: str, photo: str) -> None:
    sc = scene(name)
    gt = truth_camera(sc)
    ph = load_photo(photo)
    small, s = ph.working(1024)
    gray = to_gray(small)
    segs = detect_segments(enhance(small))
    cal = calibrate_auto(segs, small.shape[1], small.shape[0])
    cam = cal.camera(gt.C[2])
    edges = OrientedEdges(segs[side_contrast(small, segs) >= 4], gray.shape)
    fam, reg = SegmentFamilies(segs, cal.labels), RegionColors(small)
    q = np.round(cal.R.T @ gt.R)
    tp = np.array(sc["room"]["shell"]["floor_polygon"], float)
    pts = np.array([q[:2, :2] @ (p - gt.C[:2]) for p in tp])
    truth = (pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max(), sc["room"]["shell"]["ceiling_height"])
    lay = estimate_layout(edges, cam, families=fam, regions=reg)
    for label, p in (("truth", truth), ("found", lay.as_tuple())):
        print(label, [round(float(v), 2) for v in p], terms(edges, fam, reg, cam, p))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
