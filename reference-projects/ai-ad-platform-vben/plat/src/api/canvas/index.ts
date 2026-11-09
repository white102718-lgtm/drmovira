import type {
  CanvasDetail,
  CanvasListParams,
  CanvasListResult,
  CanvasSummary,
  CreateCanvasPayload,
  UpdateCanvasPayload,
} from './types';

import { useAccessStore } from '@vben/stores';

import { readCanvasModelApiResponse } from '../canvas-model-response';

export * from './types';

const demoMode = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';
const demoCanvasStorageKey = 'fusion:demo-canvases';
const canvasApiBase = '/adgen-api/api/canvases';

let demoCanvases: CanvasSummary[] | undefined;

function cloneCanvas(canvas: CanvasSummary): CanvasSummary {
  return { ...canvas };
}

function getDemoCanvases(): CanvasSummary[] {
  if (demoCanvases) return demoCanvases;

  try {
    const value = window.localStorage.getItem(demoCanvasStorageKey);
    const parsed = value ? JSON.parse(value) : [];
    demoCanvases = Array.isArray(parsed) ? parsed : [];
  } catch {
    demoCanvases = [];
  }

  return demoCanvases;
}

function persistDemoCanvases() {
  window.localStorage.setItem(
    demoCanvasStorageKey,
    JSON.stringify(getDemoCanvases()),
  );
}

function wait<T>(value: T, delay = 180): Promise<T> {
  return new Promise((resolve) =>
    window.setTimeout(() => resolve(value), delay),
  );
}

async function requestCanvasApi<T>(
  path = '',
  init: RequestInit = {},
): Promise<T> {
  const token = useAccessStore().accessToken;
  const response = await fetch(`${canvasApiBase}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  return readCanvasModelApiResponse<T>(response);
}

/** 查询画布后端判定的跨用户列表权限，与列表鉴权保持一致。 */
export function getCanvasCapabilitiesApi(): Promise<{ canViewAll: boolean }> {
  if (demoMode) return wait({ canViewAll: false });
  return requestCanvasApi('/capabilities');
}

export async function getCanvasListApi(
  params: CanvasListParams = {},
): Promise<CanvasListResult> {
  if (demoMode) {
    const items = getDemoCanvases()
      .filter(
        (canvas) =>
          (params.includeArchived || canvas.status !== 'archived') &&
          (!params.projectId || canvas.projectId === params.projectId) &&
          (!params.requirementId ||
            canvas.requirementId === params.requirementId) &&
          (!params.taskId || canvas.taskId === params.taskId),
      )
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .map((canvas) => cloneCanvas(canvas));

    return wait({ items, total: items.length });
  }

  const search = new URLSearchParams();
  if (params.scope) search.set('scope', params.scope);
  if (params.includeArchived) search.set('includeArchived', 'true');
  if (params.projectId) search.set('projectId', params.projectId);
  if (params.requirementId) search.set('requirementId', params.requirementId);
  if (params.taskId) search.set('taskId', params.taskId);
  return requestCanvasApi<CanvasListResult>(`?${search.toString()}`);
}

export async function createCanvasApi(
  payload: CreateCanvasPayload,
): Promise<CanvasSummary> {
  if (demoMode) {
    const canvases = getDemoCanvases();
    const existing = payload.requirementId
      ? canvases.find(
          (canvas) =>
            canvas.requirementId === payload.requirementId &&
            canvas.status === 'active',
        )
      : undefined;
    if (existing) return wait(cloneCanvas(existing));

    const now = new Date().toISOString();
    const canvas: CanvasSummary = {
      createdAt: now,
      id: `canvas-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name:
        payload.name?.trim() ||
        (payload.taskId ? `需求 ${payload.taskId} · AI画布` : '未命名画布'),
      projectId: payload.projectId,
      requirementId: payload.requirementId,
      status: 'active',
      taskId: payload.taskId,
      updatedAt: now,
    };

    canvases.unshift(canvas);
    persistDemoCanvases();
    return wait(cloneCanvas(canvas));
  }

  return requestCanvasApi<CanvasSummary>('', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** 管理员只读查看草稿；不会扩大原写入接口权限。 */
export function getCanvasViewApi(canvasId: string): Promise<CanvasDetail> {
  return requestCanvasApi(`/${encodeURIComponent(canvasId)}/view`);
}

export async function getCanvasApi(canvasId: string): Promise<CanvasDetail> {
  return requestCanvasApi<CanvasDetail>(`/${encodeURIComponent(canvasId)}`);
}

export async function updateCanvasApi(
  canvasId: string,
  payload: UpdateCanvasPayload,
): Promise<CanvasDetail> {
  if (demoMode) {
    const canvas = getDemoCanvases().find((item) => item.id === canvasId);
    if (!canvas) throw new Error('画布不存在或已被删除');

    const now = new Date().toISOString();
    if (payload.name !== undefined) {
      canvas.name = payload.name.trim() || '未命名画布';
    }
    if (payload.projectId !== undefined) {
      canvas.projectId = payload.projectId || undefined;
    }
    if (payload.status !== undefined) {
      canvas.status = payload.status;
    }
    canvas.revision = (canvas.revision || 1) + 1;
    canvas.updatedAt = now;
    persistDemoCanvases();
    return wait({ ...cloneCanvas(canvas), draft: payload.draft });
  }

  return requestCanvasApi<CanvasDetail>(`/${encodeURIComponent(canvasId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function archiveCanvasApi(
  canvasId: string,
): Promise<CanvasSummary> {
  if (demoMode) {
    const canvas = getDemoCanvases().find((item) => item.id === canvasId);
    if (!canvas) throw new Error('画布不存在或已被删除');

    const now = new Date().toISOString();
    Object.assign(canvas, {
      archivedAt: now,
      status: 'archived' as const,
      updatedAt: now,
    });
    persistDemoCanvases();
    return wait(cloneCanvas(canvas));
  }

  return requestCanvasApi<CanvasSummary>(
    `/${encodeURIComponent(canvasId)}/archive`,
    {
      method: 'POST',
    },
  );
}

/** 只读历史由后端校验画布归属或管理员权限。 */
export function getCanvasHistoryApi<T>(
  canvasId: string,
  params: URLSearchParams,
): Promise<T> {
  return requestCanvasApi(`/${encodeURIComponent(canvasId)}/history?${params}`);
}
