import type { AdAccountSelectionAdapter } from './adapter';
import type {
  AdAccountSelectionQuery,
  AdAccountSelectionResult,
  SelectableAdAccount,
} from './types';

function isNotExpired(account: SelectableAdAccount, now: Date) {
  if (!account.authorizationExpiresAt) return true;
  const expiresAt = Date.parse(account.authorizationExpiresAt);
  return Number.isFinite(expiresAt) && expiresAt > now.getTime();
}

function isBindingUsable(account: SelectableAdAccount) {
  // Expiring bindings are still active until their expiry boundary; expired
  // and unbound accounts must never enter ad creation.
  return (
    account.bindingStatus === 'bound' || account.bindingStatus === 'expiring'
  );
}

export interface AdAccountSelectionServiceOptions {
  now?: () => Date;
}

export class AdAccountSelectionService {
  private readonly now: () => Date;

  constructor(
    private readonly adapter: AdAccountSelectionAdapter,
    options: AdAccountSelectionServiceOptions = {},
  ) {
    this.now = options.now ?? (() => new Date());
  }

  async findSelectable(
    query: AdAccountSelectionQuery,
    adAccountId: string,
  ): Promise<SelectableAdAccount | undefined> {
    const candidates = await this.adapter.listCandidates({
      ...query,
      accountIds: [adAccountId],
      keyword: undefined,
      page: undefined,
      pageSize: undefined,
    });
    return this.filterEligible(candidates, {
      ...query,
      keyword: undefined,
    }).find((account) => account.adAccountId === adAccountId);
  }

  async list(
    query: AdAccountSelectionQuery,
  ): Promise<AdAccountSelectionResult> {
    const candidates = await this.adapter.listCandidates(query);
    const eligible = this.filterEligible(candidates, query);
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.min(100, Math.max(1, query.pageSize ?? 20));
    const offset = (page - 1) * pageSize;

    return {
      items: eligible.slice(offset, offset + pageSize),
      page,
      pageSize,
      total: eligible.length,
    };
  }

  private filterEligible(
    candidates: SelectableAdAccount[],
    query: AdAccountSelectionQuery,
  ) {
    const keyword = query.keyword?.trim().toLowerCase();
    const accountIds = query.accountIds
      ?.map((value) => value.trim().toLowerCase())
      .filter(Boolean);
    const accountNames = query.accountNames
      ?.map((value) => value.trim().toLowerCase())
      .filter(Boolean);
    const pixelName = query.pixelName?.trim().toLowerCase();
    const now = this.now();

    return candidates.filter((account) => {
      const matchesStableScope =
        account.projectId === query.projectId &&
        account.platform === query.platform &&
        (!query.agencyLineId || account.agencyLineId === query.agencyLineId) &&
        // userName is display/legacy metadata only and must never authorize.
        // Omitting userId is an explicit all-scope call (for example, admin).
        (!query.userId || account.assigneeId === query.userId);
      const isUsable =
        account.assignmentStatus === 'active' &&
        account.accountStatus === 'active' &&
        account.resourceStatus === 'assigned' &&
        account.authorizationStatus === 'authorized' &&
        isBindingUsable(account) &&
        isNotExpired(account, now);
      const matchesKeyword =
        !keyword ||
        [
          account.name,
          account.adAccountId,
          account.assigneeName,
          account.businessManager.name,
        ].some((value) => value?.toLowerCase().includes(keyword));
      const matchesAccountIds =
        !accountIds?.length ||
        accountIds.some((value) =>
          account.adAccountId.toLowerCase().includes(value),
        );
      const matchesAccountNames =
        !accountNames?.length ||
        accountNames.some((value) =>
          account.name.toLowerCase().includes(value),
        );
      const matchesPixel =
        !pixelName ||
        account.pixels.some((pixel) =>
          pixel.name.toLowerCase().includes(pixelName),
        );

      return (
        matchesStableScope &&
        isUsable &&
        matchesKeyword &&
        matchesAccountIds &&
        matchesAccountNames &&
        matchesPixel
      );
    });
  }
}
