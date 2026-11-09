import type {
  DeliveryDistributionPreview,
  DeliveryExecutionUnit,
  DeliveryMaterialDistributionItem,
  MaterialAllocationAsset,
  MaterialAllocationRequirement,
  MaterialAllocationUser,
  MaterialOversendAssignment,
  MaterialProductionSlot,
  OversendPreview,
  ProductionAllocationPreview,
} from './types';

const LOCKED_PRODUCTION_STATUSES = new Set<MaterialProductionSlot['status']>([
  'accepted',
  'delivered',
  'in_progress',
]);

function stableText(left: string, right: string) {
  return left.localeCompare(right, 'zh-CN');
}

function uniqueActiveUsers(users: readonly MaterialAllocationUser[]) {
  const unique = new Map<string, MaterialAllocationUser>();
  for (const user of users) {
    const userId = user.userId.trim();
    if (!userId || user.active === false || unique.has(userId)) continue;
    unique.set(userId, { ...user, userId });
  }
  return [...unique.values()].sort((left, right) =>
    stableText(left.userId, right.userId),
  );
}

export function sortMaterialRequirements(
  requirements: readonly MaterialAllocationRequirement[],
) {
  return [...requirements].sort(
    (left, right) =>
      left.sortOrder - right.sortOrder || stableText(left.id, right.id),
  );
}

export function normalizeMaterialOrder(
  materials: readonly MaterialAllocationAsset[],
  preferredIds: readonly string[] = [],
) {
  const preferredOrder = new Map(
    preferredIds.map((materialId, index) => [materialId, index]),
  );
  return [...materials]
    .sort((left, right) => {
      const leftPreferred = preferredOrder.get(left.id);
      const rightPreferred = preferredOrder.get(right.id);
      if (leftPreferred !== undefined || rightPreferred !== undefined) {
        return (
          (leftPreferred ?? Number.MAX_SAFE_INTEGER) -
          (rightPreferred ?? Number.MAX_SAFE_INTEGER)
        );
      }
      return left.sortOrder - right.sortOrder || stableText(left.id, right.id);
    })
    .map((material) => material.id);
}

export function moveOrderedItem(
  ids: readonly string[],
  itemId: string,
  direction: -1 | 1,
) {
  const next = [...ids];
  const index = next.indexOf(itemId);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= next.length) return next;
  const currentItem = next[index];
  const targetItem = next[target];
  if (currentItem === undefined || targetItem === undefined) return next;
  next[index] = targetItem;
  next[target] = currentItem;
  return next;
}

export function buildBalancedProductionSlots(input: {
  designers: readonly MaterialAllocationUser[];
  existingSlots?: readonly MaterialProductionSlot[];
  requirements: readonly MaterialAllocationRequirement[];
  taskId: string;
}): ProductionAllocationPreview {
  const designers = uniqueActiveUsers(input.designers);
  const requirements = sortMaterialRequirements(input.requirements).filter(
    (requirement) => requirement.quantity > 0,
  );
  const existingSlots = input.existingSlots ?? [];
  const activeRequirementIds = new Set(
    requirements.map((requirement) => requirement.id),
  );
  const lockedByKey = new Map<string, MaterialProductionSlot>();

  for (const slot of existingSlots) {
    if (!LOCKED_PRODUCTION_STATUSES.has(slot.status) && !slot.locked) continue;
    lockedByKey.set(`${slot.requirementId}:${slot.slotNo}`, {
      ...slot,
      locked: true,
    });
  }

  const designerLoads: Record<string, number> = Object.fromEntries(
    designers.map((designer) => [designer.userId, 0]),
  );
  const slots: MaterialProductionSlot[] = [];
  const overPlanSlots = existingSlots.filter((slot) => {
    if (!slot.locked && !LOCKED_PRODUCTION_STATUSES.has(slot.status)) {
      return false;
    }
    const requirement = requirements.find(
      (item) => item.id === slot.requirementId,
    );
    return !requirement || slot.slotNo > requirement.quantity;
  });

  for (const slot of lockedByKey.values()) {
    const currentLoad = designerLoads[slot.designerUserId];
    if (currentLoad !== undefined) {
      designerLoads[slot.designerUserId] = currentLoad + 1;
    }
  }

  let cursor = 0;
  for (const requirement of requirements) {
    const requirementDesignerIds = new Set(
      requirement.designerUserIds?.filter(Boolean) ?? [],
    );
    const requirementDesigners =
      requirementDesignerIds.size > 0
        ? designers.filter((designer) =>
            requirementDesignerIds.has(designer.userId),
          )
        : designers;
    const requirementLoads: Record<string, number> = Object.fromEntries(
      requirementDesigners.map((designer) => [designer.userId, 0]),
    );

    for (let slotNo = 1; slotNo <= requirement.quantity; slotNo += 1) {
      const key = `${requirement.id}:${slotNo}`;
      const locked = lockedByKey.get(key);
      if (locked) {
        slots.push({ ...locked, overPlan: false });
        const currentRequirementLoad = requirementLoads[locked.designerUserId];
        if (currentRequirementLoad !== undefined) {
          requirementLoads[locked.designerUserId] = currentRequirementLoad + 1;
        }
        continue;
      }

      if (requirementDesigners.length === 0) continue;
      const rotationOffset = cursor % requirementDesigners.length;
      const ranked = requirementDesigners
        .map((designer, index) => ({
          designer,
          index,
          requirementLoad: requirementLoads[designer.userId] ?? 0,
          rotationRank:
            (index - rotationOffset + requirementDesigners.length) %
            requirementDesigners.length,
          totalLoad: designerLoads[designer.userId] ?? 0,
        }))
        .sort(
          (left, right) =>
            left.totalLoad - right.totalLoad ||
            left.requirementLoad - right.requirementLoad ||
            left.rotationRank - right.rotationRank ||
            stableText(left.designer.userId, right.designer.userId),
        );
      const selected = ranked[0];
      if (!selected) continue;
      const designer = selected.designer;
      slots.push({
        designerUserId: designer.userId,
        designerUserName: designer.userName,
        id: `production-slot:${input.taskId}:${requirement.id}:${slotNo}`,
        locked: false,
        requirementId: requirement.id,
        slotNo,
        status: 'planned',
      });
      designerLoads[designer.userId] =
        (designerLoads[designer.userId] ?? 0) + 1;
      requirementLoads[designer.userId] =
        (requirementLoads[designer.userId] ?? 0) + 1;
      cursor = (selected.index + 1) % requirementDesigners.length;
    }
  }

  for (const slot of overPlanSlots) {
    if (
      activeRequirementIds.has(slot.requirementId) &&
      slots.some((item) => item.id === slot.id)
    ) {
      continue;
    }
    slots.push({ ...slot, locked: true, overPlan: true });
  }

  const loadValues = Object.values(designerLoads);
  const maxLoadDifference =
    loadValues.length > 0
      ? Math.max(...loadValues) - Math.min(...loadValues)
      : 0;

  return { designerLoads, maxLoadDifference, slots };
}

export function buildUniqueDeliveryDistribution(input: {
  allowReuse?: boolean;
  executionUnits: readonly DeliveryExecutionUnit[];
  materials: readonly MaterialAllocationAsset[];
  preferredMaterialIds?: readonly string[];
  taskId: string;
}): DeliveryDistributionPreview {
  const executionUnits = [...input.executionUnits].sort((left, right) =>
    stableText(left.id, right.id),
  );
  const acceptedMaterials = input.materials.filter(
    (material) => material.accepted,
  );
  const materialById = new Map(
    acceptedMaterials.map((material) => [material.id, material]),
  );
  const materialIds = normalizeMaterialOrder(
    acceptedMaterials,
    input.preferredMaterialIds,
  );
  const items: DeliveryMaterialDistributionItem[] = [];
  const duplicateMaterialIds = new Set<string>();
  const missingExecutionUnitIds: string[] = [];

  executionUnits.forEach((executionUnit, index) => {
    if (materialIds.length === 0) {
      missingExecutionUnitIds.push(executionUnit.id);
      return;
    }
    if (index >= materialIds.length && !input.allowReuse) {
      missingExecutionUnitIds.push(executionUnit.id);
      return;
    }
    const materialId = materialIds[index % materialIds.length];
    if (!materialId) return;
    const material = materialById.get(materialId);
    if (!material) return;
    const repeated = index >= materialIds.length;
    if (repeated) duplicateMaterialIds.add(materialId);
    items.push({
      executionUnitId: executionUnit.id,
      id: `distribution:${input.taskId}:${executionUnit.id}`,
      materialId,
      materialName: material.name,
      repeated,
      status: 'preview',
    });
  });

  return {
    canConfirm:
      missingExecutionUnitIds.length === 0 &&
      (duplicateMaterialIds.size === 0 || Boolean(input.allowReuse)),
    duplicateMaterialIds: [...duplicateMaterialIds],
    items,
    missingExecutionUnitIds,
  };
}

export function buildOversendAssignments(input: {
  existingAssignments?: readonly MaterialOversendAssignment[];
  materials: readonly MaterialAllocationAsset[];
  projectId: string;
  recipients: readonly MaterialAllocationUser[];
  requirements: readonly MaterialAllocationRequirement[];
  taskId: string;
}): OversendPreview {
  const requirementById = new Map(
    input.requirements.map((requirement) => [requirement.id, requirement]),
  );
  const recipients = uniqueActiveUsers(input.recipients).filter(
    (recipient) => recipient.projectId === input.projectId,
  );
  const acceptedByRequirement = new Map<string, MaterialAllocationAsset[]>();
  for (const material of input.materials.filter((item) => item.accepted)) {
    const requirementId = material.requirementId ?? '';
    acceptedByRequirement.set(requirementId, [
      ...(acceptedByRequirement.get(requirementId) ?? []),
      material,
    ]);
  }

  const materialIds: string[] = [];
  for (const [requirementId, materials] of acceptedByRequirement) {
    const plannedQuantity = requirementById.get(requirementId)?.quantity ?? 0;
    const orderedIds = normalizeMaterialOrder(materials);
    materialIds.push(...orderedIds.slice(plannedQuantity));
  }

  if (recipients.length === 0) return { assignments: [], materialIds };

  const preserved = (input.existingAssignments ?? []).filter(
    (assignment) =>
      assignment.status !== 'revoked' &&
      materialIds.includes(assignment.materialId) &&
      recipients.some(
        (recipient) => recipient.userId === assignment.recipientUserId,
      ),
  );
  const assignedMaterialIds = new Set(
    preserved.map((assignment) => assignment.materialId),
  );
  const recipientLoads: Record<string, number> = Object.fromEntries(
    recipients.map((recipient) => [recipient.userId, 0]),
  );
  for (const assignment of preserved) {
    recipientLoads[assignment.recipientUserId] =
      (recipientLoads[assignment.recipientUserId] ?? 0) + 1;
  }

  const assignments = [...preserved];
  for (const materialId of materialIds) {
    if (assignedMaterialIds.has(materialId)) continue;
    const recipient = [...recipients].sort(
      (left, right) =>
        (recipientLoads[left.userId] ?? 0) -
          (recipientLoads[right.userId] ?? 0) ||
        stableText(left.userId, right.userId),
    )[0];
    const material = input.materials.find((item) => item.id === materialId);
    if (!recipient || !material) continue;
    assignments.push({
      id: `oversend:${input.taskId}:${materialId}`,
      materialId,
      recipientUserId: recipient.userId,
      recipientUserName: recipient.userName,
      requirementId: material.requirementId,
      status: 'assigned',
    });
    recipientLoads[recipient.userId] =
      (recipientLoads[recipient.userId] ?? 0) + 1;
  }

  return { assignments, materialIds };
}
