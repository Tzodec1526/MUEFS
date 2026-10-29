/**
 * Experimental WebMCP types — https://webmachinelearning.github.io/webmcp/ (the ModelContext
 * interface as of September 2026). The spec removed provideContext() and clearContext() in
 * March 2026 (webmachinelearning/webmcp#132) and Chrome 147 dropped them.
 */

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
  /** Unregisters the tool when aborted. */
  signal?: AbortSignal;
  exposedTo?: string[];
}

export interface RegisteredTool {
  name: string;
  title?: string;
  description: string;
}

export interface ModelContext {
  /**
   * Rejects (InvalidStateError) when the document already has a tool of that name, declarative
   * forms included. Chrome before 151 returns undefined and throws instead.
   */
  registerTool(
    tool: ModelContextTool,
    options?: ModelContextRegisterOptions,
  ): Promise<void>;
  getTools?(options?: { signal?: AbortSignal }): Promise<RegisteredTool[]>;
  executeTool?(tool: RegisteredTool, input?: Record<string, unknown>): Promise<string>;
  ontoolchange?: ((event: Event) => void) | null;
  addEventListener?(type: string, listener: (event: Event) => void): void;
  removeEventListener?(type: string, listener: (event: Event) => void): void;
}

declare global {
  interface Document {
    /** The spec's location, in Chrome from 150. */
    modelContext?: ModelContext;
  }
  interface Navigator {
    /** The earlier location: Chrome 146 to 151 (deprecated in 150, removed in 152). */
    modelContext?: ModelContext;
  }
}
