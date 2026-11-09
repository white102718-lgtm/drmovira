import type { DynamicFormField } from '#/api/asset-flow';

export const DEFAULT_SELECT_PLACEHOLDER = '请选择';

/** 创建动态表单字段的初始值，确保下拉空值不会遮挡 placeholder。 */
export function createDynamicFieldInitialValue(
  field: DynamicFormField,
): number | string | string[] | undefined {
  if (field.defaultValue !== undefined) {
    return Array.isArray(field.defaultValue)
      ? [...field.defaultValue]
      : field.defaultValue;
  }
  if (field.type === 'number') {
    return field.required ? (field.minValue ?? 1) : undefined;
  }
  if (['date-range', 'multi-select', 'pixel-selector'].includes(field.type))
    return [];
  if (field.type === 'select') return undefined;
  return '';
}

/** 返回审批动态表单字段在申请页面使用的输入提示。 */
export function resolveDynamicFieldPlaceholder(
  field: Pick<DynamicFormField, 'placeholder' | 'type'>,
): string | undefined {
  const configuredPlaceholder = field.placeholder?.trim();
  if (configuredPlaceholder) return configuredPlaceholder;

  return ['multi-select', 'pixel-selector', 'select'].includes(field.type)
    ? DEFAULT_SELECT_PLACEHOLDER
    : undefined;
}
