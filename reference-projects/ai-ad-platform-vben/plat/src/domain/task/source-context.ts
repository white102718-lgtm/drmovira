import type {
  CreateMaterialTaskContext,
  MaterialTaskSourceQuery,
} from './types';

function readQueryText(value: unknown) {
  const raw = Array.isArray(value) ? value[0] : value;
  return typeof raw === 'string' ? raw.trim() : '';
}

/**
 * Parses only stable IDs from the compatible route query. A display name is
 * never promoted to an ID, so a tampered or old bookmark fails closed.
 */
export function parseMaterialTaskSourceQuery(
  query: Record<string, unknown>,
): MaterialTaskSourceQuery {
  const projectId = readQueryText(query.projectId);
  const sourceTaskId = readQueryText(query.sourceTaskId);

  // `projectId` alone has been supported by old requirement bookmarks. It is
  // a preselection hint, not proof of a source task, and must remain manual.
  if (!sourceTaskId) return { kind: 'manual' };
  if (!projectId) {
    return {
      kind: 'invalid',
      reason: '来源素材任务必须同时携带项目 ID 与投放任务 ID',
    };
  }
  return { kind: 'linked', projectId, sourceTaskId };
}

export function createMaterialTaskContext(
  source: Extract<MaterialTaskSourceQuery, { kind: 'linked' }>,
  requester: { requesterId: string; requesterName: string },
): CreateMaterialTaskContext {
  const requesterId = requester.requesterId.trim();
  const requesterName = requester.requesterName.trim();
  if (!requesterId || !requesterName) {
    throw new Error('当前请求人缺少稳定用户 ID，无法建立来源任务关系');
  }
  return {
    projectId: source.projectId,
    requesterId,
    requesterName,
    sourceTaskId: source.sourceTaskId,
  };
}
