import type {
  DeliveryRecordStatus,
  DeliverySourceAdSet,
  DeliverySourceCampaign,
  DeliverySourceQuery,
} from '#/domain/task-delivery/types';

import { isFusionDemoMode } from '#/api';
import { backendClient } from '#/api/request';

/** @deprecated Import task-delivery source types from the domain instead. */
export type DeliveryCenterRecordStatus = DeliveryRecordStatus;
/** @deprecated Import task-delivery source types from the domain instead. */
export type DeliveryCenterAdSetOption = DeliverySourceAdSet;
/** @deprecated Import task-delivery source types from the domain instead. */
export type DeliveryCenterCampaignOption = DeliverySourceCampaign;

const demoCampaigns: DeliveryCenterCampaignOption[] = [
  {
    accountId: 'tt-jp-pixel-042',
    accountName: 'Pixel Quest · TikTok 日本首发',
    adSets: [
      {
        adCount: 6,
        ads: [
          {
            id: 'AD-TT-PQ-UGC-01A',
            name: 'UGC 开箱 · 15 秒',
            status: 'active',
          },
          {
            id: 'AD-TT-PQ-UGC-01B',
            name: 'UGC 玩法展示 · 20 秒',
            status: 'active',
          },
        ],
        dailyBudget: 220_000,
        id: 'AS-TT-PQ-UGC-01',
        name: 'UGC 高互动人群 · 18-34',
        status: 'active',
      },
      {
        adCount: 8,
        ads: [
          {
            id: 'AD-TT-PQ-LAL-02A',
            name: '付费用户相似 · 竖版 A',
            status: 'active',
          },
          {
            id: 'AD-TT-PQ-LAL-02B',
            name: '付费用户相似 · 竖版 B',
            status: 'active',
          },
        ],
        dailyBudget: 300_000,
        id: 'AS-TT-PQ-LAL-02',
        name: '付费用户相似人群 · 3%',
        status: 'active',
      },
      {
        adCount: 4,
        ads: [
          { id: 'AD-TT-PQ-RTG-03A', name: '再营销 · 版本 A', status: 'active' },
        ],
        dailyBudget: 160_000,
        id: 'AS-TT-PQ-RTG-03',
        name: '落地页访问再营销 · 14 天',
        status: 'active',
      },
    ],
    agencyLineId: 'agency-orbit-tiktok-sea',
    agencyLineName: 'Orbit-TikTok-SEA',
    currency: 'JPY',
    dataCutoffAt: '2026-08-11 16:30',
    dailyBudget: 680_000,
    id: '1837420194550017',
    materialVersion: 'MAT-PQ-JP-20260811-v3',
    name: 'Pixel Quest 日本首发 · 二次扩量',
    platform: 'TikTok',
    projectId: 'project-pixel',
    projectName: 'Pixel Quest 日本首发',
    startedAt: '2026-08-11 09:30',
    status: 'active',
    syncedAt: '2026-08-11 16:42',
  },
  {
    accountId: 'tt-jp-pixel-042',
    accountName: 'Pixel Quest · TikTok 日本首发',
    adSets: [
      {
        adCount: 4,
        ads: [
          {
            id: 'AD-TT-PQ-CREATIVE-04A',
            name: '首轮创意复测 · 竖版',
            status: 'paused',
          },
        ],
        dailyBudget: 120_000,
        id: 'AS-TT-PQ-CREATIVE-04',
        name: '首轮创意复测 · 女性 25-44',
        status: 'paused',
      },
    ],
    agencyLineId: 'agency-orbit-tiktok-sea',
    agencyLineName: 'Orbit-TikTok-SEA',
    currency: 'JPY',
    dataCutoffAt: '2026-08-11 16:20',
    dailyBudget: 120_000,
    id: '1837420194550198',
    materialVersion: 'MAT-PQ-JP-20260810-v2',
    name: 'Pixel Quest 日本首发 · 首轮复测',
    platform: 'TikTok',
    projectId: 'project-pixel',
    projectName: 'Pixel Quest 日本首发',
    startedAt: '2026-08-10 11:00',
    status: 'paused',
    syncedAt: '2026-08-11 16:39',
  },
  {
    accountId: 'act-starfall-us-008',
    accountName: 'Starfall · Meta 美国增长',
    adSets: [
      {
        adCount: 12,
        ads: [
          {
            id: 'AD-META-SF-BROAD-01A',
            name: 'Broad · UGC 版本 A',
            status: 'active',
          },
          {
            id: 'AD-META-SF-BROAD-01B',
            name: 'Broad · 静态图版本 B',
            status: 'active',
          },
        ],
        dailyBudget: 5400,
        id: 'AS-META-SF-BROAD-01',
        name: '美国广泛受众 · Advantage+',
        status: 'active',
      },
      {
        adCount: 8,
        ads: [
          {
            id: 'AD-META-SF-LAL-02A',
            name: 'LAL · 视频版本 A',
            status: 'active',
          },
        ],
        dailyBudget: 3600,
        id: 'AS-META-SF-LAL-02',
        name: '高价值付费用户相似人群',
        status: 'active',
      },
    ],
    agencyLineId: 'agency-starfall-fb-id',
    agencyLineName: 'Starfall-FB-ID',
    currency: 'USD',
    dataCutoffAt: '2026-08-11 16:40',
    dailyBudget: 9000,
    id: 'CMP-META-SF-US-240811',
    materialVersion: 'MAT-SF-US-20260811-v5',
    name: 'Starfall 美国暑期扩量 · 第二阶段',
    platform: 'Facebook',
    projectId: 'project-starfall',
    projectName: 'Starfall 全球增长',
    startedAt: '2026-08-11 08:00',
    status: 'active',
    syncedAt: '2026-08-11 16:45',
  },
  {
    accountId: 'act-ark-us-014',
    accountName: 'Project Ark · Google 美国市场',
    adSets: [
      {
        adCount: 10,
        ads: [
          {
            id: 'AD-GGL-ARK-PMAX-01A',
            name: 'PMax · 图片变体 A',
            status: 'partial',
          },
        ],
        dailyBudget: 4800,
        id: 'AS-GGL-ARK-PMAX-01',
        name: 'PMax · 商店节日主题素材',
        status: 'partial',
      },
    ],
    agencyLineId: 'agency-starfall-google-us',
    agencyLineName: 'Starfall-Google-US',
    currency: 'USD',
    dataCutoffAt: '2026-08-11 16:25',
    dailyBudget: 4800,
    id: 'CMP-GGL-ARK-US-240810',
    materialVersion: 'MAT-ARK-US-20260810-v2',
    name: 'Project Ark 美国市场 · 节日主题验证',
    platform: 'Google',
    projectId: 'project-ark',
    projectName: 'Project Ark 美国市场',
    startedAt: '2026-08-10 16:00',
    status: 'partial',
    syncedAt: '2026-08-11 16:31',
  },
];

export async function getDeliveryCenterCampaignOptionsApi(
  params?: DeliverySourceQuery,
) {
  if (isFusionDemoMode()) {
    const keyword = params?.projectName?.trim().toLowerCase();
    return demoCampaigns
      .filter(
        (campaign) =>
          (!params?.projectId || campaign.projectId === params.projectId) &&
          (!keyword || campaign.projectName.toLowerCase().includes(keyword)),
      )
      .map((campaign) => ({
        ...campaign,
        adSets: campaign.adSets.map((adSet) => ({
          ...adSet,
          ads: adSet.ads.map((ad) => ({ ...ad })),
        })),
      }));
  }

  return backendClient.get<DeliveryCenterCampaignOption[]>(
    '/fusion/delivery/campaign-options',
    { params },
  );
}
