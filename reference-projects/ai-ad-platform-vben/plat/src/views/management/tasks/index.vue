<script lang="ts" setup>
import type { Dayjs } from 'dayjs';

import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { TaskDispatchItem } from '#/api/management/task-manager';

import { computed, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  DatePicker,
  Input,
  message,
  Modal,
  Select,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  createTask,
  deleteTask,
  getTaskList,
  getUserOptions,
  updateTask,
} from '#/api';
import PlatformSelect from '#/views/components/PlatformSelect.vue';

const loadingSave = ref(false);
const taskTypeOptions = ref<{ label: string; value: string }[]>([
  { label: '下户', value: '1' },
  { label: '创建系列', value: '2' },
]);
const userOptions = ref<{ label: string; value: string }[]>([]);
const computedUserOptions = computed(() => userOptions.value);

// 获取下拉选项数据
const fetchOptions = async () => {
  try {
    const users = await getUserOptions();
    userOptions.value = users.map((item) => ({
      label: item,
      value: item,
    }));

    await gridApi.reload();
  } catch (error) {}
};

onMounted(() => {
  fetchOptions();
});

// 筛选表单配置
const formOptions: VbenFormProps = {
  commonConfig: {
    colon: false,
  },
  schema: [
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        placeholder: '选择任务类型',
        style: { width: '160px' },
      },
      fieldName: 'taskType',
      label: '任务类型',
      labelClass: 'w-[70px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        placeholder: '选择项目名称',
        style: { width: '160px' },
      },
      fieldName: 'gamePlatform',
      label: '项目名称',
      labelClass: 'w-[70px]',
    },
    {
      component: 'DatePicker',
      componentProps: {
        allowClear: true,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: 'YYYY-MM-DD',
        style: { width: '130px' },
        valueFormat: 'YYYY-MM-DD',
      },
      fieldName: 'startTime',
      label: '起始日期',
      labelClass: 'w-[70px]',
    },
    {
      component: 'DatePicker',
      componentProps: {
        allowClear: true,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: 'YYYY-MM-DD',
        style: { width: '130px' },
        valueFormat: 'YYYY-MM-DD',
      },
      fieldName: 'endTime',
      label: '结束日期',
      labelClass: 'w-[70px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[240px_240px_210px_210px_160px] py-2.5 pb-0 gap-x-1',
};

const gridOptions: VxeGridProps<TaskDispatchItem> = {
  toolbarConfig: {
    refresh: { code: 'query' },
  },
  autoResize: true,
  border: true,
  columns: [
    { title: '序号', type: 'seq', width: 60 },
    {
      field: 'task_type',
      title: '任务类型',
      minWidth: 120,
      editRender: {
        name: 'VxeSelect',
        options: taskTypeOptions.value,
      },
    },
    {
      field: 'description',
      title: '描述',
      minWidth: 200,
      slots: { edit: 'description_edit' },
      editRender: {},
    },
    {
      field: 'game_platform',
      title: '项目名称',
      minWidth: 120,
      slots: { edit: 'game_platform_edit' },
      editRender: {},
    },
    {
      field: 'related_users',
      title: '相关人员',
      minWidth: 180,
      slots: { edit: 'related_users_edit' },
      editRender: {},
      formatter: ({ cellValue }) => {
        if (!cellValue || cellValue.length === 0) return '';
        return cellValue
          .map((userId: string) => {
            const user = userOptions.value.find(
              (item) => item.value === userId,
            );
            return user ? user.label : userId;
          })
          .join(', ');
      },
    },
    {
      field: 'status',
      title: '当前状态',
      minWidth: 100,
      editRender: {
        name: 'VxeSelect',
        options: [
          { label: '已发起', value: 'initiated' },
          { label: '已领取/进行中', value: 'in_progress' },
          { label: '已完成', value: 'completed' },
        ],
      },
      formatter: ({ cellValue }) => {
        const statusMap = {
          initiated: '已发起',
          in_progress: '已领取/进行中',
          completed: '已完成',
        };
        return statusMap[cellValue as keyof typeof statusMap] || cellValue;
      },
    },
    {
      field: 'create_time',
      title: '发起时间',
      minWidth: 160,
      formatter: ({ cellValue }) => {
        return cellValue
          ? dayjs.tz(cellValue).format('YYYY-MM-DD HH:mm:ss')
          : '';
      },
      slots: { edit: 'create_time_edit' },
      editRender: {},
    },
    {
      field: 'deadline',
      title: '截止时间',
      minWidth: 160,
      formatter: ({ cellValue }) => {
        return cellValue
          ? dayjs.tz(cellValue).format('YYYY-MM-DD HH:mm:ss')
          : '';
      },
      slots: { edit: 'deadline_edit' },
      editRender: {},
    },
    {
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      minWidth: 160,
    },
  ],
  editConfig: {
    mode: 'row',
    showStatus: true,
    trigger: 'click',
    autoClear: false,
  },
  height: '100%',
  keepSource: true,
  pagerConfig: {
    enabled: true,
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        try {
          const params = {
            page: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          };

          const result = await getTaskList(params);
          const {
            items = [],
            total = 0,
            page: currentPage = 1,
            pageSize: size = 20,
          } = result || {};
          return {
            page: currentPage,
            pageSize: size,
            total,
            items,
          };
        } catch {
          return {
            page: 1,
            pageSize: 20,
            total: 0,
            items: [],
          };
        }
      },
    },
  },
  showOverflow: false,
};

const [Grid, gridApi] = useVbenVxeGrid({ formOptions, gridOptions });

function hasEditStatus(row: TaskDispatchItem) {
  return gridApi.grid?.isEditByRow(row);
}

function editRowEvent(row: TaskDispatchItem) {
  gridApi.grid?.setEditRow(row);
}

async function saveRowEvent(row: TaskDispatchItem) {
  loadingSave.value = true;
  try {
    if (row.id === null) {
      if (!row.task_type) {
        message.error('任务类型不能为空');
        return;
      }
      if (!row.description) {
        message.error('任务描述不能为空');
        return;
      }
      await createTask(row);
      message.success('新增成功');
    } else if (row.id) {
      await updateTask(row.id, row);
      await gridApi.grid?.clearEdit();
      message.success('保存成功');
    }
    await gridApi.reload();
  } finally {
    loadingSave.value = false;
  }
}

function cancelRowEvent() {
  gridApi.grid?.clearEdit();
}

async function handleDelete(row: TaskDispatchItem) {
  if (row.id) {
    Modal.confirm({
      cancelText: '取消',
      content: `确定要删除任务 "${row.description}" 吗？`,
      okText: '确定',
      onOk: async () => {
        try {
          await deleteTask(row.id as string);
          message.success('删除任务成功');
          await gridApi.reload();
        } catch (error: any) {}
      },
      title: '确认删除',
    });
  } else {
    await gridApi.grid.remove(row);
  }
}

async function addTask() {
  const now = dayjs.tz().format('YYYY-MM-DD HH:mm:ss');
  const newRow = {
    id: null,
    task_type: null,
    description: null,
    game_platform: null,
    related_users: [],
    status: 'initiated',
    create_time: now,
    deadline: '',
  };

  if (gridApi.grid) {
    const { row } = await gridApi.grid.insert(newRow);
    gridApi.grid.setEditRow(row);
  }
}
</script>

<template>
  <Page
    class="adpulse-section-page flex h-full min-h-0 flex-col [&_.relative.rounded]:!pb-[2px] [&_.relative.rounded]:!pt-0 [&_.vxe-grid]:overflow-hidden [&_.vxe-grid]:!pt-0"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden"
  >
    <template #default>
      <!-- 表格区域 -->
      <div class="ux-fill-grid-host h-full min-h-0 min-w-0">
        <Grid class="h-full">
          <template #toolbar-tools>
            <Button @click="addTask">新增任务</Button>
          </template>

          <template #create_time_edit="{ row }">
            <DatePicker
              v-model:value="row.create_time"
              type="date"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              show-time
              placeholder="请选择发起时间"
              style="width: 100%"
            />
          </template>

          <template #deadline_edit="{ row }">
            <DatePicker
              v-model:value="row.deadline"
              type="date"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              show-time
              placeholder="请选择截止时间"
              style="width: 100%"
            />
          </template>

          <template #description_edit="{ row }">
            <Input
              v-model:value="row.description"
              placeholder="请输入描述"
              style="width: 100%"
            />
          </template>

          <template #game_platform_edit="{ row }">
            <PlatformSelect
              v-model:value="row.game_platform"
              placeholder="请选择项目名称"
              style="width: 100%"
            />
          </template>

          <template #related_users_edit="{ row }">
            <Select
              v-model:value="row.related_users"
              mode="multiple"
              placeholder="请选择相关人员"
              style="width: 100%"
              :options="computedUserOptions"
            />
          </template>

          <template #action="{ row }">
            <template v-if="hasEditStatus(row)">
              <Button
                danger
                :loading="loadingSave"
                class="mr-2"
                @click="saveRowEvent(row)"
              >
                保存
              </Button>
              <Button @click="cancelRowEvent()">取消</Button>
            </template>
            <template v-else>
              <Button class="mr-2" @click="editRowEvent(row)"> 编辑 </Button>
              <Button danger @click="handleDelete(row)"> 删除 </Button>
            </template>
          </template>
        </Grid>
      </div>
    </template>
  </Page>
</template>
