<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AccountUsage, Developer } from '#/api';

import { h, markRaw, nextTick, ref } from 'vue';
import { useRouter } from 'vue-router';

import {
  Button,
  DatePicker,
  message,
  Modal,
  notification,
  Popconfirm,
  Space,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenForm } from '#/adapter/form';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  createDeveloper,
  deleteDeveloper,
  getDeveloperList,
  restartConsumer,
  updateDeveloper,
} from '#/api';
import DepartmentSelect from '#/views/components/DepartmentSelect.vue';

interface StatusOption {
  disabled?: boolean;
  label: string;
  value: number;
}

const fetchDevelopers = async (
  page: number,
  pageSize: number,
  formValues: any,
) => {
  return await getDeveloperList(
    page,
    pageSize,
    formValues.dev_id,
    'facebook', // 固定为 facebook
    undefined,
    undefined,
    formValues.status,
  );
};

// 生成表单配置的函数，includeEnable参数决定是否包含"启用"选项
const generateFormSchema = (includeEnable = false) => {
  const statusOptions: StatusOption[] = [{ label: '停用', value: 0 }];

  if (includeEnable) {
    statusOptions.push(
      { label: '启用', value: 1 },
      { label: '异常', value: 2 },
    );
  }

  return [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'dev_id',
      label: '个号ID',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入个号名称',
      },
      fieldName: 'app_name',
      label: '个号名称',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'app_id',
      label: '应用编号',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'app_secret',
      label: '应用密钥',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'access_token',
      label: '访问令牌',
      rules: 'required',
    },
    {
      component: 'Select',
      componentProps: {
        options: statusOptions,
      },
      defaultValue: 0,
      fieldName: 'status',
      label: '状态',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'description',
      label: '描述',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请通知开发人员填写',
      },
      fieldName: 'proxy',
      label: '代理ip',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        mode: 'multiple',
        options: [
          { label: '拉取成效数据', value: 'insights_pull' },
          { label: '企业登录', value: 'facebook_login' },
          { label: '同步个号', value: 'sync_personal' },
          { label: '同步BM', value: 'sync_bm' },
          { label: '同步像素', value: 'sync_pixels' },
        ],
        placeholder: '请选择账户用途',
        style: { width: '100%' },
      },
      defaultValue: [],
      fieldName: 'account_usage',
      label: '账户用途',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'config_id',
      label: '配置ID',
    },
    {
      component: markRaw(DepartmentSelect),
      componentProps: {
        allowClear: true,
        multiple: true,
        placeholder: '请选择部门',
        style: { width: '100%' },
      },
      defaultValue: [],
      fieldName: 'department',
      label: '部门',
      rules: 'required',
    },
  ];
};

const createFormSchema = generateFormSchema(false);
const editFormSchema = generateFormSchema(true);

const formOptions: VbenFormProps = {
  commonConfig: {
    colon: false,
  },
  schema: [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'dev_id',
      label: '个号ID',
      labelClass: 'w-[100px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '停用', value: 0 },
          { label: '启用', value: 1 },
          { label: '异常', value: 2 },
        ],
      },
      fieldName: 'status',
      label: '状态',
      labelClass: 'w-[40px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[250px_250px_max-content] py-1 pb-0 gap-x-2',
};

const gridOptions: VxeGridProps<Developer> = {
  autoResize: true,
  columns: [
    { align: 'left', minWidth: 38, title: '', type: 'checkbox' },
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: 'dev_id', minWidth: 110, title: '个号ID' },
    {
      field: 'app_name',
      minWidth: 150,
      showOverflow: true,
      title: '个号名称',
    },
    {
      field: 'app_id',
      minWidth: 110,
      title: '应用编号',
      titlePrefix: { content: 'app_id' },
    },
    {
      field: 'app_secret',
      minWidth: 140,
      resizable: true,
      showOverflow: true,
      title: '应用密钥',
      titlePrefix: { content: 'app_secret' },
    },
    {
      field: 'access_token',
      minWidth: 140,
      resizable: true,
      showOverflow: true,
      title: '访问令牌',
      titlePrefix: { content: 'access_token' },
    },
    {
      field: 'status',
      minWidth: 50,
      slots: { default: 'status' },
      title: '状态',
    },
    { field: 'description', minWidth: 130, showOverflow: true, title: '描述' },
    { field: 'proxy', minWidth: 120, showOverflow: true, title: '代理ip' },
    {
      field: 'account_usage',
      minWidth: 190,
      slots: { default: 'account_usage' },
      title: '账户用途',
    },
    { field: 'config_id', minWidth: 110, showOverflow: true, title: '配置ID' },
    {
      field: 'department',
      minWidth: 130,
      slots: { default: 'department' },
      title: '部门',
    },
    {
      field: 'operate',
      fixed: 'right',
      slots: { default: 'operate' },
      title: '操作',
      width: 190,
    },
  ],
  height: '100%',
  keepSource: true,
  pagerConfig: {
    pageSize: 50,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        return await fetchDevelopers(
          page.currentPage,
          page.pageSize,
          formValues,
        );
      },
    },
    sort: true,
  },
  showOverflow: false,
  sortConfig: {
    remote: true,
  },
  toolbarConfig: {
    refresh: true,
  },
};
const createModalLoading = ref(false);
const editModalLoading = ref(false);
const router = useRouter();

// 初始化Grid和表单
const [Grid, gridApi] = useVbenVxeGrid({
  formOptions,
  routeState: { scope: 'facebook_developer' },
  gridClass: '!p-0',
  gridOptions,
});

// 新增开发者表单
const [CreateForm, createFormApi] = useVbenForm({
  commonConfig: {
    colon: false,
    labelWidth: 115,
  },
  compact: true,
  handleSubmit: submitCreate,
  layout: 'horizontal',
  schema: createFormSchema,
  submitButtonOptions: {
    content: '确定',
    get loading() {
      return createModalLoading.value;
    },
  },
});

// 编辑开发者表单
const [EditForm, editFormApi] = useVbenForm({
  commonConfig: {
    colon: false,
    labelWidth: 120,
  },
  compact: true,
  handleSubmit: submitEdit,
  layout: 'horizontal',
  schema: editFormSchema,
  submitButtonOptions: {
    content: '确定',
    get loading() {
      return editModalLoading.value;
    },
  },
});

// 模态框控制
const isCreateModalVisible = ref(false);
const isEditModalVisible = ref(false);
const currentDeveloper = ref<Developer | null>(null);
const syncDate = ref<string | undefined>(dayjs.tz().format('YYYY-MM-DD'));
const syncDisabled = ref(false);

const openCreateModal = () => {
  isCreateModalVisible.value = true;
};

function openSyncHistory() {
  void router.push({
    path: '/management/developers/sync-history',
    query: { tab: 'facebook' },
  });
}

const openEditModal = async (developer: Developer) => {
  editFormApi.resetForm();
  currentDeveloper.value = developer;
  isEditModalVisible.value = true;

  await nextTick();
  setTimeout(() => {
    editFormApi.setValues({
      ...developer,
      account_usage: accountUsageToArray(developer.account_usage),
    });
  }, 100);
};

const handleSync = async (id: string) => {
  syncDisabled.value = true;
  if (!syncDate.value) {
    message.warning('请选择同步日期');
    syncDisabled.value = false;
    return;
  }
  const res = await restartConsumer(id, syncDate.value);
  message.success(res.message, 7);
};

const accountUsageKeys: (keyof AccountUsage)[] = [
  'insights_pull',
  'facebook_login',
  'sync_personal',
  'sync_bm',
  'sync_pixels',
];

function arrayToAccountUsage(arr: string[]): AccountUsage {
  const result = {} as AccountUsage;
  for (const key of accountUsageKeys) {
    result[key] = arr.includes(key);
  }
  return result;
}

function accountUsageToArray(usage: AccountUsage | undefined): string[] {
  if (!usage) return [];
  return accountUsageKeys.filter((k) => usage[k]);
}

// 提交创建开发者
async function submitCreate() {
  try {
    await createFormApi.validate();
    createModalLoading.value = true;
    const formValues = createFormApi.form.values as any;
    const payload = {
      ...formValues,
      ad_platform: 'facebook',
      account_usage: arrayToAccountUsage(formValues.account_usage || []),
    };
    await createDeveloper(payload);
    message.success('创建开发者成功');
    isCreateModalVisible.value = false;
    await gridApi.reload();
  } finally {
    createModalLoading.value = false;
  }
}

// 提交编辑开发者
async function submitEdit() {
  if (!currentDeveloper.value) return;
  await editFormApi.validate();
  editModalLoading.value = true;
  try {
    const values = editFormApi.form.values as any;
    const payload: Record<string, any> = {
      ...values,
      account_usage: arrayToAccountUsage(values.account_usage || []),
    };
    if (!payload.department || payload.department.length === 0) {
      payload.department = [];
    }
    if (!payload.proxy) payload.proxy = null;
    await updateDeveloper(currentDeveloper.value._id, payload);
    notification.success({
      message: '更新开发者成功',
      description: h(
        'div',
        { style: 'white-space: pre-line' },
        '数据同步失败的日期需要同步一下数据哦\n代理ip没有填可以把废弃的个号ip填过来(否则需要开发处理)',
      ),
      duration: 7,
    });
    isEditModalVisible.value = false;
    await gridApi.reload();
  } finally {
    editModalLoading.value = false;
  }
}

// 确认删除开发者
const confirmDelete = async (id: string) => {
  await deleteDeveloper(id);
  message.success('删除开发者成功');
  await gridApi.reload();
};

// 批量删除选中的开发者
const batchDelete = async () => {
  const selectedRecords = gridApi.grid.getCheckboxRecords();
  if (selectedRecords.length === 0) {
    message.error('请至少选择一条记录');
    return;
  }

  Modal.confirm({
    content: `确定要删除选中的 ${selectedRecords.length} 条记录吗？`,
    async onOk() {
      try {
        let successCount = 0;
        let errorCount = 0;

        for (const record of selectedRecords) {
          try {
            await deleteDeveloper(record._id);
            successCount++;
          } catch {
            errorCount++;
          }
        }

        if (successCount > 0) {
          message.success(`成功删除 ${successCount} 条记录`);
        }

        if (errorCount > 0) {
          message.error(`${errorCount} 条记录删除失败`);
        }
      } catch {
        message.error('批量删除失败');
      }
    },
    async afterClose() {
      await gridApi.reload();
    },
    title: '批量删除',
  });
};
</script>

<template>
  <Grid class="developer-management-grid h-full min-w-0">
    <template #toolbar-tools>
      <Space wrap>
        <Button @click="openCreateModal">新增开发者</Button>
        <Button @click="openSyncHistory">数据同步记录</Button>
        <Button danger @click="batchDelete">批量删除</Button>
      </Space>
    </template>
    <template #status="{ row }">
      <Tag
        :color="
          row.status === 1 ? 'success' : row.status === 2 ? 'warning' : 'error'
        "
      >
        {{ row.status === 1 ? '已启用' : row.status === 2 ? '异常' : '停用' }}
      </Tag>
    </template>
    <template #account_usage="{ row }">
      <div
        v-if="row.account_usage"
        class="flex max-h-[56px] flex-wrap justify-center gap-1 overflow-hidden"
      >
        <Tag v-if="row.account_usage.insights_pull">拉取成效</Tag>
        <Tag v-if="row.account_usage.facebook_login" color="green">
          企业登录
        </Tag>
        <Tag v-if="row.account_usage.sync_personal" color="purple">
          同步个号
        </Tag>
        <Tag v-if="row.account_usage.sync_bm" color="orange">同步BM</Tag>
        <Tag v-if="row.account_usage.sync_pixels">同步像素</Tag>
      </div>
    </template>
    <template #department="{ row }">
      <div
        v-if="row.department && row.department.length > 0"
        class="flex max-h-[56px] flex-wrap justify-center gap-1 overflow-hidden"
      >
        <Tag v-for="dept in row.department" :key="dept">
          {{ dept }}
        </Tag>
      </div>
    </template>
    <template #operate="{ row }">
      <Space size="small">
        <DatePicker
          v-model:value="syncDate"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 90px"
          :show-today="false"
          :allow-clear="false"
          :suffix-icon="null"
          @open-change="syncDisabled = false"
        >
          <template #renderExtraFooter>
            <div class="flex justify-end py-1">
              <Button :disabled="syncDisabled" @click="handleSync(row._id)">
                同步
              </Button>
            </div>
          </template>
        </DatePicker>
        <Button type="link" @click="openEditModal(row)">编辑</Button>
        <Popconfirm
          title="确定删除此开发者吗?"
          ok-text="确定"
          cancel-text="取消"
          placement="left"
          @confirm="confirmDelete(row._id)"
        >
          <Button type="link" danger>删除</Button>
        </Popconfirm>
      </Space>
    </template>
  </Grid>
  <Modal
    v-model:open="isCreateModalVisible"
    title="新增Facebook开发者"
    :footer="null"
  >
    <CreateForm />
  </Modal>
  <Modal
    v-model:open="isEditModalVisible"
    title="修改Facebook开发者"
    :footer="null"
  >
    <EditForm />
  </Modal>
</template>

<style scoped>
:deep(.lucide-circle-alert-icon) {
  cursor: default;
  outline: none;
}
</style>
