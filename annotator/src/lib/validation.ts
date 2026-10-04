// Map pydantic validation errors (PUT /annotations -> 422 {ok:false, errors:[...]}) onto the
// annotation items they point at, so the UI can show each message next to the offending item.

import type { Annotations } from '../types/annotations';
import { type ItemRef, describeRef, objectsOf, refKey } from './annotations';

export interface ValidationIssue {
  type?: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
  ctx?: unknown;
}

const LIST_KINDS: Record<string, ItemRef['kind']> = {
  objects: 'object',
  openings: 'opening',
  floor_corners: 'floor_corner',
  known_lengths: 'known_length',
  boundary_lines: 'boundary_line',
};

const CAL_LIST_KINDS: Record<string, ItemRef['kind']> = {
  parallel_pairs: 'parallel_pair',
  vertical_lines: 'vertical_line',
};

function toIndex(v: unknown): number | null {
  if (typeof v === 'number' && Number.isInteger(v) && v >= 0) return v;
  if (typeof v === 'string' && /^\d+$/.test(v)) return Number(v);
  return null;
}

/** The item an error location points at, or null for document-level errors. */
export function refFromLoc(loc: readonly (string | number)[]): ItemRef | null {
  const l = loc[0] === 'body' ? loc.slice(1) : loc;
  const head = l[0];
  if (typeof head !== 'string') return null;
  if (head in LIST_KINDS) {
    const index = toIndex(l[1]);
    return index === null ? null : ({ kind: LIST_KINDS[head], index } as ItemRef);
  }
  if (head === 'calibration') {
    const sub = l[1];
    if (sub === 'reference') return { kind: 'reference' };
    if (typeof sub === 'string' && sub in CAL_LIST_KINDS) {
      const index = toIndex(l[2]);
      return index === null ? null : ({ kind: CAL_LIST_KINDS[sub], index } as ItemRef);
    }
  }
  return null;
}

/** Location inside the item, e.g. "box" for ['objects', 2, 'box']. */
export function fieldFromLoc(loc: readonly (string | number)[]): string {
  const l = loc[0] === 'body' ? loc.slice(1) : loc;
  const ref = refFromLoc(l);
  if (!ref) return l.join('.');
  const skip = l[0] === 'calibration' ? (ref.kind === 'reference' ? 2 : 3) : 2;
  return l.slice(skip).join('.');
}

/** Pydantic prefixes model-validator messages with "Value error, "; drop it for display. */
export function cleanMsg(msg: string): string {
  return msg.replace(/^Value error, /, '');
}

/** Every item an issue concerns: its `loc`, or the objects named in a duplicate-id error. */
export function refsForIssue(issue: ValidationIssue, doc: Annotations | null): ItemRef[] {
  const ref = refFromLoc(issue.loc);
  if (ref) return [ref];
  const dup = /duplicate object ids: \[([^\]]*)\]/.exec(issue.msg);
  if (dup && doc) {
    const ids = new Set(Array.from(dup[1].matchAll(/'([^']*)'|"([^"]*)"/g), (m) => m[1] ?? m[2]));
    return objectsOf(doc)
      .map((o, index) => ({ o, index }))
      .filter(({ o }) => ids.has(o.id))
      .map(({ index }) => ({ kind: 'object', index }));
  }
  return [];
}

/** issue list grouped by refKey; document-level issues are under "" */
export function issuesByItem(issues: readonly ValidationIssue[], doc: Annotations | null): Map<string, ValidationIssue[]> {
  const out = new Map<string, ValidationIssue[]>();
  const add = (k: string, i: ValidationIssue) => out.set(k, [...(out.get(k) ?? []), i]);
  for (const issue of issues) {
    const refs = refsForIssue(issue, doc);
    if (refs.length === 0) add('', issue);
    for (const r of refs) add(refKey(r), issue);
  }
  return out;
}

/** One readable line, e.g. `object "sofa" › box: box must be [x0, y0, x1, y1] with x1 > x0 ...`. */
export function describeIssue(issue: ValidationIssue, doc: Annotations | null): string {
  const ref = refFromLoc(issue.loc);
  const field = fieldFromLoc(issue.loc);
  const where = ref && doc ? describeRef(doc, ref) : ref ? refKey(ref) : '';
  const prefix = [where, field].filter(Boolean).join(' › ');
  return prefix ? `${prefix}: ${cleanMsg(issue.msg)}` : cleanMsg(issue.msg);
}

/** Accept both room_gen's `{ok:false, errors:[...]}` and FastAPI's `{detail:[...]}` 422 bodies. */
export function parseIssues(body: unknown): ValidationIssue[] {
  if (!body || typeof body !== 'object') return [];
  const b = body as { errors?: unknown; detail?: unknown };
  const raw = Array.isArray(b.errors) ? b.errors : Array.isArray(b.detail) ? b.detail : null;
  if (!raw) {
    if (typeof b.detail === 'string') return [{ loc: [], msg: b.detail }];
    return [];
  }
  return raw
    .filter((e): e is Record<string, unknown> => !!e && typeof e === 'object')
    .map((e) => ({
      type: typeof e.type === 'string' ? e.type : undefined,
      loc: Array.isArray(e.loc) ? (e.loc.filter((x) => typeof x === 'string' || typeof x === 'number') as (string | number)[]) : [],
      msg: typeof e.msg === 'string' ? e.msg : JSON.stringify(e),
      input: e.input,
      ctx: e.ctx,
    }));
}

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isPoint = (p: unknown): boolean => Array.isArray(p) && p.length === 2 && p.every(finite);

/**
 * Client-side check of the rules in room_gen.models.Annotations that the editor can break or that
 * an imported file may already break. Messages and `loc` follow pydantic so they render the same
 * way as server errors. (The server cannot currently serialise `value_error` issues such as a
 * flipped box or duplicate ids -- they come back as HTTP 500 -- so these are caught here first.)
 */
export function localIssues(doc: Annotations): ValidationIssue[] {
  const out: ValidationIssue[] = [];
  const add = (loc: (string | number)[], msg: string) => out.push({ loc, msg });
  const objs = doc.objects ?? [];
  objs.forEach((o, i) => {
    if (typeof o.id !== 'string' || !/^[a-z0-9][a-z0-9_-]*$/.test(o.id)) add(['objects', i, 'id'], "String should match pattern '^[a-z0-9][a-z0-9_-]*$'");
    else if (o.id.length > 80) add(['objects', i, 'id'], 'String should have at most 80 characters');
    const b = o.box as unknown;
    if (!Array.isArray(b) || b.length !== 4 || !b.every(finite)) add(['objects', i, 'box'], 'box must be 4 numbers [x0, y0, x1, y1]');
    else if (!(b[2] > b[0] && b[3] > b[1])) add(['objects', i, 'box'], 'Value error, box must be [x0, y0, x1, y1] with x1 > x0 and y1 > y0');
  });
  const ids = objs.map((o) => o.id);
  const dupes = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))].sort();
  if (dupes.length) add([], `Value error, duplicate object ids: [${dupes.map((d) => `'${d}'`).join(', ')}]`);
  (doc.openings ?? []).forEach((o, i) => {
    if (!['door', 'window', 'opening'].includes(o.kind)) add(['openings', i, 'kind'], "Input should be 'door', 'window' or 'opening'");
    if (!Array.isArray(o.quad) || o.quad.length !== 4 || !o.quad.every(isPoint)) add(['openings', i, 'quad'], 'quad must be 4 [u, v] points');
  });
  (doc.known_lengths ?? []).forEach((k, i) => {
    if (!(finite(k.metres) && k.metres > 0)) add(['known_lengths', i, 'metres'], 'Input should be greater than 0');
    if (!Array.isArray(k.pixels) || k.pixels.length !== 2 || !k.pixels.every(isPoint)) add(['known_lengths', i, 'pixels'], 'pixels must be two [u, v] points');
  });
  (doc.boundary_lines ?? []).forEach((b, i) => {
    if (!['wall_floor', 'wall_ceiling', 'wall_wall'].includes(b.kind))
      add(['boundary_lines', i, 'kind'], "Input should be 'wall_floor', 'wall_ceiling' or 'wall_wall'");
    if (!Array.isArray(b.pixels) || b.pixels.length < 2) add(['boundary_lines', i, 'pixels'], 'List should have at least 2 items');
    else if (!b.pixels.every(isPoint)) add(['boundary_lines', i, 'pixels'], 'pixels must be [u, v] points');
  });
  const cal = doc.calibration ?? {};
  (cal.parallel_pairs ?? []).forEach((p, i) => {
    if (!['x', 'y', 'z'].includes(p.axis)) add(['calibration', 'parallel_pairs', i, 'axis'], "Input should be 'x', 'y' or 'z'");
    if (!Array.isArray(p.lines) || p.lines.length < 2) add(['calibration', 'parallel_pairs', i, 'lines'], 'List should have at least 2 items');
  });
  if (cal.reference && !(finite(cal.reference.metres) && cal.reference.metres > 0))
    add(['calibration', 'reference', 'metres'], 'Input should be greater than 0');
  if (doc.ceiling_height_m !== undefined && doc.ceiling_height_m !== null && !(doc.ceiling_height_m > 0))
    add(['ceiling_height_m'], 'Input should be greater than 0');
  return out;
}
