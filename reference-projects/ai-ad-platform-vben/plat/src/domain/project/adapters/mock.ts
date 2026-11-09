import type { ProjectAdapter } from '../adapter';
import type {
  ProjectAgencyLineBindingInput,
  ProjectAgencyLineDeliveryOption,
  ProjectAgencyLineOption,
  ProjectContext,
  ProjectTabCounts,
  ProjectListParams,
  ProjectListResult,
  ProjectOperatingOverview,
  ProjectOption,
  ProjectRegionOption,
  ProjectSearchOption,
  ProjectSummary,
  ProjectUpsertPayload,
  ProjectWallet,
} from '../types';

import {
  demoProjectOperatingRecords,
  demoProjectOperationMetrics,
  demoProjects,
} from '#/api/fusion/fixtures';
import {
  AgencyLineService,
  demoAgencyLines,
  MockAgencyLineAdapter,
} from '#/domain/agency-line';
import {
  readVersionedCollection,
  writeVersionedCollection,
} from '#/mock/persistence/versioned-collection';
import { filterDemoProjects, getCurrentDemoActor } from '#/mock/demo-access';

const PROJECT_STORAGE_KEY = 'fusion:demo-projects';

const agencyLineIdByName = new Map(
  demoAgencyLines.map((line) => [line.name, line.id]),
);
const agencyLineNameById = new Map(
  demoAgencyLines.map((line) => [line.id, line.name]),
);

function resolveAgencyLineIds(project: ProjectSummary) {
  return project.agencyLineIds?.length
    ? [...project.agencyLineIds]
    : (project.agentLines ?? []).map(
        (name) => agencyLineIdByName.get(name) ?? `legacy:${name}`,
      );
}

export interface MockProjectAdapterOptions {
  agencyLines?: Pick<AgencyLineService, 'list' | 'listOptions'>;
  delay?: number;
  id?: () => string;
  now?: () => string;
  storage?: Storage;
}

function cloneProject(project: ProjectSummary): ProjectSummary {
  const agencyLineIds = resolveAgencyLineIds(project);
  return {
    ...project,
    agentLines: agencyLineIds.map(
      (id) => agencyLineNameById.get(id) ?? id.replace(/^legacy:/, ''),
    ),
    agencyLineIds,
    countryRegions: [...project.countryRegions],
    deliveryLines: project.deliveryLines.map((line) => ({ ...line })),
    kpiRequirements: project.kpiRequirements?.map((item) => ({ ...item })),
    mediaChannelIds: [...(project.mediaChannelIds ?? [])],
    platforms: [...project.platforms],
    wallet: project.wallet ? { ...project.wallet } : undefined,
  };
}

function createWallet(
  projectCode: string,
  suffix: string,
  accountName: string,
) {
  const seed = `${projectCode.replaceAll('-', '').toLowerCase()}${suffix}`;
  return {
    ethAddress: `0x${seed.padEnd(40, '0').slice(0, 40)}`,
    feeUnit: 'USDT',
    accountName,
    id: `WALLET-${projectCode}`,
    key: `wk_demo_${seed.slice(0, 22)}`,
    usdtAddress: `T${seed.padEnd(33, 'X').slice(0, 33)}`,
  };
}

export class MockProjectAdapter implements ProjectAdapter {
  async createWallet(id: string): Promise<ProjectWallet> {
    this.hydrate();
    const project = demoProjects.find((item) => item.id === id);
    if (!project) throw new Error('项目不存在或已被删除');
    project.wallet ??= createWallet(
      project.projectCode,
      project.id,
      project.name,
    );
    project.createWallet = true;
    project.updatedAt = this.now();
    this.persist();
    return this.wait({ ...project.wallet });
  }

  listRegionOptions(): Promise<ProjectRegionOption[]> {
    return Promise.resolve([
      {
        code: 'ASIA',
        countries: [
          { code: 'JP', name: '日本' },
          { code: 'SG', name: '新加坡' },
        ],
        name: '亚洲',
      },
      {
        code: 'EUROPE',
        countries: [
          { code: 'GB', name: '英国' },
          { code: 'DE', name: '德国' },
        ],
        name: '欧洲',
      },
      {
        code: 'NORTH_AMERICA',
        countries: [{ code: 'US', name: '美国' }],
        name: '北美洲',
      },
    ]);
  }
  private readonly agencyLines: Pick<AgencyLineService, 'list' | 'listOptions'>;
  private readonly delay: number;
  private readonly generateId: () => string;
  private hydrated = false;
  private readonly now: () => string;
  private readonly storage: Storage;

  constructor(options: MockProjectAdapterOptions = {}) {
    this.delay = options.delay ?? 180;
    this.generateId = options.id ?? (() => Date.now().toString(36));
    this.now = options.now ?? (() => new Date().toISOString());
    this.storage = options.storage ?? window.localStorage;
    this.agencyLines =
      options.agencyLines ??
      new AgencyLineService(
        new MockAgencyLineAdapter({
          delay: this.delay,
          now: this.now,
          storage: this.storage,
        }),
      );
  }

  async applyAgencyLineBindings(
    id: string,
    input: ProjectAgencyLineBindingInput,
  ): Promise<ProjectSummary> {
    const project = await this.get(id);
    const remove = new Set(input.remove ?? []);
    return this.bindAgencyLines(id, [
      ...(project.agencyLineIds ?? []).filter((lineId) => !remove.has(lineId)),
      ...(input.add ?? []),
    ]);
  }

  async bindAgencyLines(
    id: string,
    agencyLineIds: string[],
  ): Promise<ProjectSummary> {
    this.hydrate();
    const project = demoProjects.find((item) => item.id === id);
    if (!project) throw new Error('项目不存在或已被删除');
    const stableIds = [...new Set(agencyLineIds)];
    const availableLines = await this.agencyLines.listOptions({});
    const availableIds = new Set(availableLines.map((line) => line.id));
    const missingIds = stableIds.filter((lineId) => !availableIds.has(lineId));
    if (missingIds.length > 0) {
      throw new Error(`代理线不存在或已被删除：${missingIds.join('、')}`);
    }
    availableLines.forEach((line) => {
      agencyLineIdByName.set(line.name, line.id);
      agencyLineNameById.set(line.id, line.name);
    });
    Object.assign(project, {
      agencyLineIds: stableIds,
      agentLines: stableIds.map(
        (lineId) =>
          agencyLineNameById.get(lineId) ?? lineId.replace(/^legacy:/, ''),
      ),
      updatedAt: this.now(),
    });
    this.persist();
    return this.wait(cloneProject(project));
  }

  async get(id: string): Promise<ProjectSummary> {
    this.hydrate();
    const project = demoProjects.find((item) => item.id === id);
    if (!project) throw new Error('项目不存在或已被删除');
    return this.wait(cloneProject(project));
  }

  async getTabCounts(): Promise<ProjectTabCounts> {
    this.hydrate();
    const lines = await this.agencyLines.listOptions({});
    return this.wait({
      agencyLineCount: lines.length,
      projectCount: filterDemoProjects(getCurrentDemoActor(), demoProjects)
        .length,
    });
  }

  async getContext(): Promise<ProjectContext> {
    this.hydrate();
    return this.wait({
      options: demoProjects.map(
        ({ id, name, platforms, projectCode, status }) => ({
          id,
          name,
          platforms: [...platforms],
          projectCode,
          status,
        }),
      ),
      statistics: {
        active: demoProjects.filter((item) => item.status === 'active').length,
        draftOrPending: demoProjects.filter((item) =>
          ['draft', 'pending'].includes(item.status),
        ).length,
        endedOrArchived: demoProjects.filter((item) =>
          ['archived', 'ended'].includes(item.status),
        ).length,
        total: demoProjects.length,
      },
    });
  }

  async getOperatingOverview(id: string): Promise<ProjectOperatingOverview> {
    const project = await this.get(id);
    const metric = demoProjectOperationMetrics[id] ?? {
      actualSpend: 0,
      attributionCompleted: false,
      currency: project.currency,
      metricCutoff: project.updatedAt,
      settledAmount: 0,
      settlementStatus: 'unsettled' as const,
    };
    const records = demoProjectOperatingRecords[id] ?? {
      completedPlans: [],
      completedTasks: [],
      totalPlanCount: 0,
      totalTaskCount: 0,
    };

    return this.wait({
      ...metric,
      completedPlanCount: records.completedPlans.length,
      completedPlans: records.completedPlans.map((item) => ({ ...item })),
      completedTaskCount: records.completedTasks.length,
      completedTasks: records.completedTasks.map((item) => ({ ...item })),
      dataQualityNote: '当前为领域级 Mock 经营快照，正式口径以后端聚合为准。',
      dataQualityStatus: metric.metricCutoff ? 'estimated' : 'missing',
      project,
      realizedRoi: metric.attributionCompleted ? metric.realizedRoi : undefined,
      totalPlanCount: records.totalPlanCount,
      totalTaskCount: records.totalTaskCount,
    });
  }

  async list(query: ProjectListParams = {}): Promise<ProjectListResult> {
    this.hydrate();
    const keyword = query.keyword?.trim().toLowerCase();
    const filtered = demoProjects.filter((item) => {
      const matchesKeyword =
        !keyword ||
        `${item.name}${item.projectCode}${item.productName}${item.countryRegions.join('')}`
          .toLowerCase()
          .includes(keyword);
      const matchesLegacyCustomer =
        !query.customerId || item.customerId === query.customerId;
      const matchesPlatform =
        !query.platform || item.platforms.includes(query.platform);
      const matchesStatus = !query.status || item.status === query.status;
      return (
        matchesKeyword &&
        matchesLegacyCustomer &&
        matchesPlatform &&
        matchesStatus
      );
    });
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 20;

    return this.wait({
      items: filtered
        .slice((page - 1) * pageSize, page * pageSize)
        .map((item) => cloneProject(item)),
      total: filtered.length,
    });
  }

  async listAgencyLines(): Promise<ProjectAgencyLineOption[]> {
    const lines = await this.agencyLines.listOptions({});
    const supported = lines.filter((line) =>
      ['facebook', 'google', 'tiktok'].includes(line.platform),
    );
    supported.forEach((line) => {
      agencyLineIdByName.set(line.name, line.id);
      agencyLineNameById.set(line.id, line.name);
    });
    return this.wait(
      supported.map((line) => ({
        id: line.id,
        name: line.name,
        platform: line.platform as ProjectAgencyLineOption['platform'],
      })),
    );
  }

  async listAgencyLineDeliveryOptions(
    projectId: string,
  ): Promise<ProjectAgencyLineDeliveryOption[]> {
    const result = await this.agencyLines.list({
      page: 1,
      pageSize: 100,
      projectId,
    });
    return this.wait(
      result.items.map(({ deliveryUrl, id, name, platform }) => ({
        deliveryUrl,
        id,
        name,
        platform,
      })),
    );
  }

  async listOptions(): Promise<ProjectOption[]> {
    this.hydrate();
    return this.wait(demoProjects.map((item) => cloneProject(item)));
  }

  async searchScopedOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    return this.searchOptions(keyword);
  }

  async searchOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    this.hydrate();
    const normalizedKeyword = keyword?.trim().toLowerCase();
    return this.wait(
      demoProjects
        .filter(
          (project) =>
            !normalizedKeyword ||
            `${project.name}${project.projectCode}`
              .toLowerCase()
              .includes(normalizedKeyword),
        )
        .slice(0, 50)
        .map(({ id, name }) => ({ id, name })),
    );
  }

  async save(input: ProjectUpsertPayload): Promise<ProjectSummary> {
    this.hydrate();
    const normalizedCode = input.projectCode.trim().toUpperCase();
    if (!normalizedCode) throw new Error('项目编码不能为空');
    if (!input.name.trim()) throw new Error('项目名称不能为空');
    if (
      demoProjects.some(
        (item) =>
          item.id !== input.id &&
          item.projectCode.trim().toUpperCase() === normalizedCode,
      )
    ) {
      throw new Error('项目编码已存在，请使用其他编码');
    }

    const current = demoProjects.find((item) => item.id === input.id);
    const now = this.now();
    const hasAgencyLineInput =
      input.agencyLineIds !== undefined || input.agentLines !== undefined;
    const agencyLineIds = [
      ...(hasAgencyLineInput
        ? (input.agencyLineIds ?? input.agentLines ?? [])
        : (current?.agencyLineIds ?? [])),
    ];
    if (current) {
      Object.assign(current, input, {
        agencyLineIds,
        agentLines: agencyLineIds.map(
          (id) => agencyLineNameById.get(id) ?? id.replace(/^legacy:/, ''),
        ),
        name: input.name.trim(),
        productName: input.productName.trim(),
        projectCode: normalizedCode,
        updatedAt: now,
      });
      this.persist();
      return this.wait(cloneProject(current));
    }

    const suffix = this.generateId();
    const created: ProjectSummary = {
      ...input,
      adAccountCount: 0,
      agencyLineIds,
      agentLines: agencyLineIds.map(
        (id) => agencyLineNameById.get(id) ?? id.replace(/^legacy:/, ''),
      ),
      customerId: input.customerId ?? '',
      customerName: input.customerName ?? '',
      deliveryLines: [],
      id: `project-${suffix}`,
      materialCount: 0,
      name: input.name.trim(),
      ownerName: input.ownerName ?? '',
      productName: input.productName.trim(),
      projectCode: normalizedCode,
      updatedAt: now,
      wallet: input.createWallet
        ? createWallet(normalizedCode, suffix, input.name.trim())
        : undefined,
    };
    demoProjects.unshift(created);
    this.persist();
    return this.wait(cloneProject(created));
  }

  private hydrate() {
    if (this.hydrated) return;
    const projects = readVersionedCollection<ProjectSummary>({
      fallback: demoProjects,
      now: this.now,
      storage: this.storage,
      storageKey: PROJECT_STORAGE_KEY,
    });
    demoProjects.splice(
      0,
      Infinity,
      ...projects.map((project) => {
        const seeded = demoProjects.find((item) => item.id === project.id);
        const agencyLineIds = resolveAgencyLineIds({
          ...seeded,
          ...project,
          agentLines: project.agentLines ?? seeded?.agentLines,
        } as ProjectSummary);
        return {
          ...seeded,
          ...project,
          agencyLineIds,
          agentLines: agencyLineIds.map(
            (id) => agencyLineNameById.get(id) ?? id.replace(/^legacy:/, ''),
          ),
          wallet:
            project.wallet ??
            seeded?.wallet ??
            (project.createWallet === false
              ? undefined
              : createWallet(project.projectCode, project.id, project.name)),
        };
      }),
    );
    this.hydrated = true;
  }

  private persist() {
    writeVersionedCollection(this.storage, PROJECT_STORAGE_KEY, demoProjects, {
      now: this.now,
    });
  }

  private wait<T>(value: T): Promise<T> {
    if (this.delay <= 0) return Promise.resolve(value);
    return new Promise((resolve) =>
      window.setTimeout(() => resolve(value), this.delay),
    );
  }
}
