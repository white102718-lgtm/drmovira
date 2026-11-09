<script setup lang="ts">
import type { MaterialItem } from '#/views/createAdvertisement/types';

import { computed, onUnmounted, ref, watch } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  Button,
  Checkbox,
  Drawer,
  Empty,
  Image,
  message,
  Popconfirm,
  Select,
  Spin,
  Switch,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import { getUserNameOptions } from '#/api';
import {
  createAds,
  createMaterialTemplate,
  deleteAds,
  queryAdStructure,
  updateMaterialTemplate,
} from '#/api/advertisement';
import { reuseCreativeHistory } from '#/api/advertisement/creativeHistory';
import {
  applyMaterialGroup,
  createMaterialGroup,
  updateMaterialGroup,
} from '#/api/advertisement/materialGroup';
import { getBatchMaterialImgApi, getMaterialsByIds } from '#/api/materials/all';
import MaterialGroupLoadTab from '#/views/createAdvertisement/components/MaterialGroupLoadTab.vue';
import MaterialTemplateLoadTab from '#/views/createAdvertisement/components/MaterialTemplateLoadTab.vue';
import AdCreativeSelectionModal from '#/views/createAdvertisement/modals/AdCreativeSelectionModal.vue';
import CreativeHistoryModal from '#/views/createAdvertisement/modals/CreativeHistoryModal.vue';
import MaterialGroupSaveModal from '#/views/createAdvertisement/modals/MaterialGroupSaveModal.vue';
import MaterialSelectionModal from '#/views/createAdvertisement/modals/MaterialSelectionModal.vue';
import TemplateSaveModal from '#/views/createAdvertisement/modals/TemplateSaveModal.vue';

interface PageOption {
  developer_ids: string[];
  id: string;
  name: string;
  picture?: string;
}

interface DevOption {
  id: string;
  name: string;
  type?: 'personal' | 'system';
}

interface TreeAd {
  ad_id: string;
  ad_name: string;
  thumbnail?: string;
}

interface PendingAd {
  body: string;
  callToAction: string | undefined;
  img?: string;
  materialId: string;
  name: string;
  pageId: string;
  title: string;
  uid: string;
}

interface TreeAdset {
  ads: TreeAd[];
  adset_id: string;
  adset_name: string;
  page_options: PageOption[];
  pendingAds: PendingAd[];
}

interface TreeCampaign {
  adsets: TreeAdset[];
  campaign_id: string;
  campaign_name: string;
}

interface TreeAccount {
  account_id: string;
  account_name: string;
  campaigns: TreeCampaign[];
  developers: DevOption[];
  link_url: string;
  selectedDevId: string;
}

const props = defineProps<{
  adIds?: string[];
  adsetIds?: string[];
  campaignIds?: string[];
  open: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void;
}>();

const loading = ref(false);
const treeData = ref<TreeAccount[]>([]);
const expandedIds = ref(new Set<string>());
const pendingDeleteAds = ref<
  Array<{ account_id: string; id: string; name: string }>
>([]);
const overZoneId = ref<null | string>(null);

const materials = ref<MaterialItem[]>([]);
const selectedMaterialIds = ref<string[]>([]);
const batchTitle = ref('');
const batchBody = ref('');
const batchCTA = ref<string | undefined>(undefined);

const showMaterialModal = ref(false);
const showAdCreativeModal = ref(false);
const showMaterialGroupSaveModal = ref(false);
const showCreativeHistoryModal = ref(false);

const materialGroupLoadTabRef = ref<any>(null);
const currentMaterialGroupId = ref<null | string>(null);
const currentMaterialGroupName = ref('');
const currentMaterialGroupDescription = ref('');

const operatorOptions = ref<Array<{ label: string; value: string }>>([]);

const userStore = useUserStore();
const showTemplateSaveModal = ref(false);
const currentMaterialTemplateId = ref<null | string>(null);
const currentMaterialTemplateName = ref('');

const uploadedMaterialIds = computed(() =>
  materials.value.map((m) => m.id || m.materialId).filter(Boolean),
);

const callToActionOptions = [
  { value: 'ORDER_NOW', label: '立即订购' },
  { value: 'SUBSCRIBE', label: '订阅' },
  { value: 'LEARN_MORE', label: '详细了解' },
  { value: 'DOWNLOAD', label: '下载' },
  { value: 'BOOK_NOW', label: '立即预定' },
  { value: 'SHOP_NOW', label: '去逛逛' },
  { value: 'LISTEN_NOW', label: '立即收听' },
  { value: 'PLAY_GAME', label: '玩游戏' },
  { value: 'WATCH_MORE', label: '更多视频' },
  { value: 'SIGN_UP', label: '立即注册' },
  { value: 'BUY_NOW', label: '立即购买' },
  { value: 'USE_APP', label: '使用应用' },
  { value: 'INSTALL_APP', label: '立即安装' },
  { value: 'NO_BUTTON', label: '无按钮' },
  { value: 'APPLY_NOW', label: '立即申请' },
  { value: 'CONTACT_US', label: '联系我们' },
  { value: 'GET_OFFER', label: '领取优惠' },
];

const pendingAdsCount = computed(() => {
  let count = 0;
  treeData.value.forEach((acc) =>
    acc.campaigns.forEach((camp) =>
      camp.adsets.forEach((adset) => {
        count += adset.pendingAds.length;
      }),
    ),
  );
  return count;
});

const bootstrapExpanded = () => {
  const next = new Set<string>();
  treeData.value.forEach((acc) => {
    next.add(acc.account_id);
    acc.campaigns.forEach((camp) => {
      next.add(camp.campaign_id);
      camp.adsets.forEach((adset) => next.add(adset.adset_id));
    });
  });
  expandedIds.value = next;
};

const toggleExpand = (id: string) => {
  const next = new Set(expandedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedIds.value = next;
};

const pickAdsetPage = (page_options: PageOption[], devId: string): string => {
  const candidates = page_options.filter(
    (p) => !devId || p.developer_ids.includes(devId),
  );
  return candidates[0]?.id ?? '';
};

const onDevChange = (account: TreeAccount) => {
  const devId = account.selectedDevId;
  account.campaigns.forEach((camp) =>
    camp.adsets.forEach((adset) => {
      const validIds = new Set(
        adset.page_options
          .filter((p) => !devId || p.developer_ids.includes(devId))
          .map((p) => p.id),
      );
      const fallback = pickAdsetPage(adset.page_options, devId);
      adset.pendingAds.forEach((pad) => {
        if (!pad.pageId || !validIds.has(pad.pageId)) pad.pageId = fallback;
      });
    }),
  );
};

const fetchData = async () => {
  loading.value = true;
  try {
    const params: {
      ad_ids?: string[];
      adset_ids?: string[];
      campaign_ids?: string[];
    } = {};
    if (props.campaignIds?.length) params.campaign_ids = props.campaignIds;
    if (props.adsetIds?.length) params.adset_ids = props.adsetIds;
    if (props.adIds?.length) params.ad_ids = props.adIds;
    const result = await queryAdStructure(params);
    const raw: any[] = result ?? [];
    treeData.value = raw.map((acc) => {
      const developers: DevOption[] = acc.developers ?? [];
      const selectedDevId = developers[0]?.id ?? '';
      return {
        account_id: acc.account_id,
        account_name: acc.account_name,
        link_url: acc.link_url,
        developers,
        selectedDevId,
        campaigns: (acc.campaigns ?? []).map((camp: any) => ({
          campaign_id: camp.campaign_id,
          campaign_name: camp.campaign_name,
          adsets: (camp.adsets ?? []).map((adset: any) => ({
            adset_id: adset.adset_id,
            adset_name: adset.adset_name,
            ads: adset.ads ?? [],
            page_options: (adset.page_options ?? []) as PageOption[],
            pendingAds: [],
          })),
        })),
      } as TreeAccount;
    });
    bootstrapExpanded();
  } catch {
  } finally {
    loading.value = false;
  }
};

const loadOperatorOptions = async () => {
  try {
    const users = await getUserNameOptions(['operator', 'operator_leader']);
    operatorOptions.value = users.map((user) => ({
      label: user.full_name,
      value: user.real_name,
    }));
  } catch {}
};

watch(
  () => props.open,
  (val) => {
    if (val) {
      fetchData();
      loadOperatorOptions();
    } else {
      treeData.value = [];
      materials.value = [];
      selectedMaterialIds.value = [];
      expandedIds.value = new Set();
      overZoneId.value = null;
      pendingDeleteAds.value = [];
    }
  },
);

const onMaterialDragStart = (event: DragEvent, mat: MaterialItem) => {
  event.dataTransfer?.setData('text/plain', mat.id || mat.materialId);
  event.dataTransfer?.setData('mat-name', mat.basename || mat.filename || '');
  event.dataTransfer?.setData('mat-img', getMatImg(mat));
  event.dataTransfer?.setData('mat-title', mat.title || '');
  event.dataTransfer?.setData('mat-body', mat.description || '');
  event.dataTransfer?.setData('mat-cta', mat.callToAction || '');
};

const onDragOver = (event: DragEvent, adsetId: string) => {
  event.preventDefault();
  overZoneId.value = adsetId;
};

const onDragLeave = (event: DragEvent, adsetId: string) => {
  if (
    !(event.currentTarget as Element)?.contains(event.relatedTarget as Node) &&
    overZoneId.value === adsetId
  )
    overZoneId.value = null;
};

const onDrop = (event: DragEvent, adset: TreeAdset, account: TreeAccount) => {
  event.preventDefault();
  overZoneId.value = null;
  const materialId = event.dataTransfer?.getData('text/plain');
  if (!materialId) return;
  if (adset.pendingAds.some((p) => p.materialId === materialId)) return;
  adset.pendingAds.push({
    body: event.dataTransfer?.getData('mat-body') || '',
    callToAction: event.dataTransfer?.getData('mat-cta') || undefined,
    img: event.dataTransfer?.getData('mat-img') || '',
    materialId,
    name: event.dataTransfer?.getData('mat-name') || materialId,
    pageId: pickAdsetPage(adset.page_options, account.selectedDevId),
    title: event.dataTransfer?.getData('mat-title') || '',
    uid: `${Date.now()}_${materialId}`,
  });
};

const removePendingAd = (adset: TreeAdset, uid: string) => {
  const idx = adset.pendingAds.findIndex((p) => p.uid === uid);
  if (idx !== -1) adset.pendingAds.splice(idx, 1);
};

const removeExistingAd = (
  adset: TreeAdset,
  adId: string,
  accountId: string,
) => {
  const idx = adset.ads.findIndex((a) => a.ad_id === adId);
  if (idx === -1) return;
  const ad = adset.ads[idx]!;
  pendingDeleteAds.value.push({
    account_id: accountId,
    id: ad.ad_id,
    name: ad.ad_name,
  });
  adset.ads.splice(idx, 1);
};

const loadMaterialImages = async (mats: MaterialItem[]) => {
  const uniqueNames = mats
    .filter((m) => !m.img && m.unique_name)
    .map((m) => m.unique_name);
  if (uniqueNames.length === 0) return;
  try {
    const imgs: any = await getBatchMaterialImgApi(uniqueNames);
    mats.forEach((m) => {
      if (m.unique_name && imgs[m.unique_name]) m.img = imgs[m.unique_name];
    });
  } catch {}
};

const normalizeMat = (m: MaterialItem): MaterialItem => ({
  ...m,
  callToAction: (m.callToAction as string) || undefined,
});

const handleMaterialConfirm = async (selected: MaterialItem[]) => {
  const existingIds = new Set(materials.value.map((m) => m.id || m.materialId));
  const newMats = selected
    .filter((m) => !existingIds.has(m.id || m.materialId))
    .map(normalizeMat);
  materials.value.push(...newMats);
  showMaterialModal.value = false;
  loadMaterialImages(newMats);
};

const handleAdCreativeConfirm = async (selected: any[]) => {
  const existingIds = new Set(materials.value.map((m) => m.id || m.materialId));
  const newMats = selected
    .filter((m) => !existingIds.has(m.id || m.materialId))
    .map(normalizeMat);
  materials.value.push(...newMats);
  showAdCreativeModal.value = false;
  loadMaterialImages(newMats);
};

const deleteSelectedMaterials = () => {
  if (selectedMaterialIds.value.length === 0) return;
  const removeSet = new Set(selectedMaterialIds.value);
  materials.value = materials.value.filter(
    (m) => !removeSet.has(m.id || m.materialId),
  );
  selectedMaterialIds.value = [];
};

const toggleMaterialSelect = (id: string) => {
  const idx = selectedMaterialIds.value.indexOf(id);
  if (idx === -1) {
    selectedMaterialIds.value.push(id);
  } else {
    selectedMaterialIds.value.splice(idx, 1);
  }
};

const selectAllMaterials = () => {
  selectedMaterialIds.value = materials.value.map((m) => m.id || m.materialId);
};

const invertSelection = () => {
  const current = new Set(selectedMaterialIds.value);
  selectedMaterialIds.value = materials.value
    .map((m) => m.id || m.materialId)
    .filter((id) => !current.has(id));
};

const pageFilterOption = (input: string, opt: any) =>
  opt.label?.toLowerCase().includes(input.toLowerCase());

const getMatImg = (mat: MaterialItem): string => {
  const raw = mat.img || (mat as any).thumbnail || '';
  if (!raw) return '';
  if (raw.startsWith('http') || raw.startsWith('data:')) return raw;
  return `data:image/jpeg;base64,${raw}`;
};

const clearAllMaterials = () => {
  selectedMaterialIds.value = [];
};

const setMatCTA = (mat: MaterialItem, v: unknown) => {
  mat.callToAction = (v as string) || undefined;
};

const isPreviewMode = ref(true);
const isSelecting = ref(false);
const selectionBox = ref({ startX: 0, startY: 0, endX: 0, endY: 0 });
const gridContainer = ref<HTMLElement | null>(null);
const selectionStartSelected = ref<Set<string>>(new Set());

const updateSelectedCards = () => {
  if (!gridContainer.value) return;
  const container = gridContainer.value;
  const cards = container.querySelectorAll<HTMLElement>('[data-mat-id]');
  const newSelected = new Set<string>(selectionStartSelected.value);
  const selectionRect = {
    left: Math.min(selectionBox.value.startX, selectionBox.value.endX),
    top: Math.min(selectionBox.value.startY, selectionBox.value.endY),
    right: Math.max(selectionBox.value.startX, selectionBox.value.endX),
    bottom: Math.max(selectionBox.value.startY, selectionBox.value.endY),
  };
  if (
    Math.abs(selectionBox.value.endX - selectionBox.value.startX) < 5 ||
    Math.abs(selectionBox.value.endY - selectionBox.value.startY) < 5
  )
    return;
  const containerRect = container.getBoundingClientRect();
  cards.forEach((card) => {
    const cardRect = card.getBoundingClientRect();
    const rel = {
      left: cardRect.left - containerRect.left + container.scrollLeft,
      top: cardRect.top - containerRect.top + container.scrollTop,
      right: cardRect.right - containerRect.left + container.scrollLeft,
      bottom: cardRect.bottom - containerRect.top + container.scrollTop,
    };
    const intersecting = !(
      rel.right < selectionRect.left ||
      rel.left > selectionRect.right ||
      rel.bottom < selectionRect.top ||
      rel.top > selectionRect.bottom
    );
    const id = card.dataset.matId!;
    if (intersecting) {
      if (selectionStartSelected.value.has(id)) newSelected.delete(id);
      else newSelected.add(id);
    }
  });
  selectedMaterialIds.value = [...newSelected];
};

const updateSelectionMove = (event: MouseEvent) => {
  if (!isSelecting.value || !gridContainer.value) return;
  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.endX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.endY =
    event.clientY - rect.top + gridContainer.value.scrollTop;
  updateSelectedCards();
};

const endSelectionMove = () => {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelectionMove);
  document.removeEventListener('mouseup', endSelectionMove);
};

const startSelection = (event: MouseEvent) => {
  if (isPreviewMode.value) return;
  const target = event.target as HTMLElement;
  const isInteractive =
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'BUTTON' ||
    target.isContentEditable ||
    !!target.closest(
      'input, textarea, button, .ant-checkbox, .ant-select, .area-box',
    );
  if (isInteractive) return;
  if (!gridContainer.value) return;
  isSelecting.value = true;
  selectionStartSelected.value = new Set<string>(selectedMaterialIds.value);
  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.startX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.startY =
    event.clientY - rect.top + gridContainer.value.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;
  document.addEventListener('mousemove', updateSelectionMove);
  document.addEventListener('mouseup', endSelectionMove);
  event.preventDefault();
};

onUnmounted(() => {
  document.removeEventListener('mousemove', updateSelectionMove);
  document.removeEventListener('mouseup', endSelectionMove);
});

const handleMaterialTemplateApply = (templateData: any) => {
  if (templateData.batchTitle !== undefined)
    batchTitle.value = templateData.batchTitle;
  if (templateData.batchDescription !== undefined)
    batchBody.value = templateData.batchDescription;
  if (templateData.batchCallToAction !== undefined)
    batchCTA.value = templateData.batchCallToAction;
  message.success('模板应用成功');
};

async function handleSaveTemplate(templateName: string, description: string) {
  try {
    const realName =
      (userStore.userInfo as any)?.realName ||
      (userStore.userInfo as any)?.full_name ||
      '';
    const data = {
      batchCallToAction: batchCTA.value,
      batchDescription: batchBody.value,
      batchTitle: batchTitle.value,
      description,
      name: templateName,
      real_name: realName,
    };
    if (currentMaterialTemplateId.value) {
      await updateMaterialTemplate(currentMaterialTemplateId.value, data);
      currentMaterialTemplateName.value = templateName;
      message.success('模板更新成功');
    } else {
      const res: any = await createMaterialTemplate(data);
      const resData = res?.data || res;
      if (resData?.id) {
        currentMaterialTemplateId.value = resData.id;
        currentMaterialTemplateName.value = templateName;
      }
      message.success('模板保存成功');
    }
    showTemplateSaveModal.value = false;
  } catch {
    message.error('保存模板失败');
  }
}

const applyBatch = () => {
  const targets =
    selectedMaterialIds.value.length > 0
      ? new Set(selectedMaterialIds.value)
      : null;
  materials.value.forEach((m) => {
    if (!targets || targets.has(m.id || m.materialId)) {
      if (batchTitle.value) m.title = batchTitle.value;
      if (batchBody.value) m.description = batchBody.value;
      if (batchCTA.value) m.callToAction = batchCTA.value;
    }
  });
  message.success('批量应用成功');
};

async function handleMaterialGroupApply(
  groupId: string,
  mode: 'append' | 'replace',
) {
  try {
    const response: any = await applyMaterialGroup(groupId, mode);
    const rd = response?.data || response;
    const groupMaterials: any[] = rd?.materials || [];
    if (groupMaterials.length === 0) {
      message.warning('该素材组没有可用的素材');
      materialGroupLoadTabRef.value?.finishApply();
      return;
    }
    const materialIds = groupMaterials.map((m: any) => m.material_id);
    let fullData: any[] = [];
    try {
      const res: any = await getMaterialsByIds({ ids: materialIds });
      const resData = res?.data || res;
      if (Array.isArray(resData)) fullData = resData;
      else if (Array.isArray(resData?.items)) fullData = resData.items;
    } catch {}
    const dataMap = new Map(fullData.map((m: any) => [m._id || m.id, m]));
    const newMats: MaterialItem[] = groupMaterials.map((m: any) => {
      const full = dataMap.get(m.material_id) || {};
      return {
        callToAction: m.call_to_action,
        description: m.body,
        filename: full.basename || full.filename || '',
        filetype: full.filetype || 'image',
        id: m.material_id,
        materialId: m.material_id,
        name: full.basename || full.name || `素材_${m.material_id.slice(0, 8)}`,
        title: m.title,
        unique_name: full.unique_name || '',
        uploadTime: full.upload_time || '',
      } as MaterialItem;
    });
    if (mode === 'replace') {
      materials.value = newMats;
    } else {
      const existing = new Set(
        materials.value.map((m) => m.id || m.materialId),
      );
      newMats.forEach((m) => {
        if (existing.has(m.id)) {
          const mat = materials.value.find(
            (x) => (x.id || x.materialId) === m.id,
          );
          if (mat) {
            mat.title = m.title;
            mat.description = m.description;
            mat.callToAction = m.callToAction;
          }
        } else {
          materials.value.push(m);
        }
      });
    }
    loadMaterialImages(materials.value);
    message.success('素材组应用成功');
  } catch {
    message.error('应用素材组失败');
  } finally {
    materialGroupLoadTabRef.value?.finishApply();
  }
}

async function handleSaveMaterialGroup(
  data: { description: string; name: string },
  action: 'create' | 'update',
) {
  try {
    const mats = materials.value.map((m) => ({
      body: m.description || '',
      call_to_action: m.callToAction,
      material_id: m.materialId || m.id,
      title: m.title || '',
    }));
    if (action === 'update' && currentMaterialGroupId.value) {
      await updateMaterialGroup(currentMaterialGroupId.value, {
        ...data,
        materials: mats,
      });
      currentMaterialGroupName.value = data.name;
      message.success('素材组更新成功');
    } else {
      const res: any = await createMaterialGroup({ ...data, materials: mats });
      const resData = res?.data || res;
      if (resData?.id) {
        currentMaterialGroupId.value = resData.id;
        currentMaterialGroupName.value = data.name;
        currentMaterialGroupDescription.value = data.description;
      }
      message.success('素材组保存成功');
    }
    showMaterialGroupSaveModal.value = false;
    materialGroupLoadTabRef.value?.refresh();
  } catch {
    message.error('保存素材组失败');
  }
}

const buildAdConfig = (pad: PendingAd) => {
  const mat = materials.value.find(
    (m) => (m.id || m.materialId) === pad.materialId,
  );
  return {
    name: pad.name,
    status: 'ACTIVE',
    creative: {
      type: mat?.filetype || 'image',
      path: mat?.unique_name || mat?.filename || '',
      picture: pad.img || '',
      title: pad.title,
      body: pad.body,
      description: pad.body,
      ...(pad.callToAction
        ? { call_to_action: { type: pad.callToAction } }
        : {}),
    },
    contextual_multi_ads: { enroll_status: 'OPT_IN' },
  };
};

const handleSubmit = async () => {
  // 校验:每张待提交广告卡都要选好主页
  for (const account of treeData.value) {
    for (const camp of account.campaigns) {
      for (const adset of camp.adsets) {
        const missing = adset.pendingAds.find((pad) => !pad.pageId);
        if (missing) {
          message.warning(
            `广告组 ${adset.adset_name} 中"${missing.name}"未选择主页`,
          );
          return;
        }
      }
    }
  }

  const requests = treeData.value
    .map((account) => {
      const operations: Array<{
        ads: ReturnType<typeof buildAdConfig>[];
        adset_id: string;
        adset_name: string;
        campaign_name: string;
        page_id: string;
      }> = [];
      account.campaigns.forEach((camp) =>
        camp.adsets.forEach((adset) => {
          if (adset.pendingAds.length === 0) return;
          // 同一 adset 下按 pageId 分桶,每桶产出一条 operation
          const byPage = new Map<string, PendingAd[]>();
          for (const pad of adset.pendingAds) {
            const key = pad.pageId;
            if (!byPage.has(key)) byPage.set(key, []);
            byPage.get(key)!.push(pad);
          }
          for (const [pageId, pads] of byPage) {
            operations.push({
              adset_id: adset.adset_id,
              campaign_name: camp.campaign_name,
              adset_name: adset.adset_name,
              page_id: pageId,
              ads: pads.map(buildAdConfig),
            });
          }
        }),
      );
      const selectedDev = account.developers.find(
        (d) => d.id === account.selectedDevId,
      );
      // 请求级 page_id 取首个 op 的主页作兜底(后端要求必填)。
      const fallbackPageId = operations[0]?.page_id ?? '';
      return {
        account_id: account.account_id,
        page_id: fallbackPageId,
        link_url: account.link_url,
        object_type: selectedDev?.type,
        personal_id: account.selectedDevId,
        operations,
      };
    })
    .filter((req) => req.operations.length > 0);

  if (requests.length === 0 && pendingDeleteAds.value.length === 0) {
    message.warning('没有待提交的广告');
    return;
  }
  loading.value = true;
  try {
    if (pendingDeleteAds.value.length > 0) {
      const accountById = new Map(treeData.value.map((a) => [a.account_id, a]));
      const byAccount = new Map<string, Array<{ id: string; name: string }>>();
      for (const ad of pendingDeleteAds.value) {
        if (!byAccount.has(ad.account_id)) byAccount.set(ad.account_id, []);
        byAccount.get(ad.account_id)!.push({ id: ad.id, name: ad.name });
      }
      await Promise.all(
        [...byAccount.entries()].map(([accId, ads]) => {
          const acc = accountById.get(accId);
          const devId = acc?.selectedDevId ?? '';
          const dev = acc?.developers.find((d) => d.id === devId);
          return deleteAds({
            ads,
            object_type: dev?.type,
            personal_id: devId || undefined,
          });
        }),
      );
    }
    if (requests.length > 0) {
      const results = await Promise.all(requests.map((req) => createAds(req)));
      const tips = (results as any[])
        .map((r) => (typeof r === 'string' ? r : r?.data || r?.message))
        .filter(Boolean)
        .join('；');
      message.success(tips || '广告提交成功');
    } else {
      message.success('操作成功');
    }
    emit('update:open', false);
  } catch {
  } finally {
    loading.value = false;
  }
};

async function handleReuseCreativeHistory(
  historyId: string,
  mode: 'append' | 'replace',
) {
  try {
    const res: any = await reuseCreativeHistory(historyId);
    const rd = res?.data || res;
    const creatives: any[] = rd?.creatives || [];
    const newMats: MaterialItem[] = creatives.map(
      (c: any) =>
        ({
          callToAction: c.call_to_action?.type || c.callToAction || null,
          description: c.body || c.description || '',
          filename: c.filename || c.path || '',
          filetype: c.filetype || c.type || 'image',
          id: c.material_id || c.id || `hist_${Date.now()}`,
          img: c.img || c.picture || '',
          materialId: c.material_id || c.id || '',
          name: c.name || c.filename || '',
          title: c.title || '',
          unique_name: c.unique_name || '',
          uploadTime: '',
        }) as MaterialItem,
    );
    if (mode === 'replace') {
      materials.value = newMats;
    } else {
      const existing = new Set(
        materials.value.map((m) => m.id || m.materialId),
      );
      newMats.forEach((m) => {
        if (existing.has(m.id)) {
          const mat = materials.value.find(
            (x) => (x.id || x.materialId) === m.id,
          );
          if (mat) {
            mat.title = m.title;
            mat.description = m.description;
            mat.callToAction = m.callToAction;
          }
        } else {
          materials.value.push(m);
        }
      });
    }
  } catch {
    message.error('复用创意历史失败');
  }
}
</script>

<template>
  <Drawer
    :open="open"
    placement="right"
    width="88%"
    :footer="null"
    title="操作广告"
    root-class-name="supplementary-drawer"
    @close="emit('update:open', false)"
  >
    <template #extra>
      <Button
        type="primary"
        :disabled="pendingAdsCount === 0 && pendingDeleteAds.length === 0"
        @click="handleSubmit"
      >
        提交
      </Button>
    </template>
    <Spin :spinning="loading" class="supp-spin-wrap">
      <div
        v-if="treeData.length === 0"
        class="flex h-full items-center justify-center"
      >
        <Empty v-if="!loading" description="暂无数据，请重新选择！" />
      </div>
      <div
        v-if="treeData.length > 0"
        class="flex min-h-0 flex-1 gap-4 overflow-hidden p-4"
      >
        <!-- 左侧：投放树 -->
        <div
          class="flex w-[540px] flex-none flex-col self-stretch overflow-hidden rounded-lg border border-gray-200 bg-gray-50 p-3"
        >
          <!-- <div class="mb-3 flex flex-shrink-0 items-center justify-between">
            <span class="text-sm font-semibold text-gray-700">投放树</span>
          </div> -->

          <div class="flex-1 space-y-2 overflow-y-auto">
            <template v-for="account in treeData" :key="account.account_id">
              <div
                class="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
              >
                <!-- 账户行 -->
                <div class="flex items-center gap-2 px-3 py-2">
                  <button
                    class="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                    @click="toggleExpand(account.account_id)"
                  >
                    <span class="w-3.5 flex-shrink-0 text-xs text-blue-400">
                      {{ expandedIds.has(account.account_id) ? '▼' : '▶' }}
                    </span>
                    <span
                      class="flex-shrink-0 rounded-full bg-purple-50 px-1.5 py-0.5 text-xs text-purple-600"
                      >户</span
                    >
                    <span
                      class="min-w-0 flex-1 truncate text-xs font-semibold"
                      >{{ account.account_name }}</span
                    >
                  </button>
                  <Select
                    v-model:value="account.selectedDevId"
                    :options="
                      account.developers.map((o) => ({
                        label: o.name,
                        value: o.id,
                      }))
                    "
                    placeholder="开发者"
                    allow-clear
                    size="small"
                    style="width: 160px"
                    class="ml-auto shrink-0"
                    @change="onDevChange(account)"
                  />
                </div>

                <!-- campaigns -->
                <div
                  v-if="expandedIds.has(account.account_id)"
                  class="space-y-1 px-2 pb-2"
                >
                  <template
                    v-for="campaign in account.campaigns"
                    :key="campaign.campaign_id"
                  >
                    <div
                      class="overflow-hidden rounded-lg border border-gray-100 bg-gray-50"
                    >
                      <button
                        class="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left hover:bg-gray-100"
                        @click="toggleExpand(campaign.campaign_id)"
                      >
                        <span class="w-3.5 flex-shrink-0 text-xs text-blue-400">
                          {{
                            expandedIds.has(campaign.campaign_id) ? '▼' : '▶'
                          }}
                        </span>
                        <span
                          class="flex-shrink-0 rounded-full bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600"
                          >系列</span
                        >
                        <Tooltip
                          :title="campaign.campaign_name"
                          placement="topLeft"
                        >
                          <span
                            class="min-w-0 flex-1 truncate text-xs font-medium"
                            >{{ campaign.campaign_name }}</span
                          >
                        </Tooltip>
                      </button>

                      <!-- adsets 两列布局 -->
                      <div
                        v-if="expandedIds.has(campaign.campaign_id)"
                        class="grid grid-cols-2 gap-1 px-1.5 pb-1.5"
                      >
                        <template
                          v-for="adset in campaign.adsets"
                          :key="adset.adset_id"
                        >
                          <div
                            class="overflow-hidden rounded-lg border border-gray-200 bg-white"
                          >
                            <div
                              class="flex w-full items-center gap-1 px-2 py-1.5 hover:bg-gray-50"
                            >
                              <span
                                class="flex-shrink-0 rounded-full bg-green-50 px-1 py-0.5 text-xs text-green-600"
                                >组</span
                              >
                              <Tooltip
                                :title="adset.adset_name"
                                placement="topLeft"
                              >
                                <span
                                  class="min-w-0 flex-1 truncate text-xs font-medium"
                                  >{{ adset.adset_name }}</span
                                >
                              </Tooltip>
                            </div>

                            <!-- 拖拽落点（包住所有广告内容） -->
                            <div
                              v-if="expandedIds.has(adset.adset_id)"
                              class="rounded-b-lg border border-dashed p-1.5 transition-colors"
                              :class="
                                overZoneId === adset.adset_id
                                  ? 'border-orange-400 bg-orange-50'
                                  : 'border-blue-200 bg-blue-50/30'
                              "
                              @dragover="onDragOver($event, adset.adset_id)"
                              @dragleave="onDragLeave($event, adset.adset_id)"
                              @drop="onDrop($event, adset, account)"
                            >
                              <!-- 空状态提示 -->
                              <div
                                v-if="
                                  adset.pendingAds.length === 0 &&
                                  adset.ads.length === 0
                                "
                                class="py-1.5 text-center text-xs text-gray-400"
                              >
                                拖拽右侧素材到此处
                              </div>

                              <!-- 广告 -->
                              <div
                                v-if="
                                  adset.pendingAds.length > 0 ||
                                  adset.ads.length > 0
                                "
                                class="grid grid-cols-2 gap-1"
                              >
                                <div
                                  v-for="pad in adset.pendingAds"
                                  :key="pad.uid"
                                  class="flex flex-col overflow-hidden rounded-md border border-orange-200 bg-orange-50"
                                >
                                  <div class="flex items-center gap-1.5 pr-1">
                                    <Image
                                      v-if="pad.img"
                                      :src="pad.img"
                                      :width="30"
                                      :height="30"
                                      :preview="true"
                                      class="block flex-shrink-0 cursor-zoom-in rounded-l-md object-cover"
                                      @click.stop
                                    >
                                      <template #previewMask>
                                        <span
                                          class="icon-[ant-design--eye-outlined] text-sm"
                                        ></span>
                                      </template>
                                    </Image>
                                    <div
                                      v-else
                                      class="h-[30px] w-[30px] flex-shrink-0 rounded-l-md"
                                      style="
                                        background: linear-gradient(
                                          140deg,
                                          #f0a875,
                                          #dd8a63
                                        );
                                      "
                                    ></div>
                                    <Tooltip
                                      :title="pad.name"
                                      placement="topLeft"
                                    >
                                      <span
                                        class="min-w-0 flex-1 truncate text-xs font-medium text-orange-700"
                                        >{{ pad.name }}</span
                                      >
                                    </Tooltip>
                                    <button
                                      class="flex-shrink-0 text-gray-300 hover:text-red-500"
                                      @click="removePendingAd(adset, pad.uid)"
                                    >
                                      <span
                                        class="icon-[ant-design--close-outlined] text-[10px]"
                                      ></span>
                                    </button>
                                  </div>
                                  <Select
                                    v-model:value="pad.pageId"
                                    placeholder="选择主页"
                                    class="m-1 mt-0"
                                    show-search
                                    allow-clear
                                    option-label-prop="label"
                                    popup-class-name="page-picker-popup"
                                    :dropdown-match-select-width="false"
                                    :dropdown-style="{ minWidth: '260px' }"
                                    :filter-option="pageFilterOption"
                                  >
                                    <Select.Option
                                      v-for="p in adset.page_options.filter(
                                        (p) =>
                                          !account.selectedDevId ||
                                          p.developer_ids.includes(
                                            account.selectedDevId,
                                          ),
                                      )"
                                      :key="p.id"
                                      :value="p.id"
                                      :label="p.name || p.id"
                                    >
                                      <span class="flex items-center gap-2">
                                        <img
                                          v-if="p.picture"
                                          alt=""
                                          :src="p.picture"
                                          class="h-6 w-6 flex-shrink-0 rounded-full bg-gray-100 object-cover"
                                        />
                                        <span
                                          v-else
                                          class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-gray-100 text-[10px] text-gray-500"
                                          >{{
                                            (p.name || p.id).slice(0, 1)
                                          }}</span
                                        >
                                        <span
                                          class="min-w-0 flex-1 truncate text-[13px]"
                                          >{{ p.name || p.id }}</span
                                        >
                                      </span>
                                    </Select.Option>
                                  </Select>
                                </div>
                                <div
                                  v-for="ad in adset.ads"
                                  :key="ad.ad_id"
                                  class="flex items-center gap-1.5 overflow-hidden rounded-md border border-gray-200 bg-white pr-1"
                                >
                                  <Image
                                    v-if="ad.thumbnail"
                                    :src="
                                      ad.thumbnail.startsWith('http') ||
                                      ad.thumbnail.startsWith('data:')
                                        ? ad.thumbnail
                                        : `data:image/jpeg;base64,${ad.thumbnail}`
                                    "
                                    :width="30"
                                    :height="30"
                                    :preview="true"
                                    class="block flex-shrink-0 cursor-zoom-in rounded-l-md object-cover"
                                    @click.stop
                                  >
                                    <template #previewMask>
                                      <span
                                        class="icon-[ant-design--eye-outlined] text-sm"
                                      ></span>
                                    </template>
                                  </Image>
                                  <div
                                    v-else
                                    class="h-[30px] w-[30px] flex-shrink-0 rounded-l-md"
                                    style="
                                      background: linear-gradient(
                                        140deg,
                                        #c8d3e0,
                                        #8b9dc3
                                      );
                                    "
                                  ></div>
                                  <Tooltip
                                    :title="ad.ad_name"
                                    placement="topLeft"
                                  >
                                    <span
                                      class="min-w-0 flex-1 truncate text-xs text-gray-500"
                                      >{{ ad.ad_name }}</span
                                    >
                                  </Tooltip>
                                  <Popconfirm
                                    title="确认删除该广告？"
                                    ok-text="删除"
                                    cancel-text="取消"
                                    placement="top"
                                    @confirm="
                                      removeExistingAd(
                                        adset,
                                        ad.ad_id,
                                        account.account_id,
                                      )
                                    "
                                  >
                                    <button
                                      class="flex-shrink-0 text-gray-300 hover:text-red-500"
                                    >
                                      <span
                                        class="icon-[ant-design--close-outlined] text-[10px]"
                                      ></span>
                                    </button>
                                  </Popconfirm>
                                </div>
                              </div>
                            </div>
                          </div>
                        </template>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </template>
          </div>
          <span class="mt-2 text-xs text-gray-400"
            >共 {{ pendingAdsCount }} 条待提交广告</span
          >
        </div>

        <!-- 右侧：素材配置面板 -->
        <div
          class="supplement-load-tab-wrap flex min-w-0 flex-1 flex-col gap-2"
        >
          <!-- 素材操作栏 -->
          <div
            class="flex flex-wrap items-center gap-1.5 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2"
          >
            <Button
              class="rounded-md"
              type="primary"
              @click="showMaterialModal = true"
            >
              添加广告
            </Button>
            <Button
              class="rounded-md"
              type="primary"
              @click="showAdCreativeModal = true"
            >
              临时素材
            </Button>
            <Button
              danger
              :disabled="selectedMaterialIds.length === 0"
              @click="deleteSelectedMaterials"
            >
              删除{{
                selectedMaterialIds.length > 0
                  ? `(${selectedMaterialIds.length})`
                  : ''
              }}
            </Button>
            <Button
              :disabled="materials.length === 0"
              @click="showMaterialGroupSaveModal = true"
            >
              保存素材组
            </Button>
            <div class="supplement-load-tab-wrap">
              <MaterialGroupLoadTab
                ref="materialGroupLoadTabRef"
                :has-current-materials="materials.length > 0"
                @apply="handleMaterialGroupApply"
                @history="showCreativeHistoryModal = true"
              />
            </div>
            <Tooltip title="查看并复用创意历史配置">
              <Button @click="showCreativeHistoryModal = true">
                创意历史
              </Button>
            </Tooltip>
          </div>

          <!-- 批量设置 + 模板 -->
          <div
            class="flex flex-wrap items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2"
          >
            <Button @click="showTemplateSaveModal = true">
              <span class="icon-[ant-design--file-text-outlined] mr-1"></span
              >保存模板
            </Button>
            <div class="supplement-load-tab-wrap">
              <MaterialTemplateLoadTab
                :user-options="operatorOptions"
                @apply="handleMaterialTemplateApply"
              />
            </div>
            <div class="mx-1 h-4 w-px bg-gray-200"></div>
            <span class="flex-shrink-0 text-gray-600">广告正文:</span>
            <Textarea
              v-model:value="batchBody"
              :auto-size="{ minRows: 1, maxRows: 2 }"
              placeholder="批量设置正文"
              class="w-[180px]"
            />
            <span class="flex-shrink-0 text-gray-600">广告标题:</span>
            <Textarea
              v-model:value="batchTitle"
              :auto-size="{ minRows: 1, maxRows: 2 }"
              placeholder="批量设置标题"
              class="w-[150px]"
            />
            <span class="flex-shrink-0 text-gray-600">行动号召:</span>
            <Select
              v-model:value="batchCTA"
              placeholder="选择行动号召"
              allow-clear
              class="w-[130px]"
              :options="callToActionOptions"
            />
            <Button type="primary" @click="applyBatch">
              批量应用{{
                selectedMaterialIds.length > 0
                  ? `(${selectedMaterialIds.length})`
                  : ''
              }}
            </Button>
          </div>

          <!-- 素材网格 -->
          <div class="flex items-center justify-between px-1">
            <div class="flex items-center gap-1.5">
              <span class="text-xs text-gray-400">
                {{
                  materials.length > 0 ? `共 ${materials.length} 个素材` : ''
                }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <Tooltip>
                <template #title>
                  <div v-if="!isPreviewMode">
                    选择模式：拖拽框选或勾选素材，再次框选可取消
                  </div>
                  <div v-else>预览模式：拖拽素材缩略图到左侧广告组</div>
                </template>
                <Switch
                  :checked="!isPreviewMode"
                  checked-children="选择"
                  un-checked-children="预览"
                  @change="
                    (v) => {
                      isPreviewMode = !v;
                      isSelecting = false;
                    }
                  "
                />
              </Tooltip>
              <Button.Group v-if="materials.length > 0">
                <Button @click="selectAllMaterials">全选</Button>
                <Button @click="invertSelection">反选</Button>
                <Button
                  :disabled="selectedMaterialIds.length === 0"
                  @click="clearAllMaterials"
                >
                  清空勾选
                </Button>
              </Button.Group>
            </div>
          </div>

          <!-- 素材网格 -->
          <div class="relative flex-1 overflow-y-auto">
            <div
              v-if="materials.length === 0"
              class="flex h-32 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400"
            >
              点击"添加广告"或“临时素材”选择素材，然后拖拽缩略图到左侧广告组
            </div>
            <div
              v-else
              ref="gridContainer"
              class="grid grid-cols-6 gap-2"
              :class="{
                'select-none': !isPreviewMode,
                'cursor-crosshair': isSelecting && !isPreviewMode,
                'border-2 border-dashed border-blue-200': !isPreviewMode,
              }"
              @mousedown="startSelection"
            >
              <!-- 框选视觉效果 -->
              <div
                v-if="isSelecting"
                class="pointer-events-none absolute z-10 rounded-sm border-2 border-blue-400 bg-blue-100/20"
                :style="{
                  left: `${Math.min(selectionBox.startX, selectionBox.endX)}px`,
                  top: `${Math.min(selectionBox.startY, selectionBox.endY)}px`,
                  width: `${Math.abs(selectionBox.endX - selectionBox.startX)}px`,
                  height: `${Math.abs(selectionBox.endY - selectionBox.startY)}px`,
                }"
              ></div>
              <div
                v-for="mat in materials"
                :key="mat.id || mat.materialId"
                :data-mat-id="mat.id || mat.materialId"
                class="overflow-hidden rounded-xl border bg-white shadow-sm transition-shadow hover:shadow-md"
                :class="
                  selectedMaterialIds.includes(mat.id || mat.materialId)
                    ? 'border-blue-400 ring-2 ring-blue-200'
                    : 'border-gray-200'
                "
              >
                <!-- 缩略图（预览模式拖拽，选择模式不可拖） -->
                <div
                  class="relative h-[120px] bg-gray-100"
                  :class="
                    isPreviewMode
                      ? 'cursor-grab active:cursor-grabbing'
                      : 'cursor-default'
                  "
                  :draggable="isPreviewMode"
                  @dragstart="isPreviewMode && onMaterialDragStart($event, mat)"
                >
                  <img
                    v-if="getMatImg(mat)"
                    alt="素材预览"
                    :src="getMatImg(mat)"
                    class="h-full w-full object-cover"
                  />
                  <div
                    v-else
                    class="flex h-full items-center justify-center text-sm font-medium text-white"
                    style="
                      background: linear-gradient(
                        140deg,
                        #8b9dc3,
                        rgb(36 29 23 / 35%)
                      );
                    "
                  >
                    {{ mat.filetype === 'video' ? '视频' : '图片' }}
                  </div>
                  <div
                    class="absolute left-1.5 top-1.5"
                    @click.stop
                    @mousedown.stop
                  >
                    <Checkbox
                      class="mat-cb-sm"
                      :checked="
                        selectedMaterialIds.includes(mat.id || mat.materialId)
                      "
                      @change="toggleMaterialSelect(mat.id || mat.materialId)"
                    />
                  </div>
                  <div
                    class="absolute right-1.5 top-1.5 rounded bg-black/40 px-1 py-0.5 text-xs text-white"
                  >
                    {{ mat.filetype === 'video' ? '视频' : '图片' }}
                  </div>
                  <div
                    class="absolute inset-x-0 bottom-0 bg-black/40 px-1.5 py-0.5"
                  >
                    <div
                      class="truncate text-center text-xs text-white/90"
                      :title="mat.basename || mat.filename"
                    >
                      {{ mat.basename || mat.filename }}
                    </div>
                  </div>
                </div>

                <!-- 编辑区域 -->
                <div class="area-box space-y-1.5 p-2">
                  <Textarea
                    v-model:value="mat.description"
                    :auto-size="{ minRows: 1, maxRows: 2 }"
                    class="text-[13px]"
                    placeholder="广告正文"
                  />
                  <Textarea
                    v-model:value="mat.title"
                    :auto-size="{ minRows: 1, maxRows: 2 }"
                    class="text-[13px]"
                    placeholder="广告标题"
                  />
                  <Select
                    :value="mat.callToAction || undefined"
                    placeholder="行动号召"
                    class="w-full text-[13px]"
                    allow-clear
                    :options="callToActionOptions"
                    @change="(v) => setMatCTA(mat, v)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Spin>

    <MaterialSelectionModal
      :open="showMaterialModal"
      :operator-options="operatorOptions"
      :uploaded-material-ids="uploadedMaterialIds"
      @update:open="showMaterialModal = $event"
      @confirm="handleMaterialConfirm"
    />

    <AdCreativeSelectionModal
      :open="showAdCreativeModal"
      :selected-ids="uploadedMaterialIds"
      @update:open="showAdCreativeModal = $event"
      @confirm="handleAdCreativeConfirm"
    />

    <MaterialGroupSaveModal
      :visible="showMaterialGroupSaveModal"
      :materials-count="materials.length"
      :current-group-id="currentMaterialGroupId || undefined"
      :current-group-name="currentMaterialGroupName"
      :current-group-description="currentMaterialGroupDescription"
      @cancel="showMaterialGroupSaveModal = false"
      @confirm="handleSaveMaterialGroup"
    />

    <CreativeHistoryModal
      :visible="showCreativeHistoryModal"
      :has-current-materials="materials.length > 0"
      @update:visible="showCreativeHistoryModal = $event"
      @reuse="handleReuseCreativeHistory"
    />

    <TemplateSaveModal
      :open="showTemplateSaveModal"
      title="保存正文标题模板"
      :initial-name="currentMaterialTemplateName"
      @confirm="handleSaveTemplate"
      @update:open="showTemplateSaveModal = $event"
    />
  </Drawer>
</template>

<style scoped></style>

<style></style>
