/**
 * 广告数据转换函数
 * 将表单数据转换为API所需格式
 */

import type {
  AdvertiserItem,
  MaterialItem,
  RegionGroup,
  SelectedProduct,
  SeriesData,
  SeriesSettings,
} from '#/views/createAdvertisement/types';

import { convertBudgetToCents, mapObjective } from './mappings';

const ALL_PUBLISHER_PLATFORMS = [
  'facebook',
  'instagram',
  'audience_network',
  'messenger',
  'whatsapp',
  'threads',
] as const;

type PublisherPlatform = (typeof ALL_PUBLISHER_PLATFORMS)[number];

interface ChatQuestion {
  autoReply: string;
  question: string;
}

interface ChatToolData {
  greeting: string;
  greetingType: string;
  questions: ChatQuestion[];
  reengagementEnabled: boolean;
  reengagementText: string;
}

/**
 * 表单数据接口
 */
export interface FormData {
  adsPerGroup?: number;
  applicationId?: string;
  appStoreUrl?: string;
  chatToolData?: ChatToolData;
  conversionEvent?: string;
  conversionLocation?: string;
  isEngagement?: boolean;
  schedule_end_time?: string;
  schedule_start_time?: string;
  selectedTasksData: SelectedProduct[];
  seriesList: SeriesData[];
  step1Data: {
    adName: string;
    groupName: string;
    seriesName: string;
  };
  uploadedMaterials: MaterialItem[];
}

interface AccountInfo {
  account_id: string;
  account_name: string;
  page_id: string;
  page_name: string;
  person_id: string;
  person_name: string;
  pixel_id: string;
  pixel_name: string;
}

interface AccountGroup {
  account_ids: AccountInfo[];
  agent_line: string;
  country: string;
  game_platform: string;
  link_url: string;
}

/**
 * 提取广告账户信息列表 (包含账户ID、像素ID、主页ID)
 */
function normalizeActAccountId(account: string): string {
  if (!account) return '';
  return account.startsWith('act_') ? account : `act_${account}`;
}

function safeString(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

function findOptionName(
  options: any[] | undefined,
  selectedId: unknown,
): string {
  const sid = safeString(selectedId);
  if (!sid || !Array.isArray(options)) return '';
  const found = options.find((opt) => safeString(opt?.id) === sid);
  return safeString(found?.name);
}

/**
 * 转换 account_groups (每条任务线一个 AccountGroup，广告账户可多选)
 */
function transformAccountGroups(
  selectedTasks: SelectedProduct[],
  formData: FormData,
): AccountGroup[] {
  return selectedTasks.map((task) => {
    const accountMap = new Map<string, AccountInfo>();

    (task.advertisers || []).forEach((adv: AdvertiserItem) => {
      const accountId = normalizeActAccountId(adv.account);
      if (!accountId) return;

      const accountName = safeString(
        (adv as any).广告账户名称 || (adv as any).account_name || adv.name,
      );

      const selectedPixelId =
        (adv as any).selectedPixel || (adv as any).像素ID || '';
      const selectedPageId =
        (adv as any).selectedPublicPage || (adv as any).公共主页ID || '';

      const pixelId = safeString(selectedPixelId);
      const pageId = safeString(selectedPageId);

      const pixelName =
        findOptionName((adv as any).pixelOptions, selectedPixelId) ||
        safeString(
          (adv as any).pixel_name || (adv as any).像素名称 || adv.pixel,
        );
      const pageName =
        findOptionName((adv as any).publicPageOptions, selectedPageId) ||
        safeString(
          (adv as any).page_name || (adv as any).公共主页名称 || adv.publicPage,
        );

      // 提取个号
      const personId = safeString(adv.personId || '');
      const personName = safeString(adv.personAccountName || '');

      if (!accountMap.has(accountId)) {
        const info: AccountInfo = {
          account_id: accountId,
          account_name: accountName,
          page_id: pageId,
          page_name: pageName,
          pixel_id: pixelId,
          pixel_name: pixelName,
          person_id: personId,
          person_name: personName,
        };
        accountMap.set(accountId, info);
      }
    });

    return {
      game_platform: task.projectName,
      agent_line: task.taskName,
      link_url: formData.appStoreUrl || task.url,
      country: task.regionName || '',
      account_ids: [...accountMap.values()],
    };
  });
}

/**
 * 转换预算 (根据预算类型返回对应字段)
 * 返回 daily_budget 和 lifetime_budget，根据预算类型设置对应值，另一个设为 null
 */
function transformBudget(settings: SeriesSettings): any {
  const budgetInCents = convertBudgetToCents(settings.budget);

  if (settings.budgetType === '单日预算') {
    return {
      daily_budget: budgetInCents,
      lifetime_budget: null,
    };
  }
  return {
    daily_budget: null,
    lifetime_budget: budgetInCents,
  };
}

/**
 * 提取国家代码列表
 */
function extractCountries(regionGroup: RegionGroup): string[] {
  return regionGroup.country ? [regionGroup.country] : [];
}

function normalizeAgeRange(group: RegionGroup): [number, number] {
  const fallback: [number, number] = [18, 65];
  const rawMin = Number(group.ageStart);
  const rawMax = Number(group.ageRangeEnd);
  if (!Number.isFinite(rawMin) || !Number.isFinite(rawMax)) return fallback;
  const min = Math.min(rawMin, rawMax);
  const max = Math.max(rawMin, rawMax);
  return [min, max];
}

function isAllPublisherPlatformsSelected(selected: unknown): boolean {
  if (!Array.isArray(selected) || selected.length === 0) return false;
  const set = new Set(selected as PublisherPlatform[]);
  if (set.size !== ALL_PUBLISHER_PLATFORMS.length) return false;
  return ALL_PUBLISHER_PLATFORMS.every((p) => set.has(p));
}

/**
 * 从任务线数据中获取主页ID
 */
function getPageIdFromTask(formData: FormData, index: number): string {
  const taskIndex = Math.min(
    Math.max(index, 0),
    formData.selectedTasksData.length - 1,
  );
  const task = formData.selectedTasksData[taskIndex];
  if (!task?.advertisers?.length) return '';
  const adv = task.advertisers[0];
  return safeString(
    (adv as any).selectedPublicPage || (adv as any).公共主页ID || '',
  );
}

const MESSAGING_DESTINATION_SUBTYPES: Record<string, string> = {
  INSTAGRAM_DIRECT: 'INSTAGRAM_DIRECT',
  MESSENGER: 'MESSENGER_CHAT',
  WHATSAPP: 'WHATSAPP',
};

/**
 * 构建互动目标的 engagement_config，仅消息类目标需要
 */
function buildEngagementConfig(
  destinationType: string,
  pageId: string,
): any | undefined {
  const subtype = MESSAGING_DESTINATION_SUBTYPES[destinationType];
  if (!subtype) return undefined;
  return {
    channel: destinationType,
    page_id: pageId,
    subtype,
  };
}

/**
 * 构建互动目标的 page_welcome_message
 */
function buildPageWelcomeMessage(chatToolData: ChatToolData): any {
  const mediaType = chatToolData.greetingType === 'TEXT' ? 'text' : 'text';
  const iceBreakers = chatToolData.questions.map((q) => ({
    response: q.autoReply || null,
    title: q.question,
  }));
  const result: any = {
    auto_follow_up: {
      text: chatToolData.greeting,
    },
    media_type: mediaType,
    text_format: {
      customer_action_type: 'ice_breakers',
      message: {
        ice_breakers: iceBreakers,
        quick_replies: [],
        text: chatToolData.greeting,
      },
    },
  };
  if (chatToolData.reengagementEnabled) {
    result.reengagement = {
      include_products: false,
      text: chatToolData.reengagementText,
    };
  }
  return result;
}

/**
 * 转换受众定向
 */
function transformTargeting(group: RegionGroup, _formData: FormData): any {
  const targeting: any = {
    age_range: normalizeAgeRange(group),
    geo_locations: {
      countries: extractCountries(group),
    },
  };

  // 平台
  if (
    group.publisher_platforms &&
    group.publisher_platforms.length > 0 &&
    !isAllPublisherPlatformsSelected(group.publisher_platforms)
  ) {
    targeting.publisher_platforms = group.publisher_platforms;
  }
  // 进阶赋能型受众
  if (group.isNewModelEnabled) {
    targeting.targeting_automation = {
      advantage_audience: 1,
    };
  }

  // 设备平台
  if (group.device_platforms && group.device_platforms.length > 0) {
    targeting.device_platforms = group.device_platforms;
  }

  // 操作系统（包含版本信息）
  if (group.user_os && group.user_os.length > 0) {
    targeting.user_os = group.user_os;
  }

  // 包含的具体设备
  if (group.user_device && group.user_device.length > 0) {
    targeting.user_device = group.user_device;
  }

  // 语言
  if (group.language && group.language.length > 0) {
    targeting.locales = group.language.map(Number);
  }

  // 性别筛选
  if (group.gender !== '不限') {
    const genderValue = group.gender === '男' ? [1] : [2];
    targeting.genders = genderValue;
  }

  return targeting;
}

/**
 * 转换推广对象 (Pixel配置)
 */
function transformPromotedObject(
  group: RegionGroup,
  _formData: FormData,
  adsetIndex: number,
  seriesType?: string,
): any | undefined {
  if (seriesType === '互动') {
    const pageId = getPageIdFromTask(_formData, adsetIndex);
    if (!pageId) return undefined;
    return { page_id: pageId };
  }

  const conversionGoal = group.conversionGoal || _formData.conversionEvent;

  if (!conversionGoal) {
    return undefined;
  }

  const taskIndex = Math.min(
    adsetIndex,
    _formData.selectedTasksData.length - 1,
  );
  const task = _formData.selectedTasksData[Math.max(taskIndex, 0)];

  if (!task) {
    return undefined;
  }

  const promotedObject: any = {
    custom_event_type: conversionGoal,
  };

  const conversionLocation =
    group.conversionLocation || _formData.conversionLocation;

  if (conversionLocation === 'APP') {
    const appId = group.applicationId || _formData.applicationId;
    const storeUrl = group.objectStoreUrl || _formData.appStoreUrl;

    if (appId) {
      promotedObject.application_id = appId;
    }
    if (storeUrl) {
      promotedObject.object_store_url = storeUrl;
    }
  }

  return promotedObject;
}

/**
 * 转换广告列表
 * 根据素材索引从对应任务线中获取公共主页ID
 */
function transformAds(formData: FormData): any[] {
  return formData.uploadedMaterials.map((material, materialIndex) => {
    // 根据素材索引获取对应的任务线（如果索引超出范围，使用第一个任务线）
    const taskIndex = Math.min(
      materialIndex,
      formData.selectedTasksData.length - 1,
    );
    const finalTaskIndex =
      taskIndex >= 0 && taskIndex < formData.selectedTasksData.length
        ? taskIndex
        : formData.selectedTasksData.length > 0
          ? 0
          : -1;
    const task =
      finalTaskIndex >= 0
        ? formData.selectedTasksData[finalTaskIndex]
        : undefined;

    // 根据来源视图选择 name 字段
    let adName = material.name; // 默认使用 name
    if (material._sourceView === 'view1' && material.unique_name) {
      adName = material.unique_name;
    } else if (material._sourceView === 'view2' && material.basename) {
      adName = material.basename;
    }
    if (!adName) {
      adName = material.basename || material.filename;
    }

    // 确定素材类型
    const isVideo = material.filetype === 'video';
    const creativeType = isVideo ? 'video' : 'image';

    const creative: any = {
      body: material.description || '',
      title: material.title || '',
      type: creativeType,
      call_to_action: {},
    };

    if (isVideo) {
      creative.video_id = material.materialId;
    } else {
      creative.image_hash = material.materialId;
    }

    // 保存 basename 和 img
    if (material.unique_name || material.basename) {
      creative.basename = material.unique_name || material.basename;
    }
    if (material.img) {
      creative.img = material.img;
    }

    if (material.callToAction) {
      creative.call_to_action.type = material.callToAction;
    }

    if (formData.isEngagement) {
      const destType = formData.conversionLocation || '';
      if (MESSAGING_DESTINATION_SUBTYPES[destType]) {
        creative.call_to_action.value = { app_destination: destType };
      }
      const effectiveChatToolData = material.chatToolData || formData.chatToolData;
      if (effectiveChatToolData) {
        creative.page_welcome_message = buildPageWelcomeMessage(
          effectiveChatToolData,
        );
      }
    }

    if (!material.isOriginalPost && material.enhancement) {
      creative.enhancement = { ...material.enhancement };
    }

    const pageId = safeString(
      (task?.advertisers?.[0] as any)?.selectedPublicPage ||
        (task?.advertisers?.[0] as any)?.公共主页ID ||
        '',
    );

    return {
      contextual_multi_ads: {
        enroll_status:
          formData.seriesList[0]?.seriesSettings?.contextualMultiAds === false
            ? 'OPT_OUT'
            : 'OPT_IN',
      },
      creative: material.isOriginalPost && material.pageId && material.id
        ? { post_id: `${material.pageId}_${material.id}` }
        : creative,
      link_url: formData.appStoreUrl || task?.url || '',
      ...(material.displayLink ? { display_link: material.displayLink } : {}),
      name: adName,
      page_id: pageId,
      status: 'ACTIVE',
      ...(material._targetAccountName
        ? { target_account_name: material._targetAccountName }
        : {}),
      ...(material._targetAdsetNames
        ? { target_adset_name: material._targetAdsetNames }
        : {}),
      ...(material._allocByTag ? { by_tag: true } : {}),
    };
  });
}

/**
 * 转换广告组列表
 */
function transformAdSets(series: SeriesData, formData: FormData): any[] {
  const bidStrategy =
    series.seriesSettings.targetPrice || 'LOWEST_COST_WITHOUT_CAP';
  return series.regionGroups.map((group, groupIndex) => {
    const adset: any = {
      bid_strategy: bidStrategy,
      ...(bidStrategy === 'LOWEST_COST_WITHOUT_CAP'
        ? {}
        : {
            bid_amount: convertBudgetToCents(
              Number(series.seriesSettings.targetValue),
            ),
          }),
      billing_event: group.billingEvent || 'IMPRESSIONS',
      // 关闭时不下发, 由 FB 自行处理
      ...(series.seriesSettings.inventoryFilterLevel === 'OFF'
        ? {}
        : {
            brand_safety_content_filter_levels: [
              `FACEBOOK_${series.seriesSettings.inventoryFilterLevel ?? 'RELAXED'}`,
              `AN_${series.seriesSettings.inventoryFilterLevel ?? 'RELAXED'}`,
            ],
          }),
      name: group.name,
      optimization_goal: group.optimizationTarget,
      status: 'ACTIVE',
      targeting: transformTargeting(group, formData),
    };

    // 动态素材：开启后单图/单文案也由后端包成 asset_feed_spec
    if (group.isDynamicCreative) {
      adset.is_dynamic_creative = true;
    }

    // 转化发生位置
    if (group.conversionLocation) {
      adset.destination_type = group.conversionLocation;
    }

    // 排期时间
    if (formData.schedule_start_time) {
      adset.start_time = formData.schedule_start_time;
    }
    if (formData.schedule_end_time) {
      adset.end_time = formData.schedule_end_time;
    }

    // 如果是广告组预算，则在广告组级别添加预算字段
    if (series.seriesSettings.objectiveType === '广告组预算') {
      Object.assign(adset, transformBudget(series.seriesSettings));
    }

    const seriesType = series.seriesSettings.seriesType;

    const promotedObject = transformPromotedObject(
      group,
      formData,
      groupIndex,
      seriesType,
    );
    if (promotedObject) {
      adset.promoted_object = promotedObject;
    }

    if (seriesType === '互动' && adset.destination_type) {
      const pageId = getPageIdFromTask(formData, groupIndex);
      adset.engagement_config = buildEngagementConfig(
        adset.destination_type,
        pageId,
      );
    }

    return adset;
  });
}

/**
 * 转换广告系列列表
 */
function transformCampaigns(formData: FormData): any[] {
  return formData.seriesList.map((series) => {
    const specialAdCategories =
      series.seriesSettings.specialAdCategories ?? [];
    const campaign: any = {
      adsets: transformAdSets(series, formData),
      auto_regulation_identity:
        series.seriesSettings.autoRegulationIdentity ?? false,
      bid_strategy:
        series.seriesSettings.targetPrice || 'LOWEST_COST_WITHOUT_CAP',
      is_adset_budget_sharing_enabled:
        series.seriesSettings.objectiveType === '广告组预算',
      name: series.name,
      objective: mapObjective(series.seriesSettings.seriesType),
      special_ad_categories:
        specialAdCategories.length > 0 ? specialAdCategories : [],
      special_ad_category_country:
        specialAdCategories.length > 0
          ? (series.seriesSettings.specialAdCountries ?? [])
          : [],
      status: 'ACTIVE',
    };

    // 如果是广告系列预算，则在广告系列级别添加预算字段
    if (series.seriesSettings.objectiveType === '广告系列预算') {
      Object.assign(campaign, transformBudget(series.seriesSettings));
    }

    return campaign;
  });
}

/**
 * 收集所有广告到顶级数组
 * 将嵌套在 campaigns > adsets > ads 中的所有广告平铺到一个数组
 */
function flattenAllAds(formData: FormData): any[] {
  return transformAds(formData);
}

/**
 * 主转换函数: 将表单数据转换为API所需格式
 */
export function transformToAdvertisementParams(formData: FormData): any {
  return {
    account_groups: transformAccountGroups(formData.selectedTasksData, formData),
    ads: flattenAllAds(formData),
    campaigns: transformCampaigns(formData),
  };
}
