<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Popconfirm,
  Row,
  Select,
  Table,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

type BindingStatus = 'active' | 'expired' | 'expiring' | 'unbound';
type Platform = 'facebook' | 'google' | 'kwai' | 'tiktok';

interface AccountBinding {
  accountId: string;
  accountName: string;
  boundAt: string;
  deliveryLine: string;
  id: string;
  lastSyncAt: string;
  note?: string;
  owner: string;
  platform: Platform;
  project: string;
  status: BindingStatus;
}

interface BindingFormState {
  accountId?: string;
  deliveryLine?: string;
  note: string;
  owner?: string;
  platform: Platform;
  project?: string;
}

const platformMeta: Record<
  Platform,
  { color: string; icon: string; label: string }
> = {
  facebook: {
    color: 'blue',
    icon: 'simple-icons:facebook',
    label: 'Facebook',
  },
  google: {
    color: 'geekblue',
    icon: 'simple-icons:googleads',
    label: 'Google',
  },
  kwai: {
    color: 'orange',
    icon: 'simple-icons:kuaishou',
    label: 'Kwai',
  },
  tiktok: {
    color: 'default',
    icon: 'simple-icons:tiktok',
    label: 'TikTok',
  },
};

const statusMeta: Record<BindingStatus, { color: string; label: string }> = {
  active: { color: 'success', label: '绑定正常' },
  expiring: { color: 'warning', label: '授权即将到期' },
  expired: { color: 'error', label: '授权已失效' },
  unbound: { color: 'default', label: '已解绑' },
};

const projectLines: Record<string, string[]> = {
  'Pixel Quest 日本首发': ['日本首发'],
  'Project Ark 美国市场': ['美国市场拓量', 'Google 搜索增长'],
  'Starfall 全球增长': ['全球规模化', '拉美增量测试'],
};

const accountPool: Record<
  Platform,
  { accountId: string; accountName: string }[]
> = {
  facebook: [
    { accountId: 'act_7329184062', accountName: 'Starfall FB 全球主账户' },
    { accountId: 'act_6247301958', accountName: 'Project Ark FB 美国账户' },
  ],
  google: [
    { accountId: '887-201-4608', accountName: 'Project Ark Google Ads' },
    { accountId: '506-314-7920', accountName: 'Starfall Google 全球账户' },
  ],
  kwai: [
    { accountId: 'kw_760241985', accountName: 'Project Ark Kwai 巴西账户' },
    { accountId: 'kw_860219476', accountName: 'Starfall Kwai 拉美账户' },
  ],
  tiktok: [
    { accountId: 'tt_9182047635', accountName: 'Pixel Quest TikTok 日本账户' },
    { accountId: 'tt_1724069853', accountName: 'Starfall TikTok 全球账户' },
  ],
};

const ownerOptions = ['陈航', '林琦', '赵宁', '李想'].map((value) => ({
  label: value,
  value,
}));

const bindings = ref<AccountBinding[]>([
  {
    accountId: 'act_7329184062',
    accountName: 'Starfall FB 全球主账户',
    boundAt: '2026-08-01 09:20',
    deliveryLine: '全球规模化',
    id: 'binding-001',
    lastSyncAt: '2026-08-11 10:18',
    owner: '陈航',
    platform: 'facebook',
    project: 'Starfall 全球增长',
    status: 'active',
  },
  {
    accountId: '506-314-7920',
    accountName: 'Starfall Google 全球账户',
    boundAt: '2026-08-03 14:40',
    deliveryLine: '全球规模化',
    id: 'binding-002',
    lastSyncAt: '2026-08-11 10:08',
    owner: '陈航',
    platform: 'google',
    project: 'Starfall 全球增长',
    status: 'active',
  },
  {
    accountId: 'tt_9182047635',
    accountName: 'Pixel Quest TikTok 日本账户',
    boundAt: '2026-08-05 11:12',
    deliveryLine: '日本首发',
    id: 'binding-003',
    lastSyncAt: '2026-08-11 09:46',
    owner: '赵宁',
    platform: 'tiktok',
    project: 'Pixel Quest 日本首发',
    status: 'expiring',
  },
  {
    accountId: 'kw_760241985',
    accountName: 'Project Ark Kwai 巴西账户',
    boundAt: '2026-07-26 16:05',
    deliveryLine: '美国市场拓量',
    id: 'binding-004',
    lastSyncAt: '2026-08-10 22:30',
    owner: '林琦',
    platform: 'kwai',
    project: 'Project Ark 美国市场',
    status: 'expired',
  },
  {
    accountId: '887-201-4608',
    accountName: 'Project Ark Google Ads',
    boundAt: '2026-07-18 10:30',
    deliveryLine: 'Google 搜索增长',
    id: 'binding-005',
    lastSyncAt: '-',
    owner: '李想',
    platform: 'google',
    project: 'Project Ark 美国市场',
    status: 'unbound',
  },
]);

const filters = reactive({
  deliveryLine: 'all',
  owner: 'all',
  project: 'all',
  status: 'all',
});

const drawerOpen = ref(false);
const saving = ref(false);
const syncingId = ref('');

const bindingForm = reactive<BindingFormState>({
  accountId: undefined,
  deliveryLine: undefined,
  note: '',
  owner: undefined,
  platform: 'facebook',
  project: undefined,
});

const columns: TableColumnsType<AccountBinding> = [
  { key: 'account', title: '账户 / 平台', width: '27%' },
  { key: 'assignment', title: '项目 / 投放线 / 负责人', width: '31%' },
  { key: 'status', title: '状态 / 最近同步', width: '22%' },
  { key: 'actions', title: '操作', width: '20%' },
];

const projectOptions = Object.keys(projectLines).map((value) => ({
  label: value,
  value,
}));

const deliveryLineOptions = computed(() => {
  if (bindingForm.project) {
    return (projectLines[bindingForm.project] ?? []).map((value) => ({
      label: value,
      value,
    }));
  }
  return [...new Set(Object.values(projectLines).flat())].map((value) => ({
    label: value,
    value,
  }));
});

const filterDeliveryLineOptions = computed(() => [
  { label: '全部投放线', value: 'all' },
  ...[...new Set(Object.values(projectLines).flat())].map((value) => ({
    label: value,
    value,
  })),
]);

const platformOptions = Object.entries(platformMeta).map(([value, item]) => ({
  label: item.label,
  value,
}));

const accountOptions = computed(() =>
  accountPool[bindingForm.platform].map((item) => ({
    label: `${item.accountName} · ${item.accountId}`,
    value: item.accountId,
  })),
);

const filteredBindings = computed(() =>
  bindings.value.filter(
    (item) =>
      (filters.project === 'all' || item.project === filters.project) &&
      (filters.deliveryLine === 'all' ||
        item.deliveryLine === filters.deliveryLine) &&
      (filters.owner === 'all' || item.owner === filters.owner) &&
      (filters.status === 'all' || item.status === filters.status),
  ),
);

const summary = computed(() => [
  {
    icon: 'lucide:link-2',
    label: '有效绑定',
    tone: 'bg-blue-50 text-blue-600',
    value: bindings.value.filter((item) => item.status === 'active').length,
  },
  {
    icon: 'lucide:layers-3',
    label: '已接入平台',
    tone: 'bg-violet-50 text-violet-600',
    value: new Set(
      bindings.value
        .filter((item) => item.status !== 'unbound')
        .map((item) => item.platform),
    ).size,
  },
  {
    icon: 'lucide:triangle-alert',
    label: '待处理授权',
    tone: 'bg-amber-50 text-amber-600',
    value: bindings.value.filter((item) =>
      ['expired', 'expiring'].includes(item.status),
    ).length,
  },
  {
    icon: 'lucide:folder-kanban',
    label: '覆盖项目',
    tone: 'bg-emerald-50 text-emerald-600',
    value: new Set(
      bindings.value
        .filter((item) => item.status !== 'unbound')
        .map((item) => item.project),
    ).size,
  },
]);

function resetFilters() {
  Object.assign(filters, {
    deliveryLine: 'all',
    owner: 'all',
    project: 'all',
    status: 'all',
  });
}

function resetBindingForm() {
  Object.assign(bindingForm, {
    accountId: undefined,
    deliveryLine: undefined,
    note: '',
    owner: undefined,
    platform: 'facebook',
    project: undefined,
  });
}

function openBindingDrawer() {
  resetBindingForm();
  drawerOpen.value = true;
}

function platformInfo(value: unknown) {
  return platformMeta[value as Platform] ?? platformMeta.facebook;
}

function statusInfo(value: unknown) {
  return statusMeta[value as BindingStatus] ?? statusMeta.unbound;
}

function onProjectChange() {
  const availableLines = bindingForm.project
    ? (projectLines[bindingForm.project] ?? [])
    : [];
  if (!availableLines.includes(bindingForm.deliveryLine ?? '')) {
    bindingForm.deliveryLine = availableLines[0];
  }
}

function onPlatformChange() {
  bindingForm.accountId = undefined;
}

async function submitBinding() {
  if (
    !bindingForm.project ||
    !bindingForm.deliveryLine ||
    !bindingForm.accountId ||
    !bindingForm.owner
  ) {
    message.warning('请完整填写项目、投放线、广告账户和负责人');
    return;
  }

  const duplicated = bindings.value.some(
    (item) =>
      item.platform === bindingForm.platform &&
      item.accountId === bindingForm.accountId &&
      item.project === bindingForm.project &&
      item.deliveryLine === bindingForm.deliveryLine &&
      item.status !== 'unbound',
  );
  if (duplicated) {
    message.warning('该广告账户已绑定到当前项目和投放线');
    return;
  }

  saving.value = true;
  await new Promise((resolve) => setTimeout(resolve, 450));
  const account = accountPool[bindingForm.platform].find(
    (item) => item.accountId === bindingForm.accountId,
  );
  const now = dayjs().format('YYYY-MM-DD HH:mm');
  bindings.value.unshift({
    accountId: bindingForm.accountId,
    accountName: account?.accountName ?? '未命名广告账户',
    boundAt: now,
    deliveryLine: bindingForm.deliveryLine,
    id: `binding-${Date.now()}`,
    lastSyncAt: now,
    note: bindingForm.note,
    owner: bindingForm.owner,
    platform: bindingForm.platform,
    project: bindingForm.project,
    status: 'active',
  });
  saving.value = false;
  drawerOpen.value = false;
  message.success('广告账户绑定成功');
}

async function syncBinding(record: AccountBinding | Record<string, unknown>) {
  const binding = record as AccountBinding;
  syncingId.value = binding.id;
  await new Promise((resolve) => setTimeout(resolve, 500));
  binding.lastSyncAt = dayjs().format('YYYY-MM-DD HH:mm');
  syncingId.value = '';
  message.success(`${binding.accountName} 同步完成`);
}

function renewBinding(record: AccountBinding | Record<string, unknown>) {
  const binding = record as AccountBinding;
  binding.status = 'active';
  binding.lastSyncAt = dayjs().format('YYYY-MM-DD HH:mm');
  message.success('授权已恢复，账户可以继续投放');
}

function unbind(record: AccountBinding | Record<string, unknown>) {
  const binding = record as AccountBinding;
  binding.status = 'unbound';
  binding.lastSyncAt = '-';
  message.success('已解除该账户与投放线的绑定');
}
</script>

<template>
  <Page auto-content-height class="bg-slate-50" content-class="pb-6">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <div
        class="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <div class="flex items-center gap-2">
            <div
              class="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600"
            >
              <IconifyIcon icon="lucide:link-2" class="text-xl" />
            </div>
            <div>
              <h1 class="m-0 text-lg font-semibold text-slate-900">
                广告账户绑定
              </h1>
              <p class="m-0 mt-1 text-sm text-slate-500">
                将平台广告账户绑定到具体项目与投放线，明确数据、权限和负责人归属。
              </p>
            </div>
          </div>
        </div>
        <Button
          type="primary"
          class="self-start sm:self-auto"
          @click="openBindingDrawer"
        >
          <template #icon>
            <IconifyIcon icon="lucide:plus" />
          </template>
          新增绑定
        </Button>
      </div>

      <Row :gutter="[12, 12]">
        <Col
          v-for="item in summary"
          :key="item.label"
          :xs="12"
          :sm="12"
          :lg="6"
        >
          <Card
            :bordered="false"
            class="h-full border border-slate-200 shadow-sm"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm text-slate-500">{{ item.label }}</div>
                <div class="mt-1 text-2xl font-semibold text-slate-900">
                  {{ item.value }}
                </div>
              </div>
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" class="text-xl" />
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Card :bordered="false" class="border border-slate-200 shadow-sm">
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Select
            v-model:value="filters.project"
            :options="[{ label: '全部项目', value: 'all' }, ...projectOptions]"
            placeholder="项目"
          />
          <Select
            v-model:value="filters.deliveryLine"
            :options="filterDeliveryLineOptions"
            placeholder="投放线"
          />
          <Select
            v-model:value="filters.owner"
            :options="[{ label: '全部负责人', value: 'all' }, ...ownerOptions]"
            placeholder="负责人"
          />
          <Select
            v-model:value="filters.status"
            :options="[
              { label: '全部状态', value: 'all' },
              ...Object.entries(statusMeta).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
            placeholder="绑定状态"
          />
          <Button
            class="md:justify-self-start xl:justify-self-stretch"
            @click="resetFilters"
          >
            重置筛选
          </Button>
        </div>
      </Card>

      <Card
        :bordered="false"
        class="min-h-0 border border-slate-200 shadow-sm"
        :body-style="{ padding: 0 }"
      >
        <div
          class="flex items-center justify-between border-b border-slate-100 px-4 py-3"
        >
          <div>
            <div class="font-medium text-slate-900">账户绑定列表</div>
            <div class="mt-0.5 text-xs text-slate-500">
              共 {{ filteredBindings.length }} 条绑定记录
            </div>
          </div>
          <Tag color="blue">Facebook · Google · TikTok · Kwai</Tag>
        </div>

        <div class="hidden min-w-0 xl:block">
          <Table
            :columns="columns"
            :data-source="filteredBindings"
            :pagination="{ pageSize: 10, showSizeChanger: false }"
            row-key="id"
            table-layout="fixed"
          >
            <template #emptyText>
              <Empty description="当前筛选条件下暂无绑定记录" />
            </template>

            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'account'">
                <div class="min-w-0">
                  <div
                    class="truncate font-medium text-slate-800"
                    :title="record.accountName"
                  >
                    {{ record.accountName }}
                  </div>
                  <div
                    class="mt-1 truncate font-mono text-xs text-slate-400"
                    :title="record.accountId"
                  >
                    {{ record.accountId }}
                  </div>
                  <Tag
                    class="!m-0 mt-2"
                    :color="platformInfo(record.platform).color"
                  >
                    <span class="inline-flex items-center gap-1.5">
                      <IconifyIcon :icon="platformInfo(record.platform).icon" />
                      {{ platformInfo(record.platform).label }}
                    </span>
                  </Tag>
                </div>
              </template>

              <template v-else-if="column.key === 'assignment'">
                <div class="min-w-0 text-sm">
                  <div class="truncate font-medium text-slate-800">
                    {{ record.project }}
                  </div>
                  <div class="mt-1 truncate text-xs text-slate-500">
                    {{ record.deliveryLine }} · {{ record.owner }}
                  </div>
                </div>
              </template>

              <template v-else-if="column.key === 'status'">
                <div class="min-w-0">
                  <Tag :color="statusInfo(record.status).color">
                    {{ statusInfo(record.status).label }}
                  </Tag>
                  <div class="mt-1 truncate text-xs text-slate-500">
                    {{ record.lastSyncAt }}
                  </div>
                </div>
              </template>

              <template v-else-if="column.key === 'actions'">
                <div class="flex flex-wrap items-center gap-x-1">
                  <Button
                    v-if="
                      record.status === 'active' || record.status === 'expiring'
                    "
                    type="link"
                    :loading="syncingId === record.id"
                    @click="syncBinding(record)"
                  >
                    同步
                  </Button>
                  <Button
                    v-if="
                      record.status === 'expired' || record.status === 'unbound'
                    "
                    type="link"
                    @click="renewBinding(record)"
                  >
                    {{ record.status === 'unbound' ? '重新绑定' : '重新授权' }}
                  </Button>
                  <Popconfirm
                    v-if="record.status !== 'unbound'"
                    title="确定解除该账户绑定吗？"
                    description="解绑后，该投放线将停止同步该账户的数据。"
                    ok-text="确认解绑"
                    cancel-text="取消"
                    @confirm="unbind(record)"
                  >
                    <Button type="link" danger>解绑</Button>
                  </Popconfirm>
                </div>
              </template>
            </template>
          </Table>
        </div>

        <div class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:hidden">
          <Card
            v-for="binding in filteredBindings"
            :key="binding.id"
            :bordered="false"
            class="min-w-0 border border-slate-200 shadow-none"
          >
            <article class="min-w-0">
              <div class="flex min-w-0 items-start justify-between gap-3">
                <div class="min-w-0">
                  <h2
                    class="m-0 truncate text-sm font-semibold text-slate-900"
                    :title="binding.accountName"
                  >
                    {{ binding.accountName }}
                  </h2>
                  <div
                    class="mt-1 truncate font-mono text-xs text-slate-400"
                    :title="binding.accountId"
                  >
                    {{ binding.accountId }}
                  </div>
                </div>
                <Tag
                  class="!m-0 shrink-0"
                  :color="platformInfo(binding.platform).color"
                >
                  <span class="inline-flex items-center gap-1.5">
                    <IconifyIcon :icon="platformInfo(binding.platform).icon" />
                    {{ platformInfo(binding.platform).label }}
                  </span>
                </Tag>
              </div>

              <div class="mt-3">
                <Tag :color="statusInfo(binding.status).color">
                  {{ statusInfo(binding.status).label }}
                </Tag>
              </div>

              <dl
                class="mt-3 grid grid-cols-[68px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
              >
                <dt class="text-slate-500">项目</dt>
                <dd class="m-0 min-w-0 truncate text-slate-800">
                  {{ binding.project }}
                </dd>
                <dt class="text-slate-500">投放线</dt>
                <dd class="m-0 min-w-0 truncate text-slate-800">
                  {{ binding.deliveryLine }}
                </dd>
                <dt class="text-slate-500">负责人</dt>
                <dd class="m-0 min-w-0 truncate text-slate-800">
                  {{ binding.owner }}
                </dd>
                <dt class="text-slate-500">最近同步</dt>
                <dd class="m-0 min-w-0 truncate text-slate-800">
                  {{ binding.lastSyncAt }}
                </dd>
              </dl>

              <div
                class="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3"
              >
                <Button
                  v-if="
                    binding.status === 'active' || binding.status === 'expiring'
                  "
                  block
                  class=""
                  :loading="syncingId === binding.id"
                  @click="syncBinding(binding)"
                >
                  同步
                </Button>
                <Button
                  v-if="
                    binding.status === 'expired' || binding.status === 'unbound'
                  "
                  block
                  class=""
                  type="primary"
                  @click="renewBinding(binding)"
                >
                  {{ binding.status === 'unbound' ? '重新绑定' : '重新授权' }}
                </Button>
                <Popconfirm
                  v-if="binding.status !== 'unbound'"
                  title="确定解除该账户绑定吗？"
                  description="解绑后，该投放线将停止同步该账户的数据。"
                  ok-text="确认解绑"
                  cancel-text="取消"
                  @confirm="unbind(binding)"
                >
                  <Button block class="w-full" danger>解绑</Button>
                </Popconfirm>
              </div>
            </article>
          </Card>

          <div v-if="filteredBindings.length === 0" class="col-span-full py-8">
            <Empty description="当前筛选条件下暂无绑定记录" />
          </div>
        </div>
      </Card>
    </div>

    <Drawer
      v-model:open="drawerOpen"
      title="新增广告账户绑定"
      width="min(520px, 100vw)"
      :destroy-on-close="false"
    >
      <Alert
        type="info"
        show-icon
        class="mb-5"
        message="一个绑定关系只服务于一条项目投放线"
        description="绑定后，广告数据、告警和操作权限将归入所选项目与投放线。"
      />

      <Form layout="vertical">
        <FormItem label="所属项目" required>
          <Select
            v-model:value="bindingForm.project"
            :options="projectOptions"
            placeholder="请选择项目"
            @change="onProjectChange"
          />
        </FormItem>
        <FormItem label="投放线" required>
          <Select
            v-model:value="bindingForm.deliveryLine"
            :options="deliveryLineOptions"
            :disabled="!bindingForm.project"
            placeholder="请先选择项目"
          />
        </FormItem>
        <FormItem label="广告平台" required>
          <Select
            v-model:value="bindingForm.platform"
            :options="platformOptions"
            @change="onPlatformChange"
          />
        </FormItem>
        <FormItem label="广告账户" required>
          <Select
            v-model:value="bindingForm.accountId"
            :options="accountOptions"
            show-search
            option-filter-prop="label"
            placeholder="请选择已授权的广告账户"
          />
        </FormItem>
        <FormItem label="负责人" required>
          <Select
            v-model:value="bindingForm.owner"
            :options="ownerOptions"
            placeholder="请选择账户负责人"
          />
        </FormItem>
        <FormItem label="备注">
          <Input.TextArea
            v-model:value="bindingForm.note"
            :maxlength="200"
            :rows="3"
            show-count
            placeholder="填写授权范围、使用限制或交接信息"
          />
        </FormItem>
      </Form>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button @click="drawerOpen = false">取消</Button>
          <Button type="primary" :loading="saving" @click="submitBinding">
            确认绑定
          </Button>
        </div>
      </template>
    </Drawer>
  </Page>
</template>
