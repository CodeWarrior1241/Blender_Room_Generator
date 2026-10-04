import { type ReactNode, useEffect, useState } from 'react';
import { WALL_HINTS } from '../lib/annotations';
import type { ArchetypeInfo } from '../types/api';

/** Text input that only reports a value on blur / Enter, and only when `validate` accepts it. */
export function CommitInput(props: {
  value: string;
  onCommit: (v: string) => void;
  validate?: (v: string) => string | null;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const { value, onCommit, validate, placeholder, ariaLabel } = props;
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const err = text !== value && validate ? validate(text) : null;
  const commit = () => {
    if (text !== value && !err) onCommit(text);
  };
  return (
    <>
      <input
        value={text}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-invalid={!!err}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
          if (e.key === 'Escape') setText(value);
        }}
      />
      {err && <div className="field-err">{err}</div>}
    </>
  );
}

export function parseMetres(text: string): number | null {
  if (!text.trim()) return null;
  const n = Number(text.replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Positive number in metres; reports valid values as they are typed. */
export function MetresInput(props: { value: number | null | undefined; onChange: (v: number) => void; autoFocus?: boolean; ariaLabel?: string }) {
  const { value, onChange, autoFocus, ariaLabel } = props;
  const [text, setText] = useState(value != null ? String(value) : '');
  useEffect(() => {
    setText((t) => (parseMetres(t) === (value ?? null) ? t : value != null ? String(value) : ''));
  }, [value]);
  const ok = parseMetres(text) !== null;
  return (
    <>
      <input
        type="text"
        inputMode="decimal"
        autoFocus={autoFocus}
        value={text}
        aria-label={ariaLabel}
        aria-invalid={!ok}
        placeholder="metres"
        onChange={(e) => {
          setText(e.target.value);
          const v = parseMetres(e.target.value);
          if (v !== null) onChange(v);
        }}
      />
      {!ok && text.trim() !== '' && <div className="field-err">enter a length in metres greater than 0</div>}
    </>
  );
}

export function ArchetypeSelect(props: { value: string; archetypes: readonly ArchetypeInfo[]; onChange: (v: string) => void }) {
  const { value, archetypes, onChange } = props;
  const groups = new Map<string, ArchetypeInfo[]>();
  for (const a of archetypes) groups.set(a.category ?? 'other', [...(groups.get(a.category ?? 'other') ?? []), a]);
  const known = archetypes.some((a) => a.name === value);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">(none: resolve from label at build time)</option>
      {value && !known && <option value={value}>{value}</option>}
      {[...groups.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([cat, list]) => (
          <optgroup key={cat} label={cat}>
            {list
              .slice()
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((a) => (
                <option key={a.name} value={a.name} title={a.description}>
                  {a.name.replace(/_/g, ' ')}
                </option>
              ))}
          </optgroup>
        ))}
    </select>
  );
}

export function SupportSelect(props: { value: string; objectIds: readonly string[]; onChange: (v: string) => void }) {
  const { value, objectIds, onChange } = props;
  const base = ['floor', 'wall', 'ceiling'];
  const known = base.includes(value) || objectIds.includes(value);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {base.map((b) => (
        <option key={b} value={b}>
          {b}
        </option>
      ))}
      {value && !known && <option value={value}>{value} (missing)</option>}
      {objectIds.length > 0 && (
        <optgroup label="on top of object">
          {objectIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}

export function WallHintSelect(props: { value: string | null | undefined; onChange: (v: string | null) => void }) {
  const { value, onChange } = props;
  const v = value ?? '';
  return (
    <select value={v} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">(no hint)</option>
      {WALL_HINTS.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
      <optgroup label="room edge index">
        {['0', '1', '2', '3'].map((h) => (
          <option key={h} value={h}>
            edge {h}
          </option>
        ))}
      </optgroup>
      {v && !(WALL_HINTS as readonly string[]).includes(v) && !['0', '1', '2', '3'].includes(v) && <option value={v}>{v}</option>}
    </select>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function splitList(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export function fmtPt(p: readonly number[]): string {
  return `(${p.map((n) => n.toFixed(1)).join(', ')})`;
}
