import type { MaterialSelectionAdapter } from './adapter';
import type {
  MaterialSelectionPage,
  MaterialSelectionQuery,
  SelectableMaterial,
} from './types';

function clone(item: SelectableMaterial): SelectableMaterial {
  return { ...item };
}

function normalizeQuery(query: MaterialSelectionQuery): MaterialSelectionQuery {
  const projectId = query.projectId.trim();
  if (!projectId) throw new Error('素材选择缺少稳定项目 ID');
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 100;
  if (!Number.isInteger(page) || page < 1) throw new Error('素材页码无效');
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 200) {
    throw new Error('素材分页大小必须在 1 到 200 之间');
  }
  return { page, pageSize, projectId };
}

/**
 * Read-only material eligibility facade. `materialIds` in the legacy ad draft
 * keep their original meaning; this service only decides whether a stable ID
 * may be selected in the current project context.
 */
export class MaterialSelectionService {
  constructor(private readonly adapter: MaterialSelectionAdapter) {}

  async findSelectable(
    query: MaterialSelectionQuery,
    materialVersionId: string,
  ): Promise<SelectableMaterial | undefined> {
    const id = materialVersionId.trim();
    if (!id) return undefined;
    const result = await this.listSelectable({
      ...query,
      page: 1,
      pageSize: 200,
    });
    const item = result.items.find((candidate) => candidate.id === id);
    return item ? clone(item) : undefined;
  }

  async listSelectable(
    query: MaterialSelectionQuery,
  ): Promise<MaterialSelectionPage> {
    const result = await this.adapter.listSelectable(normalizeQuery(query));
    const items = result.items
      .filter((item) => item.approvalStatus === 'approved')
      .map((item) => clone(item));
    return { items, total: result.total };
  }
}
