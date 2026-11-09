import type { ComputedRef } from 'vue';

import type {
  DashboardAnalysis,
  DashboardAnalyzeQuery,
  DashboardHosting,
  DashboardHostingQuery,
} from '#/domain/my-dashboard';

import { onBeforeUnmount, ref, watch } from 'vue';

import { myDashboardService } from '#/domain/my-dashboard';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

/** 整窗态势与托管独立加载；系列手动分析由成效表管理。 */
export function useMyDashboardAgent(
  query: ComputedRef<DashboardAnalyzeQuery>,
  active: ComputedRef<boolean>,
) {
  const analysis = ref<DashboardAnalysis | null>(null);
  const analysisLoading = ref(false);
  const analysisError = ref('');
  let analysisRequest = 0;
  let analysisController: AbortController | undefined;

  async function loadAnalysis() {
    const request = ++analysisRequest;
    analysisController?.abort();
    analysis.value = null;
    analysisError.value = '';
    analysisLoading.value = false;
    if (!active.value) return true;
    analysisController = new AbortController();
    analysisLoading.value = true;
    try {
      const result = await myDashboardService.analyze(
        query.value,
        analysisController.signal,
      );
      if (request !== analysisRequest) return false;
      analysis.value = result;
      return true;
    } catch (error) {
      if (request === analysisRequest)
        analysisError.value = errorMessage(error, '智能体分析暂时不可用');
      return false;
    } finally {
      if (request === analysisRequest) analysisLoading.value = false;
    }
  }

  const hosting = ref<DashboardHosting | null>(null);
  const hostingLoading = ref(false);
  const hostingSaving = ref(false);
  const hostingError = ref('');
  const hostingLoaded = ref(false);
  const hostingDraft = ref({
    cadence: 'hourly' as 'hourly' | 'realtime',
    enabled: false,
    range: query.value.range,
    spend_change_threshold: 15 as number | undefined,
  });
  let hostingRequest = 0;

  function fillHosting(result: DashboardHosting) {
    hosting.value = result;
    hostingDraft.value = {
      cadence: result.cadence ?? 'hourly',
      enabled: result.enabled,
      range: result.range ?? query.value.range,
      spend_change_threshold: result.spend_change_threshold ?? 15,
    };
  }

  async function loadHosting() {
    const request = ++hostingRequest;
    hostingLoading.value = true;
    hostingLoaded.value = false;
    hostingError.value = '';
    try {
      const result = await myDashboardService.getHosting();
      if (request !== hostingRequest) return;
      fillHosting(result);
      hostingLoaded.value = true;
    } catch (error) {
      if (request === hostingRequest)
        hostingError.value = errorMessage(error, '读取托管设置失败，请重试。');
    } finally {
      if (request === hostingRequest) hostingLoading.value = false;
    }
  }

  async function saveHosting() {
    if (!hostingLoaded.value || hostingLoading.value || hostingSaving.value)
      return false;
    hostingError.value = '';
    if (hostingDraft.value.enabled && hosting.value?.feishu_bound === false) {
      hostingError.value = '需要先绑定飞书，才能把托管分析推给你。';
      return false;
    }
    const draft = hostingDraft.value;
    if (draft.enabled && typeof draft.spend_change_threshold !== 'number') {
      hostingError.value = '请输入消耗波动提醒阈值。';
      return false;
    }
    const payload: DashboardHostingQuery = draft.enabled
      ? {
          enabled: true,
          cadence: draft.cadence,
          range: draft.range,
          spend_change_threshold: draft.spend_change_threshold ?? 15,
        }
      : { enabled: false };
    hostingSaving.value = true;
    try {
      const result = await myDashboardService.saveHosting(payload);
      if (
        result.enabled !== payload.enabled ||
        (result.enabled && result.feishu_bound === false)
      ) {
        throw new Error('托管设置未生效，请确认已绑定飞书后重试。');
      }
      fillHosting(result);
      return true;
    } catch (error) {
      hostingError.value = errorMessage(error, '保存托管设置失败，请重试。');
      return false;
    } finally {
      hostingSaving.value = false;
    }
  }

  watch([query, active], () => void loadAnalysis(), { immediate: true });
  onBeforeUnmount(() => {
    analysisRequest += 1;
    hostingRequest += 1;
    analysisController?.abort();
  });

  return {
    analysis,
    analysisError,
    analysisLoading,
    hosting,
    hostingDraft,
    hostingError,
    hostingLoaded,
    hostingLoading,
    hostingSaving,
    loadAnalysis,
    loadHosting,
    saveHosting,
  };
}
