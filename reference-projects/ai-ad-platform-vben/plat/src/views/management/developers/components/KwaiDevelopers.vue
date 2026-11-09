<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { Developer } from '#/api';

import { h, markRaw, nextTick, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  DatePicker,
  message,
  Modal,
  notification,
  Popconfirm,
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
import AgentLineSelect from '#/views/components/AgentLineSelect.vue';
import UserSelect from '#/views/components/UserSelect.vue';

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
    'kwai', // 固定为 kwai
    formValues.agent_lines,
    formValues.placer_id,
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
      label: '开发者账号ID',
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
      component: markRaw(AgentLineSelect),
      componentProps: {
        multiple: true,
        placeholder: '请选择代理线',
        style: { width: '100%' },
      },
      fieldName: 'agent_lines',
      label: '代理线',
      rules: 'required',
    },
    {
      component: markRaw(UserSelect),
      componentProps: {
        allowClear: true,
        placeholder: '右上角头像中的蓝色字体',
      },
      fieldName: 'placer_id',
      label: '投放员ID',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'app_name',
      label: 'app名称',
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
      label: '开发者账号ID',
      labelClass: 'w-[100px]',
    },
    {
      component: markRaw(AgentLineSelect),
      componentProps: {
        multiple: true,
        placeholder: '请选择代理线',
        style: { width: '100%' },
      },
      fieldName: 'agent_lines',
      label: '代理线',
      labelClass: 'w-[60px]',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
      },
      fieldName: 'placer_id',
      label: '投放员ID',
      labelClass: 'w-[70px]',
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
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(4,1fr)_auto] py-1 pb-1 gap-x-4',
};

const gridOptions: VxeGridProps<Developer> = {
  checkboxConfig: {
    highlight: true,
  },
  columns: [
    { align: 'left', minWidth: 38, title: '', type: 'checkbox' },
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: 'dev_id', minWidth: 120, title: '开发者账号ID' },
    { field: 'app_id', minWidth: 125, title: '应用编号' },
    {
      field: 'app_secret',
      minWidth: 240,
      resizable: true,
      showOverflow: true,
      title: '应用密钥',
    },
    {
      field: 'access_token',
      minWidth: 150,
      resizable: true,
      showOverflow: true,
      title: '访问令牌',
    },
    {
      field: 'status',
      minWidth: 50,
      slots: { default: 'status' },
      title: '状态',
    },
    {
      field: 'agent_lines',
      minWidth: 200,
      slots: { default: 'agent_lines' },
      title: '代理线',
    },
    { field: 'placer_id', minWidth: 100, title: '投放员ID' },
    { field: 'app_name', minWidth: 100, title: 'app名称' },
    { field: 'description', minWidth: 150, showOverflow: true, title: '描述' },
    { field: 'proxy', minWidth: 130, showOverflow: true, title: '代理ip' },
    {
      field: 'operate',
      fixed: 'right',
      slots: { default: 'operate' },
      title: '操作',
      width: 170,
    },
  ],
  height: window.innerHeight - 160,
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
  stripe: true,
  toolbarConfig: {
    refresh: true,
  },
};
const createModalLoading = ref(false);
const editModalLoading = ref(false);

// 初始化Grid和表单
const [Grid, gridApi] = useVbenVxeGrid({
  formOptions,
  gridOptions,
  routeState: { scope: 'kwai_developer' },
});

// 新增开发者表单
const [CreateForm, createFormApi] = useVbenForm({
  commonConfig: {
    colon: false,
    labelWidth: 100,
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
    labelWidth: 100,
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
  createFormApi.setValues({ ad_platform: 'kwai' });
  isCreateModalVisible.value = true;
};

const openEditModal = async (developer: Developer) => {
  editFormApi.resetForm();
  currentDeveloper.value = developer;
  isEditModalVisible.value = true;

  // 延迟设置表单值，确保组件已完全初始化
  await nextTick();
  setTimeout(() => {
    editFormApi.setValues(developer);
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

// 提交创建开发者
async function submitCreate() {
  try {
    await createFormApi.validate();
    createModalLoading.value = true;
    const formValues = createFormApi.form.values as Developer;
    const payload = {
      ...formValues,
      ad_platform: 'kwai',
    };
    await createDeveloper(payload);
    message.success('创建开发者成功');
    await gridApi.reload();
    isCreateModalVisible.value = false;
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
    const values = editFormApi.form.values as Partial<Developer>;
    await updateDeveloper(currentDeveloper.value._id, values);
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

        await gridApi.reload();
      } catch {
        message.error('批量删除失败');
      }
    },
    title: '批量删除',
  });
};
</script>

<template>
  <Page content-class="!p-0">
    <Grid
      class="[&_.relative.rounded]:!pb-3 [&_.relative.rounded]:!pt-0 [&_.vxe-grid]:overflow-hidden [&_.vxe-grid]:!pt-0"
    >
      <template #toolbar-tools>
        <Button @click="openCreateModal">新增开发者</Button>
        <Button danger @click="batchDelete">批量删除</Button>
      </template>
      <template #status="{ row }">
        <Tag
          :color="
            row.status === 1
              ? 'success'
              : row.status === 2
                ? 'warning'
                : 'error'
          "
        >
          {{ row.status === 1 ? '已启用' : row.status === 2 ? '异常' : '停用' }}
        </Tag>
      </template>
      <template #agent_lines="{ row }">
        <Tag
          v-for="(line, index) in row.agent_lines"
          :key="index"
          color="blue"
          class="m-0"
        >
          {{ line }}
        </Tag>
      </template>
      <template #operate="{ row }">
        <DatePicker
          v-model:value="syncDate"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 90px"
          :show-today="false"
          :allow-clear="false"
          :suffix-icon="null"
          class="mr-1"
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
        <Button type="link" class="pl-0 pr-1" @click="openEditModal(row)">
          编辑
        </Button>
        <Popconfirm
          title="确定删除此开发者吗?"
          ok-text="确定"
          cancel-text="取消"
          placement="left"
          @confirm="confirmDelete(row._id)"
        >
          <Button type="link" class="p-0" danger>删除</Button>
        </Popconfirm>
      </template>
    </Grid>
    <Modal
      v-model:open="isCreateModalVisible"
      title="新增Kwai开发者"
      :footer="null"
    >
      <CreateForm />
    </Modal>
    <Modal
      v-model:open="isEditModalVisible"
      title="修改Kwai开发者"
      :footer="null"
    >
      <EditForm />
    </Modal>
  </Page>
</template>
