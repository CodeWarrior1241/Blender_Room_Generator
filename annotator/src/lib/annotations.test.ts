import { describe, expect, it } from 'vitest';
import type { Annotations } from '../types/annotations';
import {
  type EditAction,
  type History,
  HISTORY_LIMIT,
  HUMAN_PROVENANCE,
  applyEdit,
  canRedo,
  canUndo,
  historyReducer,
  initHistory,
  isDirty,
  normalizeDoc,
} from './annotations';

const AUTO = { by: 'auto', tool: 'detector', confidence: 0.6 } as const;

function baseDoc(): Annotations {
  return {
    schema_version: 1,
    world: 'living',
    image: 'source/0-photo.png',
    image_size: [1280, 960],
    calibration: { parallel_pairs: [], vertical_lines: [] },
    floor_corners: [],
    objects: [
      { id: 'sofa', label: 'couch', box: [242, 456, 635, 650], support: 'floor', archetype: 'sofa', params: {}, materials_hint: [], score: 0.55, provenance: { ...AUTO } },
      { id: 'lamp', label: 'table lamp', box: [10, 10, 40, 60], support: 'sofa', provenance: { ...AUTO } },
    ],
    openings: [{ kind: 'window', quad: [[1, 1], [9, 1], [9, 9], [1, 9]], provenance: { ...AUTO } }],
    known_lengths: [],
    notes: [],
    provenance: { by: 'auto', tool: 'room_gen auto', confidence: 0.5 },
  };
}

const edit = (h: History, e: EditAction, tag?: string) => historyReducer(h, { type: 'edit', edit: e, tag });

describe('applyEdit: objects', () => {
  it('adds an object with a slug id, normalised box and human provenance', () => {
    const d = applyEdit(baseDoc(), { type: 'addObject', object: { label: 'Coffee Table', box: [600, 700, 400, 500], archetype: 'coffee_table' } });
    const o = d.objects!.at(-1)!;
    expect(o.id).toBe('coffee-table');
    expect(o.label).toBe('Coffee Table');
    expect(o.box).toEqual([400, 500, 600, 700]);
    expect(o.support).toBe('floor');
    expect(o.archetype).toBe('coffee_table');
    expect(o.provenance).toEqual(HUMAN_PROVENANCE);
    expect(d.provenance).toEqual(HUMAN_PROVENANCE);
  });

  it('keeps ids unique when the label repeats', () => {
    let d = baseDoc();
    d = applyEdit(d, { type: 'addObject', object: { label: 'sofa', box: [0, 0, 5, 5] } });
    d = applyEdit(d, { type: 'addObject', object: { label: 'Sofa', box: [0, 0, 5, 5] } });
    expect(d.objects!.map((o) => o.id)).toEqual(['sofa', 'lamp', 'sofa-2', 'sofa-3']);
  });

  it('slugifies an explicit id and never lets an object support itself', () => {
    const d = applyEdit(baseDoc(), { type: 'addObject', object: { label: 'x', id: 'Big Shelf', box: [0, 0, 5, 5], support: 'big-shelf' } });
    const o = d.objects!.at(-1)!;
    expect(o.id).toBe('big-shelf');
    expect(o.support).toBe('floor');
  });

  it('editing an auto object makes it human', () => {
    const d = applyEdit(baseDoc(), { type: 'updateObject', index: 0, patch: { label: 'sofa' } });
    expect(d.objects![0].provenance).toEqual(HUMAN_PROVENANCE);
    expect(d.objects![0].score).toBe(0.55); // detector score is kept
    expect(d.objects![1].provenance).toEqual(AUTO); // untouched items stay auto
  });

  it('a no-op patch returns the same document', () => {
    const doc = baseDoc();
    expect(applyEdit(doc, { type: 'updateObject', index: 0, patch: { label: 'couch' } })).toBe(doc);
    expect(applyEdit(doc, { type: 'updateObject', index: 9, patch: { label: 'x' } })).toBe(doc);
  });

  it('rejects an invalid or duplicate id but applies the rest of the patch', () => {
    const doc = baseDoc();
    expect(applyEdit(doc, { type: 'updateObject', index: 0, patch: { id: 'lamp' } })).toBe(doc);
    expect(applyEdit(doc, { type: 'updateObject', index: 0, patch: { id: 'Bad Id' } })).toBe(doc);
    const d = applyEdit(doc, { type: 'updateObject', index: 0, patch: { id: 'lamp', label: 'big sofa' } });
    expect(d.objects![0].id).toBe('sofa');
    expect(d.objects![0].label).toBe('big sofa');
  });

  it('renaming an id updates support references', () => {
    const d = applyEdit(baseDoc(), { type: 'updateObject', index: 0, patch: { id: 'couch' } });
    expect(d.objects![0].id).toBe('couch');
    expect(d.objects![1].support).toBe('couch');
    expect(d.objects![1].provenance).toEqual(HUMAN_PROVENANCE);
  });

  it('a box patch is normalised', () => {
    const d = applyEdit(baseDoc(), { type: 'updateObject', index: 0, patch: { box: [635, 650, 242, 456] } });
    expect(d.objects![0].box).toEqual([242, 456, 635, 650]);
  });

  it('moves a corner handle, also across the opposite corner', () => {
    let d = applyEdit(baseDoc(), { type: 'moveHandle', ref: { kind: 'object', index: 1 }, handle: 2, to: [50, 80] });
    expect(d.objects![1].box).toEqual([10, 10, 50, 80]);
    expect(d.objects![1].provenance).toEqual(HUMAN_PROVENANCE);
    // drag BR past TL with the anchor captured at drag start
    d = applyEdit(d, { type: 'moveHandle', ref: { kind: 'object', index: 1 }, handle: 2, to: [0, 0], anchor: [10, 10] });
    expect(d.objects![1].box).toEqual([0, 0, 10, 10]);
  });

  it('translates a box', () => {
    const d = applyEdit(baseDoc(), { type: 'translate', ref: { kind: 'object', index: 1 }, delta: [5, -5] });
    expect(d.objects![1].box).toEqual([15, 5, 45, 55]);
    expect(d.objects![1].provenance!.by).toBe('human');
  });

  it('deleting an object re-homes the objects it supported', () => {
    const d = applyEdit(baseDoc(), { type: 'delete', ref: { kind: 'object', index: 0 } });
    expect(d.objects!.map((o) => o.id)).toEqual(['lamp']);
    expect(d.objects![0].support).toBe('floor');
  });
});

describe('applyEdit: other items', () => {
  it('openings: add with human provenance, drop empty wall hint, move a vertex', () => {
    let d = applyEdit(baseDoc(), {
      type: 'addOpening',
      opening: { kind: 'door', quad: [[0, 0], [10, 0], [10, 20], [0, 20]], wall_hint: null, label: '' },
    });
    const o = d.openings![1];
    expect(o.provenance).toEqual(HUMAN_PROVENANCE);
    expect('wall_hint' in o).toBe(false);
    d = applyEdit(d, { type: 'updateOpening', index: 1, patch: { wall_hint: 'left' } });
    expect(d.openings![1].wall_hint).toBe('left');
    d = applyEdit(d, { type: 'moveHandle', ref: { kind: 'opening', index: 0 }, handle: 2, to: [12, 13] });
    expect(d.openings![0].quad[2]).toEqual([12, 13]);
    expect(d.openings![0].provenance).toEqual(HUMAN_PROVENANCE);
  });

  it('floor corners: add, move, delete', () => {
    let d = applyEdit(baseDoc(), { type: 'addFloorCorner', point: [1.234, 5.678] });
    expect(d.floor_corners).toEqual([[1.2, 5.7]]);
    d = applyEdit(d, { type: 'moveHandle', ref: { kind: 'floor_corner', index: 0 }, handle: 0, to: [3, 4] });
    expect(d.floor_corners).toEqual([[3, 4]]);
    d = applyEdit(d, { type: 'delete', ref: { kind: 'floor_corner', index: 0 } });
    expect(d.floor_corners).toEqual([]);
  });

  it('known lengths require metres > 0', () => {
    const doc = baseDoc();
    expect(applyEdit(doc, { type: 'addKnownLength', value: { pixels: [[0, 0], [1, 1]], metres: 0 } })).toBe(doc);
    const d = applyEdit(doc, { type: 'addKnownLength', value: { pixels: [[0, 0], [1, 1]], metres: 1.2, label: 'rug' } });
    expect(d.known_lengths).toEqual([{ pixels: [[0, 0], [1, 1]], metres: 1.2, label: 'rug' }]);
    expect(applyEdit(d, { type: 'updateKnownLength', index: 0, patch: { metres: -1 } })).toBe(d);
  });

  it('parallel pairs: add and move an endpoint of the second line', () => {
    let d = applyEdit(baseDoc(), {
      type: 'addParallelPair',
      value: { axis: 'x', lines: [[[0, 0], [10, 1]], [[0, 10], [10, 12]]] },
    });
    expect(d.calibration!.parallel_pairs).toHaveLength(1);
    d = applyEdit(d, { type: 'moveHandle', ref: { kind: 'parallel_pair', index: 0 }, handle: 3, to: [20, 20] });
    expect(d.calibration!.parallel_pairs![0].lines[1]).toEqual([[0, 10], [20, 20]]);
    d = applyEdit(d, { type: 'updateParallelPair', index: 0, patch: { axis: 'z' } });
    expect(d.calibration!.parallel_pairs![0].axis).toBe('z');
  });

  it('reference: set, edit, delete', () => {
    let d = applyEdit(baseDoc(), { type: 'setReference', value: { pixels: [[100, 900], [100, 300]], metres: 2.03, label: 'door' } });
    expect(d.calibration!.reference).toEqual({ kind: 'vertical', pixels: [[100, 900], [100, 300]], metres: 2.03, label: 'door' });
    d = applyEdit(d, { type: 'updateReference', patch: { metres: 2.1 } });
    expect(d.calibration!.reference!.metres).toBe(2.1);
    d = applyEdit(d, { type: 'delete', ref: { kind: 'reference' } });
    expect(d.calibration!.reference).toBeUndefined();
    expect(d.calibration!.parallel_pairs).toEqual([]);
  });

  it('does not mutate its input', () => {
    const doc = baseDoc();
    const snapshot = JSON.stringify(doc);
    applyEdit(doc, { type: 'translate', ref: { kind: 'opening', index: 0 }, delta: [1, 1] });
    applyEdit(doc, { type: 'delete', ref: { kind: 'object', index: 0 } });
    applyEdit(doc, { type: 'updateObject', index: 0, patch: { id: 'couch' } });
    expect(JSON.stringify(doc)).toBe(snapshot);
  });
});

describe('applyEdit: boundary lines', () => {
  const withBoundary = (): Annotations => ({
    ...baseDoc(),
    boundary_lines: [{ kind: 'wall_floor', pixels: [[0, 700], [400, 640], [900, 600]], provenance: { ...AUTO } }],
  });

  it('adds a polyline with human provenance and rounded pixels', () => {
    const d = applyEdit(baseDoc(), { type: 'addBoundaryLine', value: { kind: 'wall_ceiling', pixels: [[0.04, 100.06], [500, 80]] } });
    expect(d.boundary_lines).toEqual([{ kind: 'wall_ceiling', pixels: [[0, 100.1], [500, 80]], provenance: HUMAN_PROVENANCE }]);
    expect(d.provenance).toEqual(HUMAN_PROVENANCE);
  });

  it('rejects fewer than 2 points and unknown kinds', () => {
    const doc = baseDoc();
    expect(applyEdit(doc, { type: 'addBoundaryLine', value: { kind: 'wall_floor', pixels: [[1, 1]] } })).toBe(doc);
    expect(applyEdit(doc, { type: 'addBoundaryLine', value: { kind: 'floor' as never, pixels: [[1, 1], [2, 2]] } })).toBe(doc);
  });

  it('moves one vertex and makes an auto line human', () => {
    const d = applyEdit(withBoundary(), { type: 'moveHandle', ref: { kind: 'boundary_line', index: 0 }, handle: 1, to: [410.04, 650] });
    expect(d.boundary_lines![0].pixels).toEqual([[0, 700], [410, 650], [900, 600]]);
    expect(d.boundary_lines![0].provenance).toEqual(HUMAN_PROVENANCE);
    const doc = withBoundary();
    expect(applyEdit(doc, { type: 'moveHandle', ref: { kind: 'boundary_line', index: 0 }, handle: 7, to: [1, 1] })).toBe(doc);
  });

  it('translates the whole line', () => {
    const d = applyEdit(withBoundary(), { type: 'translate', ref: { kind: 'boundary_line', index: 0 }, delta: [10, -5] });
    expect(d.boundary_lines![0].pixels).toEqual([[10, 695], [410, 635], [910, 595]]);
  });

  it('changes the kind', () => {
    const d = applyEdit(withBoundary(), { type: 'updateBoundaryLine', index: 0, patch: { kind: 'wall_wall' } });
    expect(d.boundary_lines![0].kind).toBe('wall_wall');
    expect(d.boundary_lines![0].provenance!.by).toBe('human');
  });

  it('removes a vertex but keeps at least 2', () => {
    let d = applyEdit(withBoundary(), { type: 'removeVertex', ref: { kind: 'boundary_line', index: 0 }, handle: 1 });
    expect(d.boundary_lines![0].pixels).toEqual([[0, 700], [900, 600]]);
    const same = applyEdit(d, { type: 'removeVertex', ref: { kind: 'boundary_line', index: 0 }, handle: 0 });
    expect(same).toBe(d);
    d = applyEdit(d, { type: 'delete', ref: { kind: 'boundary_line', index: 0 } });
    expect(d.boundary_lines).toEqual([]);
  });

  it('add / edit vertex / delete are undoable steps; a vertex drag is one step', () => {
    let h = initHistory(baseDoc());
    expect(h.present.boundary_lines).toEqual([]);
    h = edit(h, { type: 'addBoundaryLine', value: { kind: 'wall_floor', pixels: [[0, 0], [10, 0], [20, 5]] } });
    for (let x = 11; x <= 15; x++) h = edit(h, { type: 'moveHandle', ref: { kind: 'boundary_line', index: 0 }, handle: 1, to: [x, 1] }, 'drag-v');
    h = historyReducer(h, { type: 'endGesture' });
    h = edit(h, { type: 'delete', ref: { kind: 'boundary_line', index: 0 } });
    expect(h.present.boundary_lines).toEqual([]);
    expect(h.past).toHaveLength(3);
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.boundary_lines![0].pixels).toEqual([[0, 0], [15, 1], [20, 5]]);
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.boundary_lines![0].pixels).toEqual([[0, 0], [10, 0], [20, 5]]);
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.boundary_lines).toEqual([]);
    expect(isDirty(h)).toBe(false);
    h = historyReducer(h, { type: 'redo' });
    expect(h.present.boundary_lines).toHaveLength(1);
  });

  it('every other edit, load, undo and redo preserve boundary_lines untouched', () => {
    const doc = withBoundary();
    const before = JSON.stringify(doc.boundary_lines);
    const edits: EditAction[] = [
      { type: 'addObject', object: { label: 'chair', box: [0, 0, 5, 5] } },
      { type: 'updateObject', index: 0, patch: { label: 'sofa' } },
      { type: 'translate', ref: { kind: 'object', index: 1 }, delta: [1, 1] },
      { type: 'delete', ref: { kind: 'object', index: 0 } },
      { type: 'addOpening', opening: { kind: 'door', quad: [[0, 0], [1, 0], [1, 1], [0, 1]] } },
      { type: 'addFloorCorner', point: [3, 3] },
      { type: 'addKnownLength', value: { pixels: [[0, 0], [1, 1]], metres: 1 } },
      { type: 'addParallelPair', value: { axis: 'x', lines: [[[0, 0], [1, 1]], [[0, 2], [1, 3]]] } },
      { type: 'setReference', value: { pixels: [[5, 9], [5, 1]], metres: 2 } },
      { type: 'setCeilingHeight', value: 2.5 },
    ];
    let h = initHistory(doc);
    expect(JSON.stringify(h.present.boundary_lines)).toBe(before);
    for (const e of edits) {
      h = edit(h, e);
      expect(JSON.stringify(h.present.boundary_lines)).toBe(before);
    }
    while (canUndo(h)) h = historyReducer(h, { type: 'undo' });
    while (canRedo(h)) h = historyReducer(h, { type: 'redo' });
    expect(JSON.stringify(h.present.boundary_lines)).toBe(before);
  });
});

describe('history', () => {
  it('normalises a skeleton document on load', () => {
    const h = initHistory({ world: 'w', image: 'i.png', image_size: [10, 10] });
    expect(h.present.objects).toEqual([]);
    expect(h.present.calibration).toEqual({ parallel_pairs: [], vertical_lines: [] });
    expect(isDirty(h)).toBe(false);
    expect(normalizeDoc(h.present).schema_version).toBe(1);
  });

  it('add / undo / redo', () => {
    let h = initHistory(baseDoc());
    h = edit(h, { type: 'addFloorCorner', point: [1, 1] });
    h = edit(h, { type: 'addFloorCorner', point: [2, 2] });
    expect(h.present.floor_corners).toHaveLength(2);
    expect(isDirty(h)).toBe(true);
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.floor_corners).toEqual([[1, 1]]);
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.floor_corners).toEqual([]);
    expect(isDirty(h)).toBe(false); // back at the saved document
    expect(canUndo(h)).toBe(false);
    h = historyReducer(h, { type: 'redo' });
    h = historyReducer(h, { type: 'redo' });
    expect(h.present.floor_corners).toEqual([[1, 1], [2, 2]]);
    expect(canRedo(h)).toBe(false);
  });

  it('a new edit clears the redo stack', () => {
    let h = initHistory(baseDoc());
    h = edit(h, { type: 'addFloorCorner', point: [1, 1] });
    h = historyReducer(h, { type: 'undo' });
    h = edit(h, { type: 'addFloorCorner', point: [5, 5] });
    expect(canRedo(h)).toBe(false);
    expect(h.present.floor_corners).toEqual([[5, 5]]);
  });

  it('no-op edits do not create undo steps', () => {
    const h = initHistory(baseDoc());
    expect(edit(h, { type: 'updateObject', index: 0, patch: { label: 'couch' } })).toBe(h);
  });

  it('edits with the same tag merge into one step (one drag = one undo)', () => {
    let h = initHistory(baseDoc());
    for (let i = 1; i <= 10; i++) h = edit(h, { type: 'translate', ref: { kind: 'object', index: 1 }, delta: [1, 0] }, 'drag-1');
    h = historyReducer(h, { type: 'endGesture' });
    expect(h.present.objects![1].box).toEqual([20, 10, 50, 60]);
    expect(h.past).toHaveLength(1);
    h = edit(h, { type: 'translate', ref: { kind: 'object', index: 1 }, delta: [1, 0] }, 'drag-1');
    expect(h.past).toHaveLength(2); // after endGesture the same tag opens a new step
    h = historyReducer(h, { type: 'undo' });
    h = historyReducer(h, { type: 'undo' });
    expect(h.present.objects![1].box).toEqual([10, 10, 40, 60]);
    expect(h.present.objects![1].provenance).toEqual(AUTO);
  });

  it(`keeps at least 50 undo steps (limit ${HISTORY_LIMIT})`, () => {
    let h = initHistory(baseDoc());
    for (let i = 0; i < 120; i++) h = edit(h, { type: 'addFloorCorner', point: [i, i] });
    expect(h.past.length).toBe(HISTORY_LIMIT);
    expect(HISTORY_LIMIT).toBeGreaterThanOrEqual(50);
    for (let i = 0; i < 50; i++) h = historyReducer(h, { type: 'undo' });
    expect(h.present.floor_corners).toHaveLength(70);
  });

  it('markSaved tracks the saved document', () => {
    let h = initHistory(baseDoc());
    h = edit(h, { type: 'addFloorCorner', point: [1, 1] });
    const sent = h.present;
    h = edit(h, { type: 'addFloorCorner', point: [2, 2] }); // edited while the save was in flight
    h = historyReducer(h, { type: 'markSaved', doc: sent });
    expect(isDirty(h)).toBe(true);
    h = historyReducer(h, { type: 'undo' });
    expect(isDirty(h)).toBe(false);
  });

  it('load resets history', () => {
    let h = initHistory(baseDoc());
    h = edit(h, { type: 'addFloorCorner', point: [1, 1] });
    h = historyReducer(h, { type: 'load', doc: baseDoc() });
    expect(canUndo(h)).toBe(false);
    expect(isDirty(h)).toBe(false);
  });
});
