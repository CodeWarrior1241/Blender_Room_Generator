import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import type { Line } from '../lib/geometry';

/**
 * Distance in metres between two floor pixels with the current camera (POST /backproject), or
 * null when there is no calibration yet or a point is above the horizon.
 */
export function useFloorDistance(slug: string | null, pixels: Line | null, enabled: boolean): number | null {
  const [dist, setDist] = useState<number | null>(null);
  const key = pixels ? JSON.stringify(pixels) : '';
  useEffect(() => {
    setDist(null);
    if (!slug || !pixels || !enabled) return;
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const pts = await api.backproject(slug, [pixels[0], pixels[1]]);
        if (cancelled || !pts || !pts[0] || !pts[1]) return;
        setDist(Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]));
      } catch {
        /* estimate is optional */
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [slug, key, enabled]);
  return dist;
}

/** Floor positions (metres) of pixels with the current camera; null entries are off the floor. */
export function useFloorPoints(slug: string | null, points: readonly [number, number][], enabled: boolean, revision = 0) {
  const [out, setOut] = useState<([number, number] | null)[] | null>(null);
  const key = JSON.stringify(points);
  useEffect(() => {
    setOut(null);
    if (!slug || !enabled || points.length === 0) return;
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const res = await api.backproject(slug, points.map((p) => [p[0], p[1]] as [number, number]));
        if (!cancelled) setOut(res);
      } catch {
        /* optional */
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [slug, key, enabled, revision]);
  return out;
}

/** 'ok' | 'missing' | 'unknown' for an image URL (used for the optional overlay.png). */
export function useImageAvailable(url: string | null): 'ok' | 'missing' | 'unknown' {
  const [state, setState] = useState<'ok' | 'missing' | 'unknown'>('unknown');
  useEffect(() => {
    setState('unknown');
    if (!url) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => !cancelled && setState('ok');
    img.onerror = () => !cancelled && setState('missing');
    img.src = url;
    return () => {
      cancelled = true;
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);
  return state;
}

/** Natural size of an image, to cross-check annotations.image_size. */
export function useNaturalSize(url: string | null): [number, number] | null {
  const [size, setSize] = useState<[number, number] | null>(null);
  useEffect(() => {
    setSize(null);
    if (!url) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => !cancelled && setSize([img.naturalWidth, img.naturalHeight]);
    img.src = url;
    return () => {
      cancelled = true;
      img.onload = null;
    };
  }, [url]);
  return size;
}
