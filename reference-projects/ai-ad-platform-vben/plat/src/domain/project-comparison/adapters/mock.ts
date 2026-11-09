import type { ProjectComparisonAdapter } from '../adapter';
import type {
  ProjectComparisonQuery,
  ProjectComparisonSourceData,
} from '../types';

import { projectComparisonMockData } from '../mock-data';

export interface MockProjectComparisonAdapterOptions {
  delay?: number;
}

function cloneSourceData(
  source: ProjectComparisonSourceData,
): ProjectComparisonSourceData {
  return {
    agencyLines: source.agencyLines.map((line) => ({ ...line })),
    asOf: source.asOf,
    ...(source.creativeDirectionRecords
      ? {
          creativeDirectionRecords: source.creativeDirectionRecords.map(
            (record) => ({ ...record }),
          ),
        }
      : {}),
    ...(source.creativeDirections
      ? {
          creativeDirections: source.creativeDirections.map((direction) => ({
            ...direction,
            materialVersionIds: [...direction.materialVersionIds],
          })),
        }
      : {}),
    records: source.records.map((record) => ({ ...record })),
  };
}

/**
 * P0 deterministic Mock only. It is intentionally not an adapter for the
 * existing advertising dashboard endpoint because that endpoint lacks stable
 * project and agency-line query dimensions.
 */
export class MockProjectComparisonAdapter implements ProjectComparisonAdapter {
  private readonly delay: number;

  constructor(options: MockProjectComparisonAdapterOptions = {}) {
    this.delay = options.delay ?? 180;
  }

  async getSourceData(
    query: ProjectComparisonQuery,
  ): Promise<ProjectComparisonSourceData> {
    const source = projectComparisonMockData.get(query.projectId);
    if (!source) {
      throw new Error('该项目暂未接入环比分析演示数据');
    }
    const allowedLines = new Set(query.agencyLineIds ?? []);
    const filtered =
      allowedLines.size > 0
        ? {
            ...source,
            agencyLines: source.agencyLines.filter((line) =>
              allowedLines.has(line.id),
            ),
            creativeDirectionRecords: source.creativeDirectionRecords?.filter(
              (record) => allowedLines.has(record.agencyLineId),
            ),
            creativeDirections: source.creativeDirections?.filter((direction) =>
              allowedLines.has(direction.agencyLineId),
            ),
            records: source.records.filter((record) =>
              allowedLines.has(record.agencyLineId),
            ),
          }
        : source;
    return this.wait(cloneSourceData(filtered));
  }

  private wait<T>(value: T): Promise<T> {
    if (this.delay <= 0) return Promise.resolve(value);
    return new Promise((resolve) =>
      window.setTimeout(() => resolve(value), this.delay),
    );
  }
}
