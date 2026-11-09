<script lang="ts" setup>
import type {
  AlertConfig,
  AlertLimitPollInterval,
  AlertRecipient,
} from '#/api/alert-notifications';

import { computed, onMounted, reactive, ref } from 'vue';

import {
  Button,
  Card,
  Form,
  FormItem,
  message,
  Select,
  Spin,
  Switch,
  Tabs,
  TabPane,
  Tag,
  Typography,
} from 'ant-design-vue';

import {
  getAlertSettings,
  saveAlertSettings,
  sendAlertTestNotification,
} from '#/api/alert-notifications';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import { getSharedOrganizationUsers } from '#/views/components/organization-options-cache';
import MediaResourcePage from '../components/MediaResourcePage.vue';
import BanRecordsTab from './components/BanRecordsTab.vue';
import LimitChangeRecordsTab from './components/LimitChangeRecordsTab.vue';

defineOptions({ name: 'MediaResourceAlertNotifications' });

const { Paragraph, Title } = Typography;
const activeTab = ref('settings');
const loading = ref(false);
const saving = ref(false);
const testingDelivery = ref(false);
const userOptions = ref<Array<{ label: string; value: string }>>([]);
const userIds = ref<string[]>([]);
const chatIds = ref<string[]>([]);

const defaultConfig: AlertConfig = {
  banEnabled: true,
  banThreshold: 1,
  banWindowUnit: 'HOURS',
  banWindowValue: 1,
  enabled: false,
  limitChangeEnabled: true,
  limitPollIntervalMinutes: 15,
};
const config = reactive<AlertConfig>({ ...defaultConfig });
const routeState = createListRouteStateTarget({
  tab: activeTab,
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    tab: {
      codec: {
        parse(value) {
          const tab = (Array.isArray(value) ? value[0] : value) ?? undefined;
          if (tab === 'records') return 'ban-records';
          return ['ban-records', 'limit-change-records', 'settings'].includes(
            tab ?? '',
          )
            ? tab
            : 'settings';
        },
        serialize(value) {
          return value === 'settings' ? undefined : value;
        },
      },
    },
  },
  state: routeState,
});

const recipientCount = computed(
  () => userIds.value.length + chatIds.value.length,
);
const limitPollIntervalOptions: Array<{
  label: string;
  value: AlertLimitPollInterval;
}> = ([5, 10, 15, 30, 60] as const).map((minutes) => ({
  label: `${minutes} 分钟`,
  value: minutes,
}));

async function loadSettings() {
  loading.value = true;
  try {
    const [settings, users] = await Promise.all([
      getAlertSettings(),
      getSharedOrganizationUsers(),
    ]);
    Object.assign(config, settings.config);
    // 封号提醒固定按自然小时执行；旧字段仅保留用于兼容现有接口。
    config.banThreshold = 1;
    config.banWindowUnit = 'HOURS';
    config.banWindowValue = 1;
    userOptions.value = users
      .filter((user) => user.status === 1)
      .map((user) => ({ label: user.displayName, value: user.id }));
    userIds.value = settings.recipients
      .filter((item) => item.recipientType === 'USER')
      .map((item) => item.recipientKey);
    chatIds.value = settings.recipients
      .filter((item) => item.recipientType === 'CHAT')
      .map((item) => item.recipientKey);
  } finally {
    loading.value = false;
  }
}

function recipients(): AlertRecipient[] {
  const labels = new Map(
    userOptions.value.map((item) => [item.value, item.label]),
  );
  return [
    ...userIds.value.map((id) => ({
      recipientKey: id,
      recipientName: labels.get(id) ?? id,
      recipientType: 'USER' as const,
    })),
    ...chatIds.value.map((id) => ({
      recipientKey: id.trim(),
      recipientName: id.trim(),
      recipientType: 'CHAT' as const,
    })),
  ].filter((item) => item.recipientKey);
}

async function save() {
  if (config.enabled && recipientCount.value === 0) {
    message.warning(
      '开启自动预警前，请至少选择一位系统用户或填写一个飞书群 Chat ID',
    );
    return;
  }
  saving.value = true;
  try {
    await saveAlertSettings({ ...config, recipients: recipients() });
    message.success('预警配置已保存');
  } finally {
    saving.value = false;
  }
}

async function sendTestNotification() {
  const targets = recipients();
  if (targets.length === 0) {
    message.warning('请先选择系统用户或填写飞书群 Chat ID');
    return;
  }

  testingDelivery.value = true;
  try {
    const result = await sendAlertTestNotification(targets);
    if (result.failedCount === 0) {
      message.success(`测试消息已发送至 ${result.successCount} 个目标`);
    } else if (result.successCount === 0) {
      message.error(`测试消息发送失败，共 ${result.failedCount} 个目标`);
    } else {
      message.warning(
        `测试消息部分发送成功：成功 ${result.successCount} 个，失败 ${result.failedCount} 个`,
      );
    }
  } finally {
    testingDelivery.value = false;
  }
}

async function handleTabChange(key: string | number) {
  activeTab.value = String(key);
  await commitQueryState();
}

onMounted(async () => {
  await restoreFromRoute();
  await loadSettings();
});
</script>

<template>
  <MediaResourcePage>
    <Card :bordered="false" class="alert-page-header">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Title :level="3" class="!mb-1">预警通知</Title>
          <Paragraph class="text-muted-foreground !mb-0">
            统一管理广告户封号与限额变化通知，并直接查询 Facebook
            平台同步产生的原始事件。
          </Paragraph>
        </div>
        <Tag color="default">
          封号每小时，10:00、18:30、24:00 汇总 · 限额每
          {{ config.limitPollIntervalMinutes }} 分钟
        </Tag>
      </div>
    </Card>

    <Card :bordered="false" class="alert-content-card">
      <Tabs :active-key="activeTab" @change="handleTabChange">
        <TabPane key="settings" tab="通知配置">
          <Spin :spinning="loading">
            <Form layout="vertical" class="alert-form">
              <section class="rule-section rule-section--master">
                <div>
                  <div class="rule-title">开启自动预警通知</div>
                  <div class="rule-help">
                    关闭后保留配置和历史记录，但不再创建新提醒。
                  </div>
                </div>
                <Switch
                  v-model:checked="config.enabled"
                  aria-label="开启自动预警通知"
                />
              </section>

              <section class="rule-section">
                <div class="rule-heading">
                  <div>
                    <div class="rule-title">收件目标</div>
                    <div class="rule-help">
                      系统用户发送飞书私聊；群聊请填写机器人所在群的 Chat ID。
                    </div>
                  </div>
                  <div class="recipient-actions">
                    <Tag>{{ recipientCount }} 个目标</Tag>
                    <Button
                      :disabled="recipientCount === 0"
                      :loading="testingDelivery"
                      @click="sendTestNotification"
                    >
                      发送测试通知
                    </Button>
                  </div>
                </div>
                <div class="field-grid field-grid--single">
                  <FormItem label="系统用户">
                    <Select
                      v-model:value="userIds"
                      allow-clear
                      mode="multiple"
                      option-filter-prop="label"
                      :options="userOptions"
                      placeholder="选择接收飞书私聊的系统用户"
                    />
                  </FormItem>
                  <FormItem
                    label="飞书群 Chat ID"
                    extra="输入后按回车，可添加多个群。"
                  >
                    <Select
                      v-model:value="chatIds"
                      mode="tags"
                      placeholder="例如 oc_xxxxxxxxxxxxxxxx"
                      :token-separators="[',', ' ']"
                    />
                  </FormItem>
                </div>
              </section>

              <section class="rule-section">
                <div class="rule-heading">
                  <div>
                    <div class="rule-title">封号小时提醒</div>
                    <div class="rule-help">
                      每小时整点发送最近一个自然小时内的封号广告户；每天
                      10:00、18:30、24:00 额外发送当天累计汇总。
                    </div>
                  </div>
                  <Switch
                    v-model:checked="config.banEnabled"
                    aria-label="开启封号小时提醒"
                  />
                </div>
              </section>

              <section class="rule-section">
                <div class="rule-heading">
                  <div>
                    <div class="rule-title">限额更新通知</div>
                    <div class="rule-help">
                      account_dsl
                      设置、提高、降低或清空时逐事件提醒；首次基线不提醒。
                    </div>
                  </div>
                  <Switch
                    v-model:checked="config.limitChangeEnabled"
                    aria-label="开启限额更新通知"
                  />
                </div>
                <div class="field-grid">
                  <FormItem
                    label="轮询间隔"
                    extra="每次只查询最近所选时长内新生成的限额变化记录。"
                  >
                    <Select
                      v-model:value="config.limitPollIntervalMinutes"
                      :disabled="!config.limitChangeEnabled"
                      :options="limitPollIntervalOptions"
                    />
                  </FormItem>
                </div>
              </section>

              <div class="action-bar">
                <Button type="primary" :loading="saving" @click="save"
                  >保存配置</Button
                >
              </div>
            </Form>
          </Spin>
        </TabPane>

        <TabPane key="ban-records" tab="封户记录">
          <BanRecordsTab :active="activeTab === 'ban-records'" />
        </TabPane>

        <TabPane key="limit-change-records" tab="限额变更记录">
          <LimitChangeRecordsTab
            :active="activeTab === 'limit-change-records'"
          />
        </TabPane>
      </Tabs>
    </Card>
  </MediaResourcePage>
</template>

<style scoped>
.alert-page-header,
.alert-content-card {
  border: 1px solid hsl(var(--border));
  box-shadow: none;
}

.alert-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rule-section {
  padding: 16px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
}

.rule-section--master,
.rule-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.rule-title {
  color: hsl(var(--foreground));
  font-size: 15px;
  font-weight: 600;
  line-height: 24px;
}

.rule-help {
  margin-top: 2px;
  color: hsl(var(--muted-foreground));
  font-size: 13px;
  line-height: 20px;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.field-grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.action-bar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
}

.recipient-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 900px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .rule-section--master,
  .rule-heading {
    align-items: center;
  }

  .action-bar {
    flex-direction: column-reverse;
  }

  .recipient-actions {
    justify-content: flex-start;
  }
}
</style>
