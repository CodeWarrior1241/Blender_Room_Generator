import { describe, expect, it, vi } from 'vitest';
import type { Annotations } from '../types/annotations';
import { ApiError, createApi } from './api';

const doc: Annotations = {
  world: 'living',
  image: 'source/0-photo.png',
  image_size: [1280, 960],
  objects: [],
  boundary_lines: [{ kind: 'wall_floor', pixels: [[0, 700], [640, 610], [1280, 650]], provenance: { by: 'human', tool: 'annotator', confidence: 0.9 } }],
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('api client', () => {
  it('PUTs the document as JSON and returns ok', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, { ok: true, objects: 3, openings: 1 }));
    const api = createApi({ fetch });
    const res = await api.saveAnnotations('living room', doc);
    expect(res).toEqual({ ok: true, objects: 3, openings: 1 });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/worlds/living%20room/annotations');
    expect(init.method).toBe('PUT');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual(doc);
    expect(JSON.parse(init.body as string).boundary_lines).toEqual(doc.boundary_lines); // nothing dropped
  });

  it('parses a 422 {ok:false, errors} into issues', async () => {
    const body = {
      ok: false,
      errors: [
        { type: 'string_pattern_mismatch', loc: ['objects', 0, 'id'], msg: "String should match pattern '^[a-z0-9][a-z0-9_-]*$'", input: 'Bad Id', ctx: { pattern: '^[a-z0-9][a-z0-9_-]*$' } },
        { type: 'greater_than', loc: ['calibration', 'reference', 'metres'], msg: 'Input should be greater than 0', input: 0 },
      ],
    };
    const api = createApi({ fetch: async () => jsonResponse(422, body) });
    const res = await api.saveAnnotations('living', doc);
    expect(res.ok).toBe(false);
    if (res.ok) return;
    expect(res.status).toBe(422);
    expect(res.issues).toHaveLength(2);
    expect(res.issues[0].loc).toEqual(['objects', 0, 'id']);
    expect(res.issues[1].msg).toBe('Input should be greater than 0');
  });

  it('parses a FastAPI-style 422 {detail:[...]}', async () => {
    const api = createApi({ fetch: async () => jsonResponse(422, { detail: [{ type: 'missing', loc: ['body'], msg: 'Field required' }] }) });
    const res = await api.saveAnnotations('living', doc);
    expect(res).toMatchObject({ ok: false, issues: [{ loc: ['body'], msg: 'Field required' }] });
  });

  it('keeps a 422 with an unreadable body as one document-level issue', async () => {
    const api = createApi({ fetch: async () => new Response('bad', { status: 422 }) });
    const res = await api.saveAnnotations('living', doc);
    expect(res).toMatchObject({ ok: false, issues: [{ loc: [], msg: 'HTTP 422: bad' }] });
  });

  it('throws ApiError with the text of a non-JSON 500', async () => {
    const api = createApi({ fetch: async () => new Response('Internal Server Error', { status: 500 }) });
    await expect(api.saveAnnotations('living', doc)).rejects.toMatchObject({ name: 'ApiError', status: 500, message: 'HTTP 500: Internal Server Error' });
  });

  it('throws ApiError with FastAPI detail for 404', async () => {
    const api = createApi({ fetch: async () => jsonResponse(404, { detail: "world 'x' not found" }) });
    const err = await api.getWorld('x').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("world 'x' not found");
  });

  it('wraps network failures', async () => {
    const api = createApi({ fetch: async () => { throw new TypeError('Failed to fetch'); } });
    await expect(api.listWorlds()).rejects.toMatchObject({ status: 0 });
  });

  it('camera: 409 means not calibrated yet', async () => {
    const api = createApi({ fetch: async () => jsonResponse(409, { detail: 'no calibration yet' }) });
    expect(await api.getCamera('living')).toBeNull();
  });

  it('camera: passes the grid and returns polylines', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, { source: 'room', camera: {}, hfov_deg: 60, floor_grid: [[[0, 0], [1, 1]]], wireframe: [] }));
    const cam = await createApi({ fetch }).getCamera('living', 0.25);
    expect(cam?.floor_grid).toHaveLength(1);
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe('/api/worlds/living/camera?grid=0.25');
  });

  it('auto and build POST JSON bodies', async () => {
    const fetch = vi.fn(async () => jsonResponse(200, { ok: true }));
    const api = createApi({ fetch });
    await api.runAuto('living', 'off');
    await api.build('living', true);
    const calls = fetch.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0][0]).toBe('/api/worlds/living/auto');
    expect(JSON.parse(calls[0][1].body as string)).toEqual({ ml: 'off' });
    expect(calls[1][0]).toBe('/api/worlds/living/build');
    expect(JSON.parse(calls[1][1].body as string)).toEqual({ force: true });
  });

  it('lists worlds and archetypes, resolves labels', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/worlds')) return jsonResponse(200, { worlds: [{ slug: 'living', latest_room_index: 2 }] });
      if (url.includes('/resolve')) return jsonResponse(200, { label: 'couch', archetype: 'sofa', matched: true });
      return jsonResponse(200, { archetypes: [{ name: 'sofa' }] });
    });
    const api = createApi({ fetch });
    expect((await api.listWorlds())[0].slug).toBe('living');
    expect((await api.listArchetypes())[0].name).toBe('sofa');
    expect((await api.resolveArchetype('big couch')).archetype).toBe('sofa');
    expect(fetch.mock.calls[2][0]).toBe('/api/archetypes/resolve?label=big%20couch');
  });

  it('builds file URLs under the world directory', () => {
    const api = createApi();
    expect(api.fileUrl('living', 'output/world/2-world-room.glb', 7)).toBe('/api/worlds/living/files/output/world/2-world-room.glb?v=7');
    expect(api.imageUrl('living')).toBe('/api/worlds/living/image');
  });
});
