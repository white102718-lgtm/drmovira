import type {
  AdAccountSelectionQuery,
  SelectableAdAccount,
  SelectableAdAccountPlatform,
} from './types';

export const LEGACY_PROJECT_ID_BY_NAME: Readonly<Record<string, string>> = {
  'Starfall 全球增长': 'project-starfall',
};

export const LEGACY_AGENCY_LINE: Readonly<
  Record<string, { id: string; platform: SelectableAdAccountPlatform }>
> = {
  'Starfall-FB-ID': {
    id: 'agency-starfall-fb-id',
    platform: 'facebook',
  },
  'Starfall-Google-US': {
    id: 'agency-starfall-google-us',
    platform: 'google',
  },
};

export interface LegacyAdAccountTaskContext {
  agencyLineId?: string;
  platform?: SelectableAdAccountPlatform;
  projectId?: string;
  projectName?: string;
  taskName?: string;
}

export function resolveLegacyAdAccountQuery(
  task: LegacyAdAccountTaskContext,
  overrides: Partial<AdAccountSelectionQuery> = {},
): AdAccountSelectionQuery | undefined {
  const legacyLine = task.taskName
    ? LEGACY_AGENCY_LINE[task.taskName]
    : undefined;
  const projectId =
    task.projectId ??
    (task.projectName
      ? LEGACY_PROJECT_ID_BY_NAME[task.projectName]
      : undefined);
  const agencyLineId = task.agencyLineId ?? legacyLine?.id;
  const platform = overrides.platform ?? task.platform ?? legacyLine?.platform;

  if (!projectId || !agencyLineId || !platform) return undefined;

  return {
    accountIds: overrides.accountIds,
    accountNames: overrides.accountNames,
    agencyLineId,
    keyword: overrides.keyword,
    page: overrides.page,
    pageSize: overrides.pageSize,
    platform,
    pixelName: overrides.pixelName,
    projectId,
    userId: overrides.userId,
  };
}

export function toLegacyAdvertiserAccount(account: SelectableAdAccount) {
  const pageOwners = new Map<
    string,
    { id: string; name: string; person_id: string; picture: string }[]
  >();

  const ownedPages = account.pages.filter(
    (page) => page.ownerId && page.ownerName,
  );
  for (const page of ownedPages) {
    const ownerName = page.ownerName as string;
    const ownerId = page.ownerId as string;
    const ownerPages = pageOwners.get(ownerName) ?? [];
    ownerPages.push({
      id: page.id,
      name: page.name,
      person_id: ownerId,
      picture: page.pictureUrl ?? '',
    });
    pageOwners.set(ownerName, ownerPages);
  }

  const defaultPage = ownedPages[0];
  return {
    account_status: account.accountStatus,
    ad_account_id: account.adAccountId,
    ad_account_name: account.name,
    agency_line_id: account.agencyLineId,
    assigned_page_id: defaultPage?.id,
    assigned_page_name: defaultPage?.name,
    assigned_page_picture: defaultPage?.pictureUrl ?? '',
    assignment_status: account.assignmentStatus,
    authorization_status: account.authorizationStatus,
    balance: account.balance ?? 0,
    binding_status: account.bindingStatus,
    bm_name: account.businessManager.name ?? '-',
    currency: account.currency,
    inventory_account_id: account.id,
    person_and_page: Object.fromEntries(pageOwners),
    pixels: account.pixels.map((pixel) => ({
      id: pixel.id,
      name: pixel.name,
    })),
    platform: account.platform,
    project_id: account.projectId,
    resource_status: account.resourceStatus,
    spend_cap: account.spendCap ?? 0,
    status: '活跃',
    usage_status: '已分配·已绑定',
  };
}
