// Object ids: same rules as room_gen.models.Slug (pattern + max length) and the same
// derivation as room_gen.indexed.slugify, so ids made here match ids made by the CLI.

export const ID_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;
export const ID_MAX_LENGTH = 80;
export const ID_FALLBACK = 'object';

export function isValidId(id: string): boolean {
  return id.length > 0 && id.length <= ID_MAX_LENGTH && ID_PATTERN.test(id);
}

/**
 * Same output as `room_gen.indexed.slugify` (lower-case, non-[a-z0-9] runs become '-', trimmed,
 * then cut to 80), except that an empty result becomes "object" so it is always a valid id.
 */
export function slugify(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, ID_MAX_LENGTH);
  return slug || ID_FALLBACK;
}

/** `base` slugified, then suffixed `-2`, `-3`, ... until it is not in `taken`. */
export function uniqueId(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const root = isValidId(base) ? base : slugify(base);
  if (!used.has(root)) return root;
  for (let n = 2; ; n++) {
    const suffix = `-${n}`;
    const candidate = `${root.slice(0, ID_MAX_LENGTH - suffix.length).replace(/-+$/g, '')}${suffix}`;
    if (!used.has(candidate)) return candidate;
  }
}

/** Why `id` cannot be used (null when it can). `taken` should exclude the object's own id. */
export function idProblem(id: string, taken: Iterable<string>): string | null {
  if (!id) return 'id is required';
  if (id.length > ID_MAX_LENGTH) return `id is longer than ${ID_MAX_LENGTH} characters`;
  if (!ID_PATTERN.test(id)) return 'id must match ^[a-z0-9][a-z0-9_-]*$ (lower-case letters, digits, _ and -)';
  for (const t of taken) if (t === id) return `id "${id}" is already used`;
  return null;
}
