export type CanvasStatus = 'active' | 'archived';

export interface CanvasSummary {
  ownerId?: string;
  archivedAt?: string;
  createdAt: string;
  id: string;
  name: string;
  nodeCount?: number;
  outputCount?: number;
  projectId?: string;
  requirementId?: string;
  revision?: number;
  status: CanvasStatus;
  taskId?: string;
  updatedAt: string;
}

export interface CanvasDraftPayload {
  edges: unknown[];
  nodes: unknown[];
  title: string;
  updatedAt: string;
  version: 1;
  viewport: Record<string, unknown>;
}

export interface CanvasDetail extends CanvasSummary {
  draft?: CanvasDraftPayload | null;
}

export interface CanvasListParams {
  scope?: 'all';
  includeArchived?: boolean;
  projectId?: string;
  requirementId?: string;
  taskId?: string;
}

export interface CanvasListResult {
  items: CanvasSummary[];
  total: number;
}

export interface CreateCanvasPayload {
  canvasId?: string;
  draft?: CanvasDraftPayload;
  name?: string;
  projectId?: string;
  requirementId?: string;
  taskId?: string;
}

export interface UpdateCanvasPayload {
  draft?: CanvasDraftPayload;
  name?: string;
  projectId?: null | string;
  revision?: number;
  status?: CanvasStatus;
}
