/** Experimental WebMCP types — https://webmachinelearning.github.io/webmcp/ */

export type JsonSchema = Record<string, unknown>;

export interface ModelContextTool {
  name: string;
  title?: string;
  description: string;
  inputSchema?: JsonSchema;
  execute: (input: Record<string, unknown>) => Promise<unknown>;
}

export interface ModelContextRegisterOptions {
  signal?: AbortSignal;
}

export interface ModelContext {
  registerTool(
    tool: ModelContextTool,
    options?: ModelContextRegisterOptions,
  ): Promise<void>;
}

declare global {
  interface Document {
    modelContext?: ModelContext;
  }
}

export function hasWebMcp(): boolean {
  return typeof document !== 'undefined' && 'modelContext' in document && !!document.modelContext;
}
