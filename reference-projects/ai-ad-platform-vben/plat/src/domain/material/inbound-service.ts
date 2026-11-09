import type {
  AtomicMaterialInboundAdapter,
  MaterialInboundAdapter,
} from './adapter';
import type {
  AssignAcceptedMaterialsInput,
  AssignAcceptedMaterialsResult,
  AtomicMaterialInboundInput,
  AtomicMaterialInboundOperation,
  MaterialFolderRelation,
  MaterialFolderRelationFailure,
} from './types';

function uniqueStableIds(values: readonly string[], field: string) {
  const ids = values.map((value) => value.trim()).filter(Boolean);
  if (ids.length === 0) throw new Error(`请至少选择 1 个${field}`);
  return [...new Set(ids)];
}

function validRating(rating: number | undefined = 5) {
  if (!Number.isFinite(rating) || rating < 1 || rating > 5) {
    throw new Error('验收评分必须在 1 到 5 之间');
  }
  return rating;
}

/**
 * Validates stable server material IDs before the legacy accept/assign APIs
 * are called. Folder writes remain per-folder because the old transport has
 * no documented multi-folder transaction or idempotency contract.
 */
export class MaterialInboundService {
  constructor(
    private readonly adapter: MaterialInboundAdapter,
    private readonly atomicAdapter?: AtomicMaterialInboundAdapter,
  ) {}

  async acceptAndAssign(
    input: AssignAcceptedMaterialsInput,
  ): Promise<AssignAcceptedMaterialsResult> {
    const orderId = input.orderId.trim();
    if (!orderId) throw new Error('素材订单缺少稳定 ID，无法验收入库');
    const materialIds = uniqueStableIds(input.materialIds, '素材');
    const folderIds = uniqueStableIds(input.folderIds, '目标文件夹');
    const rating = validRating(input.rating);

    const [order, availableMaterials] = await Promise.all([
      this.adapter.getOrder(orderId),
      this.adapter.listOrderMaterials(orderId),
    ]);
    if (order.orderId !== orderId) {
      throw new Error('素材订单返回的稳定 ID 不匹配，已阻断入库');
    }
    if (!['accepted', 'archived', 'pending_accept'].includes(order.status)) {
      throw new Error('素材订单尚未进入可验收或可入库状态');
    }

    const availableById = new Map(
      availableMaterials.map((material) => [material.id, material]),
    );
    const missingIds = materialIds.filter((id) => !availableById.has(id));
    if (missingIds.length > 0) {
      throw new Error(
        `所选素材不属于当前订单或缺少稳定素材 ID：${missingIds.join('、')}`,
      );
    }

    let resolvedOrder = order;
    let acceptanceSubmitted = false;
    if (order.status === 'pending_accept') {
      resolvedOrder = await this.adapter.acceptOrder(orderId, rating);
      if (resolvedOrder.orderId !== orderId) {
        throw new Error('验收接口返回的稳定订单 ID 不匹配，已阻断入库');
      }
      if (!['accepted', 'archived'].includes(resolvedOrder.status)) {
        throw new Error('素材订单验收未确认通过，已阻断入库');
      }
      acceptanceSubmitted = true;
    }

    const relations: MaterialFolderRelation[] = [];
    const failures: MaterialFolderRelationFailure[] = [];
    for (const folderId of folderIds) {
      try {
        relations.push(
          ...(await this.adapter.submitFolderRelations({
            folderId,
            materialIds,
            orderId,
            scope: input.scope,
          })),
        );
      } catch (error) {
        failures.push({
          folderId,
          message: error instanceof Error ? error.message : '素材关系写入失败',
        });
      }
    }

    return {
      acceptanceSubmitted,
      failures,
      materials: materialIds.flatMap((id) => {
        const material = availableById.get(id);
        return material ? [{ ...material }] : [];
      }),
      order: resolvedOrder,
      relations,
    };
  }

  /**
   * Uses only a backend-provided atomic transaction. This path is opt-in and
   * never falls back to the legacy accept + per-folder writes after an error:
   * doing so could duplicate an operation when a formal request times out.
   */
  async acceptAndAssignAtomically(
    input: AtomicMaterialInboundInput,
  ): Promise<AtomicMaterialInboundOperation> {
    if (!this.atomicAdapter) {
      throw new Error('正式素材入库原子契约尚未接入，不能替代旧入库流程');
    }

    const idempotencyKey = input.idempotencyKey.trim();
    if (!idempotencyKey) throw new Error('正式素材入库缺少幂等键');
    const orderId = input.orderId.trim();
    if (!orderId) throw new Error('素材订单缺少稳定 ID，无法验收入库');

    const operation = await this.atomicAdapter.acceptAndAssignAtomically({
      folderIds: uniqueStableIds(input.folderIds, '目标文件夹'),
      idempotencyKey,
      materialIds: uniqueStableIds(input.materialIds, '素材'),
      orderId,
      rating: validRating(input.rating),
      scope: input.scope,
    });
    if (operation.idempotencyKey !== idempotencyKey) {
      throw new Error('正式入库接口回传的幂等键不匹配');
    }
    if (operation.order.orderId !== orderId) {
      throw new Error('正式入库接口返回的稳定订单 ID 不匹配');
    }
    return operation;
  }
}
