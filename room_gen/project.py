"""Workspace and world-directory management (parity with image-blaster's project-state.mjs)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from room_gen.config import load_config
from room_gen.indexed import artifact_path, is_visible, latest_indexed, parse_indexed_name, slugify
from room_gen.jsonio import read_json_if_exists, write_json

IMAGE_EXTENSIONS = {".avif", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"}
MODEL_EXTENSIONS = {".glb", ".obj", ".fbx", ".usdz", ".blend"}
PROJECT_DIRS = ("source", "output", "output/world")
RESERVED_OUTPUT_DIRS = {"world", "sfx"}


@dataclass
class Workspace:
    root: Path
    config: dict[str, Any]

    @classmethod
    def open(cls, root: str | Path = ".", config_path: str | Path | None = None) -> "Workspace":
        root = Path(root).resolve()
        return cls(root, load_config(root, config_path))

    @property
    def worlds_dir(self) -> Path:
        return self.root / self.config.get("worlds_dir", "worlds")

    @property
    def input_dir(self) -> Path:
        return self.root / self.config.get("input_dir", "input")

    def world(self, slug: str) -> "World":
        return World(self, slugify(slug))

    def worlds(self) -> list[str]:
        if not self.worlds_dir.is_dir():
            return []
        return sorted(p.name for p in self.worlds_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


@dataclass
class World:
    ws: Workspace
    slug: str

    @property
    def dir(self) -> Path:
        return self.ws.worlds_dir / self.slug

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def rel(self, path: str | Path) -> str:
        """World-relative POSIX path (how JSON files reference other files)."""
        path = Path(path).resolve()
        try:
            return path.relative_to(self.dir.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def resolve(self, ref: str) -> Path:
        """Resolve a path stored in JSON: world-relative, workspace-relative, or absolute."""
        p = Path(ref)
        if p.is_absolute():
            return p
        if (self.dir / p).exists():
            return self.dir / p
        if (self.ws.root / p).exists():
            return self.ws.root / p
        prefix = f"{self.ws.config.get('worlds_dir', 'worlds')}/{self.slug}/"
        if ref.startswith(prefix):
            return self.dir / ref[len(prefix) :]
        return self.dir / p

    def workspace_rel(self, path: str | Path) -> str:
        path = Path(path).resolve()
        try:
            return path.relative_to(self.ws.root).as_posix()
        except ValueError:
            return path.as_posix()

    # ----- well-known files --------------------------------------------------------------
    @property
    def annotations_path(self) -> Path:
        return self.path("annotations.json")

    @property
    def calibration_path(self) -> Path:
        return self.path("calibration.json")

    @property
    def room_path(self) -> Path:
        return self.path("room.json")

    @property
    def image_json_path(self) -> Path:
        return self.path("image.json")

    @property
    def scene_path(self) -> Path:
        return self.path("scene.json")

    def object_dir(self, object_id: str) -> Path:
        return self.path("output", object_id)

    def source_images(self) -> list[Path]:
        src = self.path("source")
        if not src.is_dir():
            return []
        return sorted(p for p in src.iterdir() if p.is_file() and is_visible(p) and p.suffix.lower() in IMAGE_EXTENSIONS)

    def primary_image(self) -> Path | None:
        """Highest-index visible source image (image-blaster's default source)."""
        latest = latest_indexed(self.path("source"), extensions=IMAGE_EXTENSIONS)
        if latest:
            return self.path("source", latest.name)
        images = self.source_images()
        return images[-1] if images else None

    def ensure(self, display_name: str | None = None) -> dict:
        for d in PROJECT_DIRS:
            self.path(d).mkdir(parents=True, exist_ok=True)
        project_path = self.path("project.json")
        existing = read_json_if_exists(project_path) or {}
        project = {
            "schema_version": 1,
            "slug": self.slug,
            "display_name": display_name or existing.get("display_name") or " ".join(w.capitalize() for w in self.slug.split("-") if w),
            "created_at": existing.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if existing.get("notes"):
            project["notes"] = existing["notes"]
        write_json(project_path, project)
        return project

    def stage_input(self) -> list[dict]:
        """Move images from the workspace input/ into source/ as index-0 files."""
        staged = []
        inp = self.ws.input_dir
        if not inp.is_dir():
            return staged
        src = self.path("source")
        src.mkdir(parents=True, exist_ok=True)
        for f in sorted(inp.iterdir()):
            if not f.is_file() or f.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            parsed = parse_indexed_name(f.name)
            name = f.name if parsed and parsed.index == 0 else artifact_path(src, 0, slugify(f.stem) or "image", f.suffix.lower()).name
            target = src / name
            k = 1
            while target.exists():
                target = src / f"{Path(name).stem}-{k}{Path(name).suffix}"
                k += 1
            f.rename(target)
            staged.append({"from": f"{self.ws.config.get('input_dir', 'input')}/{f.name}", "to": self.workspace_rel(target)})
        return staged

    def objects(self) -> list[dict]:
        out = []
        out_dir = self.path("output")
        if not out_dir.is_dir():
            return out
        for d in sorted(out_dir.iterdir()):
            if not d.is_dir() or d.name in RESERVED_OUTPUT_DIRS or d.name.startswith("."):
                continue
            has_object = (d / "object.json").is_file()
            has_recipe = (d / "recipe.json").is_file()
            if not (has_object or has_recipe):
                continue
            model = latest_indexed(d, extensions={".glb"})
            out.append({
                "id": d.name,
                "has_object_json": has_object,
                "has_recipe": has_recipe,
                "latest_model": self.workspace_rel(d / model.name) if model else None,
                "status": "completed" if model else "pending",
            })
        return out

    def state(self) -> dict:
        world_dir = self.path("output", "world")
        latest_world = latest_indexed(world_dir, "world", {".json"})
        latest_room = latest_indexed(world_dir, "world-room", {".blend", ".glb"})
        objects = self.objects()
        primary = self.primary_image()
        return {
            "project": read_json_if_exists(self.path("project.json")),
            "paths": {
                "root": self.workspace_rel(self.dir),
                "source": self.workspace_rel(self.path("source")),
                "output": self.workspace_rel(self.path("output")),
                "world": self.workspace_rel(world_dir),
            },
            "state": {
                "source_image_count": len(self.source_images()),
                "primary_image": self.workspace_rel(primary) if primary else None,
                "has_image_json": self.image_json_path.is_file(),
                "has_annotations": self.annotations_path.is_file(),
                "has_calibration": self.calibration_path.is_file(),
                "has_room": self.room_path.is_file(),
                "has_scene": self.scene_path.is_file(),
                "latest_world_index": latest_world.index if latest_world else None,
                "latest_room_index": latest_room.index if latest_room else None,
                "object_count": len(objects),
                "objects_built": sum(1 for o in objects if o["status"] == "completed"),
            },
            "objects": objects,
        }
