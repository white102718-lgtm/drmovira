import type {
  AgencyLineImportError,
  AgencyLineImportField,
  AgencyLineImportParseResult,
  AgencyLineUpsertInput,
} from './types';

import { AgencyLineInputError, normalizeAgencyLineInput } from './validation';

const FIELD_ALIASES = {
  autoRun: ['autoRun', 'auto_run', '自动运行'],
  budgetCap: ['budgetCap', 'budget_cap', '预算上限'],
  budgetFloor: ['budgetFloor', 'budget_floor', '预算下限'],
  cloakUrl: ['cloakUrl', 'cloak_url', '斗篷链接'],
  deliveryUrl: ['deliveryUrl', 'package_url', '投放链接'],
  enabled: ['enabled', '是否启用'],
  id: ['id', '_id'],
  isSend: ['isSend', 'is_send', '是否发送'],
  legacyGamePlatform: ['legacyGamePlatform', 'game_platform'],
  name: ['name', 'agent_line', '代理线'],
  objective: ['objective', '系列目标'],
  optimizerId: ['optimizerId', 'optimizer_id', '投手ID', '投手 ID', '优化师ID'],
  optimizerName: [
    'optimizerName',
    'optimizer',
    '投手',
    '优化师',
    '优化师(关联数据需要)',
  ],
  packageName: ['packageName', 'package_name', '包名'],
  packageType: ['packageType', 'package_type', '包类型'],
  pageId: ['pageId', 'page_id', '主页ID', '主页 ID'],
  pixelId: ['pixelId', 'pixel_id', '像素ID', '像素 ID'],
  pixelName: [
    'pixelName',
    'pixel_name',
    '像素',
    '像素名称',
    '像素名称(创建广告时必填)',
  ],
  platform: ['platform', 'media_platform', '投放平台'],
  projectId: ['projectId', 'project_id', '项目ID'],
  testCode: ['testCode', 'test_code', '测试代码'],
  token: ['token', 'Token', 'TOKEN'],
  type: ['type', '类型'],
} as const satisfies Record<
  Exclude<AgencyLineImportField, 'row'>,
  readonly string[]
>;

type ImportRecord = Record<string, unknown>;

/** 统一预览字段名但不丢弃无效行，保留原值供用户直接修正。 */
export function prepareAgencyLineImportRows(
  sources: ImportRecord[],
): ImportRecord[] {
  return sources.map((record) => {
    const result: ImportRecord = {};
    for (const field of Object.keys(FIELD_ALIASES) as Array<
      keyof typeof FIELD_ALIASES
    >) {
      result[field] = findValue(record, field);
    }
    const projectNameAlias = PROJECT_NAME_ALIASES.find((alias) =>
      Object.prototype.hasOwnProperty.call(record, alias),
    );
    if (projectNameAlias) result.projectName = record[projectNameAlias];
    return result;
  });
}

interface ProjectNameReference {
  id: string;
  name: string;
}

export interface AgencyLineProjectNameResolution {
  errors: AgencyLineImportError[];
  rows: ImportRecord[];
}

const PROJECT_NAME_ALIASES = [
  'projectName',
  'project_name',
  '项目名称',
] as const;

/**
 * 将导入文件中的项目名称解析为稳定 ID，实际关系仍始终使用 ID 建立。
 * 旧模板的 projectId、project_id 和项目ID保持兼容，便于已下载文件平滑过渡。
 */
export function resolveAgencyLineImportProjectNames(
  sources: readonly unknown[],
  projects: readonly ProjectNameReference[],
): AgencyLineProjectNameResolution {
  const errors: AgencyLineImportError[] = [];
  const projectsByName = new Map(
    projects.map((project) => [project.name.trim().toLowerCase(), project]),
  );
  const rows = sources.map((source, index) => {
    if (!source || typeof source !== 'object' || Array.isArray(source)) {
      return source as ImportRecord;
    }
    const record = source as ImportRecord;
    const projectNameAlias = PROJECT_NAME_ALIASES.find((alias) =>
      Object.prototype.hasOwnProperty.call(record, alias),
    );
    if (!projectNameAlias) return record;
    const rawProjectName = record[projectNameAlias];
    if (rawProjectName === undefined || rawProjectName === null) return record;
    const projectName = String(rawProjectName).trim();
    if (!projectName) return { ...record, projectId: '' };
    const project = projectsByName.get(projectName.toLowerCase());
    if (!project) {
      errors.push({
        code: 'invalid_value',
        field: 'projectId',
        message: `项目名称不存在：${projectName}`,
        row: index + 1,
      });
      return record;
    }
    return { ...record, projectId: project.id };
  });
  return { errors, rows };
}

function addError(
  errors: AgencyLineImportError[],
  row: number,
  field: AgencyLineImportField,
  message: string,
  code: AgencyLineImportError['code'] = 'invalid_type',
) {
  errors.push({ code, field, message, row });
}

function findValue(record: ImportRecord, field: keyof typeof FIELD_ALIASES) {
  for (const alias of FIELD_ALIASES[field]) {
    if (Object.prototype.hasOwnProperty.call(record, alias)) {
      return record[alias];
    }
  }
  return undefined;
}

function readText(
  record: ImportRecord,
  field: keyof typeof FIELD_ALIASES,
  row: number,
  errors: AgencyLineImportError[],
) {
  const value = findValue(record, field);
  if (value === undefined || value === null) return '';
  // ID 不允许从 Excel 已舍入的长数字或科学计数法文本猜测恢复。
  if (['pixelName', 'pageId', 'optimizerId'].includes(field)) {
    const label =
      field === 'pixelName'
        ? '像素 ID'
        : field === 'pageId'
          ? '主页 ID'
          : '投手 ID';
    if (
      typeof value === 'number' &&
      (!Number.isSafeInteger(value) || Math.abs(value) >= 1e15)
    ) {
      addError(
        errors,
        row,
        field,
        `${label} 被保存为长数字，可能已丢失精度，请从原始来源复制完整 ID 并以文本填写`,
        'invalid_value',
      );
    } else if (
      typeof value === 'string' &&
      /^[+-]?\d+(?:\.\d+)?e[+-]?\d+$/i.test(value.trim())
    ) {
      addError(
        errors,
        row,
        field,
        `${label} 为科学计数法，请从原始来源复制完整 ID 并以文本填写`,
        'invalid_value',
      );
    }
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value).trim();
  }
  addError(errors, row, field, `${field} 必须是文本`);
  return '';
}

function readOptionalText(
  record: ImportRecord,
  field: keyof typeof FIELD_ALIASES,
  row: number,
  errors: AgencyLineImportError[],
) {
  return readText(record, field, row, errors) || undefined;
}

function readBoolean(
  record: ImportRecord,
  field: 'autoRun' | 'enabled' | 'isSend',
  fallback: boolean,
  row: number,
  errors: AgencyLineImportError[],
) {
  const value = findValue(record, field);
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  if (value === 1 || value === '1') return true;
  if (value === 0 || value === '0') return false;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', 'yes', '启用', '是'].includes(normalized)) return true;
    if (['false', 'no', '否', '禁用'].includes(normalized)) return false;
  }
  addError(errors, row, field, `${field} 必须是布尔值`);
  return fallback;
}

function readOptionalNumber(
  record: ImportRecord,
  field: 'budgetCap' | 'budgetFloor',
  row: number,
  errors: AgencyLineImportError[],
) {
  const value = findValue(record, field);
  if (value === undefined || value === null || value === '') return undefined;
  const number =
    typeof value === 'number' ? value : Number(String(value).trim());
  if (Number.isFinite(number)) return number;
  addError(errors, row, field, `${field} 必须是有效数字`);
  return undefined;
}

function parseRow(
  source: unknown,
  row: number,
  errors: AgencyLineImportError[],
): AgencyLineUpsertInput | undefined {
  if (!source || typeof source !== 'object' || Array.isArray(source)) {
    addError(errors, row, 'row', '导入行必须是字段对象');
    return undefined;
  }
  const record = source as ImportRecord;
  const input: AgencyLineUpsertInput = {
    autoRun: readBoolean(record, 'autoRun', false, row, errors),
    budgetCap: readOptionalNumber(record, 'budgetCap', row, errors),
    budgetFloor: readOptionalNumber(record, 'budgetFloor', row, errors),
    cloakUrl: readText(record, 'cloakUrl', row, errors),
    deliveryUrl: readText(record, 'deliveryUrl', row, errors),
    enabled: readBoolean(record, 'enabled', true, row, errors),
    id: readOptionalText(record, 'id', row, errors),
    isSend: readBoolean(record, 'isSend', false, row, errors),
    legacyGamePlatform: readOptionalText(
      record,
      'legacyGamePlatform',
      row,
      errors,
    ),
    name: readText(record, 'name', row, errors),
    objective: readText(record, 'objective', row, errors),
    optimizerId: readOptionalText(record, 'optimizerId', row, errors),
    optimizerName: readText(record, 'optimizerName', row, errors),
    packageName: readText(record, 'packageName', row, errors),
    packageType: readText(record, 'packageType', row, errors),
    pageId: readText(record, 'pageId', row, errors),
    pixelId: readText(record, 'pixelId', row, errors),
    pixelName: readText(record, 'pixelName', row, errors),
    platform: readText(record, 'platform', row, errors),
    projectId: readOptionalText(record, 'projectId', row, errors),
    testCode: readText(record, 'testCode', row, errors),
    token: readText(record, 'token', row, errors),
    type: readText(record, 'type', row, errors),
  };

  const requiredFields: Array<
    [field: 'name' | 'optimizerName' | 'platform', message: string]
  > = [
    ['name', '代理线名称不能为空'],
    ['platform', '投放平台不能为空'],
  ];
  for (const [field, message] of requiredFields) {
    if (!input[field].trim()) {
      addError(errors, row, field, message, 'required');
    }
  }
  if (errors.some((error) => error.row === row)) {
    return undefined;
  }
  let normalized: AgencyLineUpsertInput | undefined;
  try {
    normalized = normalizeAgencyLineInput(input);
  } catch (error) {
    if (error instanceof AgencyLineInputError) {
      addError(errors, row, error.field, error.message, error.code);
    } else {
      addError(errors, row, 'row', '导入行校验失败', 'invalid_value');
    }
  }
  return normalized;
}

/**
 * Accepts canonical keys, legacy snake_case keys, or the explicit Chinese
 * template headers. It never guesses platform/project relationships.
 */
export function parseAgencyLineImportRows(
  sources: readonly unknown[],
): AgencyLineImportParseResult {
  const errors: AgencyLineImportError[] = [];
  const rows = sources.flatMap((source, index) => {
    const row = index + 1;
    const input = parseRow(source, row, errors);
    return input ? [{ input, row }] : [];
  });

  return { errors, rows, total: sources.length };
}
