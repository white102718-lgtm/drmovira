import type { DeliveryTaskItem } from '#/domain/task/delivery-items';
import type {
  DeliveryCompletionState,
  DeliverySubmissionInput,
  DeliverySubmissionRecord,
} from '#/domain/task-delivery';
import type { TaskAssignment, TaskSourceRef } from '#/domain/task/types';

import { computed } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

import { deliveryWorkflowService } from '#/domain/task-delivery';

export type TaskCenterKind = 'am' | 'material' | 'media';
export type TaskCenterStatus =
  | 'paused'
  | 'cancelled'
  | 'assigned_pending_confirmation'
  | 'draft'
  | 'doing'
  | 'done'
  | 'pending'
  | 'pending_acceptance'
  | 'pending_assignment'
  | 'partially_completed'
  | 'rejected'
  | 'risk'
  | 'withdrawn';
/** 新任务为组织架构部门 ID，历史任务可能保留旧团队编码。 */
export type DeliveryTeamCode = string;
export type AmDeliveryStatus = 'active' | 'failed' | 'partial' | 'paused';
export type AmCompletionEntryMode = 'delivery-center' | 'manual';
export type TaskAcceptanceDecision = 'accepted' | 'rejected';
export type TaskCompletionRecordStatus =
  | 'accepted'
  | 'rejected'
  | 'submitted'
  | 'superseded';

export interface TaskAttachmentMeta {
  /** Media content type returned by the MaterialOrder upload service. */
  contentType?: string;
  duration?: number;
  fileMd5?: string;
  hash?: string;
  height?: number;
  id: string;
  img?: string;
  name: string;
  objectKey?: string;
  /** Optional immutable backend file identifier; objectKey remains required. */
  serverFileId?: string;
  sha3_256?: string;
  size: number;
  source?: string;
  type: string;
  uploadedAt?: string;
  url?: string;
  width?: number;
}

interface TaskCompletionInputBase {
  files: TaskAttachmentMeta[];
  note: string;
  submittedBy: string;
}

export interface MaterialTaskCompletionInput extends TaskCompletionInputBase {
  creativePlanner?: string;
  designer?: string;
  /** Returned only when the legacy deliver endpoint exposes an immutable ID. */
  formalDeliveryId?: string;
  /** Returned only when the legacy deliver endpoint exposes a version number. */
  formalVersionNo?: number;
  kind: 'material';
  /** 实际交付素材数量。 */
  deliveredQuantity?: number;
  /** 素材交付入库状态。 */
  libraryStatus?: string;
  /** Stable MaterialOrder source link; legacy material records may omit it. */
  sourceOrderId: string;
  sourceRequirementId?: string;
}

export interface AmTaskCompletionInput extends TaskCompletionInputBase {
  accountId: string;
  accountName?: string;
  actualBudget: number;
  actualSpend?: number;
  actualStartAt: string;
  adCount: number;
  adsetCount: number;
  agencyLineId?: string;
  agencyLineName?: string;
  campaignCount: number;
  campaignIds: string[];
  currency: string;
  dailyReportSpend?: number;
  dataCutoffAt?: string;
  deliveryStatus: AmDeliveryStatus;
  entryMode?: AmCompletionEntryMode;
  exceptionNote: string;
  kind: 'am';
  materialVersion?: string;
  platform: string;
  sourceAdIds?: string[];
  sourceAdsetIds?: string[];
  sourceCampaignName?: string;
  sourceSyncedAt?: string;
}

export interface MediaTaskCompletionInput extends TaskCompletionInputBase {
  kind: 'media';
}

export type TaskCompletionInput =
  | AmTaskCompletionInput
  | MaterialTaskCompletionInput
  | MediaTaskCompletionInput;

interface TaskCompletionRecordMeta {
  /** 投放任务所属的团队—投手执行项；素材任务为空。 */
  allocationId?: string;
  status: TaskCompletionRecordStatus;
  submissionId: string;
  submittedAt: string;
  versionNo: number;
}

export type AmTaskCompletionRecord = AmTaskCompletionInput &
  TaskCompletionRecordMeta;
export type MaterialTaskCompletionRecord = MaterialTaskCompletionInput &
  TaskCompletionRecordMeta;
export type MediaTaskCompletionRecord = MediaTaskCompletionInput &
  TaskCompletionRecordMeta;
export type TaskCompletionRecord =
  | AmTaskCompletionRecord
  | MaterialTaskCompletionRecord
  | MediaTaskCompletionRecord;

export interface TaskAcceptanceRecord {
  decision: TaskAcceptanceDecision;
  reason: string;
  reviewedAt: string;
  /** Additive stable reviewer ID. `reviewer` remains the legacy display name. */
  reviewer: string;
  reviewerId?: string;
  submissionId: string;
  versionNo: number;
}

export interface TaskRejectionRecord {
  reason: string;
  rejectedAt: string;
  rejectedBy: string;
  rejectedById?: string;
}

export interface TaskCompletionState {
  acceptanceHistory: TaskAcceptanceRecord[];
  current?: TaskCompletionRecord;
  history: TaskCompletionRecord[];
}

export interface DeliveryTeamAllocation {
  /** Stable executor ID. `owner` remains the legacy display value. */
  assigneeId?: string;
  /** Stable executor display name, retained when the account is disabled. */
  assigneeName?: string;
  h5Count: number;
  id: string;
  owner: string;
  pwaCount: number;
  /** 当前投手执行项状态，仅正式投放任务详情返回。 */
  status?: 'ASSIGNED' | 'COMPLETED' | 'SUBMITTED';
  submittedAt?: string;
  completedAt?: string;
  team: DeliveryTeamCode;
  /** 部门展示名称，兼容草稿和历史任务回显。 */
  teamName?: string;
}

export interface DeliveryTaskFormData {
  items?: DeliveryTaskItem[];
  allocations: DeliveryTeamAllocation[];
  amOwner: string;
  amUsers?: Array<{ userId: string; userName: string }>;
  attachments: TaskAttachmentMeta[];
  dueAt: string;
  /** Stable project delivery leader id. Old drafts may not have this field. */
  ownerId?: string;
  /** Stable project delivery leader display name; amOwner remains legacy. */
  ownerName?: string;
  platforms: string[];
  productUrl: string;
  projectId: string;
  projectName: string;
  region: string;
  startAt: string;
  target: string;
  title: string;
}

export interface TaskCenterTask {
  actionLabel: string;
  assignedAt?: string;
  assignerId?: string;
  assignerName?: string;
  /** Additive stable participant list; legacy owner/allocation names remain. */
  assignments?: TaskAssignment[];
  audiences: string[];
  completedAt?: string;
  completion?: TaskCompletionState;
  /** 稳定的任务创建者用户ID，用于判断分配和验收权限。 */
  creatorId?: string;
  createdAt: string;
  createdBy: string;
  delivery?: DeliveryTaskFormData;
  /** 当前用户是否为该投放任务中仍待交付的投手。 */
  deliveryOperator?: boolean;
  /** 投放任务列表中的 AM 姓名。 */
  amNames?: string;
  draftId?: string;
  dueAt: string;
  followed?: boolean;
  id: string;
  kind: TaskCenterKind;
  /**
   * 素材任务迁移期的旧工单稳定 ID。存在时，状态与交付动作由
   * backend_new 的 material-orders 状态机负责，不能调用通用 /tasks 接口。
   */
  legacyMaterialOrderId?: string;
  /** 旧素材工单原始状态，用于区分待提交、待验收与已入库口径。 */
  legacyMaterialOrderStatus?: string;
  owner: string;
  ownerId?: string;
  ownerName?: string;
  progress: number;
  project: string;
  projectId?: string;
  rejection?: TaskRejectionRecord;
  route: string;
  /** Additive source relation; legacy `sourceId` remains unchanged. */
  source?: TaskSourceRef;
  sourceId?: string;
  status: TaskCenterStatus;
  submissionCount?: number;
  summary: string;
  title: string;
  updatedAt: string;
  withdrawnAt?: string;
}

export interface TaskCenterDraft {
  createdAt: string;
  createdBy: string;
  form: DeliveryTaskFormData;
  id: string;
  kind: 'am';
  updatedAt: string;
}

export interface CreateTaskCenterTaskInput {
  actionLabel: string;
  assignments?: TaskAssignment[];
  audiences?: string[];
  createdBy?: string;
  delivery?: DeliveryTaskFormData;
  dueAt: string;
  followed?: boolean;
  id?: string;
  kind: TaskCenterKind;
  owner: string;
  ownerId?: string;
  ownerName?: string;
  progress?: number;
  project: string;
  projectId?: string;
  route: string;
  source?: TaskSourceRef;
  sourceId?: string;
  status?: TaskCenterStatus;
  summary: string;
  title: string;
}

const TASK_STORAGE_KEY = 'adpulse:task-center:tasks';
const DRAFT_STORAGE_KEY = 'adpulse:task-center:delivery-drafts';
export const PENDING_ACCEPTANCE_EXAMPLE_TASK_ID = 'TASK-AM-ACCEPT-20260811';
export const PENDING_ASSIGNMENT_MATERIAL_EXAMPLE_TASK_ID =
  'TASK-MAT-PENDING-ASSIGN-20260813';
export const PENDING_ASSIGNMENT_AM_EXAMPLE_TASK_ID =
  'TASK-AM-PENDING-ASSIGN-20260813';
export const ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID =
  'TASK-MAT-ASSIGNED-CONFIRM-20260813';

function nowText() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

function createTaskId(kind: TaskCenterKind) {
  const prefixes: Record<TaskCenterKind, string> = {
    am: 'AM',
    material: 'MAT',
    media: 'MED',
  };
  const prefix = prefixes[kind];
  const timestamp = String(Date.now()).slice(-8);
  const random = Math.random().toString(36).slice(2, 5).toUpperCase();
  return `TASK-${prefix}-${timestamp}${random}`;
}

function createDraftId() {
  return `DRAFT-DELIVERY-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

/** Legacy material/media submissions retain their existing ID format. */
function createSubmissionId() {
  return `SUBMISSION-${Date.now()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

function isCompletionInputValid(input: TaskCompletionInput) {
  if (!input.submittedBy.trim()) return false;

  if (input.kind === 'material') {
    return (
      input.files.length > 0 &&
      Boolean(input.note.trim()) &&
      Boolean(input.sourceOrderId.trim()) &&
      input.files.every(
        (file) =>
          Boolean(file.id.trim()) &&
          Boolean(file.objectKey?.trim()) &&
          !file.objectKey?.startsWith('task-completion/') &&
          Boolean(file.type.trim()) &&
          Boolean(file.fileMd5?.trim()) &&
          Boolean(file.sha3_256?.trim()) &&
          Number.isFinite(file.size) &&
          file.size >= 0 &&
          Number.isFinite(file.width) &&
          Number.isFinite(file.height) &&
          Number.isFinite(file.duration),
      )
    );
  }

  if (input.kind === 'media') {
    return Boolean(input.note.trim());
  }

  return deliveryWorkflowService.isSubmissionValid(input);
}

function createCompletionRecord(
  input: TaskCompletionInput,
  versionNo: number,
): TaskCompletionRecord {
  const metadata: TaskCompletionRecordMeta = {
    status: 'submitted',
    submissionId: createSubmissionId(),
    submittedAt: nowText(),
    versionNo,
  };
  if (input.kind === 'am') return { ...input, ...metadata };
  if (input.kind === 'material') return { ...input, ...metadata };
  return { ...input, ...metadata };
}

function toDeliveryCompletionState(
  completion: TaskCompletionState,
): DeliveryCompletionState {
  const toRecord = (record: TaskCompletionRecord) => {
    if (record.kind !== 'am') return;
    const { kind: _kind, ...deliveryRecord } = record;
    return deliveryRecord as DeliverySubmissionRecord;
  };

  return {
    acceptanceHistory: completion.acceptanceHistory.map((record) => ({
      ...record,
    })),
    current: completion.current ? toRecord(completion.current) : undefined,
    history: completion.history.flatMap((record) => {
      const deliveryRecord = toRecord(record);
      return deliveryRecord ? [deliveryRecord] : [];
    }),
  };
}

function fromDeliveryCompletionState(
  completion: DeliveryCompletionState,
): TaskCompletionState {
  const toAmRecord = (
    record: DeliverySubmissionRecord,
  ): AmTaskCompletionRecord => ({
    ...record,
    kind: 'am',
  });

  return {
    acceptanceHistory: completion.acceptanceHistory.map((record) => ({
      ...record,
    })),
    current: completion.current ? toAmRecord(completion.current) : undefined,
    history: completion.history.map((record) => toAmRecord(record)),
  };
}

function createEmptyCompletionState(): TaskCompletionState {
  return { acceptanceHistory: [], history: [] };
}

function createPendingAcceptanceExampleTask(): TaskCenterTask {
  return {
    actionLabel: '查看投放交付',
    audiences: ['all'],
    completion: {
      acceptanceHistory: [],
      current: {
        accountId: 'tt-jp-pixel-042',
        actualBudget: 680_000,
        actualStartAt: '2026-08-11 09:30',
        adCount: 18,
        adsetCount: 6,
        campaignCount: 2,
        campaignIds: ['1837420194550017', '1837420194550198'],
        currency: 'JPY',
        deliveryStatus: 'active',
        exceptionNote: '',
        files: [
          {
            id: 'acceptance-proof-001',
            name: 'PixelQuest_日本首轮投放成功证明.png',
            objectKey:
              'task-completion/TASK-AM-ACCEPT-20260811/acceptance-proof-001.png',
            size: 824_316,
            source: 'task-center-demo',
            type: 'image/png',
            uploadedAt: '2026-08-11 14:18:00',
          },
          {
            id: 'acceptance-data-001',
            name: 'PixelQuest_日本首轮投放数据.csv',
            objectKey:
              'task-completion/TASK-AM-ACCEPT-20260811/acceptance-data-001.csv',
            size: 186_420,
            source: 'task-center-demo',
            type: 'text/csv',
            uploadedAt: '2026-08-11 14:19:00',
          },
        ],
        kind: 'am',
        note: '已按计划完成日本首轮 TikTok 投放，账户与 Campaign 均正常启量。',
        platform: 'TikTok',
        status: 'submitted',
        submissionId: 'SUBMISSION-DEMO-ACCEPTANCE-001',
        submittedAt: '2026-08-11 14:20:00',
        submittedBy: '赵宁',
        versionNo: 1,
      },
      history: [],
    },
    createdAt: '2026-08-10 15:20:00',
    createdBy: '当前用户',
    dueAt: '2026-08-12 18:00',
    followed: true,
    id: PENDING_ACCEPTANCE_EXAMPLE_TASK_ID,
    kind: 'am',
    owner: '赵宁',
    progress: 100,
    project: 'Pixel Quest 日本首发',
    projectId: 'project-pixel',
    route: '/workbench/tasks',
    sourceId: 'REQ-AM-20260810-018',
    status: 'pending_acceptance',
    submissionCount: 1,
    summary:
      '完成日本首轮 TikTok 投放，提交实际账户、Campaign 结构、预算与成功证明供创建人验收。',
    title: 'Pixel Quest 日本首轮投放交付验收',
    updatedAt: '2026-08-11 14:20:00',
  };
}

function createPendingMaterialAcceptanceExampleTask(): TaskCenterTask {
  return {
    actionLabel: '验收素材',
    audiences: ['material_dispatcher', 'reviewer'],
    completion: {
      acceptanceHistory: [],
      current: {
        creativePlanner: '林策划',
        designer: '陈素材',
        files: [
          {
            id: 'material-101',
            name: '美国付费用户图片裂变_开屏视频.mp4',
            objectKey: 'material-orders/order-1002/material-101.mp4',
            size: 2_048_000,
            source: 'material-order-demo',
            type: 'video/mp4',
          },
          {
            id: 'material-102',
            name: '美国付费用户图片裂变_礼包主图.png',
            objectKey: 'material-orders/order-1002/material-102.png',
            size: 864_000,
            source: 'material-order-demo',
            type: 'image/png',
          },
        ],
        formalDeliveryId: 'delivery-order-1002-v1',
        formalVersionNo: 1,
        kind: 'material',
        note: '本次已实际交付 2 条素材，原需求数量 12 条；待验收通过后可选择素材加入素材库。',
        sourceOrderId: 'order-1002',
        status: 'submitted',
        submittedAt: '2026-08-20 10:05:00',
        submittedBy: '陈素材',
        submissionId: 'SUBMISSION-MATERIAL-ACCEPTANCE-001',
        versionNo: 1,
      },
      history: [],
    },
    createdAt: '2026-08-20 09:20:00',
    createdBy: '林策划',
    dueAt: '今天 18:00',
    followed: true,
    id: 'TASK-MAT-ACCEPT-20260820',
    kind: 'material',
    owner: '陈素材',
    progress: 100,
    project: 'Starfall 全球增长',
    projectId: 'project-starfall',
    route: '/requirement/detail',
    sourceId: 'order-1002',
    status: 'pending_acceptance',
    submissionCount: 1,
    summary: '本次实际交付 2 / 12 条素材。验收通过后可将素材移动到素材库。',
    title: '美国付费用户图片裂变 · 素材验收',
    updatedAt: '2026-08-20 10:05:00',
  };
}

/**
 * Additive demo fixtures for assignment hand-off. They retain the existing
 * TaskCenter record and storage shape; no completed/delivery workflow changes.
 */
function createAssignmentStateExampleTasks(): TaskCenterTask[] {
  return [
    {
      actionLabel: '分配素材负责人',
      assignments: [],
      audiences: ['material_dispatcher', 'reviewer'],
      createdAt: '2026-08-13 09:10:00',
      createdBy: '周主管',
      dueAt: '今天 17:30',
      id: PENDING_ASSIGNMENT_MATERIAL_EXAMPLE_TASK_ID,
      kind: 'material',
      owner: '素材负责人待分配',
      progress: 0,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/requirement/pool',
      status: 'pending_assignment',
      summary: '已创建素材需求，等待素材负责人领取并分配制作人。',
      title: 'Starfall 北美商店图二次适配',
      updatedAt: '2026-08-13 09:10:00',
    },
    {
      actionLabel: '分配投放负责人',
      assignments: [],
      audiences: ['am', 'operator_leader'],
      createdAt: '2026-08-13 09:20:00',
      createdBy: '周主管',
      dueAt: '明天 10:00',
      id: PENDING_ASSIGNMENT_AM_EXAMPLE_TASK_ID,
      kind: 'am',
      owner: '投放负责人待分配',
      progress: 0,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/workbench/tasks',
      status: 'pending_assignment',
      summary: '已创建投放准备任务，等待投放负责人确认归属后进入执行。',
      title: 'Orbit 巴西拉新投放准备',
      updatedAt: '2026-08-13 09:20:00',
    },
    {
      actionLabel: '提交交付',
      assignments: [
        {
          assigneeId: 'user-2',
          assigneeName: '陈素材',
          id: `assignment:${ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID}:user-2`,
          progress: 0,
          role: 'executor',
          status: 'pending',
          taskId: ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID,
        },
      ],
      audiences: ['creator', 'designer'],
      createdAt: '2026-08-13 09:30:00',
      createdBy: '林策划',
      dueAt: '8 月 14 日 18:00',
      id: ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID,
      kind: 'material',
      owner: '陈素材',
      ownerId: 'user-2',
      ownerName: '陈素材',
      progress: 0,
      project: 'Pixel Quest 日本首发',
      projectId: 'project-pixel',
      route: '/requirement/myTask',
      sourceId: 'order-1001',
      status: 'doing',
      summary: '素材任务已分配给陈素材，正在制作中。',
      title: 'Pixel Quest 日语开屏视频制作',
      updatedAt: '2026-08-13 09:30:00',
    },
  ];
}

/** Demo records keep the inactive-task view useful before users have created
 * their own withdrawal or rejection history. */
function createInactiveExampleTasks(): TaskCenterTask[] {
  return [
    {
      actionLabel: '查看撤回详情',
      audiences: ['all'],
      createdAt: '2026-08-12 10:30:00',
      createdBy: '周宁',
      dueAt: '已撤回',
      id: 'TASK-AM-WITHDRAWN-20260812',
      kind: 'am',
      owner: '周宁',
      progress: 0,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/workbench/tasks',
      status: 'withdrawn',
      summary: '预算策略调整，原定美国扩量任务已撤回，等待重新排期后再发起。',
      title: 'Starfall 美国扩量投放调整',
      updatedAt: '2026-08-14 09:40:00',
      withdrawnAt: '2026-08-14 09:40:00',
    },
    {
      actionLabel: '查看驳回原因',
      audiences: ['all'],
      createdAt: '2026-08-11 14:00:00',
      createdBy: '周宁',
      dueAt: '已驳回',
      id: 'TASK-MAT-REJECTED-20260811',
      kind: 'material',
      owner: '陈素材',
      progress: 0,
      project: 'Pixel Quest 日本首发',
      projectId: 'project-pixel',
      rejection: {
        reason: '首版字幕与品牌规范不一致，请按日语本地化标准调整后重新提交。',
        rejectedAt: '2026-08-14 11:20:00',
        rejectedBy: '周宁',
      },
      route: '/requirement/pool',
      status: 'rejected',
      summary: '素材交付未通过审核，已退回制作人补充修改。',
      title: 'Pixel Quest 日语开屏视频字幕适配',
      updatedAt: '2026-08-14 11:20:00',
    },
  ];
}

function normalizeStoredTasks(storedTasks: TaskCenterTask[]) {
  const demoMaterialOrderLinks: Record<string, string> = {
    [ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID]: 'order-1001',
    'TASK-MAT-2079': 'order-1001',
    'TASK-MAT-2088': 'order-1002',
  };
  const normalized = storedTasks.map((task) => {
    // The retired pitcher workspace now routes its task-center entries back to
    // the task list, so persisted task links do not lead to a removed page.
    const routeCompatibleTask =
      task.route === '/requirement/pitcher'
        ? {
            ...task,
            actionLabel:
              task.actionLabel === '进入投手需求工作台'
                ? '查看投放任务'
                : task.actionLabel,
            route: '/workbench/tasks',
          }
        : task;
    // The first hand-off fixture used an obsolete Orbit project reference.
    // Migrate only the untouched pending demo record by stable task ID; any
    // already-assigned user record keeps its original historical scope.
    const compatibleTask =
      routeCompatibleTask.id === PENDING_ASSIGNMENT_AM_EXAMPLE_TASK_ID &&
      routeCompatibleTask.status === 'pending_assignment' &&
      routeCompatibleTask.projectId === 'project-orbit'
        ? {
            ...routeCompatibleTask,
            project: 'Starfall 全球增长',
            projectId: 'project-starfall',
          }
        : routeCompatibleTask;
    const linkedTask =
      compatibleTask.kind === 'material' &&
      !compatibleTask.sourceId &&
      demoMaterialOrderLinks[compatibleTask.id]
        ? {
            ...compatibleTask,
            sourceId: demoMaterialOrderLinks[compatibleTask.id],
          }
        : compatibleTask;
    if (!linkedTask.completion) return linkedTask;
    return {
      ...linkedTask,
      completion: {
        ...linkedTask.completion,
        acceptanceHistory: Array.isArray(
          linkedTask.completion.acceptanceHistory,
        )
          ? linkedTask.completion.acceptanceHistory
          : [],
        history: Array.isArray(linkedTask.completion.history)
          ? linkedTask.completion.history
          : [],
      },
    };
  });

  const demoTasks = [
    createPendingAcceptanceExampleTask(),
    createPendingMaterialAcceptanceExampleTask(),
    ...createAssignmentStateExampleTasks(),
    ...createInactiveExampleTasks(),
  ];
  return [
    ...demoTasks.filter(
      (demoTask) => !normalized.some((task) => task.id === demoTask.id),
    ),
    ...normalized,
  ];
}

function createInitialTasks(): TaskCenterTask[] {
  return [
    createPendingAcceptanceExampleTask(),
    createPendingMaterialAcceptanceExampleTask(),
    ...createAssignmentStateExampleTasks(),
    ...createInactiveExampleTasks(),
    {
      actionLabel: '查看投放任务',
      audiences: ['am', 'operator', 'operator_leader'],
      createdAt: '2026-08-07 09:15:00',
      createdBy: '陈航',
      dueAt: '今天 18:00',
      followed: true,
      id: 'TASK-AM-1042',
      kind: 'am',
      owner: '陈航',
      progress: 62,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/workbench/tasks',
      status: 'doing',
      summary: '确认预算、受众与素材组合，并将制作需求拆分给素材团队。',
      title: 'Starfall 美国暑期扩量投放准备',
      updatedAt: '2026-08-11 10:18:00',
    },
    {
      actionLabel: '查看投放任务',
      audiences: ['am', 'operator', 'operator_leader'],
      createdAt: '2026-08-08 11:30:00',
      createdBy: '赵宁',
      dueAt: '明天 12:00',
      followed: false,
      id: 'TASK-AM-1038',
      kind: 'am',
      owner: '赵宁',
      progress: 34,
      project: 'Pixel Quest 日本首发',
      projectId: 'project-pixel',
      route: '/workbench/tasks',
      status: 'pending',
      summary: '根据首轮素材表现创建二次投放需求并补充制作任务。',
      title: 'Pixel Quest 日本首发二次投放',
      updatedAt: '2026-08-11 09:42:00',
    },
    {
      actionLabel: '进入素材需求池',
      audiences: ['material_dispatcher', 'operator_leader', 'reviewer'],
      createdAt: '2026-08-09 13:20:00',
      createdBy: '林琦',
      dueAt: '今天 16:30',
      followed: true,
      id: 'TASK-MAT-2088',
      kind: 'material',
      owner: '林琦',
      progress: 80,
      project: 'Project Ark 美国市场',
      projectId: 'project-ark',
      route: '/requirement/pool',
      sourceId: 'order-1002',
      status: 'risk',
      summary: '审核 12 张图片变体，确认规格和品牌规范后完成验收。',
      title: '商店节日主题图片变体',
      updatedAt: '2026-08-11 11:05:00',
    },
    {
      actionLabel: '进入制作任务',
      audiences: ['creator', 'designer'],
      createdAt: '2026-08-09 16:10:00',
      createdBy: '李想',
      dueAt: '8 月 13 日',
      followed: false,
      id: 'TASK-MAT-2079',
      kind: 'material',
      owner: '李想',
      progress: 45,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/requirement/myTask',
      sourceId: 'order-1001',
      status: 'doing',
      summary: '完成视频切割、字幕适配和多语言版本交付。',
      title: 'UGC 竖版视频批量制作',
      updatedAt: '2026-08-11 08:56:00',
    },
    {
      actionLabel: '进入账户审批',
      audiences: ['media', 'reviewer'],
      createdAt: '2026-08-10 09:30:00',
      createdBy: '媒介一组',
      dueAt: '今天 15:00',
      followed: false,
      id: 'TASK-MED-3014',
      kind: 'media',
      owner: '媒介一组',
      progress: 10,
      project: 'Pixel Quest 日本首发',
      projectId: 'project-pixel',
      route: '/media-resources/applications',
      status: 'pending',
      summary: '核验账户库存、代理线、时区与项目归属后完成出库。',
      title: 'TikTok 日本首发账户申请审批',
      updatedAt: '2026-08-11 09:16:00',
    },
    {
      actionLabel: '查看操作记录',
      audiences: ['media', 'reviewer'],
      createdAt: '2026-08-08 15:45:00',
      createdBy: '媒介二组',
      dueAt: '已完成',
      followed: true,
      id: 'TASK-MED-3009',
      kind: 'media',
      owner: '媒介二组',
      progress: 100,
      project: 'Starfall 全球增长',
      projectId: 'project-starfall',
      route: '/media-resources/audit',
      status: 'done',
      summary: '异常账户已停用并完成替换，操作记录已归档。',
      title: 'Facebook 账户异常处理',
      updatedAt: '2026-08-10 17:20:00',
    },
  ];
}

export const useTaskCenterStore = defineStore('adpulse-task-center', () => {
  const tasks = useStorage<TaskCenterTask[]>(
    TASK_STORAGE_KEY,
    createInitialTasks(),
  );
  const drafts = useStorage<TaskCenterDraft[]>(DRAFT_STORAGE_KEY, []);
  const normalizedTasks = normalizeStoredTasks(tasks.value);
  if (JSON.stringify(normalizedTasks) !== JSON.stringify(tasks.value)) {
    tasks.value = normalizedTasks;
  }

  const activeTasks = computed(() =>
    tasks.value.filter(
      (task) =>
        !(
          [
            'done',
            'rejected',
            'withdrawn',
            'paused',
            'cancelled',
          ] as TaskCenterStatus[]
        ).includes(task.status),
    ),
  );

  function addTask(input: CreateTaskCenterTaskInput) {
    const timestamp = nowText();
    const task: TaskCenterTask = {
      ...input,
      audiences: input.audiences ?? ['all'],
      createdAt: timestamp,
      createdBy: input.createdBy ?? input.owner,
      id: input.id ?? createTaskId(input.kind),
      progress: input.progress ?? 0,
      status: input.status ?? 'pending',
      updatedAt: timestamp,
    };
    tasks.value.unshift(task);
    return task;
  }

  function patchTask(taskId: string, patch: Partial<TaskCenterTask>) {
    const index = tasks.value.findIndex((task) => task.id === taskId);
    if (index === -1) return;
    const current = tasks.value[index];
    if (!current) return;
    const updated: TaskCenterTask = {
      ...current,
      ...patch,
      id: taskId,
      updatedAt: nowText(),
    };
    tasks.value[index] = updated;
    return updated;
  }

  /** 用服务端任务快照替换本地列表；草稿仍保留在浏览器中。 */
  function replaceTasks(serverTasks: TaskCenterTask[]) {
    tasks.value = serverTasks;
  }

  function toggleFollow(taskId: string) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (!task) return;
    return patchTask(taskId, { followed: !task.followed });
  }

  /**
   * Compatibility confirmation for an already assigned demo task. Formal
   * assignee identity and optimistic locking must still be enforced by the
   * future task backend, not by this browser Store.
   */
  function confirmAssignedTask(taskId: string) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (!task || task.status !== 'assigned_pending_confirmation') return;
    return patchTask(taskId, {
      actionLabel: '处理中',
      assignments: task.assignments?.map((assignment) =>
        assignment.role === 'executor' && assignment.status === 'pending'
          ? { ...assignment, status: 'doing' as const }
          : assignment,
      ),
      progress: Math.max(task.progress, 1),
      status: 'doing',
    });
  }

  function completeTask(taskId: string, input: TaskCompletionInput) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (
      !task ||
      ['done', 'pending_acceptance', 'withdrawn'].includes(task.status) ||
      task.kind !== input.kind ||
      !isCompletionInputValid(input)
    ) {
      return;
    }

    const completion = task.completion ?? createEmptyCompletionState();
    if (input.kind === 'am') {
      try {
        const deliveryCompletion = deliveryWorkflowService.submit(
          toDeliveryCompletionState(completion),
          input as DeliverySubmissionInput,
        );
        return patchTask(taskId, {
          completedAt: undefined,
          completion: fromDeliveryCompletionState(deliveryCompletion),
          progress: 100,
          status: 'pending_acceptance',
          submissionCount: deliveryCompletion.current?.versionNo,
        });
      } catch {
        return;
      }
    }

    const history = completion.current
      ? [
          ...completion.history,
          {
            ...completion.current,
            status:
              completion.current.status === 'rejected'
                ? ('rejected' as const)
                : ('superseded' as const),
          },
        ]
      : completion.history;
    const previousVersions = [
      ...history.map((record) => record.versionNo),
      ...(completion.current ? [completion.current.versionNo] : []),
    ];
    const versionNo = Math.max(0, ...previousVersions) + 1;
    const record = createCompletionRecord(input, versionNo);

    return patchTask(taskId, {
      completedAt: undefined,
      completion: {
        acceptanceHistory: completion.acceptanceHistory,
        current: record,
        history,
      },
      progress: 100,
      status: 'pending_acceptance',
      submissionCount: versionNo,
    });
  }

  function acceptTask(
    taskId: string,
    reviewer: string,
    reason = '',
    reviewerId?: string,
  ) {
    const task = tasks.value.find((item) => item.id === taskId);
    const completion = task?.completion;
    const current = completion?.current;
    if (
      !task ||
      task.status !== 'pending_acceptance' ||
      !completion ||
      !current ||
      !reviewer.trim()
    ) {
      return;
    }

    // Canonical material delivery/acceptance is owned by MaterialOrder. Keep
    // legacy local material records compatible, but never mark a linked order
    // accepted from Task Center without the formal acceptance endpoint.
    if (current.kind === 'material' && current.sourceOrderId) return;

    if (current.kind === 'am') {
      try {
        const deliveryAcceptance = deliveryWorkflowService.accept(
          toDeliveryCompletionState(completion),
          reviewer,
          reason,
          reviewerId,
        );
        return patchTask(taskId, {
          completedAt: deliveryAcceptance.acceptance.reviewedAt,
          completion: fromDeliveryCompletionState(
            deliveryAcceptance.completion,
          ),
          progress: 100,
          status: 'done',
        });
      } catch {
        return;
      }
    }

    const acceptanceRecord: TaskAcceptanceRecord = {
      decision: 'accepted',
      reason: reason.trim(),
      reviewedAt: nowText(),
      reviewerId: reviewerId?.trim() || undefined,
      reviewer: reviewer.trim(),
      submissionId: current.submissionId,
      versionNo: current.versionNo,
    };
    return patchTask(taskId, {
      completedAt: acceptanceRecord.reviewedAt,
      completion: {
        ...completion,
        acceptanceHistory: [...completion.acceptanceHistory, acceptanceRecord],
      },
      progress: 100,
      status: 'done',
    });
  }

  function rejectTask(
    taskId: string,
    reviewer: string,
    reason: string,
    reviewerId?: string,
  ) {
    const task = tasks.value.find((item) => item.id === taskId);
    const completion = task?.completion;
    const current = completion?.current;
    if (
      !task ||
      task.status !== 'pending_acceptance' ||
      !completion ||
      !current ||
      !reviewer.trim() ||
      !reason.trim()
    ) {
      return;
    }

    // A linked MaterialOrder must be rejected through its established review
    // route so its server versions are retained and task state cannot diverge
    // from the source order.
    if (current.kind === 'material' && current.sourceOrderId) return;

    if (current.kind === 'am') {
      try {
        const deliveryRejection = deliveryWorkflowService.reject(
          toDeliveryCompletionState(completion),
          reviewer,
          reason,
          reviewerId,
        );
        return patchTask(taskId, {
          completedAt: undefined,
          completion: fromDeliveryCompletionState(deliveryRejection.completion),
          progress: 0,
          status: 'doing',
        });
      } catch {
        return;
      }
    }

    const acceptanceRecord: TaskAcceptanceRecord = {
      decision: 'rejected',
      reason: reason.trim(),
      reviewedAt: nowText(),
      reviewerId: reviewerId?.trim() || undefined,
      reviewer: reviewer.trim(),
      submissionId: current.submissionId,
      versionNo: current.versionNo,
    };
    return patchTask(taskId, {
      completedAt: undefined,
      completion: {
        acceptanceHistory: [...completion.acceptanceHistory, acceptanceRecord],
        current: { ...current, status: 'rejected' },
        history: completion.history,
      },
      progress: 0,
      status: 'doing',
    });
  }

  /**
   * MaterialOrder remains the authority for a linked material delivery. This
   * only projects a confirmed source-order rejection back into the existing
   * task record so the next delivery becomes a new local version; it does not
   * call or emulate the formal rejection endpoint.
   */
  function syncMaterialOrderRejection(
    taskId: string,
    sourceOrderId: string,
    reason = '素材订单已打回，请补充后重新提交',
  ) {
    const task = tasks.value.find((item) => item.id === taskId);
    const completion = task?.completion;
    const current = completion?.current;
    if (
      !task ||
      task.kind !== 'material' ||
      task.sourceId !== sourceOrderId ||
      task.status !== 'pending_acceptance' ||
      !completion ||
      !current ||
      current.kind !== 'material' ||
      current.sourceOrderId !== sourceOrderId
    ) {
      return;
    }
    if (current.status === 'rejected') return task;

    const acceptanceRecord: TaskAcceptanceRecord = {
      decision: 'rejected',
      reason,
      reviewedAt: nowText(),
      reviewer: '素材订单',
      submissionId: current.submissionId,
      versionNo: current.versionNo,
    };
    return patchTask(taskId, {
      completedAt: undefined,
      completion: {
        acceptanceHistory: [...completion.acceptanceHistory, acceptanceRecord],
        current: { ...current, status: 'rejected' },
        history: completion.history,
      },
      progress: 0,
      status: 'doing',
    });
  }

  function withdrawTask(taskId: string) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (
      !task ||
      ['done', 'pending_acceptance', 'withdrawn'].includes(task.status)
    ) {
      return;
    }
    return patchTask(taskId, {
      status: 'withdrawn',
      withdrawnAt: nowText(),
    });
  }

  function rejectActiveTask(
    taskId: string,
    rejectedBy: string,
    reason: string,
    rejectedById?: string,
  ) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (
      !task ||
      ['done', 'rejected', 'withdrawn'].includes(task.status) ||
      !rejectedBy.trim() ||
      !reason.trim()
    ) {
      return;
    }
    const rejection: TaskRejectionRecord = {
      reason: reason.trim(),
      rejectedAt: nowText(),
      rejectedBy: rejectedBy.trim(),
      rejectedById: rejectedById?.trim() || undefined,
    };
    return patchTask(taskId, {
      actionLabel: '查看驳回原因',
      completedAt: undefined,
      progress: 0,
      rejection,
      status: 'rejected',
    });
  }

  function resubmitTask(taskId: string, patch: Partial<TaskCenterTask> = {}) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (!task || !['done', 'rejected', 'withdrawn'].includes(task.status)) {
      return;
    }
    const isInactive = ['rejected', 'withdrawn'].includes(task.status);
    const completion = task.completion ?? createEmptyCompletionState();
    const history = completion.current
      ? [
          ...completion.history,
          { ...completion.current, status: 'superseded' as const },
        ]
      : completion.history;
    return patchTask(taskId, {
      ...patch,
      actionLabel: patch.actionLabel ?? '提交任务交付',
      completedAt: undefined,
      completion: {
        acceptanceHistory: completion.acceptanceHistory,
        history,
      },
      dueAt:
        patch.dueAt ??
        task.delivery?.dueAt ??
        (isInactive || task.dueAt === '已完成' ? '待重新排期' : task.dueAt),
      progress: 0,
      rejection: undefined,
      status: 'pending',
      withdrawnAt: undefined,
    });
  }

  function addDraft(form: DeliveryTaskFormData, createdBy: string) {
    const timestamp = nowText();
    const draft: TaskCenterDraft = {
      createdAt: timestamp,
      createdBy,
      form,
      id: createDraftId(),
      kind: 'am',
      updatedAt: timestamp,
    };
    drafts.value.unshift(draft);
    return draft;
  }

  function updateDraft(
    draftId: string,
    form: DeliveryTaskFormData,
    createdBy?: string,
  ) {
    const index = drafts.value.findIndex((draft) => draft.id === draftId);
    if (index === -1) return;
    const current = drafts.value[index];
    if (!current) return;
    const updated: TaskCenterDraft = {
      ...current,
      createdBy: createdBy ?? current.createdBy,
      form,
      updatedAt: nowText(),
    };
    drafts.value[index] = updated;
    return updated;
  }

  function removeDraft(draftId: string) {
    drafts.value = drafts.value.filter((draft) => draft.id !== draftId);
  }

  function getDraft(draftId: string) {
    return drafts.value.find((draft) => draft.id === draftId);
  }

  function resetDemoData() {
    tasks.value = createInitialTasks();
    drafts.value = [];
  }

  return {
    acceptTask,
    activeTasks,
    addDraft,
    addTask,
    completeTask,
    confirmAssignedTask,
    drafts,
    getDraft,
    patchTask,
    rejectActiveTask,
    rejectTask,
    replaceTasks,
    removeDraft,
    resubmitTask,
    resetDemoData,
    syncMaterialOrderRejection,
    tasks,
    toggleFollow,
    updateDraft,
    withdrawTask,
  };
});
