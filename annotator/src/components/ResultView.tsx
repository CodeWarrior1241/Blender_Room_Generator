import { Suspense, lazy, useEffect, useState } from 'react';
import { api } from '../lib/api';

const GlbViewer = lazy(() => import('./GlbViewer'));

function Picture({ src, alt, missing }: { src: string; alt: string; missing: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  if (failed) return <div className="missing">{missing}</div>;
  return (
    <a href={src} target="_blank" rel="noreferrer" title="Open full size">
      <img src={src} alt={alt} onError={() => setFailed(true)} />
    </a>
  );
}

/** Latest build outputs: room GLB, preview render, plan, and the auto overlay. */
export default function ResultView({ slug, index, revision }: { slug: string; index: number | null | undefined; revision: number }) {
  const file = (name: string) => api.fileUrl(slug, `output/world/${name}`, `${index ?? 'none'}-${revision}`);
  return (
    <div className="result">
      {index == null ? (
        <div className="result-empty">
          <p>No build yet. Run auto (it writes room.json), then Build.</p>
        </div>
      ) : (
        <>
          <section className="result-3d">
            <h3>
              Room model <span className="muted small">{index}-world-room.glb</span>
            </h3>
            <Suspense fallback={<div className="glb-msg">Loading viewer...</div>}>
              <GlbViewer url={file(`${index}-world-room.glb`)} />
            </Suspense>
          </section>
          <section>
            <h3>
              Preview <span className="muted small">{index}-world-room-preview.png</span>
            </h3>
            <Picture src={file(`${index}-world-room-preview.png`)} alt="Room preview render" missing="No preview render for this build." />
          </section>
          <section>
            <h3>
              Plan <span className="muted small">{index}-world-plan.png</span>
            </h3>
            <Picture src={file(`${index}-world-plan.png`)} alt="Floor plan" missing="No plan image for this build." />
          </section>
        </>
      )}
      <section>
        <h3>
          Auto overlay <span className="muted small">overlay.png</span>
        </h3>
        <Picture src={file('overlay.png')} alt="Auto pipeline overlay" missing="No overlay yet: run auto." />
      </section>
    </div>
  );
}
