import type { TaskSourceRelationAdapter } from '../adapter';
import type { TaskSourceRelation } from '../types';

import type { StorageLike } from '#/mock/persistence/versioned-collection';

import {
  readVersionedCollection,
  writeVersionedCollection,
} from '#/mock/persistence/versioned-collection';

export const TASK_SOURCE_RELATIONS_STORAGE_KEY = 'fusion:task-source-relations';

export interface MockTaskSourceRelationAdapterOptions {
  now?: () => string;
  storage?: StorageLike;
}

function cloneRelation(relation: TaskSourceRelation): TaskSourceRelation {
  return { ...relation };
}

/**
 * This bridge exists only in Demo mode. It has no seed data: an explicitly
 * empty collection stays empty and never fabricates production relationships.
 */
export class MockTaskSourceRelationAdapter
  implements TaskSourceRelationAdapter
{
  private readonly now: () => string;
  private readonly storage: StorageLike;

  constructor(options: MockTaskSourceRelationAdapterOptions = {}) {
    this.now = options.now ?? (() => new Date().toISOString());
    this.storage = options.storage ?? window.localStorage;
  }

  listBySourceTask(sourceTaskId: string): TaskSourceRelation[] {
    return this.read()
      .filter((relation) => relation.sourceTaskId === sourceTaskId)
      .map((relation) => cloneRelation(relation));
  }

  save(input: TaskSourceRelation): TaskSourceRelation {
    const relations = this.read();
    const index = relations.findIndex(
      (relation) =>
        relation.sourceTaskId === input.sourceTaskId &&
        relation.materialOrderId === input.materialOrderId,
    );
    const relation: TaskSourceRelation = {
      ...cloneRelation(input),
      createdAt: relations[index]?.createdAt ?? input.createdAt,
      updatedAt: this.now(),
    };
    if (index === -1) relations.unshift(relation);
    else relations[index] = relation;
    writeVersionedCollection(
      this.storage,
      TASK_SOURCE_RELATIONS_STORAGE_KEY,
      relations,
      { now: this.now },
    );
    return cloneRelation(relation);
  }

  private read() {
    return readVersionedCollection<TaskSourceRelation>({
      fallback: [],
      now: this.now,
      storage: this.storage,
      storageKey: TASK_SOURCE_RELATIONS_STORAGE_KEY,
    }).map((relation) => cloneRelation(relation));
  }
}
