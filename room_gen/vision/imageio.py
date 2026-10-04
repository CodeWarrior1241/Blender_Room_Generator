"""Photo loading with EXIF orientation applied, working-resolution copies, saving."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from room_gen.exif import read_exif

try:  # optional HEIC support
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass


@dataclass
class Photo:
    path: Path
    rgb: np.ndarray  # H x W x 3 uint8, orientation applied
    exif: dict = field(default_factory=dict)

    @property
    def width(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def height(self) -> int:
        return int(self.rgb.shape[0])

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def working(self, long_side: int = 1024) -> tuple[np.ndarray, float]:
        """Downscaled RGB copy and the scale factor (working = native * s)."""
        s = min(1.0, long_side / max(self.width, self.height))
        if s >= 0.999:
            return self.rgb.copy(), 1.0
        w, h = int(round(self.width * s)), int(round(self.height * s))
        small = cv2.resize(self.rgb, (w, h), interpolation=cv2.INTER_AREA)
        return small, w / self.width


def load_photo(path: str | Path) -> Photo:
    path = Path(path)
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        rgb = np.asarray(img.convert("RGB")).copy()
    return Photo(path, rgb, read_exif(path))


def to_gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def save_rgb(path: str | Path, rgb: np.ndarray, quality: int = 92) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if path.suffix.lower() in (".jpg", ".jpeg") else []
    if not cv2.imwrite(str(path), bgr, params):
        raise OSError(f"could not write {path}")
    return path
