"""``room_gen`` command line. Every command prints one JSON report on stdout."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from room_gen import __version__
from room_gen.jsonio import dumps, read_json, write_json
from room_gen.project import Workspace

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Photo of a room -> editable Blender scene.")
archetypes_app = typer.Typer(help="Parametric furniture archetypes.", no_args_is_help=True)
models_app = typer.Typer(help="Optional local vision models (room_gen[ml]).", no_args_is_help=True)
app.add_typer(archetypes_app, name="archetypes")
app.add_typer(models_app, name="models")


class Ctx:
    root: Path = Path(".")
    config: Optional[Path] = None
    blender: Optional[str] = None


def ws() -> Workspace:
    return Workspace.open(Ctx.root, Ctx.config)


def emit(obj, code: int = 0) -> None:
    sys.stdout.write(dumps(obj))
    sys.stdout.flush()
    if code:
        raise typer.Exit(code)


def fail(message: str, **extra) -> None:
    emit({"ok": False, "error": message, **extra}, code=1)


@app.callback()
def _main(
    root: Path = typer.Option(Path("."), "--root", help="Workspace root (holds worlds/ and input/)."),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to room_gen.config.json."),
    blender: Optional[str] = typer.Option(None, "--blender", help="Blender executable."),
) -> None:
    Ctx.root, Ctx.config, Ctx.blender = root, config, blender


@app.command()
def version() -> None:
    emit({"room_gen": __version__})


@app.command()
def probe() -> None:
    """Report Blender, OpenCV, optional models and annotator status."""
    from room_gen.blender_exec import BlenderError, blender_version, find_blender, run_blender

    w = ws()
    report: dict = {"ok": True, "room_gen": __version__, "python": sys.version.split()[0]}
    exe = find_blender(w.config, Ctx.blender)
    report["blender"] = {"path": exe, "version": blender_version(exe) if exe else None}
    if exe:
        try:
            caps = run_blender("probe", None, config=w.config, blender=exe, timeout=120)
            report["blender"]["capabilities"] = {k: v for k, v in caps.items() if k not in ("ok", "command", "blender")}
        except BlenderError as exc:
            report["blender"]["error"] = str(exc)
    else:
        report["ok"] = False
        report["blender"]["install"] = "https://www.blender.org/download/"
    try:
        import cv2

        report["opencv"] = cv2.__version__
    except ImportError:
        report["opencv"] = None
    from room_gen.ml import runtime

    report["ml"] = runtime.status(w.config)
    dist = Path(__file__).resolve().parent.parent / "annotator" / "dist" / "index.html"
    report["annotator_built"] = dist.is_file()
    report["worlds"] = w.worlds()
    staged = sorted(p.name for p in w.input_dir.iterdir() if p.is_file() and not p.name.startswith(".")) if w.input_dir.is_dir() else []
    report["staged_input"] = staged
    emit(report)


@app.command()
def project(
    world: str = typer.Option(..., "--world", help="World slug (created if missing)."),
    stage_input: bool = typer.Option(False, "--stage-input", help="Move input/ images into source/."),
    display_name: Optional[str] = typer.Option(None, "--display-name"),
) -> None:
    """Create or inspect a world envelope (parity with image-blaster's project-state)."""
    w = ws().world(world)
    if not w.slug:
        fail("world slug is empty")
    w.ensure(display_name)
    staged = w.stage_input() if stage_input else []
    emit({"ok": True, "world": w.slug, "staged_files": staged, **w.state()})


@app.command()
def validate(
    room: Optional[Path] = typer.Option(None, "--room"),
    recipe: Optional[Path] = typer.Option(None, "--recipe"),
    annotations: Optional[Path] = typer.Option(None, "--annotations"),
    calibration: Optional[Path] = typer.Option(None, "--calibration"),
    image: Optional[Path] = typer.Option(None, "--image", help="image.json"),
) -> None:
    """Validate contract files; recipes are also expanded and size-checked."""
    from pydantic import ValidationError

    from room_gen import models
    from room_gen.build import BuildError, prepare_recipe

    checks = [(room, models.Room), (annotations, models.Annotations), (calibration, models.Calibration), (image, models.ImageAnalysis)]
    results = []
    ok = True
    for path, model in checks:
        if path is None:
            continue
        try:
            model.model_validate(read_json(path))
            results.append({"file": str(path), "ok": True})
        except (ValidationError, ValueError) as exc:
            ok = False
            results.append({"file": str(path), "ok": False, "errors": str(exc).splitlines()})
    if recipe is not None:
        try:
            rec, warnings = prepare_recipe(read_json(recipe))
            from room_gen.meshgen import recipe_bbox, recipe_face_count

            lo, hi = recipe_bbox(rec)
            results.append({"file": str(recipe), "ok": True, "parts": len(rec["parts"]), "faces": recipe_face_count(rec),
                            "size_m": [round(hi[i] - lo[i], 4) for i in range(3)], "warnings": warnings})
        except (ValidationError, ValueError, KeyError, BuildError) as exc:
            ok = False
            results.append({"file": str(recipe), "ok": False, "errors": str(exc).splitlines()})
    if not results:
        fail("nothing to validate; pass --room, --recipe, --annotations, --calibration or --image")
    emit({"ok": ok, "results": results}, code=0 if ok else 1)


@app.command()
def schemas(out: Path = typer.Option(Path("schemas"), "--out")) -> None:
    """Write JSON Schema files generated from the pydantic models."""
    from room_gen.models import SCHEMA_MODELS

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in SCHEMA_MODELS.items():
        path = out / f"{name}.schema.json"
        write_json(path, model.model_json_schema())
        written.append(str(path))
    emit({"ok": True, "written": written})


@app.command()
def build(
    world: str = typer.Option(..., "--world"),
    formats: Optional[str] = typer.Option(None, "--formats", help="Comma list: glb,fbx,obj,usd"),
    objects: Optional[str] = typer.Option(None, "--objects", help="Only these object ids."),
    force: bool = typer.Option(False, "--force", "--regenerate", help="Rebuild even if inputs are unchanged."),
    no_previews: bool = typer.Option(False, "--no-previews"),
) -> None:
    """Build shell, objects, lights and camera in Blender; export and render previews."""
    from room_gen.blender_exec import BlenderError
    from room_gen.build import BuildError
    from room_gen.build import build as do_build

    w = ws().world(world)
    try:
        res = do_build(w, formats=formats.split(",") if formats else None, objects_only=objects.split(",") if objects else None,
                       force=force, previews=not no_previews, blender=Ctx.blender)
    except (BuildError, BlenderError) as exc:
        fail(str(exc), log_tail=getattr(exc, "log_tail", "")[-1500:])
    emit({"ok": True, **res})


@app.command("export")
def export_cmd(
    world: str = typer.Option(..., "--world"),
    formats: str = typer.Option("glb,fbx,obj", "--formats"),
) -> None:
    """Rebuild the latest room into a new index with the requested export formats."""
    from room_gen.blender_exec import BlenderError
    from room_gen.build import BuildError
    from room_gen.build import build as do_build

    w = ws().world(world)
    try:
        res = do_build(w, formats=formats.split(","), force=True, blender=Ctx.blender)
    except (BuildError, BlenderError) as exc:
        fail(str(exc))
    emit({"ok": True, **res})


@app.command()
def bridge(
    world: Path = typer.Option(..., "--world", help="Path to an image-blaster worlds/<slug> directory."),
    out: Optional[str] = typer.Option(None, "--out", help="Slug of the world here that receives the files."),
    formats: str = typer.Option("glb", "--formats"),
) -> None:
    """Import an image-blaster world (collider, objects, scene.json, sun) into Blender."""
    from room_gen.blender_exec import BlenderError
    from room_gen.build import bridge as do_bridge

    target = ws().world(out or world.resolve().name)
    try:
        res = do_bridge(world, target, formats=formats.split(","), blender=Ctx.blender)
    except BlenderError as exc:
        fail(str(exc), log_tail=exc.log_tail[-1500:])
    emit({"ok": True, **res})


@app.command()
def inspect(file: Path = typer.Argument(..., help="A .glb/.fbx/.obj/.blend to re-import and summarise.")) -> None:
    """Re-import an exported file in Blender and report meshes, faces and bounds."""
    from room_gen.blender_exec import BlenderError, run_blender

    try:
        res = run_blender("inspect", {"path": str(file.resolve())}, config=ws().config, blender=Ctx.blender)
    except BlenderError as exc:
        fail(str(exc))
    emit({k: v for k, v in res.items() if k not in ("command",)})


@app.command()
def patch(
    room: Path = typer.Option(..., "--room"),
    ops: Path = typer.Option(..., "--ops", help="RFC 7386 merge patch JSON file."),
) -> None:
    """Apply a JSON merge patch to room.json (validated before writing)."""
    from pydantic import ValidationError

    from room_gen.models import Room
    from room_gen.patch import merge_patch
    from room_gen.sidecar import now_iso

    merged = merge_patch(read_json(room), read_json(ops))
    merged["updated_at"] = now_iso()
    try:
        Room.model_validate(merged)
    except ValidationError as exc:
        fail("patched room.json is invalid; nothing written", errors=str(exc).splitlines())
    write_json(room, merged)
    emit({"ok": True, "room": str(room)})


@app.command()
def path(
    world: str = typer.Option(..., "--world"),
    kind: str = typer.Option("world", "--kind", help="world | object"),
    slug: Optional[str] = typer.Option(None, "--slug"),
    ext: str = typer.Option(".glb", "--ext"),
    next_: bool = typer.Option(False, "--next", help="Path for the next index instead of the latest."),
) -> None:
    """Compute an indexed artifact path."""
    from room_gen.indexed import artifact_path, latest_indexed, next_index

    w = ws().world(world)
    directory = w.path("output", "world") if kind == "world" else w.object_dir(slug or "")
    family = slug or ("world" if kind == "world" else "")
    if next_:
        idx = next_index(directory, family)
    else:
        latest = latest_indexed(directory, family, {ext})
        if not latest:
            fail(f"no {family}{ext} artifact yet")
        idx = latest.index
    emit({"ok": True, "index": idx, "path": w.workspace_rel(artifact_path(directory, idx, family, ext))})


# ----- archetypes ---------------------------------------------------------------------------


@archetypes_app.command("list")
def archetypes_list() -> None:
    from room_gen import archetypes as A

    emit({"ok": True, "archetypes": [{"name": n, "category": A.get(n).category, "default_size": [A.get(n).defaults[k] for k in ("width", "depth", "height")],
                                      "synonyms": A.get(n).synonyms} for n in A.names()]})


@archetypes_app.command("show")
def archetypes_show(name: str) -> None:
    from room_gen import archetypes as A

    try:
        emit({"ok": True, **A.describe(name)})
    except KeyError as exc:
        fail(str(exc))


@archetypes_app.command("resolve")
def archetypes_resolve(label: str) -> None:
    from room_gen import archetypes as A

    name, matched = A.resolve(label)
    emit({"ok": True, "label": label, "archetype": name, "matched": matched})


@archetypes_app.command("expand")
def archetypes_expand(recipe: Path, write: bool = typer.Option(False, "--write", help="Write the expanded recipe back.")) -> None:
    from room_gen.build import prepare_recipe

    rec, warnings = prepare_recipe(read_json(recipe))
    if write:
        write_json(recipe, rec)
    emit({"ok": True, "parts": len(rec["parts"]), "bbox_m": rec.get("bbox_m"), "warnings": warnings, **({} if write else {"recipe": rec})})


# ----- models -------------------------------------------------------------------------------


@models_app.command("list")
def models_list() -> None:
    from room_gen.ml import runtime

    emit({"ok": True, **runtime.status(ws().config)})


@models_app.command("check")
def models_check() -> None:
    from room_gen.ml import runtime

    st = runtime.status(ws().config)
    emit({"ok": st["installed"], **st}, code=0 if st["installed"] else 1)


@models_app.command("download")
def models_download() -> None:
    from room_gen.ml import runtime

    try:
        res = runtime.download(ws().config)
    except RuntimeError as exc:
        fail(str(exc))
    emit({"ok": True, **res})


def main() -> None:
    from room_gen import cli_vision  # noqa: F401 - registers the vision commands

    app()


if __name__ == "__main__":
    main()
