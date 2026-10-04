"""Prepare build jobs for Blender and record the results (CLAUDE.md §7.6, §9)."""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
from typing import Any

from room_gen import archetypes, meshgen
from room_gen.blender_exec import run_blender
from room_gen.coords import IMAGE_BLASTER_OBJECT_SCALE, blender_to_three, yaw_deg_to_three_rotation
from room_gen.geometry import PinholeCamera
from room_gen.indexed import artifact_path, latest_indexed, next_index, request_path
from room_gen.jsonio import read_json, read_json_if_exists, write_json
from room_gen.models import MAX_FACES, Recipe, Room
from room_gen.project import World
from room_gen.sidecar import now_iso, write_request
from room_gen.textures import ensure_texture

TEXTURE_DIR = ("output", "world", "textures")


class BuildError(RuntimeError):
    pass


# ----- recipes ------------------------------------------------------------------------------


def _scale_part(part: dict, k: float) -> dict:
    p = copy.deepcopy(part)
    p["position"] = [c * k for c in p.get("position", (0, 0, 0))]
    for key in ("radius", "radius2", "height"):
        if p.get(key) is not None:
            p[key] *= k
    if p.get("size"):
        p["size"] = [c * k for c in p["size"]]
    for key in ("polygon", "profile"):
        if p.get(key):
            p[key] = [[c * k for c in pt] for pt in p[key]]
    if p.get("array"):
        p["array"]["offset"] = [c * k for c in p["array"]["offset"]]
    if p.get("bevel"):
        p["bevel"]["width"] *= k
    return p


def prepare_recipe(recipe: dict, *, auto_fit: bool = True) -> tuple[dict, list[str]]:
    """Validate, expand archetypes, and fit to ``bbox_m``. Returns (recipe, warnings)."""
    warnings: list[str] = []
    if recipe.get("archetype"):
        recipe, w = archetypes.expand(recipe)
        warnings += w
    rec = Recipe.model_validate(recipe).model_dump(mode="json", exclude_none=True)
    lo, hi = meshgen.recipe_bbox(rec)
    size = [hi[i] - lo[i] for i in range(3)]
    if rec.get("bbox_m") and min(size) > 0:
        ratios = [rec["bbox_m"][i] / size[i] for i in range(3) if size[i] > 1e-6]
        err = max(abs(r - 1) for r in ratios)
        if err > 0.10:
            if auto_fit:
                k = math.prod(ratios) ** (1 / len(ratios))
                rec["parts"] = [_scale_part(p, k) for p in rec["parts"]]
                warnings.append(f"{rec['object']}: parts scaled by {k:.3f} to fit bbox_m (was off by {err:.0%})")
            else:
                warnings.append(f"{rec['object']}: built size {size} differs from bbox_m {rec['bbox_m']} by {err:.0%}")
    faces = meshgen.recipe_face_count(rec)
    if faces > MAX_FACES:
        raise BuildError(f"{rec['object']}: {faces} faces exceeds the {MAX_FACES} cap")
    return rec, warnings


def _material_for_job(world: World, spec: dict) -> dict:
    out = dict(spec)
    if spec.get("procedural"):
        out["texture_abs"] = str(ensure_texture(world.path(*TEXTURE_DIR), spec["procedural"], spec.get("base_color", "#cccccc")))
    if spec.get("image"):
        path = world.resolve(spec["image"])
        if path.is_file():
            out["image_abs"] = str(path)
    return out


def load_recipe(world: World, placement: dict | None, object_id: str) -> dict | None:
    ref = (placement or {}).get("recipe") or f"output/{object_id}/recipe.json"
    path = world.resolve(ref)
    return read_json(path) if path.is_file() else None


# ----- scene.json and world manifest ----------------------------------------------------------


def scene_json_from_room(room: dict, object_assets: dict[str, str], existing: dict | None = None) -> dict:
    """image-blaster viewer scene (Three.js Y-up; the viewer renders objects at 0.5 scale)."""
    instances = []
    for k, pl in enumerate(room.get("placements", [])):
        oid = pl["object"]
        inst = {
            "instanceId": f"{oid}-{k + 1}",
            "objectId": oid,
            "physics": "static",
            "position": list(blender_to_three(pl["position"])),
            "rotation": list(yaw_deg_to_three_rotation(pl.get("yaw", 0.0))),
            "scale": [pl.get("scale", 1.0) / IMAGE_BLASTER_OBJECT_SCALE] * 3,
        }
        if oid in object_assets:
            inst["assetId"] = object_assets[oid]
        instances.append(inst)
    scene = dict(existing or {})
    scene.update({"version": 1, "instances": instances, "metricScaleFactor": 1.0, "groundPlaneOffset": 0.0, "groundPlaneColliderEnabled": False})
    sun = (room.get("lighting") or {}).get("sun")
    if sun:
        az, el = math.radians(sun.get("azimuth", 215)), math.radians(sun.get("elevation", 35))
        # direction toward the sun in Three space, expressed as viewer Euler (x, 0, z) from (0, 10, 0)
        d_b = (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))
        x, y, z = blender_to_three(d_b)
        rx = math.asin(max(-1.0, min(1.0, z)))  # viewer: Rz(rz) @ Rx(rx) applied to (0, 10, 0)
        rz = math.atan2(-x, y)
        scene["sun"] = {"intensity": max(0.2, sun.get("strength", 3.0) / 2.5), "rotation": [rx, 0.0, rz]}
    return scene


def world_manifest(world: World, room: dict, index: int, files: dict[str, str | None], models: dict) -> dict:
    caption = room.get("notes", [""])[0] if room.get("notes") else ""
    image_json = read_json_if_exists(world.image_json_path) or {}
    caption = image_json.get("short_caption") or caption or f"Room generated for {world.slug}"
    def url(key):
        return f"/worlds/{world.slug}/output/world/{Path(files[key]).name}" if files.get(key) else ""
    return {
        "world_id": f"room-gen-{world.slug}-{index}",
        "display_name": image_json.get("scene_name") or world.slug.replace("-", " ").title(),
        "assets": {
            "caption": caption,
            "mesh": {"collider_mesh_url": url("glb")},
            "imagery": {"pano_url": ""},
            "thumbnail_url": url("thumbnail"),
            "splats": {"spz_urls": {}, "semantics_metadata": {"metric_scale_factor": 1.0, "ground_plane_offset": 0.0, "flip_y": False}},
        },
        "world_marble_url": "",
        "tags": ["room-gen"],
        "world_prompt": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "generator": {
            "provider": "room-gen",
            "room_json": "room.json",
            "calibration_json": "calibration.json" if world.calibration_path.is_file() else None,
            "files": {k: (Path(v).name if v else None) for k, v in files.items()},
            "tiers_used": models,
        },
    }


def _tiers(room: dict) -> dict:
    tiers: dict[str, str] = {}
    tiers["shell"] = room["shell"].get("provenance", {}).get("by", "auto")
    tiers["lighting"] = room.get("lighting", {}).get("provenance", {}).get("by", "auto")
    if room.get("camera"):
        tiers["camera"] = room["camera"].get("provenance", {}).get("by", "auto")
    for pl in room.get("placements", []):
        tiers[f"placement:{pl['object']}"] = pl.get("provenance", {}).get("by", "auto")
    return tiers


def _hash_inputs(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# ----- build -----------------------------------------------------------------------------------


def build(world: World, *, formats: list[str] | None = None, objects_only: list[str] | None = None,
          force: bool = False, previews: bool = True, blender: str | None = None) -> dict:
    cfg = world.ws.config
    if not world.room_path.is_file():
        raise BuildError(f"{world.workspace_rel(world.room_path)} does not exist; run `room_gen auto` or write it first")
    room_model = Room.model_validate(read_json(world.room_path))
    room = room_model.model_dump(mode="json", exclude_none=True)
    formats = formats or list(cfg.get("exports", ["glb"]))
    if "glb" not in formats:
        formats = ["glb", *formats]
    warnings: list[str] = []

    # objects: every placement plus every recipe under output/<id>/
    object_ids: list[str] = [pl["object"] for pl in room.get("placements", [])]
    for obj in world.objects():
        if obj["has_recipe"] and obj["id"] not in object_ids:
            object_ids.append(obj["id"])
    if objects_only:
        object_ids = [o for o in object_ids if o in objects_only]
    placements = {pl["object"]: pl for pl in room.get("placements", [])}
    input_files = [world.room_path]
    job_objects, job_fixed, asset_ids = [], [], {}
    for oid in object_ids:
        recipe = load_recipe(world, placements.get(oid), oid)
        if recipe is None:
            warnings.append(f"{oid}: no recipe.json; skipped")
            continue
        recipe, w = prepare_recipe(recipe, auto_fit=cfg.get("recipes", {}).get("auto_fit", True))
        warnings += w
        input_files.append(world.resolve((placements.get(oid) or {}).get("recipe") or f"output/{oid}/recipe.json"))
        odir = world.object_dir(oid)
        idx = next_index(odir, oid)
        outs = {fmt: str(artifact_path(odir, idx, oid, f".{fmt}")) for fmt in formats}
        outs["blend"] = str(artifact_path(odir, idx, oid, ".blend"))
        if previews:
            outs["preview"] = str(artifact_path(odir, idx, oid, "-preview.png"))
        mats = {slot: _material_for_job(world, spec) for slot, spec in recipe.get("materials", {}).items()}
        recipe = {**recipe, "materials": mats}
        job_objects.append({"id": oid, "index": idx, "recipe": recipe, "placement": placements.get(oid), "outputs": outs})
        asset_ids[oid] = f"{world.slug}/{oid}/{idx}"
    for ff in room.get("fixed_features", []):
        path = world.resolve(ff["recipe"])
        if not path.is_file():
            warnings.append(f"fixed feature {ff['id']}: recipe {ff['recipe']} missing")
            continue
        recipe, w = prepare_recipe(read_json(path))
        warnings += w
        recipe["materials"] = {slot: _material_for_job(world, spec) for slot, spec in recipe.get("materials", {}).items()}
        job_fixed.append({"id": ff["id"], "recipe": recipe, "placement": {"position": ff["position"], "yaw": ff.get("yaw", 0.0), "scale": 1.0}})
        input_files.append(path)

    wdir = world.path("output", "world")
    digest = _hash_inputs(input_files)
    latest = latest_indexed(wdir, "world", {".json"})
    if latest and not force and not objects_only:
        side = read_json_if_exists(request_path(wdir, latest.index, "world"))
        if side and side.get("input_digest") == digest and side.get("status") == "completed":
            return {"status": "up-to-date", "index": latest.index, "world": world.slug, "message": "inputs unchanged; use --force to rebuild"}
    widx = next_index(wdir, "world")
    files = {fmt: str(artifact_path(wdir, widx, "world", f".{fmt}")) for fmt in formats}
    files["blend"] = str(artifact_path(wdir, widx, "world", ".blend"))
    if previews:
        files["preview"] = str(artifact_path(wdir, widx, "world", "-preview.png"))
    room_files = {fmt: str(artifact_path(wdir, widx, "world-room", f".{fmt}")) for fmt in formats}
    room_files["blend"] = str(artifact_path(wdir, widx, "world-room", ".blend"))
    if previews:
        room_files["preview"] = str(artifact_path(wdir, widx, "world-room", "-preview.png"))
        room_files["plan"] = str(artifact_path(wdir, widx, "world-plan", ".png"))
        room_files["thumbnail_stem"] = str(wdir / f"{widx}-world-thumbnail")

    materials = {name: _material_for_job(world, spec) for name, spec in room.get("materials", {}).items()}
    camera = None
    if room.get("camera"):
        camera = PinholeCamera.from_dict(room["camera"]).blender_params()
    render_cfg = dict(cfg.get("render", {}))
    job = {
        "kind": "build",
        "world": world.slug,
        "room": room,
        "materials": materials,
        "camera": camera,
        "fixed": job_fixed,
        "objects": job_objects,
        "outputs": {"world": files, "room": room_files},
        "render": render_cfg,
        "formats": formats,
    }
    started = now_iso()
    log_path = world.path("output", "world", f".{widx}-world-blender.log")
    try:
        result = run_blender("build", job, config=cfg, blender=blender, log_path=log_path)
    except Exception as exc:
        write_request(request_path(wdir, widx, "world"), kind="world", root=world.ws.root, inputs=input_files,
                      error=str(exc), started_at=started, extra={"input_digest": digest})
        raise
    produced = [o["path"] for o in result.get("outputs", []) if o.get("ok")]
    thumb = next((o["path"] for o in result["outputs"] if o.get("format") == "thumbnail"), None)
    manifest_files = {"glb": files.get("glb"), "blend": files.get("blend"), "preview": files.get("preview"),
                      "room_blend": room_files.get("blend"), "room_glb": room_files.get("glb"), "room_preview": room_files.get("preview"),
                      "plan": room_files.get("plan"), "thumbnail": thumb}
    manifest = world_manifest(world, room, widx, manifest_files, _tiers(room))
    manifest_path = write_json(artifact_path(wdir, widx, "world", ".json"), manifest)
    scene = scene_json_from_room(room, asset_ids, read_json_if_exists(world.scene_path))
    write_json(world.scene_path, scene)
    failed = [o for o in result.get("outputs", []) if not o.get("ok")]
    write_request(request_path(wdir, widx, "world"), kind="world", root=world.ws.root, inputs=input_files,
                  outputs=[*produced, manifest_path], started_at=started,
                  extra={"input_digest": digest, "blender": result.get("blender"), "blender_version": result.get("capabilities", {}).get("blender_version"),
                         "seconds": result.get("seconds"), "warnings": warnings, "failed_outputs": failed})
    for item in job_objects:
        odir = world.object_dir(item["id"])
        outs = [p for k, p in item["outputs"].items() if Path(p).is_file()]
        rep = next((r for r in result.get("objects", []) if r["id"] == item["id"]), {})
        write_request(request_path(odir, item["index"], item["id"], "model"), kind="model", root=world.ws.root,
                      inputs=[world.resolve((item.get("placement") or {}).get("recipe") or f"output/{item['id']}/recipe.json")],
                      outputs=outs, started_at=started, extra={"faces": rep.get("faces"), "dimensions": rep.get("dimensions"), "warnings": rep.get("warnings", [])})
    for rep in result.get("objects", []):
        warnings += [f"{rep['id']}: {w}" for w in rep.get("warnings", [])]
    return {
        "status": "built",
        "world": world.slug,
        "index": widx,
        "seconds": result.get("seconds"),
        "files": {k: world.workspace_rel(v) for k, v in {**files, **{f"room_{k}": v for k, v in room_files.items()}}.items() if v and Path(v).exists()},
        "thumbnail": world.workspace_rel(thumb) if thumb else None,
        "manifest": world.workspace_rel(manifest_path),
        "objects": [{"id": r["id"], "faces": r["faces"], "dimensions": r["dimensions"]} for r in result.get("objects", [])],
        "failed_outputs": failed,
        "warnings": warnings,
    }


def render_room(room: dict, camera: PinholeCamera, out_path: str | Path, *, world: World | None = None,
                objects: list[dict] | None = None, samples: int = 64, config: dict | None = None,
                engine: str = "eevee", blender: str | None = None) -> dict:
    """Render a room spec from an arbitrary camera (synthetic benchmark photos)."""
    texdir = (world.path(*TEXTURE_DIR) if world else Path(out_path).parent / "textures")
    def mat(spec):
        out = dict(spec)
        if spec.get("procedural"):
            out["texture_abs"] = str(ensure_texture(texdir, spec["procedural"], spec.get("base_color", "#cccccc")))
        return out
    job_objects = []
    for item in objects or []:
        rec, _ = prepare_recipe(item["recipe"])
        rec["materials"] = {k: mat(v) for k, v in rec.get("materials", {}).items()}
        job_objects.append({"id": item["id"], "recipe": rec, "placement": item["placement"]})
    job = {
        "kind": "render",
        "room": room,
        "materials": {k: mat(v) for k, v in room.get("materials", {}).items()},
        "camera": camera.blender_params(),
        "objects": job_objects,
        "output": str(Path(out_path).resolve()),
        "samples": samples,
        "engine": engine,
    }
    return run_blender("render", job, config=config, blender=blender)


def bridge(world_dir: str | Path, out_world: World, *, formats: list[str] | None = None, blender: str | None = None) -> dict:
    """Import an image-blaster world directory into Blender and export it."""
    from room_gen.models import SceneProject

    src = Path(world_dir).resolve()
    wdir = src / "output" / "world"
    latest_json = latest_indexed(wdir, "world", {".json"})
    collider = None
    semantics: dict[str, Any] = {}
    if latest_json:
        manifest = read_json(wdir / latest_json.name)
        semantics = ((manifest.get("assets") or {}).get("splats") or {}).get("semantics_metadata") or {}
        cand = artifact_path(wdir, latest_json.index, "world", ".glb")
        collider = str(cand) if cand.is_file() else None
    if collider is None:
        latest_glb = latest_indexed(wdir, "world", {".glb"})
        collider = str(wdir / latest_glb.name) if latest_glb else None
    scene_path = src / "scene.json"
    scene = SceneProject.model_validate(read_json(scene_path)).model_dump(mode="json", exclude_none=True) if scene_path.is_file() else {}
    assets: dict[str, str] = {}
    out_dir = src / "output"
    if out_dir.is_dir():
        for d in out_dir.iterdir():
            if not d.is_dir() or d.name in ("world", "sfx"):
                continue
            glbs = sorted((p for p in d.iterdir() if p.suffix.lower() == ".glb" and not p.name.startswith(".")), key=lambda p: p.name)
            for g in glbs:
                from room_gen.indexed import parse_indexed_name

                parsed = parse_indexed_name(g.name)
                if parsed:
                    assets[f"{src.name}/{d.name}/{parsed.index}"] = str(g)
            latest = latest_indexed(d, extensions={".glb"})
            if latest:
                assets[d.name] = str(d / latest.name)
                assets[f"{src.name}/{d.name}"] = str(d / latest.name)
    out_world.ensure()
    odir = out_world.path("output", "world")
    idx = next_index(odir, "world-bridge")
    formats = formats or ["glb"]
    outputs = {fmt: str(artifact_path(odir, idx, "world-bridge", f".{fmt}")) for fmt in formats}
    outputs["blend"] = str(artifact_path(odir, idx, "world-bridge", ".blend"))
    outputs["preview"] = str(artifact_path(odir, idx, "world-bridge", "-preview.png"))
    job = {"collider": collider, "semantics": semantics, "scene": scene, "assets": assets, "outputs": outputs, "formats": formats}
    result = run_blender("bridge", job, config=out_world.ws.config, blender=blender)
    write_request(request_path(odir, idx, "world-bridge"), kind="bridge", root=out_world.ws.root,
                  inputs=[p for p in [collider, str(scene_path) if scene_path.is_file() else None] if p],
                  outputs=[o["path"] for o in result.get("outputs", []) if o.get("ok")],
                  extra={"source_world": str(src), "instances": len(result.get("instances", [])), "warnings": result.get("warnings", [])})
    return {"status": "bridged", "index": idx, "source": str(src), "world": result.get("world"), "instances": result.get("instances", []),
            "warnings": result.get("warnings", []), "files": {o.get("format", "?"): out_world.workspace_rel(o["path"]) for o in result.get("outputs", []) if o.get("ok")}}
