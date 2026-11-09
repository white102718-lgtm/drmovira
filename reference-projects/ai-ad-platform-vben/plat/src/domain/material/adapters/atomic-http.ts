import type {
  AtomicMaterialInboundAdapter,
  AtomicMaterialInboundTransport,
} from '../adapter';
import type {
  AtomicMaterialInboundInput,
  AtomicMaterialInboundOperation,
  MaterialFolderRelation,
  MaterialOrderInboundContext,
  MaterialOrderInboundStatus,
} from '../types';

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown, message: string): UnknownRecord {
  if (!isRecord(value)) throw new Error(message);
  return value;
}

function readString(record: UnknownRecord, keys: readonly string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function readRequiredString(
  record: UnknownRecord,
  keys: readonly string[],
  message: string,
) {
  const value = readString(record, keys);
  if (!value) throw new Error(message);
  return value;
}

function readOperationRecord(response: unknown): UnknownRecord {
  const envelope = asRecord(response, '正式入库接口返回格式无效');
  const data = isRecord(envelope.data) ? envelope.data : envelope;
  return isRecord(data.operation) ? data.operation : data;
}

function readStatus(value: unknown): 'completed' | 'failed' | 'pending' {
  if (value === 'completed' || value === 'failed' || value === 'pending') {
    return value;
  }
  throw new Error('正式入库接口缺少有效的原子操作状态');
}

function readOrder(
  record: UnknownRecord,
  requestedOrderId: string,
): MaterialOrderInboundContext {
  const rawOrder = isRecord(record.order) ? record.order : record;
  const orderId = readRequiredString(
    rawOrder,
    ['orderId', 'order_id'],
    '正式入库接口缺少稳定订单 ID',
  );
  if (orderId !== requestedOrderId) {
    throw new Error('正式入库接口返回的稳定订单 ID 不匹配');
  }

  const rawStatus = readString(rawOrder, ['status']) ?? 'accepted';
  const status: MaterialOrderInboundStatus = [
    'accepted',
    'archived',
    'pending_accept',
  ].includes(rawStatus)
    ? (rawStatus as MaterialOrderInboundStatus)
    : 'unknown';

  return {
    orderId,
    status,
    title: readString(rawOrder, ['title', 'name']) ?? '',
  };
}

function readRelations(
  record: UnknownRecord,
  request: AtomicMaterialInboundInput,
  status: 'completed' | 'failed' | 'pending',
): MaterialFolderRelation[] {
  const rawRelations = record.relations;
  if (!Array.isArray(rawRelations)) {
    if (status === 'completed') {
      throw new Error('正式入库接口未返回已创建的文件夹关系');
    }
    return [];
  }

  const expected = new Set(
    request.folderIds.flatMap((folderId) =>
      request.materialIds.map((materialId) => `${folderId}\u0000${materialId}`),
    ),
  );
  const seen = new Set<string>();
  const relations = rawRelations.map((item) => {
    const relation = asRecord(item, '正式入库接口包含无效的文件夹关系');
    const folderId = readRequiredString(
      relation,
      ['folderId', 'folder_id'],
      '正式入库接口关系缺少稳定文件夹 ID',
    );
    const materialId = readRequiredString(
      relation,
      ['materialId', 'material_id'],
      '正式入库接口关系缺少稳定素材 ID',
    );
    const relationId = readRequiredString(
      relation,
      ['relationId', 'relation_id', 'id', '_id'],
      '正式入库接口关系缺少不可变关系 ID',
    );
    const key = `${folderId}\u0000${materialId}`;
    if (!expected.has(key) || seen.has(key)) {
      throw new Error('正式入库接口返回了未请求或重复的文件夹关系');
    }
    seen.add(key);
    return {
      folderId,
      materialId,
      relationId,
      sourceOrderId: request.orderId,
      writeStatus: 'created' as const,
    };
  });

  if (status === 'completed' && seen.size !== expected.size) {
    throw new Error('正式入库接口未完整创建所请求的文件夹关系');
  }
  return relations;
}

/**
 * Normalizes the documented atomic response envelope. It intentionally has no
 * direct `backendClient` dependency: endpoint discovery and authentication are
 * a backend integration concern, and callers must inject the agreed transport.
 */
export class HttpAtomicMaterialInboundAdapter
  implements AtomicMaterialInboundAdapter
{
  constructor(private readonly transport: AtomicMaterialInboundTransport) {}

  async acceptAndAssignAtomically(
    request: AtomicMaterialInboundInput,
  ): Promise<AtomicMaterialInboundOperation> {
    const record = readOperationRecord(await this.transport.submit(request));
    const operationId = readRequiredString(
      record,
      ['operationId', 'operation_id', 'id', '_id'],
      '正式入库接口缺少不可变操作 ID',
    );
    const idempotencyKey = readRequiredString(
      record,
      ['idempotencyKey', 'idempotency_key'],
      '正式入库接口未回传幂等键',
    );
    if (idempotencyKey !== request.idempotencyKey) {
      throw new Error('正式入库接口回传的幂等键不匹配');
    }
    const audit = asRecord(record.audit, '正式入库接口缺少审计记录');

    return {
      audit: {
        action: 'accepted_and_assigned',
        id: readRequiredString(
          audit,
          ['id', '_id', 'auditId', 'audit_id'],
          '正式入库接口审计记录缺少不可变 ID',
        ),
        occurredAt: readRequiredString(
          audit,
          ['occurredAt', 'occurred_at', 'createdAt', 'created_at'],
          '正式入库接口审计记录缺少发生时间',
        ),
      },
      idempotencyKey,
      operationId,
      order: readOrder(record, request.orderId),
      relations: readRelations(record, request, readStatus(record.status)),
      status: readStatus(record.status),
    };
  }
}
