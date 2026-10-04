import { type PointerEvent as ReactPointerEvent, type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Annotations } from '../types/annotations';
import type { CameraOverlay } from '../types/api';
import {
  BOUNDARY_LABEL,
  type Axis,
  type BoundaryKind,
  type EditAction,
  type ItemRef,
  boundariesOf,
  cornersOf,
  isAuto,
  lengthsOf,
  objectsOf,
  openingsOf,
  pairsOf,
  referenceOf,
  refKey,
  sameRef,
  verticalsOf,
} from '../lib/annotations';
import {
  type Box,
  type Line,
  type Vec2,
  type View,
  boxArea,
  boxCorners,
  clampPoint,
  distance,
  fitView,
  lineIntersection,
  midpoint,
  normalizeBox,
  oppositeCorner,
  orderBottomFirst,
  quadFromTwoClicks,
  round1,
  roundPt,
  screenToImage,
  snapVertical,
  wheelZoomFactor,
  zoomAt,
} from '../lib/geometry';
import { AXIS_COLOR, BOUNDARY_COLOR, BOUNDARY_SHORT, type Draft, type Layers, type Tool, isTextInput } from '../lib/ui';

export interface ViewportProps {
  imageUrl: string;
  /** output/world/overlay.png, shown instead of the photo when layers.overlayBackground */
  overlayUrl: string | null;
  imageSize: [number, number];
  doc: Annotations;
  tool: Tool;
  axis: Axis;
  selection: ItemRef | null;
  draft: Draft | null;
  layers: Layers;
  camera: CameraOverlay | null;
  errorKeys: ReadonlySet<string>;
  /** increment to re-fit the image into the viewport */
  fitSignal: number;
  onSelect: (ref: ItemRef | null) => void;
  onEdit: (edit: EditAction, tag?: string) => void;
  onGestureEnd: () => void;
  onDraft: (draft: Draft) => void;
  /** Boundary tool: kind of the line being drawn and its points so far (state lives in App). */
  boundaryKind: BoundaryKind;
  polyline: readonly Vec2[];
  /** a click while drawing a boundary line; `tol` = image px that count as "the same point" */
  onBoundaryPoint: (p: Vec2, tol: number) => void;
  onBoundaryFinish: () => void;
}

type Gesture =
  | { type: 'pan'; start: Vec2; startView: View }
  | { type: 'translate'; ref: ItemRef; origin: Vec2; applied: Vec2; tag: string }
  | { type: 'handle'; ref: ItemRef; handle: number; anchor?: Vec2; tag: string }
  | { type: 'rect'; start: Vec2 }
  | { type: 'click2'; first: Vec2; downScreen: Vec2 };

interface Hit {
  ref: ItemRef;
  handle: number | 'body';
}

function parseHit(target: EventTarget | null): Hit | null {
  const el = target instanceof Element ? target.closest('[data-hit]') : null;
  if (!el) return null;
  const [kind, idx] = (el.getAttribute('data-hit') ?? '').split(':');
  const h = el.getAttribute('data-handle') ?? 'body';
  const ref = (kind === 'reference' ? { kind: 'reference' } : { kind, index: Number(idx) }) as ItemRef;
  return { ref, handle: h === 'body' ? 'body' : Number(h) };
}

const pts = (list: readonly Vec2[]) => list.map((p) => `${p[0]},${p[1]}`).join(' ');

let tagSeq = 0;

export default function Viewport(props: ViewportProps) {
  const { imageUrl, overlayUrl, imageSize, doc, tool, axis, selection, draft, layers, camera, errorKeys, fitSignal } = props;
  const { onSelect, onEdit, onGestureEnd, onDraft, boundaryKind, polyline, onBoundaryPoint, onBoundaryFinish } = props;
  const [W, H] = imageSize;

  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState<[number, number]>([0, 0]);
  const [view, setView] = useState<View>({ scale: 1, tx: 0, ty: 0 });
  const viewRef = useRef(view);
  viewRef.current = view;
  const fittedKey = useRef('');
  const gesture = useRef<Gesture | null>(null);
  const [hover, setHover] = useState<Vec2 | null>(null);
  const [clicks, setClicks] = useState<Vec2[]>([]);
  const [firstLine, setFirstLine] = useState<Line | null>(null);
  const [rect, setRect] = useState<[Vec2, Vec2] | null>(null);
  const [panning, setPanning] = useState(false);
  const [spaceHeld, setSpaceHeld] = useState(false);
  const spaceRef = useRef(false);
  const [imageError, setImageError] = useState(false);

  // ---- size, fit -------------------------------------------------------------------------
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const update = () => setSize([el.clientWidth, el.clientHeight]);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fit = useCallback(() => {
    if (size[0] > 0 && size[1] > 0 && W > 0 && H > 0) setView(fitView(W, H, size[0], size[1], 16));
  }, [size, W, H]);

  useEffect(() => {
    const key = `${imageUrl}|${W}x${H}`;
    if (size[0] > 0 && size[1] > 0 && fittedKey.current !== key) {
      fittedKey.current = key;
      fit();
    }
  }, [imageUrl, W, H, size, fit]);

  const lastFitSignal = useRef(fitSignal);
  useEffect(() => {
    if (lastFitSignal.current !== fitSignal) {
      lastFitSignal.current = fitSignal;
      fit();
    }
  }, [fitSignal, fit]);

  useEffect(() => setImageError(false), [imageUrl, overlayUrl, layers.overlayBackground]);

  // ---- reset in-progress drawing when the tool changes or on Escape -------------------------
  const resetDrawing = useCallback(() => {
    setClicks([]);
    setFirstLine(null);
    setRect(null);
    if (gesture.current && (gesture.current.type === 'rect' || gesture.current.type === 'click2')) gesture.current = null;
  }, []);
  useEffect(resetDrawing, [tool, imageUrl, resetDrawing]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'Escape') resetDrawing();
      if (e.key === ' ' && !isTextInput(e.target)) {
        if (!spaceRef.current) setSpaceHeld(true);
        spaceRef.current = true;
        e.preventDefault();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.key === ' ') {
        spaceRef.current = false;
        setSpaceHeld(false);
      }
    };
    const blur = () => {
      spaceRef.current = false;
      setSpaceHeld(false);
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, [resetDrawing]);

  // ---- wheel zoom (native listener: React's wheel handler is passive) -----------------------
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      const at: Vec2 = [e.clientX - r.left, e.clientY - r.top];
      setView((v) => zoomAt(v, at, wheelZoomFactor(e.deltaY, e.deltaMode)));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, []);

  // ---- pointer handling ----------------------------------------------------------------------
  const local = (e: { clientX: number; clientY: number }): Vec2 => {
    const r = svgRef.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const clampImg = (p: Vec2): Vec2 => roundPt(clampPoint(p, W, H));

  const constrain = (p: Vec2, first: Vec2 | undefined, shift: boolean): Vec2 =>
    tool === 'reference' && shift && first ? snapVertical(first, p) : p;

  function completeTwoPoint(a: Vec2, b: Vec2) {
    setClicks([]);
    if (distance(a, b) * viewRef.current.scale < 3) return; // a double click, not a shape
    switch (tool) {
      case 'opening': {
        const q = quadFromTwoClicks(clampImg(a), clampImg(b));
        if (q[1][0] - q[0][0] < 1 || q[3][1] - q[0][1] < 1) return;
        onDraft({ kind: 'opening', quad: q });
        return;
      }
      case 'reference':
        onDraft({ kind: 'reference', pixels: orderBottomFirst(roundPt(a), roundPt(b)) });
        return;
      case 'length':
        onDraft({ kind: 'known_length', pixels: [roundPt(a), roundPt(b)] });
        return;
      case 'calib': {
        const line: Line = [roundPt(a), roundPt(b)];
        if (!firstLine) setFirstLine(line);
        else {
          onEdit({ type: 'addParallelPair', value: { axis, lines: [firstLine, line] } });
          setFirstLine(null);
        }
        return;
      }
      default:
        return;
    }
  }

  function startPan(e: ReactPointerEvent<SVGSVGElement>, s: Vec2) {
    gesture.current = { type: 'pan', start: s, startView: viewRef.current };
    setPanning(true);
    svgRef.current?.setPointerCapture(e.pointerId);
  }

  function onPointerDown(e: ReactPointerEvent<SVGSVGElement>) {
    const s = local(e);
    const p = screenToImage(viewRef.current, s);
    if (e.button === 1 || (e.button === 0 && spaceRef.current)) {
      e.preventDefault();
      startPan(e, s);
      return;
    }
    if (e.button !== 0) return;
    (document.activeElement as HTMLElement | null)?.blur?.(); // commit any side-panel field
    const tag = `drag-${++tagSeq}`;
    switch (tool) {
      case 'select': {
        const hit = parseHit(e.target);
        if (!hit) {
          onSelect(null);
          startPan(e, s);
          return;
        }
        onSelect(hit.ref);
        svgRef.current?.setPointerCapture(e.pointerId);
        if (hit.handle === 'body') {
          gesture.current = { type: 'translate', ref: hit.ref, origin: p, applied: [0, 0], tag };
        } else {
          const obj = hit.ref.kind === 'object' ? objectsOf(doc)[hit.ref.index] : undefined;
          gesture.current = {
            type: 'handle',
            ref: hit.ref,
            handle: hit.handle,
            anchor: obj ? oppositeCorner(obj.box as Box, hit.handle) : undefined,
            tag,
          };
        }
        return;
      }
      case 'box': {
        const start = clampImg(p);
        gesture.current = { type: 'rect', start };
        setRect([start, start]);
        svgRef.current?.setPointerCapture(e.pointerId);
        return;
      }
      case 'corner':
        onEdit({ type: 'addFloorCorner', point: roundPt(p) });
        return;
      case 'boundary': {
        // Shift keeps a corner (wall/wall) line image-vertical
        const last = polyline[polyline.length - 1];
        const pt = boundaryKind === 'wall_wall' && e.shiftKey && last ? snapVertical(last, p) : p;
        onBoundaryPoint(roundPt(pt), 4 / viewRef.current.scale);
        return;
      }
      default: {
        const first = clicks[0];
        const pt = constrain(p, first, e.shiftKey);
        if (!first) {
          setClicks([pt]);
          gesture.current = { type: 'click2', first: pt, downScreen: s };
          svgRef.current?.setPointerCapture(e.pointerId);
        } else {
          completeTwoPoint(first, pt);
        }
      }
    }
  }

  function onPointerMove(e: ReactPointerEvent<SVGSVGElement>) {
    const s = local(e);
    const p = screenToImage(viewRef.current, s);
    setHover(p);
    const g = gesture.current;
    if (!g) return;
    switch (g.type) {
      case 'pan':
        setView({ scale: g.startView.scale, tx: g.startView.tx + s[0] - g.start[0], ty: g.startView.ty + s[1] - g.start[1] });
        return;
      case 'translate': {
        const total: Vec2 = [round1(p[0] - g.origin[0]), round1(p[1] - g.origin[1])];
        const step: Vec2 = [round1(total[0] - g.applied[0]), round1(total[1] - g.applied[1])];
        if (step[0] !== 0 || step[1] !== 0) {
          g.applied = total;
          onEdit({ type: 'translate', ref: g.ref, delta: step }, g.tag);
        }
        return;
      }
      case 'handle': {
        const to = g.ref.kind === 'object' || g.ref.kind === 'opening' ? clampImg(p) : roundPt(p);
        onEdit({ type: 'moveHandle', ref: g.ref, handle: g.handle, to, anchor: g.anchor }, g.tag);
        return;
      }
      case 'rect':
        setRect([g.start, clampImg(p)]);
        return;
      case 'click2':
        return;
    }
  }

  function endGesture(e: ReactPointerEvent<SVGSVGElement>, cancelled: boolean) {
    const g = gesture.current;
    gesture.current = null;
    if (svgRef.current?.hasPointerCapture(e.pointerId)) svgRef.current.releasePointerCapture(e.pointerId);
    if (!g) return;
    const s = local(e);
    const p = screenToImage(viewRef.current, s);
    switch (g.type) {
      case 'pan':
        setPanning(false);
        return;
      case 'translate':
      case 'handle':
        onGestureEnd();
        return;
      case 'rect': {
        setRect(null);
        if (cancelled) return;
        const b = clampImg(p);
        const sc = viewRef.current.scale;
        if (Math.abs(b[0] - g.start[0]) * sc >= 4 && Math.abs(b[1] - g.start[1]) * sc >= 4) {
          onDraft({ kind: 'object', box: normalizeBox(g.start, b) });
        }
        return;
      }
      case 'click2':
        // press-drag-release draws the segment in one go
        if (!cancelled && distance(s, g.downScreen) > 6) completeTwoPoint(g.first, constrain(p, g.first, e.shiftKey));
        return;
    }
  }

  // ---- rendering -------------------------------------------------------------------------------
  const k = 1 / view.scale; // image units per screen pixel
  const handleR = 5.5 * k;
  const fontSize = 12 * k;
  const select = tool === 'select';

  const visible = (prov: Parameters<typeof isAuto>[0]) => (isAuto(prov) ? layers.auto : layers.human);

  const cls = (ref: ItemRef, base: string, auto: boolean) =>
    [base, auto ? 'auto' : 'human', sameRef(ref, selection) ? 'selected' : '', errorKeys.has(refKey(ref)) ? 'err' : '']
      .filter(Boolean)
      .join(' ');

  const label = (at: Vec2, text: string, color?: string, anchor: 'start' | 'middle' = 'start'): ReactNode =>
    layers.labels ? (
      <text className="lbl" x={at[0]} y={at[1]} fontSize={fontSize} fill={color} textAnchor={anchor} strokeWidth={3 * k}>
        {text}
      </text>
    ) : null;

  const errBadge = (ref: ItemRef, at: Vec2): ReactNode =>
    errorKeys.has(refKey(ref)) ? (
      <g className="err-badge" transform={`translate(${at[0]} ${at[1]}) scale(${k})`}>
        <circle r={8} />
        <text y={4} textAnchor="middle" fontSize={12}>
          !
        </text>
      </g>
    ) : null;

  const handleDots = (ref: ItemRef, points: readonly Vec2[], indices?: readonly number[]): ReactNode =>
    select && sameRef(ref, selection)
      ? points.map((p, i) => (
          <circle
            key={`h${i}`}
            className="handle"
            cx={p[0]}
            cy={p[1]}
            r={handleR}
            data-hit={refKey(ref)}
            data-handle={indices ? indices[i] : i}
          />
        ))
      : null;

  const segment = (a: Vec2, b: Vec2, className: string, extra?: Record<string, unknown>) => (
    <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className={className} {...extra} />
  );

  const objects = useMemo(
    () =>
      objectsOf(doc)
        .map((o, index) => ({ o, index, area: boxArea(o.box as Box) }))
        .sort((a, b) => b.area - a.area),
    [doc],
  );

  const vpGuides = (lines: readonly Line[], color: string): ReactNode => {
    if (lines.length < 2) return null;
    const vp = lineIntersection(lines[0], lines[1]);
    const far = 6 * Math.max(W, H);
    if (!vp || Math.abs(vp[0] - W / 2) > far || Math.abs(vp[1] - H / 2) > far) return null;
    return lines.map((l, i) => {
      const near = distance(l[0], vp) < distance(l[1], vp) ? l[0] : l[1];
      return <line key={`vp${i}`} className="vp-guide" x1={near[0]} y1={near[1]} x2={vp[0]} y2={vp[1]} stroke={color} />;
    });
  };

  const hoverPt = hover && clicks[0] ? constrain(hover, clicks[0], false) : hover;
  const cursor = panning ? 'grabbing' : spaceHeld ? 'grab' : select ? 'default' : 'crosshair';
  const showOverlay = layers.overlayBackground && !!overlayUrl;

  return (
    <div className="viewport" ref={wrapRef}>
      <svg
        ref={svgRef}
        className={`stage tool-${tool}`}
        style={{ cursor }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => endGesture(e, false)}
        onPointerCancel={(e) => endGesture(e, true)}
        onPointerLeave={() => setHover(null)}
        onContextMenu={(e) => e.preventDefault()}
        onDoubleClick={() => {
          if (tool === 'boundary') onBoundaryFinish();
        }}
        onAuxClick={(e) => e.preventDefault()}
      >
        <g transform={`matrix(${view.scale} 0 0 ${view.scale} ${view.tx} ${view.ty})`}>
          <rect className="image-frame" x={0} y={0} width={W} height={H} />
          <image
            href={showOverlay ? overlayUrl! : imageUrl}
            x={0}
            y={0}
            width={W}
            height={H}
            preserveAspectRatio="none"
            onError={() => setImageError(true)}
            onLoad={() => setImageError(false)}
          />

          <defs>
            <clipPath id="image-clip">
              <rect x={0} y={0} width={W} height={H} />
            </clipPath>
          </defs>
          {camera && layers.grid && (
            <g className="grid" clipPath="url(#image-clip)">
              {camera.floor_grid.map((l, i) => (
                <polyline key={i} points={pts(l)} />
              ))}
            </g>
          )}
          {camera && layers.wireframe && (
            <g className="wire" clipPath="url(#image-clip)">
              {camera.wireframe.map((l, i) => (
                <polyline key={i} points={pts(l)} />
              ))}
            </g>
          )}

          <g className={`items ${select ? 'interactive' : ''}`}>
            {objects.map(({ o, index }) => {
              const ref: ItemRef = { kind: 'object', index };
              const auto = isAuto(o.provenance);
              if (!visible(o.provenance) && !sameRef(ref, selection)) return null;
              const [x0, y0, x1, y1] = o.box;
              return (
                <g key={`o${index}`} className={cls(ref, 'obj', auto)} data-hit={refKey(ref)} data-handle="body">
                  <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} />
                  {label([x0 + 3 * k, y0 + fontSize + 2 * k], o.id)}
                  {errBadge(ref, [x1, y0])}
                </g>
              );
            })}

            {openingsOf(doc).map((o, index) => {
              const ref: ItemRef = { kind: 'opening', index };
              const auto = isAuto(o.provenance);
              if (!visible(o.provenance) && !sameRef(ref, selection)) return null;
              const q = o.quad as Vec2[];
              return (
                <g key={`op${index}`} className={cls(ref, 'opening', auto)} data-hit={refKey(ref)} data-handle="body">
                  <polygon points={pts(q)} />
                  {label([q[0][0] + 3 * k, q[0][1] + fontSize + 2 * k], `${o.kind}${o.wall_hint ? ` · ${o.wall_hint}` : ''}`)}
                  {errBadge(ref, q[1])}
                </g>
              );
            })}

            {boundariesOf(doc).map((b, index) => {
              const ref: ItemRef = { kind: 'boundary_line', index };
              const auto = isAuto(b.provenance);
              if (!visible(b.provenance) && !sameRef(ref, selection)) return null;
              const line = b.pixels as Vec2[];
              const color = BOUNDARY_COLOR[b.kind] ?? 'white';
              return (
                <g key={`bl${index}`} className={cls(ref, 'boundary', auto)} data-hit={refKey(ref)} data-handle="body" style={{ color }}>
                  <polyline className="hit" points={pts(line)} />
                  <polyline className="halo" points={pts(line)} />
                  <polyline className="shape" points={pts(line)} />
                  {line.map((p, i) => (
                    <circle key={i} className="vertex" cx={p[0]} cy={p[1]} r={2.5 * k} />
                  ))}
                  {label([line[0][0] + 6 * k, line[0][1] - 6 * k], BOUNDARY_SHORT[b.kind] ?? b.kind, color)}
                  {errBadge(ref, line[line.length - 1])}
                </g>
              );
            })}

            {layers.human && cornersOf(doc).length > 1 && <polyline className="floor-trace" points={pts(cornersOf(doc))} />}
            {layers.human &&
              cornersOf(doc).map((p, index) => {
                const ref: ItemRef = { kind: 'floor_corner', index };
                return (
                  <g key={`fc${index}`} className={cls(ref, 'corner', false)} data-hit={refKey(ref)} data-handle="body">
                    <circle cx={p[0]} cy={p[1]} r={handleR * 1.1} />
                    {label([p[0] + 8 * k, p[1] - 6 * k], String(index + 1))}
                    {errBadge(ref, p)}
                  </g>
                );
              })}

            {layers.human &&
              lengthsOf(doc).map((kl, index) => {
                const ref: ItemRef = { kind: 'known_length', index };
                const [a, b] = kl.pixels as Line;
                return (
                  <g key={`kl${index}`} className={cls(ref, 'length', false)} data-hit={refKey(ref)} data-handle="body">
                    {segment(a, b, 'hit')}
                    {segment(a, b, 'shape')}
                    <circle className="end" cx={a[0]} cy={a[1]} r={3 * k} />
                    <circle className="end" cx={b[0]} cy={b[1]} r={3 * k} />
                    {label(midpoint(a, b), `${kl.metres} m${kl.label ? ` ${kl.label}` : ''}`, undefined, 'middle')}
                    {errBadge(ref, b)}
                  </g>
                );
              })}

            {layers.human &&
              pairsOf(doc).map((pair, index) => {
                const ref: ItemRef = { kind: 'parallel_pair', index };
                const color = AXIS_COLOR[pair.axis] ?? 'white';
                const lines = pair.lines as Line[];
                return (
                  <g key={`pp${index}`} className={cls(ref, 'pair', false)} data-hit={refKey(ref)} data-handle="body" style={{ color }}>
                    {vpGuides(lines, color)}
                    {lines.map((l, i) => (
                      <g key={i}>
                        {segment(l[0], l[1], 'hit')}
                        {segment(l[0], l[1], 'shape')}
                      </g>
                    ))}
                    {label(midpoint(lines[0][0], lines[0][1]), pair.axis, color, 'middle')}
                    {errBadge(ref, lines[0][1])}
                  </g>
                );
              })}

            {layers.human &&
              verticalsOf(doc).map((l, index) => {
                const ref: ItemRef = { kind: 'vertical_line', index };
                return (
                  <g key={`vl${index}`} className={cls(ref, 'vertical', false)} data-hit={refKey(ref)} data-handle="body" style={{ color: AXIS_COLOR.z }}>
                    {segment(l[0], l[1], 'hit')}
                    {segment(l[0], l[1], 'shape')}
                    {errBadge(ref, l[1])}
                  </g>
                );
              })}

            {layers.human &&
              (() => {
                const r = referenceOf(doc);
                if (!r) return null;
                const ref: ItemRef = { kind: 'reference' };
                const [a, b] = r.pixels as Line;
                return (
                  <g className={cls(ref, 'reference', false)} data-hit="reference" data-handle="body">
                    {segment(a, b, 'hit')}
                    {segment(a, b, 'shape')}
                    <circle className="foot" cx={a[0]} cy={a[1]} r={4 * k} />
                    {label([b[0] + 8 * k, b[1]], `${r.metres} m${r.label ? ` ${r.label}` : ''}`)}
                    {errBadge(ref, b)}
                  </g>
                );
              })()}
          </g>

          {/* handles of the selected item, on top of everything */}
          <g className="handles">
            {selection?.kind === 'object' &&
              objectsOf(doc)[selection.index] &&
              handleDots(selection, boxCorners(objectsOf(doc)[selection.index].box as Box))}
            {selection?.kind === 'opening' && openingsOf(doc)[selection.index] && handleDots(selection, openingsOf(doc)[selection.index].quad as Vec2[])}
            {selection?.kind === 'known_length' && lengthsOf(doc)[selection.index] && handleDots(selection, lengthsOf(doc)[selection.index].pixels as Line)}
            {selection?.kind === 'vertical_line' && verticalsOf(doc)[selection.index] && handleDots(selection, verticalsOf(doc)[selection.index])}
            {selection?.kind === 'reference' && referenceOf(doc) && handleDots(selection, referenceOf(doc)!.pixels as Line)}
            {selection?.kind === 'boundary_line' &&
              boundariesOf(doc)[selection.index] &&
              handleDots(selection, boundariesOf(doc)[selection.index].pixels as Vec2[])}
            {selection?.kind === 'parallel_pair' &&
              pairsOf(doc)[selection.index] &&
              handleDots(selection, (pairsOf(doc)[selection.index].lines as Line[]).slice(0, 2).flat() as Vec2[], [0, 1, 2, 3])}
          </g>

          {/* shape waiting for its side-panel form */}
          {draft && (
            <g className="draft">
              {draft.kind === 'object' && (
                <rect x={draft.box[0]} y={draft.box[1]} width={draft.box[2] - draft.box[0]} height={draft.box[3] - draft.box[1]} />
              )}
              {draft.kind === 'opening' && <polygon points={pts(draft.quad)} />}
              {(draft.kind === 'reference' || draft.kind === 'known_length') && (
                <>
                  {segment(draft.pixels[0], draft.pixels[1], 'shape')}
                  <circle cx={draft.pixels[0][0]} cy={draft.pixels[0][1]} r={4 * k} />
                </>
              )}
            </g>
          )}

          {/* in-progress drawing */}
          <g className="drawing" style={{ color: tool === 'calib' ? AXIS_COLOR[axis] : undefined }}>
            {rect && (
              <rect
                x={Math.min(rect[0][0], rect[1][0])}
                y={Math.min(rect[0][1], rect[1][1])}
                width={Math.abs(rect[1][0] - rect[0][0])}
                height={Math.abs(rect[1][1] - rect[0][1])}
              />
            )}
            {firstLine && segment(firstLine[0], firstLine[1], 'shape')}
            {clicks[0] && <circle cx={clicks[0][0]} cy={clicks[0][1]} r={4 * k} />}
            {clicks[0] && hoverPt && tool === 'opening' && <polygon points={pts(quadFromTwoClicks(clicks[0], hoverPt))} />}
            {clicks[0] && hoverPt && tool !== 'opening' && segment(clicks[0], hoverPt, 'shape')}
            {firstLine && clicks[0] && hoverPt && vpGuides([firstLine, [clicks[0], hoverPt]], AXIS_COLOR[axis])}
          </g>
          {tool === 'boundary' && polyline.length > 0 && (
            <g className="drawing boundary-drawing" style={{ color: BOUNDARY_COLOR[boundaryKind] }}>
              {polyline.length > 1 && <polyline className="halo" points={pts(polyline)} />}
              {polyline.length > 1 && <polyline className="shape" points={pts(polyline)} />}
              {hover && segment(polyline[polyline.length - 1], hover, 'shape rubber')}
              {polyline.map((p, i) => (
                <circle key={i} cx={p[0]} cy={p[1]} r={3.5 * k} />
              ))}
            </g>
          )}
        </g>
      </svg>

      {imageError && (
        <div className="viewport-msg">
          {showOverlay ? 'overlay.png could not be loaded (run auto first).' : 'The photo could not be loaded.'}
        </div>
      )}
      {tool === 'boundary' && (
        <div className="viewport-hint" style={{ borderColor: BOUNDARY_COLOR[boundaryKind] }}>
          <b style={{ color: BOUNDARY_COLOR[boundaryKind] }}>{BOUNDARY_LABEL[boundaryKind]}</b> · {polyline.length} point
          {polyline.length === 1 ? '' : 's'}
          {polyline.length >= 2 ? ' · Enter or double-click finishes' : ''}
        </div>
      )}
      {tool === 'calib' && (
        <div className="viewport-hint" style={{ borderColor: AXIS_COLOR[axis] }}>
          axis <b style={{ color: AXIS_COLOR[axis] }}>{axis}</b> · line {firstLine ? 2 : 1} of 2
        </div>
      )}
      <div className="viewport-status">
        {hover ? `u ${hover[0].toFixed(1)}  v ${hover[1].toFixed(1)}` : `${W} × ${H} px`} · {Math.round(view.scale * 100)}%
      </div>
      <div className="zoom-buttons">
        <button type="button" title="Zoom out (wheel)" onClick={() => setView((v) => zoomAt(v, [size[0] / 2, size[1] / 2], 1 / 1.25))}>
          −
        </button>
        <button type="button" title="Actual pixels (100%)" onClick={() => setView((v) => zoomAt(v, [size[0] / 2, size[1] / 2], 1 / v.scale))}>
          1:1
        </button>
        <button type="button" title="Zoom in (wheel)" onClick={() => setView((v) => zoomAt(v, [size[0] / 2, size[1] / 2], 1.25))}>
          +
        </button>
        <button type="button" title="Fit image (0)" onClick={fit}>
          Fit
        </button>
      </div>
    </div>
  );
}

