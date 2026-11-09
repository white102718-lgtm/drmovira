import type { TableColumnsType } from 'ant-design-vue';

import type { AdvertiserData, PublicPageOption } from '../types';

import { computed, ref } from 'vue';

import { message } from 'ant-design-vue';

import { batchQueryMissionLineInfo } from '#/api/advertisement';
import { getPixels } from '#/api/management/fb-resource';

// 反查 page_id 归属于 person_and_page 里哪个个号 key
function findAssignedOwnerKey(
  accountAndPage: Record<string, any[]>,
  pageId?: string,
): string | undefined {
  if (!pageId) return undefined;
  return Object.keys(accountAndPage).find((k) =>
    (accountAndPage[k] || []).some((p: any) => p.id === pageId),
  );
}

export function useAdvertiser() {
  const advertiserSearchName = ref('');
  const advertiserSearchAccountId = ref('');
  const advertiserSearchStatus = ref<string>('活跃');
  const advertiserSearchPixel = ref<string>('全部');
  const advertiserSearchPersonAccount = ref<string>('全部');
  const selectedAdvertisers = ref<string[]>([]);

  // 跨页缓存
  interface UserEditSnapshot {
    publicPageOptions?: PublicPageOption[];
    rawRecord?: any;
    selectedPersonAccount?: string;
    selectedPersonId?: string;
    selectedPixel?: string;
    selectedPublicPage?: string;
  }
  const userEditCache = new Map<string, UserEditSnapshot>();
  const pageCheckboxCache = new Map<number, string[]>();
  const allSelectedAccountIds = ref<string[]>([]);

  function refreshAllSelectedIds() {
    const all = new Set<string>();
    pageCheckboxCache.forEach((keys) => keys.forEach((k) => all.add(k)));
    allSelectedAccountIds.value = [...all];
  }

  // 表格 loading
  const tableLoading = ref(false);

  // 分页状态
  const advertiserPage = ref(1);
  const advertiserPageSize = ref(50);
  const advertiserTotal = ref(0);

  // 将任务线数据转换为广告账户列表
  const advertisers = ref<AdvertiserData[]>([]);

  // 初始化广告账户数据
  let lastInitKey: null | string = null;

  function clearLoadedAccounts(page = 1) {
    advertisers.value = [];
    selectedAdvertisers.value = [];
    advertiserPage.value = page;
    advertiserTotal.value = 0;
    lastInitKey = null;
    userEditCache.clear();
    pageCheckboxCache.clear();
    refreshAllSelectedIds();
  }

  function initAdvertisers(taskData?: any, forcePixel = true) {
    if (!taskData) {
      clearLoadedAccounts();
      return;
    }

    const taskPixelName: string | undefined =
      taskData.pixel_name ||
      taskData.pixelName ||
      taskData.pixel ||
      taskData.像素名称;

    // 更新分页状态
    advertiserTotal.value =
      taskData.accounts_total ?? taskData.accounts?.length ?? 0;
    advertiserPage.value = taskData.accounts_page ?? 1;
    advertiserPageSize.value = taskData.accounts_page_size ?? 50;

    // 检查是否有 accounts 数组
    if (!Array.isArray(taskData.accounts) || taskData.accounts.length === 0) {
      advertisers.value = [];
      lastInitKey = null;
      return;
    }

    const initKey = `${taskData.taskCode ?? ''}_${taskData.accounts_page ?? 1}_${taskData.accounts?.length ?? 0}`;
    if (initKey === lastInitKey && advertisers.value.length > 0) return;
    lastInitKey = initKey;

    advertisers.value = taskData.accounts.map((account: any, index: number) => {
      let personAccountOptions: Array<{ name: string; person_id: string }> = [];
      const allPublicPageOptions: PublicPageOption[] = [];
      let selectedPersonAccount: string | undefined;
      let selectedPersonId: string | undefined;
      let selectedPublicPage: string | undefined;

      const accountAndPage = account.person_and_page || {};

      personAccountOptions = Object.keys(accountAndPage).map((personName) => {
        const pages = accountAndPage[personName];
        const personId = pages[0]?.person_id || '';
        return { name: personName, person_id: personId };
      });

      Object.entries(accountAndPage).forEach(
        ([personName, pages]: [string, any]) => {
          pages.forEach((page: any) => {
            allPublicPageOptions.push({
              id: page.id,
              name: page.name,
              label: `${page.name} ID: ${page.id}`,
              value: page.id,
              personName,
              personId: page.person_id,
              picture: page.picture || '',
            });
          });
        },
      );

      // 默认主页只用代理线配置分配的 assigned_page_id,未配置则不预选
      const assignedOwnerKey = findAssignedOwnerKey(
        accountAndPage,
        account.assigned_page_id,
      );
      selectedPersonAccount = assignedOwnerKey ?? personAccountOptions[0]?.name;
      selectedPersonId =
        personAccountOptions.find((p) => p.name === selectedPersonAccount)
          ?.person_id ?? personAccountOptions[0]?.person_id;
      selectedPublicPage = account.assigned_page_id;

      // 处理像素选项
      const pixelOptions = (account.pixels || []).map((item: any) => ({
        id: item.id,
        name: item.name,
        label: `${item.name} ID: ${item.id}`,
        value: item.id,
      }));

      let selectedPixelId: string | undefined;
      if (taskPixelName && pixelOptions.length > 0) {
        const matched = pixelOptions.find(
          (opt: any) => opt.name === taskPixelName,
        );
        if (matched) {
          selectedPixelId = matched.id;
        }
      }
      if (!selectedPixelId && pixelOptions.length > 0) {
        selectedPixelId = pixelOptions[0].id;
      }

      return {
        // 先保留原始数据，再以稳定的平台账户 ID 和规范化字段收口。
        ...taskData,
        ...account,

        // 唯一标识
        id: account.ad_account_id || `${taskData.taskCode || '1'}_${index}`,

        // 任务线信息（从 taskData 继承）
        projectName: taskData.projectName,
        regionName: taskData.regionName,
        taskName: taskData.taskName,
        taskCode: taskData.taskCode,
        url: taskData.url,
        dealerName: taskData.dealerName,

        // 广告账户信息
        accountId: account.ad_account_id,
        accountName: account.ad_account_name,
        bmName: account.bm_name || '-',
        status: account.status || '活跃',

        // 账户财务信息
        spendCap: account.spend_cap || 0,
        balance: account.balance || 0,

        // 个号字段
        personAccountOptions,
        selectedPersonAccount,
        selectedPersonId,

        // 公共主页选项（包含个号信息）
        publicPageOptions: allPublicPageOptions,
        selectedPublicPage,

        // 像素选项
        pixelOptions,
        selectedPixel: selectedPixelId,
      };
    });

    const pixelSet = new Set<string>();
    advertisers.value.forEach((adv) => {
      if (Array.isArray(adv.pixelOptions)) {
        adv.pixelOptions.forEach((opt: any) => {
          if (opt.name) {
            pixelSet.add(opt.name);
          }
        });
      }
    });

    const allPixels = [...pixelSet];
    if (forcePixel && !taskPixelName && allPixels.length > 0) {
      advertiserSearchPixel.value = allPixels[0] ?? '全部';
    }

    // 任务线有像素时回填筛选栏
    if (taskPixelName && forcePixel) {
      advertiserSearchPixel.value = taskPixelName;
    }
  }

  function saveCurrentPageState() {
    advertisers.value.forEach((adv) => {
      userEditCache.set(adv.accountId, {
        selectedPersonAccount: adv.selectedPersonAccount,
        selectedPersonId: adv.selectedPersonId,
        selectedPublicPage: adv.selectedPublicPage,
        selectedPixel: adv.selectedPixel,
        publicPageOptions: adv.publicPageOptions,
        rawRecord: adv,
      });
    });
    pageCheckboxCache.set(advertiserPage.value, [...selectedAdvertisers.value]);
    refreshAllSelectedIds();
  }

  function restorePageState(page: number) {
    let hasRestored = false;
    advertisers.value.forEach((adv) => {
      const cached = userEditCache.get(adv.accountId);
      if (!cached) return;
      if (cached.selectedPersonAccount !== undefined)
        adv.selectedPersonAccount = cached.selectedPersonAccount;
      if (cached.selectedPersonId !== undefined)
        adv.selectedPersonId = cached.selectedPersonId;
      if (cached.selectedPublicPage !== undefined)
        adv.selectedPublicPage = cached.selectedPublicPage;
      if (cached.selectedPixel !== undefined)
        adv.selectedPixel = cached.selectedPixel;
      if (cached.publicPageOptions?.length)
        adv.publicPageOptions = cached.publicPageOptions;
      hasRestored = true;
    });
    const cachedKeys = pageCheckboxCache.get(page);
    if (cachedKeys !== undefined) selectedAdvertisers.value = cachedKeys;
    if (hasRestored) advertisers.value = [...advertisers.value];
  }

  let lastPixelFilter: string | undefined;

  async function loadPageAccounts(
    taskData: any,
    page: number,
    filters?: {
      account_id?: string[];
      account_name?: string[];
      pixel_name_filter?: string;
      status?: string;
    },
  ) {
    if (!taskData) return;
    saveCurrentPageState();
    // 像素筛选变了 → 旧的选中缓存作废，默认选中跟着新搜索走
    if (filters?.pixel_name_filter !== lastPixelFilter) {
      lastPixelFilter = filters?.pixel_name_filter;
      userEditCache.forEach((snap) => {
        snap.selectedPixel = undefined;
      });
    }
    lastInitKey = null;
    tableLoading.value = true;
    try {
      const queries = [
        {
          task_name: taskData.projectName || '',
          subtask_name: taskData.taskName || '',
        },
      ];
      const resp = await batchQueryMissionLineInfo(
        queries,
        page,
        advertiserPageSize.value,
        filters,
      );
      const results = resp?.data;
      const responseCode = resp?.code;
      const responseMessage = resp?.message;

      if (responseCode === 400) {
        clearLoadedAccounts(page);
        if (responseMessage) {
          message.error(responseMessage);
        }
        return;
      }

      if (results && Array.isArray(results) && results[0]) {
        const accounts = results[0].accounts || [];
        const pageData = {
          ...taskData,
          // 按像素搜索时默认选中跟着搜索走，与后端 _front_load_pixel 一致
          pixel_name: filters?.pixel_name_filter || taskData.pixel_name,
          accounts,
          accounts_total: results[0].accounts_total,
          accounts_page: page,
          accounts_page_size: results[0].accounts_page_size,
        };
        initAdvertisers(pageData, false);
        restorePageState(page);
      } else {
        clearLoadedAccounts(page);
        if (responseMessage) message.warning(responseMessage);
      }
    } catch (error: any) {
      clearLoadedAccounts(page);
      const errorMessage =
        error?.response?.data?.message || error?.message || '查询广告账户失败';
      message.error(errorMessage);
    } finally {
      tableLoading.value = false;
    }
  }

  // 动态生成表格列
  const advertiserColumns = computed<TableColumnsType>(() => [
    // { title: '投放师', dataIndex: 'dealerName', width: 120, fixed: 'left' },
    { title: '广告账户名称', dataIndex: 'accountName', width: 280 },
    { title: '广告账户ID', dataIndex: 'accountId', width: 150 },
    // { title: '所属BM', dataIndex: 'bmName', width: 180, ellipsis: true },
    { title: '个号', key: 'personAccountSelect', width: 160 },
    { title: '公共主页', key: 'publicPageSelect', width: 220 },
    { title: '像素', key: 'pixelSelect', width: 220 },
    { title: '账户限额', dataIndex: 'spendCap', width: 100 },
    { title: '账户余额', dataIndex: 'balance', width: 100 },
    { title: '状态', key: 'statusBadge', width: 80 },
  ]);

  // 像素筛选候选：走后端 /fb_resource/pixels 模糊搜索（大小写不敏感，与 pixel_name_filter 同逻辑）
  const pixelSearchOptions = ref<string[]>([]);
  const pixelSearchLoading = ref(false);
  let pixelSearchTimer: null | ReturnType<typeof setTimeout> = null;

  async function loadPixelOptions(kw?: string) {
    pixelSearchLoading.value = true;
    try {
      const resp: any = await getPixels({
        page: 1,
        page_size: 20,
        personal_only: true,
        ...(kw ? { name: kw } : {}),
      });
      const items: any[] = resp?.items || [];
      pixelSearchOptions.value = [
        ...new Set(items.map((p: any) => p.name).filter(Boolean)),
      ] as string[];
    } catch (error) {
      pixelSearchOptions.value = [];
      void error;
    } finally {
      pixelSearchLoading.value = false;
    }
  }

  function handlePixelSearch(kw: string) {
    if (pixelSearchTimer) clearTimeout(pixelSearchTimer);
    pixelSearchTimer = setTimeout(() => loadPixelOptions(kw || undefined), 300);
  }

  // 获取所有可用的像素选项（用于筛选下拉框）
  const pixelFilterOptions = computed(() => {
    const pixelSet = new Set<string>();
    advertisers.value.forEach((adv) => {
      if (Array.isArray(adv.pixelOptions)) {
        adv.pixelOptions.forEach((opt: any) => {
          if (opt.name) {
            pixelSet.add(opt.name);
          }
        });
      }
    });
    return [...pixelSet];
  });

  // 获取所有可用的个号选项（用于筛选下拉框）
  const personAccountFilterOptions = computed(() => {
    const personSet = new Set<string>();
    advertisers.value.forEach((adv) => {
      if (Array.isArray(adv.personAccountOptions)) {
        adv.personAccountOptions.forEach((opt: any) => {
          if (opt.name) {
            personSet.add(opt.name);
          }
        });
      }
    });
    return [...personSet];
  });

  // 过滤后的广告账户列表
  const filteredAdvertisers = computed(() => {
    let result = advertisers.value;

    if (advertiserSearchName.value) {
      const searchLower = advertiserSearchName.value.trim().toLowerCase();
      result = result.filter(
        (adv) =>
          (adv.accountName || '').toLowerCase().includes(searchLower) ||
          (adv.accountId || '').toLowerCase().includes(searchLower) ||
          (adv.taskName || '').toLowerCase().includes(searchLower) ||
          (adv.projectName || '').toLowerCase().includes(searchLower),
      );
    }

    if (advertiserSearchStatus.value !== '全部') {
      result = result.filter(
        (adv) => adv.status === advertiserSearchStatus.value,
      );
    }

    if (advertiserSearchPixel.value !== '全部') {
      result = result.filter((adv) => {
        if (!Array.isArray(adv.pixelOptions)) return false;
        return adv.pixelOptions.some(
          (opt: any) => opt.name === advertiserSearchPixel.value,
        );
      });
    }

    if (advertiserSearchPersonAccount.value !== '全部') {
      result = result.filter((adv) => {
        if (!Array.isArray(adv.personAccountOptions)) return false;
        return adv.personAccountOptions.some(
          (opt: any) => opt.name === advertiserSearchPersonAccount.value,
        );
      });
    }

    return result;
  });

  function resetSelection() {
    selectedAdvertisers.value = [];
    advertisers.value = [];
    lastInitKey = null;
    advertiserSearchName.value = '';
    advertiserSearchAccountId.value = '';
    advertiserSearchStatus.value = '活跃';
    advertiserSearchPixel.value = '全部';
    advertiserSearchPersonAccount.value = '全部';
    advertiserPage.value = 1;
    advertiserTotal.value = 0;
    userEditCache.clear();
    pageCheckboxCache.clear();
    refreshAllSelectedIds();
  }

  // ---- 弹窗共用函数 ----
  function filterOption(input: string, option: any) {
    const label = option.label || option.children?.[0]?.children || '';
    return label.toLowerCase().includes(input.toLowerCase());
  }

  function handleSelectionChange(keys: any) {
    selectedAdvertisers.value = keys;
    pageCheckboxCache.set(advertiserPage.value, [...keys]);
    refreshAllSelectedIds();
  }

  function handlePixelFilterChange(val: any) {
    advertiserSearchPixel.value = val;
  }

  // 切换个号后，默认主页必须属于该个号；未配置默认主页时保持未选中。
  function handlePersonAccountChange(record: any, value: any) {
    const personValue = Array.isArray(value) ? value[0] : value;
    const personName =
      typeof personValue === 'number' ? String(personValue) : personValue;
    record.selectedPersonAccount = personName;
    const person = record.personAccountOptions?.find(
      (p: any) => p.name === personName,
    );
    record.selectedPersonId = person?.person_id;
    const assignedPage = record.publicPageOptions?.find(
      (page: any) =>
        page.personName === personName && page.id === record.assigned_page_id,
    );
    record.selectedPublicPage = assignedPage?.id;
    advertisers.value = [...advertisers.value];
  }

  // Select 版批量
  function applyBatchPixelById(pixelId: string, selectedKeys: string[]) {
    if (!pixelId) return { success: false, message: '请选择像素' };
    if (selectedKeys.length === 0)
      return { success: false, message: '请先选择要应用的行' };
    let appliedCount = 0;
    advertisers.value.forEach((adv) => {
      if (selectedKeys.includes(adv.id || '')) {
        const matched = adv.pixelOptions?.find(
          (opt: any) => opt.id === pixelId,
        );
        if (matched) {
          adv.selectedPixel = matched.id;
          appliedCount++;
        }
      }
    });
    // 跨页缓存
    const currentPageIds = new Set(
      advertisers.value.map((adv) => adv.id || ''),
    );
    selectedKeys.forEach((key) => {
      if (currentPageIds.has(key)) return;
      const cached = userEditCache.get(key);
      if (cached) {
        const matched = cached.rawRecord?.pixelOptions?.find(
          (opt: any) => opt.id === pixelId,
        );
        if (matched) {
          cached.selectedPixel = matched.id;
          if (cached.rawRecord) cached.rawRecord.selectedPixel = matched.id;
          appliedCount++;
        }
      }
    });
    return appliedCount > 0
      ? { success: true, message: `已应用像素到 ${appliedCount} 个账户` }
      : { success: false, message: '所选账户中无匹配的像素' };
  }

  function applyBatchPersonAccountById(
    personName: string,
    selectedKeys: string[],
  ) {
    if (!personName) return { success: false, message: '请选择个号' };
    if (selectedKeys.length === 0)
      return { success: false, message: '请先选择要应用的行' };
    let appliedCount = 0;
    advertisers.value.forEach((adv) => {
      if (selectedKeys.includes(adv.id || '')) {
        const matched = adv.personAccountOptions?.find(
          (p: any) => p.name === personName,
        );
        if (matched) {
          adv.selectedPersonAccount = matched.name;
          adv.selectedPersonId = matched.person_id;
          adv.selectedPublicPage = adv.publicPageOptions?.some(
            (page: any) =>
              page.id === adv.assigned_page_id &&
              page.personName === matched.name,
          )
            ? adv.assigned_page_id
            : undefined;
          appliedCount++;
        }
      }
    });
    return appliedCount > 0
      ? { success: true, message: `已应用个号到 ${appliedCount} 个账户` }
      : { success: false, message: '所选账户中无匹配的个号' };
  }

  function applyBatchPublicPageById(pageId: string, selectedKeys: string[]) {
    if (!pageId) return { success: false, message: '请选择公共主页' };
    if (selectedKeys.length === 0)
      return { success: false, message: '请先选择要应用的行' };
    let appliedCount = 0;

    // 批量主页仅应用到当前选中个号实际持有该主页的账户，不注入池外主页。
    function applyToRecord(rec: any): boolean {
      const matched = rec.publicPageOptions?.find(
        (opt: PublicPageOption) =>
          opt.id === pageId && opt.personName === rec.selectedPersonAccount,
      );
      if (!matched) return false;
      rec.selectedPublicPage = matched.id;
      return true;
    }

    // 当前页
    advertisers.value.forEach((adv) => {
      if (selectedKeys.includes(adv.id || '') && applyToRecord(adv)) {
        appliedCount++;
      }
    });
    // 跨页缓存：改 rawRecord 后把选中值同步回顶层快照
    const currentPageIds = new Set(
      advertisers.value.map((adv) => adv.id || ''),
    );
    selectedKeys.forEach((key) => {
      if (currentPageIds.has(key)) return;
      const cached = userEditCache.get(key);
      if (!cached?.rawRecord || !applyToRecord(cached.rawRecord)) return;
      cached.selectedPersonAccount = cached.rawRecord.selectedPersonAccount;
      cached.selectedPersonId = cached.rawRecord.selectedPersonId;
      cached.selectedPublicPage = cached.rawRecord.selectedPublicPage;
      cached.publicPageOptions = cached.rawRecord.publicPageOptions;
      appliedCount++;
    });
    return appliedCount > 0
      ? { success: true, message: `已应用公共主页到 ${appliedCount} 个账户` }
      : { success: false, message: '所选账户中无匹配的个号/主页' };
  }

  return {
    advertiserSearchName,
    advertiserSearchAccountId,
    advertiserSearchStatus,
    advertiserSearchPixel,
    advertiserSearchPersonAccount,
    selectedAdvertisers,
    advertisers,
    advertiserColumns,
    filteredAdvertisers,
    pixelFilterOptions,
    personAccountFilterOptions,
    advertiserPage,
    advertiserPageSize,
    advertiserTotal,
    initAdvertisers,
    loadPageAccounts,
    resetSelection,
    filterOption,
    handleSelectionChange,
    handlePixelFilterChange,
    pixelSearchOptions,
    pixelSearchLoading,
    loadPixelOptions,
    handlePixelSearch,
    handlePersonAccountChange,
    tableLoading,
    applyBatchPixelById,
    applyBatchPersonAccountById,
    applyBatchPublicPageById,
    userEditCache,
    allSelectedAccountIds,
    saveCurrentPageState,
  };
}
