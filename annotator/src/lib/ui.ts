// UI vocabulary shared by the components (no React here).

import type { Axis, BoundaryKind } from './annotations';
import type { Box, Line, Quad } from './geometry';

export type Tool = 'select' | 'box' | 'opening' | 'corner' | 'boundary' | 'calib' | 'reference' | 'length';

export interface ToolInfo {
  id: Tool;
  label: string;
  key: string;
  hint: string;
}

export const TOOLS: readonly ToolInfo[] = [
  {
    id: 'select',
    label: 'Select / move',
    key: 'V',
    hint: 'Click an item to select it; drag its body to move it or a handle to reshape it. Drag empty space to pan. Delete removes the selection.',
  },
  { id: 'box', label: 'Object box', key: 'B', hint: 'Drag a rectangle around an object, then name it in the side panel.' },
  { id: 'opening', label: 'Opening', key: 'O', hint: 'Click two opposite corners of a door, window or wall opening.' },
  {
    id: 'corner',
    label: 'Floor corner',
    key: 'F',
    hint: 'Click each visible point where two walls meet the floor, left to right.',
  },
  {
    id: 'boundary',
    label: 'Boundary line',
    key: 'W',
    hint:
      'Trace a visible stretch of the wall/floor or wall/ceiling boundary, or a vertical room corner (wall/wall), click by click. ' +
      'Only room boundaries: not furniture edges, skirting on furniture or curtain hems. Keys 1 / 2 / 3 pick the kind. ' +
      'Enter or double-click finishes, Backspace removes the last point, Esc cancels.',
  },
  {
    id: 'calib',
    label: 'Calibration lines',
    key: 'C',
    hint: 'Draw two image lines that are parallel in the room (two clicks each). Keys 1 / 2 / 3 pick axis x / y / z (z = vertical).',
  },
  {
    id: 'reference',
    label: 'Reference height',
    key: 'R',
    hint: 'Click the BOTTOM (where it stands on the floor), then the top of something vertical of known height. Shift snaps to image-vertical.',
  },
  { id: 'length', label: 'Known length', key: 'L', hint: 'Click two points on the floor a known distance apart.' },
];

export const TOOL_BY_KEY: Readonly<Record<string, Tool>> = Object.fromEntries(TOOLS.map((t) => [t.key.toLowerCase(), t.id]));

export const AXES: readonly Axis[] = ['x', 'y', 'z'];

/** Colour per boundary-line kind (CSS custom properties defined in styles.css). */
export const BOUNDARY_COLOR: Readonly<Record<BoundaryKind, string>> = {
  wall_floor: 'var(--c-wall-floor)',
  wall_ceiling: 'var(--c-wall-ceiling)',
  wall_wall: 'var(--c-wall-wall)',
};

/** Short on-photo label per boundary-line kind. */
export const BOUNDARY_SHORT: Readonly<Record<BoundaryKind, string>> = {
  wall_floor: 'floor',
  wall_ceiling: 'ceiling',
  wall_wall: 'corner',
};

/** Colour per calibration axis (CSS custom properties defined in styles.css). */
export const AXIS_COLOR: Readonly<Record<Axis, string>> = {
  x: 'var(--axis-x)',
  y: 'var(--axis-y)',
  z: 'var(--axis-z)',
};

/** A drawn shape waiting for the side-panel form (label, metres, ...) before it is added. */
export type Draft =
  | { kind: 'object'; box: Box }
  | { kind: 'opening'; quad: Quad }
  | { kind: 'reference'; pixels: Line }
  | { kind: 'known_length'; pixels: Line };

export interface Layers {
  /** items with provenance auto/fit (drawn dashed) */
  auto: boolean;
  /** items made or edited by a person, plus calibration hints (drawn solid) */
  human: boolean;
  labels: boolean;
  grid: boolean;
  wireframe: boolean;
  /** show output/world/overlay.png instead of the photo */
  overlayBackground: boolean;
}

export const DEFAULT_LAYERS: Layers = {
  auto: true,
  human: true,
  labels: true,
  grid: true,
  wireframe: true,
  overlayBackground: false,
};

export type MlMode = 'auto' | 'on' | 'off';

export function readHashSlug(hash: string): string | null {
  const m = /^#\/?([^/?#]+)/.exec(hash);
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return m[1];
  }
}

export function hashForSlug(slug: string): string {
  return `#/${encodeURIComponent(slug)}`;
}

/** Strip the world directory prefix from a workspace-relative path returned by build/auto. */
export function worldRelative(path: string, worldRoot: string | undefined): string {
  const root = (worldRoot ?? '').replace(/\/+$/, '');
  return root && path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
}

export function isTextInput(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== 'string') return false;
  const el = target as HTMLElement;
  const tag = el.tagName.toLowerCase();
  if (tag === 'textarea' || tag === 'select' || el.isContentEditable) return true;
  if (tag !== 'input') return false;
  const type = ((el as HTMLInputElement).type || 'text').toLowerCase();
  return !['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color'].includes(type);
}
