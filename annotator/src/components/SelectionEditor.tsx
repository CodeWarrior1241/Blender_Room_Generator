import { useState } from 'react';
import type { Annotations, ObjectAnnotation, OpeningAnnotation, Provenance, WallHint } from '../types/annotations';
import type { ArchetypeInfo } from '../types/api';
import {
  type EditAction,
  type ItemRef,
  type OpeningKind,
  BOUNDARY_KINDS,
  BOUNDARY_LABEL,
  boundariesOf,
  cornersOf,
  describeRef,
  lengthsOf,
  objectsOf,
  openingsOf,
  pairsOf,
  referenceOf,
  refKey,
  verticalsOf,
} from '../lib/annotations';
import { api } from '../lib/api';
import { type Line, lineIntersection } from '../lib/geometry';
import { idProblem } from '../lib/slug';
import { AXES, AXIS_COLOR, BOUNDARY_COLOR } from '../lib/ui';
import { ArchetypeSelect, CommitInput, Field, MetresInput, SupportSelect, WallHintSelect, fmtPt, splitList } from './fields';
import { useFloorDistance, useFloorPoints } from './hooks';

export interface SelectionEditorProps {
  doc: Annotations;
  selection: ItemRef;
  slug: string;
  archetypes: readonly ArchetypeInfo[];
  hasCamera: boolean;
  issues: readonly string[];
  onEdit: (edit: EditAction, tag?: string) => void;
  onDelete: () => void;
}

function ProvenanceLine({ p, score }: { p?: Provenance; score?: number | null }) {
  const by = p?.by ?? 'auto';
  return (
    <p className="small muted">
      <span className={`badge ${by}`}>{by}</span> {p?.tool || 'unknown tool'}
      {p?.confidence !== undefined && ` · confidence ${p.confidence}`}
      {score != null && ` · score ${score}`}
      {by !== 'human' && <span className="block">Editing it marks it human: auto keeps human items on its next run.</span>}
    </p>
  );
}

export default function SelectionEditor(props: SelectionEditorProps) {
  const { doc, selection, issues, onDelete } = props;
  return (
    <section className="editor" key={refKey(selection)}>
      <div className="editor-head">
        <h3>{describeRef(doc, selection)}</h3>
        <button type="button" className="danger small" onClick={onDelete} title="Delete (Del)">
          Delete
        </button>
      </div>
      {issues.length > 0 && (
        <ul className="issues inline">
          {issues.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      )}
      <Body {...props} />
    </section>
  );
}

function Body(props: SelectionEditorProps) {
  const { doc, selection: ref } = props;
  switch (ref.kind) {
    case 'object':
      return <ObjectEditor {...props} index={ref.index} />;
    case 'opening':
      return <OpeningEditor {...props} index={ref.index} />;
    case 'known_length':
      return <LengthEditor {...props} index={ref.index} />;
    case 'reference':
      return <ReferenceEditor {...props} />;
    case 'parallel_pair':
      return <PairEditor {...props} index={ref.index} />;
    case 'floor_corner': {
      const p = cornersOf(doc)[ref.index];
      return p ? <CornerEditor {...props} index={ref.index} /> : null;
    }
    case 'boundary_line':
      return <BoundaryEditor {...props} index={ref.index} />;
    case 'vertical_line': {
      const l = verticalsOf(doc)[ref.index];
      return l ? (
        <p className="small muted">
          {fmtPt(l[0])} to {fmtPt(l[1])}. Vertical lines are a calibration hint (z axis); drag the ends to adjust.
        </p>
      ) : null;
    }
  }
}

function ObjectEditor({ doc, index, archetypes, onEdit }: SelectionEditorProps & { index: number }) {
  const o = objectsOf(doc)[index];
  const [suggest, setSuggest] = useState('');
  if (!o) return null;
  const others = objectsOf(doc)
    .filter((_, i) => i !== index)
    .map((x) => x.id);
  const update = (patch: Partial<Omit<ObjectAnnotation, 'provenance'>>, tag?: string) => onEdit({ type: 'updateObject', index, patch }, tag);
  const resolve = async () => {
    try {
      const r = await api.resolveArchetype(o.label);
      update({ archetype: r.archetype });
      setSuggest(r.matched ? `matched "${r.archetype}"` : `no match, fallback "${r.archetype}"`);
    } catch (e) {
      setSuggest(`lookup failed: ${(e as Error).message}`);
    }
  };
  return (
    <div className="form">
      <ProvenanceLine p={o.provenance} score={o.score} />
      <Field label="Label">
        <input value={o.label} onChange={(e) => update({ label: e.target.value }, `label:${index}`)} />
      </Field>
      <Field label="Id" hint="renaming also updates objects that stand on it">
        <CommitInput value={o.id} validate={(v) => idProblem(v, others)} onCommit={(v) => update({ id: v })} ariaLabel="object id" />
      </Field>
      <Field label="Archetype" hint={suggest}>
        <div className="row tight">
          <ArchetypeSelect value={o.archetype ?? ''} archetypes={archetypes} onChange={(v) => update({ archetype: v || null })} />
          <button type="button" className="small" onClick={resolve} title="Resolve the archetype from the label">
            From label
          </button>
        </div>
      </Field>
      <Field label="Support">
        <SupportSelect value={o.support ?? 'floor'} objectIds={others} onChange={(v) => update({ support: v })} />
      </Field>
      <Field label="Materials hint" hint="comma separated">
        <CommitInput
          value={(o.materials_hint ?? []).join(', ')}
          onCommit={(v) => update({ materials_hint: splitList(v) })}
          placeholder="green fabric, oak"
          ariaLabel="materials hint"
        />
      </Field>
      <p className="small muted">box [{o.box.map((n) => n.toFixed(1)).join(', ')}]</p>
    </div>
  );
}

function OpeningEditor({ doc, index, onEdit }: SelectionEditorProps & { index: number }) {
  const o = openingsOf(doc)[index];
  if (!o) return null;
  const update = (patch: Partial<Omit<OpeningAnnotation, 'provenance'>>, tag?: string) => onEdit({ type: 'updateOpening', index, patch }, tag);
  return (
    <div className="form">
      <ProvenanceLine p={o.provenance} />
      <Field label="Kind">
        <select value={o.kind} onChange={(e) => update({ kind: e.target.value as OpeningKind })}>
          <option value="door">door</option>
          <option value="window">window</option>
          <option value="opening">opening</option>
        </select>
      </Field>
      <Field label="Wall">
        <WallHintSelect value={o.wall_hint} onChange={(v) => update({ wall_hint: (v || null) as WallHint })} />
      </Field>
      <Field label="Label">
        <input value={o.label ?? ''} onChange={(e) => update({ label: e.target.value }, `opening-label:${index}`)} />
      </Field>
      <p className="small muted">quad {o.quad.map((p) => fmtPt(p)).join(' ')}</p>
    </div>
  );
}

function LengthEditor({ doc, index, slug, hasCamera, onEdit }: SelectionEditorProps & { index: number }) {
  const k = lengthsOf(doc)[index];
  const est = useFloorDistance(slug, k ? (k.pixels as Line) : null, hasCamera);
  if (!k) return null;
  return (
    <div className="form">
      <Field label="Metres" hint={est !== null ? `current camera measures about ${est.toFixed(2)} m` : undefined}>
        <MetresInput value={k.metres} onChange={(v) => onEdit({ type: 'updateKnownLength', index, patch: { metres: v } }, `metres:${index}`)} />
      </Field>
      <Field label="Label">
        <input value={k.label ?? ''} onChange={(e) => onEdit({ type: 'updateKnownLength', index, patch: { label: e.target.value } }, `kl-label:${index}`)} />
      </Field>
      <p className="small muted">
        {fmtPt(k.pixels[0])} to {fmtPt(k.pixels[1])}
      </p>
    </div>
  );
}

function ReferenceEditor({ doc, onEdit }: SelectionEditorProps) {
  const r = referenceOf(doc);
  if (!r) return null;
  const [bottom, top] = r.pixels as Line;
  return (
    <div className="form">
      <Field label="Metres">
        <MetresInput value={r.metres} onChange={(v) => onEdit({ type: 'updateReference', patch: { metres: v } }, 'ref-metres')} />
      </Field>
      <Field label="Label">
        <input value={r.label ?? ''} onChange={(e) => onEdit({ type: 'updateReference', patch: { label: e.target.value } }, 'ref-label')} />
      </Field>
      <p className="small muted">
        bottom {fmtPt(bottom)} · top {fmtPt(top)}
      </p>
      {bottom[1] < top[1] && (
        <p className="warn small">
          The first (bottom) point is above the second one; the reference must start where it stands on the floor.{' '}
          <button type="button" className="small" onClick={() => onEdit({ type: 'updateReference', patch: { pixels: [top, bottom] } })}>
            Swap ends
          </button>
        </p>
      )}
    </div>
  );
}

function BoundaryEditor({ doc, index, onEdit }: SelectionEditorProps & { index: number }) {
  const b = boundariesOf(doc)[index];
  if (!b) return null;
  const ref = { kind: 'boundary_line' as const, index };
  return (
    <div className="form">
      <ProvenanceLine p={b.provenance} />
      <Field label="Kind" hint="visible room boundaries only: not furniture edges or curtain hems">
        <div className="row tight wrap" role="radiogroup">
          {BOUNDARY_KINDS.map((kd) => (
            <button
              key={kd}
              type="button"
              role="radio"
              aria-checked={b.kind === kd}
              className={`axis-btn ${b.kind === kd ? 'active' : ''}`}
              style={{ color: BOUNDARY_COLOR[kd] }}
              onClick={() => onEdit({ type: 'updateBoundaryLine', index, patch: { kind: kd } })}
            >
              {BOUNDARY_LABEL[kd]}
            </button>
          ))}
        </div>
      </Field>
      <Field label={`Points (${b.pixels.length})`} hint="drag the white handles (Select tool) to move a point">
        <ol className="vertex-list">
          {b.pixels.map((p, i) => (
            <li key={i}>
              <span className="small">{fmtPt(p)}</span>
              <button
                type="button"
                className="small"
                disabled={b.pixels.length <= 2}
                title={b.pixels.length <= 2 ? 'a boundary line needs at least 2 points' : 'Remove this point'}
                onClick={() => onEdit({ type: 'removeVertex', ref, handle: i })}
              >
                ×
              </button>
            </li>
          ))}
        </ol>
      </Field>
    </div>
  );
}

function PairEditor({ doc, index, onEdit }: SelectionEditorProps & { index: number }) {
  const p = pairsOf(doc)[index];
  if (!p) return null;
  const vp = p.lines.length >= 2 ? lineIntersection(p.lines[0] as Line, p.lines[1] as Line) : null;
  return (
    <div className="form">
      <Field label="Axis" hint="x and y are horizontal room directions, z is vertical">
        <div className="row tight" role="radiogroup">
          {AXES.map((a) => (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={p.axis === a}
              className={`axis-btn ${p.axis === a ? 'active' : ''}`}
              style={{ color: AXIS_COLOR[a] }}
              onClick={() => onEdit({ type: 'updateParallelPair', index, patch: { axis: a } })}
            >
              {a}
            </button>
          ))}
        </div>
      </Field>
      <p className="small muted">{vp ? `lines meet at ${fmtPt(vp)}` : 'lines are parallel in the image (vanishing point at infinity)'}</p>
    </div>
  );
}

function CornerEditor({ doc, index, slug, hasCamera }: SelectionEditorProps & { index: number }) {
  const p = cornersOf(doc)[index];
  const floor = useFloorPoints(slug, p ? [p] : [], hasCamera);
  if (!p) return null;
  const f = floor?.[0];
  return (
    <p className="small muted">
      pixel {fmtPt(p)}
      {f && (
        <>
          {' '}
          · floor ({f[0].toFixed(2)} m, {f[1].toFixed(2)} m) with the current camera
        </>
      )}
    </p>
  );
}
