/**
 * Agent input is checked against the tool's own inputSchema (definitions.ts) before the tool
 * runs, so no implementation sees a value its schema does not allow. In particular every id
 * the tools put into an API path or query must be an integer, never text such as
 * "../documents/12/download".
 */

import type { JsonSchema } from './types';

interface PropertySchema {
  type?: 'integer' | 'number' | 'string' | 'boolean';
  enum?: readonly unknown[];
  minimum?: number;
  maximum?: number;
  maxLength?: number;
}

function problemWith(name: string, value: unknown, schema: PropertySchema): string | null {
  switch (schema.type) {
    case 'integer':
      if (typeof value !== 'number' || !Number.isInteger(value)) return `${name} must be an integer.`;
      break;
    case 'number':
      if (typeof value !== 'number' || !Number.isFinite(value)) return `${name} must be a number.`;
      break;
    case 'string':
      if (typeof value !== 'string') return `${name} must be a string.`;
      break;
    case 'boolean':
      if (typeof value !== 'boolean') return `${name} must be true or false.`;
      break;
  }
  if (schema.enum && !schema.enum.includes(value)) {
    return `${name} must be one of: ${schema.enum.join(', ')}.`;
  }
  if (typeof value === 'number') {
    const { minimum = -Infinity, maximum = Infinity } = schema;
    if (value < minimum || value > maximum) {
      return Number.isFinite(minimum) && Number.isFinite(maximum)
        ? `${name} must be from ${minimum} to ${maximum}.`
        : Number.isFinite(minimum) ? `${name} must be at least ${minimum}.` : `${name} must be at most ${maximum}.`;
    }
  }
  if (typeof value === 'string' && schema.maxLength !== undefined && value.length > schema.maxLength) {
    return `${name} must be at most ${schema.maxLength} characters.`;
  }
  return null;
}

export type CheckedInput = { ok: true; input: Record<string, unknown> } | { ok: false; error: string };

/**
 * Check agent input against a tool's object schema. Null stands for an omitted optional
 * value and is dropped; properties the schema does not name pass through unchecked.
 */
export function checkToolInput(schema: JsonSchema, raw: unknown): CheckedInput {
  if (raw !== undefined && raw !== null && (typeof raw !== 'object' || Array.isArray(raw))) {
    return { ok: false, error: 'Tool input must be a JSON object.' };
  }
  // fromEntries defines own properties, so a "__proto__" key cannot supply inherited values.
  const input: Record<string, unknown> = Object.fromEntries(Object.entries((raw ?? {}) as Record<string, unknown>)
    .filter(([, value]) => value !== null && value !== undefined));
  const has = (name: string) => Object.prototype.hasOwnProperty.call(input, name);
  const properties = (schema.properties ?? {}) as Record<string, PropertySchema>;
  for (const name of (schema.required ?? []) as string[]) {
    if (!has(name)) return { ok: false, error: `${name} is required.` };
  }
  for (const [name, propertySchema] of Object.entries(properties)) {
    if (!has(name)) continue;
    const problem = problemWith(name, input[name], propertySchema);
    if (problem) return { ok: false, error: problem };
  }
  return { ok: true, input };
}
