"""Local backend for the web annotator (CLAUDE.md §8.10). Serves annotator/dist and a JSON API.

Everything the annotator does ends up in ``annotations.json``; the same file run through the
CLI produces the same build.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from room_gen import archetypes, shellgeom
from room_gen.geometry import PinholeCamera
from room_gen.jsonio import read_json_if_exists, write_json
from room_gen.models import Annotations
from room_gen.project import Workspace, World

DIST = Path(__file__).resolve().parent.parent / "annotator" / "dist"


def _world(ws: Workspace, slug: str) -> World:
    w = ws.world(slug)
    if not w.dir.is_dir():
        raise HTTPException(404, f"world {slug!r} not found")
    return w


def _default_annotations(w: World) -> dict:
    from room_gen.vision.imageio import load_photo

    img = w.primary_image()
    if img is None:
        raise HTTPException(409, "the world has no source image yet")
    photo = load_photo(img)
    return {"schema_version": 1, "world": w.slug, "image": w.rel(img), "image_size": [photo.width, photo.height],
            "calibration": {}, "objects": [], "openings": [], "floor_corners": [], "known_lengths": [], "notes": [],
            "provenance": {"by": "human", "tool": "annotator", "confidence": 0.9}}


def _camera_from_files(w: World) -> tuple[PinholeCamera, str] | None:
    room = read_json_if_exists(w.room_path)
    if room and room.get("camera"):
        return PinholeCamera.from_dict(room["camera"]), "room"
    cal = read_json_if_exists(w.calibration_path)
    if cal:
        cam = PinholeCamera(cal["fx"], cal["fy"], cal["cx"], cal["cy"], cal["image_size"][0], cal["image_size"][1], cal["R"], cal["camera_position"])
        return cam, "calibration"
    return None


def _project_lines(cam: PinholeCamera, segs3d, n: int = 40) -> list[list[list[float]]]:
    out = []
    for a, b in segs3d:
        t = np.linspace(0, 1, n)[:, None]
        pts = np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t
        uv, z = cam.project(pts)
        ok = (z > 0.05) & np.isfinite(uv).all(axis=1)
        line = [[round(float(p[0]), 1), round(float(p[1]), 1)] for p, good in zip(uv, ok) if good and abs(p).max() < 1e5]
        if len(line) >= 2:
            out.append(line)
    return out


def create_app(root: str | Path = ".", config: str | Path | None = None) -> FastAPI:
    ws = Workspace.open(root, config)
    app = FastAPI(title="room_gen annotator", version="0.1")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "root": str(ws.root), "annotator_built": (DIST / "index.html").is_file()}

    @app.get("/api/worlds")
    def worlds() -> dict:
        return {"worlds": [{"slug": s, **ws.world(s).state()["state"]} for s in ws.worlds()]}

    @app.get("/api/worlds/{slug}")
    def world(slug: str) -> dict:
        w = _world(ws, slug)
        return {"slug": w.slug, **w.state(), "annotations": read_json_if_exists(w.annotations_path),
                "room": read_json_if_exists(w.room_path), "calibration": read_json_if_exists(w.calibration_path)}

    @app.get("/api/worlds/{slug}/image")
    def image(slug: str):
        w = _world(ws, slug)
        img = w.primary_image()
        if img is None:
            raise HTTPException(404, "no source image")
        return FileResponse(img)

    @app.get("/api/worlds/{slug}/annotations")
    def get_annotations(slug: str) -> dict:
        w = _world(ws, slug)
        return read_json_if_exists(w.annotations_path) or _default_annotations(w)

    @app.put("/api/worlds/{slug}/annotations")
    def put_annotations(slug: str, body: dict[str, Any] = Body(...)) -> dict:
        w = _world(ws, slug)
        try:
            ann = Annotations.model_validate(body)
        except ValidationError as exc:
            return JSONResponse(status_code=422, content={"ok": False, "errors": exc.errors(include_url=False, include_context=False)})
        write_json(w.annotations_path, ann)
        return {"ok": True, "objects": len(ann.objects), "openings": len(ann.openings)}

    @app.get("/api/worlds/{slug}/camera")
    def camera(slug: str, grid: float = 0.5) -> dict:
        """Current camera plus a projected floor grid and room wireframe (native pixels)."""
        w = _world(ws, slug)
        got = _camera_from_files(w)
        if got is None:
            raise HTTPException(409, "no calibration yet; run auto or calibrate first")
        cam, source = got
        room = read_json_if_exists(w.room_path)
        lines = []
        if room:
            x0, y0, x1, y1 = shellgeom.bbox([tuple(p) for p in room["shell"]["floor_polygon"]])
        else:
            x0, y0, x1, y1 = cam.C[0] - 4, cam.C[1], cam.C[0] + 4, cam.C[1] + 8
        for x in np.arange(math.floor(x0 / grid) * grid, x1 + 1e-6, grid):
            lines.append(((x, y0, 0.0), (x, y1, 0.0)))
        for y in np.arange(math.floor(y0 / grid) * grid, y1 + 1e-6, grid):
            lines.append(((x0, y, 0.0), (x1, y, 0.0)))
        wire = [(a, b) for a, b, _ in shellgeom.shell_edges_world(room["shell"])] if room else []
        return {"source": source, "camera": cam.to_dict(), "hfov_deg": round(cam.hfov_deg, 2),
                "floor_grid": _project_lines(cam, lines), "wireframe": _project_lines(cam, wire)}

    @app.post("/api/worlds/{slug}/backproject")
    def backproject(slug: str, body: dict[str, Any] = Body(...)) -> dict:
        """Pixels -> floor-plane points (metres) with the current camera."""
        w = _world(ws, slug)
        got = _camera_from_files(w)
        if got is None:
            raise HTTPException(409, "no calibration yet")
        cam, _ = got
        pts, ok = cam.floor_point(body.get("points", []))
        return {"points": [[round(float(p[0]), 4), round(float(p[1]), 4)] if good else None for p, good in zip(pts, ok)]}

    @app.post("/api/worlds/{slug}/auto")
    def auto(slug: str, body: dict[str, Any] = Body(default={})) -> dict:
        from room_gen.pipeline import run_auto

        w = _world(ws, slug)
        try:
            return {"ok": True, **run_auto(w, ml_mode=body.get("ml"), fit=body.get("fit"), textures=body.get("textures"))}
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/worlds/{slug}/build")
    def build(slug: str, body: dict[str, Any] = Body(default={})) -> dict:
        from room_gen.blender_exec import BlenderError
        from room_gen.build import BuildError
        from room_gen.build import build as do_build

        w = _world(ws, slug)
        try:
            return {"ok": True, **do_build(w, formats=body.get("formats"), force=bool(body.get("force", False)))}
        except (BuildError, BlenderError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/worlds/{slug}/files/{path:path}")
    def files(slug: str, path: str):
        w = _world(ws, slug)
        target = (w.dir / path).resolve()
        if w.dir.resolve() not in target.parents or not target.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(target)

    @app.get("/api/archetypes")
    def list_archetypes() -> dict:
        return {"archetypes": [archetypes.describe(n) for n in archetypes.names()]}

    @app.get("/api/archetypes/resolve")
    def resolve(label: str) -> dict:
        name, matched = archetypes.resolve(label)
        return {"label": label, "archetype": name, "matched": matched}

    if (DIST / "index.html").is_file():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="annotator")
    else:
        @app.get("/")
        def missing() -> JSONResponse:
            return JSONResponse({"ok": False, "error": "annotator not built: cd annotator && npm install && npm run build"}, status_code=503)

    return app
