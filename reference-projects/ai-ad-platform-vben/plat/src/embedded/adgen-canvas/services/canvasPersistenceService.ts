import type { CanvasDraft } from '../features/canvas/types';

import { readCanvasModelApiResponse } from '../../../api/canvas-model-response';

import { authService } from './authService';
import { API_BASE_URL } from './runtimeConfig';

const CANVAS_API_URL = `${API_BASE_URL}/canvases`;

export interface PersistedCanvasRecord {
  draft?: CanvasDraft | null;
  id: string;
  name: string;
  revision: number;
  status: 'active' | 'archived';
  updatedAt?: string;
}

const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const token = authService.getToken();
  const response = await fetch(`${CANVAS_API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  return readCanvasModelApiResponse<T>(response);
};

export const loadPersistedCanvas = (
  canvasId: string,
): Promise<PersistedCanvasRecord> =>
  request<PersistedCanvasRecord>(`/${encodeURIComponent(canvasId)}`);

export const createPersistedCanvas = (
  canvasId: string,
  draft: CanvasDraft,
): Promise<PersistedCanvasRecord> =>
  request<PersistedCanvasRecord>('', {
    method: 'POST',
    body: JSON.stringify({
      canvasId,
      draft,
      name: draft.title,
    }),
  });

export const savePersistedCanvas = (
  canvasId: string,
  draft: CanvasDraft,
  revision: number,
  force = false,
): Promise<PersistedCanvasRecord> =>
  request<PersistedCanvasRecord>(`/${encodeURIComponent(canvasId)}`, {
    method: 'PUT',
    body: JSON.stringify({
      draft,
      name: draft.title,
      revision,
      ...(force ? { force: true } : {}),
    }),
  });
