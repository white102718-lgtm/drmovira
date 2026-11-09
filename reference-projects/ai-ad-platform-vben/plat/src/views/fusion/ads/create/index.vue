<script lang="ts" setup>
import type {
  AdDraftPayload,
  PlatformCapability,
  PlatformCode,
  PreflightResult,
} from '#/api';
import type { SelectableAdAccount } from '#/domain/ad-account-selection';
import type { AgencyLineOption } from '#/domain/agency-line';
import type { SelectableMaterial } from '#/domain/material';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import { useStorage } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  DescriptionsItem,
  Divider,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  Result,
  Row,
  Select,
  Steps,
  Tag,
} from 'ant-design-vue';

import { getPlatformCapabilitiesApi, isFusionDemoMode } from '#/api';
import { adAccountSelectionService } from '#/domain/ad-account-selection';
import { adPublishingService } from '#/domain/ad-publishing';
import {
  agencyLineService,
  getAgencyLineAdCreationIssue,
  listAgencyLinesForAdCreation,
} from '#/domain/agency-line';
import {
  DemoMaterialSelectionAdapter,
  HttpMaterialSelectionAdapter,
  MaterialSelectionService,
} from '#/domain/material';
import { projectService } from '#/domain/project';
import {
  useGlobalTaskStore,
  useProjectContextStore,
  useWorkflowStore,
} from '#/store';

interface WizardDraft extends AdDraftPayload {
  adGroupName: string;
  bidStrategy: string;
  fractureMode: 'material' | 'version';
  headline: string;
  primaryText: string;
}

const router = useRouter();
const route = useRoute();
const projectStore = useProjectContextStore();
const taskStore = useGlobalTaskStore();
const userStore = useUserStore();
const workflowStore = useWorkflowStore();
const materialSelectionService = new MaterialSelectionService(
  isFusionDemoMode()
    ? new DemoMaterialSelectionAdapter({
        materials: () => workflowStore.materialVersions,
      })
    : new HttpMaterialSelectionAdapter(),
);
const currentStep = ref(0);
const publishing = ref(false);
const checking = ref(false);
const preflight = ref<null | PreflightResult>(null);
const capabilities = ref<PlatformCapability[]>([]);
const selectableAdAccounts = ref<SelectableAdAccount[]>([]);
const accountLoading = ref(false);
const accountContextMessage = ref('');
const agencyLineOptions = ref<
  Array<AgencyLineOption & { label: string; value: string }>
>([]);
const selectedProjectAgencyLineIds = ref<string[]>([]);
const selectableMaterials = ref<SelectableMaterial[]>([]);
const materialLoading = ref(false);
const materialContextMessage = ref('');
const unverifiedMaterialIds = ref<string[]>([]);
const validationMessage = ref('');
const publishResult = ref<{ jobId: string; platform: PlatformCode }>();
const publishResultOpen = ref(false);

const draft = useStorage<WizardDraft>(
  'fusion:unified-ad-draft',
  {
    adAccountId: '',
    adAccountInventoryId: '',
    agencyLineId: '',
    adGroupName: '',
    bidStrategy: 'lowest_cost',
    budget: 100,
    campaignName: '',
    conversionTargetId: '',
    creativeIdentityId: '',
    deliveryLineId: '',
    destinationUrl: '',
    fractureMode: 'version',
    headline: '',
    materialIds: [],
    objective: '',
    platform: 'facebook',
    primaryText: '',
    projectId: '',
    scheduleStart: '',
    targeting: { ageMax: 55, ageMin: 18, countries: ['US'], languages: ['en'] },
  },
  localStorage,
  { mergeDefaults: true },
);

const platformMeta: Record<
  PlatformCode,
  { color: string; description: string; icon: string; label: string }
> = {
  facebook: {
    color: '#1877f2',
    description: '支持 Page、Pixel 和动态创意',
    icon: 'logos:facebook',
    label: 'Facebook',
  },
  google: {
    color: '#4285f4',
    description: '支持转化操作和素材资源组',
    icon: 'logos:google-icon',
    label: 'Google',
  },
  tiktok: {
    color: '#111827',
    description: '支持身份、Pixel 与 Spark 素材',
    icon: 'logos:tiktok-icon',
    label: 'TikTok',
  },
};

const stepItems = [
  { description: '项目、平台与账户', title: '业务' },
  { description: '目标、预算与排期', title: '系列' },
  { description: '定向、出价与转化', title: '广告组' },
  { description: '素材、文案与落地页', title: '创意' },
  { description: '统一校验后异步发布', title: '发布' },
];

const currentCapability = computed(() =>
  capabilities.value.find((item) => item.platform === draft.value.platform),
);
const selectedAgencyLine = computed(() =>
  agencyLineOptions.value.find((line) => line.id === draft.value.agencyLineId),
);
const selectedAdAccount = computed(() =>
  selectableAdAccounts.value.find(
    (account) => account.adAccountId === draft.value.adAccountId,
  ),
);
const selectableAgencyLineOptions = computed(() =>
  listAgencyLinesForAdCreation(agencyLineOptions.value, {
    agencyLineIds: selectedProjectAgencyLineIds.value,
    platform: draft.value.platform,
  }),
);
const resourceOptions = computed(() => ({
  adAccounts: selectableAdAccounts.value.map((account) => ({
    label: `${account.name} · ${account.adAccountId} · ${account.currency ?? '-'} ${account.balance ?? 0}`,
    value: account.adAccountId,
  })),
  conversions:
    selectedAdAccount.value?.pixels.map((pixel) => ({
      label: `${pixel.name} · ${pixel.id}`,
      value: pixel.id,
    })) ?? [],
  identities:
    selectedAdAccount.value?.pages.map((page) => ({
      label: `${page.name} · ${page.id}`,
      value: page.id,
    })) ?? [],
}));

function platformNeedsIdentity(platform: PlatformCode) {
  return platform === 'facebook' || platform === 'tiktok';
}

let accountRequestToken = 0;
let materialRequestToken = 0;

function readCurrentRoleCodes() {
  const roles = userStore.userInfo?.roles;
  if (!Array.isArray(roles)) return [];
  return roles
    .map((role) =>
      typeof role === 'string'
        ? role
        : ((role as { code?: string; name?: string; roleCode?: string }).code ??
          (role as { roleCode?: string }).roleCode ??
          (role as { name?: string }).name ??
          ''),
    )
    .map((role) => role.toLowerCase());
}

function hasAllAccountScope() {
  return readCurrentRoleCodes().some((role) =>
    ['admin', 'super', 'super_admin', '管理员'].includes(role),
  );
}

function getAccountScopeUserId() {
  if (hasAllAccountScope()) return undefined;
  const info = userStore.userInfo as
    | null
    | undefined
    | { _id?: string; userId?: string };
  return info?.userId || info?._id || '';
}

const agencyLineIssueMessages = {
  disabled: '当前代理线已停用，不能创建广告',
  'missing-pixel': '当前代理线缺少像素名称，不能创建广告',
  'not-bound': '当前代理线未绑定所选项目',
  'platform-mismatch': '当前代理线与所选投放平台不匹配',
} as const;

async function loadSelectableAdAccounts() {
  const requestToken = ++accountRequestToken;
  const projectId = draft.value.projectId;
  const platform = draft.value.platform;
  const agencyLineId = draft.value.agencyLineId;
  if (!projectId) {
    selectedProjectAgencyLineIds.value = [];
    selectableAdAccounts.value = [];
    draft.value.adAccountId = '';
    draft.value.adAccountInventoryId = '';
    return;
  }

  accountLoading.value = true;
  accountContextMessage.value = '';
  try {
    const project = await projectService.get(projectId);
    if (requestToken !== accountRequestToken) return;
    selectedProjectAgencyLineIds.value = [...(project.agencyLineIds ?? [])];

    if (!platform || !agencyLineId) {
      selectableAdAccounts.value = [];
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      return;
    }

    const belongsToProject = project.agencyLineIds?.includes(agencyLineId);
    const line = agencyLineOptions.value.find(
      (option) => option.value === agencyLineId,
    );
    if (!line) {
      selectableAdAccounts.value = [];
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      accountContextMessage.value = '请先选择当前项目与平台的代理线';
      return;
    }
    const lineIssue = getAgencyLineAdCreationIssue(line, {
      agencyLineIds: project.agencyLineIds ?? [],
      platform,
    });
    if (!belongsToProject || lineIssue) {
      selectableAdAccounts.value = [];
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      accountContextMessage.value = lineIssue
        ? agencyLineIssueMessages[lineIssue]
        : '当前代理线未绑定所选项目';
      return;
    }

    const scopeUserId = getAccountScopeUserId();
    if (!hasAllAccountScope() && !scopeUserId) {
      selectableAdAccounts.value = [];
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      accountContextMessage.value =
        '当前用户缺少稳定用户 ID，无法校验广告账户权限';
      return;
    }

    const result = await adAccountSelectionService.list({
      agencyLineId,
      page: 1,
      pageSize: 100,
      platform,
      projectId,
      userId: scopeUserId || undefined,
    });
    if (requestToken !== accountRequestToken) return;
    selectableAdAccounts.value = result.items;

    const restoredAccount = result.items.find(
      (account) => account.adAccountId === draft.value.adAccountId,
    );
    if (restoredAccount) {
      draft.value.adAccountInventoryId = restoredAccount.id;
    }

    if (!draft.value.objective && line.objective) {
      draft.value.objective = line.objective;
    }

    if (
      draft.value.adAccountId &&
      !result.items.some(
        (account) => account.adAccountId === draft.value.adAccountId,
      )
    ) {
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      accountContextMessage.value = '旧草稿账户在当前上下文不可用，请重新选择';
      draft.value.conversionTargetId = '';
      draft.value.creativeIdentityId = '';
    }
  } catch (error) {
    if (requestToken !== accountRequestToken) return;
    selectedProjectAgencyLineIds.value = [];
    selectableAdAccounts.value = [];
    draft.value.adAccountId = '';
    draft.value.adAccountInventoryId = '';
    accountContextMessage.value =
      error instanceof Error ? error.message : '加载可用账户失败';
  } finally {
    if (requestToken === accountRequestToken) accountLoading.value = false;
  }
}

async function loadSelectableMaterials() {
  const requestToken = ++materialRequestToken;
  const projectId = draft.value.projectId;
  if (!projectId) {
    selectableMaterials.value = [];
    unverifiedMaterialIds.value = [...new Set(draft.value.materialIds)];
    materialContextMessage.value =
      draft.value.materialIds.length > 0
        ? '旧草稿素材缺少项目上下文，需选择项目后重新校验'
        : '';
    return;
  }

  materialLoading.value = true;
  materialContextMessage.value = '';
  try {
    const result = await materialSelectionService.listSelectable({
      page: 1,
      pageSize: 100,
      projectId,
    });
    if (requestToken !== materialRequestToken) return;
    selectableMaterials.value = [...result.items];
    const selectableIds = new Set(result.items.map((item) => item.id));
    unverifiedMaterialIds.value = [
      ...new Set(
        draft.value.materialIds.filter((id) => !selectableIds.has(id)),
      ),
    ];
    if (unverifiedMaterialIds.value.length > 0) {
      materialContextMessage.value =
        '草稿中存在当前项目不可用的素材，已保留显示但必须移除或重新选择后才能发布';
    } else if (result.items.length > 0) {
      materialContextMessage.value = '';
    } else {
      materialContextMessage.value =
        '当前项目没有已审核素材，请先在素材中心完成审核';
    }
  } catch (error) {
    if (requestToken !== materialRequestToken) return;
    selectableMaterials.value = [];
    unverifiedMaterialIds.value = [...new Set(draft.value.materialIds)];
    materialContextMessage.value =
      error instanceof Error ? error.message : '加载可选素材失败，请稍后重试';
  } finally {
    if (requestToken === materialRequestToken) materialLoading.value = false;
  }
}

const materialOptions = computed<SelectableMaterial[]>(() => {
  const knownIds = new Set(selectableMaterials.value.map((item) => item.id));
  const legacyDrafts = unverifiedMaterialIds.value
    .filter((id) => !knownIds.has(id))
    .map((id) => ({
      approvalStatus: 'unknown' as const,
      id,
      name: `旧草稿素材 · ${id}`,
      projectId: draft.value.projectId,
      ratio: '待重新校验',
      source: 'legacy-draft' as const,
      type: '素材版本',
    }));
  return [...selectableMaterials.value, ...legacyDrafts];
});

const incomingMaterialVersion = computed(() =>
  typeof route.query.materialVersion === 'string'
    ? route.query.materialVersion
    : '',
);

function selectPlatform(platform: PlatformCode) {
  draft.value.platform = platform;
  draft.value.agencyLineId = '';
  draft.value.adAccountId = '';
  draft.value.adAccountInventoryId = '';
  draft.value.conversionTargetId = '';
  draft.value.creativeIdentityId = '';
  draft.value.objective = '';
  preflight.value = null;
}

function selectProject(projectId: string) {
  projectStore.selectProject(projectId);
  draft.value.deliveryLineId = '';
  draft.value.agencyLineId = '';
  draft.value.adAccountId = '';
  draft.value.adAccountInventoryId = '';
  preflight.value = null;
}

function selectAdAccount(adAccountId: string) {
  const account = selectableAdAccounts.value.find(
    (candidate) => candidate.adAccountId === adAccountId,
  );
  draft.value.conversionTargetId = account?.pixels[0]?.id ?? '';
  draft.value.creativeIdentityId = account?.pages[0]?.id ?? '';
  draft.value.adAccountInventoryId = account?.id ?? '';
  preflight.value = null;
}

watch(
  () =>
    [
      draft.value.projectId,
      draft.value.platform,
      draft.value.agencyLineId,
    ] as const,
  () => void loadSelectableAdAccounts(),
);

watch(
  () => draft.value.projectId,
  () => void loadSelectableMaterials(),
);

watch(
  () => draft.value.materialIds,
  (materialIds) => {
    unverifiedMaterialIds.value = unverifiedMaterialIds.value.filter((id) =>
      materialIds.includes(id),
    );
  },
  { deep: true },
);

function validationForStep(step: number) {
  const value = draft.value;
  if (step === 0) {
    const missing = [
      !value.projectId && '项目',
      !value.agencyLineId && '代理线',
      !value.adAccountId && '广告账户',
    ].filter(Boolean);
    return missing.length > 0 ? `请补充：${missing.join('、')}` : '';
  }
  if (step === 1) {
    const missing = [
      !value.campaignName && '广告系列名称',
      !value.objective && '营销目标',
      !(value.budget > 0) && '有效预算',
      !value.scheduleStart && '开始时间',
    ].filter(Boolean);
    return missing.length > 0 ? `请补充：${missing.join('、')}` : '';
  }
  if (step === 2) {
    const missing = [
      !value.adGroupName && '广告组名称',
      !value.conversionTargetId && '转化目标',
      platformNeedsIdentity(value.platform) &&
        !value.creativeIdentityId &&
        '创意身份',
      value.targeting.countries.length === 0 && '国家/地区',
    ].filter(Boolean);
    return missing.length > 0 ? `请补充：${missing.join('、')}` : '';
  }
  if (step === 3) {
    const missing = [
      value.materialIds.length === 0 && '至少一个已审核素材版本',
      !value.headline && '标题',
      !/^https?:\/\//.test(value.destinationUrl) && '有效的 http(s) 落地页',
    ].filter(Boolean);
    return missing.length > 0 ? `请补充：${missing.join('、')}` : '';
  }
  return '';
}

function requiredForStep(step: number) {
  const value = draft.value;
  if (step === 0)
    return Boolean(
      value.projectId &&
        value.platform &&
        value.agencyLineId &&
        value.adAccountId,
    );
  if (step === 1)
    return Boolean(
      value.campaignName &&
        value.objective &&
        value.budget > 0 &&
        value.scheduleStart,
    );
  if (step === 2)
    return Boolean(
      value.adGroupName &&
        value.conversionTargetId &&
        (!platformNeedsIdentity(value.platform) || value.creativeIdentityId) &&
        value.targeting.countries.length > 0,
    );
  if (step === 3)
    return Boolean(
      value.materialIds.length > 0 &&
        value.headline &&
        /^https?:\/\//.test(value.destinationUrl),
    );
  return true;
}

async function nextStep() {
  validationMessage.value = validationForStep(currentStep.value);
  if (!requiredForStep(currentStep.value)) {
    return;
  }
  if (currentStep.value === 3) {
    await runPreflight();
  }
  currentStep.value = Math.min(4, currentStep.value + 1);
  validationMessage.value = '';
}

async function runPreflight() {
  checking.value = true;
  try {
    const apiResult = await adPublishingService.preflight(draft.value);
    let accountEligible = false;
    let accountEligibilityMessage = '广告账户仍符合项目、平台代理线和用户权限';
    let accountAssetsEligible = false;
    let accountAssetsEligibilityMessage = '转化目标与创意身份仍属于所选账户';
    let agencyLineEligible = false;
    let agencyLineEligibilityMessage = '代理线仍已绑定、启用且平台与像素有效';
    const scopeUserId = getAccountScopeUserId();
    try {
      const agencyLineId = draft.value.agencyLineId;
      if (!draft.value.projectId || !agencyLineId) {
        throw new Error('项目或代理线未选择');
      }
      const [currentProject, currentLine] = await Promise.all([
        projectService.get(draft.value.projectId),
        agencyLineService.get(agencyLineId),
      ]);
      const lineIssue = getAgencyLineAdCreationIssue(currentLine, {
        agencyLineIds: currentProject.agencyLineIds ?? [],
        platform: draft.value.platform,
      });
      agencyLineEligible = !lineIssue;
      if (lineIssue) {
        agencyLineEligibilityMessage = agencyLineIssueMessages[lineIssue];
      }

      if (
        agencyLineEligible &&
        draft.value.adAccountId &&
        (hasAllAccountScope() || scopeUserId)
      ) {
        const verifiedAccount = await adAccountSelectionService.findSelectable(
          {
            agencyLineId,
            platform: draft.value.platform,
            projectId: draft.value.projectId,
            userId: scopeUserId || undefined,
          },
          draft.value.adAccountId,
        );
        accountEligible = Boolean(verifiedAccount);
        if (verifiedAccount) {
          accountEligible =
            !draft.value.adAccountInventoryId ||
            draft.value.adAccountInventoryId === verifiedAccount.id;
          const ownsConversion = verifiedAccount.pixels.some(
            (pixel) => pixel.id === draft.value.conversionTargetId,
          );
          const ownsIdentity =
            !platformNeedsIdentity(verifiedAccount.platform) ||
            verifiedAccount.pages.some(
              (page) => page.id === draft.value.creativeIdentityId,
            );
          accountAssetsEligible =
            accountEligible && ownsConversion && ownsIdentity;
        }
      }
      if (!accountEligible) {
        accountEligibilityMessage =
          '广告账户已失效、越权或不再属于当前项目与代理线';
      }
      if (!accountAssetsEligible) {
        accountAssetsEligibilityMessage =
          '转化目标或创意身份已失效，或不属于所选广告账户';
      }
    } catch {
      agencyLineEligibilityMessage = '代理线资格复核失败，请稍后重试';
      accountEligibilityMessage = '广告账户资格复核失败，请稍后重试';
      accountAssetsEligibilityMessage = '账户资产资格复核失败，请稍后重试';
    }

    let materialsEligible = false;
    let materialsEligibilityMessage = '所选素材包含未审核、已失效或未知版本';
    try {
      if (!draft.value.projectId || draft.value.materialIds.length === 0) {
        throw new Error('未选择素材或项目');
      }
      const verified = await Promise.all(
        draft.value.materialIds.map((materialVersionId) =>
          materialSelectionService.findSelectable(
            { projectId: draft.value.projectId },
            materialVersionId,
          ),
        ),
      );
      materialsEligible = verified.every(Boolean);
      if (materialsEligible) {
        materialsEligibilityMessage = '所选素材版本仍已审核且可用于当前发布';
      }
    } catch {
      materialsEligibilityMessage = '素材资格复核失败，请稍后重试';
    }

    const additionalChecks = [
      {
        code: 'agency-line-eligibility',
        message: agencyLineEligibilityMessage,
        passed: agencyLineEligible,
        severity: 'error' as const,
      },
      {
        code: 'account-eligibility',
        message: accountEligibilityMessage,
        passed: accountEligible,
        severity: 'error' as const,
      },
      {
        code: 'account-assets-eligibility',
        message: accountAssetsEligibilityMessage,
        passed: accountAssetsEligible,
        severity: 'error' as const,
      },
      {
        code: 'material-eligibility',
        message: materialsEligibilityMessage,
        passed: materialsEligible,
        severity: 'error' as const,
      },
    ];
    const merged = adPublishingService.withChecks(
      {
        ...apiResult,
        checks: apiResult.checks.filter(
          (check) =>
            !['account-eligibility', 'agency-line-eligibility'].includes(
              check.code,
            ),
        ),
      },
      additionalChecks,
    );
    preflight.value = {
      ...merged,
      passed: apiResult.passed && merged.passed,
    };
  } finally {
    checking.value = false;
  }
}

async function publish() {
  await runPreflight();
  if (!preflight.value?.passed) {
    message.error('发布前检查未通过，请修复错误项');
    return;
  }
  publishing.value = true;
  try {
    const result = await adPublishingService.publish(
      draft.value,
      preflight.value,
    );
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    taskStore.addTask({
      createdAt: now,
      id: result.jobId,
      platform: draft.value.platform,
      progress: 0,
      projectId: draft.value.projectId,
      refundable: false,
      status: result.status,
      title: `${platformMeta[draft.value.platform].label} · ${draft.value.campaignName}`,
      updatedAt: now,
    });
    workflowStore.registerPublishedAd({
      campaignName: draft.value.campaignName,
      jobId: result.jobId,
      materialVersionIds: draft.value.materialIds,
      platform: draft.value.platform,
      projectId: draft.value.projectId,
    });
    publishResult.value = {
      jobId: result.jobId,
      platform: draft.value.platform,
    };
    publishResultOpen.value = true;
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '广告发布失败，请稍后重试',
    );
  } finally {
    publishing.value = false;
  }
}

onMounted(async () => {
  await projectStore.loadProjectOptions();
  const lines = await agencyLineService.listOptions({});
  agencyLineOptions.value = lines.map((line) => ({
    ...line,
    label: line.name,
    value: line.id,
  }));
  capabilities.value = await getPlatformCapabilitiesApi();
  if (!draft.value.projectId)
    draft.value.projectId = projectStore.selectedProjectId;
  if (!draft.value.deliveryLineId)
    draft.value.deliveryLineId = projectStore.selectedDeliveryLineId;
  if (draft.value.projectId) {
    try {
      const currentProject = await projectService.get(draft.value.projectId);
      selectedProjectAgencyLineIds.value = [
        ...(currentProject.agencyLineIds ?? []),
      ];
      if (
        !draft.value.agencyLineId ||
        !currentProject.agencyLineIds?.includes(draft.value.agencyLineId)
      ) {
        draft.value.agencyLineId =
          listAgencyLinesForAdCreation(agencyLineOptions.value, {
            agencyLineIds: currentProject.agencyLineIds ?? [],
            platform: draft.value.platform,
          })[0]?.id ?? '';
      }
    } catch {
      draft.value.projectId = '';
      draft.value.agencyLineId = '';
      draft.value.adAccountId = '';
      draft.value.adAccountInventoryId = '';
      selectedProjectAgencyLineIds.value = [];
      accountContextMessage.value = '旧草稿项目已不可用，请重新选择';
    }
  }
  await loadSelectableAdAccounts();
  if (incomingMaterialVersion.value) {
    const version = incomingMaterialVersion.value;
    if (!draft.value.materialIds.includes(version))
      draft.value.materialIds = [version, ...draft.value.materialIds];
  }
  await loadSelectableMaterials();
});
</script>

<template>
  <Page
    class="adpulse-section-page bg-muted/40"
    content-class="flex min-h-0 flex-col p-4"
  >
    <div class="w-full min-w-0">
      <section class="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="text-foreground m-0 text-xl font-semibold tracking-tight">
            创建多平台广告
          </h1>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            一个流程覆盖 Facebook、Google 与 TikTok，平台差异由配置驱动。
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button @click="router.push('/home')">退出向导</Button>
          <Button @click="message.success('草稿已自动保存到本机')">
            保存草稿
          </Button>
        </div>
      </section>

      <Card
        class="border-border bg-card mb-4"
        :body-style="{ padding: '16px' }"
      >
        <div class="ad-create-steps overflow-x-auto pb-1">
          <Steps
            :current="currentStep"
            :items="stepItems"
            :responsive="false"
            class="min-w-[460px]"
          />
        </div>
      </Card>

      <Alert
        class="mb-4"
        message="统一身份与权限由 Java 签发；首期保留现有 Python AI 服务和 Mpower 投放后端，投放域计划第二期迁移 Java。"
        type="info"
        show-icon
        closable
      />

      <Alert
        v-if="incomingMaterialVersion"
        class="mb-4"
        :message="`已从上一环节带入素材版本：${incomingMaterialVersion}`"
        description="素材已加入当前草稿，仍需在当前项目的已审核素材中复核通过后才可发布。"
        type="info"
        show-icon
      >
        <template #action>
          <Button @click="currentStep = 3">查看素材</Button>
        </template>
      </Alert>

      <Card class="border-border bg-card" :body-style="{ padding: '16px' }">
        <Alert
          v-if="validationMessage"
          class="mb-5"
          :message="validationMessage"
          type="error"
          show-icon
          closable
          @close="validationMessage = ''"
        />
        <section v-if="currentStep === 0">
          <h2 class="text-foreground m-0 text-lg font-semibold">
            选择项目、投放线和平台
          </h2>
          <p class="text-muted-foreground mb-5 mt-1 text-sm">
            广告账户、素材和归因结果全部绑定当前 Project。
          </p>
          <Row :gutter="[16, 16]">
            <Col :xs="24" :lg="12">
              <Form layout="vertical" class="ux-form-label-top">
                <FormItem label="项目" required>
                  <Select
                    v-model:value="draft.projectId"
                    :options="
                      projectStore.projectOptions.map((item) => ({
                        label: `${item.customerName} / ${item.name}`,
                        value: item.id,
                      }))
                    "
                    show-search
                    option-filter-prop="label"
                    @change="(value) => selectProject(String(value))"
                  />
                </FormItem>
                <FormItem label="投放线">
                  <Select
                    v-model:value="draft.deliveryLineId"
                    :options="
                      projectStore.deliveryLineOptions.map((item) => ({
                        label: item.name,
                        value: item.id,
                      }))
                    "
                    @change="
                      (value) =>
                        projectStore.selectDeliveryLine(String(value || ''))
                    "
                  />
                </FormItem>
                <FormItem label="代理线" required>
                  <Select
                    v-model:value="draft.agencyLineId"
                    :options="selectableAgencyLineOptions"
                    placeholder="选择当前项目的平台代理线"
                  />
                  <div
                    v-if="selectedAgencyLine"
                    class="text-muted-foreground mt-1 text-xs"
                  >
                    像素：{{ selectedAgencyLine.pixelName || '未配置' }}
                    <span v-if="selectedAgencyLine.pageId">
                      · 主页：{{ selectedAgencyLine.pageId }}
                    </span>
                  </div>
                </FormItem>
                <FormItem
                  :label="currentCapability?.adAccountLabel || '广告账户'"
                  required
                >
                  <Select
                    v-model:value="draft.adAccountId"
                    :options="resourceOptions.adAccounts"
                    :loading="accountLoading"
                    :not-found-content="
                      accountLoading
                        ? '加载中…'
                        : accountContextMessage || '暂无符合条件的账户'
                    "
                    placeholder="选择已授权且属于当前项目的账户"
                    @change="(value) => selectAdAccount(String(value || ''))"
                  />
                  <div
                    v-if="accountContextMessage"
                    class="text-muted-foreground mt-1 text-xs"
                  >
                    {{ accountContextMessage }}
                  </div>
                </FormItem>
              </Form>
            </Col>
            <Col :xs="24" :lg="12">
              <div class="text-foreground mb-2 text-sm font-medium">
                投放平台
              </div>
              <div class="space-y-3">
                <button
                  v-for="(meta, code) in platformMeta"
                  :key="code"
                  type="button"
                  class="flex w-full cursor-pointer items-center gap-4 rounded-lg border p-4 text-left transition-colors"
                  :class="
                    draft.platform === code
                      ? 'border-primary bg-accent'
                      : 'border-border bg-card hover:bg-accent'
                  "
                  @click="selectPlatform(code as PlatformCode)"
                >
                  <span
                    class="bg-muted text-muted-foreground flex h-10 w-10 items-center justify-center rounded-lg"
                  >
                    <IconifyIcon :icon="meta.icon" class="text-xl" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="text-foreground block text-sm font-semibold">{{
                      meta.label
                    }}</span>
                    <span class="text-muted-foreground mt-1 block text-xs">{{
                      meta.description
                    }}</span>
                  </span>
                  <IconifyIcon
                    v-if="draft.platform === code"
                    icon="lucide:circle-check-big"
                    class="text-primary text-xl"
                  />
                </button>
              </div>
            </Col>
          </Row>
        </section>

        <section v-else-if="currentStep === 1">
          <h2 class="text-foreground m-0 text-lg font-semibold">
            广告系列设置
          </h2>
          <p class="text-muted-foreground mb-5 mt-1 text-sm">
            统一字段在三平台复用，发布时转换为平台参数。
          </p>
          <Form layout="vertical" class="max-w-3xl">
            <FormItem label="广告系列名称" required
              ><Input
                v-model:value="draft.campaignName"
                placeholder="例如：Starfall_US_Purchase_202608"
            /></FormItem>
            <FormItem label="营销目标" required>
              <Select
                v-model:value="draft.objective"
                :options="
                  currentCapability?.supportedObjectives.map((item) => ({
                    label: item,
                    value: item,
                  }))
                "
              />
            </FormItem>
            <Row :gutter="16">
              <Col :xs="24" :md="12"
                ><FormItem label="每日预算" required
                  ><InputNumber
                    v-model:value="draft.budget"
                    :min="1"
                    :precision="2"
                    class="w-full"
                    addon-before="USD" /></FormItem
              ></Col>
              <Col :xs="24" :md="12"
                ><FormItem label="开始时间" required
                  ><Input
                    v-model:value="draft.scheduleStart"
                    type="datetime-local" /></FormItem
              ></Col>
            </Row>
            <FormItem label="结束时间"
              ><Input v-model:value="draft.scheduleEnd" type="datetime-local"
            /></FormItem>
          </Form>
        </section>

        <section v-else-if="currentStep === 2">
          <h2 class="text-foreground m-0 text-lg font-semibold">
            {{ currentCapability?.adGroupLabel || '广告组' }}设置
          </h2>
          <p class="text-muted-foreground mb-5 mt-1 text-sm">
            配置定向、转化目标、出价策略和平台创意身份。
          </p>
          <Form layout="vertical" class="max-w-4xl">
            <FormItem
              :label="`${currentCapability?.adGroupLabel || '广告组'}名称`"
              required
              ><Input v-model:value="draft.adGroupName"
            /></FormItem>
            <Row :gutter="16">
              <Col :xs="24" :md="12"
                ><FormItem :label="currentCapability?.conversionLabel" required
                  ><Select
                    v-model:value="draft.conversionTargetId"
                    :options="resourceOptions.conversions" /></FormItem
              ></Col>
              <Col :xs="24" :md="12"
                ><FormItem
                  :label="currentCapability?.creativeIdentityLabel"
                  required
                  ><Select
                    v-model:value="draft.creativeIdentityId"
                    :options="resourceOptions.identities" /></FormItem
              ></Col>
            </Row>
            <FormItem label="出价策略"
              ><Select
                v-model:value="draft.bidStrategy"
                :options="[
                  { label: '最低成本', value: 'lowest_cost' },
                  { label: '成本上限', value: 'cost_cap' },
                  { label: '目标 ROAS', value: 'target_roas' },
                ]"
            /></FormItem>
            <Divider orientation="left">受众定向</Divider>
            <Row :gutter="16">
              <Col :xs="24" :md="12"
                ><FormItem label="国家/地区" required
                  ><Select
                    v-model:value="draft.targeting.countries"
                    mode="multiple"
                    :options="[
                      { label: '美国', value: 'US' },
                      { label: '日本', value: 'JP' },
                      { label: '泰国', value: 'TH' },
                      { label: '印度尼西亚', value: 'ID' },
                    ]" /></FormItem
              ></Col>
              <Col :xs="12" :md="6"
                ><FormItem label="最小年龄"
                  ><InputNumber
                    v-model:value="draft.targeting.ageMin"
                    :min="13"
                    :max="65"
                    class="w-full" /></FormItem
              ></Col>
              <Col :xs="12" :md="6"
                ><FormItem label="最大年龄"
                  ><InputNumber
                    v-model:value="draft.targeting.ageMax"
                    :min="13"
                    :max="65"
                    class="w-full" /></FormItem
              ></Col>
            </Row>
          </Form>
        </section>

        <section v-else-if="currentStep === 3">
          <h2 class="text-foreground m-0 text-lg font-semibold">
            广告创意与素材
          </h2>
          <p class="text-muted-foreground mb-5 mt-1 text-sm">
            每个选中项都绑定 MaterialVersion
            ID，动态创意数据可回传到具体素材版本。
          </p>
          <Row :gutter="[16, 16]">
            <Col :xs="24" :xl="14">
              <div class="text-foreground mb-2 text-sm font-medium">
                选择已审核素材 <span class="text-red-500">*</span>
              </div>
              <Alert
                v-if="materialContextMessage"
                class="mb-3"
                :message="materialContextMessage"
                :type="unverifiedMaterialIds.length ? 'warning' : 'info'"
                show-icon
              />
              <Checkbox.Group
                v-model:value="draft.materialIds"
                class="grid w-full grid-cols-1 gap-3 md:grid-cols-2"
              >
                <label
                  v-for="item in materialOptions"
                  :key="item.id"
                  class="hover:bg-accent flex cursor-pointer gap-3 rounded-lg border p-4 transition-colors"
                  :class="
                    draft.materialIds.includes(item.id)
                      ? 'border-primary bg-accent'
                      : 'border-border bg-card'
                  "
                >
                  <Checkbox
                    :value="item.id"
                    :disabled="
                      materialLoading ||
                      (item.approvalStatus !== 'approved' &&
                        !draft.materialIds.includes(item.id))
                    "
                    class="mt-0.5"
                  />
                  <span class="min-w-0">
                    <span class="text-foreground block text-sm font-medium">{{
                      item.name
                    }}</span>
                    <span class="mt-2 flex gap-1"
                      ><Tag color="blue">{{ item.type }}</Tag
                      ><Tag>{{ item.ratio }}</Tag
                      ><Tag
                        :color="
                          item.approvalStatus === 'approved'
                            ? 'success'
                            : 'warning'
                        "
                        >{{
                          item.approvalStatus === 'approved'
                            ? '审核通过'
                            : '待重新校验'
                        }}</Tag
                      ></span
                    >
                    <span class="text-muted-foreground mt-2 block text-xs">{{
                      item.id
                    }}</span>
                  </span>
                </label>
              </Checkbox.Group>
              <Alert
                class="mt-4"
                message="平台回传表现数据时，使用广告创意与 MaterialVersion 的映射进行归因；动态创意也会保留每个素材元素的映射。"
                type="info"
                show-icon
              />
            </Col>
            <Col :xs="24" :xl="10">
              <Form layout="vertical">
                <FormItem label="主文案"
                  ><Input.TextArea v-model:value="draft.primaryText" :rows="4"
                /></FormItem>
                <FormItem label="标题" required
                  ><Input v-model:value="draft.headline"
                /></FormItem>
                <FormItem label="落地页" required
                  ><Input
                    v-model:value="draft.destinationUrl"
                    placeholder="https://"
                /></FormItem>
                <FormItem label="后续 AI 裂变的保存方式">
                  <Radio.Group v-model:value="draft.fractureMode">
                    <Radio value="version">作为当前素材的新版本</Radio>
                    <Radio value="material">创建新素材</Radio>
                  </Radio.Group>
                  <div class="text-muted-foreground mt-2 text-xs">
                    按用户选择决定 Material 与 MaterialVersion 的边界。
                  </div>
                </FormItem>
              </Form>
            </Col>
          </Row>
        </section>

        <section v-else>
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="text-foreground m-0 text-lg font-semibold">
                发布前检查
              </h2>
              <p class="text-muted-foreground mb-0 mt-1 text-sm">
                通过预检后，发布转为后台任务，不阻塞当前页面。
              </p>
            </div>
            <Button :loading="checking" @click="runPreflight">重新检查</Button>
          </div>
          <div class="my-5 space-y-2">
            <div
              v-for="check in preflight?.checks"
              :key="check.code"
              class="border-border flex items-center gap-3 rounded-lg border p-3"
            >
              <IconifyIcon
                :icon="
                  check.passed ? 'lucide:circle-check-big' : 'lucide:circle-x'
                "
                :class="check.passed ? 'text-green-600' : 'text-red-600'"
                class="text-lg"
              />
              <span class="text-foreground text-sm">{{ check.message }}</span>
              <Tag
                class="ml-auto"
                :color="
                  check.passed
                    ? 'success'
                    : check.severity === 'error'
                      ? 'error'
                      : 'warning'
                "
                >{{ check.passed ? '通过' : '需修复' }}</Tag
              >
            </div>
          </div>
          <Descriptions bordered :column="{ xs: 1, sm: 2 }">
            <DescriptionsItem label="项目">{{
              projectStore.projectOptions.find(
                (item) => item.id === draft.projectId,
              )?.name
            }}</DescriptionsItem>
            <DescriptionsItem label="平台"
              ><Tag color="blue">{{
                platformMeta[draft.platform].label
              }}</Tag></DescriptionsItem
            >
            <DescriptionsItem label="广告系列">{{
              draft.campaignName
            }}</DescriptionsItem>
            <DescriptionsItem label="营销目标">{{
              draft.objective
            }}</DescriptionsItem>
            <DescriptionsItem label="每日预算"
              >USD {{ draft.budget }}</DescriptionsItem
            >
            <DescriptionsItem label="素材版本"
              >{{ draft.materialIds.length }} 个</DescriptionsItem
            >
            <DescriptionsItem label="归因口径" :span="2"
              >后端接口统一定义
              CPP、CVR、ROAS、时区、币种和归因窗口；前端只展示正式口径。</DescriptionsItem
            >
          </Descriptions>
        </section>
      </Card>
    </div>

    <div
      class="border-border bg-card sticky bottom-0 z-10 mt-4 rounded-lg border px-4 py-3"
    >
      <div
        class="flex w-full min-w-0 flex-wrap items-center justify-between gap-3"
      >
        <div class="text-muted-foreground text-xs">
          草稿自动保存 · 当前步骤 {{ currentStep + 1 }}/5
        </div>
        <div class="ml-auto flex flex-wrap gap-2">
          <Button
            v-if="currentStep > 0"
            @click="
              currentStep--;
              validationMessage = '';
            "
            >上一步</Button
          >
          <Button
            v-if="currentStep < 4"
            type="primary"
            :loading="checking"
            @click="nextStep"
            >下一步</Button
          >
          <Button
            v-else
            type="primary"
            :loading="publishing"
            :disabled="!preflight?.passed"
            @click="publish"
            >确认并发布</Button
          >
        </div>
      </div>
    </div>

    <Modal
      v-model:open="publishResultOpen"
      :footer="null"
      :width="560"
      centered
    >
      <Result
        status="success"
        title="发布任务已创建"
        :sub-title="`${platformMeta[publishResult?.platform || draft.platform].label} 将在后台依次创建广告系列、广告组和广告；任务编号 ${publishResult?.jobId || ''}`"
      >
        <template #extra>
          <div class="flex flex-wrap justify-center gap-2">
            <Button
              @click="
                publishResultOpen = false;
                taskStore.openDrawer();
              "
              >查看任务进度</Button
            >
            <Button @click="router.push('/fusion/review-experiments')"
              >进入复盘与实验</Button
            >
            <Button type="primary" @click="publishResultOpen = false"
              >留在当前页</Button
            >
          </div>
        </template>
      </Result>
    </Modal>
  </Page>
</template>

<style scoped>
@media (max-width: 1199px) {
}
</style>
