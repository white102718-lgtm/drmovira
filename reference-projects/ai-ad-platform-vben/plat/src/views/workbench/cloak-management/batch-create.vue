<script setup lang="ts">
import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';
import type {
  CloakBatchCreateInput,
  CloakCountryOption,
  CloakDomainOption,
} from '#/domain/cloak';
import type {
  ProjectAgencyLineDeliveryOption,
  ProjectSearchOption,
} from '#/domain/project';
import type { SelectValue } from 'ant-design-vue/es/select';

import { computed, onActivated, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useDebounceFn } from '@vueuse/core';

import {
  Alert,
  Button,
  Card,
  Checkbox,
  CheckboxGroup,
  Input,
  message,
  Radio,
  RadioGroup,
  Select,
  Spin,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';
import { cloakService } from '#/domain/cloak';
import { projectService } from '#/domain/project';

defineOptions({ name: 'WorkbenchCloakBatchCreate' });

type CloakMode = 'all' | 'cloak' | 'off';

interface PromotionDraft {
  agencyLineId: string;
  domainId?: string;
  id: string;
  name: string;
  sourceUrl: string;
  taskLineName?: string;
}

const router = useRouter();
const loadingProjects = ref(false);
const loadingAgencyLines = ref(false);
const loadingDomains = ref(false);
const loadingCountries = ref(false);
const projectOptions = ref<ProjectSearchOption[]>([]);
const selectedProjectOption = ref<ProjectSearchOption>();
const selectedProjectId = ref<string>();
const projectAgencyLines = ref<ProjectAgencyLineDeliveryOption[]>([]);
const occupiedAgencyLineIds = ref(new Set<string>());
const selectedAgencyLineIds = ref<string[]>([]);
const manualLinks = ref('');
const promotionDrafts = ref<PromotionDraft[]>([]);
const domainOptions = ref<CloakDomainOption[]>([]);
const countryOptions = ref<CloakCountryOption[]>([]);
const reviewUrl = ref('');
const mode = ref<CloakMode>('all');
const region = ref<string>();
const blockedLanguage = ref(false);
const blockedPc = ref(false);
const blockedProxy = ref(false);
const linkedTable = ref(true);
const submitting = ref(false);
const submittingText = ref('');
let submittedPayloadFingerprint = '';
let submittedRequestId = '';
let agencyLineRequestSequence = 0;
let occupiedLineRequestSequence = 0;
let projectRequestSequence = 0;

const projectSelectOptions = computed(() =>
  projectOptions.value.map((project) => ({
    label: project.name,
    value: project.id,
  })),
);
const domainSelectOptions = computed(() =>
  domainOptions.value.map((option) => ({
    ...option,
    label: option.genDomain.startsWith('.')
      ? option.genDomain
      : `.${option.genDomain}`,
  })),
);
const agencyLineRows = computed(() =>
  projectAgencyLines.value.map((line, index) => ({
    ...line,
    sequence: index + 1,
  })),
);
const normalizedManualLinks = computed(() =>
  manualLinks.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean),
);

function resolveSubmitRequestId(
  payload: Omit<CloakBatchCreateInput, 'requestId'>,
) {
  const fingerprint = JSON.stringify(payload);
  if (fingerprint !== submittedPayloadFingerprint) {
    submittedPayloadFingerprint = fingerprint;
    submittedRequestId = crypto.randomUUID();
  }
  return submittedRequestId;
}
const isOverLimit = computed(() => normalizedManualLinks.value.length > 50);
const completedDraftCount = computed(
  () =>
    promotionDrafts.value.filter((item) => item.name && item.domainId).length,
);
const agencyLineColumns: ShadcnDataTableColumn[] = [
  { align: 'left', key: 'select', title: '选择', width: 64 },
  { align: 'left', key: 'sequence', title: '序号', width: 64 },
  { key: 'name', title: '代理线', width: 260 },
  { key: 'platform', title: '平台', width: 110 },
  { key: 'deliveryUrl', title: '投放链接', width: 440 },
];

async function loadDomainOptions() {
  loadingDomains.value = true;
  try {
    domainOptions.value = await cloakService.listDomains();
  } finally {
    loadingDomains.value = false;
  }
}

async function loadCountryOptions() {
  loadingCountries.value = true;
  try {
    countryOptions.value = await cloakService.listCountries();
  } finally {
    loadingCountries.value = false;
  }
}

async function loadProjectOptions(keyword = '') {
  const requestSequence = ++projectRequestSequence;
  loadingProjects.value = true;
  try {
    const results = await projectService.searchOptions(keyword);
    if (requestSequence !== projectRequestSequence) return;
    const selected = selectedProjectOption.value;
    projectOptions.value =
      selected && !results.some((item) => item.id === selected.id)
        ? [selected, ...results]
        : results;
  } finally {
    if (requestSequence === projectRequestSequence) {
      loadingProjects.value = false;
    }
  }
}

const handleProjectSearch = useDebounceFn((keyword: string) => {
  void loadProjectOptions(keyword);
}, 300);

async function refreshOccupiedAgencyLineIds(projectId: string) {
  const requestSequence = ++occupiedLineRequestSequence;
  const occupiedIds = await cloakService.listOccupiedAgencyLineIds(projectId);
  if (
    requestSequence !== occupiedLineRequestSequence ||
    selectedProjectId.value !== projectId
  ) {
    return;
  }
  occupiedAgencyLineIds.value = new Set(occupiedIds);
  selectedAgencyLineIds.value = selectedAgencyLineIds.value.filter(
    (id) => !occupiedAgencyLineIds.value.has(id),
  );
}

async function handleProjectChange(projectId: SelectValue) {
  manualLinks.value = '';
  selectedAgencyLineIds.value = [];
  projectAgencyLines.value = [];
  occupiedAgencyLineIds.value = new Set();
  promotionDrafts.value = [];

  const requestSequence = ++agencyLineRequestSequence;
  loadingAgencyLines.value = false;
  const normalizedProjectId =
    typeof projectId === 'string' ? projectId : undefined;
  selectedProjectOption.value = projectOptions.value.find(
    (item) => item.id === normalizedProjectId,
  );
  if (!normalizedProjectId) return;

  loadingAgencyLines.value = true;
  try {
    const [result, occupiedIds] = await Promise.all([
      projectService.listAgencyLineDeliveryOptions(normalizedProjectId),
      cloakService.listOccupiedAgencyLineIds(normalizedProjectId),
    ]);
    if (requestSequence !== agencyLineRequestSequence) return;
    projectAgencyLines.value = result;
    occupiedAgencyLineIds.value = new Set(occupiedIds);
  } finally {
    if (requestSequence === agencyLineRequestSequence) {
      loadingAgencyLines.value = false;
    }
  }
}

function updatePromotionDrafts() {
  if (normalizedManualLinks.value.length === 0) {
    message.warning('请至少勾选一条有投放链接的代理线');
    return;
  }
  if (isOverLimit.value) {
    message.warning('单次最多创建 50 条推广链接');
    return;
  }

  const selectedLines = projectAgencyLines.value.filter((line) =>
    selectedAgencyLineIds.value.includes(line.id),
  );
  promotionDrafts.value = selectedLines.map((line, index) => {
    const sourceUrl = line.deliveryUrl.trim();
    const existing = promotionDrafts.value[index];
    const canReuseExisting = existing?.agencyLineId === line.id;
    return {
      agencyLineId: line.id,
      domainId: canReuseExisting ? existing.domainId : undefined,
      id: `promotion-${index + 1}`,
      name: canReuseExisting ? existing.name : '',
      sourceUrl,
      taskLineName: line.name,
    };
  });
  message.success(`已同步 ${promotionDrafts.value.length} 条推广链接记录`);
}

function splitNameSegments(value: string) {
  return value
    .trim()
    .split(/[-_ ]+/)
    .filter(Boolean);
}

function autoNameDrafts() {
  if (promotionDrafts.value.length === 0) {
    message.warning('请先更新创建清单');
    return;
  }
  const projectNameSegment = splitNameSegments(
    selectedProjectOption.value?.name ?? '',
  )[0];
  if (!projectNameSegment) {
    message.warning('请先选择项目，再执行自动命名');
    return;
  }

  const defaultDomainId = domainOptions.value[0]?.value;
  if (!defaultDomainId) {
    message.warning('暂无可用推广域名，请稍后重试');
    return;
  }
  let missingTaskLineCount = 0;
  promotionDrafts.value = promotionDrafts.value.map((item) => {
    const taskLineSegments = splitNameSegments(item.taskLineName ?? '').slice(
      -2,
    );
    if (taskLineSegments.length === 0) missingTaskLineCount += 1;
    return {
      ...item,
      domainId: item.domainId || defaultDomainId,
      name: [projectNameSegment, ...taskLineSegments]
        .join('')
        .replace(/[^a-z0-9]/gi, '')
        .toLowerCase(),
    };
  });

  if (missingTaskLineCount > 0) {
    message.warning(
      `已自动填充；${missingTaskLineCount} 条代理线缺少名称，仅使用项目名称命名`,
    );
    return;
  }
  message.success('已自动生成命名并选择默认域名');
}

async function submitBatch() {
  if (!selectedProjectId.value) {
    message.warning('请先选择项目');
    return;
  }
  if (promotionDrafts.value.length === 0) {
    message.warning('请先更新创建清单');
    return;
  }
  if (!reviewUrl.value.trim()) {
    message.warning('请填写审核链接');
    return;
  }
  if (promotionDrafts.value.some((item) => !item.name || !item.domainId)) {
    message.warning('请完成全部推广链接的命名和域名选择');
    return;
  }

  const selectedCountry = countryOptions.value.find(
    (option) => option.value === region.value,
  );
  submitting.value = true;
  submittingText.value = '正在创建斗篷链接…';
  try {
    const payload: Omit<CloakBatchCreateInput, 'requestId'> = {
      blockedLanguage: blockedLanguage.value,
      blockedPc: blockedPc.value,
      blockedProxy: blockedProxy.value,
      country: selectedCountry?.value,
      countryLabel: selectedCountry?.label,
      items: promotionDrafts.value.map((item) => {
        const domain = domainOptions.value.find(
          (option) => option.value === item.domainId,
        );
        if (!domain) throw new Error('推广域名已失效，请重新选择');
        return {
          adUrl: item.name,
          agencyLineId: item.agencyLineId,
          genDomain: domain.genDomain,
          genId: domain.genId,
        };
      }),
      mode: mode.value,
      projectId: selectedProjectId.value,
      reviewUrl: reviewUrl.value.trim(),
    };
    const result = await cloakService.createBatch({
      ...payload,
      requestId: resolveSubmitRequestId(payload),
    });
    if (linkedTable.value) {
      submittingText.value = '批量创建斗篷链接成功，现在正在回写代理线文档…';
      try {
        const writeback = await cloakService.writebackSheet(result.batchId);
        if (writeback.failedCount > 0) {
          const firstFailure = writeback.failures[0];
          const failureDetail = firstFailure
            ? `：${firstFailure.agencyLineName} ${firstFailure.message}`
            : '';
          message.warning({
            content: `斗篷创建成功；文档回写成功 ${writeback.successCount} 条，失败 ${writeback.failedCount} 条${failureDetail}`,
            duration: 8,
          });
        } else {
          message.success({
            content: `已创建并回写 ${writeback.successCount} 条斗篷链接`,
          });
        }
      } catch {
        message.error({
          content:
            '斗篷已创建成功，但代理线文档回写接口调用失败，可在管理列表中重新回填',
          duration: 6,
        });
      }
    } else {
      message.success({
        content: `已成功创建 ${result.totalCount} 条斗篷记录`,
      });
    }
    await router.push('/workbench/cloaks');
  } finally {
    submitting.value = false;
    submittingText.value = '';
  }
}

watch(selectedAgencyLineIds, (agencyLineIds) => {
  const selectedLinks = projectAgencyLines.value
    .filter((line) => agencyLineIds.includes(line.id))
    .map((line) => line.deliveryUrl.trim())
    .filter(Boolean);
  manualLinks.value = selectedLinks.join('\n');
  promotionDrafts.value = [];
});

watch(manualLinks, () => {
  if (promotionDrafts.value.length > 0) promotionDrafts.value = [];
});

onMounted(() => {
  void loadProjectOptions();
  void loadDomainOptions();
  void loadCountryOptions();
});

onActivated(() => {
  if (selectedProjectId.value) {
    void refreshOccupiedAgencyLineIds(selectedProjectId.value);
  }
});
</script>

<template>
  <div
    v-if="submitting"
    class="fixed inset-0 z-[1000] grid place-items-center bg-black/45 backdrop-blur-[2px]"
  >
    <div
      class="bg-background flex w-[calc(100%-2rem)] max-w-[520px] flex-col items-center rounded-xl border px-10 py-9 text-center shadow-2xl"
    >
      <Spin />
      <div class="text-foreground mt-5 text-base font-medium">
        {{ submittingText }}
      </div>
      <div class="text-muted-foreground mt-2 text-sm">
        请勿关闭或刷新当前页面
      </div>
    </div>
  </div>

  <Page class="bg-muted/40">
    <div class="mx-auto w-full max-w-[1120px] space-y-4 pb-24">
      <header class="flex flex-wrap items-center gap-3 py-1">
        <Button
          aria-label="返回斗篷管理"
          shape="circle"
          @click="router.push('/workbench/cloaks')"
        >
          <template #icon><IconifyIcon icon="lucide:arrow-left" /></template>
        </Button>
        <div>
          <h1 class="text-foreground m-0 text-xl font-semibold">
            批量创建斗篷
          </h1>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            按项目代理线的投放链接批量创建斗篷并保存到管理列表。
          </p>
        </div>
      </header>

      <Card :bordered="true">
        <div class="mb-4 flex items-start gap-3">
          <span
            class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
            >1</span
          >
          <div>
            <h2 class="text-foreground m-0 text-base font-semibold">
              选择项目
            </h2>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              项目来自业务中心的项目管理；选择后可勾选项目关联代理线中的投放链接。
            </p>
          </div>
        </div>
        <Spin :spinning="loadingProjects || loadingAgencyLines">
          <Select
            v-model:value="selectedProjectId"
            allow-clear
            class="w-full"
            :filter-option="false"
            :loading="loadingProjects"
            :options="projectSelectOptions"
            placeholder="输入项目名称或编码搜索"
            show-search
            @change="handleProjectChange"
            @search="handleProjectSearch"
          />
          <div v-if="selectedProjectId" class="mt-4 border-t pt-4">
            <div class="mb-3">
              <h3 class="text-foreground m-0 text-sm font-semibold">
                项目投放链接
              </h3>
              <p class="text-muted-foreground mb-0 mt-1 text-xs leading-5">
                勾选后会自动生成下方投放链接清单；已存在斗篷管理记录的代理线需先删除后才能重新创建。
              </p>
            </div>
            <CheckboxGroup
              v-model:value="selectedAgencyLineIds"
              class="block w-full"
            >
              <div class="overflow-hidden rounded-lg border">
                <ShadcnDataTable
                  :columns="agencyLineColumns"
                  :data="agencyLineRows"
                  empty-text="该项目暂未关联配置了投放链接的代理线。"
                  :paginate="false"
                  row-key="id"
                >
                  <template #cell-select="{ record }">
                    <Tooltip
                      v-if="occupiedAgencyLineIds.has(record.id)"
                      title="该代理线已存在斗篷管理记录，请先到斗篷管理中删除"
                    >
                      <span class="inline-flex cursor-not-allowed">
                        <Checkbox
                          :aria-label="`代理线 ${record.name} 已存在斗篷记录`"
                          disabled
                          :value="record.id"
                        />
                      </span>
                    </Tooltip>
                    <Checkbox
                      v-else
                      :aria-label="`选择代理线 ${record.name}`"
                      :disabled="!record.deliveryUrl.trim()"
                      :value="record.id"
                    />
                  </template>
                  <template #cell-name="{ record }">
                    <div class="flex items-center gap-2">
                      <span>{{ record.name }}</span>
                      <Tag
                        v-if="occupiedAgencyLineIds.has(record.id)"
                        color="default"
                      >
                        已创建
                      </Tag>
                    </div>
                  </template>
                  <template #cell-platform="{ record }">
                    <Tag>{{ record.platform }}</Tag>
                  </template>
                  <template #cell-deliveryUrl="{ record }">
                    <span
                      :class="
                        record.deliveryUrl
                          ? 'text-foreground'
                          : 'text-muted-foreground'
                      "
                      class="block max-w-[420px] break-all"
                    >
                      {{ record.deliveryUrl || '该代理线尚未配置投放链接' }}
                    </span>
                  </template>
                </ShadcnDataTable>
              </div>
            </CheckboxGroup>
          </div>
        </Spin>
      </Card>

      <Card :bordered="true">
        <div class="mb-4 flex items-start gap-3">
          <span
            class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
            >2</span
          >
          <div>
            <h2 class="text-foreground m-0 text-base font-semibold">
              投放链接清单
            </h2>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              链接只来自上一步勾选的项目代理线，不允许手动修改或追加。
            </p>
          </div>
        </div>
        <label>
          <span class="text-foreground mb-2 block text-sm">投放链接列表</span>
          <Input.TextArea
            v-model:value="manualLinks"
            :rows="6"
            placeholder="请先在上方勾选代理线"
            readonly
          />
        </label>
        <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
          <span
            :class="isOverLimit ? 'text-destructive' : 'text-muted-foreground'"
            class="text-sm"
          >
            当前 {{ normalizedManualLinks.length }} 条{{
              isOverLimit ? '，已超过上限' : ''
            }}
          </span>
          <Button
            :disabled="normalizedManualLinks.length === 0 || isOverLimit"
            type="primary"
            @click="updatePromotionDrafts"
          >
            更新创建清单
          </Button>
        </div>
      </Card>

      <Card :bordered="true">
        <div class="mb-4 flex items-start gap-3">
          <div class="flex items-start gap-3">
            <span
              class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
              >3</span
            >
            <div>
              <h2 class="text-foreground m-0 text-base font-semibold">
                推广链接配置
              </h2>
              <p class="text-muted-foreground mb-0 mt-1 text-sm">
                每条投放链接对应一条推广链接；命名和域名默认均为空。
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button
              :disabled="promotionDrafts.length === 0"
              @click="autoNameDrafts"
              >自动命名</Button
            >
            <Tag color="blue">{{ promotionDrafts.length }} 条记录</Tag>
          </div>
        </div>

        <Alert
          v-if="promotionDrafts.length === 0"
          message="填写链接后点击“更新创建清单”，这里会按行数生成推广链接记录。"
          show-icon
          type="info"
        />
        <div v-else class="space-y-3">
          <div
            v-for="(draft, index) in promotionDrafts"
            :key="draft.id"
            class="grid min-w-0 grid-cols-[28px_56px_28px_72px_minmax(150px,0.8fr)_minmax(220px,1.2fr)] items-center gap-2"
          >
            <span
              class="bg-muted text-muted-foreground grid size-7 place-items-center rounded-md text-xs font-medium"
            >
              {{ index + 1 }}
            </span>
            <Tooltip trigger="hover">
              <template #title>
                <span class="break-all">{{ draft.sourceUrl }}</span>
              </template>
              <Button class="!p-0" type="link"> 落地页 </Button>
            </Tooltip>
            <IconifyIcon
              aria-hidden="true"
              class="text-muted-foreground justify-self-center"
              icon="lucide:arrow-right"
            />
            <span
              class="text-muted-foreground bg-muted/40 rounded-md border px-3 py-2 text-sm"
              >https://</span
            >
            <Input v-model:value="draft.name" placeholder="输入命名" />
            <Select
              v-model:value="draft.domainId"
              class="w-full"
              :loading="loadingDomains"
              :options="domainSelectOptions"
              placeholder="请选择域名池中的域名"
            />
          </div>
        </div>
      </Card>

      <Card :bordered="true">
        <div class="mb-4 flex items-start gap-3">
          <span
            class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
            >4</span
          >
          <div>
            <h2 class="text-foreground m-0 text-base font-semibold">
              审核链接（A面链接）配置
            </h2>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              为本批次填写审核人员访问的链接，完成后才能提交创建。
            </p>
          </div>
        </div>
        <label class="block max-w-[720px]">
          <span class="text-foreground mb-2 block text-sm"> 审核链接 </span>
          <Input
            v-model:value="reviewUrl"
            placeholder="https://review.example.com/preview"
            required
          />
          <span class="text-muted-foreground mt-2 block text-xs">
            用于审核或验收，不会替换已填写的真实链接；此项必填。
          </span>
        </label>
      </Card>

      <Card :bordered="true">
        <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div class="flex items-start gap-3">
            <span
              class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
              >5</span
            >
            <div>
              <h2 class="text-foreground m-0 text-base font-semibold">
                批量斗篷规则
              </h2>
              <p class="text-muted-foreground mb-0 mt-1 text-sm">
                斗篷模式、地区和拦截规则统一应用到当前清单。
              </p>
            </div>
          </div>
        </div>
        <div class="grid gap-6 lg:grid-cols-2">
          <fieldset>
            <legend class="text-foreground mb-3 text-sm">
              开关 / 斗篷模式
            </legend>
            <RadioGroup v-model:value="mode">
              <Radio value="off">全关</Radio>
              <Radio value="all">全开</Radio>
              <Radio value="cloak">斗篷</Radio>
            </RadioGroup>
          </fieldset>
          <label>
            <span class="text-foreground mb-2 block text-sm">投放地区</span>
            <Select
              v-model:value="region"
              allow-clear
              class="w-full"
              :loading="loadingCountries"
              :options="countryOptions"
              placeholder="请选择投放地区"
            />
          </label>
        </div>
        <div class="mt-5 flex flex-wrap gap-x-8 gap-y-3">
          <label class="flex items-center gap-2 text-sm"
            ><Switch v-model:checked="blockedLanguage" />禁止空语言</label
          >
          <label class="flex items-center gap-2 text-sm"
            ><Switch v-model:checked="blockedPc" />禁止 PC</label
          >
          <label class="flex items-center gap-2 text-sm"
            ><Switch v-model:checked="blockedProxy" />禁止代理</label
          >
        </div>
      </Card>

      <Card :bordered="true">
        <div class="mb-4 flex items-start gap-3">
          <span
            class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-md font-semibold"
            >6</span
          >
          <div>
            <h2 class="text-foreground m-0 text-base font-semibold">
              其他设置
            </h2>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              关联项目已移除；关联表格当前仅展示设置，不产生实际效果。
            </p>
          </div>
        </div>
        <div
          class="flex items-center justify-between rounded-lg border px-4 py-3"
        >
          <div>
            <div class="text-foreground text-sm font-medium">关联到表格</div>
            <div class="text-muted-foreground mt-1 text-xs">
              开启后，斗篷创建成功将继续回写项目配置的代理线 Google Sheet。
            </div>
          </div>
          <Switch v-model:checked="linkedTable" />
        </div>
      </Card>
    </div>

    <div
      class="bg-background/95 fixed inset-x-0 bottom-0 z-30 border-t backdrop-blur"
    >
      <div
        class="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-3 px-4 py-3"
      >
        <span class="text-muted-foreground text-sm"
          >创建项 {{ promotionDrafts.length }} 条，已完成
          {{ completedDraftCount }} 条</span
        >
        <div class="flex gap-2">
          <Button @click="router.push('/workbench/cloaks')">取消</Button>
          <Button
            :disabled="promotionDrafts.length === 0 || !reviewUrl.trim()"
            :loading="submitting"
            type="primary"
            @click="submitBatch"
            >提交</Button
          >
        </div>
      </div>
    </div>
  </Page>
</template>
