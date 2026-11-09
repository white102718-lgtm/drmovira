<script lang="ts" setup>
import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AgentLineKpiConfig } from '#/api/management/platform-config';

import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';

import {
  AutoComplete,
  Button,
  Input,
  message,
  Modal,
  Select,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  createAgentLineKpiConfig,
  deleteAgentLineKpiConfig,
  getAgentLineKpiConfigList,
  updateAgentLineKpiConfig,
} from '#/api/management/platform-config';

// 接收平台名称参数
interface Props {
  agentOptions?: Array<{ label: string; value: string }>;
  agentSearch?: string;
  platformName?: string;
}

const route = useRoute();

const props = withDefaults(defineProps<Props>(), {
  platformName: '',
  agentOptions: () => [],
  agentSearch: '',
});

const loadingSave = ref(false);
const agentOptions = computed(() => props.agentOptions || []);

onMounted(() => {
  // fetchAgentOptions 调用已移至父组件
});

watch([() => props.platformName, () => props.agentSearch], () => {
  gridApi?.reload();
});

const gridOptions: VxeGridProps<AgentLineKpiConfig> = {
  toolbarConfig: {
    refresh: { code: 'query' },
  },
  autoResize: true,
  border: true,
  columns: [
    {
      fixed: 'left',
      title: '序号',
      width: 60,
      slots: { default: 'seq' },
    },
    {
      fixed: 'left',
      field: 'agent_lines',
      title: '代理线',
      minWidth: 200,
      editRender: {},
      slots: {
        default: 'agent_lines_default',
        edit: 'agent_lines_edit',
      },
      formatter: ({ row }: { row: AgentLineKpiConfig }) => {
        if (Array.isArray(row.agent_lines) && row.agent_lines.length > 0) {
          return row.agent_lines[0] || '';
        }
        return '';
      },
    },
    {
      field: 'target_purpose',
      title: '目标用途',
      minWidth: 85,
      editRender: {},
      slots: {
        default: 'target_purpose_default',
        edit: 'target_purpose_edit',
      },
    },
    {
      field: 'event_name',
      title: '事件',
      minWidth: 100,
      editRender: {},
      slots: {
        default: 'event_name_default',
        edit: 'event_name_edit',
      },
    },
    {
      field: 'type',
      title: '类型',
      minWidth: 85,
      editRender: {},
      slots: {
        default: 'type_default',
        edit: 'type_edit',
      },
    },
    {
      field: 'event_field',
      title: '事件字段',
      minWidth: 140,
      editRender: {},
      slots: {
        default: 'event_field_default',
        edit: 'event_field_edit',
      },
    },
    {
      field: 'target_cost',
      title: '目标成本',
      minWidth: 100,
      editRender: {
        name: 'VxeNumberInput',
        props: { controlConfig: { showButton: false } },
      },
    },
    {
      field: 'target_lost_percent',
      title: '损失率',
      minWidth: 100,
      editRender: {
        name: 'VxeNumberInput',
        props: { type: 'float', controlConfig: { showButton: false } },
      },
      formatter: ({ cellValue }) => {
        return cellValue === undefined
          ? ''
          : `${(cellValue * 100).toFixed(1)}%`;
      },
    },
    {
      field: 'target_lifetime_hour',
      title: '生命周期(小时)',
      minWidth: 130,
      editRender: {
        name: 'VxeNumberInput',
        props: { controlConfig: { showButton: false } },
      },
    },
    {
      field: 'max_target_cost',
      title: '最高成本',
      minWidth: 100,
      editRender: {
        name: 'VxeNumberInput',
        props: { controlConfig: { showButton: false } },
      },
    },
    {
      field: 'check_hourly',
      title: '检查方式',
      minWidth: 100,
      slots: { edit: 'check_hourly_edit' },
      editRender: {},
    },
    {
      fixed: 'right',
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      minWidth: 160,
    },
  ],
  editConfig: {
    mode: 'row',
    showStatus: true,
    trigger: 'manual',
    autoClear: false,
  },
  keepSource: true,
  pagerConfig: {
    enabled: true,
    pageSize: 20,
    pageSizes: [10, 20, 50, 100],
    layouts: ['PrevPage', 'JumpNumber', 'NextPage', 'Sizes', 'Total'],
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        try {
          const agentSearch = (props.agentSearch || '').trim();
          if (!props.platformName && !agentSearch) {
            return { page: 1, pageSize: 20, total: 0, items: [] };
          }
          const allData = await getAgentLineKpiConfigList(
            props.platformName,
            agentSearch || undefined,
          );
          const items = Array.isArray(allData) ? allData : [];

          // 前端分页处理
          const currentPage = page.currentPage || 1;
          const pageSize = page.pageSize || 20;
          const startIndex = (currentPage - 1) * pageSize;
          const endIndex = startIndex + pageSize;
          const pageItems = items.slice(startIndex, endIndex);

          return {
            page: currentPage,
            pageSize,
            total: items.length,
            items: pageItems,
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

const [Grid, gridApi] = useVbenVxeGrid({ gridOptions });

function hasEditStatus(row: AgentLineKpiConfig) {
  return gridApi.grid?.isEditByRow(row);
}

function editRowEvent(row: AgentLineKpiConfig) {
  row.agent_lines_temp =
    Array.isArray(row.agent_lines) && row.agent_lines.length > 0
      ? row.agent_lines[0]
      : undefined;
  gridApi.grid?.setEditRow(row);
}

async function saveRowEvent(row: AgentLineKpiConfig) {
  loadingSave.value = true;
  try {
    // 将单选的临时值转换为数组格式
    const dataToSave = {
      ...row,
      agent_lines: row.agent_lines_temp ? [row.agent_lines_temp] : [],
    };
    delete dataToSave.agent_lines_temp;

    if (row.id === null) {
      await createAgentLineKpiConfig(dataToSave);
      message.success('新增成功');
    } else if (row.id) {
      await updateAgentLineKpiConfig(row.id, dataToSave);
      message.success('保存成功');
    }
    await gridApi.grid?.clearEdit();
    await gridApi.reload();
  } finally {
    loadingSave.value = false;
  }
}

function cancelRowEvent() {
  gridApi.grid?.clearEdit();
}

async function handleDelete(row: AgentLineKpiConfig) {
  if (row.id) {
    const agentLineName =
      Array.isArray(row.agent_lines) && row.agent_lines.length > 0
        ? row.agent_lines[0]
        : '';
    const rowId = row.id;
    Modal.confirm({
      cancelText: '取消',
      content: `确定要删除代理线 "${agentLineName}" 的配置吗？`,
      okText: '确定',
      onOk: async () => {
        try {
          await deleteAgentLineKpiConfig(rowId);
          message.success('删除KPI配置成功');
        } catch {}
      },
      onCancel: () => {},
      afterClose: async () => {
        await gridApi.reload();
      },
      title: '确认删除',
    });
  } else {
    await gridApi.grid.remove(row);
  }
}

function addAgentLineConfig() {
  const newRow = {
    id: null,
    agent_lines: [],
    game_platform: props.platformName,
    target_purpose: null,
    target_cost: null,
    target_lost_percent: null,
    target_lifetime_hour: null,
    max_target_cost: null,
    check_hourly: null,
    event_name: null,
    event_field: null,
  };
  gridApi.grid.insertAt(newRow, -1);
  gridApi.grid.setEditRow(newRow);
}

watch(
  () => route.query.tab,
  async (tab) => {
    if (tab === 'PlatformKpiConfig') {
      await nextTick();
      (gridApi.grid as any)?.resize?.();
    }
  },
);
</script>

<template>
  <!--调整下一层级样式, 选中下一层级-->
  <Page class="[&>div]:m-0 [&>div]:p-0">
    <template #default>
      <Grid>
        <template #toolbar-actions>
          <span class="mr-4">kpi配置</span>
        </template>

        <template #toolbar-tools>
          <Button @click="addAgentLineConfig">新增代理线配置</Button>
        </template>

        <template #seq="{ rowIndex }">
          {{
            ((gridApi.grid?.getProxyInfo()?.pager?.currentPage || 1) - 1) *
              (gridApi.grid?.getProxyInfo()?.pager?.pageSize || 20) +
            rowIndex +
            1
          }}
        </template>

        <template #agent_lines_default="{ row }">
          <div class="flex min-h-6 items-center justify-center">
            <span
              v-if="
                Array.isArray(row.agent_lines) && row.agent_lines.length > 0
              "
            >
              {{ row.agent_lines[0] }}
            </span>
          </div>
        </template>

        <template #agent_lines_edit="{ row }">
          <div class="h-auto min-h-8 w-full">
            <Select
              v-model:value="row.agent_lines_temp"
              class="w-full"
              placeholder="请选择代理线"
              :allow-clear="true"
              :dropdown-match-select-width="false"
              :show-search="true"
              :filter-option="true"
              :options="agentOptions"
            />
          </div>
        </template>

        <template #check_hourly_edit="{ row }">
          <Input v-model:value="row.check_hourly" style="width: 100%" />
        </template>

        <template #target_purpose_default="{ row }">
          <span v-if="row.target_purpose">{{ row.target_purpose }}</span>
        </template>

        <template #target_purpose_edit="{ row }">
          <Select
            v-model:value="row.target_purpose"
            class="w-full"
            placeholder="请选择目标用途"
            :allow-clear="true"
            :options="[
              { label: '成本', value: '成本' },
              { label: '回收', value: '回收' },
            ]"
          />
        </template>

        <template #event_name_default="{ row }">
          <span v-if="row.event_name">{{ row.event_name }}</span>
        </template>

        <template #event_name_edit="{ row }">
          <AutoComplete
            v-model:value="row.event_name"
            class="w-full"
            placeholder="请选择或输入事件名称"
            :allow-clear="true"
            :options="[
              { value: '安装' },
              { value: '完成注册' },
              { value: '首充' },
              { value: '复购' },
              { value: '复购价值' },
            ]"
          />
        </template>

        <template #type_default="{ row }">
          <span v-if="row.type">{{ row.type }}</span>
        </template>

        <template #type_edit="{ row }">
          <Select
            v-model:value="row.type"
            class="w-full"
            placeholder="请选择目标用途"
            :allow-clear="true"
            :options="[
              { label: '测试', value: '测试' },
              { label: '标准', value: '标准' },
            ]"
          />
        </template>

        <template #event_field_default="{ row }">
          <span v-if="row.event_field">{{ row.event_field }}</span>
        </template>

        <template #event_field_edit="{ row }">
          <Select
            v-model:value="row.event_field"
            class="w-full"
            placeholder="请选择事件字段"
            :allow-clear="true"
            :options="[
              { label: 'app_installs', value: 'app_installs' },
              {
                label: 'complete_registration',
                value: 'complete_registration',
              },
              { label: 'subscribe_website', value: 'subscribe_website' },
              {
                label: 'subscribe_website_values',
                value: 'subscribe_website_values',
              },
              { label: 'purchases', value: 'purchases' },
              { label: 'purchases_value', value: 'purchases_value' },
            ]"
          />
        </template>

        <template #action="{ row }">
          <template v-if="hasEditStatus(row)">
            <Button
              :loading="loadingSave"
              @click="saveRowEvent(row)"
              class="mr-2"
              danger
            >
              保存
            </Button>
            <Button @click="cancelRowEvent()">取消</Button>
          </template>
          <template v-else>
            <Button @click="editRowEvent(row)" class="mr-2"> 编辑 </Button>
            <Button danger @click="handleDelete(row)"> 删除 </Button>
          </template>
        </template>
      </Grid>
    </template>
  </Page>
</template>
