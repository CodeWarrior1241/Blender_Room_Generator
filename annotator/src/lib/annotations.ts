// Pure reducer over the annotations.json document plus an undo/redo history.
// Every object, opening or boundary line created or edited here is stamped with HUMAN_PROVENANCE, and so is the
// document itself; the auto pipeline keeps human blocks and regenerates only auto/fit ones.

import type {
  Annotations,
  BoundaryLine,
  KnownLength,
  ObjectAnnotation,
  OpeningAnnotation,
  ParallelPair,
  Provenance,
  Reference, WallHint} from '../types/annotations';
import {
  type Box,
  type Line,
  type Quad,
  type Vec2,
  normalizeBox,
  normalizeBoxArray,
  oppositeCorner,
  roundPt,
  translateBox,
  translatePoint,
} from './geometry';
import { isValidId, slugify, uniqueId } from './slug';

export const HUMAN_PROVENANCE: Readonly<Required<Provenance>> = Object.freeze({
  by: 'human',
  tool: 'annotator',
  confidence: 0.9,
});

export function humanProvenance(): Provenance {
  return { ...HUMAN_PROVENANCE };
}

export type Axis = ParallelPair['axis'];
export type OpeningKind = OpeningAnnotation['kind'];
export const WALL_HINTS = ['left', 'right', 'back', 'front'] as const;
export type BoundaryKind = BoundaryLine['kind'];
export const BOUNDARY_KINDS: readonly BoundaryKind[] = ['wall_floor', 'wall_ceiling', 'wall_wall'];
export const BOUNDARY_LABEL: Readonly<Record<BoundaryKind, string>> = {
  wall_floor: 'wall / floor',
  wall_ceiling: 'wall / ceiling',
  wall_wall: 'corner (wall / wall)',
};

// ------------------------------------------------------------------------------------------
// Item references (selection, handles, validation errors)
// ------------------------------------------------------------------------------------------

export type IndexedKind =
  | 'object'
  | 'opening'
  | 'floor_corner'
  | 'known_length'
  | 'parallel_pair'
  | 'vertical_line'
  | 'boundary_line';
export type ItemKind = IndexedKind | 'reference';
export type ItemRef = { kind: IndexedKind; index: number } | { kind: 'reference'; index?: undefined };

export function refKey(ref: ItemRef): string {
  return ref.kind === 'reference' ? 'reference' : `${ref.kind}:${ref.index}`;
}

export function sameRef(a: ItemRef | null | undefined, b: ItemRef | null | undefined): boolean {
  return !!a && !!b && a.kind === b.kind && a.index === b.index;
}

// Accessors that tolerate the optional arrays of the generated type.
export const objectsOf = (d: Annotations): ObjectAnnotation[] => d.objects ?? [];
export const openingsOf = (d: Annotations): OpeningAnnotation[] => d.openings ?? [];
export const cornersOf = (d: Annotations): Vec2[] => (d.floor_corners ?? []) as Vec2[];
export const lengthsOf = (d: Annotations): KnownLength[] => d.known_lengths ?? [];
export const pairsOf = (d: Annotations): ParallelPair[] => d.calibration?.parallel_pairs ?? [];
export const verticalsOf = (d: Annotations): Line[] => (d.calibration?.vertical_lines ?? []) as Line[];
export const referenceOf = (d: Annotations): Reference | null => d.calibration?.reference ?? null;
export const boundariesOf = (d: Annotations): BoundaryLine[] => d.boundary_lines ?? [];

export function itemExists(doc: Annotations, ref: ItemRef): boolean {
  switch (ref.kind) {
    case 'object':
      return ref.index < objectsOf(doc).length;
    case 'opening':
      return ref.index < openingsOf(doc).length;
    case 'floor_corner':
      return ref.index < cornersOf(doc).length;
    case 'known_length':
      return ref.index < lengthsOf(doc).length;
    case 'parallel_pair':
      return ref.index < pairsOf(doc).length;
    case 'vertical_line':
      return ref.index < verticalsOf(doc).length;
    case 'boundary_line':
      return ref.index < boundariesOf(doc).length;
    case 'reference':
      return referenceOf(doc) !== null;
  }
}

export function describeRef(doc: Annotations, ref: ItemRef): string {
  switch (ref.kind) {
    case 'object': {
      const o = objectsOf(doc)[ref.index];
      return o ? `object "${o.id}"` : `object #${ref.index + 1}`;
    }
    case 'opening': {
      const o = openingsOf(doc)[ref.index];
      return `opening #${ref.index + 1}${o ? ` (${o.kind}${o.label ? `, ${o.label}` : ''})` : ''}`;
    }
    case 'floor_corner':
      return `floor corner #${ref.index + 1}`;
    case 'known_length':
      return `known length #${ref.index + 1}`;
    case 'parallel_pair': {
      const p = pairsOf(doc)[ref.index];
      return `calibration pair #${ref.index + 1}${p ? ` (${p.axis})` : ''}`;
    }
    case 'vertical_line':
      return `vertical line #${ref.index + 1}`;
    case 'boundary_line': {
      const b = boundariesOf(doc)[ref.index];
      return `boundary line #${ref.index + 1}${b ? ` (${BOUNDARY_LABEL[b.kind] ?? b.kind})` : ''}`;
    }
    case 'reference':
      return 'reference';
  }
}

/** True when the block was produced by the automatic pass (drawn dashed in the UI). */
export function isAuto(p: Provenance | undefined): boolean {
  return (p?.by ?? 'auto') === 'auto' || p?.by === 'fit';
}

/** Fill the optional arrays so the editor never has to special-case missing keys. */
export function normalizeDoc(doc: Annotations): Annotations {
  const cal = doc.calibration ?? {};
  return {
    ...doc,
    schema_version: 1,
    calibration: { ...cal, parallel_pairs: cal.parallel_pairs ?? [], vertical_lines: cal.vertical_lines ?? [] },
    floor_corners: doc.floor_corners ?? [],
    objects: doc.objects ?? [],
    openings: doc.openings ?? [],
    known_lengths: doc.known_lengths ?? [],
    boundary_lines: doc.boundary_lines ?? [],
    notes: doc.notes ?? [],
  };
}

// ------------------------------------------------------------------------------------------
// Edits
// ------------------------------------------------------------------------------------------

export interface NewObject {
  label: string;
  box: Box;
  id?: string;
  support?: string;
  archetype?: string | null;
  params?: Record<string, unknown>;
  materials_hint?: string[];
}

export interface NewOpening {
  kind: OpeningKind;
  quad: Quad;
  wall_hint?: string | null;
  label?: string;
}

export type EditAction =
  | { type: 'addObject'; object: NewObject }
  | { type: 'updateObject'; index: number; patch: Partial<Omit<ObjectAnnotation, 'provenance'>> }
  | { type: 'addOpening'; opening: NewOpening }
  | { type: 'updateOpening'; index: number; patch: Partial<Omit<OpeningAnnotation, 'provenance'>> }
  | { type: 'addFloorCorner'; point: Vec2 }
  | { type: 'addKnownLength'; value: KnownLength }
  | { type: 'updateKnownLength'; index: number; patch: Partial<KnownLength> }
  | { type: 'addParallelPair'; value: ParallelPair }
  | { type: 'updateParallelPair'; index: number; patch: Partial<ParallelPair> }
  | { type: 'setReference'; value: Omit<Reference, 'kind'> | null }
  | { type: 'updateReference'; patch: Partial<Omit<Reference, 'kind'>> }
  | { type: 'setCeilingHeight'; value: number | null }
  | { type: 'addBoundaryLine'; value: { kind: BoundaryKind; pixels: readonly Vec2[] } }
  | { type: 'updateBoundaryLine'; index: number; patch: Partial<Omit<BoundaryLine, 'provenance'>> }
  /** Remove one vertex of a boundary line (kept at 2 points minimum). */
  | { type: 'removeVertex'; ref: ItemRef; handle: number }
  /** Drag one handle. Objects: handle 0..3 = corner TL, TR, BR, BL; `anchor` (the fixed corner
   *  captured when the drag started) defaults to the corner opposite `handle`. Openings: quad
   *  vertex. Lines and lengths: endpoint 0/1. Parallel pairs: line*2 + endpoint. Boundary lines:
   *  vertex index. */
  | { type: 'moveHandle'; ref: ItemRef; handle: number; to: Vec2; anchor?: Vec2 }
  | { type: 'translate'; ref: ItemRef; delta: Vec2 }
  | { type: 'delete'; ref: ItemRef };

const validMetres = (m: unknown): m is number => typeof m === 'number' && Number.isFinite(m) && m > 0;

function same(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

function patchChanges<T extends object>(old: T, patch: Partial<T>): boolean {
  return Object.keys(patch).some((k) => !same((old as Record<string, unknown>)[k], (patch as Record<string, unknown>)[k]));
}

/** Document-level change: anything edited in the UI marks the document as human-authored. */
function touch(doc: Annotations, patch: Partial<Annotations>): Annotations {
  return { ...doc, ...patch, provenance: humanProvenance() };
}

function touchCalibration(doc: Annotations, patch: Partial<NonNullable<Annotations['calibration']>>): Annotations {
  return touch(doc, { calibration: { ...(doc.calibration ?? {}), ...patch } });
}

function replaceAt<T>(list: readonly T[], index: number, value: T): T[] {
  return list.map((v, i) => (i === index ? value : v));
}

function removeAt<T>(list: readonly T[], index: number): T[] {
  return list.filter((_, i) => i !== index);
}

function cleanOpening(o: OpeningAnnotation): OpeningAnnotation {
  if (o.wall_hint === null || (o.wall_hint as string | undefined) === '' || o.wall_hint === undefined) {
    const rest = { ...o };
    delete rest.wall_hint;
    return rest;
  }
  return o;
}

function moveLine(line: Line, handle: number, to: Vec2): Line {
  const out: Line = [line[0], line[1]];
  out[handle === 1 ? 1 : 0] = roundPt(to);
  return out;
}

function translateLine(line: Line, d: Vec2): Line {
  return [translatePoint(line[0], d), translatePoint(line[1], d)];
}

function updateObjectAt(doc: Annotations, index: number, patch: Partial<ObjectAnnotation>): Annotations {
  const objs = objectsOf(doc);
  const old = objs[index];
  if (!old || !patchChanges(old, patch)) return doc;
  const next: ObjectAnnotation = { ...old, ...patch, provenance: humanProvenance() };
  if (patch.box) next.box = normalizeBoxArray(patch.box);
  if (patch.id !== undefined && patch.id !== old.id) {
    const others = objs.filter((_, i) => i !== index).map((o) => o.id);
    if (!isValidId(patch.id) || others.includes(patch.id)) next.id = old.id;
  }
  if (next.support === next.id) next.support = old.support !== old.id ? (old.support ?? 'floor') : 'floor';
  if (patch.archetype === null || patch.archetype === '') delete next.archetype;
  if (same({ ...next, provenance: null }, { ...old, provenance: null })) return doc; // e.g. rejected id
  let out = replaceAt(objs, index, next);
  if (next.id !== old.id) {
    // keep "support" references pointing at the renamed object
    out = out.map((o, i) => (i !== index && o.support === old.id ? { ...o, support: next.id, provenance: humanProvenance() } : o));
  }
  return touch(doc, { objects: out });
}

function updateOpeningAt(doc: Annotations, index: number, patch: Partial<OpeningAnnotation>): Annotations {
  const list = openingsOf(doc);
  const old = list[index];
  if (!old || !patchChanges(old, patch)) return doc;
  const next = cleanOpening({ ...old, ...patch, provenance: humanProvenance() });
  if (patch.quad) next.quad = patch.quad.map((p) => roundPt(p as Vec2)) as Quad;
  return touch(doc, { openings: replaceAt(list, index, next) });
}

function updateLengthAt(doc: Annotations, index: number, patch: Partial<KnownLength>): Annotations {
  const list = lengthsOf(doc);
  const old = list[index];
  if (!old) return doc;
  const p = { ...patch };
  if ('metres' in p && !validMetres(p.metres)) delete p.metres;
  if (!patchChanges(old, p)) return doc;
  return touch(doc, { known_lengths: replaceAt(list, index, { ...old, ...p }) });
}

function updatePairAt(doc: Annotations, index: number, patch: Partial<ParallelPair>): Annotations {
  const list = pairsOf(doc);
  const old = list[index];
  if (!old || !patchChanges(old, patch)) return doc;
  return touchCalibration(doc, { parallel_pairs: replaceAt(list, index, { ...old, ...patch }) });
}

function updateReference(doc: Annotations, patch: Partial<Reference>): Annotations {
  const old = referenceOf(doc);
  if (!old) return doc;
  const p = { ...patch };
  if ('metres' in p && !validMetres(p.metres)) delete p.metres;
  if (!patchChanges(old, p)) return doc;
  return touchCalibration(doc, { reference: { ...old, ...p, kind: 'vertical' } });
}

function updateBoundaryAt(doc: Annotations, index: number, patch: Partial<BoundaryLine>): Annotations {
  const list = boundariesOf(doc);
  const old = list[index];
  if (!old) return doc;
  const p = { ...patch };
  delete p.provenance;
  if (p.kind !== undefined && !BOUNDARY_KINDS.includes(p.kind)) delete p.kind;
  if (p.pixels !== undefined) {
    if (p.pixels.length < 2) delete p.pixels;
    else p.pixels = p.pixels.map((q) => roundPt(q as Vec2)) as BoundaryLine['pixels'];
  }
  if (!patchChanges(old, p)) return doc;
  return touch(doc, { boundary_lines: replaceAt(list, index, { ...old, ...p, provenance: humanProvenance() }) });
}

function moveHandle(doc: Annotations, ref: ItemRef, handle: number, to: Vec2, anchor?: Vec2): Annotations {
  switch (ref.kind) {
    case 'object': {
      const o = objectsOf(doc)[ref.index];
      if (!o) return doc;
      const fixed = anchor ?? oppositeCorner(o.box as Box, handle);
      return updateObjectAt(doc, ref.index, { box: normalizeBox(fixed, to) });
    }
    case 'opening': {
      const o = openingsOf(doc)[ref.index];
      if (!o || handle < 0 || handle > 3) return doc;
      const quad = o.quad.map((p, i) => (i === handle ? roundPt(to) : p)) as Quad;
      return updateOpeningAt(doc, ref.index, { quad });
    }
    case 'floor_corner': {
      const list = cornersOf(doc);
      if (ref.index >= list.length) return doc;
      return touch(doc, { floor_corners: replaceAt(list, ref.index, roundPt(to)) });
    }
    case 'known_length': {
      const k = lengthsOf(doc)[ref.index];
      if (!k) return doc;
      return updateLengthAt(doc, ref.index, { pixels: moveLine(k.pixels as Line, handle, to) });
    }
    case 'parallel_pair': {
      const p = pairsOf(doc)[ref.index];
      const li = Math.floor(handle / 2);
      if (!p || !p.lines[li]) return doc;
      const lines = p.lines.map((l, i) => (i === li ? moveLine(l as Line, handle % 2, to) : l)) as ParallelPair['lines'];
      return updatePairAt(doc, ref.index, { lines });
    }
    case 'vertical_line': {
      const list = verticalsOf(doc);
      const l = list[ref.index];
      if (!l) return doc;
      return touchCalibration(doc, { vertical_lines: replaceAt(list, ref.index, moveLine(l, handle, to)) });
    }
    case 'reference': {
      const r = referenceOf(doc);
      if (!r) return doc;
      return updateReference(doc, { pixels: moveLine(r.pixels as Line, handle, to) });
    }
    case 'boundary_line': {
      const b = boundariesOf(doc)[ref.index];
      if (!b || handle < 0 || handle >= b.pixels.length) return doc;
      const pixels = b.pixels.map((p, i) => (i === handle ? roundPt(to) : p)) as BoundaryLine['pixels'];
      return updateBoundaryAt(doc, ref.index, { pixels });
    }
  }
}

function translate(doc: Annotations, ref: ItemRef, d: Vec2): Annotations {
  if (d[0] === 0 && d[1] === 0) return doc;
  switch (ref.kind) {
    case 'object': {
      const o = objectsOf(doc)[ref.index];
      return o ? updateObjectAt(doc, ref.index, { box: translateBox(o.box as Box, d) }) : doc;
    }
    case 'opening': {
      const o = openingsOf(doc)[ref.index];
      return o ? updateOpeningAt(doc, ref.index, { quad: o.quad.map((p) => translatePoint(p as Vec2, d)) as Quad }) : doc;
    }
    case 'floor_corner': {
      const list = cornersOf(doc);
      const p = list[ref.index];
      return p ? touch(doc, { floor_corners: replaceAt(list, ref.index, translatePoint(p, d)) }) : doc;
    }
    case 'known_length': {
      const k = lengthsOf(doc)[ref.index];
      return k ? updateLengthAt(doc, ref.index, { pixels: translateLine(k.pixels as Line, d) }) : doc;
    }
    case 'parallel_pair': {
      const p = pairsOf(doc)[ref.index];
      return p ? updatePairAt(doc, ref.index, { lines: p.lines.map((l) => translateLine(l as Line, d)) as ParallelPair['lines'] }) : doc;
    }
    case 'vertical_line': {
      const list = verticalsOf(doc);
      const l = list[ref.index];
      return l ? touchCalibration(doc, { vertical_lines: replaceAt(list, ref.index, translateLine(l, d)) }) : doc;
    }
    case 'reference': {
      const r = referenceOf(doc);
      return r ? updateReference(doc, { pixels: translateLine(r.pixels as Line, d) }) : doc;
    }
    case 'boundary_line': {
      const b = boundariesOf(doc)[ref.index];
      return b ? updateBoundaryAt(doc, ref.index, { pixels: b.pixels.map((p) => translatePoint(p as Vec2, d)) as BoundaryLine['pixels'] }) : doc;
    }
  }
}

function deleteItem(doc: Annotations, ref: ItemRef): Annotations {
  if (!itemExists(doc, ref)) return doc;
  switch (ref.kind) {
    case 'object': {
      const objs = objectsOf(doc);
      const gone = objs[ref.index].id;
      const rest = removeAt(objs, ref.index).map((o) =>
        o.support === gone ? { ...o, support: 'floor', provenance: humanProvenance() } : o,
      );
      return touch(doc, { objects: rest });
    }
    case 'opening':
      return touch(doc, { openings: removeAt(openingsOf(doc), ref.index) });
    case 'floor_corner':
      return touch(doc, { floor_corners: removeAt(cornersOf(doc), ref.index) });
    case 'known_length':
      return touch(doc, { known_lengths: removeAt(lengthsOf(doc), ref.index) });
    case 'parallel_pair':
      return touchCalibration(doc, { parallel_pairs: removeAt(pairsOf(doc), ref.index) });
    case 'vertical_line':
      return touchCalibration(doc, { vertical_lines: removeAt(verticalsOf(doc), ref.index) });
    case 'boundary_line':
      return touch(doc, { boundary_lines: removeAt(boundariesOf(doc), ref.index) });
    case 'reference': {
      const cal = { ...(doc.calibration ?? {}) };
      delete cal.reference;
      return touch(doc, { calibration: cal });
    }
  }
}

/** Apply one edit. Returns the same object when nothing changed (no undo step is recorded). */
export function applyEdit(doc: Annotations, action: EditAction): Annotations {
  switch (action.type) {
    case 'addObject': {
      const objs = objectsOf(doc);
      const o = action.object;
      const label = o.label.trim();
      const id = uniqueId(o.id && o.id.trim() ? o.id.trim() : slugify(label), objs.map((x) => x.id));
      const support = o.support && o.support !== id ? o.support : 'floor';
      const obj: ObjectAnnotation = {
        id,
        label: label || id,
        box: normalizeBoxArray(o.box),
        support,
        params: o.params ?? {},
        materials_hint: o.materials_hint ?? [],
        provenance: humanProvenance(),
      };
      if (o.archetype) obj.archetype = o.archetype;
      return touch(doc, { objects: [...objs, obj] });
    }
    case 'updateObject':
      return updateObjectAt(doc, action.index, action.patch);
    case 'addOpening': {
      const o = action.opening;
      const opening = cleanOpening({
        kind: o.kind,
        quad: o.quad.map((p) => roundPt(p)) as Quad,
        wall_hint: (o.wall_hint || null) as WallHint,
        label: o.label ?? '',
        provenance: humanProvenance(),
      });
      return touch(doc, { openings: [...openingsOf(doc), opening] });
    }
    case 'updateOpening':
      return updateOpeningAt(doc, action.index, action.patch);
    case 'addFloorCorner':
      return touch(doc, { floor_corners: [...cornersOf(doc), roundPt(action.point)] });
    case 'addKnownLength': {
      const v = action.value;
      if (!validMetres(v.metres)) return doc;
      const k: KnownLength = { pixels: [roundPt(v.pixels[0]), roundPt(v.pixels[1])], metres: v.metres, label: v.label ?? '' };
      return touch(doc, { known_lengths: [...lengthsOf(doc), k] });
    }
    case 'updateKnownLength':
      return updateLengthAt(doc, action.index, action.patch);
    case 'addParallelPair': {
      const v = action.value;
      if (v.lines.length < 2) return doc;
      const lines = v.lines.map((l) => [roundPt(l[0]), roundPt(l[1])]) as ParallelPair['lines'];
      return touchCalibration(doc, { parallel_pairs: [...pairsOf(doc), { axis: v.axis, lines }] });
    }
    case 'updateParallelPair':
      return updatePairAt(doc, action.index, action.patch);
    case 'setReference': {
      if (action.value === null) return deleteItem(doc, { kind: 'reference' });
      const v = action.value;
      if (!validMetres(v.metres)) return doc;
      const reference: Reference = {
        kind: 'vertical',
        pixels: [roundPt(v.pixels[0]), roundPt(v.pixels[1])],
        metres: v.metres,
        label: v.label ?? '',
      };
      return touchCalibration(doc, { reference });
    }
    case 'updateReference':
      return updateReference(doc, action.patch);
    case 'setCeilingHeight': {
      const v = action.value;
      if (v !== null && !validMetres(v)) return doc;
      if ((doc.ceiling_height_m ?? null) === v) return doc;
      return touch(doc, { ceiling_height_m: v });
    }
    case 'addBoundaryLine': {
      const { kind, pixels } = action.value;
      if (!BOUNDARY_KINDS.includes(kind) || pixels.length < 2) return doc;
      const line: BoundaryLine = {
        kind,
        pixels: pixels.map((p) => roundPt(p)) as BoundaryLine['pixels'],
        provenance: humanProvenance(),
      };
      return touch(doc, { boundary_lines: [...boundariesOf(doc), line] });
    }
    case 'updateBoundaryLine':
      return updateBoundaryAt(doc, action.index, action.patch);
    case 'removeVertex': {
      if (action.ref.kind !== 'boundary_line') return doc;
      const b = boundariesOf(doc)[action.ref.index];
      if (!b || b.pixels.length <= 2 || action.handle < 0 || action.handle >= b.pixels.length) return doc;
      return updateBoundaryAt(doc, action.ref.index, { pixels: removeAt(b.pixels, action.handle) as BoundaryLine['pixels'] });
    }
    case 'moveHandle':
      return moveHandle(doc, action.ref, action.handle, action.to, action.anchor);
    case 'translate':
      return translate(doc, action.ref, action.delta);
    case 'delete':
      return deleteItem(doc, action.ref);
  }
}

// ------------------------------------------------------------------------------------------
// Undo / redo
// ------------------------------------------------------------------------------------------

export const HISTORY_LIMIT = 100;

export interface History {
  past: Annotations[];
  present: Annotations;
  future: Annotations[];
  /** The document as last loaded from or saved to the server (dirty = present !== saved). */
  saved: Annotations;
  /** Tag of the open undo step; edits with the same tag merge into it (one drag = one step). */
  lastTag: string | null;
}

export type HistoryAction =
  | { type: 'load'; doc: Annotations }
  | { type: 'edit'; edit: EditAction; tag?: string }
  | { type: 'endGesture' }
  | { type: 'undo' }
  | { type: 'redo' }
  | { type: 'markSaved'; doc: Annotations };

export function initHistory(doc: Annotations): History {
  const d = normalizeDoc(doc);
  return { past: [], present: d, future: [], saved: d, lastTag: null };
}

export function historyReducer(state: History, action: HistoryAction): History {
  switch (action.type) {
    case 'load':
      return initHistory(action.doc);
    case 'edit': {
      const next = applyEdit(state.present, action.edit);
      if (next === state.present) return state;
      if (action.tag && action.tag === state.lastTag) return { ...state, present: next, future: [] };
      return {
        ...state,
        past: [...state.past, state.present].slice(-HISTORY_LIMIT),
        present: next,
        future: [],
        lastTag: action.tag ?? null,
      };
    }
    case 'endGesture':
      return state.lastTag === null ? state : { ...state, lastTag: null };
    case 'undo': {
      if (state.past.length === 0) return state;
      return {
        ...state,
        past: state.past.slice(0, -1),
        present: state.past[state.past.length - 1],
        future: [state.present, ...state.future],
        lastTag: null,
      };
    }
    case 'redo': {
      if (state.future.length === 0) return state;
      return {
        ...state,
        past: [...state.past, state.present].slice(-HISTORY_LIMIT),
        present: state.future[0],
        future: state.future.slice(1),
        lastTag: null,
      };
    }
    case 'markSaved':
      return { ...state, saved: action.doc };
  }
}

export const isDirty = (h: History): boolean => h.present !== h.saved;
export const canUndo = (h: History): boolean => h.past.length > 0;
export const canRedo = (h: History): boolean => h.future.length > 0;
