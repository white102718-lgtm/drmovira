import { describe, expect, it } from 'vitest';

import {
  buildBalancedProductionSlots,
  buildOversendAssignments,
  buildUniqueDeliveryDistribution,
  moveOrderedItem,
} from './service';

const designers = [
  { userId: 'designer-a', userName: '甲' },
  { userId: 'designer-b', userName: '乙' },
];

describe('material task allocation', () => {
  it('balances the total and every requirement across designers', () => {
    const preview = buildBalancedProductionSlots({
      designers,
      requirements: [
        { id: 'req-1', label: '需求 1', quantity: 2, sortOrder: 1000 },
        { id: 'req-2', label: '需求 2', quantity: 3, sortOrder: 2000 },
        { id: 'req-3', label: '需求 3', quantity: 4, sortOrder: 3000 },
      ],
      taskId: 'task-1',
    });

    expect(preview.slots).toHaveLength(9);
    expect(Object.values(preview.designerLoads).sort()).toEqual([4, 5]);
    expect(preview.maxLoadDifference).toBe(1);

    for (const requirementId of ['req-1', 'req-2', 'req-3']) {
      const counts = designers.map(
        (designer) =>
          preview.slots.filter(
            (slot) =>
              slot.requirementId === requirementId &&
              slot.designerUserId === designer.userId,
          ).length,
      );
      expect(Math.max(...counts) - Math.min(...counts)).toBeLessThanOrEqual(1);
    }
  });

  it('respects the creator selection of each child requirement', () => {
    const preview = buildBalancedProductionSlots({
      designers: [...designers, { userId: 'designer-c', userName: '丙' }],
      requirements: [
        {
          designerUserIds: ['designer-a'],
          id: 'req-a-only',
          label: '需求 A',
          quantity: 3,
          sortOrder: 1000,
        },
        {
          designerUserIds: ['designer-b', 'designer-c'],
          id: 'req-bc',
          label: '需求 B',
          quantity: 5,
          sortOrder: 2000,
        },
      ],
      taskId: 'task-by-requirement',
    });

    expect(
      preview.slots
        .filter((slot) => slot.requirementId === 'req-a-only')
        .map((slot) => slot.designerUserId),
    ).toEqual(['designer-a', 'designer-a', 'designer-a']);
    expect(
      new Set(
        preview.slots
          .filter((slot) => slot.requirementId === 'req-bc')
          .map((slot) => slot.designerUserId),
      ),
    ).toEqual(new Set(['designer-b', 'designer-c']));
  });

  it('preserves locked work and only rebalances remaining slots', () => {
    const preview = buildBalancedProductionSlots({
      designers,
      existingSlots: [
        {
          designerUserId: 'designer-a',
          designerUserName: '甲',
          id: 'locked-slot',
          locked: true,
          requirementId: 'req-1',
          slotNo: 1,
          status: 'delivered',
        },
      ],
      requirements: [
        { id: 'req-1', label: '需求 1', quantity: 3, sortOrder: 1000 },
      ],
      taskId: 'task-1',
    });

    expect(preview.slots.find((slot) => slot.slotNo === 1)).toMatchObject({
      designerUserId: 'designer-a',
      id: 'locked-slot',
      status: 'delivered',
    });
    expect(preview.designerLoads).toEqual({
      'designer-a': 2,
      'designer-b': 1,
    });
  });

  it('blocks duplicate delivery material unless reuse is explicitly enabled', () => {
    const base = {
      executionUnits: [
        { id: 'unit-1', label: '投放位 1' },
        { id: 'unit-2', label: '投放位 2' },
        { id: 'unit-3', label: '投放位 3' },
      ],
      materials: [
        { accepted: true, id: 'mat-1', name: '素材 1', sortOrder: 1000 },
        { accepted: true, id: 'mat-2', name: '素材 2', sortOrder: 2000 },
      ],
      taskId: 'delivery-1',
    };

    const blocked = buildUniqueDeliveryDistribution(base);
    expect(blocked.canConfirm).toBe(false);
    expect(blocked.missingExecutionUnitIds).toEqual(['unit-3']);
    expect(blocked.duplicateMaterialIds).toEqual([]);

    const allowed = buildUniqueDeliveryDistribution({
      ...base,
      allowReuse: true,
    });
    expect(allowed.canConfirm).toBe(true);
    expect(allowed.items[2]).toMatchObject({
      materialId: 'mat-1',
      repeated: true,
    });
  });

  it('shares oversend only among active members in the same project', () => {
    const preview = buildOversendAssignments({
      materials: [
        {
          accepted: true,
          id: 'mat-1',
          name: '素材 1',
          requirementId: 'req-1',
          sortOrder: 1000,
        },
        {
          accepted: true,
          id: 'mat-2',
          name: '素材 2',
          requirementId: 'req-1',
          sortOrder: 2000,
        },
        {
          accepted: true,
          id: 'mat-3',
          name: '素材 3',
          requirementId: 'req-1',
          sortOrder: 3000,
        },
      ],
      projectId: 'project-1',
      recipients: [
        { projectId: 'project-1', userId: 'user-a', userName: 'A' },
        { projectId: 'project-1', userId: 'user-b', userName: 'B' },
        { projectId: 'project-2', userId: 'user-c', userName: 'C' },
      ],
      requirements: [
        { id: 'req-1', label: '需求 1', quantity: 1, sortOrder: 1000 },
      ],
      taskId: 'task-1',
    });

    expect(preview.materialIds).toEqual(['mat-2', 'mat-3']);
    expect(
      preview.assignments.map((assignment) => assignment.recipientUserId),
    ).toEqual(['user-a', 'user-b']);
  });

  it('moves ordered items without crossing the list boundary', () => {
    expect(moveOrderedItem(['a', 'b', 'c'], 'b', -1)).toEqual(['b', 'a', 'c']);
    expect(moveOrderedItem(['a', 'b', 'c'], 'a', -1)).toEqual(['a', 'b', 'c']);
  });
});
