// Response shapes of room_gen/server.py (hand-written; the server returns plain dicts).
// Everything except what the UI relies on is optional so a newer backend does not break it.

export type Polyline = [number, number][];

export interface WorldStateFlags {
  source_image_count?: number;
  primary_image?: string | null;
  has_image_json?: boolean;
  has_annotations?: boolean;
  has_calibration?: boolean;
  has_room?: boolean;
  has_scene?: boolean;
  latest_world_index?: number | null;
  latest_room_index?: number | null;
  object_count?: number;
  objects_built?: number;
}

/** GET /api/worlds -> {worlds: WorldSummary[]} (slug merged with the state flags). */
export interface WorldSummary extends WorldStateFlags {
  slug: string;
}

/** GET /api/worlds/{slug} */
export interface WorldDetail {
  slug: string;
  project?: { display_name?: string; slug?: string } | null;
  paths?: Record<string, string>;
  state: WorldStateFlags;
  objects?: unknown[];
  annotations?: unknown;
  room?: unknown;
  calibration?: unknown;
}

/** GET /api/worlds/{slug}/camera */
export interface CameraOverlay {
  source: string;
  camera: Record<string, unknown>;
  hfov_deg: number;
  floor_grid: Polyline[];
  wireframe: Polyline[];
}

export interface ArchetypeInfo {
  name: string;
  category?: string;
  description?: string;
  defaults?: Record<string, unknown>;
  ranges?: Record<string, [number, number]>;
  material_slots?: Record<string, string | null>;
  synonyms?: string[];
  /** floor | wall | ceiling | surface */
  support?: string;
  against_wall?: boolean;
}

export interface ResolveResult {
  label: string;
  archetype: string;
  matched: boolean;
}

/** POST /api/worlds/{slug}/auto (room_gen.pipeline.run_auto + ok) */
export interface AutoSummary {
  ok: boolean;
  world?: string;
  image?: string;
  models?: Record<string, string> | null;
  calibration?: {
    method?: string;
    focal_px?: number;
    hfov_deg?: number;
    confidence?: number;
    finite_vanishing_points?: number;
    residual_deg?: number;
  };
  scale?: { camera_height_m?: number; source?: string; confidence?: number };
  shell?: {
    size_m?: [number, number];
    ceiling_height?: number;
    visible_edges?: unknown;
    openings?: number;
    confidence?: number | null;
  };
  fit?: unknown;
  objects?: { id: string; archetype?: string; size_m?: number[]; confidence?: number; notes?: unknown }[];
  textures?: Record<string, unknown>;
  overlay?: string;
  notes?: string[];
  seconds?: Record<string, number>;
}

/** POST /api/worlds/{slug}/build (room_gen.build.build + ok) */
export interface BuildResult {
  ok: boolean;
  status?: 'built' | 'up-to-date' | string;
  world?: string;
  index?: number;
  seconds?: number | null;
  message?: string;
  files?: Record<string, string>;
  thumbnail?: string | null;
  manifest?: string;
  objects?: { id: string; faces?: number; dimensions?: number[] }[];
  failed_outputs?: unknown;
  warnings?: string[];
}
