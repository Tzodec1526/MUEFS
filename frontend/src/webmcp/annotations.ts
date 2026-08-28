/** WebMCP tool annotation helpers (spec § ToolAnnotations). */

import type { ModelContextTool } from './types';

export type ToolAnnotations = NonNullable<ModelContextTool['annotations']>;

/** Read-only lookup — no state changes on the server. */
export const READ_ONLY: ToolAnnotations = { readOnlyHint: true };

/** Returns user-generated or court record text agents must not treat as instructions. */
export const UNTRUSTED_RECORDS: ToolAnnotations = {
  readOnlyHint: true,
  untrustedContentHint: true,
};

/** Mutating court action — agent should confirm with the human filer/clerk first. */
export const MUTATING: ToolAnnotations = { readOnlyHint: false };
