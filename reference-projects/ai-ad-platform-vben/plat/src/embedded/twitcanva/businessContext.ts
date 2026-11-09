import type { TwitCanvaRuntimeOptions } from './runtime';

import { type NodeData, NodeStatus, NodeType } from './types';

const BUSINESS_NODE_TYPES = new Set<NodeType>([
  NodeType.PROJECT,
  NodeType.PRODUCT,
  NodeType.KPI,
  NodeType.REQUIREMENT,
  NodeType.BRAND_GUIDELINE,
  NodeType.REFERENCE,
]);

export function isBusinessContextNode(type: NodeType) {
  return BUSINESS_NODE_TYPES.has(type);
}

export function createBusinessContextNodes(
  runtime: TwitCanvaRuntimeOptions,
): NodeData[] {
  if (!runtime.requirementId) return [];

  const canvasId = runtime.canvasId || 'canvas';
  const projectId = runtime.projectId || '待关联';
  const requirementId = runtime.requirementId;
  const taskId = runtime.taskId || requirementId;

  const definitions: Array<
    Pick<NodeData, 'businessFields' | 'businessSource' | 'title' | 'type'>
  > = [
    {
      businessFields: [
        { label: '项目 ID', value: projectId },
        { label: '数据归属', value: '继承当前项目' },
      ],
      businessSource: 'Project 主数据',
      title: '项目',
      type: NodeType.PROJECT,
    },
    {
      businessFields: [
        { label: '产品', value: '跟随项目产品关联' },
        { label: '知识库', value: '统一产品知识库' },
      ],
      businessSource: 'Product 主数据',
      title: '产品',
      type: NodeType.PRODUCT,
    },
    {
      businessFields: [
        { label: '目标', value: '继承项目主 / 辅 KPI' },
        { label: '用途', value: '作为 AI 生产上下文' },
      ],
      businessSource: '项目 KPI',
      title: 'KPI',
      type: NodeType.KPI,
    },
    {
      businessFields: [
        {
          label: '需求',
          value: runtime.initialTitle || `需求 ${requirementId}`,
        },
        { label: '需求 ID', value: requirementId },
        { label: '任务 ID', value: taskId },
      ],
      businessSource: '素材工单',
      title: '素材工单',
      type: NodeType.REQUIREMENT,
    },
    {
      businessFields: [
        { label: '规范', value: '继承产品品牌规范' },
        { label: '禁止项', value: '由知识库同步' },
      ],
      businessSource: 'CreativeProfile',
      title: '品牌规范',
      type: NodeType.BRAND_GUIDELINE,
    },
    {
      businessFields: [
        { label: '参考素材', value: '由工单附件同步' },
        { label: '状态', value: '等待接口返回资源' },
      ],
      businessSource: 'Requirement Reference',
      title: '参考素材',
      type: NodeType.REFERENCE,
    },
  ];

  return definitions.map((definition, index) => {
    const fields = definition.businessFields ?? [];
    return {
      ...definition,
      aspectRatio: 'Auto',
      id: `${canvasId}-context-${index + 1}`,
      model: '',
      parentIds: [],
      prompt: fields.map(({ label, value }) => `${label}: ${value}`).join('\n'),
      readOnly: true,
      resolution: 'Auto',
      status: NodeStatus.SUCCESS,
      x: 160,
      y: 120 + index * 210,
    } satisfies NodeData;
  });
}
