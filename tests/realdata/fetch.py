"""Fetch the reference data for tests/realdata into deps/sunrgbd (research use only).

Two official sources, each contacted gently:
- SUN RGB-D (Princeton): only the 14.5 MB annotation file, read out of SUNRGBDtoolbox.zip with a
  handful of paced HTTP range requests.
- NYU Depth v2 (NYU): the labelled set, one resumable 3 GB download. It provides the photos
  (cropped exactly as SUN RGB-D crops them) and the scene types used for selection.

    uv sync --extra realdata
    uv run python -m tests.realdata.fetch --accept-license              # data for nyu_subset.json
    uv run python -m tests.realdata.fetch --accept-license --select 40  # rebuild nyu_subset.json
"""

from __future__ import annotations

import argparse
import getpass
import http.client
import io
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "deps" / "sunrgbd"
SUBSET = Path(__file__).resolve().parent / "nyu_subset.json"
TOOLBOX_URL = "https://rgbd.cs.princeton.edu/data/SUNRGBDtoolbox.zip"
META_MEMBER = "SUNRGBDtoolbox/Metadata/SUNRGBDMeta.mat"
NYU_URL = "https://horatio.cs.nyu.edu/mit/silberman/nyu_depth_v2/nyu_depth_v2_labeled.mat"
NYU_FILE = DATA / "nyu_depth_v2_labeled.mat"
NYU_SIZE = 2972037809
UA = {"User-Agent": "room-gen-tests/0.1 (research use)"}
# SUN RGB-D uses the valid region of the 640 x 480 Kinect frame: rows 45..471, cols 41..601 (1-based)
CROP = (slice(44, 471), slice(40, 601))


class RangeClient:
    """HTTP range reader that is easy on the server: one kept-alive connection, a pause
    between requests, and it gives up (instead of retrying hard) when refused."""

    def __init__(self, url: str, pause: float = 1.0, attempts: int = 3):
        u = urllib.parse.urlsplit(url)
        self.host, self.path, self.pause, self.attempts = u.netloc, u.path, pause, attempts
        self.conn: http.client.HTTPSConnection | None = None
        self.requests = 0
        self.size = int(self._request("HEAD")[1]["Content-Length"])

    def _request(self, method: str, start: int | None = None, end: int | None = None):
        headers = dict(UA)
        if start is not None:
            headers["Range"] = f"bytes={start}-{end}"
        for attempt in range(self.attempts):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPSConnection(self.host, timeout=120)
                self.conn.request(method, self.path, headers=headers)
                r = self.conn.getresponse()
                body = r.read()
                if r.status not in (200, 206):
                    raise OSError(f"HTTP {r.status}")
                self.requests += 1
                time.sleep(self.pause)
                return body, r.headers
            except (OSError, http.client.HTTPException) as exc:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None
                if attempt == self.attempts - 1:
                    raise SystemExit(f"{self.host} refused the request ({exc}). It may be rate-limiting; "
                                     "try again later rather than retrying in a loop.") from exc
                time.sleep(10 * (attempt + 1))
        raise RuntimeError("unreachable")

    def get(self, start: int, end: int) -> bytes:
        return self._request("GET", start, end)[0]


class HTTPRangeFile(io.RawIOBase):
    """Seekable read-only file over a RangeClient (enough for zipfile)."""

    def __init__(self, url: str):
        self.client = RangeClient(url)
        self.size, self.pos = self.client.size, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self.pos = {io.SEEK_SET: offset, io.SEEK_CUR: self.pos + offset, io.SEEK_END: self.size + offset}[whence]
        return self.pos

    def readinto(self, buffer) -> int:
        n = min(len(buffer), self.size - self.pos)
        if n <= 0:
            return 0
        data = self.client.get(self.pos, self.pos + n - 1)
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


def accept_license(flag: bool) -> None:
    marker = DATA / "LICENSE_ACCEPTED"
    if marker.is_file():
        return
    if not flag:
        sys.exit("SUN RGB-D and NYU Depth v2 are licensed for research use only.\n"
                 "Re-run with --accept-license to confirm this is a research use. See deps/sunrgbd/README.md.")
    DATA.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "by": getpass.getuser(),
                                  "terms": "research use only (https://rgbd.cs.princeton.edu/, https://cs.nyu.edu/~fergus/datasets/nyu_depth_v2.html)"},
                                 indent=2) + "\n")


def fetch_metadata() -> Path:
    out = DATA / "Metadata" / "SUNRGBDMeta.mat"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = HTTPRangeFile(TOOLBOX_URL)
    with zipfile.ZipFile(io.BufferedReader(raw, buffer_size=1 << 20)) as zf, zf.open(META_MEMBER) as src:
        out.write_bytes(src.read())
    print(f"SUN RGB-D metadata: {out.stat().st_size / 1e6:.1f} MB in {raw.client.requests} requests", flush=True)
    return out


def fetch_nyu() -> Path:
    """Resumable single download of the NYU labelled set."""
    have = NYU_FILE.stat().st_size if NYU_FILE.is_file() else 0
    if have == NYU_SIZE:
        return NYU_FILE
    NYU_FILE.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading NYU Depth v2 labelled set ({NYU_SIZE / 1e9:.2f} GB, resuming at {have / 1e9:.2f} GB)", flush=True)
    req = urllib.request.Request(NYU_URL, headers={**UA, **({"Range": f"bytes={have}-"} if have else {})})
    with urllib.request.urlopen(req, timeout=120) as r, open(NYU_FILE, "ab" if have else "wb") as f:
        while chunk := r.read(1 << 22):
            f.write(chunk)
    if NYU_FILE.stat().st_size != NYU_SIZE:
        raise SystemExit("NYU download incomplete; run the command again to resume")
    return NYU_FILE


class NYULabeled:
    """Images and scene types from nyu_depth_v2_labeled.mat (MATLAB v7.3 / HDF5)."""

    def __init__(self, path: Path):
        import h5py

        self.f = h5py.File(path, "r")
        self.images = self.f["images"]  # (1449, 3, 640, 480)
        self._scenes = None

    def scene(self, number: int) -> str:
        if self._scenes is None:
            refs = self.f["sceneTypes"][0]
            self._scenes = ["".join(chr(c) for c in self.f[r][:].flatten()) for r in refs]
        return self._scenes[number - 1]

    def image(self, number: int):
        """RGB crop (427 x 561) of frame NYU<number>, as used by SUN RGB-D."""
        rgb = self.images[number - 1].transpose(2, 1, 0)  # -> (480, 640, 3)
        return rgb[CROP]


def nyu_number(frame_id: str) -> int:
    return int(frame_id.replace("NYU", ""))


def fetch_frames(frames: list[dict], nyu: NYULabeled) -> int:
    from PIL import Image

    got = 0
    for fr in frames:
        dest = DATA / "nyu" / fr["id"]
        dest.mkdir(parents=True, exist_ok=True)
        n = nyu_number(fr["id"])
        if not (dest / "image.jpg").is_file():
            Image.fromarray(nyu.image(n)).save(dest / "image.jpg", quality=95)
            got += 1
        if not (dest / "scene.txt").is_file():
            (dest / "scene.txt").write_text(nyu.scene(n) + "\n")
    return got


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accept-license", action="store_true")
    ap.add_argument("--select", type=int, default=0, help="rebuild tests/realdata/nyu_subset.json with N frames")
    args = ap.parse_args()
    accept_license(args.accept_license)
    from tests.realdata import sunrgbd

    meta = sunrgbd.load_meta(fetch_metadata())
    nyu = NYULabeled(fetch_nyu())
    if args.select:
        sunrgbd.select_subset(meta, nyu, args.select, SUBSET)
    subset = json.loads(SUBSET.read_text())
    frames = [sunrgbd.frame_record(meta, f["index"]) for f in subset["frames"]]
    n = fetch_frames(frames, nyu)
    for fr in frames:
        sunrgbd.write_truth(meta[fr["index"]], DATA / "nyu" / fr["id"])
    print(f"{len(frames)} frames ready in {DATA / 'nyu'} ({n} images written)", flush=True)


if __name__ == "__main__":
    main()
