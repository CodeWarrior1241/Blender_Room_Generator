import { describe, expect, it } from 'vitest';
import type { Vec2 } from './geometry';
import { MIN_POLYLINE_POINTS, appendPoint, dedupePolyline, finishPolyline, popPoint } from './polyline';

describe('polyline drawing', () => {
  it('appends clicked points rounded to 0.1 px', () => {
    let pts: Vec2[] = [];
    pts = appendPoint(pts, [10.04, 20.06], 2);
    pts = appendPoint(pts, [100, 50], 2);
    expect(pts).toEqual([
      [10, 20.1],
      [100, 50],
    ]);
  });

  it('ignores a click on the previous point (second click of a double-click)', () => {
    const pts = appendPoint(appendPoint([], [10, 10], 3), [100, 10], 3);
    const again = appendPoint(pts, [101.5, 11], 3);
    expect(again).toBe(pts);
    expect(appendPoint(pts, [104, 10], 3)).toHaveLength(3);
  });

  it('only compares against the last point (a line may come back to its start)', () => {
    let pts: Vec2[] = [];
    for (const p of [
      [0, 0],
      [50, 0],
      [0.5, 0.5],
    ] as Vec2[])
      pts = appendPoint(pts, p, 2);
    expect(pts).toHaveLength(3);
  });

  it('pops the last point (Backspace) and is safe on an empty list', () => {
    expect(popPoint([[1, 1], [2, 2]])).toEqual([[1, 1]]);
    expect(popPoint([])).toEqual([]);
  });

  it('does not finish with fewer than 2 distinct points', () => {
    expect(MIN_POLYLINE_POINTS).toBe(2);
    expect(finishPolyline([])).toBeNull();
    expect(finishPolyline([[5, 5]])).toBeNull();
    expect(finishPolyline([[5, 5], [5.2, 5.1]])).toBeNull(); // the same point twice
  });

  it('finishes with the cleaned points (Enter / double-click)', () => {
    expect(
      finishPolyline([
        [0, 0],
        [0, 0],
        [40, 10],
        [80.04, 20],
      ]),
    ).toEqual([
      [0, 0],
      [40, 10],
      [80, 20],
    ]);
  });

  it('dedupes consecutive points within the tolerance', () => {
    expect(dedupePolyline([[0, 0], [1, 0], [10, 0]], 2)).toEqual([[0, 0], [10, 0]]);
  });
});
