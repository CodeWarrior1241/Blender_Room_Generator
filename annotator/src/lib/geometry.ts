// Pure geometry helpers. Image coordinates are native pixels of the source photo, origin top-left,
// `[u, v]`. Screen coordinates are CSS pixels relative to the viewport element's top-left corner.

export type Vec2 = [number, number];
export type Box = [number, number, number, number];
export type Line = [Vec2, Vec2];
export type Quad = [Vec2, Vec2, Vec2, Vec2];

/** screen = image * scale + [tx, ty] */
export interface View {
  scale: number;
  tx: number;
  ty: number;
}

export const MIN_SCALE = 0.01;
export const MAX_SCALE = 64;

export function clampScale(s: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
}

export function imageToScreen(view: View, p: Vec2): Vec2 {
  return [p[0] * view.scale + view.tx, p[1] * view.scale + view.ty];
}

export function screenToImage(view: View, p: Vec2): Vec2 {
  return [(p[0] - view.tx) / view.scale, (p[1] - view.ty) / view.scale];
}

/** Zoom by `factor` keeping the image point under `screenPt` fixed on screen. */
export function zoomAt(view: View, screenPt: Vec2, factor: number): View {
  const scale = clampScale(view.scale * factor);
  const [u, v] = screenToImage(view, screenPt);
  return { scale, tx: screenPt[0] - u * scale, ty: screenPt[1] - v * scale };
}

export function panBy(view: View, dx: number, dy: number): View {
  return { scale: view.scale, tx: view.tx + dx, ty: view.ty + dy };
}

/** Largest scale that shows the whole image inside the viewport with `margin` px, centred. */
export function fitView(imageW: number, imageH: number, viewW: number, viewH: number, margin = 16): View {
  if (imageW <= 0 || imageH <= 0 || viewW <= 0 || viewH <= 0) return { scale: 1, tx: 0, ty: 0 };
  const availW = Math.max(1, viewW - 2 * margin);
  const availH = Math.max(1, viewH - 2 * margin);
  const scale = clampScale(Math.min(availW / imageW, availH / imageH));
  return { scale, tx: (viewW - imageW * scale) / 2, ty: (viewH - imageH * scale) / 2 };
}

/** Multiplicative zoom factor for a wheel event; deltaMode 1 = lines, 2 = pages. */
export function wheelZoomFactor(deltaY: number, deltaMode = 0): number {
  const px = deltaMode === 1 ? deltaY * 16 : deltaMode === 2 ? deltaY * 400 : deltaY;
  const clamped = Math.max(-300, Math.min(300, px));
  return Math.exp(-clamped * 0.0015);
}

export function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

export function roundPt(p: Vec2): Vec2 {
  return [round1(p[0]), round1(p[1])];
}

export function clampPoint(p: Vec2, w: number, h: number): Vec2 {
  return [Math.min(w, Math.max(0, p[0])), Math.min(h, Math.max(0, p[1]))];
}

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

/**
 * Box from two opposite corners given in any order: always x1 > x0 and y1 > y0
 * (room_gen.models.ObjectAnnotation rejects anything else). Degenerate extents grow to `minSize`.
 */
export function normalizeBox(a: Vec2, b: Vec2, minSize = 1): Box {
  let x0 = round1(Math.min(a[0], b[0]));
  let x1 = round1(Math.max(a[0], b[0]));
  let y0 = round1(Math.min(a[1], b[1]));
  let y1 = round1(Math.max(a[1], b[1]));
  if (x1 - x0 < minSize) x1 = round1(x0 + minSize);
  if (y1 - y0 < minSize) y1 = round1(y0 + minSize);
  return [x0, y0, x1, y1];
}

/** Re-order a possibly flipped `[x0, y0, x1, y1]`. */
export function normalizeBoxArray(box: readonly number[], minSize = 1): Box {
  return normalizeBox([box[0], box[1]], [box[2], box[3]], minSize);
}

/** Corners of a box clockwise from top-left: TL, TR, BR, BL. */
export function boxCorners(box: Box): Quad {
  const [x0, y0, x1, y1] = box;
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

/** The corner diagonally opposite corner `i` (0 TL, 1 TR, 2 BR, 3 BL). */
export function oppositeCorner(box: Box, i: number): Vec2 {
  return boxCorners(box)[(((i + 2) % 4) + 4) % 4];
}

/** Axis-aligned rectangle from two clicks as a quad TL, TR, BR, BL (any click order). */
export function quadFromTwoClicks(a: Vec2, b: Vec2): Quad {
  const [x0, y0, x1, y1] = [
    round1(Math.min(a[0], b[0])),
    round1(Math.min(a[1], b[1])),
    round1(Math.max(a[0], b[0])),
    round1(Math.max(a[1], b[1])),
  ];
  return [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
}

/** Order a segment so the lower image point (larger v, i.e. nearer the floor) comes first. */
export function orderBottomFirst(a: Vec2, b: Vec2): Line {
  return a[1] >= b[1] ? [a, b] : [b, a];
}

export function translatePoint(p: Vec2, d: Vec2): Vec2 {
  return [round1(p[0] + d[0]), round1(p[1] + d[1])];
}

export function translateBox(box: Box, d: Vec2): Box {
  return [round1(box[0] + d[0]), round1(box[1] + d[1]), round1(box[2] + d[0]), round1(box[3] + d[1])];
}

export function bounds(points: readonly Vec2[]): Box {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function boxArea(box: Box): number {
  return Math.max(0, box[2] - box[0]) * Math.max(0, box[3] - box[1]);
}

export function midpoint(a: Vec2, b: Vec2): Vec2 {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

/** Snap `b` onto the image-vertical line through `a` (keeps b's v). */
export function snapVertical(a: Vec2, b: Vec2): Vec2 {
  return [a[0], b[1]];
}

/** Intersection of the infinite lines through two segments (null when parallel). */
export function lineIntersection(l1: Line, l2: Line): Vec2 | null {
  const [[x1, y1], [x2, y2]] = l1;
  const [[x3, y3], [x4, y4]] = l2;
  const den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(den) < 1e-9) return null;
  const a = x1 * y2 - y1 * x2;
  const b = x3 * y4 - y3 * x4;
  return [(a * (x3 - x4) - (x1 - x2) * b) / den, (a * (y3 - y4) - (y1 - y2) * b) / den];
}
