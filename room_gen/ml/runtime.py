"""Device selection, availability and cache management for the optional models."""

from __future__ import annotations

import importlib.util
from typing import Any

ROLES = ("depth_model", "detect_model", "segment_model", "caption_model")


def installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers"))


def pick_device(preference: str = "auto") -> str:
    import torch

    if preference not in ("auto", None):
        return preference
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _cached(repo_id: str) -> bool:
    try:
        from huggingface_hub import scan_cache_dir

        return any(r.repo_id == repo_id for r in scan_cache_dir().repos)
    except Exception:  # noqa: BLE001 - cache may not exist yet
        return False


def status(config: dict) -> dict[str, Any]:
    ml = config.get("ml", {})
    out: dict[str, Any] = {"installed": installed(), "mode": ml.get("mode", "auto"), "models": {}}
    if not out["installed"]:
        out["hint"] = "uv sync --extra ml  (or: pip install 'room-gen[ml]')"
        return out
    import torch

    out["torch"] = torch.__version__
    out["device"] = pick_device(ml.get("device", "auto"))
    if out["device"] == "cuda":
        out["gpu"] = torch.cuda.get_device_name(0)
    for role in ROLES:
        repo = ml.get(role)
        if repo:
            out["models"][role.replace("_model", "")] = {"id": repo, "cached": _cached(repo)}
    return out


def enabled(config: dict, override: str | None = None) -> bool:
    mode = override or config.get("ml", {}).get("mode", "auto")
    if mode == "off":
        return False
    if mode == "on" and not installed():
        raise RuntimeError("--ml on requested but torch/transformers are not installed (uv sync --extra ml)")
    return installed()


def download(config: dict) -> dict[str, Any]:
    if not installed():
        raise RuntimeError("install the extra first: uv sync --extra ml")
    from huggingface_hub import snapshot_download

    got = {}
    for role in ROLES:
        repo = config.get("ml", {}).get(role)
        if repo:
            got[role.replace("_model", "")] = snapshot_download(repo, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"])
    return {"downloaded": got}


_CACHE: dict[str, Any] = {}


def load(kind: str, repo: str, device: str):
    """Load (processor, model) once per process. fp16 on GPU except for depth (NaNs in fp16)."""
    key = f"{kind}:{repo}:{device}"
    if key in _CACHE:
        return _CACHE[key]
    import torch
    import transformers as T

    half = device != "cpu" and kind != "depth"
    dtype = torch.float16 if half else torch.float32
    def pretrained(cls, repo_id):
        try:  # transformers >= 4.56 uses `dtype`; older releases only know `torch_dtype`
            return cls.from_pretrained(repo_id, dtype=dtype)
        except TypeError:
            return cls.from_pretrained(repo_id, torch_dtype=dtype)

    if kind == "depth":
        proc = T.AutoImageProcessor.from_pretrained(repo)
        model = pretrained(T.AutoModelForDepthEstimation, repo)
    elif kind == "detect":
        if "owl" in repo.lower():
            proc = T.Owlv2Processor.from_pretrained(repo)
            model = pretrained(T.Owlv2ForObjectDetection, repo)
        else:
            proc = T.AutoProcessor.from_pretrained(repo)
            model = pretrained(T.AutoModelForZeroShotObjectDetection, repo)
    elif kind == "segment":
        proc = T.SamProcessor.from_pretrained(repo)
        model = pretrained(T.SamModel, repo)
    else:
        raise ValueError(kind)
    model = model.to(device).eval()
    _CACHE[key] = (proc, model, dtype)
    return _CACHE[key]


def describe(kind: str, repo: str, device: str) -> dict:
    return {"kind": kind, "id": repo, "device": device}
