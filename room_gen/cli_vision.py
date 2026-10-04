"""Pipeline commands (registered on the main typer app)."""

from __future__ import annotations

from typing import Optional

import typer

from room_gen.cli import Ctx, app, emit, fail, ws


@app.command()
def auto(
    world: str = typer.Option(..., "--world"),
    ml: Optional[str] = typer.Option(None, "--ml", help="auto | on | off (default from config: auto)"),
    device: Optional[str] = typer.Option(None, "--device", help="cpu | cuda | mps"),
    no_fit: bool = typer.Option(False, "--no-fit"),
    no_textures: bool = typer.Option(False, "--no-textures"),
    build: bool = typer.Option(False, "--build", help="Run `build` afterwards."),
) -> None:
    """Photo -> annotations, calibration, room.json and recipes without any language model."""
    from room_gen.pipeline import run_auto

    w = ws().world(world)
    try:
        res = run_auto(w, ml_mode=ml, device=device, fit=False if no_fit else None, textures=False if no_textures else None)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        fail(str(exc))
    if build:
        from room_gen.blender_exec import BlenderError
        from room_gen.build import BuildError
        from room_gen.build import build as do_build

        try:
            res["build"] = do_build(w, blender=Ctx.blender)
        except (BuildError, BlenderError) as exc:
            fail(str(exc), auto=res)
    emit({"ok": True, **res})


@app.command()
def annotate(
    world: str = typer.Option(..., "--world"),
    port: int = typer.Option(5174, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Serve the web annotator for a world (http://127.0.0.1:5174/#/<world>)."""
    import threading
    import webbrowser

    import uvicorn

    from room_gen.server import DIST, create_app

    w = ws().world(world)
    if not w.dir.is_dir():
        fail(f"world {world!r} does not exist; run `room_gen project --world {world} --stage-input` first")
    if not (DIST / "index.html").is_file():
        fail("annotator not built: cd annotator && npm install && npm run build")
    url = f"http://{host}:{port}/#/{w.slug}"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"annotator at {url}", flush=True)
    uvicorn.run(create_app(Ctx.root, Ctx.config), host=host, port=port, log_level="warning")


@app.command()
def grid(
    world: str = typer.Option(..., "--world"),
    long_side: int = typer.Option(1568, "--long-side", help="Long side of the written image (vision-friendly)."),
    divisions: int = typer.Option(10, "--divisions"),
) -> None:
    """Write the photo with a labelled pixel grid (native coordinates) for reading positions off it."""
    import cv2
    import numpy as np

    from room_gen.vision.imageio import load_photo, save_rgb

    w = ws().world(world)
    img_path = w.primary_image()
    if img_path is None:
        fail("no source image")
    photo = load_photo(img_path)
    W, H = photo.size
    s = min(1.0, long_side / max(W, H))
    small = cv2.resize(photo.rgb, (int(round(W * s)), int(round(H * s))), interpolation=cv2.INTER_AREA)
    raw = max(W, H) / divisions
    mag = 10 ** int(np.floor(np.log10(raw)))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10)), key=lambda v: abs(v - raw))
    out = small.copy()
    font, scale_txt = cv2.FONT_HERSHEY_SIMPLEX, 0.45 * max(1.0, max(small.shape) / 1000)
    for x in np.arange(0, W + 1e-6, step):
        u = int(round(x * s))
        cv2.line(out, (u, 0), (u, out.shape[0] - 1), (255, 0, 255), 1, cv2.LINE_AA)
        cv2.putText(out, str(int(x)), (u + 2, 14), font, scale_txt, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(out, str(int(x)), (u + 2, 14), font, scale_txt, (200, 0, 200), 1, cv2.LINE_AA)
    for y in np.arange(0, H + 1e-6, step):
        v = int(round(y * s))
        cv2.line(out, (0, v), (out.shape[1] - 1, v), (0, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(out, str(int(y)), (2, v - 3), font, scale_txt, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(out, str(int(y)), (2, v - 3), font, scale_txt, (0, 120, 200), 1, cv2.LINE_AA)
    path = save_rgb(w.path("output", "world", "grid.png"), out)
    emit({"ok": True, "grid_image": w.workspace_rel(path), "native_size": [W, H], "grid_step_px": step,
          "note": "labels are native pixel coordinates; write annotations in native pixels"})
