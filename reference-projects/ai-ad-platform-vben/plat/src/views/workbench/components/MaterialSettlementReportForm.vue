<script lang="ts" setup>
import type { FormInstance, FormProps } from 'ant-design-vue';

import type { ProjectStatus, ProjectSummary } from '#/api';
import type { AgencyLine } from '#/domain/agency-line';
import type {
  MaterialSettlementReportFormValue,
  MaterialSettlementTaskLineSnapshot,
} from '#/domain/material-designer-settlement';

import { computed, onMounted, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Checkbox,
  DatePicker,
  Empty,
  Form,
  FormItem,
  FormItemRest,
  Input,
  InputNumber,
  Select,
  Skeleton,
  Tag,
  message,
} from 'ant-design-vue';

import { getDictionaryOptions } from '#/api';
import { agencyLineService } from '#/domain/agency-line';
import { projectService } from '#/domain/project';

defineOptions({ name: 'MaterialSettlementReportForm' });

interface MaterialSettlementFormState {
  commissionRatio?: number;
  pitcherIds: string[];
  projectIds: string[];
  remark: string;
  settlementMonth: string;
  taskLineIds: string[];
}

interface PitcherOption {
  id: string;
  name: string;
}

const selectableProjectStatuses = new Set<ProjectStatus>([
  'active',
  'ended',
  'paused',
]);
const formRef = ref<FormInstance>();
const loading = ref(false);
const loadError = ref('');
const commissionRatioOptions = ref<Array<{ label: string; value: number }>>([]);
const projects = ref<ProjectSummary[]>([]);
const agencyLines = ref<AgencyLine[]>([]);
const pitcherKeyword = ref('');
const projectKeyword = ref('');
const taskLineKeyword = ref('');
const form = reactive<MaterialSettlementFormState>({
  commissionRatio: undefined,
  pitcherIds: [],
  projectIds: [],
  remark: '',
  settlementMonth: '',
  taskLineIds: [],
});

const formRules: FormProps['rules'] = {
  commissionRatio: [
    { required: true, message: '请选择提成比例', trigger: 'change' },
  ],
  pitcherIds: [
    { required: true, message: '请至少选择一位投放师', trigger: 'change' },
  ],
  projectIds: [
    { required: true, message: '请至少选择一个项目', trigger: 'change' },
  ],
  settlementMonth: [
    { required: true, message: '请选择结算月份', trigger: 'change' },
  ],
  taskLineIds: [
    { required: true, message: '请至少选择一条任务线', trigger: 'change' },
  ],
};

const eligibleProjects = computed(() =>
  projects.value.filter((project) =>
    selectableProjectStatuses.has(project.status),
  ),
);
const projectById = computed(
  () => new Map(eligibleProjects.value.map((project) => [project.id, project])),
);
/**
 * 新系统以项目代理线承接 MPower 的任务线语义；代理线上的优化师即原结算投放师。
 */
const selectableTaskLines = computed(() =>
  agencyLines.value.filter(
    (line) =>
      Boolean(line.optimizerId && line.optimizerName.trim()) &&
      Boolean(line.projectId && projectById.value.has(line.projectId)),
  ),
);
const pitcherOptions = computed<PitcherOption[]>(() => {
  const options = new Map<string, PitcherOption>();
  selectableTaskLines.value.forEach((line) => {
    if (!line.optimizerId || !line.optimizerName.trim()) return;
    options.set(line.optimizerId, {
      id: line.optimizerId,
      name: line.optimizerName,
    });
  });
  return [...options.values()].sort((left, right) =>
    left.name.localeCompare(right.name, 'zh-CN'),
  );
});
const selectedPitcherIdSet = computed(() => new Set(form.pitcherIds));
const projectsForSelectedPitchers = computed(() => {
  const projectIds = new Set(
    selectableTaskLines.value
      .filter(
        (line) =>
          line.optimizerId && selectedPitcherIdSet.value.has(line.optimizerId),
      )
      .map((line) => line.projectId)
      .filter((id): id is string => Boolean(id)),
  );
  return eligibleProjects.value
    .filter((project) => projectIds.has(project.id))
    .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
});
const taskLinesForSelectedProjects = computed(() => {
  const selectedProjectIdSet = new Set(form.projectIds);
  return selectableTaskLines.value
    .filter((line) =>
      Boolean(
        line.projectId &&
          line.optimizerId &&
          selectedProjectIdSet.has(line.projectId) &&
          selectedPitcherIdSet.value.has(line.optimizerId),
      ),
    )
    .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
});
const selectedTaskLines = computed(() => {
  const selectedIds = new Set(form.taskLineIds);
  return selectableTaskLines.value.filter((line) => selectedIds.has(line.id));
});

function matchesKeyword(value: string, keyword: string) {
  return value.toLocaleLowerCase().includes(keyword.trim().toLocaleLowerCase());
}

const filteredPitchers = computed(() =>
  pitcherOptions.value.filter((pitcher) =>
    matchesKeyword(pitcher.name, pitcherKeyword.value),
  ),
);
const filteredProjects = computed(() =>
  projectsForSelectedPitchers.value.filter((project) =>
    matchesKeyword(project.name, projectKeyword.value),
  ),
);
const filteredTaskLines = computed(() =>
  taskLinesForSelectedProjects.value.filter((line) =>
    matchesKeyword(line.name, taskLineKeyword.value),
  ),
);

function unique(values: string[]) {
  return [...new Set(values)];
}

function normalizeCommissionRatioOptions(
  options: Array<{ label: string; value: string }>,
) {
  const ratios = options
    .map(({ value }) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0 && value <= 100);
  return unique(ratios.map(String)).map((value) => ({
    label: `${value}%`,
    value: Number(value),
  }));
}

function isPitcherSelected(pitcherId: string) {
  return form.pitcherIds.includes(pitcherId);
}

function isProjectSelected(projectId: string) {
  return form.projectIds.includes(projectId);
}

function isTaskLineSelected(taskLineId: string) {
  return form.taskLineIds.includes(taskLineId);
}

function clearSelectionValidation() {
  formRef.value?.clearValidate(['pitcherIds', 'projectIds', 'taskLineIds']);
}

/** 选择投放师时默认勾选其全部可结算项目与任务线，与 MPower 行为保持一致。 */
function togglePitcher(pitcherId: string) {
  if (isPitcherSelected(pitcherId)) {
    form.pitcherIds = form.pitcherIds.filter((id) => id !== pitcherId);
    const remainingLines = selectableTaskLines.value.filter(
      (line) =>
        line.optimizerId && selectedPitcherIdSet.value.has(line.optimizerId),
    );
    const remainingLineIds = new Set(remainingLines.map((line) => line.id));
    const remainingProjectIds = new Set(
      remainingLines
        .map((line) => line.projectId)
        .filter((id): id is string => Boolean(id)),
    );
    form.taskLineIds = form.taskLineIds.filter((id) =>
      remainingLineIds.has(id),
    );
    form.projectIds = form.projectIds.filter((id) =>
      remainingProjectIds.has(id),
    );
  } else {
    form.pitcherIds = [...form.pitcherIds, pitcherId];
    const addedLines = selectableTaskLines.value.filter(
      (line) => line.optimizerId === pitcherId,
    );
    form.projectIds = unique([
      ...form.projectIds,
      ...addedLines
        .map((line) => line.projectId)
        .filter((id): id is string => Boolean(id)),
    ]);
    form.taskLineIds = unique([
      ...form.taskLineIds,
      ...addedLines.map((line) => line.id),
    ]);
  }
  clearSelectionValidation();
}

function taskLinesForProject(projectId: string) {
  return selectableTaskLines.value.filter(
    (line) =>
      line.projectId === projectId &&
      Boolean(
        line.optimizerId && selectedPitcherIdSet.value.has(line.optimizerId),
      ),
  );
}

function toggleProject(projectId: string) {
  const projectLineIds = taskLinesForProject(projectId).map((line) => line.id);
  if (isProjectSelected(projectId)) {
    const removedLineIds = new Set(projectLineIds);
    form.projectIds = form.projectIds.filter((id) => id !== projectId);
    form.taskLineIds = form.taskLineIds.filter((id) => !removedLineIds.has(id));
  } else {
    form.projectIds = [...form.projectIds, projectId];
    form.taskLineIds = unique([...form.taskLineIds, ...projectLineIds]);
  }
  clearSelectionValidation();
}

function isProjectIndeterminate(projectId: string) {
  const lines = taskLinesForProject(projectId);
  const selectedCount = lines.filter((line) =>
    form.taskLineIds.includes(line.id),
  ).length;
  return selectedCount > 0 && selectedCount < lines.length;
}

function toggleTaskLine(taskLine: AgencyLine) {
  if (isTaskLineSelected(taskLine.id)) {
    form.taskLineIds = form.taskLineIds.filter((id) => id !== taskLine.id);
  } else {
    form.taskLineIds = [...form.taskLineIds, taskLine.id];
    if (taskLine.projectId && !form.projectIds.includes(taskLine.projectId)) {
      form.projectIds = [...form.projectIds, taskLine.projectId];
    }
  }
  clearSelectionValidation();
}

function removeTaskLine(taskLineId: string) {
  form.taskLineIds = form.taskLineIds.filter((id) => id !== taskLineId);
  clearSelectionValidation();
}

function reconcileSelection() {
  const validPitcherIds = new Set(pitcherOptions.value.map(({ id }) => id));
  form.pitcherIds = form.pitcherIds.filter((id) => validPitcherIds.has(id));
  const validProjectIds = new Set(
    projectsForSelectedPitchers.value.map(({ id }) => id),
  );
  form.projectIds = form.projectIds.filter((id) => validProjectIds.has(id));
  const validTaskLineIds = new Set(
    taskLinesForSelectedProjects.value.map(({ id }) => id),
  );
  form.taskLineIds = form.taskLineIds.filter((id) => validTaskLineIds.has(id));
}

async function loadSelectionData() {
  loading.value = true;
  loadError.value = '';
  try {
    const [projectResult, agencyLineResult, ratioOptions] = await Promise.all([
      projectService.list({ page: 1, pageSize: 1000 }),
      agencyLineService.list({ page: 1, pageSize: 1000 }),
      getDictionaryOptions('material_engineer_report_commission_ratio', {
        skipErrorMessage: true,
      }).catch(() => []),
    ]);
    projects.value = projectResult.items;
    agencyLines.value = agencyLineResult.items;
    commissionRatioOptions.value =
      normalizeCommissionRatioOptions(ratioOptions);
    reconcileSelection();
  } catch (error) {
    loadError.value =
      error instanceof Error
        ? error.message
        : '项目管理数据加载失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

function createTaskLineSnapshot(
  taskLine: AgencyLine,
): MaterialSettlementTaskLineSnapshot | undefined {
  if (!taskLine.projectId || !taskLine.optimizerId) return undefined;
  const project = projectById.value.get(taskLine.projectId);
  if (!project) return undefined;
  return {
    id: taskLine.id,
    name: taskLine.name,
    pitcherId: taskLine.optimizerId,
    pitcherName: taskLine.optimizerName,
    platform: taskLine.platform,
    projectId: project.id,
    projectName: project.name,
  };
}

/** 校验固定表单并返回提交快照；父页面只负责审批与日报接口编排。 */
async function validate(): Promise<
  MaterialSettlementReportFormValue | undefined
> {
  if (loading.value) {
    message.info('正在读取项目管理数据，请稍候');
    return undefined;
  }
  if (loadError.value) {
    message.warning('请先重新加载项目管理数据');
    return undefined;
  }
  try {
    await formRef.value?.validate();
  } catch {
    return undefined;
  }

  const taskLines = selectedTaskLines.value
    .map(createTaskLineSnapshot)
    .filter((item): item is MaterialSettlementTaskLineSnapshot =>
      Boolean(item),
    );
  const commissionRatio = form.commissionRatio;
  if (commissionRatio === undefined) return undefined;

  const pitcherIds = unique(taskLines.map(({ pitcherId }) => pitcherId));
  const projectIds = unique(taskLines.map(({ projectId }) => projectId));
  const pitcherNamesById = new Map(
    taskLines.map(({ pitcherId, pitcherName }) => [pitcherId, pitcherName]),
  );
  const projectNamesById = new Map(
    taskLines.map(({ projectId, projectName }) => [projectId, projectName]),
  );

  return {
    commissionRatio,
    pitcherIds,
    pitcherNames: pitcherIds.map((id) => pitcherNamesById.get(id) || id),
    platforms: unique(taskLines.map(({ platform }) => platform)),
    projectIds,
    projectNames: projectIds.map((id) => projectNamesById.get(id) || id),
    remark: form.remark.trim(),
    settlementMonth: form.settlementMonth,
    taskLineIds: taskLines.map(({ id }) => id),
    taskLineNames: taskLines.map(({ name }) => name),
    taskLines,
  };
}

defineExpose({ validate });

onMounted(loadSelectionData);
</script>

<template>
  <Form
    ref="formRef"
    :model="form"
    :rules="formRules"
    layout="vertical"
    @submit.prevent
  >
    <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
      <FormItem label="选择结算时间" name="settlementMonth" required>
        <DatePicker
          v-model:value="form.settlementMonth"
          class="w-full"
          picker="month"
          value-format="YYYY-MM"
          placeholder="请选择结算月份"
        />
      </FormItem>
      <FormItem label="选择提成比例" name="commissionRatio" required>
        <Select
          v-if="commissionRatioOptions.length > 0"
          v-model:value="form.commissionRatio"
          :options="commissionRatioOptions"
          placeholder="请选择提成比例"
        />
        <InputNumber
          v-else
          v-model:value="form.commissionRatio"
          :max="100"
          :min="0.01"
          :precision="2"
          :step="0.01"
          class="w-full"
          placeholder="请输入提成比例"
        >
          <template #addonAfter>%</template>
        </InputNumber>
      </FormItem>
      <FormItem label="备注" class="md:col-span-2">
        <Input.TextArea
          v-model:value="form.remark"
          :maxlength="500"
          :rows="3"
          show-count
          placeholder="请输入备注（选填）"
        />
      </FormItem>
    </div>

    <FormItem label="已选任务线" name="taskLineIds" required>
      <div
        class="flex min-h-10 flex-wrap items-center gap-2 py-1"
        aria-live="polite"
      >
        <Tag
          v-for="taskLine in selectedTaskLines"
          :key="taskLine.id"
          closable
          class="!border-border !bg-muted !text-foreground !m-0 !inline-flex !h-8 !items-center !rounded-md !px-2"
          @close="removeTaskLine(taskLine.id)"
        >
          {{ projectById.get(taskLine.projectId || '')?.name }} /
          {{ taskLine.name }}
        </Tag>
        <Tag
          v-if="selectedTaskLines.length === 0"
          class="!border-border !bg-muted !text-muted-foreground !m-0 !rounded-md !px-2 !py-1"
        >
          暂未选择任务线
        </Tag>
      </div>
    </FormItem>

    <Alert
      class="mb-4"
      message="仅可选择进行中、已暂停和已结束的项目；任务线来自“项目管理”的代理线数据。"
      show-icon
      type="warning"
    />

    <Alert
      v-if="loadError"
      class="mb-4"
      :message="loadError"
      show-icon
      type="error"
    >
      <template #action>
        <Button @click="loadSelectionData">重新加载</Button>
      </template>
    </Alert>

    <Skeleton v-if="loading" active :paragraph="{ rows: 5 }" />
    <div
      v-else
      class="border-border grid overflow-hidden rounded-[var(--adpulse-radius)] border lg:grid-cols-3"
    >
      <section
        class="border-border flex min-w-0 flex-col border-b lg:border-b-0 lg:border-r"
        aria-labelledby="material-settlement-pitcher-heading"
      >
        <div class="bg-muted/40 border-border border-b px-4 py-3">
          <strong id="material-settlement-pitcher-heading" class="text-sm">
            投放师
          </strong>
          <p class="text-muted-foreground mb-0 mt-1 text-xs">
            来自代理线配置的优化师
          </p>
        </div>
        <div class="border-border border-b p-2">
          <Input
            v-model:value="pitcherKeyword"
            allow-clear
            placeholder="搜索投放师"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" aria-hidden="true" />
            </template>
          </Input>
        </div>
        <FormItem name="pitcherIds" class="!mb-0">
          <FormItemRest>
            <div class="h-64 overflow-y-auto p-2 lg:h-80">
              <Checkbox
                v-for="pitcher in filteredPitchers"
                :key="pitcher.id"
                :checked="isPitcherSelected(pitcher.id)"
                class="hover:bg-accent !ml-0 flex min-h-11 w-full items-center rounded-md px-2 py-1"
                @change="togglePitcher(pitcher.id)"
              >
                <span class="text-foreground block truncate">{{
                  pitcher.name
                }}</span>
              </Checkbox>
              <Empty
                v-if="filteredPitchers.length === 0"
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                description="暂无可选投放师"
              />
            </div>
          </FormItemRest>
        </FormItem>
      </section>

      <section
        class="border-border flex min-w-0 flex-col border-b lg:border-b-0 lg:border-r"
        aria-labelledby="material-settlement-project-heading"
      >
        <div class="bg-muted/40 border-border border-b px-4 py-3">
          <strong id="material-settlement-project-heading" class="text-sm">
            项目
          </strong>
          <p class="text-muted-foreground mb-0 mt-1 text-xs">
            按所选投放师自动筛选
          </p>
        </div>
        <div class="border-border border-b p-2">
          <Input
            v-model:value="projectKeyword"
            allow-clear
            :disabled="form.pitcherIds.length === 0"
            placeholder="搜索项目"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" aria-hidden="true" />
            </template>
          </Input>
        </div>
        <FormItem name="projectIds" class="!mb-0">
          <FormItemRest>
            <div class="h-64 overflow-y-auto p-2 lg:h-80">
              <Checkbox
                v-for="project in filteredProjects"
                :key="project.id"
                :checked="isProjectSelected(project.id)"
                :indeterminate="isProjectIndeterminate(project.id)"
                class="hover:bg-accent !ml-0 flex min-h-11 w-full items-center rounded-md px-2 py-1"
                @change="toggleProject(project.id)"
              >
                <span class="text-foreground block truncate">{{
                  project.name
                }}</span>
              </Checkbox>
              <Empty
                v-if="filteredProjects.length === 0"
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                :description="
                  form.pitcherIds.length ? '暂无匹配项目' : '请先选择投放师'
                "
              />
            </div>
          </FormItemRest>
        </FormItem>
      </section>

      <section
        class="flex min-w-0 flex-col"
        aria-labelledby="material-settlement-task-line-heading"
      >
        <div class="bg-muted/40 border-border border-b px-4 py-3">
          <strong id="material-settlement-task-line-heading" class="text-sm">
            任务线
          </strong>
          <p class="text-muted-foreground mb-0 mt-1 text-xs">
            对应项目当前绑定的代理线
          </p>
        </div>
        <div class="border-border border-b p-2">
          <Input
            v-model:value="taskLineKeyword"
            allow-clear
            :disabled="form.projectIds.length === 0"
            placeholder="搜索任务线"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" aria-hidden="true" />
            </template>
          </Input>
        </div>
        <div class="h-64 overflow-y-auto p-2 lg:h-80">
          <Checkbox
            v-for="taskLine in filteredTaskLines"
            :key="taskLine.id"
            :checked="isTaskLineSelected(taskLine.id)"
            class="hover:bg-accent !ml-0 flex min-h-11 w-full items-center rounded-md px-2 py-1"
            @change="toggleTaskLine(taskLine)"
          >
            <span
              class="flex min-w-0 flex-1 items-center justify-between gap-2"
            >
              <span class="text-foreground block truncate">{{
                taskLine.name
              }}</span>
              <span class="text-muted-foreground shrink-0 text-xs uppercase">
                {{ taskLine.platform }}
              </span>
            </span>
          </Checkbox>
          <Empty
            v-if="filteredTaskLines.length === 0"
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            :description="
              form.projectIds.length ? '暂无匹配任务线' : '请先选择项目'
            "
          />
        </div>
      </section>
    </div>
  </Form>
</template>
