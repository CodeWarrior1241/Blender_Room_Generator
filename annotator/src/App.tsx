import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import DraftForm, { type OpeningDefaults } from './components/DraftForms';
import { useImageAvailable, useNaturalSize } from './components/hooks';
import { LayersPanel, ItemList, PipelinePanel, Spinner } from './components/Panels';
import ResultView from './components/ResultView';
import SelectionEditor from './components/SelectionEditor';
import Toolbar from './components/Toolbar';
import Viewport from './components/Viewport';
import {
  BOUNDARY_KINDS,
  BOUNDARY_LABEL,
  type Axis,
  type BoundaryKind,
  type EditAction,
  type ItemRef,
  type NewObject,
  type NewOpening,
  boundariesOf,
  canRedo,
  canUndo,
  historyReducer,
  initHistory,
  isDirty,
  itemExists,
  lengthsOf,
  objectsOf,
  openingsOf,
  refKey,
} from './lib/annotations';
import { ApiError, api } from './lib/api';
import type { Line, Vec2 } from './lib/geometry';
import { appendPoint, finishPolyline, popPoint } from './lib/polyline';
import { type ValidationIssue, describeIssue, issuesByItem, localIssues, refsForIssue } from './lib/validation';
import {
  AXES,
  AXIS_COLOR,
  BOUNDARY_COLOR,
  DEFAULT_LAYERS,
  type Draft,
  type Layers,
  type MlMode,
  TOOLS,
  TOOL_BY_KEY,
  type Tool,
  hashForSlug,
  isTextInput,
  readHashSlug,
  worldRelative,
} from './lib/ui';
import type { Annotations } from './types/annotations';
import type { ArchetypeInfo, AutoSummary, BuildResult, CameraOverlay, WorldDetail, WorldSummary } from './types/api';

const EMPTY: Annotations = { world: '', image: '', image_size: [0, 0] };
const LAYERS_KEY = 'room-annotator.layers';

type LoadState = { status: 'idle' } | { status: 'loading' } | { status: 'ready' } | { status: 'error'; message: string };

function errText(e: unknown): string {
  return e instanceof ApiError || e instanceof Error ? e.message : String(e);
}

function loadLayers(): Layers {
  try {
    const raw = window.localStorage.getItem(LAYERS_KEY);
    return raw ? { ...DEFAULT_LAYERS, ...(JSON.parse(raw) as Partial<Layers>) } : DEFAULT_LAYERS;
  } catch {
    return DEFAULT_LAYERS;
  }
}

const SHORTCUTS: [string, string][] = [
  ...TOOLS.map((t) => [t.key, t.label] as [string, string]),
  ['1 / 2 / 3', 'calibration axis x / y / z; with Boundary: wall/floor, wall/ceiling, corner'],
  ['Enter / double-click', 'finish a boundary line (Backspace removes its last point)'],
  ['Delete', 'delete the selection'],
  ['Esc', 'cancel drawing / deselect'],
  ['Ctrl+Z / Ctrl+Shift+Z', 'undo / redo (also Ctrl+Y)'],
  ['Ctrl+S', 'save'],
  ['0', 'fit the image'],
  ['Wheel', 'zoom about the cursor'],
  ['Middle drag, Space+drag', 'pan (also left-drag on empty space with Select)'],
];

export default function App() {
  const [worlds, setWorlds] = useState<WorldSummary[] | null>(null);
  const [worldsError, setWorldsError] = useState<string | null>(null);
  const [slug, setSlug] = useState<string | null>(() => readHashSlug(window.location.hash));
  const [world, setWorld] = useState<WorldDetail | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: 'idle' });
  const [hist, dispatch] = useReducer(historyReducer, EMPTY, initHistory);
  const doc = hist.present;
  const ready = load.status === 'ready';
  const dirty = ready && isDirty(hist);

  const [tool, setTool] = useState<Tool>('select');
  const [axis, setAxis] = useState<Axis>('x');
  const [boundaryKind, setBoundaryKind] = useState<BoundaryKind>('wall_floor');
  const [polyline, setPolyline] = useState<Vec2[]>([]);
  const [selection, setSelection] = useState<ItemRef | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [layers, setLayers] = useState<Layers>(loadLayers);
  const [camera, setCamera] = useState<CameraOverlay | null>(null);
  const [cameraNote, setCameraNote] = useState<string | null>(null);
  const [archetypes, setArchetypes] = useState<ArchetypeInfo[]>([]);
  const [issues, setIssues] = useState<{ list: ValidationIssue[]; doc: Annotations } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);
  const [busy, setBusy] = useState<'auto' | 'build' | null>(null);
  const [ml, setMl] = useState<MlMode>('auto');
  const [force, setForce] = useState(false);
  const [autoResult, setAutoResult] = useState<AutoSummary | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [buildResult, setBuildResult] = useState<BuildResult | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [mainView, setMainView] = useState<'photo' | 'result'>('photo');
  const [fitSignal, setFitSignal] = useState(0);
  const [revision, setRevision] = useState(0);
  const [openingDefaults, setOpeningDefaults] = useState<OpeningDefaults>({ kind: 'door', wall_hint: null });

  // latest values for event handlers registered once
  const histRef = useRef(hist);
  histRef.current = hist;
  const slugRef = useRef(slug);
  slugRef.current = slug;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const polylineRef = useRef(polyline);
  polylineRef.current = polyline;
  const loadSeq = useRef(0);

  // ---- worlds, archetypes, hash routing --------------------------------------------------------
  useEffect(() => {
    api
      .listWorlds()
      .then((w) => {
        setWorlds(w);
        setWorldsError(null);
      })
      .catch((e) => setWorldsError(`Cannot list worlds: ${errText(e)}`));
    api
      .listArchetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes([]));
  }, []);

  useEffect(() => {
    if (!slug && worlds && worlds.length === 1) {
      window.history.replaceState(null, '', hashForSlug(worlds[0].slug));
      setSlug(worlds[0].slug);
    }
  }, [slug, worlds]);

  useEffect(() => {
    const onHash = () => {
      const next = readHashSlug(window.location.hash);
      if (next === slugRef.current) return;
      if (dirtyRef.current && !window.confirm('Discard unsaved changes to this world?')) {
        window.history.replaceState(null, '', slugRef.current ? hashForSlug(slugRef.current) : '#/');
        return;
      }
      setSlug(next);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  useEffect(() => {
    try {
      window.localStorage.setItem(LAYERS_KEY, JSON.stringify(layers));
    } catch {
      /* private mode */
    }
  }, [layers]);

  useEffect(() => {
    document.title = `${dirty ? '* ' : ''}${slug ? `${slug} · ` : ''}Room annotator`;
  }, [slug, dirty]);

  // ---- loading -------------------------------------------------------------------------------------
  const refreshCamera = useCallback(async (s: string) => {
    try {
      const cam = await api.getCamera(s);
      if (slugRef.current !== s) return;
      setCamera(cam);
      setCameraNote(cam ? `Camera from ${cam.source}.json · horizontal FOV ${cam.hfov_deg}°` : 'Not calibrated yet: run auto to get the floor grid and wireframe.');
    } catch (e) {
      if (slugRef.current !== s) return;
      setCamera(null);
      setCameraNote(`Camera overlay unavailable: ${errText(e)}`);
    }
  }, []);

  const refreshWorld = useCallback(async (s: string) => {
    try {
      const detail = await api.getWorld(s);
      if (slugRef.current === s) setWorld(detail);
    } catch {
      /* keep the previous state */
    }
  }, []);

  const loadWorld = useCallback(
    async (s: string) => {
      const seq = ++loadSeq.current;
      setLoad({ status: 'loading' });
      setSelection(null);
      setDraft(null);
      setIssues(null);
      setSaveMsg(null);
      setAutoResult(null);
      setAutoError(null);
      setBuildResult(null);
      setBuildError(null);
      setCamera(null);
      setCameraNote(null);
      try {
        const [detail, ann] = await Promise.all([api.getWorld(s), api.getAnnotations(s)]);
        if (seq !== loadSeq.current) return;
        setWorld(detail);
        dispatch({ type: 'load', doc: ann });
        setLoad({ status: 'ready' });
      } catch (e) {
        if (seq !== loadSeq.current) return;
        setWorld(null);
        setLoad({ status: 'error', message: errText(e) });
        return;
      }
      void refreshCamera(s);
    },
    [refreshCamera],
  );

  useEffect(() => {
    if (slug) void loadWorld(slug);
    else {
      setLoad({ status: 'idle' });
      setWorld(null);
    }
  }, [slug, loadWorld]);

  // a boundary line in progress belongs to the Boundary tool and the loaded document
  useEffect(() => {
    if (tool !== 'boundary') setPolyline([]);
  }, [tool]);
  useEffect(() => setPolyline([]), [slug, load.status]);

  // drop a selection that no longer exists (undo, delete, reload)
  useEffect(() => {
    if (selection && !itemExists(doc, selection)) setSelection(null);
  }, [doc, selection]);

  // ---- editing -------------------------------------------------------------------------------------
  const onEdit = useCallback((edit: EditAction, tag?: string) => dispatch({ type: 'edit', edit, tag }), []);
  const onGestureEnd = useCallback(() => dispatch({ type: 'endGesture' }), []);
  const onDraft = useCallback((d: Draft) => {
    setDraft(d);
    setSelection(null);
  }, []);

  const deleteSelection = useCallback(() => {
    if (!selection) return;
    dispatch({ type: 'edit', edit: { type: 'delete', ref: selection } });
    setSelection(null);
  }, [selection]);

  const onBoundaryPoint = useCallback((p: Vec2, tol: number) => setPolyline((pts) => appendPoint(pts, p, tol)), []);
  const finishBoundary = useCallback(() => {
    const done = finishPolyline(polylineRef.current);
    if (!done) return;
    const index = boundariesOf(histRef.current.present).length;
    dispatch({ type: 'edit', edit: { type: 'addBoundaryLine', value: { kind: boundaryKind, pixels: done } } });
    setPolyline([]);
    setDraft(null);
    setSelection({ kind: 'boundary_line', index });
  }, [boundaryKind]);

  const addObject = (o: NewObject) => {
    const index = objectsOf(histRef.current.present).length;
    onEdit({ type: 'addObject', object: o });
    setDraft(null);
    setSelection({ kind: 'object', index });
  };
  const addOpening = (o: NewOpening) => {
    const index = openingsOf(histRef.current.present).length;
    onEdit({ type: 'addOpening', opening: o });
    setOpeningDefaults({ kind: o.kind, wall_hint: o.wall_hint ?? null });
    setDraft(null);
    setSelection({ kind: 'opening', index });
  };
  const setReference = (pixels: Line, metres: number, label: string) => {
    onEdit({ type: 'setReference', value: { pixels, metres, label } });
    setDraft(null);
    setSelection({ kind: 'reference' });
  };
  const addLength = (pixels: Line, metres: number, label: string) => {
    const index = lengthsOf(histRef.current.present).length;
    onEdit({ type: 'addKnownLength', value: { pixels, metres, label } });
    setDraft(null);
    setSelection({ kind: 'known_length', index });
  };

  // ---- save / auto / build -----------------------------------------------------------------------------
  const save = useCallback(async (): Promise<boolean> => {
    const s = slugRef.current;
    if (!s || load.status !== 'ready') return false;
    const sent = histRef.current.present;
    const local = localIssues(sent);
    if (local.length) {
      setIssues({ list: local, doc: sent });
      setSaveMsg({ text: `Not saved: ${local.length} problem${local.length > 1 ? 's' : ''} to fix`, kind: 'error' });
      return false;
    }
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await api.saveAnnotations(s, sent);
      if (res.ok) {
        dispatch({ type: 'markSaved', doc: sent });
        setIssues(null);
        setSaveMsg({ text: `Saved ${new Date().toLocaleTimeString()}`, kind: 'ok' });
        void refreshWorld(s);
        return true;
      }
      setIssues({ list: res.issues, doc: sent });
      setSaveMsg({ text: `Not saved: ${res.issues.length} validation error${res.issues.length > 1 ? 's' : ''}`, kind: 'error' });
      return false;
    } catch (e) {
      setSaveMsg({ text: `Save failed: ${errText(e)}`, kind: 'error' });
      return false;
    } finally {
      setSaving(false);
    }
  }, [load.status, refreshWorld]);

  const runAuto = async () => {
    const s = slugRef.current;
    if (!s || busy) return;
    if (isDirty(histRef.current) && !(await save())) {
      setAutoError('Auto not started: unsaved changes could not be saved (see the problems listed).');
      return;
    }
    setBusy('auto');
    setAutoError(null);
    setAutoResult(null);
    try {
      const summary = await api.runAuto(s, ml);
      setAutoResult(summary);
      const ann = await api.getAnnotations(s); // auto may add detected objects and openings
      if (slugRef.current === s) {
        dispatch({ type: 'load', doc: ann });
        setSelection(null);
        setDraft(null);
        setIssues(null);
      }
      setRevision((n) => n + 1);
      await Promise.all([refreshWorld(s), refreshCamera(s)]);
    } catch (e) {
      setAutoError(`Auto failed: ${errText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const runBuild = async () => {
    const s = slugRef.current;
    if (!s || busy) return;
    setBusy('build');
    setBuildError(null);
    setBuildResult(null);
    try {
      const r = await api.build(s, force);
      setBuildResult(r);
      setRevision((n) => n + 1);
      await refreshWorld(s);
      setMainView('result');
    } catch (e) {
      setBuildError(`Build failed: ${errText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  // ---- keyboard -----------------------------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      if (mod && key === 's') {
        e.preventDefault();
        if (dirtyRef.current && !saving) void save();
        return;
      }
      if (isTextInput(e.target) || !ready || busy === 'auto') return;
      if (mod && key === 'z') {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? 'redo' : 'undo' });
        return;
      }
      if (mod && key === 'y') {
        e.preventDefault();
        dispatch({ type: 'redo' });
        return;
      }
      if (mod || e.altKey) return;
      const drawing = tool === 'boundary' && polylineRef.current.length > 0;
      if (drawing && e.key === 'Enter') {
        e.preventDefault();
        finishBoundary();
        return;
      }
      if (drawing && (e.key === 'Escape' || e.key === 'Delete' || e.key === 'Backspace')) {
        e.preventDefault();
        setPolyline((pts) => (e.key === 'Escape' ? [] : popPoint(pts)));
        return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selection) {
          e.preventDefault();
          deleteSelection();
        }
        return;
      }
      if (e.key === 'Escape') {
        if (draft) setDraft(null);
        else setSelection(null);
        return;
      }
      if (e.key === '0') {
        setFitSignal((n) => n + 1);
        return;
      }
      if (e.key === '1' || e.key === '2' || e.key === '3') {
        if (tool === 'boundary') setBoundaryKind(BOUNDARY_KINDS[Number(e.key) - 1]);
        else setAxis(AXES[Number(e.key) - 1]);
        return;
      }
      const t = TOOL_BY_KEY[key];
      if (t) {
        setTool(t);
        setMainView('photo');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // ---- derived ---------------------------------------------------------------------------------------------
  const issueMap = useMemo(() => (issues ? issuesByItem(issues.list, issues.doc) : new Map<string, ValidationIssue[]>()), [issues]);
  const errorKeys = useMemo(() => new Set([...issueMap.keys()].filter(Boolean)), [issueMap]);
  const selectionIssues = selection && issues ? (issueMap.get(refKey(selection)) ?? []).map((i) => describeIssue(i, issues.doc)) : [];

  const imageUrl = slug ? api.imageUrl(slug) : '';
  const overlayUrl = slug ? api.fileUrl(slug, 'output/world/overlay.png', revision) : null;
  const overlayState = useImageAvailable(ready ? overlayUrl : null);
  const natural = useNaturalSize(ready && imageUrl ? imageUrl : null);
  const sizeOk = Array.isArray(doc.image_size) && doc.image_size[0] > 0 && doc.image_size[1] > 0;
  const imageSize: [number, number] = sizeOk ? [doc.image_size[0], doc.image_size[1]] : (natural ?? [1, 1]);
  const sizeMismatch = natural && sizeOk && (natural[0] !== doc.image_size[0] || natural[1] !== doc.image_size[1]);
  const toolInfo = TOOLS.find((t) => t.id === tool)!;
  const fileLink = (p: string) => (slug ? api.fileUrl(slug, worldRelative(p, world?.paths?.root)) : '#');

  const pickWorld = (s: string) => {
    if (s && s !== slug) window.location.hash = hashForSlug(s);
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Room annotator</span>
        <select className="world-picker" value={slug ?? ''} onChange={(e) => pickWorld(e.target.value)} aria-label="World" title="World">
          {!slug && <option value="">choose a world...</option>}
          {slug && !(worlds ?? []).some((w) => w.slug === slug) && <option value={slug}>{slug}</option>}
          {(worlds ?? []).map((w) => (
            <option key={w.slug} value={w.slug}>
              {w.slug}
            </option>
          ))}
        </select>
        <span className="save-state" aria-live="polite">
          {dirty ? <span className="dirty">● Unsaved changes</span> : ready ? <span className="clean">All changes saved</span> : null}
          {saveMsg && <span className={saveMsg.kind === 'error' ? 'error' : 'ok'}> · {saveMsg.text}</span>}
        </span>
        <span className="spacer" />
        <div className="seg" role="tablist" aria-label="Main view">
          <button type="button" role="tab" aria-selected={mainView === 'photo'} className={mainView === 'photo' ? 'active' : ''} onClick={() => setMainView('photo')}>
            Photo
          </button>
          <button type="button" role="tab" aria-selected={mainView === 'result'} className={mainView === 'result' ? 'active' : ''} onClick={() => setMainView('result')}>
            Result
          </button>
        </div>
        <button type="button" onClick={() => dispatch({ type: 'undo' })} disabled={!ready || !canUndo(hist) || busy === 'auto'} title="Undo (Ctrl+Z)">
          Undo
        </button>
        <button type="button" onClick={() => dispatch({ type: 'redo' })} disabled={!ready || !canRedo(hist) || busy === 'auto'} title="Redo (Ctrl+Shift+Z)">
          Redo
        </button>
        <button type="button" className="primary" onClick={() => void save()} disabled={!dirty || saving || !!busy} title="Save annotations.json (Ctrl+S)">
          {saving ? <Spinner /> : null} Save
        </button>
      </header>

      {worldsError && <div className="banner error">{worldsError}</div>}
      {load.status === 'error' && <div className="banner error">Could not load world "{slug}": {load.message}</div>}
      {sizeMismatch && (
        <div className="banner warn">
          The photo is {natural![0]}×{natural![1]} px but annotations.json says image_size {doc.image_size[0]}×{doc.image_size[1]}; overlays use image_size.
        </div>
      )}

      {!slug ? (
        <main className="picker">
          <h2>Choose a world</h2>
          {worlds === null && !worldsError && <p className="muted">Loading worlds...</p>}
          {worlds && worlds.length === 0 && (
            <p className="muted">
              No worlds in this workspace yet. Stage a photo with <code>room_gen project</code> first.
            </p>
          )}
          <ul className="world-cards">
            {(worlds ?? []).map((w) => (
              <li key={w.slug}>
                <a href={hashForSlug(w.slug)}>
                  <b>{w.slug}</b>
                  <span className="muted small">
                    {w.has_annotations ? 'annotated' : 'not annotated'} · {w.has_room ? 'room' : 'no room'} ·{' '}
                    {w.latest_room_index != null ? `build #${w.latest_room_index}` : 'not built'}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </main>
      ) : (
        <main className={`workspace view-${mainView}`}>
          {mainView === 'photo' && <Toolbar tool={tool} onTool={setTool} />}
          <div className="main-area">
            {load.status === 'loading' && (
              <div className="center-msg">
                <Spinner /> Loading {slug}...
              </div>
            )}
            {ready && mainView === 'photo' && (
              <Viewport
                imageUrl={imageUrl}
                overlayUrl={overlayState === 'ok' ? overlayUrl : null}
                imageSize={imageSize}
                doc={doc}
                tool={tool}
                axis={axis}
                selection={selection}
                draft={draft}
                layers={layers}
                camera={camera}
                errorKeys={errorKeys}
                fitSignal={fitSignal}
                onSelect={setSelection}
                onEdit={onEdit}
                onGestureEnd={onGestureEnd}
                onDraft={onDraft}
                boundaryKind={boundaryKind}
                polyline={polyline}
                onBoundaryPoint={onBoundaryPoint}
                onBoundaryFinish={finishBoundary}
              />
            )}
            {ready && mainView === 'result' && <ResultView slug={slug} index={world?.state.latest_room_index} revision={revision} />}
            {busy === 'auto' && (
              <div className="busy-overlay">
                <Spinner /> Running auto (about 30 s)...
              </div>
            )}
          </div>

          <aside className="sidepanel">
            {mainView === 'photo' && (
              <section className="panel tool-help">
                <h3>
                  {toolInfo.label} <kbd>{toolInfo.key}</kbd>
                </h3>
                <p className="small">{toolInfo.hint}</p>
                {tool === 'boundary' && (
                  <>
                    <div className="row tight wrap" role="radiogroup" aria-label="Boundary kind">
                      {BOUNDARY_KINDS.map((kd, i) => (
                        <button
                          key={kd}
                          type="button"
                          role="radio"
                          aria-checked={boundaryKind === kd}
                          className={`axis-btn ${boundaryKind === kd ? 'active' : ''}`}
                          style={{ color: BOUNDARY_COLOR[kd] }}
                          title={`${BOUNDARY_LABEL[kd]} (${i + 1})`}
                          onClick={() => setBoundaryKind(kd)}
                        >
                          {BOUNDARY_LABEL[kd]}
                        </button>
                      ))}
                    </div>
                    {polyline.length > 0 && (
                      <div className="row">
                        <span className="small muted">
                          {polyline.length} point{polyline.length === 1 ? '' : 's'}
                        </span>
                        <button type="button" className="small primary" disabled={polyline.length < 2} onClick={finishBoundary} title="Finish (Enter or double-click)">
                          Finish line
                        </button>
                        <button type="button" className="small" onClick={() => setPolyline(popPoint)} title="Remove the last point (Backspace)">
                          Undo point
                        </button>
                        <button type="button" className="small" onClick={() => setPolyline([])} title="Discard (Esc)">
                          Cancel
                        </button>
                      </div>
                    )}
                  </>
                )}
                {tool === 'calib' && (
                  <div className="row tight" role="radiogroup" aria-label="Calibration axis">
                    {AXES.map((a, i) => (
                      <button
                        key={a}
                        type="button"
                        role="radio"
                        aria-checked={axis === a}
                        className={`axis-btn ${axis === a ? 'active' : ''}`}
                        style={{ color: AXIS_COLOR[a] }}
                        title={`axis ${a} (${i + 1})`}
                        onClick={() => setAxis(a)}
                      >
                        {a}
                      </button>
                    ))}
                  </div>
                )}
              </section>
            )}

            {ready && slug && draft && (
              <section className="panel">
                <DraftForm
                  draft={draft}
                  doc={doc}
                  slug={slug}
                  archetypes={archetypes}
                  hasCamera={!!camera}
                  openingDefaults={openingDefaults}
                  onAddObject={addObject}
                  onAddOpening={addOpening}
                  onSetReference={setReference}
                  onAddLength={addLength}
                  onCancel={() => setDraft(null)}
                />
              </section>
            )}
            {ready && slug && !draft && selection && itemExists(doc, selection) && (
              <section className="panel">
                <SelectionEditor
                  doc={doc}
                  selection={selection}
                  slug={slug}
                  archetypes={archetypes}
                  hasCamera={!!camera}
                  issues={selectionIssues}
                  onEdit={onEdit}
                  onDelete={deleteSelection}
                />
              </section>
            )}

            {issues && issues.list.length > 0 && (
              <section className="panel issues-panel">
                <h3>Validation problems</h3>
                {issues.doc !== doc && <p className="small muted">From the last save attempt; the document has changed since.</p>}
                <ul className="issues">
                  {issues.list.map((issue, i) => {
                    const refs = refsForIssue(issue, issues.doc);
                    return (
                      <li key={i}>
                        {refs.length > 0 ? (
                          <button
                            type="button"
                            className="link"
                            onClick={() => {
                              setSelection(refs[0]);
                              setDraft(null);
                              setMainView('photo');
                            }}
                          >
                            {describeIssue(issue, issues.doc)}
                          </button>
                        ) : (
                          describeIssue(issue, issues.doc)
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            {ready && (
              <>
                <details className="panel" open>
                  <summary>Pipeline</summary>
                  <PipelinePanel
                    world={world}
                    busy={busy}
                    dirty={dirty}
                    ml={ml}
                    onMl={setMl}
                    force={force}
                    onForce={setForce}
                    onRunAuto={() => void runAuto()}
                    onBuild={() => void runBuild()}
                    autoResult={autoResult}
                    autoError={autoError}
                    buildResult={buildResult}
                    buildError={buildError}
                    fileLink={fileLink}
                  />
                </details>
                <details className="panel" open>
                  <summary>Layers</summary>
                  <LayersPanel layers={layers} onChange={setLayers} hasCamera={!!camera} overlay={overlayState} cameraNote={cameraNote} />
                </details>
                <details className="panel" open>
                  <summary>Items</summary>
                  <ItemList
                    doc={doc}
                    selection={selection}
                    errorKeys={errorKeys}
                    onSelect={(r) => {
                      setSelection(r);
                      setDraft(null);
                    }}
                    onEdit={onEdit}
                  />
                </details>
                <details className="panel">
                  <summary>Keyboard</summary>
                  <dl className="shortcuts">
                    {SHORTCUTS.map(([k, v]) => (
                      <div key={k}>
                        <dt>
                          <kbd>{k}</kbd>
                        </dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </>
            )}
          </aside>
        </main>
      )}
    </div>
  );
}
