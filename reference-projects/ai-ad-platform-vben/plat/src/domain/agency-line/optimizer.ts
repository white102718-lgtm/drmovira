import type { AgencyLine } from './types';

export interface OptimizerOption {
  label: string;
  name: string;
  value: string;
}

/** 历史选项只附加到当前编辑记录；分页缺席不能被推断为停用。 */
export function withHistoricalOptimizer(
  options: OptimizerOption[],
  line?: AgencyLine,
): OptimizerOption[] {
  if (!line?.optimizerId) return options;
  const historical = {
    label: `${line.optimizerName || line.optimizerId}${line.optimizerStatus === 0 ? '（已停用）' : ''}`,
    name: line.optimizerName,
    value: line.optimizerId,
  };
  return [
    historical,
    ...options.filter((item) => item.value !== line.optimizerId),
  ];
}

/** 空选择表示清空；选项加载失败时不能悄悄丢失已选择的 ID。 */
export function selectedOptimizer(
  id: string | undefined,
  options: OptimizerOption[],
) {
  if (!id) return { optimizerId: undefined, optimizerName: '' };
  const option = options.find((item) => item.value === id);
  if (!option) throw new Error('投手选项尚未加载，请重试或明确清空选择');
  return { optimizerId: id, optimizerName: option.name };
}
