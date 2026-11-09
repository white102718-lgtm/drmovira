<script setup lang="ts">
import type {
  FeishuAppConfig,
  FeishuOrganizationSchedule,
  FeishuOrganizationSyncLog,
  FeishuOrganizationSyncResult,
} from '#/api/feishu-sync';

import { computed, onMounted, reactive, ref } from 'vue';

import { useAccess } from '@vben/access';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
} from 'ant-design-vue';

import {
  getFeishuOrganizationAppConfig,
  getFeishuOrganizationLogs,
  getFeishuOrganizationSchedule,
  previewFeishuOrganization,
  syncFeishuOrganization,
  updateFeishuOrganizationAppConfig,
} from '#/api/feishu-sync';
import { $t } from '#/locales';

import OrganizationSchedule from './feishu-organization-schedule.vue';

defineOptions({ name: 'SystemFeishuOrganizationSync' });

type TabKey = 'application' | 'logs' | 'organization' | 'schedule';

const activeTab = ref<TabKey>('application');
const configLoading = ref(false);
const configSaving = ref(false);
const syncLoading = ref(false);
const logLoading = ref(false);
const syncResult = ref<FeishuOrganizationSyncResult>();
const logs = ref<FeishuOrganizationSyncLog[]>([]);
const schedule = ref<FeishuOrganizationSchedule>();
const previewId = ref<string>();
const previewExpiresAt = ref(0);
const requiresReview = ref(false);
const { hasAccessByCodes } = useAccess();
const canManage = computed(
  () =>
    hasAccessByCodes(['system:department:update']) &&
    hasAccessByCodes(['system:user:update']),
);
const hasActiveJob = computed(() =>
  logs.value.some(
    (log) =>
      log.triggerType !== 'PREVIEW' &&
      ['PENDING', 'RUNNING'].includes(log.status),
  ),
);
let statusRequest: Promise<void> | undefined;
const appConfig = reactive<FeishuAppConfig>({
  appId: '',
  appName: 'AdPulse 飞书应用',
  appSecret: '',
});

const logColumns = [
  { dataIndex: 'startedAt', title: '开始时间', width: 180 },
  { dataIndex: 'triggerType', title: '类型', width: 100 },
  { dataIndex: 'status', title: '状态', width: 100 },
  { dataIndex: 'departmentTotal', title: '部门总数', width: 100 },
  { dataIndex: 'userTotal', title: '人员总数', width: 100 },
  { dataIndex: 'conflictCount', title: '冲突', width: 80 },
  {
    dataIndex: 'departmentChanges',
    title: $t('feishuOrg.departmentChanges'),
    width: 190,
  },
  { dataIndex: 'userChanges', title: $t('feishuOrg.userChanges'), width: 190 },
  { dataIndex: 'startedBy', title: $t('feishuOrg.operator'), width: 120 },
  { dataIndex: 'errorMessage', title: '失败原因' },
];

async function loadAppConfig() {
  configLoading.value = true;
  try {
    Object.assign(appConfig, await getFeishuOrganizationAppConfig(), {
      appSecret: '',
    });
  } finally {
    configLoading.value = false;
  }
}

async function saveAppConfig() {
  if (!appConfig.appName.trim() || !appConfig.appId.trim()) {
    message.warning('请填写应用名称和 App ID');
    return;
  }
  configSaving.value = true;
  try {
    Object.assign(
      appConfig,
      await updateFeishuOrganizationAppConfig(appConfig),
      { appSecret: '' },
    );
    message.success('飞书应用配置已保存');
    previewId.value = undefined;
    syncResult.value = undefined;
  } finally {
    configSaving.value = false;
  }
}

async function previewSync() {
  syncLoading.value = true;
  previewId.value = undefined;
  try {
    const preview = await previewFeishuOrganization();
    syncResult.value = preview.result;
    requiresReview.value = preview.requiresReview;
    previewId.value =
      preview.result.conflictCount === 0 ? preview.previewId : undefined;
    // 客户端提前失效，服务端仍按自己的时间及操作者归属校验。
    previewExpiresAt.value = Date.now() + 14 * 60 * 1000;
    message.success('组织架构同步预览已生成');
  } finally {
    syncLoading.value = false;
  }
}

function confirmSync() {
  if (!syncResult.value) return void message.warning('请先执行同步预览');
  if (syncResult.value.conflictCount > 0) {
    return void message.warning('当前预览存在冲突，请处理后重新预览');
  }
  if (!previewId.value || Date.now() >= previewExpiresAt.value) {
    previewId.value = undefined;
    return void message.warning($t('feishuOrg.previewExpired'));
  }
  const confirmedPreviewId = previewId.value;
  const acceptMissing = requiresReview.value;
  Modal.confirm({
    cancelText: '取消',
    content: acceptMissing
      ? $t('feishuOrg.confirmRisk', {
          departments: syncResult.value.departmentDisabled,
          users: syncResult.value.userDisabled,
        })
      : '同步会新增或更新飞书部门和人员；飞书侧缺失的记录只会停用，不会删除。',
    okText: '确认同步',
    title: '确认同步飞书组织架构？',
    async onOk() {
      syncLoading.value = true;
      try {
        await syncFeishuOrganization({
          previewId: confirmedPreviewId,
          acceptMissing,
        });
        previewId.value = undefined;
        message.success($t('feishuOrg.submitted'));
        activeTab.value = 'logs';
        await loadLogs();
      } finally {
        syncLoading.value = false;
      }
    },
  });
}

async function loadLogs() {
  if (statusRequest) return statusRequest;
  logLoading.value = true;
  statusRequest = (async () => {
    try {
      const [history, config] = await Promise.all([
        getFeishuOrganizationLogs(),
        getFeishuOrganizationSchedule(),
      ]);
      logs.value = history;
      schedule.value = config;
      if (previewId.value && Date.now() >= previewExpiresAt.value)
        previewId.value = undefined;
    } catch {
      // 请求层已展示错误，此处只结束当前加载状态。
    } finally {
      logLoading.value = false;
      statusRequest = undefined;
    }
  })();
  return statusRequest;
}

function handleTabChange(key: number | string) {
  activeTab.value = String(key) as TabKey;
  if (key === 'logs' || key === 'schedule') void loadLogs();
}

function statusLabel(status: FeishuOrganizationSyncLog['status']) {
  const keys = {
    FAILED: 'failed',
    PENDING: 'pending',
    REVIEW: 'review',
    RUNNING: 'running',
    SKIPPED: 'skipped',
    SUCCESS: 'success',
  };
  return $t(`feishuOrg.${keys[status]}`);
}

onMounted(() => {
  void loadAppConfig();
});
</script>

<template>
  <main
    class="adpulse-section-page system-management-page min-h-full p-[var(--adpulse-page-gutter)] text-slate-700"
  >
    <div
      class="mx-auto flex max-w-[1600px] flex-col gap-[var(--adpulse-section-gap)]"
    >
      <header
        class="business-page-header flex flex-wrap items-center justify-between gap-3 border px-[var(--adpulse-card-padding)] py-[var(--adpulse-page-header-padding-block)]"
      >
        <div>
          <h1
            class="text-foreground m-0 font-semibold text-[var(--adpulse-page-title-size)]"
          >
            组织架构同步
          </h1>
          <p class="m-0 mt-1 text-sm text-slate-500">
            配置飞书应用，预览组织差异并执行部门和人员同步
          </p>
        </div>
        <Button
          v-if="activeTab === 'logs'"
          :loading="logLoading"
          @click="loadLogs"
        >
          <IconifyIcon icon="lucide:refresh-cw" /> 刷新记录
        </Button>
      </header>

      <Card
        :body-style="{
          padding: '0 var(--adpulse-card-padding) var(--adpulse-card-padding)',
        }"
      >
        <Alert
          v-if="!canManage"
          class="my-4"
          :message="$t('feishuOrg.readOnly')"
          type="info"
          show-icon
        />
        <Tabs :active-key="activeTab" @change="handleTabChange">
          <Tabs.TabPane key="application" tab="应用配置">
            <Spin :spinning="configLoading">
              <Alert
                class="mb-5"
                message="此配置与文档同步共用，App Secret 保存后不会回显。"
                show-icon
                type="info"
              />
              <Form layout="vertical" class="max-w-2xl" :disabled="!canManage">
                <Form.Item label="应用名称" required>
                  <Input v-model:value="appConfig.appName" :maxlength="100" />
                </Form.Item>
                <Form.Item label="App ID" required>
                  <Input
                    v-model:value="appConfig.appId"
                    :maxlength="100"
                    placeholder="cli_xxxxxxxxxxxxxxxx"
                  />
                </Form.Item>
                <Form.Item label="App Secret">
                  <Input.Password
                    v-model:value="appConfig.appSecret"
                    autocomplete="new-password"
                    placeholder="首次配置必填；留空表示不修改"
                  />
                </Form.Item>
                <Button
                  type="primary"
                  :loading="configSaving"
                  @click="saveAppConfig"
                >
                  保存应用配置
                </Button>
              </Form>
            </Spin>
          </Tabs.TabPane>

          <Tabs.TabPane key="organization" tab="组织同步">
            <Alert
              v-if="hasActiveJob"
              class="mb-4"
              :message="$t('feishuOrg.activeTask')"
              type="info"
              show-icon
            />
            <Alert
              v-if="requiresReview && syncResult"
              class="mb-4"
              :message="$t('feishuOrg.risk')"
              type="warning"
              show-icon
            />
            <Alert
              class="mb-5"
              message="请先预览。本地数据不会被飞书覆盖，角色和数据权限也不会被同步修改。"
              show-icon
              type="info"
            />
            <div class="mb-5 flex flex-wrap gap-3">
              <Button
                :loading="syncLoading"
                :disabled="hasActiveJob"
                @click="previewSync"
              >
                <IconifyIcon icon="lucide:scan-search" /> 预览同步
              </Button>
              <Button
                type="primary"
                :disabled="
                  !canManage ||
                  hasActiveJob ||
                  !previewId ||
                  !syncResult ||
                  syncResult.conflictCount > 0
                "
                :loading="syncLoading"
                @click="confirmSync"
              >
                <IconifyIcon icon="lucide:refresh-cw" /> 确认同步
              </Button>
            </div>
            <Spin :spinning="syncLoading">
              <Empty v-if="!syncResult" description="请先生成同步预览" />
              <template v-else>
                <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <Card>
                    <Statistic
                      title="部门总数"
                      :value="syncResult.departmentTotal"
                    />
                    <div class="mt-2 text-xs text-slate-500">
                      新增 {{ syncResult.departmentCreated }} · 更新
                      {{ syncResult.departmentUpdated }} · 停用
                      {{ syncResult.departmentDisabled }}
                    </div>
                  </Card>
                  <Card>
                    <Statistic title="人员总数" :value="syncResult.userTotal" />
                    <div class="mt-2 text-xs text-slate-500">
                      新增 {{ syncResult.userCreated }} · 更新
                      {{ syncResult.userUpdated }} · 停用
                      {{ syncResult.userDisabled }}
                    </div>
                  </Card>
                  <Card>
                    <Statistic
                      title="冲突数量"
                      :value="syncResult.conflictCount"
                    />
                  </Card>
                  <Card>
                    <Statistic
                      title="可执行状态"
                      :value="
                        syncResult.conflictCount === 0 ? '可同步' : '需处理'
                      "
                    />
                  </Card>
                </div>
                <Alert
                  v-if="syncResult.conflicts.length > 0"
                  class="mt-5"
                  message="同步预览存在冲突"
                  show-icon
                  type="warning"
                >
                  <template #description>
                    <ul class="mb-0 pl-5">
                      <li v-for="item in syncResult.conflicts" :key="item">
                        {{ item }}
                      </li>
                    </ul>
                  </template>
                </Alert>
              </template>
            </Spin>
          </Tabs.TabPane>

          <Tabs.TabPane key="schedule" :tab="$t('feishuOrg.schedule')">
            <OrganizationSchedule
              v-if="schedule"
              :config="schedule"
              :can-manage="canManage"
              :preview-id="previewId"
              :preview-loading="syncLoading"
              @preview="previewSync"
              @saved="schedule = $event"
            />
            <Spin v-else :spinning="logLoading" />
          </Tabs.TabPane>

          <Tabs.TabPane key="logs" tab="同步记录">
            <Table
              :columns="logColumns"
              :data-source="logs"
              :loading="logLoading"
              :pagination="{ pageSize: 20, showSizeChanger: false }"
              row-key="id"
              :scroll="{ x: 1550 }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'triggerType'">
                  {{
                    record.triggerType === 'PREVIEW'
                      ? '预览'
                      : $t(
                          record.triggerType === 'SCHEDULED'
                            ? 'feishuOrg.scheduled'
                            : 'feishuOrg.manual',
                        )
                  }}
                </template>
                <template v-else-if="column.dataIndex === 'status'">
                  <Tag
                    :color="
                      record.status === 'SUCCESS'
                        ? 'success'
                        : record.status === 'REVIEW'
                          ? 'warning'
                          : record.status === 'FAILED'
                            ? 'error'
                            : 'processing'
                    "
                  >
                    {{ statusLabel(record.status) }}
                  </Tag>
                </template>
                <template v-else-if="column.dataIndex === 'departmentChanges'">
                  {{ record.departmentCreated }} /
                  {{ record.departmentUpdated }} /
                  {{ record.departmentDisabled }}
                </template>
                <template v-else-if="column.dataIndex === 'userChanges'">
                  {{ record.userCreated }} / {{ record.userUpdated }} /
                  {{ record.userDisabled }}
                </template>
                <template v-else-if="column.dataIndex === 'startedBy'">
                  {{ record.startedBy || $t('feishuOrg.system') }}
                </template>
                <template v-else-if="column.dataIndex === 'errorMessage'">
                  {{ record.errorMessage || '-' }}
                </template>
              </template>
              <template #emptyText>
                <Empty description="暂无同步记录" />
              </template>
            </Table>
          </Tabs.TabPane>
        </Tabs>
      </Card>
    </div>
  </main>
</template>
