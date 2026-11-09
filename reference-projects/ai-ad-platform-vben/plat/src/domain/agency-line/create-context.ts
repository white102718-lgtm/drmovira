import type { AgencyLineOption } from './types';

export type AgencyLineAdCreationIssue =
  | 'disabled'
  | 'missing-pixel'
  | 'not-bound'
  | 'platform-mismatch';

export interface AgencyLineAdCreationContext {
  agencyLineIds: readonly string[];
  platform: string;
}

export function getAgencyLineAdCreationIssue(
  line: AgencyLineOption,
  context: AgencyLineAdCreationContext,
): AgencyLineAdCreationIssue | undefined {
  if (!context.agencyLineIds.includes(line.id)) return 'not-bound';
  if (line.platform !== context.platform) return 'platform-mismatch';
  if (!line.enabled) return 'disabled';
  if (!line.pixelName.trim()) return 'missing-pixel';
  return undefined;
}

export function listAgencyLinesForAdCreation<T extends AgencyLineOption>(
  lines: readonly T[],
  context: AgencyLineAdCreationContext,
): T[] {
  return lines.filter(
    (line) => getAgencyLineAdCreationIssue(line, context) === undefined,
  );
}
