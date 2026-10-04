// Click-by-click polyline drawing (Boundary tool). Pure functions; the UI keeps the point list.
//
//   click        -> appendPoint   (a click on the last point is ignored: the 2nd click of a double-click)
//   Enter / dblclick -> finishPolyline (null while fewer than 2 distinct points: keep drawing)
//   Backspace    -> popPoint
//   Esc          -> drop the list

import { type Vec2, distance, roundPt } from './geometry';

export const MIN_POLYLINE_POINTS = 2;

/** Add a clicked point unless it lands within `tol` (image px) of the previous point. */
export function appendPoint(points: readonly Vec2[], p: Vec2, tol: number): Vec2[] {
  const q = roundPt(p);
  const last = points[points.length - 1];
  if (last && distance(last, q) <= tol) return points as Vec2[];
  return [...points, q];
}

export function popPoint(points: readonly Vec2[]): Vec2[] {
  return points.slice(0, -1);
}

/** Drop consecutive points within `tol` of each other. */
export function dedupePolyline(points: readonly Vec2[], tol = 0.5): Vec2[] {
  const out: Vec2[] = [];
  for (const p of points) {
    const q = roundPt(p);
    if (out.length === 0 || distance(out[out.length - 1], q) > tol) out.push(q);
  }
  return out;
}

/** The polyline to commit, or null when it has fewer than 2 distinct points (keep drawing). */
export function finishPolyline(points: readonly Vec2[], tol = 0.5): Vec2[] | null {
  const clean = dedupePolyline(points, tol);
  return clean.length >= MIN_POLYLINE_POINTS ? clean : null;
}
