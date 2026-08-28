/** Experimental WebMCP types — https://webmachinelearning.github.io/webmcp/ */

export type JsonSchema = Record<string, unknown>;

export interface ModelContextTool {
  name: string;
  title?: string;
  description: string;
  inputSchema?: JsonSchema;
  annotations?: {
    readOnlyHint?: boolean;
    untrustedContentHint?: boolean;
  };
  execute: (input: Record<string, unknown>) => Promise<unknown>;
}

export interface ModelContextRegisterOptions {
  signal?: AbortSignal;
  exposedTo?: string[];
}

export interface RegisteredTool {
  name: string;
  title?: string;
  description: string;
}

export interface ModelContext {
  registerTool(
    tool: ModelContextTool,
    options?: ModelContextRegisterOptions,
  ): Promise<void>;
  getTools?(options?: { signal?: AbortSignal }): Promise<RegisteredTool[]>;
  executeTool?(tool: RegisteredTool, input?: Record<string, unknown>): Promise<string>;
  provideContext?(context: Record<string, unknown>): void | Promise<void>;
  ontoolchange?: ((event: Event) => void) | null;
  addEventListener?(type: string, listener: (event: Event) => void): void;
  removeEventListener?(type: string, listener: (event: Event) => void): void;
}

declare global {
  interface Document {
    modelContext?: ModelContext;
  }
}

export function hasWebMcp(): boolean {
  return typeof document !== 'undefined' && 'modelContext' in document && !!document.modelContext;
}
