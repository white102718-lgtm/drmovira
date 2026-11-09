export interface MaterialAllocationRequirement {
  /** @deprecated Legacy campaign references; creative planners are people. */
  creativeReferenceIds?: string[];
  /** Stable creative-planner user IDs selected for this child requirement. */
  creativePlannerUserIds?: string[];
  /** Stable creator IDs allowed to work on this child requirement. */
  designerUserIds?: string[];
  id: string;
  label: string;
  /** Stable material references selected for this child requirement. */
  materialReferenceIds?: string[];
  quantity: number;
  sortOrder: number;
}

export interface MaterialAllocationUser {
  active?: boolean;
  projectId?: string;
  roles?: string[];
  userId: string;
  userName: string;
}

export interface MaterialRequirementAssignmentEntry {
  /** @deprecated Legacy campaign references retained for stored-data compatibility. */
  creativeReferenceIds?: string[];
  creativePlannerUserIds?: string[];
  designerUserIds: string[];
  id: string;
  materialReferenceIds: string[];
  remark?: string;
  requirementId: string;
}

export type MaterialProductionSlotStatus =
  | 'accepted'
  | 'cancelled'
  | 'delivered'
  | 'in_progress'
  | 'planned';

export interface MaterialProductionSlot {
  designerUserId: string;
  designerUserName: string;
  id: string;
  locked: boolean;
  overPlan?: boolean;
  requirementId: string;
  slotNo: number;
  status: MaterialProductionSlotStatus;
}

export interface MaterialAllocationAsset {
  accepted: boolean;
  id: string;
  name: string;
  requirementId?: string;
  sortOrder: number;
}

export interface MaterialOversendAssignment {
  id: string;
  materialId: string;
  recipientUserId: string;
  recipientUserName: string;
  requirementId?: string;
  status: 'assigned' | 'revoked' | 'used';
}

export interface MaterialTaskAllocationState {
  /** Editable assignment rows retained so notes and split assignments can be reopened. */
  assignmentEntries?: MaterialRequirementAssignmentEntry[];
  confirmedAt?: string;
  materialOrderIds: string[];
  oversendAssignments: MaterialOversendAssignment[];
  productionSlots: MaterialProductionSlot[];
  requirements: MaterialAllocationRequirement[];
  version: number;
}

export interface DeliveryExecutionUnit {
  accountId?: string;
  adsetId?: string;
  id: string;
  label: string;
  recipientUserId?: string;
  recipientUserName?: string;
}

export interface DeliveryMaterialDistributionItem {
  executionUnitId: string;
  id: string;
  materialId: string;
  materialName: string;
  repeated: boolean;
  status: 'preview' | 'reserved' | 'used';
}

export interface DeliveryMaterialAllocationState {
  allowReuse: boolean;
  confirmedAt?: string;
  items: DeliveryMaterialDistributionItem[];
  version: number;
}

export interface ProductionAllocationPreview {
  designerLoads: Record<string, number>;
  maxLoadDifference: number;
  slots: MaterialProductionSlot[];
}

export interface DeliveryDistributionPreview {
  canConfirm: boolean;
  duplicateMaterialIds: string[];
  items: DeliveryMaterialDistributionItem[];
  missingExecutionUnitIds: string[];
}

export interface OversendPreview {
  assignments: MaterialOversendAssignment[];
  materialIds: string[];
}
