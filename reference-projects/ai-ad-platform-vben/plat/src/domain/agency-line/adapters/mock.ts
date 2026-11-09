import type { AgencyLineAdapter } from '../adapter';
import type {
  AgencyLine,
  AgencyLineCreateCommand,
  AgencyLineDeliveryUrlHistory,
  AgencyLineListQuery,
  AgencyLineListResult,
  AgencyLineOption,
  AgencyLineUpsertInput,
} from '../types';

import type { StorageLike } from '#/mock/persistence/versioned-collection';

import {
  readVersionedCollection,
  writeVersionedCollection,
} from '#/mock/persistence/versioned-collection';

export const AGENCY_LINE_STORAGE_KEY = 'fusion:demo-agency-lines';

export const demoAgencyLines: ReadonlyArray<Readonly<AgencyLine>> = [
  {
    autoRun: true,
    budgetCap: 12_000,
    budgetFloor: 500,
    cloakUrl: '',
    createdAt: '2026-08-13T00:00:00.000Z',
    deliveryUrl: 'https://play.example.com/starfall/android',
    enabled: true,
    id: 'agency-starfall-fb-id',
    isSend: true,
    legacyGamePlatform: 'Starfall 全球增长',
    name: 'Starfall-FB-ID',
    objective: 'OUTCOME_SALES',
    optimizerId: 'user-optimizer-zhao',
    optimizerName: '赵优化',
    packageName: 'com.northstar.starfall',
    packageType: 'Android',
    pageId: 'page-starfall-sea',
    pixelId: '',
    pixelName: 'Starfall SEA Pixel',
    platform: 'facebook',
    projectId: 'project-starfall',
    testCode: '',
    token: '',
    type: '',
    updatedAt: '2026-08-13T00:00:00.000Z',
  },
  {
    autoRun: true,
    budgetCap: 15_000,
    budgetFloor: 800,
    cloakUrl: '',
    createdAt: '2026-08-13T00:00:00.000Z',
    deliveryUrl: 'https://play.example.com/starfall/android',
    enabled: true,
    id: 'agency-starfall-google-us',
    isSend: true,
    legacyGamePlatform: 'Starfall 全球增长',
    name: 'Starfall-Google-US',
    objective: 'APP_CAMPAIGN',
    optimizerId: 'user-optimizer-lin',
    optimizerName: '林优化',
    packageName: 'com.northstar.starfall',
    packageType: 'Android',
    pageId: '',
    pixelId: '',
    pixelName: 'Starfall Global 转化',
    platform: 'google',
    projectId: 'project-starfall',
    testCode: '',
    token: '',
    type: '',
    updatedAt: '2026-08-13T00:00:00.000Z',
  },
  {
    autoRun: false,
    budgetCap: 420_000,
    budgetFloor: 20_000,
    cloakUrl: '',
    createdAt: '2026-08-13T00:00:00.000Z',
    deliveryUrl: 'https://apps.example.com/pixel-quest',
    enabled: true,
    id: 'agency-orbit-tiktok-sea',
    isSend: false,
    legacyGamePlatform: 'Orbit 海外发行',
    name: 'Orbit-TikTok-SEA',
    objective: 'APP_PROMOTION',
    optimizerId: 'user-optimizer-wang',
    optimizerName: '王投手',
    packageName: 'com.lighthouse.pixelquest',
    packageType: 'iOS',
    pageId: '',
    pixelId: '',
    pixelName: 'Pixel Quest CompletePayment',
    platform: 'tiktok',
    projectId: 'project-pixel',
    testCode: '',
    token: '',
    type: '',
    updatedAt: '2026-08-13T00:00:00.000Z',
  },
  {
    autoRun: false,
    budgetCap: 3000,
    budgetFloor: 100,
    cloakUrl: '',
    createdAt: '2026-08-13T00:00:00.000Z',
    deliveryUrl: 'https://play.example.com/mp012',
    enabled: true,
    id: 'agency-mp012-fb',
    isSend: false,
    legacyGamePlatform: 'Starfall 全球增长',
    name: 'MP012-FB',
    objective: 'OUTCOME_SALES',
    optimizerId: 'user-optimizer-chen',
    optimizerName: '陈航',
    packageName: 'com.northstar.mp012',
    packageType: 'Android',
    pageId: 'page-starfall-sea',
    pixelId: '',
    pixelName: 'Starfall SEA Pixel',
    platform: 'facebook',
    projectId: 'project-starfall',
    testCode: '',
    token: '',
    type: '',
    updatedAt: '2026-08-13T00:00:00.000Z',
  },
];

export interface MockAgencyLineAdapterOptions {
  delay?: number;
  id?: () => string;
  now?: () => string;
  storage?: StorageLike;
}

function clone(line: Readonly<AgencyLine>): AgencyLine {
  return { ...line };
}

function normalizeStoredLine(line: AgencyLine): AgencyLine {
  return {
    autoRun: line.autoRun ?? false,
    budgetCap: line.budgetCap,
    budgetFloor: line.budgetFloor,
    cloakUrl: line.cloakUrl ?? '',
    createdAt: line.createdAt ?? line.updatedAt ?? '',
    deliveryUrl: line.deliveryUrl ?? '',
    enabled: line.enabled ?? false,
    id: line.id,
    isSend: line.isSend ?? false,
    legacyGamePlatform: line.legacyGamePlatform,
    name: line.name,
    objective: line.objective ?? '',
    optimizerId: line.optimizerId,
    optimizerName: line.optimizerName ?? '',
    packageName: line.packageName ?? '',
    packageType: line.packageType ?? '',
    pageId: line.pageId ?? '',
    pixelId: line.pixelId ?? '',
    pixelName: line.pixelName ?? '',
    platform: line.platform,
    projectId: line.projectId,
    testCode: line.testCode ?? '',
    // 演示模式也不从 localStorage 恢复敏感 Token。
    token: '',
    type: line.type ?? '',
    updatedAt: line.updatedAt ?? '',
  };
}

export class MockAgencyLineAdapter implements AgencyLineAdapter {
  private readonly createdByRequestId = new Map<
    string,
    { fingerprint: string; line: AgencyLine }
  >();
  private readonly delay: number;
  private readonly generateId: () => string;
  private hydrated = false;
  private readonly histories = new Map<string, AgencyLineDeliveryUrlHistory[]>();
  private readonly now: () => string;
  private records: AgencyLine[] = [];
  private readonly storage: StorageLike;

  constructor(options: MockAgencyLineAdapterOptions = {}) {
    this.delay = options.delay ?? 180;
    this.generateId = options.id ?? (() => Date.now().toString(36));
    this.now = options.now ?? (() => new Date().toISOString());
    this.storage = options.storage ?? window.localStorage;
  }

  async create(command: AgencyLineCreateCommand): Promise<AgencyLine> {
    const fingerprint = JSON.stringify(command.input);
    const existing = this.createdByRequestId.get(command.requestId);
    if (existing) {
      if (existing.fingerprint !== fingerprint) {
        throw new Error('同一创建请求 ID 不能用于不同代理线数据');
      }
      return clone(existing.line);
    }

    const line = await this.save(command.input);
    this.createdByRequestId.set(command.requestId, {
      fingerprint,
      line: clone(line),
    });
    return line;
  }

  async get(id: string): Promise<AgencyLine> {
    this.hydrate();
    const line = this.records.find((item) => item.id === id);
    if (!line) throw new Error('代理线不存在或已被删除');
    return this.wait(clone(line));
  }

  async getDeliveryUrlHistory(
    id: string,
  ): Promise<AgencyLineDeliveryUrlHistory[]> {
    this.hydrate();
    if (!this.records.some((line) => line.id === id)) {
      throw new Error('代理线不存在或已被删除');
    }
    return this.wait([...(this.histories.get(id) ?? [])]);
  }

  async list(query: AgencyLineListQuery = {}): Promise<AgencyLineListResult> {
    this.hydrate();
    const keywords = [
      ...new Set(
        (query.keyword ?? '')
          .split(/\r?\n/u)
          .map((value) => value.trim().toLowerCase())
          .filter(Boolean),
      ),
    ];
    const lineName = query.lineName?.trim().toLowerCase();
    const items = this.records.filter((line) => {
      const matchesKeyword =
        keywords.length === 0 ||
        keywords.some((keyword) =>
          [
            line.name,
            line.type,
            line.deliveryUrl,
            line.pixelName,
            line.pixelId,
            line.testCode,
            line.cloakUrl,
            line.optimizerName,
          ].some((value) => value.toLowerCase().includes(keyword)),
        );
      const matchesLegacyPlatform =
        !query.legacyGamePlatform ||
        line.legacyGamePlatform === query.legacyGamePlatform;
      const matchesPlatform =
        !query.platform || line.platform === query.platform.toLowerCase();
      const matchesProject =
        !query.projectId || line.projectId === query.projectId;
      const matchesOptimizer =
        !query.optimizerId || line.optimizerId === query.optimizerId;
      return (
        (!lineName || line.name.toLowerCase().includes(lineName)) &&
        matchesKeyword &&
        matchesLegacyPlatform &&
        matchesPlatform &&
        matchesProject &&
        matchesOptimizer
      );
    });
    items.sort(
      (left, right) =>
        right.createdAt.localeCompare(left.createdAt) ||
        right.id.localeCompare(left.id),
    );
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 20);

    return this.wait({
      items: items
        .slice((page - 1) * pageSize, page * pageSize)
        .map((line) => clone(line)),
      page,
      pageSize,
      total: items.length,
    });
  }

  async listOptions(
    query: AgencyLineListQuery = {},
  ): Promise<AgencyLineOption[]> {
    const result = await this.list({ ...query, page: 1, pageSize: 10_000 });
    return result.items.map(
      ({
        enabled,
        id,
        legacyGamePlatform,
        name,
        objective,
        pageId,
        pixelName,
        platform,
        projectId,
      }) => ({
        enabled,
        id,
        legacyGamePlatform,
        name,
        objective,
        pageId,
        pixelName,
        platform,
        projectId,
      }),
    );
  }

  async remove(id: string): Promise<void> {
    this.hydrate();
    const index = this.records.findIndex((line) => line.id === id);
    if (index === -1) throw new Error('代理线不存在或已被删除');
    this.records.splice(index, 1);
    this.persist();
    await this.wait(undefined);
  }

  async save(input: AgencyLineUpsertInput): Promise<AgencyLine> {
    this.hydrate();
    const now = this.now();
    const current = input.id
      ? this.records.find((line) => line.id === input.id)
      : undefined;
    const saved: AgencyLine = {
      ...input,
      createdAt: current?.createdAt ?? now,
      id: current?.id ?? input.id ?? `agency-${this.generateId()}`,
      updatedAt: now,
    };

    if (!current || current.deliveryUrl !== saved.deliveryUrl) {
      const history = this.histories.get(saved.id) ?? [];
      if (saved.deliveryUrl || current) {
        history.unshift({
          agencyLineId: saved.id,
          changedAt: now,
          changedByName: '当前用户',
          deliveryUrl: saved.deliveryUrl,
          id: `${saved.id}-${history.length + 1}`,
          versionNo: history.length + 1,
        });
        this.histories.set(saved.id, history);
      }
    }

    if (current) Object.assign(current, saved);
    else this.records.unshift(saved);
    this.persist();
    return this.wait(clone(saved));
  }

  private hydrate() {
    if (this.hydrated) return;
    const isFirstRead = this.storage.getItem(AGENCY_LINE_STORAGE_KEY) === null;
    this.records = readVersionedCollection<AgencyLine>({
      fallback: demoAgencyLines.map((line) => clone(line)),
      now: this.now,
      storage: this.storage,
      storageKey: AGENCY_LINE_STORAGE_KEY,
    }).map((line) => normalizeStoredLine(line));
    for (const line of this.records) {
      if (!line.deliveryUrl || this.histories.has(line.id)) continue;
      this.histories.set(line.id, [
        {
          agencyLineId: line.id,
          changedAt: line.updatedAt,
          changedByName: '历史数据',
          deliveryUrl: line.deliveryUrl,
          id: `${line.id}-1`,
          versionNo: 1,
        },
      ]);
    }
    this.hydrated = true;
    if (isFirstRead) this.persist();
  }

  private persist() {
    writeVersionedCollection(
      this.storage,
      AGENCY_LINE_STORAGE_KEY,
      // Token 仅保留在当前内存会话，禁止以明文写入浏览器持久化存储。
      this.records.map((line) => ({ ...clone(line), token: '' })),
      { now: this.now },
    );
  }

  private wait<T>(value: T): Promise<T> {
    if (!this.delay) return Promise.resolve(value);
    return new Promise((resolve) => {
      setTimeout(() => resolve(value), this.delay);
    });
  }
}
