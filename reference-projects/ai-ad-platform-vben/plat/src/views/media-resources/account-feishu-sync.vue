<script setup lang="ts">
/* eslint-disable vue/html-closing-bracket-newline, vue/multiline-html-element-content-newline */
import type {
  FeishuAppConfig,
  FeishuLog,
  FeishuMapping,
  FeishuTask,
} from '#/api/feishu-sync';

import { computed, onMounted, reactive, ref, watch } from 'vue';

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
  Select,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  connectFeishuTables,
  createFeishuTask,
  deleteFeishuTask,
  getFeishuAppConfig,
  getFeishuFields,
  getFeishuLogs,
  getFeishuMappings,
  getFeishuTableColumns,
  getFeishuTaskList,
  saveFeishuMappings,
  testFeishuConnection,
  triggerFeishuTask,
  updateFeishuAppConfig,
  updateFeishuTask,
  updateFeishuTaskStatus,
} from '#/api/feishu-sync';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

defineOptions({ name: 'MediaResourceAccountFeishuSync' });

interface SheetOption {
  name: string;
  tableId: string;
}

const loading = ref(false);
const detailLoading = ref(false);
const loadError = ref('');
const detailError = ref('');
const tableKeyword = ref('');
const tasks = ref<FeishuTask[]>([]);
const selectedTaskId = ref<number | string>();
const activeTab = ref<'log' | 'mapping'>('mapping');
const routeStateReady = ref(false);
const mappings = ref<FeishuMapping[]>([]);
const logs = ref<FeishuLog[]>([]);
const mappingEditing = ref(false);
const editingMappings = ref<FeishuMapping[]>([]);
const appConfig = reactive<FeishuAppConfig>({
  appId: '',
  appName: 'Mpower 飞书应用',
});

const credentialOpen = ref(false);
const credentialSaving = ref(false);
const credentialForm = reactive<FeishuAppConfig>({ appId: '', appName: '' });
const taskOpen = ref(false);
const taskSaving = ref(false);
const connecting = ref(false);
const sheetOptions = ref<SheetOption[]>([]);
const taskForm = reactive<Partial<FeishuTask> & { docUrl?: string }>({});
const systemColumns = ref<
  Array<{ columnComment?: string; columnName: string }>
>([]);
const feishuFields = ref<Array<{ fieldName?: string; name?: string }>>([]);

const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    activeTab: {
      always: true,
      codec: {
        parse(value) {
          const tab = Array.isArray(value) ? value[0] : value;
          return tab === 'log' || tab === 'mapping' ? tab : undefined;
        },
        serialize: (value) => value,
      },
      key: 'tab',
    },
    selectedTaskId: { key: 'task_id' },
    tableKeyword: { key: 'keyword' },
  },
  onRouteStateRestored: () => {
    if (routeStateReady.value) return loadTaskDetail();
  },
  state: createListRouteStateTarget({
    activeTab,
    selectedTaskId,
    tableKeyword,
  }),
});

const filteredTasks = computed(() => {
  const keyword = tableKeyword.value.trim().toLowerCase();
  return tasks.value.filter(
    (task) =>
      !keyword ||
      `${task.taskName} ${task.tableName ?? ''} ${task.tableId}`
        .toLowerCase()
        .includes(keyword),
  );
});
const selectedTask = computed(() =>
  tasks.value.find((task) => task.taskId === selectedTaskId.value),
);
const enabledCount = computed(
  () => tasks.value.filter((task) => Number(task.status) === 1).length,
);

const mappingColumns = [
  { key: 'systemFieldName', title: '系统字段', width: 260 },
  { key: 'direction', title: '', width: 64 },
  { key: 'feishuFieldName', title: '飞书字段' },
  { key: 'isSplit', title: '拆分', width: 84 },
  { key: 'actions', title: '操作', width: 80 },
];
const logColumns = [
  { dataIndex: 'startTime', title: '开始时间', width: 180 },
  { dataIndex: 'status', title: '状态', width: 100 },
  { dataIndex: 'totalCount', title: '总数', width: 90 },
  { dataIndex: 'successCount', title: '成功', width: 90 },
  { dataIndex: 'failCount', title: '失败', width: 90 },
  { dataIndex: 'errMsg', title: '错误信息' },
];

async function loadTasks(showMessage = false) {
  loading.value = true;
  try {
    tasks.value = await getFeishuTaskList();
    loadError.value = '';
    selectedTaskId.value ||= tasks.value[0]?.taskId;
    if (showMessage) message.success('文档同步配置已刷新');
  } catch {
    tasks.value = [];
    selectedTaskId.value = undefined;
    loadError.value = '文档同步配置暂时无法加载，请稍后重试。';
  } finally {
    loading.value = false;
  }
}

async function loadAppConfig() {
  try {
    Object.assign(appConfig, await getFeishuAppConfig());
  } catch {
    Object.assign(appConfig, { appId: '', appName: 'Mpower 飞书应用' });
  }
}

async function loadTaskDetail() {
  const task = selectedTask.value;
  if (!task) return;
  detailLoading.value = true;
  try {
    const [mappingList, logList] = await Promise.all([
      getFeishuMappings(task.taskId),
      getFeishuLogs(task.taskId),
    ]);
    mappings.value = mappingList;
    logs.value = logList;
    detailError.value = '';
  } catch {
    mappings.value = [];
    logs.value = [];
    detailError.value = '字段映射或同步日志暂时无法加载。';
  } finally {
    detailLoading.value = false;
  }
}

async function toggleTask(task: FeishuTask, checked: boolean) {
  const previous = task.status;
  task.status = checked ? 1 : 0;
  try {
    await updateFeishuTaskStatus(task.taskId, task.status);
    message.success(checked ? '同步任务已启用' : '同步任务已停用');
  } catch {
    task.status = previous;
  }
}

function openCredential() {
  Object.assign(credentialForm, appConfig, { appSecret: '' });
  credentialOpen.value = true;
}

async function saveCredential() {
  if (!credentialForm.appName?.trim() || !credentialForm.appId?.trim()) {
    message.warning('请完整填写应用名称和 App ID');
    return;
  }
  credentialSaving.value = true;
  try {
    await updateFeishuAppConfig(credentialForm);
    Object.assign(appConfig, credentialForm);
    credentialOpen.value = false;
    message.success('飞书应用凭证已保存');
  } finally {
    credentialSaving.value = false;
  }
}

function openTaskModal(task?: FeishuTask) {
  Object.keys(taskForm).forEach((key) => delete (taskForm as any)[key]);
  Object.assign(
    taskForm,
    task ?? { appId: appConfig.appId, status: 1, taskType: 0 },
  );
  sheetOptions.value = [];
  taskOpen.value = true;
}

async function connectTables() {
  if (!taskForm.docUrl?.trim())
    return void message.warning('请先输入飞书文档链接或 App Token');
  connecting.value = true;
  try {
    const data = await connectFeishuTables({
      appId: appConfig.appId,
      appTokenOrUrl: taskForm.docUrl.trim(),
      taskType: taskForm.taskType ?? 0,
    });
    sheetOptions.value = data.tables ?? [];
    taskForm.appToken = data.appToken;
    message.info(
      sheetOptions.value.length > 0
        ? `已获取 ${sheetOptions.value.length} 个子表`
        : '未获取到子表，请检查文档地址',
    );
  } finally {
    connecting.value = false;
  }
}

async function saveTask() {
  if (!taskForm.taskName?.trim() || !taskForm.tableId)
    return void message.warning('请填写任务名称并选择子表');
  taskSaving.value = true;
  try {
    const selectedSheet = sheetOptions.value.find(
      (sheet) => sheet.tableId === taskForm.tableId,
    );
    taskForm.tableName ||= selectedSheet?.name;
    await (taskForm.taskId
      ? updateFeishuTask(taskForm)
      : createFeishuTask(taskForm));
    await loadTasks();
    taskOpen.value = false;
    message.success(taskForm.taskId ? '同步任务已保存' : '同步任务已创建');
  } finally {
    taskSaving.value = false;
  }
}

function removeTask(task: FeishuTask) {
  Modal.confirm({
    cancelText: '取消',
    content: '删除后会同时清除该任务的字段映射，操作不可撤销。',
    okButtonProps: { danger: true },
    okText: '删除',
    title: `删除「${task.taskName}」？`,
    async onOk() {
      await deleteFeishuTask(task.taskId);
      tasks.value = tasks.value.filter((item) => item.taskId !== task.taskId);
      selectedTaskId.value = tasks.value[0]?.taskId;
      message.success('同步任务已删除');
    },
  });
}

async function runConnectionTest() {
  if (!selectedTask.value) return;
  await testFeishuConnection(selectedTask.value.taskId);
  message.success('飞书表格连接正常');
}

async function syncNow() {
  if (!selectedTask.value) return;
  await triggerFeishuTask(selectedTask.value.taskId);
  selectedTask.value.lastSyncTime = '刚刚';
  message.success(`已触发「${selectedTask.value.taskName}」全量同步`);
  window.setTimeout(() => void loadTaskDetail(), 800);
}

async function startMappingEdit() {
  const task = selectedTask.value;
  if (!task) return;
  editingMappings.value = mappings.value.map((item) => ({ ...item }));
  try {
    const [columnsResponse, fieldsResponse] = await Promise.all([
      getFeishuTableColumns(task.targetTableName ?? ''),
      getFeishuFields(task.taskId),
    ]);
    systemColumns.value = columnsResponse;
    feishuFields.value = fieldsResponse;
  } catch {
    systemColumns.value = [];
    feishuFields.value = [];
  }
  mappingEditing.value = true;
}

function addMapping() {
  editingMappings.value.push({
    feishuFieldName: '',
    isSplit: 0,
    systemFieldName: '',
    taskId: selectedTaskId.value,
  });
}

async function saveMappings() {
  if (!selectedTask.value) return;
  const valid = editingMappings.value.filter(
    (item) => item.systemFieldName && item.feishuFieldName,
  );
  if (valid.length !== editingMappings.value.length)
    return void message.warning('请完善所有映射行，或删除空白行');
  await saveFeishuMappings({
    mappings: valid,
    taskId: selectedTask.value.taskId,
  });
  mappings.value = valid.map((item) => ({ ...item }));
  mappingEditing.value = false;
  message.success('字段映射已保存');
}

async function selectTask(taskId: number | string) {
  selectedTaskId.value = taskId;
  activeTab.value = 'mapping';
  await commitQueryState();
}

watch(tableKeyword, () => void commitQueryState());
watch(selectedTaskId, () => {
  if (routeStateReady.value) void loadTaskDetail();
});
watch(activeTab, async (tab) => {
  if (!routeStateReady.value) return;
  await commitQueryState();
  if (tab === 'log') await loadTaskDetail();
});
onMounted(async () => {
  await restoreFromRoute();
  await Promise.all([loadTasks(), loadAppConfig()]);
  await commitQueryState();
  routeStateReady.value = true;
  await loadTaskDetail();
});
</script>

<template>
  <main
    class="adpulse-section-page account-feishu-sync-page min-h-full text-slate-700"
  >
    <div class="mx-auto flex max-w-[1800px] flex-col">
      <header
        class="business-page-header flex flex-wrap items-center justify-between"
      >
        <div class="flex items-center gap-3">
          <div>
            <h1 class="m-0 font-semibold text-slate-900">文档同步</h1>
            <p class="m-0 mt-1 text-sm text-slate-500">
              管理同步任务、字段映射与运行日志
            </p>
          </div>
        </div>
        <Button :loading="loading" @click="loadTasks(true)">
          <IconifyIcon icon="lucide:refresh-cw" /> 刷新
        </Button>
      </header>

      <Alert
        v-if="loadError"
        banner
        :message="loadError"
        show-icon
        type="error"
      >
        <template #action>
          <Button @click="() => loadTasks()">重新加载</Button>
        </template>
      </Alert>

      <Card :body-style="{ padding: 'var(--adpulse-card-padding)' }">
        <div
          class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"
        >
          <div class="flex min-w-0 items-center gap-4">
            <div
              class="bg-primary flex size-9 shrink-0 items-center justify-center rounded-lg text-base text-white"
            >
              <IconifyIcon icon="lucide:send" />
            </div>
            <div class="min-w-0">
              <div class="text-lg font-semibold text-slate-900">
                {{ appConfig.appName || 'Mpower 飞书应用' }}
              </div>
              <code class="mt-1 block truncate text-sm text-slate-500">{{
                appConfig.appId || '尚未配置 App ID'
              }}</code>
            </div>
            <div class="hidden h-12 w-px bg-slate-200 sm:block"></div>
            <div class="hidden sm:block">
              <div class="text-xs font-semibold tracking-wide text-slate-400">
                APP SECRET
              </div>
              <div class="mt-1 tracking-[0.3em] text-slate-500">
                ••••••••••••••••
              </div>
            </div>
          </div>
          <Button @click="openCredential">
            <IconifyIcon icon="lucide:key-round" /> 编辑凭证
          </Button>
        </div>
      </Card>

      <div class="grid min-w-0 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card :body-style="{ padding: 0 }" class="min-w-0">
          <div
            class="flex items-center justify-between border-b border-slate-100 p-4"
          >
            <div>
              <div class="text-lg font-semibold text-slate-900">同步任务</div>
              <div class="mt-1 text-sm text-slate-500">
                {{ tasks.length }} 个任务 · {{ enabledCount }} 个启用
              </div>
            </div>
            <Button type="primary" @click="openTaskModal()">
              <IconifyIcon icon="lucide:plus" /> 添加
            </Button>
          </div>
          <div class="p-4">
            <Input
              v-model:value="tableKeyword"
              allow-clear
              placeholder="搜索任务名 / Table ID"
            >
              <template #prefix><IconifyIcon icon="lucide:search" /></template>
            </Input>
            <Spin :spinning="loading">
              <div
                class="mt-4 max-h-[var(--adpulse-table-viewport-height)] space-y-2 overflow-auto pr-1"
              >
                <button
                  v-for="task in filteredTasks"
                  :key="task.taskId"
                  class="w-full rounded-lg border p-3 text-left transition"
                  :class="
                    task.taskId === selectedTaskId
                      ? 'border-blue-500 bg-blue-50 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-blue-300'
                  "
                  type="button"
                  @click="selectTask(task.taskId)"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="truncate font-semibold text-slate-800">
                        {{ task.taskName }}
                      </div>
                      <code
                        class="mt-1 block truncate text-xs text-slate-400"
                        >{{ task.tableId }}</code
                      >
                    </div>
                    <div class="flex items-center gap-2" @click.stop>
                      <Tooltip title="删除任务">
                        <Button danger type="text" @click="removeTask(task)">
                          <IconifyIcon icon="lucide:trash-2" />
                        </Button>
                      </Tooltip>
                      <Switch
                        :checked="Number(task.status) === 1"
                        @change="
                          (checked) => toggleTask(task, Boolean(checked))
                        "
                      />
                    </div>
                  </div>
                  <div
                    class="mt-2 flex items-center gap-2 text-xs text-slate-500"
                  >
                    <span
                      class="size-2 rounded-full"
                      :class="
                        Number(task.status) === 1
                          ? 'bg-emerald-500'
                          : 'bg-slate-300'
                      "
                    ></span
                    >{{ Number(task.status) === 1 ? '已启用' : '已停用' }} ·
                    {{ task.lastSyncTime || '尚未同步' }}
                  </div>
                </button>
              </div>
            </Spin>
            <Empty
              v-if="!loading && filteredTasks.length === 0"
              class="py-8"
              description="暂无同步任务"
            />
          </div>
        </Card>

        <Card v-if="selectedTask" :body-style="{ padding: 0 }" class="min-w-0">
          <div
            class="flex flex-col gap-4 border-b border-slate-100 p-5 lg:flex-row lg:items-center lg:justify-between"
          >
            <div class="min-w-0">
              <div
                class="flex flex-wrap items-center gap-2 text-xl font-semibold text-slate-900"
              >
                {{ selectedTask.taskName
                }}<Tag
                  :color="
                    Number(selectedTask.status) === 1 ? 'success' : 'default'
                  "
                >
                  {{ Number(selectedTask.status) === 1 ? '启用中' : '已停用' }}
                </Tag>
              </div>
              <div
                class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500"
              >
                <span
                  >App Token
                  <code>{{ selectedTask.appToken || '—' }}</code></span
                ><span
                  >Table ID <code>{{ selectedTask.tableId }}</code></span
                ><span
                  >系统表
                  <code>{{ selectedTask.targetTableName || '—' }}</code></span
                >
              </div>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button @click="openTaskModal(selectedTask)">
                <IconifyIcon icon="lucide:settings-2" /> 编辑任务 </Button
              ><Button @click="runConnectionTest">
                <IconifyIcon icon="lucide:plug-zap" /> 测试连接 </Button
              ><Button type="primary" @click="syncNow">
                <IconifyIcon icon="lucide:refresh-cw" /> 全量同步
              </Button>
            </div>
          </div>
          <Spin :spinning="detailLoading">
            <div class="p-5">
              <Alert
                v-if="detailError"
                class="mb-4"
                :message="detailError"
                show-icon
                type="error"
              />
              <Tabs v-model:active-key="activeTab">
                <Tabs.TabPane key="mapping" tab="字段映射">
                  <div
                    class="flex flex-wrap items-center justify-between gap-3 pb-4 pt-2"
                  >
                    <div>
                      <div class="font-semibold text-slate-900">
                        字段映射配置
                      </div>
                      <div class="mt-1 text-sm text-slate-500">
                        已配置 {{ mappings.length }} 个字段；必填项保存前会校验
                      </div>
                    </div>
                    <div class="flex gap-2">
                      <template v-if="mappingEditing">
                        <Button @click="addMapping">
                          <IconifyIcon icon="lucide:plus" /> 添加映射 </Button
                        ><Button @click="mappingEditing = false">取消</Button
                        ><Button type="primary" @click="saveMappings">
                          保存映射
                        </Button> </template
                      ><Button v-else @click="startMappingEdit">
                        <IconifyIcon icon="lucide:pen-line" /> 编辑映射
                      </Button>
                    </div>
                  </div>
                  <Table
                    :columns="mappingColumns"
                    :data-source="mappingEditing ? editingMappings : mappings"
                    :pagination="false"
                    :scroll="{ x: 760 }"
                    row-key="systemFieldName"
                  >
                    <template #bodyCell="{ column, record, index }">
                      <template v-if="column.key === 'systemFieldName'">
                        <Select
                          v-if="mappingEditing"
                          v-model:value="record.systemFieldName"
                          class="w-full"
                          :options="
                            systemColumns.map((item) => ({
                              label: item.columnComment || item.columnName,
                              value: item.columnName,
                            }))
                          "
                          show-search
                        /><span v-else
                          >{{ record.columnComment || record.systemFieldName
                          }}<span
                            v-if="record.isRequired"
                            class="ml-1 text-red-500"
                            >*</span
                          ></span
                        >
                      </template>
                      <template v-else-if="column.key === 'direction'">
                        <span class="text-slate-400">←</span>
                      </template>
                      <template v-else-if="column.key === 'feishuFieldName'">
                        <Select
                          v-if="mappingEditing"
                          v-model:value="record.feishuFieldName"
                          class="w-full"
                          :options="
                            feishuFields.map((item) => ({
                              label: item.fieldName || item.name,
                              value: item.fieldName || item.name,
                            }))
                          "
                          show-search
                        /><span v-else>{{ record.feishuFieldName }}</span>
                      </template>
                      <template v-else-if="column.key === 'isSplit'">
                        <Switch
                          v-if="mappingEditing"
                          v-model:checked="record.isSplit"
                          :checked-value="1"
                          :un-checked-value="0"
                        /><span v-else>{{ record.isSplit ? '是' : '否' }}</span>
                      </template>
                      <template
                        v-else-if="column.key === 'actions' && mappingEditing"
                      >
                        <Button
                          danger
                          type="text"
                          @click="editingMappings.splice(index, 1)"
                        >
                          删除
                        </Button>
                      </template>
                    </template>
                  </Table>
                </Tabs.TabPane>
                <Tabs.TabPane key="log" tab="运行日志">
                  <Table
                    :columns="logColumns"
                    :data-source="logs"
                    :pagination="{ pageSize: 10 }"
                    :scroll="{ x: 900 }"
                    row-key="id"
                  >
                    <template #bodyCell="{ column, record }">
                      <Tag
                        v-if="column.dataIndex === 'status'"
                        :color="
                          Number(record.status) === 1
                            ? 'success'
                            : Number(record.status) === 0
                              ? 'processing'
                              : 'error'
                        "
                      >
                        {{
                          Number(record.status) === 1
                            ? '成功'
                            : Number(record.status) === 0
                              ? '运行中'
                              : '失败'
                        }}
                      </Tag>
                    </template>
                  </Table>
                  <Empty v-if="logs.length === 0" description="暂无运行日志" />
                </Tabs.TabPane>
              </Tabs>
            </div>
          </Spin>
        </Card>
        <Card v-else class="border-0 shadow-sm">
          <div
            class="flex min-h-[380px] flex-col items-center justify-center px-6 text-center"
          >
            <div
              class="bg-primary/10 text-primary flex size-12 items-center justify-center rounded-[var(--adpulse-card-radius)] text-2xl"
            >
              <IconifyIcon icon="lucide:table-properties" />
            </div>
            <h2 class="mb-0 mt-5 text-xl font-semibold text-slate-900">
              创建第一个飞书同步任务
            </h2>
            <p class="mb-5 mt-2 max-w-md text-sm leading-6 text-slate-500">
              绑定飞书多维表格或云文档表格后，可以配置系统字段映射、手动触发同步并查看每次运行日志。
            </p>
            <Button type="primary" @click="openTaskModal()">
              <IconifyIcon icon="lucide:plus" /> 添加同步任务
            </Button>
          </div>
        </Card>
      </div>
    </div>

    <Modal
      v-model:open="credentialOpen"
      :confirm-loading="credentialSaving"
      ok-text="保存"
      title="编辑飞书应用凭证"
      @ok="saveCredential"
    >
      <Form layout="vertical">
        <Form.Item label="应用名称" required>
          <Input
            v-model:value="credentialForm.appName"
            placeholder="例如：Mpower 飞书应用"
          /> </Form.Item
        ><Form.Item label="App ID" required>
          <Input
            v-model:value="credentialForm.appId"
            placeholder="cli_xxx"
          /> </Form.Item
        ><Form.Item label="App Secret" :required="!credentialForm.id">
          <Input.Password
            v-model:value="credentialForm.appSecret"
            placeholder="留空表示不修改（编辑时）"
          />
        </Form.Item>
      </Form>
    </Modal>

    <Modal
      v-model:open="taskOpen"
      :confirm-loading="taskSaving"
      ok-text="保存任务"
      :title="taskForm.taskId ? '编辑同步任务' : '添加同步任务'"
      width="620px"
      @ok="saveTask"
    >
      <Form layout="vertical">
        <Form.Item label="任务名称" required>
          <Input
            v-model:value="taskForm.taskName"
            placeholder="请输入任务名称"
          />
        </Form.Item>
        <div class="grid gap-4 sm:grid-cols-2">
          <Form.Item label="表格类型" required>
            <Select
              v-model:value="taskForm.taskType"
              :options="[
                { label: '多维表格', value: 0 },
                { label: '云文档表格', value: 1 },
              ]"
            /> </Form.Item
          ><Form.Item label="映射系统表" required>
            <Input
              v-model:value="taskForm.targetTableName"
              placeholder="例如 fb_account"
            />
          </Form.Item>
        </div>
        <Form.Item label="飞书文档地址">
          <Input
            v-model:value="taskForm.docUrl"
            placeholder="输入飞书文档链接或 App Token"
          >
            <template #addonAfter>
              <Button :loading="connecting" type="link" @click="connectTables">
                获取子表
              </Button>
            </template>
          </Input> </Form.Item
        ><Form.Item label="选择子表" required>
          <Select
            v-model:value="taskForm.tableId"
            :disabled="sheetOptions.length === 0 && !taskForm.tableId"
            :options="
              sheetOptions.map((item) => ({
                label: item.name,
                value: item.tableId,
              }))
            "
            :placeholder="
              taskForm.tableId
                ? taskForm.tableName || taskForm.tableId
                : '请先获取子表'
            "
            show-search
          /> </Form.Item
        ><Form.Item label="同步状态">
          <Switch
            v-model:checked="taskForm.status"
            :checked-value="1"
            :un-checked-value="0"
          />
        </Form.Item>
      </Form>
    </Modal>
  </main>
</template>

<style scoped>
.account-feishu-sync-page {
  padding: var(--adpulse-page-gutter);
  background: var(--adpulse-surface-muted);
}

.account-feishu-sync-page > div {
  gap: var(--adpulse-section-gap);
}

.account-feishu-sync-page h1 {
  font-size: var(--adpulse-page-title-size);
  line-height: 1.35;
}

.account-feishu-sync-page .business-page-header {
  min-height: var(--adpulse-page-header-min-height);
  gap: var(--adpulse-action-gap);
  padding: var(--adpulse-page-header-padding-block) var(--adpulse-page-gutter);
}
</style>
