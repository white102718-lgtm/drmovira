import type { AdAccountSelectionAdapter } from '../adapter';
import type {
  AdAccountAssignmentStatus,
  AdAccountResourceStatus,
  AdAccountStatus,
  MockAdAccountAssetFacts,
  SelectableAdAccount,
  SelectableAdAccountPlatform,
} from '../types';

export const LEGACY_MEDIA_ACCOUNT_STORAGE_KEY =
  'fusion:media-resource:accounts';
export const LEGACY_MEDIA_ASSIGNMENT_STORAGE_KEY =
  'fusion:media-resource:assignments';

export const LEGACY_PROJECT_ID_ALIASES: Readonly<Record<string, string>> = {
  'project-solar-global': 'project-starfall',
  'project-starfall-sea': 'project-starfall',
};

export const LEGACY_AGENCY_LINE_ID_ALIASES: Readonly<Record<string, string>> = {
  'agency-google-global': 'agency-starfall-google-us',
  'agency-meta-sea': 'agency-starfall-fb-id',
};

export const LEGACY_USER_ID_ALIASES: Readonly<Record<string, string>> = {
  'user-wang-min': 'user-1',
};

interface LegacyMediaAccount {
  accountId?: string;
  agencyLineId?: string;
  assigneeId?: string;
  assigneeName?: string;
  balance?: number;
  businessManagerId?: string;
  businessManagerName?: string;
  currency?: string;
  id?: string;
  name?: string;
  platform?: string;
  platformStatus?: string;
  projectId?: string;
  resourceStatus?: string;
  spendCap?: number;
}

interface LegacyMediaAssignment {
  assigneeId?: string;
  assigneeName?: string;
  mediaAccountId?: string;
  platformAccountId?: string;
  projectId?: string;
  status?: string;
}

const MOCK_ASSET_FACTS: Readonly<Record<string, MockAdAccountAssetFacts>> = {
  'media-account-google-001': {
    authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
    authorizationStatus: 'authorized',
    bindingStatus: 'bound',
    pages: [],
    pixels: [
      { id: 'google-conversion-starfall-global', name: 'Starfall Global 转化' },
    ],
  },
  'media-account-meta-001': {
    authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
    authorizationStatus: 'authorized',
    bindingStatus: 'bound',
    pages: [
      {
        id: 'page-starfall-sea',
        name: 'Starfall Quest',
        ownerId: 'personal-1',
        ownerName: '王投手',
        pictureUrl: 'https://placehold.co/64x64/4338ca/ffffff?text=S',
      },
    ],
    pixels: [{ id: 'pixel-starfall-sea', name: 'Starfall SEA Pixel' }],
  },
  'media-account-tiktok-002': {
    authorizationExpiresAt: '2026-07-31T23:59:59.000Z',
    authorizationStatus: 'expired',
    bindingStatus: 'expired',
    pages: [],
    pixels: [{ id: 'pixel-neon-jp', name: 'Neon JP Pixel' }],
  },
};

const META_001_FACTS: MockAdAccountAssetFacts = {
  authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
  authorizationStatus: 'authorized',
  bindingStatus: 'bound',
  pages: [
    {
      id: 'page-starfall-sea',
      name: 'Starfall Quest',
      ownerId: 'personal-1',
      ownerName: '王投手',
      pictureUrl: 'https://placehold.co/64x64/4338ca/ffffff?text=S',
    },
  ],
  pixels: [{ id: 'pixel-starfall-sea', name: 'Starfall SEA Pixel' }],
};

const GOOGLE_001_FACTS: MockAdAccountAssetFacts = {
  authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
  authorizationStatus: 'authorized',
  bindingStatus: 'bound',
  pages: [],
  pixels: [
    { id: 'google-conversion-starfall-global', name: 'Starfall Global 转化' },
  ],
};

const CANONICAL_FIXTURE: SelectableAdAccount[] = [
  {
    accountStatus: 'active',
    adAccountId: 'act_120240810001',
    agencyLineId: 'agency-starfall-fb-id',
    assigneeId: 'user-1',
    assigneeName: '王敏',
    assignmentStatus: 'active',
    authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
    authorizationStatus: 'authorized',
    balance: 18_240,
    bindingStatus: 'bound',
    businessManager: { id: 'bm-99810001', name: 'Starfall SEA BM' },
    currency: 'USD',
    id: 'media-account-meta-001',
    name: 'Starfall SEA 主投账户',
    pages: META_001_FACTS.pages,
    pixels: META_001_FACTS.pixels,
    platform: 'facebook',
    projectId: 'project-starfall',
    resourceStatus: 'assigned',
    spendCap: 50_000,
  },
  {
    accountStatus: 'active',
    adAccountId: '751-820-4100',
    agencyLineId: 'agency-starfall-google-us',
    assigneeId: 'user-li-yan',
    assigneeName: '李岩',
    assignmentStatus: 'active',
    authorizationExpiresAt: '2027-07-31T23:59:59.000Z',
    authorizationStatus: 'authorized',
    balance: 9850,
    bindingStatus: 'bound',
    businessManager: { id: 'mcc-9001100200', name: 'Global Growth MCC' },
    currency: 'USD',
    id: 'media-account-google-001',
    name: 'Solar Quest 全球账户',
    pages: GOOGLE_001_FACTS.pages,
    pixels: GOOGLE_001_FACTS.pixels,
    platform: 'google',
    projectId: 'project-starfall',
    resourceStatus: 'assigned',
    spendCap: 30_000,
  },
];

export interface MockAdAccountSelectionAdapterOptions {
  assetFacts?: Readonly<Record<string, MockAdAccountAssetFacts>>;
  fixture?: SelectableAdAccount[];
  storage?: Storage;
}

function parseRawArray<T>(storage: Storage, key: string): T[] | undefined {
  const raw = storage.getItem(key);
  if (raw === null) return undefined;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : undefined;
  } catch {
    return undefined;
  }
}

function resolveProjectId(value?: string) {
  if (!value) return '';
  return LEGACY_PROJECT_ID_ALIASES[value] ?? value;
}

function resolveAgencyLineId(value?: string) {
  if (!value) return '';
  return LEGACY_AGENCY_LINE_ID_ALIASES[value] ?? value;
}

function resolveUserId(value?: string) {
  if (!value) return '';
  return LEGACY_USER_ID_ALIASES[value] ?? value;
}

function isPlatform(value?: string): value is SelectableAdAccountPlatform {
  return value === 'facebook' || value === 'google' || value === 'tiktok';
}

function isAccountStatus(value?: string): value is AdAccountStatus {
  return (
    value === 'active' ||
    value === 'closed' ||
    value === 'disabled' ||
    value === 'pending_review' ||
    value === 'restricted' ||
    value === 'unsettled'
  );
}

function isResourceStatus(value?: string): value is AdAccountResourceStatus {
  return (
    value === 'assigned' ||
    value === 'available' ||
    value === 'exception' ||
    value === 'maintenance' ||
    value === 'pending_assignment' ||
    value === 'pending_return' ||
    value === 'retired'
  );
}

function isAssignmentStatus(
  value?: string,
): value is AdAccountAssignmentStatus {
  return (
    value === 'active' || value === 'return_requested' || value === 'returned'
  );
}

function cloneAccount(account: SelectableAdAccount): SelectableAdAccount {
  return {
    ...account,
    businessManager: { ...account.businessManager },
    pages: account.pages.map((page) => ({ ...page })),
    pixels: account.pixels.map((pixel) => ({ ...pixel })),
  };
}

export class MockAdAccountSelectionAdapter
  implements AdAccountSelectionAdapter
{
  private readonly assetFacts: Readonly<
    Record<string, MockAdAccountAssetFacts>
  >;
  private readonly fixture: SelectableAdAccount[];
  private readonly storage?: Storage;

  constructor(options: MockAdAccountSelectionAdapterOptions = {}) {
    this.assetFacts = options.assetFacts ?? MOCK_ASSET_FACTS;
    this.fixture = options.fixture ?? CANONICAL_FIXTURE;
    this.storage =
      options.storage ??
      (typeof window === 'undefined' ? undefined : window.localStorage);
  }

  async listCandidates(): Promise<SelectableAdAccount[]> {
    if (!this.storage) return this.fixture.map((item) => cloneAccount(item));
    const accounts = parseRawArray<LegacyMediaAccount>(
      this.storage,
      LEGACY_MEDIA_ACCOUNT_STORAGE_KEY,
    );
    const assignments = parseRawArray<LegacyMediaAssignment>(
      this.storage,
      LEGACY_MEDIA_ASSIGNMENT_STORAGE_KEY,
    );
    if (!accounts || !assignments) {
      return this.fixture.map((item) => cloneAccount(item));
    }

    const assignmentByInternalId = new Map<string, LegacyMediaAssignment>();
    const assignmentByExternalId = new Map<string, LegacyMediaAssignment>();
    for (const assignment of assignments) {
      if (assignment.mediaAccountId) {
        assignmentByInternalId.set(assignment.mediaAccountId, assignment);
      }
      if (assignment.platformAccountId) {
        assignmentByExternalId.set(assignment.platformAccountId, assignment);
      }
    }
    const externalIdCounts = new Map<string, number>();
    for (const account of accounts) {
      if (!account.accountId) continue;
      externalIdCounts.set(
        account.accountId,
        (externalIdCounts.get(account.accountId) ?? 0) + 1,
      );
    }
    return accounts.flatMap((account) => {
      if (!account.id || !account.accountId || !account.name) return [];
      if (!isPlatform(account.platform)) return [];
      if (!isAccountStatus(account.platformStatus)) return [];
      if (!isResourceStatus(account.resourceStatus)) return [];

      const assignment =
        assignmentByInternalId.get(account.id) ??
        (externalIdCounts.get(account.accountId) === 1
          ? assignmentByExternalId.get(account.accountId)
          : undefined);
      const facts = this.assetFacts[account.id];
      if (!assignment || !facts || !isAssignmentStatus(assignment.status)) {
        return [];
      }

      return [
        {
          accountStatus: account.platformStatus,
          adAccountId: account.accountId,
          agencyLineId: resolveAgencyLineId(account.agencyLineId),
          assigneeId: resolveUserId(
            assignment.assigneeId ?? account.assigneeId,
          ),
          assigneeName: assignment.assigneeName ?? account.assigneeName ?? '',
          assignmentStatus: assignment.status,
          authorizationExpiresAt: facts.authorizationExpiresAt,
          authorizationStatus: facts.authorizationStatus,
          balance: account.balance,
          bindingStatus: facts.bindingStatus,
          businessManager: {
            id: account.businessManagerId,
            name: account.businessManagerName,
          },
          currency: account.currency,
          id: account.id,
          name: account.name,
          pages: facts.pages.map((page) => ({ ...page })),
          pixels: facts.pixels.map((pixel) => ({ ...pixel })),
          platform: account.platform,
          projectId: resolveProjectId(
            assignment.projectId ?? account.projectId,
          ),
          resourceStatus: account.resourceStatus,
          spendCap: account.spendCap,
        },
      ];
    });
  }
}
