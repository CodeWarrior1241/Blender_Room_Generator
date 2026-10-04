// Thin client for room_gen/server.py. All paths are under /api.

import type { Annotations } from '../types/annotations';
import type {
  ArchetypeInfo,
  AutoSummary,
  BuildResult,
  CameraOverlay,
  ResolveResult,
  WorldDetail,
  WorldSummary,
} from '../types/api';
import { type ValidationIssue, parseIssues } from './validation';

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export type SaveResult =
  | { ok: true; objects: number; openings: number }
  | { ok: false; status: number; issues: ValidationIssue[] };

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ApiOptions {
  fetch?: FetchLike;
  base?: string;
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Human-readable message for a failed response body (FastAPI `detail`, room_gen `error`, text). */
export function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === 'object') {
    const b = body as { detail?: unknown; error?: unknown; errors?: unknown };
    if (typeof b.detail === 'string') return b.detail;
    if (typeof b.error === 'string') return b.error;
    const issues = parseIssues(body);
    if (issues.length) return issues.map((i) => `${i.loc.join('.')}: ${i.msg}`).join('; ');
  }
  if (typeof body === 'string' && body.trim()) return `HTTP ${status}: ${body.trim().slice(0, 300)}`;
  return `HTTP ${status}`;
}

export function createApi(options: ApiOptions = {}) {
  const base = (options.base ?? '/api').replace(/\/$/, '');
  const doFetch: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const w = (slug: string) => `${base}/worlds/${encodeURIComponent(slug)}`;

  async function json<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await doFetch(path, init);
    } catch (err) {
      throw new ApiError(0, `cannot reach the room_gen server (${(err as Error).message})`);
    }
    const body = await readBody(res);
    if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, body), body);
    return body as T;
  }

  const post = <T>(path: string, body: unknown) =>
    json<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  return {
    base,
    health: () => json<{ ok: boolean; root: string; annotator_built: boolean }>(`${base}/health`),
    listWorlds: async () => (await json<{ worlds: WorldSummary[] }>(`${base}/worlds`)).worlds,
    getWorld: (slug: string) => json<WorldDetail>(w(slug)),
    getAnnotations: (slug: string) => json<Annotations>(`${w(slug)}/annotations`),

    /** PUT the document. 422 (and FastAPI request errors) come back as `{ok:false, issues}`. */
    async saveAnnotations(slug: string, doc: Annotations): Promise<SaveResult> {
      let res: Response;
      try {
        res = await doFetch(`${w(slug)}/annotations`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(doc),
        });
      } catch (err) {
        throw new ApiError(0, `cannot reach the room_gen server (${(err as Error).message})`);
      }
      const body = await readBody(res);
      if (res.status === 422) {
        const issues = parseIssues(body);
        return { ok: false, status: 422, issues: issues.length ? issues : [{ loc: [], msg: errorMessage(422, body) }] };
      }
      if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, body), body);
      const b = (body ?? {}) as { objects?: number; openings?: number };
      return { ok: true, objects: b.objects ?? 0, openings: b.openings ?? 0 };
    },

    /** Projected floor grid and wireframe; null while the world has no calibration (409). */
    async getCamera(slug: string, grid = 0.5): Promise<CameraOverlay | null> {
      try {
        return await json<CameraOverlay>(`${w(slug)}/camera?grid=${encodeURIComponent(String(grid))}`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) return null;
        throw err;
      }
    },

    async backproject(slug: string, points: [number, number][]): Promise<([number, number] | null)[] | null> {
      try {
        return (await post<{ points: ([number, number] | null)[] }>(`${w(slug)}/backproject`, { points })).points;
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) return null;
        throw err;
      }
    },

    runAuto: (slug: string, ml: 'on' | 'off' | 'auto') => post<AutoSummary>(`${w(slug)}/auto`, { ml }),
    build: (slug: string, force: boolean) => post<BuildResult>(`${w(slug)}/build`, { force }),
    listArchetypes: async () => (await json<{ archetypes: ArchetypeInfo[] }>(`${base}/archetypes`)).archetypes,
    resolveArchetype: (label: string) =>
      json<ResolveResult>(`${base}/archetypes/resolve?label=${encodeURIComponent(label)}`),

    imageUrl: (slug: string) => `${w(slug)}/image`,
    /** URL of a file under the world directory, e.g. `output/world/overlay.png`. */
    fileUrl: (slug: string, path: string, bust?: string | number) =>
      `${w(slug)}/files/${path.split('/').map(encodeURIComponent).join('/')}${bust !== undefined ? `?v=${encodeURIComponent(String(bust))}` : ''}`,
  };
}

export type Api = ReturnType<typeof createApi>;

export const api: Api = createApi();
