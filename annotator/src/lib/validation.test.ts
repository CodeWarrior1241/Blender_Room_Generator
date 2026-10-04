import { describe, expect, it } from 'vitest';
import type { Annotations } from '../types/annotations';
import { describeIssue, issuesByItem, localIssues, parseIssues, refFromLoc, refsForIssue } from './validation';

const doc: Annotations = {
  world: 'w',
  image: 'i.png',
  image_size: [100, 100],
  objects: [
    { id: 'a', label: 'chair', box: [0, 0, 1, 1] },
    { id: 'b', label: 'table', box: [0, 0, 2, 2] },
    { id: 'a', label: 'chair 2', box: [5, 5, 1, 1] },
  ],
};

describe('error locations', () => {
  it('maps list locations to item refs', () => {
    expect(refFromLoc(['objects', 2, 'box'])).toEqual({ kind: 'object', index: 2 });
    expect(refFromLoc(['body', 'openings', 0, 'quad'])).toEqual({ kind: 'opening', index: 0 });
    expect(refFromLoc(['floor_corners', 3, 0])).toEqual({ kind: 'floor_corner', index: 3 });
    expect(refFromLoc(['known_lengths', 1, 'metres'])).toEqual({ kind: 'known_length', index: 1 });
    expect(refFromLoc(['calibration', 'parallel_pairs', 0, 'axis'])).toEqual({ kind: 'parallel_pair', index: 0 });
    expect(refFromLoc(['calibration', 'vertical_lines', 1])).toEqual({ kind: 'vertical_line', index: 1 });
    expect(refFromLoc(['calibration', 'reference', 'metres'])).toEqual({ kind: 'reference' });
    expect(refFromLoc(['boundary_lines', 2, 'pixels'])).toEqual({ kind: 'boundary_line', index: 2 });
    expect(refFromLoc([])).toBeNull();
    expect(refFromLoc(['image_size'])).toBeNull();
  });

  it('maps a duplicate-id model error to every object with that id', () => {
    const refs = refsForIssue({ loc: [], msg: "Value error, duplicate object ids: ['a']" }, doc);
    expect(refs).toEqual([
      { kind: 'object', index: 0 },
      { kind: 'object', index: 2 },
    ]);
  });

  it('describes an issue with the item name and field', () => {
    expect(describeIssue({ loc: ['objects', 1, 'box'], msg: 'Value error, box must be ...' }, doc)).toBe('object "b" › box: box must be ...');
    expect(describeIssue({ loc: [], msg: 'Value error, oops' }, doc)).toBe('oops');
  });

  it('groups issues by item', () => {
    const m = issuesByItem(
      [
        { loc: ['objects', 1, 'id'], msg: 'x' },
        { loc: ['image'], msg: 'y' },
      ],
      doc,
    );
    expect(m.get('object:1')).toHaveLength(1);
    expect(m.get('')).toHaveLength(1);
  });
});

describe('parseIssues', () => {
  it('reads room_gen {ok:false, errors}', () => {
    expect(parseIssues({ ok: false, errors: [{ type: 't', loc: ['objects', 0, 'id'], msg: 'm', input: 'X' }] })).toEqual([
      { type: 't', loc: ['objects', 0, 'id'], msg: 'm', input: 'X', ctx: undefined },
    ]);
  });
  it('reads FastAPI {detail:[...]} and {detail:"..."}', () => {
    expect(parseIssues({ detail: [{ loc: ['body'], msg: 'Field required' }] })[0].msg).toBe('Field required');
    expect(parseIssues({ detail: 'nope' })).toEqual([{ loc: [], msg: 'nope' }]);
  });
  it('ignores junk', () => {
    expect(parseIssues(null)).toEqual([]);
    expect(parseIssues('text')).toEqual([]);
  });
});

describe('localIssues', () => {
  it('flags flipped boxes and duplicate ids like the backend', () => {
    const issues = localIssues(doc);
    expect(issues.map((i) => i.loc)).toEqual([['objects', 2, 'box'], []]);
    expect(issues[1].msg).toBe("Value error, duplicate object ids: ['a']");
  });
  it('accepts a clean document', () => {
    expect(localIssues({ world: 'w', image: 'i', image_size: [1, 1], objects: [{ id: 'a', label: 'a', box: [0, 0, 1, 1] }] })).toEqual([]);
  });
  it('flags boundary lines with fewer than 2 points', () => {
    const d: Annotations = { world: 'w', image: 'i', image_size: [1, 1], boundary_lines: [{ kind: 'wall_floor', pixels: [[0, 0]] as never }] };
    expect(localIssues(d)).toEqual([{ loc: ['boundary_lines', 0, 'pixels'], msg: 'List should have at least 2 items' }]);
    expect(describeIssue(localIssues(d)[0], d)).toBe('boundary line #1 (wall / floor) › pixels: List should have at least 2 items');
  });
  it('flags non-positive metres', () => {
    const d: Annotations = { world: 'w', image: 'i', image_size: [1, 1], calibration: { reference: { pixels: [[0, 1], [0, 0]], metres: 0 } } };
    expect(localIssues(d)[0].loc).toEqual(['calibration', 'reference', 'metres']);
  });
});
