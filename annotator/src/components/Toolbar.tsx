import type { ReactNode } from 'react';
import { TOOLS, type Tool } from '../lib/ui';

const ICONS: Record<Tool, ReactNode> = {
  select: <path d="M5 3l13 7-6 1.5L9 18z" />,
  box: <rect x="4" y="5" width="16" height="14" rx="1" />,
  opening: (
    <>
      <path d="M6 21V4h12v17" />
      <path d="M3 21h18" />
      <circle cx="15" cy="13" r="0.9" fill="currentColor" />
    </>
  ),
  corner: (
    <>
      <path d="M3 8l9 7 9-7" />
      <path d="M12 15v6" />
      <circle cx="12" cy="15" r="2.2" fill="currentColor" />
    </>
  ),
  boundary: (
    <>
      <path d="M12 3v11" />
      <path d="M12 14L3 19M12 14l9 5" />
      <circle cx="12" cy="3.5" r="1.4" fill="currentColor" />
      <circle cx="12" cy="14" r="1.4" fill="currentColor" />
    </>
  ),
  calib: (
    <>
      <path d="M3 9L21 5" />
      <path d="M3 19l18-6" />
    </>
  ),
  reference: (
    <>
      <path d="M12 4v16" />
      <path d="M8 4h8M8 20h8" />
    </>
  ),
  length: (
    <>
      <path d="M3 14l18-4" />
      <path d="M3 11v6M21 7v6" />
    </>
  ),
};

export default function Toolbar({ tool, onTool }: { tool: Tool; onTool: (t: Tool) => void }) {
  return (
    <nav className="toolbar" aria-label="Tools">
      {TOOLS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`tool ${tool === t.id ? 'active' : ''}`}
          title={`${t.label} (${t.key})\n${t.hint}`}
          aria-label={`${t.label} (${t.key})`}
          aria-pressed={tool === t.id}
          onClick={() => onTool(t.id)}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            {ICONS[t.id]}
          </svg>
          <span className="tool-key">{t.key}</span>
        </button>
      ))}
    </nav>
  );
}
