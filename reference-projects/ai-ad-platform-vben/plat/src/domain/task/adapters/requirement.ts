import type { RequirementTaskAdapter } from '../adapter';
import type {
  CreateMaterialTaskContext,
  MaterialOrderWriteResult,
  TaskAssignment,
  TaskAssignmentProjection,
  TaskAssignmentStatus,
  UnresolvedLegacyTaskParticipant,
} from '../types';

import type {
  CreateOrderParams,
  MaterialOrderAssignmentPayload,
  MaterialOrderLegacyParticipants,
} from '#/api/requirement';

import { createMaterialOrder, updateMaterialOrder } from '#/api/requirement';

type MaterialOrderCreate = (payload: CreateOrderParams) => Promise<unknown>;
type MaterialOrderUpdate = (
  orderId: string,
  payload: CreateOrderParams,
) => Promise<unknown>;

export interface RequirementTaskAdapterOptions {
  create?: MaterialOrderCreate;
  update?: MaterialOrderUpdate;
}

export interface StableMaterialParticipant {
  departmentId?: string;
  name: string;
  userId: string;
}

export interface MaterialOrderParticipantInput {
  creativePlanners?: readonly StableMaterialParticipant[];
  designers?: readonly StableMaterialParticipant[];
  legacy?: MaterialOrderLegacyParticipants;
}

export interface MaterialOrderParticipantPayload {
  assignments: MaterialOrderAssignmentPayload[];
  creative_planner_user_ids: string[];
  creative_planners: string[];
  designer_user_ids: string[];
  designers: string[];
  legacy_participant_names: MaterialOrderLegacyParticipants;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is string => typeof item === 'string' && Boolean(item.trim()),
  );
}

function normalizeAssignmentStatus(value: unknown): TaskAssignmentStatus {
  return ['cancelled', 'doing', 'done', 'pending', 'submitted'].includes(
    String(value),
  )
    ? (value as TaskAssignmentStatus)
    : 'pending';
}

function uniqueNames(values: readonly string[]) {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function assignmentFromPayload(
  taskId: string,
  raw: unknown,
): TaskAssignment | undefined {
  const record = asRecord(raw);
  if (!record) return;
  const assigneeId = String(
    record.assignee_id ?? record.assigneeId ?? '',
  ).trim();
  const assigneeName = String(
    record.assignee_name ?? record.assigneeName ?? '',
  ).trim();
  const role = String(record.role);
  if (
    !assigneeId ||
    !assigneeName ||
    !['executor', 'observer', 'owner', 'reviewer'].includes(role)
  ) {
    return;
  }
  const progress = Number(record.progress);
  const dueAt = record.due_at ?? record.dueAt;
  const departmentId = record.department_id ?? record.departmentId;
  return {
    alsoExecutor: Boolean(record.also_executor ?? record.alsoExecutor),
    assigneeId,
    assigneeName,
    departmentId:
      typeof departmentId === 'string' && departmentId.trim()
        ? departmentId.trim()
        : undefined,
    dueAt: typeof dueAt === 'string' && dueAt.trim() ? dueAt.trim() : undefined,
    id: String(record.id ?? '').trim() || `assignment:${taskId}:${assigneeId}`,
    progress: Number.isFinite(progress)
      ? Math.max(0, Math.min(100, progress))
      : 0,
    role: role as TaskAssignment['role'],
    status: normalizeAssignmentStatus(record.status),
    taskId,
  };
}

/**
 * Reads both future stable payloads and old participant name arrays. Names in
 * old arrays deliberately remain unresolved; a same-name account is never
 * guessed or merged into a stable person.
 */
export function readMaterialOrderParticipantProjection(
  value: unknown,
): TaskAssignmentProjection {
  const record = asRecord(asRecord(value)?.data ?? value) ?? {};
  const taskId = String(
    record.id ?? record._id ?? record.order_id ?? record.orderNo ?? '',
  ).trim();
  let rawAssignments: unknown[] = [];
  if (Array.isArray(record.assignments)) {
    rawAssignments = record.assignments;
  } else if (Array.isArray(record.task_assignments)) {
    rawAssignments = record.task_assignments;
  }
  const stableAssignments = rawAssignments.flatMap((raw) => {
    const assignment = assignmentFromPayload(taskId || 'material-order', raw);
    return assignment ? [assignment] : [];
  });
  const legacy = {
    completed_designers: asStringArray(record.completed_designers),
    creative_planners: asStringArray(record.creative_planners),
    designers: asStringArray(record.designers),
  };
  const unresolvedLegacyParticipants: UnresolvedLegacyTaskParticipant[] = [
    ...legacy.creative_planners.map((name) => ({
      name,
      role: 'owner' as const,
      source: 'material-order.creative_planners',
    })),
    ...legacy.designers.map((name) => ({
      name,
      role: 'executor' as const,
      source: 'material-order.designers',
      status: legacy.completed_designers.includes(name)
        ? ('done' as const)
        : ('pending' as const),
    })),
  ];
  return {
    assignments: stableAssignments,
    unresolvedLegacyParticipants,
  };
}

/** Creates stable payload fields while continuing to submit legacy names. */
export function serializeMaterialOrderParticipants(
  orderId: string,
  input: MaterialOrderParticipantInput,
): MaterialOrderParticipantPayload {
  const normalizedOrderId = orderId.trim();
  const assignments = new Map<string, MaterialOrderAssignmentPayload>();
  const planners = input.creativePlanners ?? [];
  const designers = input.designers ?? [];
  const add = (
    participant: StableMaterialParticipant,
    role: MaterialOrderAssignmentPayload['role'],
  ) => {
    const userId = participant.userId.trim();
    const name = participant.name.trim();
    if (!userId || !name) return;
    const current = assignments.get(userId);
    assignments.set(userId, {
      also_executor:
        current?.also_executor ||
        (current?.role === 'owner' && role === 'executor'),
      assignee_id: userId,
      assignee_name: name,
      department_id: participant.departmentId?.trim() || undefined,
      id: current?.id ?? `assignment:${normalizedOrderId}:${userId}`,
      progress: current?.progress ?? 0,
      role: current?.role === 'owner' || role === 'owner' ? 'owner' : role,
      status: current?.status ?? 'pending',
    });
  };
  for (const participant of planners) add(participant, 'owner');
  for (const participant of designers) add(participant, 'executor');

  const legacy = {
    completed_designers: uniqueNames(input.legacy?.completed_designers ?? []),
    creative_planners: uniqueNames(input.legacy?.creative_planners ?? []),
    designers: uniqueNames(input.legacy?.designers ?? []),
  } satisfies MaterialOrderLegacyParticipants;
  return {
    assignments: [...assignments.values()],
    creative_planner_user_ids: [
      ...new Set(planners.map((item) => item.userId)),
    ],
    creative_planners: uniqueNames([
      ...legacy.creative_planners,
      ...planners.map((item) => item.name),
    ]),
    designer_user_ids: [...new Set(designers.map((item) => item.userId))],
    designers: uniqueNames([
      ...legacy.designers,
      ...designers.map((item) => item.name),
    ]),
    legacy_participant_names: legacy,
  };
}

function getMaterialOrderId(response: unknown): string | undefined {
  const record = asRecord(response);
  const nested = asRecord(record?.data);
  const candidate =
    record?.id ??
    record?._id ??
    record?.order_id ??
    nested?.id ??
    nested?._id ??
    nested?.order_id;
  return typeof candidate === 'string' && candidate.trim()
    ? candidate.trim()
    : undefined;
}

function getTaskCenterTaskFields(response: unknown) {
  const record = asRecord(response);
  const nested = asRecord(record?.data);
  const taskCenterTaskId =
    record?.task_center_task_id ?? nested?.task_center_task_id;
  const taskCenterTaskCode = record?.task_code ?? nested?.task_code;
  return {
    taskCenterTaskCode:
      typeof taskCenterTaskCode === 'string' && taskCenterTaskCode.trim()
        ? taskCenterTaskCode.trim()
        : undefined,
    taskCenterTaskId:
      typeof taskCenterTaskId === 'string' && taskCenterTaskId.trim()
        ? taskCenterTaskId.trim()
        : undefined,
  };
}

function messageFromError(error: unknown) {
  const record = asRecord(error);
  const response = asRecord(record?.response);
  const data = asRecord(response?.data);
  return [data?.detail, data?.message, record?.message]
    .filter((value): value is string => typeof value === 'string')
    .join(' ')
    .toLowerCase();
}

function statusFromError(error: unknown) {
  const record = asRecord(error);
  const response = asRecord(record?.response);
  return typeof response?.status === 'number' ? response.status : undefined;
}

/**
 * A fallback is safe only when the server explicitly rejected the newly added
 * fields before creating anything. Timeouts and 5xx errors are intentionally
 * never retried with the old payload.
 */
export function isUnsupportedSourceContextError(error: unknown) {
  const status = statusFromError(error);
  if (status !== 400 && status !== 422) return false;
  const message = messageFromError(error);
  return (
    /unknown|unsupported|unrecognized|unexpected|extra/.test(message) &&
    /project_id|source_task_id|requester_id|requester_name/.test(message)
  );
}

function withoutSourceContext(payload: CreateOrderParams): CreateOrderParams {
  const {
    project_id: _projectId,
    requester_id: _requesterId,
    requester_name: _requesterName,
    source_task_id: _sourceTaskId,
    ...legacyPayload
  } = payload;
  return legacyPayload;
}

function hasSourceContextFields(payload: CreateOrderParams) {
  return Boolean(
    payload.project_id ||
      payload.requester_id ||
      payload.requester_name ||
      payload.source_task_id,
  );
}

function withSourceContext(
  payload: CreateOrderParams,
  context: CreateMaterialTaskContext | undefined,
) {
  if (!context) return payload;
  return {
    ...payload,
    project_id: context.projectId,
    requester_id: context.requesterId,
    requester_name: context.requesterName,
    source_task_id: context.sourceTaskId,
  } satisfies CreateOrderParams;
}

function toWriteResult(
  response: unknown,
  context: CreateMaterialTaskContext | undefined,
  sourceLinkState: MaterialOrderWriteResult['sourceLinkState'],
  knownOrderId?: string,
): MaterialOrderWriteResult {
  const materialOrderId = getMaterialOrderId(response) ?? knownOrderId;
  const taskCenterTask = getTaskCenterTaskFields(response);
  let resolvedSourceLinkState: MaterialOrderWriteResult['sourceLinkState'] =
    'manual';
  if (context) {
    resolvedSourceLinkState = materialOrderId
      ? sourceLinkState
      : 'missing-order-id';
  }
  return {
    ...(materialOrderId ? { materialOrderId } : {}),
    response,
    sourceLinkState: resolvedSourceLinkState,
    ...taskCenterTask,
  };
}

/** Maintains the established `material-orders` route and payload shape. */
export class LegacyRequirementTaskAdapter implements RequirementTaskAdapter {
  private readonly createOrder: MaterialOrderCreate;
  private readonly updateOrder: MaterialOrderUpdate;

  constructor(options: RequirementTaskAdapterOptions = {}) {
    this.createOrder = options.create ?? createMaterialOrder;
    this.updateOrder = options.update ?? updateMaterialOrder;
  }

  async create(
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult> {
    return this.write(
      (requestPayload) => this.createOrder(requestPayload),
      payload,
      context,
    );
  }

  async update(
    orderId: string,
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult> {
    return this.write(
      (requestPayload) => this.updateOrder(orderId, requestPayload),
      payload,
      context,
      orderId,
    );
  }

  private async write(
    request: (payload: CreateOrderParams) => Promise<unknown>,
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
    knownOrderId?: string,
  ): Promise<MaterialOrderWriteResult> {
    const enriched = withSourceContext(payload, context);
    try {
      return toWriteResult(
        await request(enriched),
        context,
        context ? 'linked' : 'manual',
        knownOrderId,
      );
    } catch (error) {
      if (
        !hasSourceContextFields(enriched) ||
        !isUnsupportedSourceContextError(error)
      ) {
        throw error;
      }
      const legacyResponse = await request(withoutSourceContext(enriched));
      return toWriteResult(
        legacyResponse,
        context,
        context ? 'legacy-unlinked' : 'manual',
        knownOrderId,
      );
    }
  }
}
