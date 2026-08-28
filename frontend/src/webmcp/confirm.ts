/** Soft human confirmation for mutating WebMCP tools. */

export async function confirmAgentAction(message: string): Promise<boolean> {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') {
    return true;
  }
  return window.confirm(message);
}

export function wantsConfirmation(input: Record<string, unknown>): boolean {
  return input.confirmed !== true && input.confirmed !== 'true';
}
