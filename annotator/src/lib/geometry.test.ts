import { describe, expect, it } from 'vitest';
import {
  type Vec2,
  type View,
  boxCorners,
  clampScale,
  fitView,
  imageToScreen,
  lineIntersection,
  MAX_SCALE,
  MIN_SCALE,
  normalizeBox,
  normalizeBoxArray,
  oppositeCorner,
  orderBottomFirst,
  panBy,
  quadFromTwoClicks,
  screenToImage,
  wheelZoomFactor,
  zoomAt,
} from './geometry';

const close = (a: Vec2, b: Vec2) => {
  expect(a[0]).toBeCloseTo(b[0], 9);
  expect(a[1]).toBeCloseTo(b[1], 9);
};

describe('screen <-> image transforms', () => {
  const views: View[] = [
    { scale: 1, tx: 0, ty: 0 },
    { scale: 0.25, tx: 37.5, ty: -12 },
    { scale: 3.7, tx: -1500, ty: 220.25 },
  ];
  const pts: Vec2[] = [
    [0, 0],
    [1280, 960],
    [17.3, 911.9],
    [-50, 4000],
  ];

  it('round-trips image -> screen -> image for any view', () => {
    for (const v of views) for (const p of pts) close(screenToImage(v, imageToScreen(v, p)), p);
  });

  it('round-trips screen -> image -> screen', () => {
    for (const v of views) for (const p of pts) close(imageToScreen(v, screenToImage(v, p)), p);
  });

  it('maps the image origin to the translation', () => {
    expect(imageToScreen({ scale: 2, tx: 10, ty: 20 }, [0, 0])).toEqual([10, 20]);
    expect(imageToScreen({ scale: 2, tx: 10, ty: 20 }, [5, 5])).toEqual([20, 30]);
  });

  it('zoomAt keeps the image point under the cursor fixed', () => {
    const v: View = { scale: 0.5, tx: 30, ty: 40 };
    const cursor: Vec2 = [321, 123];
    const before = screenToImage(v, cursor);
    for (const f of [0.5, 1.1, 2, 10]) {
      const z = zoomAt(v, cursor, f);
      close(screenToImage(z, cursor), before);
      expect(z.scale).toBeCloseTo(clampScale(0.5 * f));
    }
  });

  it('zoomAt clamps the scale', () => {
    expect(zoomAt({ scale: 1, tx: 0, ty: 0 }, [0, 0], 1e9).scale).toBe(MAX_SCALE);
    expect(zoomAt({ scale: 1, tx: 0, ty: 0 }, [0, 0], 1e-9).scale).toBe(MIN_SCALE);
  });

  it('panBy moves the translation only', () => {
    expect(panBy({ scale: 2, tx: 1, ty: 2 }, 10, -5)).toEqual({ scale: 2, tx: 11, ty: -3 });
  });

  it('fitView centres the whole image', () => {
    const v = fitView(1280, 960, 800, 600, 0);
    expect(v.scale).toBeCloseTo(0.625);
    close(imageToScreen(v, [0, 0]), [0, 0]);
    close(imageToScreen(v, [1280, 960]), [800, 600]);
    const tall = fitView(1000, 1000, 800, 400, 0);
    expect(tall.scale).toBeCloseTo(0.4);
    expect(tall.tx).toBeCloseTo(200);
  });

  it('wheel zoom factor is >1 for wheel up, <1 for wheel down, symmetric', () => {
    expect(wheelZoomFactor(-100)).toBeGreaterThan(1);
    expect(wheelZoomFactor(100)).toBeLessThan(1);
    expect(wheelZoomFactor(-100) * wheelZoomFactor(100)).toBeCloseTo(1);
    expect(wheelZoomFactor(3, 1)).toBeCloseTo(wheelZoomFactor(48, 0));
  });
});

describe('box normalisation', () => {
  const a: Vec2 = [100, 200];
  const b: Vec2 = [300, 450];

  it('gives x1 > x0 and y1 > y0 for a drag in any direction', () => {
    const drags: [Vec2, Vec2][] = [
      [a, b],
      [b, a],
      [
        [a[0], b[1]],
        [b[0], a[1]],
      ],
      [
        [b[0], a[1]],
        [a[0], b[1]],
      ],
    ];
    for (const [p, q] of drags) {
      const box = normalizeBox(p, q);
      expect(box).toEqual([100, 200, 300, 450]);
      expect(box[2]).toBeGreaterThan(box[0]);
      expect(box[3]).toBeGreaterThan(box[1]);
    }
  });

  it('grows a degenerate box to the minimum size', () => {
    const box = normalizeBox([10, 10], [10, 10]);
    expect(box[2]).toBeGreaterThan(box[0]);
    expect(box[3]).toBeGreaterThan(box[1]);
  });

  it('re-orders a flipped [x0,y0,x1,y1]', () => {
    expect(normalizeBoxArray([300, 450, 100, 200])).toEqual([100, 200, 300, 450]);
  });

  it('rounds to 0.1 px', () => {
    expect(normalizeBox([1.234, 2.345], [10.06, 20.04])).toEqual([1.2, 2.3, 10.1, 20]);
  });

  it('opposite corners', () => {
    const box = normalizeBox(a, b);
    expect(boxCorners(box)).toEqual([
      [100, 200],
      [300, 200],
      [300, 450],
      [100, 450],
    ]);
    expect(oppositeCorner(box, 0)).toEqual([300, 450]);
    expect(oppositeCorner(box, 1)).toEqual([100, 450]);
    expect(oppositeCorner(box, 2)).toEqual([100, 200]);
    expect(oppositeCorner(box, 3)).toEqual([300, 200]);
  });
});

describe('quad from two clicks', () => {
  it('is an axis-aligned TL, TR, BR, BL quad whatever the click order', () => {
    const expected = [
      [10, 20],
      [110, 20],
      [110, 220],
      [10, 220],
    ];
    expect(quadFromTwoClicks([10, 20], [110, 220])).toEqual(expected);
    expect(quadFromTwoClicks([110, 220], [10, 20])).toEqual(expected);
    expect(quadFromTwoClicks([110, 20], [10, 220])).toEqual(expected);
    expect(quadFromTwoClicks([10, 220], [110, 20])).toEqual(expected);
  });

  it('has 4 points', () => {
    expect(quadFromTwoClicks([0, 0], [5, 5])).toHaveLength(4);
  });
});

describe('orderBottomFirst', () => {
  it('puts the larger v first', () => {
    expect(orderBottomFirst([5, 900], [6, 100])).toEqual([
      [5, 900],
      [6, 100],
    ]);
    expect(orderBottomFirst([6, 100], [5, 900])).toEqual([
      [5, 900],
      [6, 100],
    ]);
  });
});

describe('lineIntersection', () => {
  it('finds the vanishing point of two converging segments', () => {
    expect(lineIntersection([[0, 0], [10, 10]], [[0, 10], [10, 0]])).toEqual([5, 5]);
    const vp = lineIntersection([[0, 0], [100, 10]], [[0, 100], [100, 80]])!;
    expect(vp[0]).toBeCloseTo(1000 / 3); // y = 0.1x meets y = 100 - 0.2x
    expect(vp[1]).toBeCloseTo(100 / 3);
    expect(lineIntersection([[0, 0], [1, 0]], [[0, 1], [1, 1]])).toBeNull();
  });
});
