import { describe, expect, it } from 'vitest';
import { ID_PATTERN, idProblem, isValidId, slugify, uniqueId } from './slug';

describe('slugify', () => {
  // expected values produced by room_gen.indexed.slugify
  const cases: [string, string][] = [
    ['Coffee Table', 'coffee-table'],
    ['  table lamp ', 'table-lamp'],
    ['TV/Stand #2', 'tv-stand-2'],
    ['Ünïcode chair', 'n-code-chair'],
    ['side_table', 'side-table'],
    ['a'.repeat(90), 'a'.repeat(80)],
    ['x'.repeat(79) + ' y', 'x'.repeat(79) + '-'],
  ];
  it.each(cases)('%j -> %j (same as the backend)', (label, slug) => {
    expect(slugify(label)).toBe(slug);
  });

  it('never returns an invalid id', () => {
    for (const s of ['---', '', '   ', '!!!', '_x', 'Ünï']) {
      const id = slugify(s);
      expect(isValidId(id)).toBe(true);
      expect(ID_PATTERN.test(id)).toBe(true);
    }
    expect(slugify('---')).toBe('object');
  });
});

describe('uniqueId', () => {
  it('returns the base when free', () => {
    expect(uniqueId('sofa', ['chair'])).toBe('sofa');
  });
  it('suffixes -2, -3 ... when taken', () => {
    expect(uniqueId('sofa', ['sofa'])).toBe('sofa-2');
    expect(uniqueId('sofa', ['sofa', 'sofa-2', 'sofa-3'])).toBe('sofa-4');
  });
  it('slugifies an invalid base first', () => {
    expect(uniqueId('Floor Lamp', ['floor-lamp'])).toBe('floor-lamp-2');
  });
  it('stays within 80 characters', () => {
    const long = 'a'.repeat(80);
    const id = uniqueId(long, [long]);
    expect(id.length).toBeLessThanOrEqual(80);
    expect(id.endsWith('-2')).toBe(true);
    expect(isValidId(id)).toBe(true);
  });
});

describe('idProblem', () => {
  it('accepts a valid unused id', () => expect(idProblem('side-table_2', ['sofa'])).toBeNull());
  it('rejects bad patterns', () => {
    expect(idProblem('Sofa', [])).toMatch(/pattern|must match/);
    expect(idProblem('-sofa', [])).not.toBeNull();
    expect(idProblem('', [])).not.toBeNull();
    expect(idProblem('a'.repeat(81), [])).not.toBeNull();
  });
  it('rejects duplicates', () => expect(idProblem('sofa', ['sofa'])).toMatch(/already used/));
});
