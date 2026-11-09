<script lang="ts" setup>
import type { AuditActor } from '#/domain/resource';
import type { MediaPlatform } from '#/store/media-resource';
import type { TablePaginationConfig } from 'ant-design-vue';

import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'ant-design-vue';
import { storeToRefs } from 'pinia';

import {
  ApplicationResourceBridgeService,
  ApplicationService,
  LegacyApplicationStoreAdapter,
} from '#/domain/application';
import {
  createPositiveIntegerRouteQueryField,
  createStringRouteQueryField,
  useRouteListQuery,
} from '#/composables/use-route-list-query';
import { LegacyResourceStoreAdapter, ResourceService } from '#/domain/resource';
import { useMediaResourceStore } from '#/store/media-resource';
import { useResourceApplicationStore } from '#/store/resource-applications';

import StableUserSelect from '../components/StableUserSelect.vue';
import MediaResourcePage from './components/MediaResourcePage.vue';

type LooseRecord = Record<string, unknown>;

const resourceStore = useMediaResourceStore();
const businessApplicationStore = useResourceApplicationStore();
const userStore = useUserStore();
const { applications, availableAccounts } = storeToRefs(resourceStore);
const { applications: businessApplications } = storeToRefs(
  businessApplicationStore,
);
const resourceService = new ResourceService(
  new LegacyResourceStoreAdapter({
    approveApplication: (applicationId, accountIds, actor) =>
      resourceStore.approveApplication(applicationId, accountIds, actor),
    createApplication: (input, actor) =>
      resourceStore.createApplication(input, actor),
    listApplications: () => applications.value,
    rejectApplication: (applicationId, reason, actor) =>
      resourceStore.rejectApplication(applicationId, reason, actor),
    requestReturn: (assignmentOrAccountId, reason, actor) =>
      resourceStore.requestReturn(assignmentOrAccountId, reason, actor),
  }),
);
const businessApplicationService = new ApplicationService(
  new LegacyApplicationStoreAdapter({
    applications: () => businessApplications.value,
    remove: businessApplicationStore.removeApplication,
    upsert: businessApplicationStore.upsertApplication,
  }),
);
const applicationResourceBridge = new ApplicationResourceBridgeService(
  businessApplicationService,
  resourceService,
);

const keyword = ref('');
const statusFilter = ref('all');
const page = ref(1);
const pageSize = ref(10);
const createOpen = ref(false);
const approveOpen = ref(false);
const rejectOpen = ref(false);
const submitting = ref(false);
const activeApplication = ref<unknown>();

const createForm = reactive({
  assigneeId: '',
  assigneeName: '',
  expectedStart: '',
  platform: 'facebook' as MediaPlatform,
  projectId: '',
  projectName: '',
  purpose: '',
  quantity: 1,
  teamId: '',
  teamName: '',
  timezone: 'GMT+8',
  whitelistRequired: false,
});

const approvalForm = reactive({ accountIds: [] as string[] });
const rejectionForm = reactive({ reason: '' });

const columns = [
  { key: 'application', title: '申请单', width: 220 },
  { key: 'project', title: '项目与用途', width: 240 },
  { key: 'requirement', title: '资源要求', width: 220 },
  { key: 'user', title: '使用团队 / 使用人', width: 180 },
  { key: 'status', title: '状态', width: 110 },
  { key: 'createdAt', title: '申请时间', width: 170 },
  { key: 'actions', title: '操作', width: 190 },
];

const statusMeta: Record<string, { color: string; label: string }> = {
  approved: { color: 'green', label: '已通过' },
  partially_approved: { color: 'gold', label: '部分已分配' },
  pending: { color: 'blue', label: '待审批' },
  rejected: { color: 'red', label: '已驳回' },
};

const platformMeta: Record<string, { color: string; label: string }> = {
  facebook: { color: 'blue', label: 'Facebook' },
  google: { color: 'red', label: 'Google' },
  tiktok: { color: 'default', label: 'TikTok' },
};

const platformOptions = Object.entries(platformMeta).map(([value, item]) => ({
  label: item.label,
  value,
}));

const statusOptions = [
  { label: '全部状态', value: 'all' },
  ...Object.entries(statusMeta).map(([value, item]) => ({
    label: item.label,
    value,
  })),
];

const route = useRoute();
const router = useRouter();
const { isApplyingRoute } = useRouteListQuery({
  fields: {
    page: createPositiveIntegerRouteQueryField(page, { defaultValue: 1 }),
    pageSize: createPositiveIntegerRouteQueryField(pageSize, {
      allowedValues: [10, 20, 50, 100],
      defaultValue: 10,
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
    status: createStringRouteQueryField(statusFilter, {
      allowedValues: statusOptions.map((item) => item.value),
      defaultValue: 'all',
    }),
  },
  route,
  router,
});

function asRecord(value: unknown): LooseRecord {
  return value && typeof value === 'object' ? (value as LooseRecord) : {};
}

function readText(value: unknown, ...keys: string[]) {
  const record = asRecord(value);
  for (const key of keys) {
    const field = record[key];
    if (field !== undefined && field !== null && `${field}`.trim()) {
      return `${field}`;
    }
  }
  return '';
}

function readNumber(value: unknown, ...keys: string[]) {
  const raw = readText(value, ...keys);
  const result = Number(raw);
  return Number.isFinite(result) ? result : 0;
}

function readBoolean(value: unknown, ...keys: string[]) {
  const record = asRecord(value);
  return keys.some((key) => record[key] === true || record[key] === 'yes');
}

function rowKey(record: unknown) {
  return readText(record, 'id', 'applicationId', 'application_id');
}

function statusOf(record: unknown) {
  return readText(record, 'status') || 'pending';
}

function platformOf(record: unknown) {
  return readText(record, 'platform').toLowerCase();
}

function platformLabel(value: string) {
  return platformMeta[value]?.label ?? value ?? '-';
}

function platformColor(value: string) {
  return platformMeta[value]?.color ?? 'default';
}

const filteredApplications = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  return applications.value.filter((item) => {
    const record = asRecord(item);
    const searchable = [
      record.id,
      record.projectId,
      record.projectName,
      record.purpose,
      record.requesterName,
      record.teamName,
      record.userName,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return (
      (!query || searchable.includes(query)) &&
      (statusFilter.value === 'all' || statusOf(item) === statusFilter.value)
    );
  });
});

const pagination = computed<TablePaginationConfig>(() => ({
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  total: filteredApplications.value.length,
}));

function handleTableChange(next: TablePaginationConfig) {
  const nextPageSize = next.pageSize ?? pageSize.value;
  page.value = nextPageSize === pageSize.value ? (next.current ?? 1) : 1;
  pageSize.value = nextPageSize;
}

watch([keyword, statusFilter], () => {
  if (!isApplyingRoute.value) page.value = 1;
});

watch([() => filteredApplications.value.length, pageSize], ([total]) => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value));
  if (page.value > lastPage) page.value = lastPage;
});

const summary = computed(() => [
  {
    icon: 'lucide:inbox',
    label: '待审批',
    tone: 'text-blue-600 bg-blue-50',
    value: applications.value.filter((item) => statusOf(item) === 'pending')
      .length,
  },
  {
    icon: 'lucide:badge-check',
    label: '已通过',
    tone: 'text-emerald-600 bg-emerald-50',
    value: applications.value.filter((item) => statusOf(item) === 'approved')
      .length,
  },
  {
    icon: 'lucide:wallet-cards',
    label: '当前可用账户',
    tone: 'text-violet-600 bg-violet-50',
    value: availableAccounts.value.length,
  },
]);

const requiredAccountCount = computed(() =>
  readNumber(
    activeApplication.value,
    'requestedAccountCount',
    'quantity',
    'requestedQuantity',
  ),
);

const approvedAccountCount = computed(() => {
  const approvedIds = asRecord(activeApplication.value).approvedAccountIds;
  return Array.isArray(approvedIds) ? approvedIds.length : 0;
});

const remainingAccountCount = computed(() =>
  Math.max(0, requiredAccountCount.value - approvedAccountCount.value),
);

const eligibleAccounts = computed(() => {
  const platform = platformOf(activeApplication.value);
  return availableAccounts.value.filter(
    (account) => !platform || platformOf(account) === platform,
  );
});

const accountOptions = computed(() =>
  eligibleAccounts.value.map((account) => {
    const id = readText(account, 'id', 'resourceId', 'accountId');
    const externalId = readText(
      account,
      'externalAccountId',
      'external_account_id',
      'accountId',
      'platformAccountId',
    );
    const name = readText(account, 'accountName', 'name') || '未命名账户';
    const timezone = readText(account, 'timezone');
    return {
      label: `${name} · ${externalId || id}${timezone ? ` · ${timezone}` : ''}`,
      value: id,
    };
  }),
);

function resetCreateForm() {
  Object.assign(createForm, {
    assigneeId: '',
    assigneeName: '',
    expectedStart: '',
    platform: 'facebook',
    projectId: '',
    projectName: '',
    purpose: '',
    quantity: 1,
    teamId: '',
    teamName: '',
    timezone: 'GMT+8',
    whitelistRequired: false,
  });
}

function readCurrentUserId() {
  const user = userStore.userInfo as
    | undefined
    | { _id?: string; user_id?: string; userId?: string };
  const candidate = user?.userId ?? user?.user_id ?? user?._id;
  return typeof candidate === 'string' ? candidate.trim() : '';
}

const currentActor = computed<AuditActor>(() => ({
  id: readCurrentUserId(),
  name:
    userStore.userInfo?.realName || userStore.userInfo?.full_name || '当前用户',
}));

function handleAssigneeChange(
  assigneeId: string | undefined,
  user?: { label: string; userId: string },
) {
  createForm.assigneeId = assigneeId ?? '';
  createForm.assigneeName = user?.label ?? '';
}

async function submitApplication() {
  if (
    !createForm.projectId.trim() ||
    !createForm.projectName.trim() ||
    !createForm.teamId.trim() ||
    !createForm.teamName.trim() ||
    !createForm.assigneeId.trim() ||
    !createForm.assigneeName.trim() ||
    !createForm.purpose.trim() ||
    !createForm.expectedStart.trim()
  ) {
    message.warning('请完整填写项目、稳定团队 ID、使用人、用途和预计开始日期');
    return;
  }
  if (!currentActor.value.id) {
    message.error('当前用户缺少稳定用户 ID，不能提交资源申请');
    return;
  }
  submitting.value = true;
  try {
    await Promise.resolve(
      resourceService.createApplication(
        {
          assigneeId: createForm.assigneeId,
          assigneeName: createForm.assigneeName,
          expectedReturnAt: createForm.expectedStart.trim(),
          platform: createForm.platform,
          projectId: createForm.projectId.trim(),
          projectName: createForm.projectName.trim(),
          reason: createForm.purpose.trim(),
          requestedAccountCount: createForm.quantity,
          requestedById: currentActor.value.id,
          requestedByName: currentActor.value.name,
          teamId: createForm.teamId.trim(),
          teamName: createForm.teamName.trim(),
          title: `${createForm.projectName.trim()} ${platformLabel(createForm.platform)} 账户申请`,
          timezone: createForm.timezone.trim(),
          whitelistRequired: createForm.whitelistRequired,
        },
        currentActor.value,
      ),
    );
    message.success('资源申请已提交');
    createOpen.value = false;
    resetCreateForm();
  } finally {
    submitting.value = false;
  }
}

function openApproval(record: unknown) {
  activeApplication.value = record;
  approvalForm.accountIds = [];
  approveOpen.value = true;
}

async function approve() {
  if (approvalForm.accountIds.length !== remainingAccountCount.value) {
    message.warning(`请选择 ${remainingAccountCount.value} 个可用账户`);
    return;
  }
  submitting.value = true;
  try {
    await Promise.resolve(
      applicationResourceBridge.completeResourceApproval(
        rowKey(activeApplication.value),
        approvalForm.accountIds,
        currentActor.value,
      ),
    );
    message.success('申请已通过，账户已完成分配');
    approveOpen.value = false;
  } finally {
    submitting.value = false;
  }
}

function openRejection(record: unknown) {
  activeApplication.value = record;
  rejectionForm.reason = '';
  rejectOpen.value = true;
}

async function reject() {
  if (!rejectionForm.reason.trim()) {
    message.warning('请填写驳回原因');
    return;
  }
  submitting.value = true;
  try {
    await Promise.resolve(
      applicationResourceBridge.rejectResourceApplication(
        rowKey(activeApplication.value),
        rejectionForm.reason.trim(),
        currentActor.value,
      ),
    );
    message.success('申请已驳回');
    rejectOpen.value = false;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <MediaResourcePage>
    <div class="flex w-full min-w-0 flex-col gap-4">
      <Card :bordered="false" class="overflow-hidden shadow-sm">
        <div
          class="flex flex-col justify-between gap-4 md:flex-row md:items-center"
        >
          <div>
            <div
              class="flex items-center gap-2 text-xl font-semibold text-slate-900"
            >
              <IconifyIcon icon="lucide:clipboard-list" class="text-blue-600" />
              资源申请
            </div>
            <p class="mb-0 mt-1 text-sm text-slate-500">
              提交广告账户需求，并在审批时从可用库存中完成选户与分配。
            </p>
          </div>
          <Button type="primary" @click="createOpen = true">
            <span class="inline-flex items-center gap-2">
              <IconifyIcon icon="lucide:plus" />新增申请
            </span>
          </Button>
        </div>
      </Card>

      <Row :gutter="[16, 16]">
        <Col v-for="item in summary" :key="item.label" :xs="24" :sm="8">
          <Card :bordered="false" class="h-full shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm text-slate-500">{{ item.label }}</div>
                <div class="mt-1 text-2xl font-semibold text-slate-900">
                  {{ item.value }}
                </div>
              </div>
              <span
                class="grid size-10 place-items-center rounded-xl"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" class="text-xl" />
              </span>
            </div>
          </Card>
        </Col>
      </Row>

      <Card :bordered="false" class="shadow-sm">
        <div class="mb-4 flex flex-col gap-3 md:flex-row">
          <Input
            v-model:value="keyword"
            allow-clear
            class="w-full md:max-w-sm"
            placeholder="搜索申请单、项目、申请人或用途"
          >
            <template #prefix><IconifyIcon icon="lucide:search" /></template>
          </Input>
          <Select
            v-model:value="statusFilter"
            class="w-full md:w-40"
            :options="statusOptions"
          />
        </div>

        <Table
          :columns="columns"
          :data-source="filteredApplications"
          :pagination="pagination"
          :row-key="rowKey"
          :scroll="{ x: 1330 }"
          @change="handleTableChange"
        >
          <template #emptyText>
            <Empty description="暂无符合条件的资源申请" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'application'">
              <div class="font-medium text-slate-900">
                {{ readText(record, 'applicationNo', 'id', 'applicationId') }}
              </div>
              <div class="mt-1 text-xs text-slate-500">
                申请人：{{
                  readText(
                    record,
                    'requestedByName',
                    'requesterName',
                    'applicantName',
                  ) || '-'
                }}
              </div>
              <Tag
                v-if="readText(record, 'sourceApplicationId')"
                class="mt-2"
                color="blue"
              >
                来自业务申请 {{ readText(record, 'sourceApplicationId') }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'project'">
              <div class="font-medium text-slate-800">
                {{ readText(record, 'projectName') || '-' }}
              </div>
              <div class="mt-1 line-clamp-2 text-xs text-slate-500">
                {{ readText(record, 'reason', 'purpose') || '未填写用途' }}
              </div>
            </template>
            <template v-else-if="column.key === 'requirement'">
              <Space wrap>
                <Tag :color="platformColor(platformOf(record))">
                  {{ platformLabel(platformOf(record)) }}
                </Tag>
                <Tag>
                  {{
                    readNumber(
                      record,
                      'requestedAccountCount',
                      'quantity',
                      'requestedQuantity',
                    )
                  }}
                  个账户
                </Tag>
                <Tag
                  v-if="readBoolean(record, 'whitelistRequired')"
                  color="purple"
                >
                  需加白
                </Tag>
              </Space>
              <div class="mt-1 text-xs text-slate-500">
                {{ readText(record, 'timezone') || '-' }} ·
                {{
                  readText(
                    record,
                    'expectedStart',
                    'expectedStartDate',
                    'expectedReturnAt',
                  ) || '-'
                }}
              </div>
            </template>
            <template v-else-if="column.key === 'user'">
              <div>{{ readText(record, 'teamName') || '-' }}</div>
              <div class="mt-1 text-xs text-slate-500">
                {{ readText(record, 'assigneeName', 'userName') || '-' }}
              </div>
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag :color="statusMeta[statusOf(record)]?.color ?? 'default'">
                {{ statusMeta[statusOf(record)]?.label ?? statusOf(record) }}
              </Tag>
              <div
                v-if="statusOf(record) === 'rejected'"
                class="mt-1 max-w-40 text-xs text-red-500"
              >
                {{ readText(record, 'rejectedReason', 'rejectionReason') }}
              </div>
            </template>
            <template v-else-if="column.key === 'createdAt'">
              {{ readText(record, 'createdAt', 'submittedAt') || '-' }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <Space
                v-if="
                  statusOf(record) === 'pending' ||
                  statusOf(record) === 'partially_approved'
                "
                wrap
              >
                <Button type="link" class="!px-0" @click="openApproval(record)">
                  审批并选户
                </Button>
                <Button
                  danger
                  type="link"
                  class="!px-0"
                  @click="openRejection(record)"
                >
                  驳回
                </Button>
              </Space>
              <span v-else class="text-sm text-slate-400">已处理</span>
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <Modal
      v-model:open="createOpen"
      :confirm-loading="submitting"
      ok-text="提交申请"
      title="新增资源申请"
      width="720px"
      @ok="submitApplication"
    >
      <Alert
        class="mb-4"
        message="建议从投放任务发起；此处用于补录或临时资源需求。"
        show-icon
        type="info"
      />
      <Form layout="vertical">
        <Row :gutter="16">
          <Col :xs="24" :md="12">
            <FormItem label="项目名称" required>
              <Input v-model:value="createForm.projectName" :maxlength="80" />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="项目 ID" required>
              <Input
                v-model:value="createForm.projectId"
                placeholder="用于绑定资源分配"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="8">
            <FormItem label="平台" required>
              <Select
                v-model:value="createForm.platform"
                :options="platformOptions"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="8">
            <FormItem label="账户数量" required>
              <InputNumber
                v-model:value="createForm.quantity"
                class="!w-full"
                :min="1"
                :max="100"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="8">
            <FormItem label="时区" required>
              <Input
                v-model:value="createForm.timezone"
                placeholder="如 GMT+9"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="使用团队" required>
              <Input v-model:value="createForm.teamName" />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="团队 ID" required>
              <Input
                v-model:value="createForm.teamId"
                placeholder="填写组织目录中的稳定团队 ID"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="使用人" required>
              <StableUserSelect
                v-model="createForm.assigneeId"
                :legacy-label="createForm.assigneeName"
                placeholder="请选择使用人"
                @change="handleAssigneeChange"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="申请人" required>
              <Input :value="currentActor.name" disabled />
              <p class="mb-0 mt-1 text-xs text-slate-500">
                申请人使用当前登录用户的稳定 ID 保存。
              </p>
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="预计开始" required>
              <Input
                v-model:value="createForm.expectedStart"
                placeholder="YYYY-MM-DD"
              />
            </FormItem>
          </Col>
          <Col :span="24">
            <FormItem label="用途" required>
              <Input.TextArea
                v-model:value="createForm.purpose"
                :maxlength="300"
                :rows="3"
                show-count
              />
            </FormItem>
          </Col>
          <Col :span="24">
            <FormItem label="加白要求">
              <Switch
                v-model:checked="createForm.whitelistRequired"
                checked-children="需要加白"
                un-checked-children="无需加白"
              />
            </FormItem>
          </Col>
        </Row>
      </Form>
    </Modal>

    <Modal
      v-model:open="approveOpen"
      :confirm-loading="submitting"
      :ok-button-props="{
        disabled:
          eligibleAccounts.length < remainingAccountCount ||
          approvalForm.accountIds.length !== remainingAccountCount,
      }"
      ok-text="通过并完成分配"
      title="审批资源申请"
      width="680px"
      @ok="approve"
    >
      <Alert
        v-if="eligibleAccounts.length < remainingAccountCount"
        class="mb-4"
        :message="`当前仅有 ${eligibleAccounts.length} 个同平台可用账户，不足待分配数量 ${remainingAccountCount}。`"
        description="请先补充库存或释放已占用资源，再继续审批。"
        show-icon
        type="warning"
      />
      <div class="mb-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
        <div class="font-medium text-slate-800">
          {{ readText(activeApplication, 'projectName') || '-' }}
        </div>
        <div class="mt-1">
          {{ platformLabel(platformOf(activeApplication)) }} · 申请
          {{ requiredAccountCount }} 个，已分配
          {{ approvedAccountCount }} 个，待分配 {{ remainingAccountCount }} 个 ·
          {{ readText(activeApplication, 'timezone') || '未指定时区' }}
        </div>
      </div>
      <Form layout="vertical">
        <FormItem
          :label="`选择可用账户（${approvalForm.accountIds.length}/${remainingAccountCount}）`"
          required
        >
          <Select
            v-model:value="approvalForm.accountIds"
            mode="multiple"
            option-filter-prop="label"
            placeholder="搜索并选择账户"
            :options="accountOptions"
          />
        </FormItem>
      </Form>
    </Modal>

    <Modal
      v-model:open="rejectOpen"
      :confirm-loading="submitting"
      ok-text="确认驳回"
      ok-type="danger"
      title="驳回资源申请"
      @ok="reject"
    >
      <Alert
        class="mb-4"
        message="驳回原因将展示给申请人，请给出可执行的补充说明。"
        show-icon
        type="warning"
      />
      <Form layout="vertical">
        <FormItem label="驳回原因" required>
          <Input.TextArea
            v-model:value="rejectionForm.reason"
            :maxlength="300"
            :rows="4"
            show-count
          />
        </FormItem>
      </Form>
    </Modal>
  </MediaResourcePage>
</template>

<style scoped>
@media (max-width: 767px) {
}
</style>
