import type { Ref } from 'vue';

import type { ChooseDevOption } from '#/api/dashboard';
import type {
  AdDashboardCategory,
  AdDashboardRow,
} from '#/domain/ad-dashboard';
import type {
  DashboardConfiguredStatus,
  DashboardOperationLevel,
  DashboardOperationSnapshot,
  PendingDashboardStatusChange,
} from '#/domain/ad-dashboard/operations';

import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  ref,
  watch,
} from 'vue';

import { message } from 'ant-design-vue';

import { ApiBusinessError } from '#/api/backend-response';
import { adOperate, getAdOperateStatus } from '#/api/dashboard';
import {
  canOperateDashboardDates,
  dashboardOperationDisabledReason,
  dashboardOperationKey,
  dashboardOperationLevel,
  isDashboardConfiguredStatus,
  isDashboardOperationRunning,
  latestDashboardToggle,
} from '#/domain/ad-dashboard/operations';

interface TrackedOperation {
  after: DashboardConfiguredStatus;
  baseline?: string;
  before: DashboardConfiguredStatus;
  id: string;
  level: DashboardOperationLevel;
  phase: 'pending' | 'submitting' | 'uncertain';
}

export interface DashboardDeveloperSelection {
  developer: ChooseDevOption;
  key: string;
}

const POLL_INTERVAL = 5000;
const MAX_POLL_ATTEMPTS = 30;

/** 暂存按对象隔离；提交后的结果由队列回执确认，网络失败不得自动重发写请求。 */
export function useAdDashboardOperations(
  category: Ref<AdDashboardCategory>,
  rows: Ref<AdDashboardRow[]>,
  startDate: Ref<string>,
  endDate: Ref<string>,
) {
  const pending = ref<Record<string, PendingDashboardStatusChange>>({});
  const snapshots = ref<Record<string, DashboardOperationSnapshot>>({});
  const tracked = ref<Record<string, TrackedOperation>>({});
  const failedBase = ref<Record<string, DashboardConfiguredStatus>>({});
  const queryErrors = ref<Record<string, boolean>>({});
  const dialogOpen = ref(false);
  const saving = ref(false);
  const refreshing = ref(false);
  const timedOut = ref(false);
  const queryVersions = new Map<string, number>();
  const controllers = new Set<AbortController>();
  let version = 0;
  let suspended = false;
  let disposed = false;
  let pollAttempts = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const level = computed(() => dashboardOperationLevel(category.value));
  const pendingChanges = computed(() => Object.values(pending.value));
  const hasQueryError = computed(() =>
    [...targets().keys()].some((key) => queryErrors.value[key]),
  );
  const hasRunning = computed(
    () =>
      Object.keys(tracked.value).length > 0 ||
      Object.values(snapshots.value).some((snapshot) =>
        [snapshot.start, snapshot.pause].some((operation) =>
          isDashboardOperationRunning(operation?.status),
        ),
      ),
  );

  function clearTimer() {
    if (timer) clearTimeout(timer);
    timer = undefined;
  }

  function schedulePoll() {
    clearTimer();
    if (disposed || suspended || !hasRunning.value) return;
    if (pollAttempts >= MAX_POLL_ATTEMPTS) {
      timedOut.value = true;
      return;
    }
    timer = setTimeout(() => {
      pollAttempts += 1;
      void refreshStatus();
    }, POLL_INTERVAL);
  }

  function targets() {
    const result = new Map<
      string,
      { id: string; level: DashboardOperationLevel }
    >();
    if (level.value) {
      const currentLevel = level.value;
      for (const row of rows.value)
        result.set(dashboardOperationKey(currentLevel, row.id), {
          id: row.id,
          level: currentLevel,
        });
    }
    for (const item of [
      ...Object.values(pending.value),
      ...Object.values(tracked.value),
    ])
      result.set(dashboardOperationKey(item.level, item.id), item);
    // 翻页后仍追踪未结束的服务端任务，完成后才停止查询。
    for (const [key, snapshot] of Object.entries(snapshots.value)) {
      if (
        ![snapshot.start, snapshot.pause].some((operation) =>
          isDashboardOperationRunning(operation?.status),
        )
      )
        continue;
      const separator = key.indexOf(':');
      const operationLevel = key.slice(0, separator);
      if (
        operationLevel === 'campaign' ||
        operationLevel === 'adset' ||
        operationLevel === 'ad'
      )
        result.set(key, {
          level: operationLevel,
          id: key.slice(separator + 1),
        });
    }
    return result;
  }

  async function refreshStatus() {
    if (disposed || suspended) return;
    const requested = targets();
    if (requested.size === 0) return;
    const requestVersion = ++version;
    const controller = new AbortController();
    controllers.add(controller);
    refreshing.value = true;
    for (const key of requested.keys()) queryVersions.set(key, requestVersion);
    const groups = new Map<DashboardOperationLevel, string[]>();
    for (const target of requested.values())
      groups.set(target.level, [
        ...(groups.get(target.level) ?? []),
        target.id,
      ]);
    try {
      await Promise.all(
        [...groups].map(async ([targetLevel, ids]) => {
          try {
            const result = await getAdOperateStatus(ids, targetLevel, {
              signal: controller.signal,
              skipErrorMessage: true,
            });
            if (disposed || suspended || controller.signal.aborted) return;
            for (const id of ids) {
              const key = dashboardOperationKey(targetLevel, id);
              if (queryVersions.get(key) !== requestVersion) continue;
              const snapshot = result[id] ?? {};
              delete queryErrors.value[key];
              const task = tracked.value[key];
              // 提交前的读请求不能清掉提交中状态；同一操作的旧回执也不能被误认成本次结果。
              if (task?.phase === 'submitting') continue;
              if (task) {
                const operation =
                  snapshot[task.after === 'ACTIVE' ? 'start' : 'pause'];
                if (!operation || operation.updated_at === task.baseline)
                  continue;
                if (
                  operation.status === 'COMPLETED' ||
                  operation.status === 'FAILED'
                ) {
                  if (operation.status === 'FAILED')
                    failedBase.value[key] = task.before;
                  else delete failedBase.value[key];
                  delete tracked.value[key];
                } else if (isDashboardOperationRunning(operation.status)) {
                  task.phase = 'pending';
                }
              }
              snapshots.value[key] = snapshot;
            }
          } catch {
            if (controller.signal.aborted || disposed) return;
            for (const id of ids) {
              const key = dashboardOperationKey(targetLevel, id);
              if (queryVersions.get(key) === requestVersion)
                queryErrors.value[key] = true;
            }
          }
        }),
      );
    } finally {
      controllers.delete(controller);
      refreshing.value = controllers.size > 0;
      schedulePoll();
    }
  }

  function baseStatus(key: string, row: AdDashboardRow) {
    const latest = latestDashboardToggle(snapshots.value[key]);
    if (latest?.status === 'COMPLETED')
      return latest.op_type === 'start' ? 'ACTIVE' : 'PAUSED';
    return failedBase.value[key] ?? row.configuredStatus;
  }

  function rowState(row: AdDashboardRow) {
    const key = level.value ? dashboardOperationKey(level.value, row.id) : '';
    const task = tracked.value[key];
    const snapshot = snapshots.value[key];
    const latest = latestDashboardToggle(snapshot);
    const busy = Boolean(
      task ||
        [snapshot?.start, snapshot?.pause].some((operation) =>
          isDashboardOperationRunning(operation?.status),
        ),
    );
    const target =
      task?.after ??
      (busy && latest
        ? latest.op_type === 'start'
          ? 'ACTIVE'
          : 'PAUSED'
        : baseStatus(key, row));
    const checked = (pending.value[key]?.after ?? target) === 'ACTIVE';
    let disabledReason = dashboardOperationDisabledReason(row);
    if (!canOperateDashboardDates(startDate.value, endDate.value))
      disabledReason = '仅支持修改昨日、今日、明日状态';
    if (snapshot === undefined || queryErrors.value[key])
      disabledReason = '操作状态尚未确认，请刷新操作状态';
    if (busy)
      disabledReason =
        timedOut.value || task?.phase === 'uncertain'
          ? '执行结果待确认，请刷新操作状态或查看操作记录'
          : '操作正在执行，请等待';
    if (saving.value) disabledReason = '正在提交变更';
    return {
      busy,
      checked,
      disabledReason,
      error:
        latest?.status === 'FAILED'
          ? latest.error || '执行失败，请查看操作记录'
          : '',
      pending: Boolean(pending.value[key]),
      uncertain: Boolean(
        task?.phase === 'uncertain' || (busy && timedOut.value),
      ),
    };
  }

  function toggle(row: AdDashboardRow, checked: boolean) {
    if (!level.value || rowState(row).disabledReason) return;
    const key = dashboardOperationKey(level.value, row.id);
    const existing = pending.value[key];
    const before = existing?.before ?? baseStatus(key, row);
    if (!isDashboardConfiguredStatus(before)) return;
    const after = checked ? 'ACTIVE' : 'PAUSED';
    if (before === after) {
      delete pending.value[key];
      return;
    }
    pending.value[key] = {
      after,
      before,
      category: category.value,
      endDate: endDate.value,
      id: row.id,
      key,
      level: level.value,
      name: String(row.name ?? row.id),
      row: { ...row },
      startDate: startDate.value,
    };
  }

  function removePending(key: string) {
    if (!saving.value) delete pending.value[key];
  }

  function clearPending() {
    if (!saving.value) pending.value = {};
  }

  async function submit(selections: DashboardDeveloperSelection[]) {
    if (saving.value || selections.length === 0) return;
    saving.value = true;
    let accepted = 0;
    let uncertain = 0;
    try {
      await refreshStatus();
      // 逐条提交保留独立结果；部分失败的待提交项仍留在确认弹窗，不清掉整批修改。
      for (const selection of selections) {
        const change = pending.value[selection.key];
        if (!change) continue;
        const { key } = change;
        const developer = selection.developer;
        const snapshot = snapshots.value[key];
        const currentRow =
          category.value === change.category
            ? (rows.value.find((row) => row.id === change.id) ?? change.row)
            : change.row;
        const reason = !canOperateDashboardDates(
          change.startDate,
          change.endDate,
        )
          ? '原查询日期已超出可操作范围，请撤销后重新查询'
          : dashboardOperationDisabledReason(currentRow);
        if (
          reason ||
          !developer.id ||
          !developer.type ||
          queryErrors.value[key] ||
          snapshot === undefined
        ) {
          change.error = reason || '开发者或操作状态未确认，请刷新后重试';
          continue;
        }
        if (
          tracked.value[key] ||
          [snapshot.start, snapshot.pause].some((operation) =>
            isDashboardOperationRunning(operation?.status),
          )
        ) {
          change.error = '该对象已有执行中的指令，请等待完成';
          continue;
        }
        if (baseStatus(key, currentRow) !== change.before) {
          change.error = '对象状态已变化，请撤销该项后重新操作';
          continue;
        }
        const opType = change.after === 'ACTIVE' ? 'start' : 'pause';
        tracked.value[key] = {
          after: change.after,
          before: change.before,
          baseline: snapshot[opType]?.updated_at,
          id: change.id,
          level: change.level,
          phase: 'submitting',
        };
        queryVersions.set(key, ++version);
        try {
          await adOperate({
            id: change.id,
            level: change.level,
            name: change.name,
            object_type: developer.type,
            op_type: opType,
            personal_id: developer.id,
          });
          const task = tracked.value[key];
          if (task) task.phase = 'pending';
          delete pending.value[key];
          accepted += 1;
        } catch (error) {
          if (error instanceof ApiBusinessError) {
            delete tracked.value[key];
            change.error = error.message || '提交失败，请检查后重试';
          } else {
            // 网络中断时服务端可能已入队，继续查回执，不把同一修改恢复成可直接重发状态。
            const task = tracked.value[key];
            if (task) task.phase = 'uncertain';
            delete pending.value[key];
            uncertain += 1;
          }
        }
      }
      if (accepted)
        message.success(`已提交 ${accepted} 项变更，正在等待执行结果`);
      if (uncertain)
        message.warning(`${uncertain} 项提交结果待确认，请查看操作状态`);
      if (pendingChanges.value.length === 0) dialogOpen.value = false;
      pollAttempts = 0;
      timedOut.value = false;
      await refreshStatus();
    } finally {
      saving.value = false;
    }
  }

  function retryStatus() {
    pollAttempts = 0;
    timedOut.value = false;
    void refreshStatus();
  }

  watch(
    [category, rows],
    () => {
      if (suspended || disposed) return;
      pollAttempts = 0;
      timedOut.value = false;
      void refreshStatus();
    },
    { immediate: true },
  );

  function suspend() {
    suspended = true;
    clearTimer();
    for (const controller of controllers) controller.abort();
  }
  onDeactivated(suspend);
  onActivated(() => {
    suspended = false;
    retryStatus();
  });
  onBeforeUnmount(() => {
    disposed = true;
    suspend();
  });

  return {
    clearPending,
    dialogOpen,
    hasQueryError,
    level,
    pendingChanges,
    refreshing,
    removePending,
    retryStatus,
    rowState,
    saving,
    submit,
    timedOut,
    toggle,
  };
}
