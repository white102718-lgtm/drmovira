import type {
  AgencyLineImportErrorCode,
  AgencyLineImportField,
  AgencyLineUpsertInput,
} from './types';

export class AgencyLineInputError extends Error {
  constructor(
    message: string,
    readonly field: AgencyLineImportField,
    readonly code: AgencyLineImportErrorCode = 'invalid_value',
  ) {
    super(message);
    this.name = 'AgencyLineInputError';
  }
}

export function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

export function normalizeAgencyLineInput(
  input: AgencyLineUpsertInput,
): AgencyLineUpsertInput {
  if (!input.name.trim()) {
    throw new AgencyLineInputError('代理线名称不能为空', 'name', 'required');
  }
  if (!input.platform.trim()) {
    throw new AgencyLineInputError('投放平台不能为空', 'platform', 'required');
  }
  const platform = input.platform.trim().toLowerCase();
  const optimizerId = input.optimizerId?.trim();
  if (!optimizerId && input.optimizerName?.trim()) {
    throw new AgencyLineInputError('投手姓名不能缺少用户 ID', 'optimizerId');
  }
  if (!['facebook', 'google', 'tiktok', 'kwai'].includes(platform)) {
    throw new AgencyLineInputError(
      '投放平台仅支持 facebook、google、tiktok 或 kwai',
      'platform',
    );
  }
  if (input.deliveryUrl.trim() && !isHttpUrl(input.deliveryUrl.trim())) {
    throw new AgencyLineInputError(
      '投放链接必须是有效的 http(s) 地址',
      'deliveryUrl',
    );
  }
  if (input.cloakUrl.trim() && !isHttpUrl(input.cloakUrl.trim())) {
    throw new AgencyLineInputError(
      '斗篷链接必须是有效的 http(s) 地址',
      'cloakUrl',
    );
  }
  if (
    input.budgetCap !== undefined &&
    (!Number.isFinite(input.budgetCap) || input.budgetCap < 0)
  ) {
    throw new AgencyLineInputError('预算上限不能小于 0', 'budgetCap');
  }
  if (
    input.budgetFloor !== undefined &&
    (!Number.isFinite(input.budgetFloor) || input.budgetFloor < 0)
  ) {
    throw new AgencyLineInputError('预算下限不能小于 0', 'budgetFloor');
  }
  if (
    input.budgetCap !== undefined &&
    input.budgetFloor !== undefined &&
    input.budgetFloor > input.budgetCap
  ) {
    throw new AgencyLineInputError('预算下限不能大于预算上限', 'budgetFloor');
  }

  return {
    ...input,
    cloakUrl: input.cloakUrl.trim(),
    deliveryUrl: input.deliveryUrl.trim(),
    id: input.id?.trim() || undefined,
    legacyGamePlatform: input.legacyGamePlatform?.trim() || undefined,
    name: input.name.trim(),
    objective: input.objective.trim(),
    optimizerId: input.optimizerId?.trim() || undefined,
    optimizerName: input.optimizerName?.trim() ?? '',
    packageName: input.packageName.trim(),
    packageType: input.packageType.trim(),
    pageId: input.pageId.trim(),
    pixelId: input.pixelId.trim(),
    pixelName: input.pixelName.trim(),
    platform,
    projectId: input.projectId?.trim() || undefined,
    testCode: input.testCode.trim(),
    token: input.token.trim(),
    type: input.type.trim(),
  };
}
