/** Human confirmation for mutating WebMCP tools; an agent cannot answer it for the user. */

export async function confirmAgentAction(message: string): Promise<boolean> {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true;
  }
  return window.confirm(message);
}
