import { assertAdPublishingPlatform } from '#/domain/ad-publishing/platform';
import type {
  AdDraftPayload,
  AiCapability,
  AiJobPayload,
  AsyncTask,
  CreativeTemplate,
  CustomerListParams,
  CustomerListResult,
  CustomerOption,
  CustomerProjectCurrencySummary,
  CustomerProjectOperationMetric,
  CustomerProjectOverview,
  CustomerProjectOverviewItem,
  CustomerSummary,
  CustomerUpsertPayload,
  GenerationHistoryParams,
  GenerationHistoryResult,
  GenerationRecord,
  OperationRecord,
  PlatformCapability,
  PreflightResult,
  ProjectListParams,
  ProjectListResult,
  ProjectOperatingOverview,
  ProjectOption,
  ProjectSummary,
  ProjectUpsertPayload,
  PublishJobResult,
  StorageBucket,
  StorageObject,
  WorkspaceOverview,
} from './types';

import { projectService } from '#/domain/project';
import {
  readVersionedCollection,
  writeVersionedCollection,
} from '#/mock/persistence/versioned-collection';

import { backendClient } from '../request';
import { getAdgenOperationsSnapshotApi } from '../adgen-operations';
import {
  demoAiCapabilities,
  demoBusinessOperations,
  demoCreativeTemplates,
  demoCustomers,
  demoGenerationHistory,
  demoPlatformCapabilities,
  demoProjectOperationMetrics,
  demoProjects,
  demoStorageBuckets,
  demoStorageObjects,
  demoTasks,
  getDemoWorkspaceOverview,
} from './fixtures';
import { isFusionDemoMode } from './mode';

export { isFusionDemoMode } from './mode';
export * from './types';

const demoMode = isFusionDemoMode();
const demoCustomersStorageKey = 'fusion:demo-customers';
const demoProjectsStorageKey = 'fusion:demo-projects';
let demoMasterDataHydrated = false;

function ensureDemoMasterData() {
  if (!demoMode || demoMasterDataHydrated) return;
  const storedCustomers = readVersionedCollection<CustomerSummary>({
    fallback: demoCustomers,
    storage: window.localStorage,
    storageKey: demoCustomersStorageKey,
  });
  const storedProjects = readVersionedCollection<ProjectSummary>({
    fallback: demoProjects,
    storage: window.localStorage,
    storageKey: demoProjectsStorageKey,
  });
  demoCustomers.splice(0, Infinity, ...storedCustomers);
  demoProjects.splice(0, Infinity, ...storedProjects);
  demoMasterDataHydrated = true;
}

function persistDemoCustomers() {
  writeVersionedCollection(
    window.localStorage,
    demoCustomersStorageKey,
    demoCustomers,
  );
}

function cloneCustomer(item: CustomerSummary): CustomerSummary {
  return { ...item };
}

function cloneProject(item: ProjectSummary): ProjectSummary {
  return {
    ...item,
    agentLines: [...(item.agentLines ?? [])],
    countryRegions: [...item.countryRegions],
    deliveryLines: item.deliveryLines.map((line) => ({ ...line })),
    kpiRequirements: item.kpiRequirements?.map((item) => ({ ...item })),
    mediaChannelIds: [...(item.mediaChannelIds ?? [])],
    platforms: [...item.platforms],
    wallet: item.wallet ? { ...item.wallet } : undefined,
  };
}

function getDemoTimestamp() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

const lockedDemoTaskStatuses = new Set<AsyncTask['status']>([
  'cancel_requested',
  'cancelled',
  'failed',
  'refund_pending',
  'refunded',
]);
const guardedDemoTasks = new WeakSet<object>();

/**
 * Demo pages update task progress directly so their local preview stays live.
 * Keep those mutations on the canonical fixture object, while preventing a
 * delayed page timer from turning an already cancelled task back into success.
 */
function protectDemoTask(task: AsyncTask): AsyncTask {
  if (guardedDemoTasks.has(task)) return task;

  const protectedTask = new Proxy(task, {
    set(target, property, value, receiver) {
      if (lockedDemoTaskStatuses.has(target.status)) {
        if (
          property === 'message' ||
          property === 'progress' ||
          property === 'resultCount'
        ) {
          return true;
        }
        if (
          property === 'status' &&
          !lockedDemoTaskStatuses.has(value as AsyncTask['status'])
        ) {
          return true;
        }
      }
      return Reflect.set(target, property, value, receiver);
    },
  });
  guardedDemoTasks.add(protectedTask);

  const index = demoTasks.indexOf(task);
  if (index !== -1) demoTasks[index] = protectedTask;
  return protectedTask;
}

/** Reconcile a page-created task with the shared demo task collection. */
export function upsertDemoAsyncTaskApi(task: AsyncTask): AsyncTask {
  if (!demoMode) return task;
  const existing = demoTasks.find((item) => item.id === task.id);
  if (existing) {
    const canonical = protectDemoTask(existing);
    if (canonical !== task) Object.assign(canonical, task);
    return canonical;
  }

  const canonical = protectDemoTask(task);
  demoTasks.unshift(canonical);
  return canonical;
}

/** Update the canonical demo snapshot by id so refreshes keep live progress. */
export function updateDemoAsyncTaskApi(
  taskId: string,
  patch: Partial<AsyncTask>,
): AsyncTask | undefined {
  if (!demoMode) return undefined;
  const existing = demoTasks.find((item) => item.id === taskId);
  if (!existing) return undefined;
  const canonical = protectDemoTask(existing);
  Object.assign(canonical, patch);
  return canonical;
}

function wait<T>(value: T, delay = 180): Promise<T> {
  return new Promise((resolve) =>
    window.setTimeout(() => resolve(value), delay),
  );
}

export async function getCustomerOptionsApi(): Promise<CustomerOption[]> {
  if (demoMode) {
    ensureDemoMasterData();
    return wait(
      demoCustomers.map(({ cooperationMode, id, name, status }) => ({
        cooperationMode,
        id,
        name,
        status,
      })),
    );
  }
  return backendClient.get('/fusion/customers/options');
}

export async function getCustomerListApi(
  params: CustomerListParams = {},
): Promise<CustomerListResult> {
  if (demoMode) {
    ensureDemoMasterData();
    const keyword = params.keyword?.trim().toLowerCase();
    const filtered = demoCustomers
      .map((item) => ({
        ...item,
        projectCount: demoProjects.filter(
          (project) => project.customerId === item.id,
        ).length,
      }))
      .filter((item) => {
        const matchesCustomer =
          !params.customerId || item.id === params.customerId;
        const matchesKeyword =
          !keyword ||
          `${item.name}${item.policy ?? ''}${item.remark ?? ''}`
            .toLowerCase()
            .includes(keyword);
        const matchesMode =
          !params.cooperationMode ||
          item.cooperationMode === params.cooperationMode;
        const matchesStatus =
          params.status === undefined || item.status === params.status;
        const matchesStart =
          !params.startDate ||
          !item.startDate ||
          item.startDate >= params.startDate;
        const matchesEnd =
          !params.endDate ||
          !item.startDate ||
          item.startDate <= params.endDate;
        return (
          matchesCustomer &&
          matchesKeyword &&
          matchesMode &&
          matchesStatus &&
          matchesStart &&
          matchesEnd
        );
      });
    const page = params.page ?? 1;
    const pageSize = params.pageSize ?? 20;
    return wait({
      items: filtered
        .slice((page - 1) * pageSize, page * pageSize)
        .map((item) => cloneCustomer(item)),
      total: filtered.length,
    });
  }
  return backendClient.get('/fusion/customers', { params });
}

function getDefaultProjectOperationMetric(
  project: ProjectSummary,
): CustomerProjectOperationMetric {
  return {
    actualSpend: 0,
    attributionCompleted: false,
    currency: project.currency,
    metricCutoff: project.updatedAt,
    settledAmount: 0,
    settlementStatus: 'unsettled',
  };
}

function buildCustomerProjectOverview(
  customer: CustomerSummary,
  customerProjects: ProjectSummary[],
): CustomerProjectOverview {
  const projects: CustomerProjectOverviewItem[] = customerProjects.map(
    (project) => {
      const metric =
        demoProjectOperationMetrics[project.id] ??
        getDefaultProjectOperationMetric(project);
      const normalizedMetric: CustomerProjectOperationMetric = {
        ...metric,
        currency: metric.currency || project.currency,
        realizedRoi: metric.attributionCompleted
          ? metric.realizedRoi
          : undefined,
      };
      return {
        ...cloneProject(project),
        ...normalizedMetric,
        projectId: project.id,
        projectName: project.name,
      };
    },
  );

  const currencyTotals = new Map<string, CustomerProjectCurrencySummary>();
  projects.forEach((project) => {
    const current = currencyTotals.get(project.currency) ?? {
      amount: 0,
      currency: project.currency,
    };
    current.amount += project.actualSpend;
    currencyTotals.set(project.currency, current);
  });

  const attributedProjects = projects.filter(
    (project) =>
      project.attributionCompleted &&
      project.actualSpend > 0 &&
      project.realizedRoi !== undefined,
  );
  const attributedSpend = attributedProjects.reduce(
    (total, project) => total + project.actualSpend,
    0,
  );
  const attributedCurrencies = new Set(
    attributedProjects.map((project) => project.currency),
  );
  let realizedRoi: number | undefined;
  if (attributedCurrencies.size === 1 && attributedSpend > 0) {
    realizedRoi =
      attributedProjects.reduce(
        (total, project) =>
          total + project.actualSpend * (project.realizedRoi ?? 0),
        0,
      ) / attributedSpend;
  }

  const metricCutoff =
    projects
      .map((project) => project.metricCutoff)
      .sort((left, right) => right.localeCompare(left))[0] ??
    customer.updatedAt;

  return {
    customerId: customer.id,
    customerName: customer.name,
    metricCutoff,
    projects,
    summary: {
      activeCount: projects.filter((project) => project.status === 'active')
        .length,
      pendingSettlementCount: projects.filter(
        (project) => project.settlementStatus !== 'settled',
      ).length,
      projectCount: projects.length,
      realizedRoi,
      realizedProjectCount: attributedProjects.length,
      settledCount: projects.filter(
        (project) => project.settlementStatus === 'settled',
      ).length,
      spendByCurrency: [...currencyTotals.values()],
    },
  };
}

export async function getCustomerProjectOverviewApi(
  customerId: string,
): Promise<CustomerProjectOverview> {
  if (demoMode) {
    ensureDemoMasterData();
    const customer = demoCustomers.find((item) => item.id === customerId);
    if (!customer) throw new Error('客户不存在或已被删除');
    return wait(
      buildCustomerProjectOverview(
        customer,
        demoProjects.filter((project) => project.customerId === customerId),
      ),
    );
  }
  return backendClient.get(
    `/fusion/customers/${encodeURIComponent(customerId)}/project-overview`,
  );
}

export async function getProjectOperatingOverviewApi(
  projectId: string,
): Promise<ProjectOperatingOverview> {
  // Compatibility facade: remove only after all #/api consumers migrate to
  // projectService and the HTTP adapter contract is accepted by the backend.
  return projectService.getOperatingOverview(projectId);
}

export async function saveCustomerApi(
  payload: CustomerUpsertPayload,
): Promise<CustomerSummary> {
  if (demoMode) {
    ensureDemoMasterData();
    const normalizedName = payload.name.trim();
    const duplicate = demoCustomers.some(
      (item) =>
        item.id !== payload.id &&
        item.name.trim().toLowerCase() === normalizedName.toLowerCase(),
    );
    if (duplicate) throw new Error('客户名称已存在，请使用其他名称');

    const now = getDemoTimestamp();
    const current = demoCustomers.find((item) => item.id === payload.id);
    if (current) {
      Object.assign(current, payload, { name: normalizedName, updatedAt: now });
      persistDemoCustomers();
      return wait(cloneCustomer(current));
    }

    const created: CustomerSummary = {
      ...payload,
      createdAt: now,
      id: `customer-${Date.now()}`,
      name: normalizedName,
      projectCount: 0,
      updatedAt: now,
    };
    demoCustomers.unshift(created);
    persistDemoCustomers();
    return wait(cloneCustomer(created));
  }
  return payload.id
    ? backendClient.put(`/fusion/customers/${payload.id}`, payload)
    : backendClient.post('/fusion/customers', payload);
}

export async function getProjectOptionsApi(): Promise<ProjectOption[]> {
  // Compatibility facade for ProjectContextStore and legacy selectors.
  return projectService.listOptions();
}

export async function getProjectListApi(
  params: ProjectListParams = {},
): Promise<ProjectListResult> {
  // Compatibility facade for Requirement and other unmigrated pages.
  return projectService.list(params);
}

export async function saveProjectApi(
  payload: ProjectUpsertPayload,
): Promise<ProjectSummary> {
  // Compatibility facade for the previous HTTP/localStorage API surface.
  return projectService.save(payload);
}

export async function getWorkspaceOverviewApi(
  projectId: string,
): Promise<WorkspaceOverview> {
  if (demoMode) return wait(getDemoWorkspaceOverview(projectId));
  return backendClient.get('/fusion/workspace/overview', {
    params: { projectId },
  });
}

export async function getAiCapabilitiesApi(): Promise<AiCapability[]> {
  if (demoMode) return wait(demoAiCapabilities);
  return backendClient.get('/fusion/ai-capabilities');
}

export async function getPlatformCapabilitiesApi(): Promise<
  PlatformCapability[]
> {
  if (demoMode) return wait(demoPlatformCapabilities);
  return backendClient.get('/fusion/platform-capabilities');
}

export async function getAsyncTasksApi(
  projectId?: string,
): Promise<AsyncTask[]> {
  if (demoMode) {
    const canonicalTasks = demoTasks.map((item) => protectDemoTask(item));
    return wait(
      projectId
        ? canonicalTasks.filter((item) => item.projectId === projectId)
        : [...canonicalTasks],
    );
  }
  return backendClient.get('/fusion/tasks', { params: { projectId } });
}

export async function createAiJobApi(
  payload: AiJobPayload,
): Promise<AsyncTask> {
  if (demoMode) {
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    const created: AsyncTask = {
      capability: payload.capability,
      createdAt: now,
      id: `ai-job-${Date.now()}`,
      message: '任务已进入生成队列',
      progress: 0,
      projectId: payload.projectId,
      refundable: true,
      status: 'queued',
      title: `${payload.capability} · ${payload.expectedCount} 个产出`,
      updatedAt: now,
    };
    const canonical = protectDemoTask(created);
    demoTasks.unshift(canonical);
    return wait(canonical);
  }
  return backendClient.post('/fusion/ai-jobs', payload);
}

/**
 * Submit a cancellation request for an asynchronous task.
 *
 * The API deliberately returns the canonical task snapshot so all clients
 * (the task centre, the global drawer and the originating capability page)
 * can render the same billing state after the execution service accepts the
 * request. In demo mode we still mutate the fixture to keep the interaction
 * usable without a backend.
 */
export async function cancelAsyncTaskApi(taskId: string): Promise<AsyncTask> {
  if (demoMode) {
    const existing = demoTasks.find((item) => item.id === taskId);
    if (!existing) throw new Error('任务不存在或已刷新');
    const task = protectDemoTask(existing);
    if (!['queued', 'running'].includes(task.status)) return wait(task);
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    Object.assign(task, {
      message: '已提交取消请求，等待执行端确认并结算未执行项',
      status: 'cancel_requested' as const,
      updatedAt: now,
    });
    return wait(task);
  }
  return backendClient.post(`/fusion/tasks/${taskId}/cancel`);
}

/** Create a new queued task from a failed/cancelled task. */
export async function retryAsyncTaskApi(taskId: string): Promise<AsyncTask> {
  if (demoMode) {
    const existing = demoTasks.find((item) => item.id === taskId);
    if (!existing) throw new Error('任务不存在或已刷新');
    const source = protectDemoTask(existing);
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    const retry: AsyncTask = {
      ...source,
      createdAt: now,
      id: `${source.id}-retry-${Date.now()}`,
      message: `从任务 ${source.id} 重试`,
      progress: 0,
      status: 'queued',
      updatedAt: now,
    };
    const canonical = protectDemoTask(retry);
    demoTasks.unshift(canonical);
    return wait(canonical);
  }
  return backendClient.post(`/fusion/tasks/${taskId}/retry`);
}

export async function preflightAdDraftApi(
  payload: AdDraftPayload,
): Promise<PreflightResult> {
  assertAdPublishingPlatform(payload.platform);
  if (demoMode) {
    const checks = [
      {
        code: 'project-context',
        message: '项目与投放线已绑定',
        passed: Boolean(payload.projectId),
        severity: 'info' as const,
      },
      {
        code: 'platform-resource',
        message: '平台账户、转化目标和身份已选择',
        passed: Boolean(
          payload.adAccountId &&
            payload.conversionTargetId &&
            (payload.platform === 'google' || payload.creativeIdentityId),
        ),
        severity: 'error' as const,
      },
      {
        code: 'material-ready',
        message: '素材已完成审核并可用于投放',
        passed: payload.materialIds.length > 0,
        severity: 'error' as const,
      },
      {
        code: 'destination-url',
        message: '落地页地址格式有效',
        passed: /^https?:\/\//.test(payload.destinationUrl),
        severity: 'warning' as const,
      },
    ];
    return wait({ checks, passed: checks.every((item) => item.passed) });
  }
  return backendClient.post('/fusion/ad-publish-jobs/preflight', payload);
}

export async function publishAdDraftApi(
  payload: AdDraftPayload,
  preflightToken?: string,
): Promise<PublishJobResult> {
  assertAdPublishingPlatform(payload.platform);
  if (demoMode) {
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    const task = protectDemoTask({
      createdAt: now,
      id: `publish-job-${Date.now()}`,
      message: '发布任务已进入队列',
      platform: payload.platform,
      progress: 0,
      projectId: payload.projectId,
      refundable: false,
      status: 'queued',
      title: `${payload.platform} · ${payload.campaignName}`,
      updatedAt: now,
    });
    demoTasks.unshift(task);
    return wait({ jobId: task.id, status: task.status });
  }
  const { adAccountInventoryId, ...legacyPayload } = payload;
  if (!preflightToken) {
    return backendClient.post('/fusion/ad-publish-jobs', legacyPayload);
  }
  return backendClient.post('/fusion/ad-publish-jobs', {
    ...legacyPayload,
    ...(adAccountInventoryId ? { adAccountInventoryId } : {}),
    preflightToken,
  });
}

export async function getGenerationHistoryApi(
  params: GenerationHistoryParams = {},
): Promise<GenerationHistoryResult> {
  if (demoMode) {
    const keyword = params.keyword?.trim().toLowerCase();
    const filtered = demoGenerationHistory.filter((item) => {
      const matchesKeyword =
        !keyword ||
        `${item.title}${item.prompt}${item.sessionId}`
          .toLowerCase()
          .includes(keyword);
      return (
        matchesKeyword &&
        (!params.capability || item.capability === params.capability) &&
        (!params.status || item.status === params.status)
      );
    });
    const page = params.page ?? 1;
    const pageSize = params.pageSize ?? 10;
    return wait({
      items: filtered.slice((page - 1) * pageSize, page * pageSize),
      total: filtered.length,
    });
  }
  return backendClient.get('/fusion/generation-history', { params });
}

/** Persist a completed generation run so history and downstream actions share
 * the same record. Demo mode mutates the in-memory fixture; production uses the
 * integration endpoint owned by the AdGen adapter. */
export async function saveGenerationRecordApi(
  record: GenerationRecord,
): Promise<GenerationRecord> {
  if (demoMode) {
    const sourceTask = demoTasks.find(
      (item) =>
        item.id === record.sessionId || record.id === `history-${item.id}`,
    );
    if (sourceTask && lockedDemoTaskStatuses.has(sourceTask.status)) {
      throw new Error('任务已取消或终止，不保存生成结果');
    }
    const index = demoGenerationHistory.findIndex(
      (item) => item.id === record.id,
    );
    if (index === -1) {
      demoGenerationHistory.unshift({ ...record });
    } else {
      demoGenerationHistory[index] = { ...record };
    }
    return wait({ ...record });
  }
  return backendClient.post('/fusion/generation-history', record);
}

export async function deleteGenerationRecordApi(id: string): Promise<void> {
  if (demoMode) {
    const index = demoGenerationHistory.findIndex((item) => item.id === id);
    if (index !== -1) demoGenerationHistory.splice(index, 1);
    await wait(undefined);
    return;
  }
  await backendClient.delete(`/fusion/generation-history/${id}`);
}

export async function getCreativeTemplatesApi(): Promise<CreativeTemplate[]> {
  if (demoMode) return wait([...demoCreativeTemplates]);
  return backendClient.get('/fusion/creative-templates');
}

export async function saveCreativeTemplateApi(
  payload: Partial<CreativeTemplate> & Pick<CreativeTemplate, 'name'>,
): Promise<CreativeTemplate> {
  if (demoMode) {
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    const existing = payload.id
      ? demoCreativeTemplates.find((item) => item.id === payload.id)
      : undefined;
    if (existing) {
      Object.assign(existing, payload, { updatedAt: now });
      return wait({ ...existing });
    }
    const created: CreativeTemplate = {
      category: payload.category ?? 'general',
      description: payload.description ?? '',
      id: `template-${Date.now()}`,
      name: payload.name,
      prompt: payload.prompt ?? '',
      status: payload.status ?? 'draft',
      structure: payload.structure ?? '',
      tags: payload.tags ?? [],
      updatedAt: now,
      usageCount: 0,
    };
    demoCreativeTemplates.unshift(created);
    return wait({ ...created });
  }
  return payload.id
    ? backendClient.put(`/fusion/creative-templates/${payload.id}`, payload)
    : backendClient.post('/fusion/creative-templates', payload);
}

export async function deleteCreativeTemplateApi(id: string): Promise<void> {
  if (demoMode) {
    const index = demoCreativeTemplates.findIndex((item) => item.id === id);
    if (index !== -1) demoCreativeTemplates.splice(index, 1);
    await wait(undefined);
    return;
  }
  await backendClient.delete(`/fusion/creative-templates/${id}`);
}

export async function getStorageBucketsApi(): Promise<StorageBucket[]> {
  if (demoMode) return wait([...demoStorageBuckets]);
  return backendClient.get('/fusion/storage/buckets');
}

export async function getStorageObjectsApi(
  bucketId: string,
): Promise<StorageObject[]> {
  if (demoMode)
    return wait(
      demoStorageObjects.filter((item) => item.bucketId === bucketId),
    );
  return backendClient.get(`/fusion/storage/buckets/${bucketId}/objects`);
}

export async function createStorageFolderApi(
  bucketId: string,
  name: string,
): Promise<StorageObject> {
  if (demoMode) {
    const folder: StorageObject = {
      bucketId,
      folder: '/',
      id: `folder-${Date.now()}`,
      kind: 'folder',
      name,
      size: '-',
      updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    };
    demoStorageObjects.unshift(folder);
    return wait({ ...folder });
  }
  return backendClient.post(`/fusion/storage/buckets/${bucketId}/folders`, {
    name,
  });
}

export async function uploadStorageObjectApi(
  bucketId: string,
  fileName: string,
): Promise<StorageObject> {
  if (demoMode) {
    const extension = fileName.split('.').pop()?.toLowerCase();
    let kind: StorageObject['kind'] = 'other';
    if (['jpeg', 'jpg', 'png', 'webp'].includes(extension ?? '')) {
      kind = 'image';
    } else if (['mov', 'mp4', 'webm'].includes(extension ?? '')) {
      kind = 'video';
    } else if (['aac', 'mp3', 'wav'].includes(extension ?? '')) {
      kind = 'audio';
    }
    const object: StorageObject = {
      bucketId,
      folder: '/',
      id: `object-${Date.now()}`,
      kind,
      name: fileName,
      size: '待后端计算',
      updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    };
    demoStorageObjects.unshift(object);
    return wait({ ...object });
  }
  return backendClient.post(`/fusion/storage/buckets/${bucketId}/objects`, {
    fileName,
  });
}

export async function deleteStorageObjectApi(id: string): Promise<void> {
  if (demoMode) {
    const index = demoStorageObjects.findIndex((item) => item.id === id);
    if (index !== -1) demoStorageObjects.splice(index, 1);
    await wait(undefined);
    return;
  }
  await backendClient.delete(`/fusion/storage/objects/${id}`);
}

export async function getOperationsApi(
  domain: 'adgen' | 'business',
): Promise<OperationRecord[]> {
  if (domain === 'adgen') {
    return (await getAdgenOperationsSnapshotApi()).records;
  }
  if (demoMode) return wait([...demoBusinessOperations]);
  return backendClient.get(`/fusion/operations/${domain}`);
}
