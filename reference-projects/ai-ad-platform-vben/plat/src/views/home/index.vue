<script lang="ts" setup>
import type { HomeTodoLevel, HomeViewId } from '#/domain/home';
import type { TaskActivityReadModel } from '#/domain/task-activity';

import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore, useUserStore } from '@vben/stores';

import Card from 'ant-design-vue/es/card';

import {
  Alert,
  Button,
  Col,
  Empty,
  Progress,
  Row,
  Select,
  Skeleton,
  Tag,
} from 'ant-design-vue';

import { isFusionDemoMode } from '#/api';
import { useMaterialOrderAccess } from '#/composables/useMaterialOrderAccess';
import { HomeService } from '#/domain/home';
import {
  GlobalTaskActivityAdapter,
  TaskActivityService,
  TaskCenterActivityAdapter,
} from '#/domain/task-activity';
import {
  clearSelectedDemoRole,
  readSelectedDemoRole,
} from '#/mock/demo-role-preview';
import { resetRoutes } from '#/router';
import { useGlobalTaskStore, useProjectContextStore } from '#/store';
import { useMediaResourceStore } from '#/store/media-resource';
import { useTaskCenterStore } from '#/store/task-center';

const router = useRouter();
const accessStore = useAccessStore();
const projectStore = useProjectContextStore();
const taskStore = useGlobalTaskStore();
const taskCenterStore = useTaskCenterStore();
const mediaResourceStore = useMediaResourceStore();
const userStore = useUserStore();
const homeService = new HomeService();
const taskActivityService = new TaskActivityService([
  new TaskCenterActivityAdapter({ tasks: () => taskCenterStore.tasks }),
  new GlobalTaskActivityAdapter({ tasks: () => taskStore.tasks }),
]);
const loading = ref(false);
const loadError = ref('');
const activeHomeViewId = ref<HomeViewId>();

const demoRoleProfile = computed(() =>
  isFusionDemoMode() ? readSelectedDemoRole() : undefined,
);

const roleCodes = computed(() => {
  const profile = demoRoleProfile.value;
  if (profile) return [profile.id, ...profile.roles];
  return userStore.userInfo?.roles ?? [];
});

const activityViewer = computed(() => {
  const user = userStore.userInfo as Record<string, unknown> | undefined;
  const id = user?.userId ?? user?.user_id ?? user?._id;
  return {
    id: typeof id === 'string' ? id : undefined,
    name:
      demoRoleProfile.value?.realName ??
      userStore.userInfo?.realName ??
      userStore.userInfo?.full_name,
    roleCodes: roleCodes.value,
  };
});

const resourceSnapshot = computed(() => ({
  activeAssignmentCount: mediaResourceStore.activeAssignments.length,
  exceptionAccountCount: mediaResourceStore.exceptionAccounts.length,
  pendingApplicationCount: mediaResourceStore.pendingApplications.length,
  pendingReturnCount: mediaResourceStore.pendingReturns.length,
}));

const activityModel = ref<TaskActivityReadModel>({
  events: [],
  projectStages: [],
  todos: [],
});

const activityTasks = computed(() =>
  activityModel.value.events
    .filter(
      (event) =>
        event.eventKind === 'async-status' ||
        event.eventKind === 'stage-snapshot',
    )
    .map((event) => ({
      id: event.id,
      platform: event.platform,
      progress: event.progress ?? 0,
      projectId: event.projectId,
      status: event.state,
      targetPath: event.targetPath,
      title: event.title,
      updatedAt: event.occurredAt ?? '当前状态',
    })),
);

const homeModel = computed(() =>
  homeService.read({
    overview: null,
    projectCount: projectStore.projectOptions.filter(
      (project) => !['archived', 'ended'].includes(project.status),
    ).length,
    resource: resourceSnapshot.value,
    roleCodes: roleCodes.value,
    tasks: activityTasks.value,
    workflowStages: activityModel.value.projectStages,
  }),
);

const homeView = computed(() =>
  homeService.resolveView(homeModel.value, activeHomeViewId.value),
);

const { canCreateMaterialOrder } = useMaterialOrderAccess();
const visibleQuickActions = computed(() =>
  homeView.value.quickActions.filter(
    (action) =>
      action.path !== '/requirement/create' || canCreateMaterialOrder.value,
  ),
);

const homeViewOptions = computed(() =>
  homeModel.value.availableViews.map((view) => ({
    label: view.label,
    value: view.id,
  })),
);

const statusCards = computed(() => {
  const metricMap = new Map(
    homeModel.value.metrics.map((metric) => [metric.id, metric]),
  );
  return homeView.value.metricIds.flatMap((metricId) => {
    const metric = metricMap.get(metricId);
    return metric ? [metric] : [];
  });
});

watch(
  () => homeModel.value.availableViews.map((view) => view.id).join(','),
  () => {
    if (
      !homeModel.value.availableViews.some(
        (view) => view.id === activeHomeViewId.value,
      )
    ) {
      activeHomeViewId.value = homeModel.value.defaultViewId;
    }
  },
  { immediate: true },
);

function todoColor(level: HomeTodoLevel) {
  return { high: 'red', low: 'default', medium: 'orange' }[level];
}

function taskStatusColor(status: string) {
  if (['done', 'success'].includes(status)) return 'success';
  if (['failed', 'partial_success', 'risk'].includes(status)) return 'error';
  if (['pending_acceptance', 'pending_assignment'].includes(status)) {
    return 'warning';
  }
  if (['doing', 'queued', 'running'].includes(status)) return 'processing';
  return 'default';
}

function taskStatusLabel(status: string) {
  return (
    {
      assigned_pending_confirmation: '待确认',
      cancel_requested: '取消确认中',
      doing: '处理中',
      done: '已完成',
      failed: '失败',
      partial_success: '部分成功',
      pending: '待处理',
      pending_acceptance: '待验收',
      pending_assignment: '待分配',
      queued: '排队中',
      refund_pending: '退款处理中',
      risk: '风险',
      running: '执行中',
      success: '已完成',
    }[status] ?? '需处理'
  );
}

async function switchDemoRole() {
  clearSelectedDemoRole();
  resetRoutes();
  accessStore.setAccessMenus([]);
  accessStore.setAccessRoutes([]);
  accessStore.setAccessCodes([]);
  accessStore.setAccessToken(null);
  accessStore.setIsAccessChecked(false);
  userStore.setUserInfo(null);
  await router.replace('/auth/login');
}

function refreshActivityModel(projectId: string) {
  loading.value = true;
  loadError.value = '';
  try {
    activityModel.value = taskActivityService.readSync({
      projectId: projectId || undefined,
      viewer: activityViewer.value,
    });
  } catch {
    loadError.value = '工作台数据暂时未能更新，页面保留上次结果，可重新加载。';
  } finally {
    loading.value = false;
  }
}

watch(
  () => projectStore.selectedProjectId,
  (projectId) => refreshActivityModel(projectId),
  { immediate: true },
);
</script>

<template>
  <Page auto-content-height class="bg-muted/40" content-class="pb-6">
    <div class="ux-section-stack">
      <Alert
        v-if="loadError"
        :message="loadError"
        type="warning"
        show-icon
        closable
        @close="loadError = ''"
      >
        <template #action>
          <Button @click="refreshActivityModel(projectStore.selectedProjectId)">
            重新加载
          </Button>
        </template>
      </Alert>
      <Card>
        <div class="ux-toolbar">
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <h1 class="text-foreground m-0 text-xl font-semibold">
                {{ homeView.label }}
              </h1>
              <Tag>{{
                demoRoleProfile ? '角色 Mock 视图' : '已授权角色视图'
              }}</Tag>
            </div>
            <p class="text-muted-foreground m-0 text-sm leading-6">
              {{
                demoRoleProfile
                  ? `${demoRoleProfile.realName} · ${homeView.description}`
                  : homeView.description
              }}
            </p>
          </div>
          <div class="ux-actions w-full sm:w-auto sm:justify-end">
            <Select
              v-if="homeViewOptions.length > 1"
              v-model:value="activeHomeViewId"
              :options="homeViewOptions"
              class="min-w-[140px]"
              aria-label="切换角色首页视图"
            />
            <Button
              v-if="demoRoleProfile"
              class="min-w-[100px] whitespace-nowrap"
              @click="switchDemoRole"
            >
              切换角色
            </Button>
            <Button
              class="min-w-[88px] whitespace-nowrap"
              @click="router.push('/fusion/projects')"
            >
              项目管理
            </Button>
            <Button
              class="min-w-[108px] whitespace-nowrap"
              type="primary"
              @click="router.push('/fusion/ads/create')"
            >
              <IconifyIcon icon="lucide:plus" class="shrink-0 text-base" />
              <span>创建广告</span>
            </Button>
          </div>
        </div>
      </Card>

      <Skeleton v-if="loading" active :paragraph="{ rows: 8 }" />
      <template v-else>
        <Row :gutter="[16, 16]">
          <Col
            v-for="card in statusCards"
            :key="card.label"
            :xs="24"
            :sm="12"
            :xl="6"
          >
            <Card :bordered="true" class="h-full">
              <div class="flex items-start justify-between">
                <div>
                  <div class="text-muted-foreground text-sm">
                    {{ card.label }}
                  </div>
                  <div
                    class="text-foreground mt-2 text-2xl font-semibold tracking-tight"
                  >
                    {{ card.value }}
                  </div>
                  <div class="text-muted-foreground mt-2 text-xs leading-5">
                    {{ card.description }}
                  </div>
                </div>
                <div
                  class="bg-muted text-muted-foreground flex h-10 w-10 items-center justify-center rounded-lg"
                >
                  <IconifyIcon
                    :icon="card.icon"
                    aria-hidden="true"
                    class="text-xl"
                  />
                </div>
              </div>
            </Card>
          </Col>
        </Row>

        <Row :gutter="[16, 16]">
          <Col
            v-for="card in homeView.cards"
            :key="card.id"
            :xs="24"
            :xl="card.xl"
          >
            <Card class="h-full">
              <template #title>
                <h2 class="text-foreground m-0 text-base font-semibold">
                  {{ card.title }}
                </h2>
              </template>
              <template v-if="card.kind === 'project-workflow'">
                <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <div
                    v-for="(stage, index) in homeModel.workflow"
                    :key="stage.label"
                    class="border-border bg-muted/50 rounded-lg border p-4"
                  >
                    <div class="text-muted-foreground mb-2 text-xs font-medium">
                      {{ String(index + 1).padStart(2, '0') }} {{ stage.label }}
                    </div>
                    <div class="text-foreground text-xl font-semibold">
                      {{ stage.value }}
                    </div>
                    <div class="text-muted-foreground mt-1 text-xs leading-5">
                      {{ stage.description }}
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="card.kind === 'project-health'">
                <details class="group">
                  <summary
                    class="text-foreground flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold [&::-webkit-details-marker]:hidden"
                  >
                    <span>查看项目状态详情</span>
                    <span
                      class="text-muted-foreground flex items-center gap-2 text-xs font-normal"
                    >
                      {{ homeModel.projectHealth.length }} 项指标
                      <IconifyIcon
                        aria-hidden="true"
                        class="h-4 w-4 transition-transform group-open:rotate-180"
                        icon="lucide:chevron-down"
                      />
                    </span>
                  </summary>
                  <div
                    class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
                  >
                    <div
                      v-for="item in homeModel.projectHealth"
                      :key="item.label"
                      class="border-border bg-muted/50 rounded-lg border p-4"
                    >
                      <div class="text-muted-foreground text-xs font-medium">
                        {{ item.label }}
                      </div>
                      <div class="text-foreground mt-2 text-xl font-semibold">
                        {{ item.value }}
                      </div>
                      <div class="text-muted-foreground mt-1 text-xs leading-5">
                        {{ item.description }}
                      </div>
                    </div>
                  </div>
                </details>
              </template>

              <template v-else-if="card.kind === 'account-status'">
                <div
                  class="divide-border grid grid-cols-1 divide-y sm:grid-cols-4 sm:divide-x sm:divide-y-0"
                >
                  <div
                    v-for="item in homeModel.accountStatus"
                    :key="item.label"
                    class="min-w-0 px-0 py-3 first:pt-0 last:pb-0 sm:px-4 sm:py-0 sm:first:pl-0 sm:last:pr-0"
                  >
                    <div class="text-muted-foreground text-sm font-medium">
                      {{ item.label }}
                    </div>
                    <div
                      class="text-foreground mt-1 text-2xl font-semibold tracking-tight"
                    >
                      {{ item.value }}
                    </div>
                    <div class="text-muted-foreground mt-2 text-xs leading-5">
                      {{ item.description }}
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="card.kind === 'todos'">
                <Empty
                  v-if="homeModel.todos.length === 0"
                  description="当前没有待办"
                />
                <button
                  v-for="todo in homeModel.todos"
                  :key="todo.id"
                  type="button"
                  class="border-border bg-card hover:border-foreground/30 hover:bg-muted mb-3 flex w-full cursor-pointer items-start gap-3 rounded-lg border p-3 text-left transition-colors"
                  @click="router.push(todo.targetPath)"
                >
                  <Tag :color="todoColor(todo.level)" class="mt-0.5 shrink-0">
                    {{
                      todo.level === 'high'
                        ? '优先'
                        : todo.level === 'medium'
                          ? '关注'
                          : '待办'
                    }}
                  </Tag>
                  <span class="min-w-0">
                    <span class="text-foreground block text-sm font-medium">{{
                      todo.title
                    }}</span>
                    <span
                      class="text-muted-foreground mt-1 block text-xs leading-5"
                      >{{ todo.description }}</span
                    >
                  </span>
                </button>
              </template>

              <template v-else-if="card.kind === 'quick-actions'">
                <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <button
                    v-for="action in visibleQuickActions"
                    :key="action.path"
                    type="button"
                    class="border-border bg-card text-foreground hover:border-foreground/30 hover:bg-muted flex cursor-pointer items-center gap-3 rounded-lg border p-4 text-left text-sm font-medium transition-colors"
                    @click="router.push(action.path)"
                  >
                    <span
                      class="bg-muted text-muted-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                    >
                      <IconifyIcon
                        :icon="action.icon"
                        aria-hidden="true"
                        class="text-lg"
                      />
                    </span>
                    {{ action.label }}
                  </button>
                </div>
              </template>

              <template v-else-if="card.kind === 'tasks'">
                <div class="mb-3 flex justify-end">
                  <Button type="link" @click="taskStore.openDrawer">
                    打开任务中心
                  </Button>
                </div>
                <Empty
                  v-if="homeModel.tasks.length === 0"
                  description="暂无任务"
                />
                <div v-else class="divide-border divide-y">
                  <div
                    v-for="task in homeModel.tasks"
                    :key="task.id"
                    class="flex items-center gap-4 rounded-lg py-3 first:pt-0 last:pb-0"
                    :class="
                      task.targetPath
                        ? 'hover:bg-muted cursor-pointer transition-colors'
                        : ''
                    "
                    :role="task.targetPath ? 'link' : undefined"
                    :tabindex="task.targetPath ? 0 : undefined"
                    @click="task.targetPath && router.push(task.targetPath)"
                    @keydown.enter="
                      task.targetPath && router.push(task.targetPath)
                    "
                  >
                    <div
                      class="bg-muted text-muted-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                    >
                      <IconifyIcon
                        :icon="
                          task.platform ? 'lucide:rocket' : 'lucide:sparkles'
                        "
                        aria-hidden="true"
                      />
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="text-foreground truncate text-sm font-medium">
                        {{ task.title }}
                      </div>
                      <div class="text-muted-foreground mt-1 text-xs">
                        {{ task.updatedAt }}
                      </div>
                    </div>
                    <div class="w-24 shrink-0 sm:w-32">
                      <Progress
                        v-if="
                          ['doing', 'queued', 'running'].includes(task.status)
                        "
                        :percent="task.progress"
                      />
                      <Tag v-else :color="taskStatusColor(task.status)">
                        {{ taskStatusLabel(task.status) }}
                      </Tag>
                    </div>
                  </div>
                </div>
              </template>
            </Card>
          </Col>
        </Row>
      </template>
    </div>
  </Page>
</template>
