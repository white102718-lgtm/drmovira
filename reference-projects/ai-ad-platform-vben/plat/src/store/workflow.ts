import type { AiCapabilityCode, PlatformCode } from '#/api';

import { computed } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

export type WorkflowAssetKind =
  | 'audio'
  | 'data'
  | 'image'
  | 'report'
  | 'text'
  | 'video';

export interface WorkflowMaterialVersion {
  capability: AiCapabilityCode;
  createdAt: string;
  deliveryLineId?: string;
  id: string;
  kind: WorkflowAssetKind;
  materialId: string;
  name: string;
  parentVersionId?: string;
  projectId: string;
  ratio?: string;
  resultIndex: number;
  saveMode: 'new-material' | 'new-version';
  sourceTaskId: string;
  status: 'approved' | 'pending_review';
  version: number;
}

export interface WorkflowEvent {
  createdAt: string;
  description: string;
  id: string;
  materialVersionIds: string[];
  platform?: PlatformCode;
  projectId: string;
  status: 'completed' | 'queued';
  title: string;
  type:
    | 'ad_published'
    | 'material_approved'
    | 'material_saved'
    | 'second_creative_started';
}

interface SaveGeneratedMaterialPayload {
  capability: AiCapabilityCode;
  deliveryLineId?: string;
  kind: WorkflowAssetKind;
  name: string;
  parentVersionId?: string;
  projectId: string;
  ratio?: string;
  resultIndex: number;
  saveMode: WorkflowMaterialVersion['saveMode'];
  sourceTaskId: string;
}

interface RegisterPublishedAdPayload {
  campaignName: string;
  jobId: string;
  materialVersionIds: string[];
  platform: PlatformCode;
  projectId: string;
}

function nowLabel() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

function safeId(value: string) {
  return value
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, '-')
    .replaceAll(/(^-|-$)/g, '');
}

function resolveNextVersion(
  parent: undefined | WorkflowMaterialVersion,
  externalVersion: null | RegExpMatchArray | undefined,
  saveMode: WorkflowMaterialVersion['saveMode'],
) {
  if (parent) return parent.version + 1;
  if (saveMode === 'new-version' && externalVersion?.[1]) {
    return Number(externalVersion[1]) + 1;
  }
  return 1;
}

/**
 * Persists the small amount of cross-page state needed to demonstrate the
 * requirement → generation → material → publish loop without pretending that
 * it replaces the production Java, AdGen or AdPulse services.
 */
export const useWorkflowStore = defineStore('fusion-workflow', () => {
  const materialVersions = useStorage<WorkflowMaterialVersion[]>(
    'fusion:workflow-material-versions',
    [],
  );
  const events = useStorage<WorkflowEvent[]>('fusion:workflow-events', []);

  const savedMaterialCount = computed(() => materialVersions.value.length);
  const publishedAdCount = computed(
    () => events.value.filter((event) => event.type === 'ad_published').length,
  );

  function findGeneratedMaterial(sourceTaskId: string, resultIndex: number) {
    return materialVersions.value.find(
      (item) =>
        item.sourceTaskId === sourceTaskId && item.resultIndex === resultIndex,
    );
  }

  function saveGeneratedMaterial(payload: SaveGeneratedMaterialPayload) {
    const existing = findGeneratedMaterial(
      payload.sourceTaskId,
      payload.resultIndex,
    );
    if (existing) return existing;

    const taskPart = safeId(payload.sourceTaskId) || String(Date.now());
    const parent = payload.parentVersionId
      ? materialVersions.value.find(
          (item) => item.id === payload.parentVersionId,
        )
      : undefined;
    const externalParentVersion = payload.parentVersionId?.match(/v\s*(\d+)/i);
    const externalParentMaterial = payload.parentVersionId
      ? `material-${safeId(payload.parentVersionId.split('/')[0] || '')}`
      : '';
    const materialId =
      payload.saveMode === 'new-version' && (parent || externalParentMaterial)
        ? parent?.materialId || externalParentMaterial
        : `material-${taskPart}-${payload.resultIndex}`;
    const version = resolveNextVersion(
      parent,
      externalParentVersion,
      payload.saveMode,
    );
    const created: WorkflowMaterialVersion = {
      ...payload,
      createdAt: nowLabel(),
      id: `${materialId}-v${version}`,
      materialId,
      status: 'pending_review',
      version,
    };
    materialVersions.value = [created, ...materialVersions.value];
    events.value = [
      {
        createdAt: created.createdAt,
        description: `${created.name} 已入库，等待素材审核`,
        id: `event-material-${created.id}`,
        materialVersionIds: [created.id],
        projectId: created.projectId,
        status: 'completed',
        title: 'AI 结果已入素材库',
        type: 'material_saved',
      },
      ...events.value.filter(
        (item) => item.id !== `event-material-${created.id}`,
      ),
    ];
    return created;
  }

  function approveMaterialVersion(id: string) {
    const material = materialVersions.value.find((item) => item.id === id);
    if (!material) return;
    material.status = 'approved';
    const eventId = `event-approved-${material.id}`;
    events.value = [
      {
        createdAt: nowLabel(),
        description: `${material.name} 已审核通过，可用于广告发布`,
        id: eventId,
        materialVersionIds: [material.id],
        projectId: material.projectId,
        status: 'completed',
        title: '素材版本审核通过',
        type: 'material_approved',
      },
      ...events.value.filter((event) => event.id !== eventId),
    ];
    return material;
  }

  function registerSecondCreative(projectId: string, sourceVersion: string) {
    const id = `event-second-${safeId(projectId)}-${safeId(sourceVersion)}`;
    if (events.value.some((item) => item.id === id)) return;
    events.value = [
      {
        createdAt: nowLabel(),
        description: `已将胜出版本 ${sourceVersion} 带入 AI 创意工作台`,
        id,
        materialVersionIds: [sourceVersion],
        projectId,
        status: 'completed',
        title: '已发起二次创意',
        type: 'second_creative_started',
      },
      ...events.value,
    ];
  }

  function registerPublishedAd(payload: RegisterPublishedAdPayload) {
    const id = `event-publish-${payload.jobId}`;
    const existing = events.value.find((item) => item.id === id);
    if (existing) return existing;
    const created: WorkflowEvent = {
      createdAt: nowLabel(),
      description: `${payload.campaignName} 已进入 ${payload.platform} 异步发布队列`,
      id,
      materialVersionIds: [...payload.materialVersionIds],
      platform: payload.platform,
      projectId: payload.projectId,
      status: 'queued',
      title: '广告发布任务已创建',
      type: 'ad_published',
    };
    events.value = [created, ...events.value];
    return created;
  }

  function getProjectEvents(projectId: string) {
    return events.value.filter((event) => event.projectId === projectId);
  }

  function getProjectMaterials(projectId: string) {
    return materialVersions.value.filter(
      (item) => item.projectId === projectId,
    );
  }

  return {
    approveMaterialVersion,
    events,
    findGeneratedMaterial,
    getProjectEvents,
    getProjectMaterials,
    materialVersions,
    publishedAdCount,
    registerPublishedAd,
    registerSecondCreative,
    saveGeneratedMaterial,
    savedMaterialCount,
  };
});
