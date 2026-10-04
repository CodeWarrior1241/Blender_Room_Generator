import { type FormEvent, useEffect, useState } from 'react';
import type { Annotations } from '../types/annotations';
import type { ArchetypeInfo } from '../types/api';
import { type NewObject, type NewOpening, type OpeningKind, objectsOf, referenceOf } from '../lib/annotations';
import { api } from '../lib/api';
import type { Line } from '../lib/geometry';
import { idProblem, slugify, uniqueId } from '../lib/slug';
import type { Draft } from '../lib/ui';
import { ArchetypeSelect, Field, SupportSelect, WallHintSelect, fmtPt, parseMetres, splitList } from './fields';
import { useFloorDistance } from './hooks';

export interface OpeningDefaults {
  kind: OpeningKind;
  wall_hint: string | null;
}

export interface DraftFormProps {
  draft: Draft;
  doc: Annotations;
  slug: string;
  archetypes: readonly ArchetypeInfo[];
  hasCamera: boolean;
  openingDefaults: OpeningDefaults;
  onAddObject: (o: NewObject) => void;
  onAddOpening: (o: NewOpening) => void;
  onSetReference: (pixels: Line, metres: number, label: string) => void;
  onAddLength: (pixels: Line, metres: number, label: string) => void;
  onCancel: () => void;
}

export default function DraftForm(props: DraftFormProps) {
  const { draft } = props;
  switch (draft.kind) {
    case 'object':
      return <ObjectDraft {...props} box={draft.box} />;
    case 'opening':
      return <OpeningDraft {...props} quad={draft.quad} />;
    case 'reference':
      return <MetresDraft {...props} kind="reference" pixels={draft.pixels} />;
    case 'known_length':
      return <MetresDraft {...props} kind="known_length" pixels={draft.pixels} />;
  }
}

function Buttons({ ok, label, onCancel }: { ok: boolean; label: string; onCancel: () => void }) {
  return (
    <div className="row">
      <button type="submit" className="primary" disabled={!ok}>
        {label}
      </button>
      <button type="button" onClick={onCancel} title="Discard (Esc)">
        Cancel
      </button>
    </div>
  );
}

function ObjectDraft(props: DraftFormProps & { box: [number, number, number, number] }) {
  const { box, doc, archetypes, onAddObject, onCancel } = props;
  const ids = objectsOf(doc).map((o) => o.id);
  const [label, setLabel] = useState('');
  const [archetype, setArchetype] = useState('');
  const [archTouched, setArchTouched] = useState(false);
  const [note, setNote] = useState('');
  const [support, setSupport] = useState('floor');
  const [supportTouched, setSupportTouched] = useState(false);
  const [id, setId] = useState('');
  const [idTouched, setIdTouched] = useState(false);
  const [materials, setMaterials] = useState('');

  const effectiveId = idTouched ? id : label.trim() ? uniqueId(slugify(label), ids) : '';
  const idErr = idTouched ? idProblem(id, ids) : null;

  // pre-select the archetype (and wall/ceiling support) the backend resolves for the label
  useEffect(() => {
    const text = label.trim();
    if (!text) {
      setNote('');
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const r = await api.resolveArchetype(text);
        if (cancelled) return;
        setNote(r.matched ? `label matches "${r.archetype}"` : `no match, fallback "${r.archetype}"`);
        if (!archTouched) {
          setArchetype(r.archetype);
          if (!supportTouched) {
            const s = archetypes.find((a) => a.name === r.archetype)?.support;
            setSupport(s === 'wall' || s === 'ceiling' ? s : 'floor');
          }
        }
      } catch {
        if (!cancelled) setNote('archetype lookup failed (server unreachable?)');
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [label, archTouched, supportTouched, archetypes]);

  const ok = label.trim() !== '' && !idErr && effectiveId !== '';
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!ok) return;
    onAddObject({ label: label.trim(), box, id: effectiveId, support, archetype: archetype || null, materials_hint: splitList(materials) });
  };

  return (
    <form className="form" onSubmit={submit}>
      <h3>New object</h3>
      <p className="muted small">box [{box.map((n) => n.toFixed(0)).join(', ')}]</p>
      <Field label="Label">
        <input autoFocus value={label} placeholder="e.g. armchair" onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Field label="Archetype" hint={note}>
        <ArchetypeSelect
          value={archetype}
          archetypes={archetypes}
          onChange={(v) => {
            setArchetype(v);
            setArchTouched(true);
          }}
        />
      </Field>
      <Field label="Support">
        <SupportSelect
          value={support}
          objectIds={ids}
          onChange={(v) => {
            setSupport(v);
            setSupportTouched(true);
          }}
        />
      </Field>
      <Field label="Id" hint={idTouched ? undefined : 'derived from the label'}>
        <input
          value={effectiveId}
          aria-invalid={!!idErr}
          onChange={(e) => {
            setId(e.target.value);
            setIdTouched(true);
          }}
        />
        {idErr && <div className="field-err">{idErr}</div>}
      </Field>
      <Field label="Materials hint" hint="comma separated, optional">
        <input value={materials} placeholder="green fabric, oak" onChange={(e) => setMaterials(e.target.value)} />
      </Field>
      <Buttons ok={ok} label="Add object" onCancel={onCancel} />
    </form>
  );
}

function OpeningDraft(props: DraftFormProps & { quad: NewOpening['quad'] }) {
  const { quad, openingDefaults, onAddOpening, onCancel } = props;
  const [kind, setKind] = useState<OpeningKind>(openingDefaults.kind);
  const [wallHint, setWallHint] = useState<string | null>(openingDefaults.wall_hint);
  const [label, setLabel] = useState('');
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onAddOpening({ kind, quad, wall_hint: wallHint, label: label.trim() });
  };
  return (
    <form className="form" onSubmit={submit}>
      <h3>New opening</h3>
      <p className="muted small">
        {fmtPt(quad[0])} to {fmtPt(quad[2])}
      </p>
      <Field label="Kind">
        <select autoFocus value={kind} onChange={(e) => setKind(e.target.value as OpeningKind)}>
          <option value="door">door</option>
          <option value="window">window</option>
          <option value="opening">opening</option>
        </select>
      </Field>
      <Field label="Wall">
        <WallHintSelect value={wallHint} onChange={setWallHint} />
      </Field>
      <Field label="Label" hint="optional">
        <input value={label} placeholder="e.g. door to hallway" onChange={(e) => setLabel(e.target.value)} />
      </Field>
      <Buttons ok label="Add opening" onCancel={onCancel} />
    </form>
  );
}

function MetresDraft(props: DraftFormProps & { kind: 'reference' | 'known_length'; pixels: Line }) {
  const { kind, pixels, doc, slug, hasCamera, onSetReference, onAddLength, onCancel } = props;
  const [metresText, setMetresText] = useState('');
  const [label, setLabel] = useState('');
  const metres = parseMetres(metresText);
  const estimate = useFloorDistance(slug, kind === 'known_length' ? pixels : null, hasCamera);
  const existing = kind === 'reference' ? referenceOf(doc) : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (metres === null) return;
    if (kind === 'reference') onSetReference(pixels, metres, label.trim());
    else onAddLength(pixels, metres, label.trim());
  };
  return (
    <form className="form" onSubmit={submit}>
      <h3>{kind === 'reference' ? 'Reference height' : 'Known floor length'}</h3>
      <p className="muted small">
        {kind === 'reference' ? 'bottom' : 'from'} {fmtPt(pixels[0])} {kind === 'reference' ? 'top' : 'to'} {fmtPt(pixels[1])}
      </p>
      <Field
        label="Metres"
        hint={estimate !== null ? `current camera measures about ${estimate.toFixed(2)} m` : kind === 'reference' ? 'e.g. a door is about 2.0 m' : undefined}
      >
        <input
          autoFocus
          inputMode="decimal"
          value={metresText}
          placeholder="metres"
          aria-invalid={metresText.trim() !== '' && metres === null}
          onChange={(e) => setMetresText(e.target.value)}
        />
        {metresText.trim() !== '' && metres === null && <div className="field-err">enter a length in metres greater than 0</div>}
      </Field>
      <Field label="Label" hint="optional">
        <input value={label} placeholder={kind === 'reference' ? 'e.g. door' : 'e.g. rug width'} onChange={(e) => setLabel(e.target.value)} />
      </Field>
      {existing && <p className="warn small">Replaces the current reference ({existing.metres} m{existing.label ? `, ${existing.label}` : ''}).</p>}
      <Buttons ok={metres !== null} label={kind === 'reference' ? 'Set reference' : 'Add length'} onCancel={onCancel} />
    </form>
  );
}
