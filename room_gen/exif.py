"""EXIF facts that matter for calibration (focal length, orientation, camera model)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_EXIF_IFD = 0x8769
_TAGS = {"make": 0x010F, "model": 0x0110, "orientation": 0x0112}
_EXIF_TAGS = {"focal_mm": 0x920A, "focal_35mm": 0xA405}


def read_exif(path: str | Path) -> dict:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            out: dict = {}
            for key, tag in _TAGS.items():
                if tag in exif:
                    out[key] = exif[tag]
            sub = exif.get_ifd(_EXIF_IFD) if exif else {}
            for key, tag in _EXIF_TAGS.items():
                if tag in sub:
                    out[key] = float(sub[tag])
    except (OSError, ValueError):
        return {}
    for key in ("make", "model"):
        if key in out:
            out[key] = str(out[key]).strip("\x00 ").strip()
    if "orientation" in out:
        out["orientation"] = int(out["orientation"])
    return {k: v for k, v in out.items() if v not in (None, "", 0, 0.0)}


def focal_px_from_exif(exif: dict, width: int, height: int) -> float | None:
    """Focal length in pixels from the 35 mm-equivalent focal (36 mm-wide film, long side)."""
    f35 = exif.get("focal_35mm")
    if not f35:
        return None
    return float(f35) / 36.0 * max(width, height)
