import type { MaterialSelectionAdapter } from '../adapter';
import type {
  MaterialSelectionPage,
  MaterialSelectionQuery,
  SelectableMaterial,
} from '../types';

import type { WorkflowMaterialVersion } from '#/store/workflow';

export interface DemoMaterialSelectionAdapterOptions {
  materials: () => readonly WorkflowMaterialVersion[];
}

const DEMO_APPROVED_MATERIALS: readonly SelectableMaterial[] = [
  {
    approvalStatus: 'approved',
    id: 'material-version-3021',
    materialId: 'material-demo-starfall-1',
    name: '首充福利 · 竖版视频 V5',
    projectId: 'project-starfall',
    ratio: '9:16',
    source: 'demo-workflow',
    type: '视频',
  },
  {
    approvalStatus: 'approved',
    id: 'material-version-3018',
    materialId: 'material-demo-starfall-2',
    name: '角色养成 · 方图 V3',
    projectId: 'project-starfall',
    ratio: '1:1',
    source: 'demo-workflow',
    type: '图片',
  },
  {
    approvalStatus: 'approved',
    id: 'material-version-2996',
    materialId: 'material-demo-pixel-1',
    name: '公会战高光 · 横版视频 V2',
    projectId: 'project-pixel',
    ratio: '16:9',
    source: 'demo-workflow',
    type: '视频',
  },
  {
    approvalStatus: 'approved',
    id: 'material-version-2964',
    materialId: 'material-demo-ark-1',
    name: '节日活动 · 竖图 V4',
    projectId: 'project-ark',
    ratio: '4:5',
    source: 'demo-workflow',
    type: '图片',
  },
];

function fromWorkflow(item: WorkflowMaterialVersion): SelectableMaterial {
  return {
    approvalStatus: item.status,
    id: item.id,
    materialId: item.materialId,
    name: `${item.name} · V${item.version}`,
    projectId: item.projectId,
    ratio: item.ratio,
    source: 'demo-workflow',
    type:
      {
        audio: '音频',
        data: '数据',
        image: '图片',
        report: '报告',
        text: '文案',
        video: '视频',
      }[item.kind] ?? item.kind,
  };
}

/** Demo-only projection of the legacy workflow store and scoped fixtures. */
export class DemoMaterialSelectionAdapter implements MaterialSelectionAdapter {
  constructor(private readonly options: DemoMaterialSelectionAdapterOptions) {}

  async listSelectable(
    query: MaterialSelectionQuery,
  ): Promise<MaterialSelectionPage> {
    const projectId = query.projectId.trim();
    if (!projectId) throw new Error('素材选择缺少稳定项目 ID');
    const mapped = this.options.materials().map((item) => fromWorkflow(item));
    const ids = new Set<string>();
    const items = [...mapped, ...DEMO_APPROVED_MATERIALS]
      .filter(
        (item) =>
          item.projectId === projectId && item.approvalStatus === 'approved',
      )
      .filter((item) => {
        if (ids.has(item.id)) return false;
        ids.add(item.id);
        return true;
      })
      .map((item) => ({ ...item }));
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 100;
    const start = (page - 1) * pageSize;
    return { items: items.slice(start, start + pageSize), total: items.length };
  }
}
