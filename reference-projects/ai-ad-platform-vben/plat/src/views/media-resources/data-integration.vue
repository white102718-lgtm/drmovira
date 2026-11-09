<script lang="ts" setup>
import type {
  GoogleAccount,
  GoogleMapping,
  GoogleMappingId,
  GoogleSheetTab,
} from '#/api/data-integration';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Dropdown,
  Empty,
  Flex,
  Menu,
  MenuItem,
  message,
  Modal,
  Spin,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'ant-design-vue';

import {
  deleteGoogleMapping,
  disconnectGoogleAccount,
  getGoogleAccountList,
  getGoogleOAuthUrl,
  getGoogleSheetTabs,
  reauthorizeGoogleAccount,
  removeGoogleAccount,
  syncGoogleMapping,
  updateGoogleMappingStatus,
} from '#/api/data-integration';

import DataIntegrationMappingModal from './components/data-integration-mapping-modal.vue';
import DataIntegrationSyncLogDrawer from './components/data-integration-sync-log-drawer.vue';
import MediaResourcePage from './components/MediaResourcePage.vue';

interface MappingView {
  dateRangeLabel: string;
  direction: 'bidirectional' | 'read' | 'write';
  enabled: boolean;
  googleSheet: string;
  id: GoogleMappingId;
  lastSync: string;
  name: string;
  raw: GoogleMapping;
  reportType: number;
  sheetTabs: Array<
    Partial<Pick<GoogleSheetTab, 'id'>> & Pick<GoogleSheetTab, 'title'>
  >;
  spreadsheetId: string;
  syncFreqLabel: string;
  syncing: boolean;
}

interface AccountView {
  authorizedAt: string;
  email: string;
  id: GoogleAccount['id'];
  mappings: MappingView[];
  status: 'connected' | 'expired';
}

interface MappingModalExpose {
  open: (options: {
    accountId: GoogleAccount['id'];
    email: string;
    mapping?: GoogleMapping;
  }) => Promise<void>;
}

interface SyncLogDrawerExpose {
  open: (options: { id: GoogleMappingId; name: string }) => Promise<void>;
}

const accounts = ref<AccountView[]>([]);
const loading = ref(false);
const loadError = ref('');
const mappingModal = ref<MappingModalExpose>();
const syncLogDrawer = ref<SyncLogDrawerExpose>();
const router = useRouter();
const { Paragraph, Text, Title } = Typography;

const mappingColumns = [
  { key: 'name', title: '配置名称', width: 220 },
  { key: 'reportType', title: '系统报表', width: 120 },
  {
    dataIndex: 'googleSheet',
    key: 'googleSheet',
    title: 'Google 表格 / Sheet',
    width: 280,
  },
  { key: 'direction', title: '同步方向', width: 120 },
  {
    dataIndex: 'dateRangeLabel',
    key: 'dateRangeLabel',
    title: '日期范围',
    width: 180,
  },
  {
    dataIndex: 'syncFreqLabel',
    key: 'syncFreqLabel',
    title: '自动同步',
    width: 150,
  },
  { key: 'enabled', title: '状态', width: 100 },
  { fixed: 'right' as const, key: 'action', title: '操作', width: 230 },
];

const connectedAccountCount = computed(
  () =>
    accounts.value.filter((account) => account.status === 'connected').length,
);

function parseDateRangeConfig(mapping: GoogleMapping) {
  if (mapping.dateRangeType === 3) return '本月';
  try {
    const config = JSON.parse(mapping.dateRangeConfig || '{}') as {
      days?: number;
      endDate?: string;
      startDate?: string;
    };
    if (mapping.dateRangeType === 2) return `最近 ${config.days || 7} 天`;
    if (mapping.dateRangeType === 1 && config.startDate && config.endDate) {
      return `${config.startDate} 至 ${config.endDate}`;
    }
  } catch {
    // Invalid legacy configuration falls back to an em dash.
  }
  return '—';
}

function formatSyncFrequency(mapping: GoogleMapping) {
  if (mapping.syncFrequency === 1) return '手动';
  if (mapping.syncFrequency === 2) return `每天 ${mapping.syncTime || '00:00'}`;
  if (mapping.syncFrequency === 3) return '每小时';
  return '—';
}

function formatMapping(mapping: GoogleMapping): MappingView {
  const directions: Record<number, MappingView['direction']> = {
    1: 'read',
    2: 'write',
    3: 'bidirectional',
  };
  return {
    dateRangeLabel: parseDateRangeConfig(mapping),
    direction: directions[mapping.syncDirection ?? 2] ?? 'write',
    enabled: mapping.enableFlag === 1,
    googleSheet: mapping.spreadsheetName || '',
    id: mapping.id,
    lastSync: mapping.lastSyncTime
      ? mapping.lastSyncTime.slice(0, 16).replace('T', ' ')
      : '从未',
    name: mapping.name,
    raw: mapping,
    reportType: mapping.reportType ?? 1,
    sheetTabs: parseSheetNames(mapping.sheetNames).map((title) => ({ title })),
    spreadsheetId: mapping.spreadsheetId,
    syncing: false,
    syncFreqLabel: formatSyncFrequency(mapping),
  };
}

function parseSheetNames(value?: string) {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === 'string')
      : [];
  } catch {
    return [];
  }
}

function spreadsheetUrl(mapping: MappingView, sheetId?: string) {
  const baseUrl = `https://docs.google.com/spreadsheets/d/${encodeURIComponent(mapping.spreadsheetId)}/edit`;
  return sheetId ? `${baseUrl}#gid=${encodeURIComponent(sheetId)}` : baseUrl;
}

function formatAccount(account: GoogleAccount): AccountView {
  return {
    authorizedAt: account.authorizedAt?.slice(0, 10) ?? '',
    email: account.email,
    id: account.id,
    mappings: (account.mappings ?? []).map((mapping) => formatMapping(mapping)),
    status: account.authStatus === 1 ? 'connected' : 'expired',
  };
}

async function hydrateSheetTabs(accountViews: AccountView[]) {
  const requests = new Map<string, Promise<GoogleSheetTab[]>>();
  const tasks = accountViews.flatMap((account) =>
    account.mappings.map(async (mapping) => {
      const requestKey = `${account.id}:${mapping.spreadsheetId}`;
      let request = requests.get(requestKey);
      if (!request) {
        request = getGoogleSheetTabs({
          accountId: account.id,
          fileId: mapping.spreadsheetId,
        });
        requests.set(requestKey, request);
      }
      try {
        const selectedTitles = new Set(
          mapping.sheetTabs.map((sheet) => sheet.title),
        );
        mapping.sheetTabs = (await request).filter((sheet) =>
          selectedTitles.has(sheet.title),
        );
      } catch {
        // Google 元数据加载失败时保留表格级链接，不阻断映射列表。
      }
    }),
  );
  await Promise.all(tasks);
}

function isMappingView(mapping: unknown): mapping is MappingView {
  if (
    typeof mapping !== 'object' ||
    mapping === null ||
    !('id' in mapping) ||
    !('raw' in mapping) ||
    !('name' in mapping)
  ) {
    return false;
  }
  const candidate = mapping as {
    id: unknown;
    name: unknown;
    raw: unknown;
  };
  if (
    (typeof candidate.id !== 'number' && typeof candidate.id !== 'string') ||
    typeof candidate.name !== 'string' ||
    typeof candidate.raw !== 'object' ||
    candidate.raw === null
  ) {
    return false;
  }
  return true;
}

function asMapping(mapping: unknown): MappingView {
  if (!isMappingView(mapping)) throw new Error('映射数据格式无效');
  return mapping;
}

async function getList() {
  loading.value = true;
  loadError.value = '';
  try {
    const accountList = await getGoogleAccountList();
    accounts.value = accountList.map((account) => formatAccount(account));
    await hydrateSheetTabs(accounts.value);
  } catch (error) {
    loadError.value =
      error instanceof Error ? error.message : 'Google 账号加载失败';
  } finally {
    loading.value = false;
  }
}

async function handleAuthorize() {
  const authorizeUrl = await getGoogleOAuthUrl();
  if (authorizeUrl) window.open(authorizeUrl, '_blank', 'noopener,noreferrer');
}

function handleDisconnect(account: AccountView) {
  Modal.confirm({
    content: '断开后该账号下所有映射配置将停止同步，是否继续？',
    okButtonProps: { danger: true },
    okText: '确认断开',
    title: '断开连接',
    onOk: async () => {
      await disconnectGoogleAccount(account.id);
      message.success('已断开连接');
      await getList();
    },
  });
}

async function handleReauthorize(account: AccountView) {
  const authorizeUrl = await reauthorizeGoogleAccount(account.id);
  if (authorizeUrl) window.open(authorizeUrl, '_blank', 'noopener,noreferrer');
}

function handleRemove(account: AccountView) {
  Modal.confirm({
    content: '删除后该账号及其所有映射配置将一并删除，是否继续？',
    okButtonProps: { danger: true },
    okText: '确认移除',
    title: '移除账号',
    onOk: async () => {
      await removeGoogleAccount(account.id);
      message.success('已移除账号');
      await getList();
    },
  });
}

function handleAddMapping(account: AccountView) {
  void mappingModal.value?.open({
    accountId: account.id,
    email: account.email,
  });
}

function handleEdit(account: AccountView, mapping: MappingView) {
  void mappingModal.value?.open({
    accountId: account.id,
    email: account.email,
    mapping: mapping.raw,
  });
}

function handleViewData(mapping: MappingView) {
  void router.push({
    path: `/system-management/data-integration/${mapping.id}/data`,
    query: { name: mapping.name },
  });
}

function handleViewLogs(mapping: MappingView) {
  void syncLogDrawer.value?.open({ id: mapping.id, name: mapping.name });
}

async function handleSync(mapping: MappingView) {
  mapping.syncing = true;
  try {
    await syncGoogleMapping(mapping.id);
    message.success('同步已触发');
    await getList();
  } finally {
    mapping.syncing = false;
  }
}

async function handleEnable(mapping: MappingView) {
  await updateGoogleMappingStatus(mapping.id, 1);
  mapping.enabled = true;
  message.success('已启用');
}

async function handleDisable(mapping: MappingView) {
  await updateGoogleMappingStatus(mapping.id, 0);
  mapping.enabled = false;
  message.success('已停用');
}

function handleDeleteMapping(mapping: MappingView) {
  Modal.confirm({
    content: '确定要删除该映射配置吗？删除后不可恢复。',
    okButtonProps: { danger: true },
    okText: '确认删除',
    title: '删除映射',
    onOk: async () => {
      await deleteGoogleMapping(mapping.id);
      message.success('已删除');
      await getList();
    },
  });
}

function directionText(direction: MappingView['direction']) {
  if (direction === 'write') return '写入 →';
  if (direction === 'read') return '← 读取';
  return '⇄ 双向';
}

onMounted(getList);
</script>

<template>
  <MediaResourcePage>
    <Card>
      <Flex align="center" gap="middle" justify="space-between" wrap="wrap">
        <Space align="start">
          <IconifyIcon icon="logos:google-icon" :style="{ fontSize: '32px' }" />
          <Space direction="vertical" :size="2">
            <Space wrap>
              <Title :level="3" :style="{ margin: 0 }">Google 账号管理</Title>
              <Tag color="blue">{{ connectedAccountCount }} 个账号已连接</Tag>
            </Space>
            <Paragraph type="secondary" :style="{ margin: 0 }">
              统一管理 Google 授权，并配置系统报表与 Google Sheets
              之间的字段映射和自动同步规则。
            </Paragraph>
          </Space>
        </Space>
        <Space>
          <Button type="primary" @click="handleAuthorize">
            <template #icon><IconifyIcon icon="lucide:plus" /></template>
            授权新账号
          </Button>
          <Tooltip title="刷新账号列表">
            <Button :loading="loading" @click="getList">
              <template #icon
                ><IconifyIcon icon="lucide:refresh-cw"
              /></template>
            </Button>
          </Tooltip>
        </Space>
      </Flex>
    </Card>

    <Alert
      v-if="loadError"
      :message="loadError"
      class="!rounded-xl !border-red-200"
      show-icon
      type="error"
    >
      <template #action>
        <Button @click="getList">重新加载</Button>
      </template>
    </Alert>

    <Spin :spinning="loading">
      <div class="flex min-h-48 flex-col gap-5">
        <Card
          v-for="account in accounts"
          :key="account.id"
          :body-style="{ padding: 0 }"
        >
          <template #title>
            <Space>
              <IconifyIcon
                icon="logos:google-icon"
                :style="{ fontSize: '24px' }"
              />
              <Space direction="vertical" :size="0">
                <Text strong>{{ account.email }}</Text>
                <Text v-if="account.status === 'connected'" type="secondary">
                  授权于 {{ account.authorizedAt || '—' }} ·
                  {{ account.mappings.length }} 个映射配置
                </Text>
                <Text v-else type="warning"
                  >授权已过期，请重新授权以恢复同步</Text
                >
              </Space>
            </Space>
          </template>
          <template #extra>
            <Space wrap>
              <template v-if="account.status === 'connected'">
                <Tag color="success">已连接</Tag>
                <Button danger @click="handleDisconnect(account)"
                  >断开连接</Button
                >
              </template>
              <template v-else>
                <Tag color="warning">已过期</Tag>
                <Button type="primary" @click="handleReauthorize(account)"
                  >重新授权</Button
                >
                <Button danger type="link" @click="handleRemove(account)"
                  >移除</Button
                >
              </template>
            </Space>
          </template>

          <template v-if="account.status === 'connected'">
            <Table
              :columns="mappingColumns"
              :data-source="account.mappings"
              :pagination="false"
              :row-key="(mapping: MappingView) => mapping.id"
              :scroll="{ x: 1200 }"
            >
              <template #bodyCell="{ column, record: mapping }">
                <template v-if="column.key === 'name'">
                  <Space direction="vertical" :size="0">
                    <Text strong>{{ mapping.name }}</Text>
                    <Text type="secondary"
                      >最后同步：{{ mapping.lastSync }}</Text
                    >
                  </Space>
                </template>
                <template v-else-if="column.key === 'reportType'">{{
                  mapping.reportType === 1 ? '任务中心' : '—'
                }}</template>
                <template v-else-if="column.key === 'googleSheet'">
                  <Space direction="vertical" :size="6" class="max-w-64">
                    <a
                      :aria-label="`在新窗口打开 Google 表格：${mapping.googleSheet}`"
                      class="text-primary inline-flex items-center gap-1.5 font-medium hover:underline"
                      :href="spreadsheetUrl(asMapping(mapping))"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <IconifyIcon
                        aria-hidden="true"
                        icon="lucide:file-spreadsheet"
                      />
                      <span class="truncate">{{
                        mapping.googleSheet || '未命名表格'
                      }}</span>
                      <IconifyIcon
                        aria-hidden="true"
                        class="shrink-0 text-xs"
                        icon="lucide:external-link"
                      />
                    </a>
                    <div class="flex flex-wrap gap-1.5">
                      <a
                        v-for="sheet in asMapping(mapping).sheetTabs"
                        :key="sheet.title"
                        :aria-label="`在新窗口打开 Sheet：${sheet.title}`"
                        :href="spreadsheetUrl(asMapping(mapping), sheet.id)"
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        <Tag
                          class="hover:!border-primary hover:!text-primary !m-0 cursor-pointer transition-colors"
                        >
                          {{ sheet.title }}
                          <IconifyIcon
                            aria-hidden="true"
                            class="ml-1 text-xs"
                            icon="lucide:external-link"
                          />
                        </Tag>
                      </a>
                      <Text
                        v-if="asMapping(mapping).sheetTabs.length === 0"
                        type="secondary"
                      >
                        未选择 Sheet
                      </Text>
                    </div>
                  </Space>
                </template>
                <template v-else-if="column.key === 'direction'">{{
                  directionText(mapping.direction)
                }}</template>
                <template v-else-if="column.key === 'enabled'">
                  <Tag :color="mapping.enabled ? 'success' : 'default'">{{
                    mapping.enabled ? '启用' : '停用'
                  }}</Tag>
                </template>
                <template v-else-if="column.key === 'action'">
                  <Space :size="4">
                    <Button
                      type="link"
                      @click="handleEdit(account, asMapping(mapping))"
                    >
                      编辑
                    </Button>
                    <Button
                      type="link"
                      @click="handleViewData(asMapping(mapping))"
                    >
                      同步数据
                    </Button>
                    <Dropdown trigger="click">
                      <Button type="link">
                        更多
                        <IconifyIcon icon="lucide:chevron-down" />
                      </Button>
                      <template #overlay>
                        <Menu>
                          <template v-if="mapping.enabled">
                            <MenuItem
                              @click="handleViewLogs(asMapping(mapping))"
                            >
                              同步日志
                            </MenuItem>
                            <MenuItem
                              :disabled="mapping.syncing"
                              @click="handleSync(asMapping(mapping))"
                            >
                              {{ mapping.syncing ? '同步中…' : '立即同步' }}
                            </MenuItem>
                            <MenuItem
                              danger
                              @click="handleDisable(asMapping(mapping))"
                            >
                              停用
                            </MenuItem>
                          </template>
                          <template v-else>
                            <MenuItem
                              @click="handleViewLogs(asMapping(mapping))"
                            >
                              同步日志
                            </MenuItem>
                            <MenuItem @click="handleEnable(asMapping(mapping))">
                              启用
                            </MenuItem>
                            <MenuItem
                              danger
                              @click="handleDeleteMapping(asMapping(mapping))"
                            >
                              删除
                            </MenuItem>
                          </template>
                        </Menu>
                      </template>
                    </Dropdown>
                  </Space>
                </template>
              </template>
              <template #emptyText
                ><Empty
                  :image="Empty.PRESENTED_IMAGE_SIMPLE"
                  description="暂无映射配置"
              /></template>
            </Table>
            <Button block type="dashed" @click="handleAddMapping(account)">
              <template #icon><IconifyIcon icon="lucide:plus" /></template>
              新建映射配置
            </Button>
          </template>
        </Card>

        <Card
          v-if="!loading && !loadError && accounts.length === 0"
          :body-style="{ padding: '52px 24px' }"
          class="!rounded-2xl !border-slate-200/80 shadow-sm dark:!border-slate-800"
        >
          <Empty :image="Empty.PRESENTED_IMAGE_SIMPLE">
            <template #description>
              <div class="mx-auto max-w-md text-center">
                <div
                  class="text-base font-medium text-slate-800 dark:text-slate-200"
                >
                  还没有已授权的 Google 账号
                </div>
                <div class="mt-1.5 text-sm leading-6 text-slate-500">
                  完成授权后，即可创建报表与 Google Sheets 的数据同步配置。
                </div>
              </div>
            </template>
            <Button
              class="mt-4 !rounded-lg"
              type="primary"
              @click="handleAuthorize"
            >
              <IconifyIcon icon="lucide:plus" />授权第一个账号
            </Button>
          </Empty>
        </Card>
      </div>
    </Spin>

    <DataIntegrationMappingModal ref="mappingModal" @success="getList" />
    <DataIntegrationSyncLogDrawer ref="syncLogDrawer" />
  </MediaResourcePage>
</template>
