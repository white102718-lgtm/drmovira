import type { ComputedRef, Ref } from 'vue';

import type {
  DashboardAnalysisObject,
  DashboardAnalyzeQuery,
  DashboardCampaignPerformance,
  DashboardDateQuery,
} from '#/domain/my-dashboard';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { myDashboardService } from '#/domain/my-dashboard';

type CampaignDecision = Pick<
  DashboardAnalysisObject,
  'action' | 'kind' | 'reason' | 'status'
>;
interface CampaignAnalysisState {
  error?: string;
  result?: CampaignDecision;
  state: 'error' | 'loading' | 'success';
}

/** 成效自动查询，分析仅按行手动触发；账户、日期或成效刷新后旧分析失效。 */
export function useMyDashboardCampaigns(
  dates: ComputedRef<DashboardDateQuery>,
  accountId: Ref<string | undefined>,
  agentQuery: ComputedRef<DashboardAnalyzeQuery>,
) {
  const performance = ref<DashboardCampaignPerformance[]>([]);
  const loading = ref(false);
  const error = ref('');
  const page = ref(1);
  const pageSize = ref(10);
  const total = ref(0);
  const analyses = ref<Record<string, CampaignAnalysisState>>({});
  const controllers = new Map<string, AbortController>();
  let listRequest = 0;
  let contextVersion = 0;

  const rows = computed(() =>
    performance.value.map((row) => ({
      ...row,
      ...analyses.value[row.id]?.result,
      analysisState: analyses.value[row.id]?.state ?? 'idle',
      analysisError: analyses.value[row.id]?.error,
    })),
  );
  const recommendationCounts = computed(() => {
    const completed = Object.values(analyses.value).filter(
      (entry) => entry.state === 'success',
    );
    const decisions = completed.flatMap((entry) =>
      entry.result?.action ? [entry.result] : [],
    );
    return {
      analyzed: completed.length,
      total: decisions.length,
      bidReview: decisions.filter((entry) => entry.kind === 'bid_review')
        .length,
      budget: decisions.filter((entry) => entry.kind === 'budget').length,
      observe: decisions.filter((entry) => entry.kind === 'observe').length,
    };
  });

  function resetAnalyses() {
    contextVersion += 1;
    controllers.forEach((controller) => controller.abort());
    controllers.clear();
    analyses.value = {};
  }

  async function loadPerformance() {
    const request = ++listRequest;
    performance.value = [];
    error.value = '';
    loading.value = false;
    if (!accountId.value) {
      total.value = 0;
      return true;
    }
    loading.value = true;
    try {
      const result = await myDashboardService.campaigns({
        ...dates.value,
        accountId: accountId.value,
        page: page.value,
        pageSize: pageSize.value,
      });
      if (request !== listRequest) return false;
      performance.value = result.items;
      total.value = result.total;
      return true;
    } catch {
      if (request === listRequest) {
        total.value = 0;
        error.value = '系列成效加载失败，请重试。';
      }
      return false;
    } finally {
      if (request === listRequest) loading.value = false;
    }
  }

  async function refreshPerformance() {
    resetAnalyses();
    return loadPerformance();
  }

  async function changePage(nextPage: number, nextPageSize: number) {
    page.value = nextPageSize === pageSize.value ? nextPage : 1;
    pageSize.value = nextPageSize;
    return loadPerformance();
  }

  async function analyzeCampaign(campaignId: string) {
    if (
      !accountId.value ||
      loading.value ||
      controllers.has(campaignId) ||
      !performance.value.some((row) => row.id === campaignId)
    )
      return;
    const version = contextVersion;
    const controller = new AbortController();
    controllers.set(campaignId, controller);
    analyses.value[campaignId] = { state: 'loading' };
    try {
      const response = await myDashboardService.analyze(
        {
          ...agentQuery.value,
          account_id: accountId.value,
          grain: 'campaign',
          focus_id: campaignId,
        },
        controller.signal,
      );
      if (version !== contextVersion) return;
      const decision = response.fact.objects.find(
        (row) => row.level === 'campaign' && row.id === campaignId,
      );
      if (!decision || (!decision.status && !decision.action)) {
        throw new Error('智能体未返回该系列的分析结果，请重试。');
      }
      // 只接受该系列的判断字段，不能覆盖广告数据 API 的名称与成效。
      analyses.value[campaignId] = {
        state: 'success',
        result: {
          status: decision.status,
          action: decision.action,
          kind: decision.kind,
          reason: decision.reason,
        },
      };
    } catch (error_) {
      if (version === contextVersion) {
        analyses.value[campaignId] = {
          state: 'error',
          error:
            error_ instanceof Error ? error_.message : '智能体分析暂时不可用',
        };
      }
    } finally {
      if (controllers.get(campaignId) === controller)
        controllers.delete(campaignId);
    }
  }

  watch(
    [dates, accountId],
    () => {
      page.value = 1;
      total.value = 0;
      void refreshPerformance();
    },
    { immediate: true, flush: 'sync' },
  );
  onBeforeUnmount(() => {
    listRequest += 1;
    resetAnalyses();
  });

  return {
    analyzeCampaign,
    changePage,
    error,
    loading,
    page,
    pageSize,
    recommendationCounts,
    refreshPerformance,
    rows,
    total,
  };
}
