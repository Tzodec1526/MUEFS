import { isDemoBuild } from '../config/demoMode';
import {
  isClerkRole, isFilerRole, TOOL_DEFINITIONS, type ToolDefinition, type ToolName, type ToolTier,
} from './definitions';

/** What the /agent page and get_agent_catalog show for a tool. */
export interface CatalogEntry {
  name: ToolName;
  title: string;
  description: string;
  readOnly: boolean;
  tier: ToolTier;
}

function availableInBuild(tool: ToolDefinition): boolean {
  return !tool.demoOnly || isDemoBuild();
}

/** Whether this role may use the tool in this build; registration and execution both ask. */
export function roleMayUse(tool: ToolDefinition, role: string | null): boolean {
  if (!availableInBuild(tool)) return false;
  switch (tool.audience) {
    case 'everyone': return true;
    case 'filer': return isFilerRole(role);
    case 'clerk': return isClerkRole(role);
  }
}

/** The tools registered for this role in this build, in registration order. */
export function toolsForRole(role: string | null): readonly ToolDefinition<ToolName>[] {
  return TOOL_DEFINITIONS.filter(tool => roleMayUse(tool, role));
}

function toCatalogEntry({ name, title, description, annotations, tier }: ToolDefinition<ToolName>): CatalogEntry {
  return { name, title, description, readOnly: annotations.readOnlyHint === true, tier };
}

export function catalogForRole(role: string | null): CatalogEntry[] {
  return toolsForRole(role).map(toCatalogEntry);
}

/** Every tool this build can register for some role. */
export function catalogForBuild(): CatalogEntry[] {
  return TOOL_DEFINITIONS.filter(availableInBuild).map(toCatalogEntry);
}
