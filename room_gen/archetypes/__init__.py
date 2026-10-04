"""Parametric furniture archetypes and their expansion into recipe parts.

``expand(recipe)`` turns the archetype level of a recipe (what people and Claude write)
into the parts level (what Blender builds), deterministically.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from room_gen.archetypes import beds, lighting, misc, seating, storage, tables
from room_gen.archetypes._dsl import MAT, Archetype

_ALL: list[Archetype] = [*seating.ARCHETYPES, *tables.ARCHETYPES, *storage.ARCHETYPES, *beds.ARCHETYPES, *lighting.ARCHETYPES, *misc.ARCHETYPES]
REGISTRY: dict[str, Archetype] = {a.name: a for a in _ALL}
FALLBACK = "generic_box"


def names() -> list[str]:
    return sorted(REGISTRY)


def get(name: str) -> Archetype:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown archetype {name!r}; known: {', '.join(names())}") from None


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def _synonym_table() -> list[tuple[str, str]]:
    pairs = []
    for arch in _ALL:
        pairs.append((" ".join(_words(arch.name)), arch.name))
        for syn in arch.synonyms:
            pairs.append((" ".join(_words(syn)), arch.name))
    # longest phrases first so "coffee table" beats "table"
    pairs.sort(key=lambda p: (-len(p[0].split()), -len(p[0])))
    return pairs


_SYNONYMS = _synonym_table()


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("ches") or word.endswith("shes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def resolve(label: str | None) -> tuple[str, bool]:
    """Map a free-text label to an archetype name. Returns (name, matched)."""
    if not label:
        return FALLBACK, False
    words = _words(label)
    text = " " + " ".join(words) + " "
    text_singular = " " + " ".join(_singular(w) for w in words) + " "
    if label.lower().strip().replace(" ", "_") in REGISTRY:
        return label.lower().strip().replace(" ", "_"), True
    for phrase, name in _SYNONYMS:
        needle = f" {phrase} "
        if needle in text or needle in text_singular:
            return name, name != FALLBACK
    return FALLBACK, False


def vocabulary() -> list[str]:
    """Prompt phrases for open-vocabulary detection: one or two per archetype."""
    vocab = []
    for arch in _ALL:
        if arch.name == FALLBACK:
            continue
        vocab.append(arch.name.replace("_", " "))
    return vocab


def _clamp_params(arch: Archetype, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings = []
    out = dict(params)
    for key, (lo, hi) in arch.ranges.items():
        if key in out and isinstance(out[key], (int, float)) and not isinstance(out[key], bool):
            v = float(out[key])
            if v < lo or v > hi:
                warnings.append(f"{arch.name}.{key}={v:.3f} clamped to [{lo}, {hi}]")
                v = min(max(v, lo), hi)
            out[key] = int(round(v)) if isinstance(arch.defaults.get(key), int) and not isinstance(arch.defaults.get(key), bool) else v
    return out, warnings


def default_materials(arch: Archetype) -> dict[str, dict]:
    return copy.deepcopy(arch.materials)


def expand(recipe: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fill params, materials, parts and bbox from the archetype. Returns (recipe, warnings).

    Hand-written parts (``provenance.parts_by`` other than ``"archetype"``) are kept.
    """
    out = copy.deepcopy(recipe)
    name = out.get("archetype")
    prov = dict(out.get("provenance") or {})
    if not name:
        return out, []
    if out.get("parts") and prov.get("parts_by") not in (None, "archetype"):
        return out, []
    arch = get(name)
    params = {**arch.defaults, **(out.get("params") or {})}
    params, warnings = _clamp_params(arch, params)
    parts = arch.build(params)
    materials = default_materials(arch)
    for slot, spec in (out.get("materials") or {}).items():
        materials[slot] = {**materials.get(slot, {}), **spec}
    out.update(
        params=params,
        parts=parts,
        materials=materials,
        bbox_m=[float(params["width"]), float(params["depth"]), float(params["height"])],
        origin="bottom_center",
    )
    prov["parts_by"] = "archetype"
    out["provenance"] = prov
    out.setdefault("modifiers", [])
    return out, warnings


def describe(name: str) -> dict[str, Any]:
    arch = get(name)
    return {
        "name": arch.name,
        "category": arch.category,
        "description": arch.description,
        "defaults": arch.defaults,
        "ranges": {k: list(v) for k, v in arch.ranges.items()},
        "material_slots": {k: v.get("base_color") for k, v in arch.materials.items()},
        "synonyms": arch.synonyms,
        "support": arch.support,
        "against_wall": arch.against_wall,
    }


__all__ = ["REGISTRY", "FALLBACK", "MAT", "names", "get", "resolve", "expand", "describe", "vocabulary"]
