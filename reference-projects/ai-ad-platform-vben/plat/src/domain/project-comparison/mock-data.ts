import type {
  ProjectComparisonAgencyLineSource,
  ProjectComparisonCreativeDirectionSource,
  ProjectComparisonCreativeDirectionSourceRecord,
  ProjectComparisonSourceData,
  ProjectComparisonSourceRecord,
} from './types';

export const PROJECT_COMPARISON_DEMO_AS_OF = '2026-08-14T15:00:00+08:00';

interface ProjectScenario {
  agencyLines: ProjectComparisonAgencyLineSource[];
  dailySpend: number;
  projectId: string;
  serviceFeePercent: number;
}

interface CreativeDirectionProfile {
  assetType: ProjectComparisonCreativeDirectionSource['assetType'];
  conversionMultiplier: number;
  label: string;
  spendShare: number;
  suffix: string;
}

const creativeDirectionProfiles: readonly CreativeDirectionProfile[] = [
  {
    assetType: 'video',
    conversionMultiplier: 1.14,
    label: '前三秒冲突 · 竖版视频',
    spendShare: 0.56,
    suffix: 'hook-video',
  },
  {
    assetType: 'image',
    conversionMultiplier: 0.84,
    label: '核心卖点 · 静态图',
    spendShare: 0.44,
    suffix: 'benefit-image',
  },
];

const projectScenarios: readonly ProjectScenario[] = [
  {
    agencyLines: [
      {
        id: 'agency-starfall-fb-id',
        name: 'Starfall-FB-ID',
        platform: 'facebook',
      },
      {
        id: 'agency-starfall-google-us',
        name: 'Starfall-Google-US',
        platform: 'google',
      },
      {
        id: 'comparison-starfall-tiktok',
        name: 'Starfall-TikTok-Scale',
        platform: 'tiktok',
      },
    ],
    dailySpend: 11_400,
    projectId: 'project-starfall',
    serviceFeePercent: 12,
  },
  {
    agencyLines: [
      {
        id: 'comparison-ark-facebook',
        name: 'Ark-Facebook-Prospecting',
        platform: 'facebook',
      },
      {
        id: 'agency-starfall-google-us',
        name: 'Ark-Google-Search',
        platform: 'google',
      },
      {
        id: 'comparison-ark-remarketing',
        name: 'Ark-Remarketing',
        platform: 'facebook',
      },
    ],
    dailySpend: 6300,
    projectId: 'project-ark',
    serviceFeePercent: 10,
  },
  {
    agencyLines: [
      {
        id: 'agency-orbit-tiktok-sea',
        name: 'Orbit-TikTok-SEA',
        platform: 'tiktok',
      },
      {
        id: 'comparison-pixel-tiktok-ios',
        name: 'Pixel-TikTok-iOS',
        platform: 'tiktok',
      },
      {
        id: 'comparison-pixel-tiktok-android',
        name: 'Pixel-TikTok-Android',
        platform: 'tiktok',
      },
    ],
    dailySpend: 400_000,
    projectId: 'project-pixel',
    serviceFeePercent: 9,
  },
];

function formatDay(dayOffset: number) {
  const date = new Date(Date.UTC(2026, 6, 16 + dayOffset));
  return date.toISOString().slice(0, 10);
}

function hourlyWeight(hour: number) {
  const raw = hour >= 8 && hour <= 22 ? 1.15 : 0.72;
  return raw / 23.2;
}

function scenarioMultiplier(
  projectId: string,
  lineIndex: number,
  dayOffset: number,
) {
  const recent = dayOffset >= 27;
  if (projectId === 'project-starfall') {
    return recent ? 1.08 + lineIndex * 0.015 : 1 + lineIndex * 0.015;
  }
  if (projectId === 'project-ark') {
    return recent ? 1.12 + lineIndex * 0.01 : 1 + lineIndex * 0.01;
  }
  if (projectId === 'project-pixel') {
    return recent && lineIndex === 2 ? 1.18 : 1 + lineIndex * 0.025;
  }
  return 1;
}

function conversionMultiplier(
  projectId: string,
  lineIndex: number,
  dayOffset: number,
) {
  const recent = dayOffset >= 27;
  if (projectId === 'project-ark' && recent) return 0.8 - lineIndex * 0.015;
  if (projectId === 'project-pixel' && recent && lineIndex === 2) return 0.48;
  if (projectId === 'project-starfall' && recent)
    return 1.09 + lineIndex * 0.02;
  return 1 + lineIndex * 0.015;
}

function costMultiplier(
  projectId: string,
  lineIndex: number,
  dayOffset: number,
) {
  if (projectId === 'project-pixel' && lineIndex === 2 && dayOffset >= 27) {
    return 1.45;
  }
  return 1 + lineIndex * 0.04;
}

function makeRecord(
  scenario: ProjectScenario,
  lineIndex: number,
  dayOffset: number,
  hour: number,
): ProjectComparisonSourceRecord {
  const lineShare = [0.46, 0.33, 0.21][lineIndex] ?? 0.2;
  const wave =
    1 + (((dayOffset * 7 + hour * 3 + lineIndex * 11) % 9) - 4) * 0.012;
  const spend =
    scenario.dailySpend *
    lineShare *
    hourlyWeight(hour) *
    wave *
    scenarioMultiplier(scenario.projectId, lineIndex, dayOffset);
  const impressions = spend * (lineIndex === 1 ? 142 : 128);
  const clicks = impressions * (lineIndex === 1 ? 0.0175 : 0.019);
  const conversion = conversionMultiplier(
    scenario.projectId,
    lineIndex,
    dayOffset,
  );
  const registrations = clicks * (lineIndex === 2 ? 0.092 : 0.11) * conversion;
  const firstPurchases =
    registrations * (lineIndex === 1 ? 0.138 : 0.16) * conversion;
  const firstPurchaseRevenue =
    firstPurchases * (scenario.projectId === 'project-pixel' ? 14_000 : 85);
  const projectCost =
    spend * 0.072 * costMultiplier(scenario.projectId, lineIndex, dayOffset);

  const agencyLine = scenario.agencyLines[lineIndex];
  if (!agencyLine) throw new Error('代理线演示数据不完整');
  return {
    agencyLineId: agencyLine.id,
    clicks,
    day: formatDay(dayOffset),
    firstPurchaseRevenue,
    firstPurchases,
    hour,
    impressions,
    projectCost,
    registrations,
    spend,
  };
}

function buildCreativeDirections(scenario: ProjectScenario) {
  return scenario.agencyLines.flatMap((line, lineIndex) =>
    creativeDirectionProfiles.map((profile, profileIndex) => ({
      agencyLineId: line.id,
      assetType: profile.assetType,
      id: `creative-direction:${scenario.projectId}:${lineIndex}:${profile.suffix}`,
      materialVersionIds: [
        `material-version:${scenario.projectId}:${lineIndex}:${profileIndex}:v1`,
        `material-version:${scenario.projectId}:${lineIndex}:${profileIndex}:v2`,
      ],
      name: `${line.name} · ${profile.label}`,
      platform: line.platform,
    })),
  );
}

function makeCreativeDirectionRecord(
  record: ProjectComparisonSourceRecord,
  direction: ProjectComparisonCreativeDirectionSource,
  profile: CreativeDirectionProfile,
): ProjectComparisonCreativeDirectionSourceRecord {
  const share = profile.spendShare;
  const conversion = profile.conversionMultiplier;
  return {
    ...record,
    clicks: record.clicks * share,
    creativeDirectionId: direction.id,
    firstPurchaseRevenue: record.firstPurchaseRevenue * share * conversion,
    firstPurchases: record.firstPurchases * share * conversion,
    impressions: record.impressions * share,
    projectCost: record.projectCost * share,
    registrations: record.registrations * share * conversion,
    spend: record.spend * share,
  };
}

function buildProjectSourceData(
  scenario: ProjectScenario,
): ProjectComparisonSourceData {
  const records: ProjectComparisonSourceRecord[] = [];
  const creativeDirections = buildCreativeDirections(scenario);
  const creativeDirectionRecords: ProjectComparisonCreativeDirectionSourceRecord[] =
    [];
  for (let dayOffset = 0; dayOffset < 30; dayOffset += 1) {
    for (
      let lineIndex = 0;
      lineIndex < scenario.agencyLines.length;
      lineIndex += 1
    ) {
      for (let hour = 0; hour < 24; hour += 1) {
        const record = makeRecord(scenario, lineIndex, dayOffset, hour);
        records.push(record);
        const lineDirections = creativeDirections.filter(
          (direction) =>
            direction.agencyLineId === scenario.agencyLines[lineIndex]?.id,
        );
        for (const direction of lineDirections) {
          const profile = creativeDirectionProfiles.find((item) =>
            direction.id.endsWith(item.suffix),
          );
          if (!profile) throw new Error('素材方向演示数据不完整');
          creativeDirectionRecords.push(
            makeCreativeDirectionRecord(record, direction, profile),
          );
        }
      }
    }
  }
  return {
    agencyLines: scenario.agencyLines.map((line) => ({ ...line })),
    asOf: PROJECT_COMPARISON_DEMO_AS_OF,
    creativeDirectionRecords,
    creativeDirections,
    records,
  };
}

export const projectComparisonMockData = new Map(
  projectScenarios.map((scenario) => [
    scenario.projectId,
    buildProjectSourceData(scenario),
  ]),
);

export const projectComparisonServiceFeePercentByProject = new Map(
  projectScenarios.map((scenario) => [
    scenario.projectId,
    scenario.serviceFeePercent,
  ]),
);
