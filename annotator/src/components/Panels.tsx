import type { ReactNode } from 'react';
import type { Annotations } from '../types/annotations';
import type { AutoSummary, BuildResult, WorldDetail } from '../types/api';
import {
  type EditAction,
  type ItemRef,
  BOUNDARY_LABEL,
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
import { AXIS_COLOR, BOUNDARY_COLOR, type Layers, type MlMode } from '../lib/ui';
import { MetresInput, fmtPt } from './fields';

// ------------------------------------------------------------------------------------------
// Items
// ------------------------------------------------------------------------------------------

interface ItemListProps {
  doc: Annotations;
  selection: ItemRef | null;
  errorKeys: ReadonlySet<string>;
  onSelect: (ref: ItemRef) => void;
  onEdit: (edit: EditAction, tag?: string) => void;
}

function Row(props: { ref_: ItemRef; selection: ItemRef | null; errorKeys: ReadonlySet<string>; onSelect: (r: ItemRef) => void; children: ReactNode; auto?: boolean; color?: string }) {
  const { ref_, selection, errorKeys, onSelect, children, auto, color } = props;
  const err = errorKeys.has(refKey(ref_));
  return (
    <li>
      <button type="button" className={`item-row ${sameRef(ref_, selection) ? 'selected' : ''} ${err ? 'err' : ''}`} onClick={() => onSelect(ref_)}>
        <span className={`swatch ${auto ? 'auto' : ''}`} style={{ color }} aria-hidden />
        <span className="item-text">{children}</span>
        {auto !== undefined && <span className={`badge ${auto ? 'auto' : 'human'}`}>{auto ? 'auto' : 'human'}</span>}
        {err && (
          <span className="err-dot" title="has validation errors">
            !
          </span>
        )}
      </button>
    </li>
  );
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <div className="group">
      <h4>
        {title} <span className="muted">{count}</span>
      </h4>
      {count > 0 ? <ul className="item-list">{children}</ul> : <p className="muted small">none</p>}
    </div>
  );
}

export function ItemList({ doc, selection, errorKeys, onSelect, onEdit }: ItemListProps) {
  const common = { selection, errorKeys, onSelect };
  const ref = referenceOf(doc);
  return (
    <div className="items-panel">
      <Group title="Objects" count={objectsOf(doc).length}>
        {objectsOf(doc).map((o, index) => (
          <Row key={index} ref_={{ kind: 'object', index }} auto={isAuto(o.provenance)} color="var(--c-object)" {...common}>
            <b>{o.id}</b> <span className="muted">{o.archetype ?? o.label}</span>
            {o.support && o.support !== 'floor' && <span className="muted"> on {o.support}</span>}
          </Row>
        ))}
      </Group>
      <Group title="Openings" count={openingsOf(doc).length}>
        {openingsOf(doc).map((o, index) => (
          <Row key={index} ref_={{ kind: 'opening', index }} auto={isAuto(o.provenance)} color="var(--c-opening)" {...common}>
            {o.kind}
            {o.wall_hint ? ` · ${o.wall_hint}` : ''} {o.label && <span className="muted">{o.label}</span>}
          </Row>
        ))}
      </Group>
      <Group title="Boundary lines" count={boundariesOf(doc).length}>
        {boundariesOf(doc).map((b, index) => (
          <Row key={index} ref_={{ kind: 'boundary_line', index }} auto={isAuto(b.provenance)} color={BOUNDARY_COLOR[b.kind]} {...common}>
            {BOUNDARY_LABEL[b.kind] ?? b.kind} <span className="muted">{b.pixels.length} points</span>
          </Row>
        ))}
      </Group>
      <Group title="Floor corners" count={cornersOf(doc).length}>
        {cornersOf(doc).map((p, index) => (
          <Row key={index} ref_={{ kind: 'floor_corner', index }} color="var(--c-corner)" {...common}>
            #{index + 1} <span className="muted">{fmtPt(p)}</span>
          </Row>
        ))}
      </Group>
      <Group title="Calibration" count={pairsOf(doc).length + verticalsOf(doc).length + (ref ? 1 : 0)}>
        {pairsOf(doc).map((p, index) => (
          <Row key={`p${index}`} ref_={{ kind: 'parallel_pair', index }} color={AXIS_COLOR[p.axis]} {...common}>
            line pair · axis <b style={{ color: AXIS_COLOR[p.axis] }}>{p.axis}</b>
          </Row>
        ))}
        {verticalsOf(doc).map((_, index) => (
          <Row key={`v${index}`} ref_={{ kind: 'vertical_line', index }} color={AXIS_COLOR.z} {...common}>
            vertical line #{index + 1}
          </Row>
        ))}
        {ref && (
          <Row ref_={{ kind: 'reference' }} color="var(--c-reference)" {...common}>
            reference {ref.metres} m <span className="muted">{ref.label}</span>
          </Row>
        )}
      </Group>
      <Group title="Known lengths" count={lengthsOf(doc).length}>
        {lengthsOf(doc).map((k, index) => (
          <Row key={index} ref_={{ kind: 'known_length', index }} color="var(--c-length)" {...common}>
            {k.metres} m <span className="muted">{k.label}</span>
          </Row>
        ))}
      </Group>
      <div className="group">
        <h4>Room</h4>
        <label className="field">
          <span className="field-label">Ceiling height (m), optional</span>
          <div className="row tight">
            <MetresInput value={doc.ceiling_height_m ?? null} onChange={(v) => onEdit({ type: 'setCeilingHeight', value: v }, 'ceiling')} ariaLabel="ceiling height" />
            {doc.ceiling_height_m != null && (
              <button type="button" className="small" onClick={() => onEdit({ type: 'setCeilingHeight', value: null })}>
                Clear
              </button>
            )}
          </div>
        </label>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------
// Layers
// ------------------------------------------------------------------------------------------

export function LayersPanel(props: {
  layers: Layers;
  onChange: (l: Layers) => void;
  hasCamera: boolean;
  overlay: 'ok' | 'missing' | 'unknown';
  cameraNote: string | null;
}) {
  const { layers, onChange, hasCamera, overlay, cameraNote } = props;
  const box = (key: keyof Layers, label: ReactNode, disabled = false, title?: string) => (
    <label className={`check ${disabled ? 'disabled' : ''}`} title={title}>
      <input type="checkbox" checked={layers[key] && !disabled} disabled={disabled} onChange={(e) => onChange({ ...layers, [key]: e.target.checked })} />
      {label}
    </label>
  );
  return (
    <div className="layers">
      {box('auto', <>Detected (auto) items, dashed</>)}
      {box('human', <>Human items and hints, solid</>)}
      {box('labels', 'Labels')}
      {box('grid', 'Floor grid (0.5 m)', !hasCamera, hasCamera ? undefined : 'available once the world is calibrated')}
      {box('wireframe', 'Room wireframe', !hasCamera, hasCamera ? undefined : 'available once the world is calibrated')}
      {box('overlayBackground', 'Background: auto overlay.png', overlay !== 'ok', overlay === 'ok' ? undefined : 'output/world/overlay.png does not exist yet')}
      {cameraNote && <p className="small muted">{cameraNote}</p>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------
// Pipeline (auto + build)
// ------------------------------------------------------------------------------------------

const fmt = (n: number | null | undefined, digits = 2) => (typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '?');

export function AutoSummaryView({ s }: { s: AutoSummary }) {
  const size = s.shell?.size_m;
  return (
    <div className="summary">
      <dl>
        <dt>Room size</dt>
        <dd>{size ? `${fmt(size[0])} × ${fmt(size[1])} m` : '?'}</dd>
        <dt>Ceiling</dt>
        <dd>{fmt(s.shell?.ceiling_height)} m</dd>
        <dt>Scale</dt>
        <dd>
          {s.scale ? (
            <>
              camera height {fmt(s.scale.camera_height_m)} m · {s.scale.source ?? '?'} · confidence {fmt(s.scale.confidence)}
            </>
          ) : (
            '?'
          )}
        </dd>
        <dt>Field of view</dt>
        <dd>
          {fmt(s.calibration?.hfov_deg, 1)}° horizontal{s.calibration?.method ? ` · ${s.calibration.method}` : ''}
        </dd>
        <dt>Objects</dt>
        <dd>{s.objects?.length ?? 0}</dd>
      </dl>
      {s.notes && s.notes.length > 0 && (
        <>
          <h5>Notes</h5>
          <ul className="notes">
            {s.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </>
      )}
      <details>
        <summary>Full response</summary>
        <pre>{JSON.stringify(s, null, 2)}</pre>
      </details>
    </div>
  );
}

export function BuildResultView({ r, fileLink }: { r: BuildResult; fileLink: (workspacePath: string) => string }) {
  const fo = r.failed_outputs;
  const failed = Boolean(fo) && (Array.isArray(fo) ? fo.length > 0 : typeof fo === 'object' ? Object.keys(fo as object).length > 0 : true);
  return (
    <div className="summary">
      <p>
        <b>{r.status ?? 'done'}</b>
        {r.index !== undefined && ` · build #${r.index}`}
        {typeof r.seconds === 'number' && ` · ${r.seconds.toFixed(1)} s`}
      </p>
      {r.message && <p className="small muted">{r.message}</p>}
      {r.warnings && r.warnings.length > 0 && (
        <ul className="notes warn">
          {r.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      {failed && <pre className="warn">failed outputs: {JSON.stringify(r.failed_outputs, null, 2)}</pre>}
      {r.files && Object.keys(r.files).length > 0 && (
        <ul className="files">
          {Object.entries(r.files).map(([k, v]) => (
            <li key={k}>
              <a href={fileLink(v)} target="_blank" rel="noreferrer">
                {k}
              </a>{' '}
              <span className="muted small">{v}</span>
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary>Full response</summary>
        <pre>{JSON.stringify(r, null, 2)}</pre>
      </details>
    </div>
  );
}

export interface PipelineProps {
  world: WorldDetail | null;
  busy: 'auto' | 'build' | null;
  dirty: boolean;
  ml: MlMode;
  onMl: (m: MlMode) => void;
  force: boolean;
  onForce: (f: boolean) => void;
  onRunAuto: () => void;
  onBuild: () => void;
  autoResult: AutoSummary | null;
  autoError: string | null;
  buildResult: BuildResult | null;
  buildError: string | null;
  fileLink: (workspacePath: string) => string;
}

export function PipelinePanel(p: PipelineProps) {
  const st = p.world?.state;
  const flag = (ok: boolean | undefined, label: string) => <span className={`flag ${ok ? 'on' : ''}`}>{label}</span>;
  return (
    <div className="pipeline">
      {st && (
        <p className="flags">
          {flag(st.has_annotations, 'annotations')}
          {flag(st.has_calibration, 'calibration')}
          {flag(st.has_room, 'room')}
          {flag(st.latest_room_index != null, st.latest_room_index != null ? `build #${st.latest_room_index}` : 'no build')}
        </p>
      )}
      <div className="row">
        <select value={p.ml} onChange={(e) => p.onMl(e.target.value as MlMode)} disabled={!!p.busy} title="Local ML models (depth, detection)" aria-label="ML mode">
          <option value="auto">ML: auto</option>
          <option value="on">ML: on</option>
          <option value="off">ML: off</option>
        </select>
        <button type="button" className="primary" onClick={p.onRunAuto} disabled={!!p.busy} title="Run the automatic pipeline (about 30 s). Saves unsaved changes first.">
          {p.busy === 'auto' ? <Spinner /> : null} Run auto
        </button>
      </div>
      <p className="small muted">
        Auto re-reads annotations.json, keeps human items, and rewrites calibration, room.json and overlay.png.
        {p.dirty && ' Unsaved changes are saved first.'}
      </p>
      {p.autoError && <p className="error small">{p.autoError}</p>}
      {p.autoResult && <AutoSummaryView s={p.autoResult} />}

      <div className="row">
        <label className="check" title="Rebuild even if inputs are unchanged">
          <input type="checkbox" checked={p.force} onChange={(e) => p.onForce(e.target.checked)} disabled={!!p.busy} /> force
        </label>
        <button type="button" onClick={p.onBuild} disabled={!!p.busy || st?.has_room === false} title={st?.has_room === false ? 'Run auto first: build needs room.json' : 'Build the Blender scene (about 10 s)'}>
          {p.busy === 'build' ? <Spinner /> : null} Build
        </button>
      </div>
      <p className="small muted">Build uses room.json from the last auto run.</p>
      {p.buildError && <p className="error small">{p.buildError}</p>}
      {p.buildResult && <BuildResultView r={p.buildResult} fileLink={p.fileLink} />}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="working" />;
}
