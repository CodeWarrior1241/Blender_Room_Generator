// The annotation types are generated from schemas/annotations.schema.json (npm run gen:types).
// These tests fail when the schema changes and the generated file was not refreshed.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { generate } from '../../scripts/gen-types.mjs';

const schemaUrl = new URL('../../../schemas/annotations.schema.json', import.meta.url);
const generatedUrl = new URL('./annotations.ts', import.meta.url);

interface JsonSchemaObject {
  required?: string[];
  properties?: Record<string, unknown>;
}

const schema = JSON.parse(readFileSync(schemaUrl, 'utf8')) as JsonSchemaObject & { $defs: Record<string, JsonSchemaObject> };
const generated = readFileSync(generatedUrl, 'utf8');

function interfaceBody(name: string): string {
  const m = new RegExp(`export interface ${name} \\{([\\s\\S]*?)\\n\\}`).exec(generated);
  if (!m) throw new Error(`interface ${name} not found in generated types`);
  return m[1];
}

describe('generated annotation types', () => {
  it('are up to date with the schema (run `npm run gen:types` if this fails)', async () => {
    expect(await generate()).toBe(generated);
  }, 20000);

  const models: [string, JsonSchemaObject][] = [
    ['Annotations', schema],
    ['ObjectAnnotation', schema.$defs.ObjectAnnotation],
    ['OpeningAnnotation', schema.$defs.OpeningAnnotation],
    ['KnownLength', schema.$defs.KnownLength],
    ['Reference', schema.$defs.Reference],
    ['ParallelPair', schema.$defs.ParallelPair],
    ['Provenance', schema.$defs.Provenance],
    ['CalibrationHints', schema.$defs.CalibrationHints],
    ['BoundaryLine', schema.$defs.BoundaryLine],
  ];

  it.each(models)('%s: every schema property exists, required ones are not optional', (name, def) => {
    const body = interfaceBody(name);
    for (const prop of Object.keys(def.properties ?? {})) {
      const required = (def.required ?? []).includes(prop);
      expect(body, `${name}.${prop}`).toMatch(new RegExp(`\\n  ${prop}${required ? '' : '\\?'}: `));
    }
  });

  it('pins the required fields the editor relies on', () => {
    expect(schema.required).toEqual(expect.arrayContaining(['world', 'image', 'image_size']));
    expect(schema.$defs.ObjectAnnotation.required).toEqual(expect.arrayContaining(['id', 'label', 'box']));
    expect(schema.$defs.OpeningAnnotation.required).toEqual(expect.arrayContaining(['kind', 'quad']));
  });
});
