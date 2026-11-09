import {
  demoRoleProfilesAsUsers,
  getDemoRoleProfile,
  readSelectedDemoRole,
  toDemoRoleUserInfo,
} from '#/mock/demo-role-preview';

interface DemoMockRequest {
  baseURL?: string;
  data?: any;
  method?: string;
  params?: Record<string, any>;
  url?: string;
}

interface DemoMockResult {
  data: any;
  matched: boolean;
}

export const isDemoMockEnabled =
  import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

const now = '2026-08-07 16:30:00';
const demoFeedbacks: Array<Record<string, any>> = [
  {
    adminReply: null,
    attachmentCount: 1,
    attachments: [
      {
        fileSize: 284_672,
        id: 'demo-feedback-file-1',
        mimeType: 'image/png',
        originalName: '保存失败截图.png',
        sortOrder: 0,
      },
    ],
    category: 'BUG',
    clientIp: '203.0.113.18',
    content:
      '在广告创建页面填写完预算后点击保存，按钮持续加载但没有成功提示。刷新后数据没有保存。大约发生在今天 15:20。',
    createdAt: '2026-08-21 15:24:18',
    deviceType: 'desktop',
    diagnostics: {
      appVersion: '5.5.7',
      browser: 'Google Chrome',
      consoleLogs: [
        {
          level: 'error',
          message: 'TypeError: Failed to fetch /ads/draft',
          timestamp: '2026-08-21T07:23:58.000Z',
        },
      ],
      deviceMemory: 16,
      devicePixelRatio: 1,
      deviceType: 'desktop',
      hardwareConcurrency: 12,
      language: 'zh-CN',
      networkType: '4g',
      operatingSystem: 'Windows',
      pageUrl: 'http://localhost:5555/createAdvertisement',
      routeName: 'CreateAdvertisement',
      screenResolution: '1920×1080',
      timezone: 'Asia/Shanghai',
      viewportSize: '1440×900',
    },
    id: 'demo-feedback-1',
    pageUrl: 'http://localhost:5555/createAdvertisement',
    processedAt: null,
    processedById: null,
    processedByName: null,
    status: 'PENDING',
    submittedById: 'demo-user-1',
    submittedByName: '王投手',
    submittedByUsername: 'wang.tou',
    title: '创建广告保存后一直加载',
    updatedAt: '2026-08-21 15:24:18',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/139.0',
  },
  {
    adminReply: '已进入产品评审，计划与下个批量编辑版本一并排期。',
    attachmentCount: 0,
    attachments: [],
    category: 'FEATURE',
    clientIp: '198.51.100.9',
    content: '希望素材库支持批量修改标签，并在提交前预览将被修改的素材数量。',
    createdAt: '2026-08-20 10:12:31',
    deviceType: 'desktop',
    diagnostics: null,
    id: 'demo-feedback-2',
    pageUrl: '/materials/material-library',
    processedAt: '2026-08-20 14:30:00',
    processedById: 'demo-admin',
    processedByName: '系统管理员',
    status: 'PROCESSING',
    submittedById: 'demo-user-2',
    submittedByName: '陈素材',
    submittedByUsername: 'chen.sucai',
    title: '素材标签支持批量修改',
    updatedAt: '2026-08-20 14:30:00',
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1',
  },
];
const tinyPng =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL6WQAAAABJRU5ErkJggg==';

interface DemoUploadTask {
  result: {
    duplicate_count: number;
    duplicate_names: string[];
    errors: { error: string; name: string }[];
    failed: number;
    items: Array<Record<string, unknown>>;
    skipped: unknown[];
    success: number;
    total: number;
  };
}

const demoUploadTasks = new Map<string, DemoUploadTask>();
const demoDeliveryVersions = new Map<string, number>();
let demoUploadSequence = 0;

function readDemoRequestBody(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === 'object'
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

function createDemoUploadTask(data: unknown) {
  const formData =
    typeof FormData !== 'undefined' && data instanceof FormData
      ? data
      : undefined;
  const file = formData?.get('file');
  const name =
    file && typeof file === 'object' && 'name' in file
      ? String(file.name)
      : `material-${demoUploadSequence + 1}.zip`;
  const size =
    file && typeof file === 'object' && 'size' in file
      ? Number(file.size) || 0
      : 0;
  const contentType =
    file && typeof file === 'object' && 'type' in file
      ? String(file.type || 'application/octet-stream')
      : 'application/octet-stream';
  const extension = name.split('.').pop()?.toLowerCase() || 'file';
  const isVideo = ['avi', 'mkv', 'mov', 'mp4', 'webm'].includes(extension);
  const id = `demo-upload-${++demoUploadSequence}`;
  const objectKey = `material-orders/demo/${id}/${name}`;
  demoUploadTasks.set(id, {
    result: {
      duplicate_count: 0,
      duplicate_names: [],
      errors: [],
      failed: 0,
      items: [
        {
          basename: name,
          content_type: contentType,
          duration: isVideo ? 12 : 0,
          file_md5: `demo-md5-${id}`,
          filetype: isVideo ? 'video' : extension,
          height: isVideo ? 1920 : 0,
          id,
          img: isVideo ? `https://demo.local/thumbs/${id}.jpg` : '',
          name: `material-orders/${name}`,
          object_key: objectKey,
          sha3_256: `demo-sha3-${id}`,
          size,
          url: `https://demo.local/files/${id}/${encodeURIComponent(name)}`,
          width: isVideo ? 1080 : 0,
        },
      ],
      skipped: [],
      success: 1,
      total: 1,
    },
  });
  return { task_id: id };
}

const demoDepartments = [
  '增长一部',
  '全球发行部',
  '创意中心',
  '客户成功部',
  '媒介资源中心',
  '经营管理部',
  '财务部',
  '数据增长部',
];
const demoNames = [
  ...demoRoleProfilesAsUsers().map((user) => user.full_name),
  '赵优化',
];

const demoPlatformConfigs = [
  {
    _id: 'platform-starfall',
    agent_lines: ['Starfall-FB-ID', 'Starfall-Google-US'],
    agent_lines_count: 2,
    attribution_platform: 'AppsFlyer',
    departments: ['增长一部', '全球发行部'],
    enabled: true,
    game_platform: 'Starfall 全球增长',
    start_time: '2026-01-01',
    target_region: ['ID', 'US'],
    total_budget: '500000',
    visible: true,
  },
  {
    _id: 'platform-orbit',
    agent_lines: ['Orbit-TikTok-SEA', 'Orbit-Kwai-BR'],
    agent_lines_count: 2,
    attribution_platform: 'Adjust',
    departments: ['全球发行部'],
    enabled: true,
    game_platform: 'Orbit 海外发行',
    start_time: '2026-03-15',
    target_region: ['BR', 'TH'],
    total_budget: '320000',
    visible: true,
  },
  {
    _id: 'platform-nova',
    agent_lines: ['Nova-FB-EU'],
    agent_lines_count: 1,
    attribution_platform: 'Singular',
    departments: ['增长一部'],
    enabled: false,
    game_platform: 'Nova 欧洲测试',
    start_time: '2026-07-01',
    target_region: ['DE', 'FR'],
    total_budget: '80000',
    visible: true,
  },
];

const demoOrders = [
  {
    id: 'order-1001',
    order_no: 'MR-20260807-001',
    title: '印尼新用户暑期增长素材',
    project: 'Starfall 全球增长',
    project_id: 'project-starfall',
    priority: 'P0',
    demand_type: 'video',
    quantity: 6,
    status: 'pending_assign',
    creator: '王投手',
    designers: [],
    creative_planners: ['林策划'],
    department: '增长一部',
    tags: { country: ['ID'], gameplay: ['消除'], theme: ['暑期'] },
    created_at: '2026-08-07 09:12:00',
    submitted_at: '2026-08-07 09:20:00',
    expected_delivery_at: '2026-08-08 18:00:00',
    remaining_hours: 25,
    description: ['前三秒突出奖励', '9:16 竖版', '提供 3 个钩子变体'],
  },
  {
    id: 'order-1002',
    order_no: 'MR-20260806-018',
    title: '美国付费用户图片裂变',
    project: 'Starfall 全球增长',
    project_id: 'project-starfall',
    priority: 'P1',
    demand_type: 'image',
    quantity: 12,
    status: 'pending_accept',
    creator: '赵优化',
    designers: ['陈素材'],
    creative_planners: ['林策划'],
    assignments: [
      {
        assignee_id: 'user-7',
        assignee_name: '林策划',
        department_id: 'department-creative',
        id: 'assignment:order-1002:user-7',
        progress: 50,
        role: 'owner',
        status: 'doing',
      },
      {
        assignee_id: 'user-2',
        assignee_name: '陈晨',
        department_id: 'department-creative',
        id: 'assignment:order-1002:user-2',
        progress: 42,
        role: 'executor',
        status: 'doing',
      },
    ],
    department: '创意中心',
    tags: { country: ['US'], gameplay: ['策略'], theme: ['高价值礼包'] },
    created_at: '2026-08-06 14:30:00',
    submitted_at: '2026-08-06 14:46:00',
    expected_delivery_at: '2026-08-08 12:00:00',
    remaining_hours: 19,
    upload_done_count: 14,
    upload_total_count: 14,
    description: [{ id: 'req-order-1002-1', seq_label: '需求1' }],
  },
  {
    id: 'order-1003',
    order_no: 'MR-20260805-011',
    title: '巴西口播视频本地化',
    project: 'Orbit 海外发行',
    project_id: 'project-orbit',
    priority: 'P1',
    demand_type: 'video',
    quantity: 4,
    status: 'pending_accept',
    creator: '王投手',
    designers: ['陈素材'],
    creative_planners: ['林策划'],
    assignments: [
      {
        assignee_id: 'user-2',
        assignee_name: '陈晨',
        department_id: 'department-creative',
        id: 'assignment:order-1003:user-2',
        progress: 100,
        role: 'executor',
        status: 'submitted',
      },
    ],
    department: '全球发行部',
    tags: { country: ['BR'], gameplay: ['社交'], theme: ['真人口播'] },
    created_at: '2026-08-05 11:15:00',
    submitted_at: '2026-08-05 11:20:00',
    expected_delivery_at: '2026-08-07 17:00:00',
    remaining_hours: 1,
    upload_done_count: 4,
    upload_total_count: 4,
  },
  {
    id: 'order-1004',
    order_no: 'MR-20260804-006',
    title: '泰国回流活动短视频',
    project: 'Orbit 海外发行',
    project_id: 'project-orbit',
    priority: 'P2',
    demand_type: 'video',
    quantity: 8,
    status: 'accepted',
    creator: '赵优化',
    designers: ['陈素材'],
    creative_planners: ['林策划'],
    assignments: [
      {
        assignee_id: 'user-2',
        assignee_name: '陈晨',
        department_id: 'department-creative',
        id: 'assignment:order-1004:user-2',
        progress: 100,
        role: 'executor',
        status: 'done',
      },
    ],
    department: '创意中心',
    tags: { country: ['TH'], gameplay: ['回流'], theme: ['限时活动'] },
    created_at: '2026-08-04 10:00:00',
    submitted_at: '2026-08-04 10:10:00',
    expected_delivery_at: '2026-08-06 18:00:00',
    remaining_hours: -22,
    upload_done_count: 8,
    upload_total_count: 8,
  },
];

const demoMaterials = [
  {
    id: 'material-101',
    basename: 'starfall_reward_hook_v03.mp4',
    filename: 'creative/starfall_reward_hook_v03.mp4',
    filetype: 'video',
    category: '成片',
    country: 'ID',
    game_platform: 'Starfall 全球增长',
    creative_editor: '陈素材',
    user: '王投手',
    operator: '王投手',
    img: tinyPng,
    created_at: '2026-08-07 10:20:00',
    updated_at: now,
    tags: ['reward', 'hook'],
    tags_new: ['奖励钩子', '前三秒强刺激'],
    tags_titles: ['奖励钩子', '前三秒强刺激'],
    tags_len: 2,
    total_spent: 3820.45,
    file_md5: 'demo-md5-101',
    sha3_256: 'demo-sha-101',
  },
  {
    id: 'material-102',
    basename: 'starfall_packshot_us_v07.png',
    filename: 'creative/starfall_packshot_us_v07.png',
    filetype: 'image',
    category: '广告图',
    country: 'US',
    game_platform: 'Starfall 全球增长',
    creative_editor: '陈素材',
    user: '赵优化',
    operator: '赵优化',
    img: tinyPng,
    created_at: '2026-08-06 16:40:00',
    updated_at: now,
    tags: ['packshot', 'offer'],
    tags_new: ['礼包展示', '高价值用户'],
    tags_titles: ['礼包展示', '高价值用户'],
    tags_len: 2,
    total_spent: 6150.2,
    file_md5: 'demo-md5-102',
    sha3_256: 'demo-sha-102',
  },
  {
    id: 'material-103',
    basename: 'orbit_br_spokesperson_v02.mp4',
    filename: 'creative/orbit_br_spokesperson_v02.mp4',
    filetype: 'video',
    category: '口播',
    country: 'BR',
    game_platform: 'Orbit 海外发行',
    creative_editor: '林策划',
    user: '王投手',
    operator: '王投手',
    img: tinyPng,
    created_at: '2026-08-05 13:00:00',
    updated_at: now,
    tags: ['ugc', 'br'],
    tags_new: ['真人口播', '葡萄牙语'],
    tags_titles: ['真人口播', '葡萄牙语'],
    tags_len: 2,
    total_spent: 2740.8,
    file_md5: 'demo-md5-103',
    sha3_256: 'demo-sha-103',
  },
];

/**
 * Stable material facts for the existing MaterialOrder detail/acceptance
 * routes. The same material ID may be submitted to more than one folder; the
 * relation itself is tracked separately and never inferred from a filename.
 */
const demoOrderMaterials: Record<string, Record<string, unknown>[]> = {
  'order-1002': [
    {
      ...demoMaterials[0],
      content_type: 'video/mp4',
      duration: 12,
      height: 1920,
      object_key: 'material-orders/order-1002/material-101.mp4',
      req_id: 'req-1002-1',
      review_status: 'pending',
      size: 2_048_000,
      url: 'https://demo.local/materials/material-101.mp4',
      width: 1080,
    },
    {
      ...demoMaterials[1],
      content_type: 'image/png',
      duration: 0,
      height: 1920,
      object_key: 'material-orders/order-1002/material-102.png',
      req_id: 'req-1002-2',
      review_status: 'pending',
      size: 864_000,
      url: 'https://demo.local/materials/material-102.png',
      width: 1080,
    },
  ],
  'order-1003': [
    {
      ...demoMaterials[2],
      content_type: 'video/mp4',
      duration: 15,
      height: 1920,
      object_key: 'material-orders/order-1003/material-103.mp4',
      req_id: 'req-1003-1',
      review_status: 'pending',
      size: 2_430_000,
      url: 'https://demo.local/materials/material-103.mp4',
      width: 1080,
    },
  ],
  'order-1004': [
    {
      ...demoMaterials[1],
      content_type: 'image/png',
      duration: 0,
      height: 1920,
      object_key: 'material-orders/order-1004/material-102.png',
      req_id: 'req-1004-1',
      review_status: 'accepted',
      size: 864_000,
      url: 'https://demo.local/materials/material-102.png',
      width: 1080,
    },
  ],
};

const demoMaterialFolderRelations = new Set<string>();
const demoMaterialOrderComments = new Map<
  string,
  Array<Record<string, unknown>>
>();

function demoOrderMaterialGroups(orderId: string) {
  const order = demoOrders.find((item) => item.id === orderId);
  const materials = demoOrderMaterials[orderId] ?? [];
  return {
    groups: [
      {
        creative_planner: order?.creative_planners?.[0] ?? '',
        designer: order?.designers?.[0] ?? '未分配',
        materials,
        req_id: materials[0]?.req_id ?? null,
        requirement: order?.title ?? '',
      },
    ],
    items: materials,
    total: materials.length,
  };
}

const demoUsers = demoRoleProfilesAsUsers();

const demoRoles = [
  {
    _id: 'role-admin',
    name: '平台管理员',
    code: 'admin',
    permissions: ['*'],
    remark: '全平台配置及审计权限',
    status: 1,
  },
  {
    _id: 'role-pitcher',
    name: '广告投手',
    code: 'operator',
    permissions: ['requirements:create', 'ads:create', 'reports:read'],
    remark: '创建需求和广告投放',
    status: 1,
  },
  {
    _id: 'role-creator',
    name: '素材制作',
    code: 'creator',
    permissions: ['requirements:produce', 'materials:write', 'ai:create'],
    remark: 'AI 与人工素材制作',
    status: 1,
  },
  {
    _id: 'role-reviewer',
    name: '素材审核',
    code: 'reviewer',
    permissions: ['materials:review', 'experiments:read'],
    remark: '审核与二次裂变',
    status: 1,
  },
];

const demoMenus = [
  ['business', '业务中心', '/business-center', 'lucide:briefcase-business'],
  ['creative', '创意中心', '/creative-center', 'lucide:sparkles'],
  ['materials', '素材中心', '/material-center', 'lucide:folders'],
  ['delivery', '投放中心', '/delivery-center', 'lucide:rocket'],
  ['data', '数据复盘', '/data-growth', 'lucide:chart-no-axes-combined'],
  ['resources', '资源与配置', '/resource-center', 'lucide:boxes'],
  ['system', '系统管理', '/system-management', 'lucide:shield-check'],
].map(([id, title, path, icon], index) => ({
  _id: `menu-${id}`,
  id: `menu-${id}`,
  pid: '',
  name: `${id}Center`,
  path,
  type: 'catalog',
  authCode: '',
  meta: { icon, order: index * 10, title },
  children: [],
}));

function normalizedPath(request: DemoMockRequest): string {
  const rawUrl = request.url || '/';
  const rawPath = new URL(rawUrl, 'http://demo.local').pathname;
  let basePath = '';
  if (request.baseURL) {
    basePath = new URL(request.baseURL, 'http://demo.local').pathname;
  }
  const combined = `${basePath}/${rawPath}`.replaceAll(/\/{2,}/g, '/');
  return combined.replace(/^\/(backend|other)(?=\/)/, '') || '/';
}

function queryValue(request: DemoMockRequest, name: string): any {
  if (request.params?.[name] !== undefined) return request.params[name];
  return new URL(request.url || '/', 'http://demo.local').searchParams.get(
    name,
  );
}

function paginated<T>(items: T[], pageSize = 20) {
  return { items, total: items.length, page: 1, pageSize, page_size: pageSize };
}

function dashboardResult(tabKey = 'campaign_id') {
  const names: Record<string, string[]> = {
    account_id: [
      'Starfall SEA 主投账户',
      'Meta SEA 备用账户 02',
      'TikTok 日本首发账户',
    ],
    ad_id: ['Reward Hook 视频 03', 'Packshot Value 图片 02', 'BR UGC 口播 06'],
    ad_platform: ['Facebook', 'Google', 'TikTok'],
    ad_set_id: ['ID Broad 18-34', 'US Value LAL 3%', 'BR Android Broad'],
    agent_line: ['MP014-FB-PWA', 'F9F9-FB-PWA-83', 'TikTok-JP-H5'],
    campaign_id: [
      'ID_RewardHook_AEO',
      'US_Packshot_Value',
      'BR_UGC_LocalVoice',
    ],
    channel: ['Facebook 海外户', 'Google Global MCC', 'TikTok 日本渠道'],
    department: ['增长一部', '全球发行部', '日本增长组'],
    game_platform: [
      'Starfall 全球增长',
      'Project Ark 美国市场',
      'Pixel Quest 日本首发',
    ],
  };
  const columns = [
    'name',
    'status',
    '花费金额',
    '在跑预算',
    '最新时间',
    '已关停消耗',
    '在跑消耗',
    '覆盖人数',
    '展示次数',
    '点击数',
    '点击率',
    '点击成本',
    '链接点击数',
    '落地页浏览',
    '落地页成本',
    '注册数',
    '注册转化率',
    '注册成本',
    '订单数',
    '订单率',
    '订单成本',
    '订单价值',
    '购物数',
    '购物成本',
    '购物价值',
    '购物ROAS',
  ];
  const rowNames = names[tabKey] ?? names.campaign_id!;
  const base = [
    {
      spend: 6284.4,
      budget: 8500,
      reach: 188_420,
      impressions: 235_945,
      clicks: 5728,
      register: 426,
      orders: 238,
      shopping: 186,
    },
    {
      spend: 9347.2,
      budget: 12_000,
      reach: 142_610,
      impressions: 168_402,
      clicks: 3822,
      register: 238,
      orders: 112,
      shopping: 93,
    },
    {
      spend: 3172.6,
      budget: 5400,
      reach: 96_740,
      impressions: 118_320,
      clicks: 2910,
      register: 196,
      orders: 86,
      shopping: 72,
    },
  ];
  const data = rowNames.map((name, index) => {
    const item = base[index]!;
    const landing = Math.round(item.clicks * 0.74);
    const linkClicks = Math.round(item.clicks * 0.87);
    const orderValue = item.orders * (62 + index * 8);
    const shoppingValue = item.shopping * (78 + index * 5);
    return {
      id: `${tabKey}-${index + 1}`,
      name,
      status: index === 2 ? 'PAUSED' : 'ACTIVE',
      花费金额: item.spend,
      在跑预算: item.budget,
      最新时间: `08-11 22:0${index + 3}`,
      已关停消耗: index === 2 ? 428.6 : 0,
      在跑消耗: index === 2 ? item.spend - 428.6 : item.spend,
      覆盖人数: item.reach,
      展示次数: item.impressions,
      点击数: item.clicks,
      点击率: `${((item.clicks / item.impressions) * 100).toFixed(2)}%`,
      点击成本: Number((item.spend / item.clicks).toFixed(2)),
      链接点击数: linkClicks,
      落地页浏览: landing,
      落地页成本: Number((item.spend / landing).toFixed(2)),
      注册数: item.register,
      注册转化率: `${((item.register / landing) * 100).toFixed(2)}%`,
      注册成本: Number((item.spend / item.register).toFixed(2)),
      订单数: item.orders,
      订单率: `${((item.orders / item.register) * 100).toFixed(2)}%`,
      订单成本: Number((item.spend / item.orders).toFixed(2)),
      订单价值: orderValue,
      购物数: item.shopping,
      购物成本: Number((item.spend / item.shopping).toFixed(2)),
      购物价值: shoppingValue,
      购物ROAS: Number((shoppingValue / item.spend).toFixed(2)),
    };
  });
  return {
    columns,
    data,
    pagination: { page: 1, page_size: 100, total: data.length, total_pages: 1 },
  };
}

function reportOverview(path: string) {
  if (path === '/dashboard/project_overview') {
    const data = [
      {
        项目: 'Starfall 全球增长',
        地区: 'ID / US',
        投手数量: 3,
        消耗: 12_860.4,
        roas: 3.18,
        cpa: 8.42,
        注册: 886,
        付费成本: 13.2,
        订阅成本: 18.6,
        vs7日: '+12.4%',
      },
      {
        项目: 'Orbit 海外发行',
        地区: 'BR / TH',
        投手数量: 2,
        消耗: 5759.6,
        roas: 2.63,
        cpa: 10.18,
        注册: 364,
        付费成本: 15.8,
        订阅成本: 21.4,
        vs7日: '+6.8%',
      },
      {
        项目: 'Nova 欧洲测试',
        地区: 'DE / FR',
        投手数量: 1,
        消耗: 1486.2,
        roas: 1.94,
        cpa: 14.76,
        注册: 92,
        付费成本: 19.6,
        订阅成本: 27.8,
        vs7日: '-3.2%',
      },
    ];
    return {
      columns: Object.keys(data[0]!),
      data,
      pagination: {
        page: 1,
        page_size: 1000,
        total: data.length,
        total_pages: 1,
      },
    };
  }
  if (path === '/dashboard/placer_overview') {
    const data = [
      {
        投手: '王投手',
        real_name: '王敏',
        组: '增长一部',
        在投代理线: 4,
        消耗: 8420.8,
        ROAS: 3.42,
        CPI: 1.84,
        付费成本: 12.6,
        订阅成本: 17.9,
      },
      {
        投手: '赵优化',
        real_name: '赵宁',
        组: '全球发行部',
        在投代理线: 3,
        消耗: 6318.5,
        ROAS: 2.91,
        CPI: 2.16,
        付费成本: 15.4,
        订阅成本: 20.8,
      },
      {
        投手: '周主管',
        real_name: '周宁',
        组: '增长一部',
        在投代理线: 2,
        消耗: 3880.7,
        ROAS: 2.68,
        CPI: 2.42,
        付费成本: 16.1,
        订阅成本: 23.2,
      },
    ];
    return {
      columns: Object.keys(data[0]!),
      data,
      pagination: {
        page: 1,
        page_size: 1000,
        total: data.length,
        total_pages: 1,
      },
    };
  }
  if (path === '/dashboard/placer_leaderboard') {
    const data = [
      { 排名: 1, 组: '增长一部', 消耗: 186_420, 同比上月: '+18.6%' },
      { 排名: 2, 组: '全球发行部', 消耗: 142_860, 同比上月: '+11.2%' },
      { 排名: 3, 组: '创意中心联投', 消耗: 57_140, 同比上月: '-2.4%' },
    ];
    return {
      columns: Object.keys(data[0]!),
      data,
      pagination: {
        page: 1,
        page_size: 1000,
        total: data.length,
        total_pages: 1,
      },
    };
  }
  const data = [
    {
      渠道商: 'Facebook',
      总消耗: 11_920.4,
      账户数: 8,
      封户数: 1,
      封户率: '12.5%',
      VS7日: '+9.6%',
    },
    {
      渠道商: 'Google',
      总消耗: 4886.6,
      账户数: 5,
      封户数: 0,
      封户率: '0%',
      VS7日: '+5.8%',
    },
    {
      渠道商: 'TikTok',
      总消耗: 3299.2,
      账户数: 4,
      封户数: 0,
      封户率: '0%',
      VS7日: '-1.7%',
    },
  ];
  return {
    columns: Object.keys(data[0]!),
    data,
    pagination: {
      page: 1,
      page_size: 1000,
      total: data.length,
      total_pages: 1,
    },
    total_row: {
      渠道商: '总计',
      总消耗: 20_106.2,
      账户数: 17,
      封户数: 1,
      封户率: '5.9%',
      VS7日: '+6.7%',
    },
  };
}

function automationOptions() {
  return {
    actions: [
      { code: 'status', name: '开关状态' },
      { code: 'daily_budget', name: '调整预算' },
    ],
    adjust_directions: [
      { code: 'increase', name: '增加' },
      { code: 'decrease', name: '减少' },
    ],
    adjust_units: [
      { code: 'percent', name: '百分比' },
      { code: 'fixed', name: '固定金额' },
    ],
    frequencies: [
      { code: 'hourly', name: '每小时' },
      { code: 'daily', name: '每天' },
    ],
    levels: [
      { code: 'campaign', name: '广告系列' },
      { code: 'adset', name: '广告组' },
      { code: 'ad', name: '广告' },
    ],
    metrics: [
      { code: 'spend', name: '消耗' },
      { code: 'purchase_roas', name: 'ROAS' },
      { code: 'registration_cost', name: '注册成本' },
    ],
    notification_channels: [
      { code: 'feishu', name: '飞书' },
      { code: 'telegram', name: 'Telegram' },
    ],
    operators: [
      { code: 'gte', name: '大于等于', value_count: 1 },
      { code: 'lte', name: '小于等于', value_count: 1 },
    ],
    status_values: [
      { code: 'active', name: '开启' },
      { code: 'paused', name: '暂停' },
    ],
    time_windows: [
      { code: 'today', name: '今天' },
      { code: 'past_3_days', name: '近三天' },
    ],
    timezones: [
      { code: 'Asia/Shanghai', name: 'Asia/Shanghai' },
      { code: 'America/Los_Angeles', name: 'America/Los_Angeles' },
    ],
  };
}

function getMockData(path: string, request: DemoMockRequest): any {
  const method = (request.method || 'GET').toUpperCase();
  if (path === '/feedbacks' && method === 'GET') {
    const keyword = String(request.params?.keyword ?? '')
      .trim()
      .toLowerCase();
    const category = String(request.params?.category ?? '');
    const status = String(request.params?.status ?? '');
    const items = demoFeedbacks.filter(
      (item) =>
        (!category || item.category === category) &&
        (!status || item.status === status) &&
        (!keyword ||
          [
            item.title,
            item.content,
            item.submittedByName,
            item.submittedByUsername,
            item.clientIp,
          ].some((value) => value.toLowerCase().includes(keyword))),
    );
    return {
      items,
      page: Number(request.params?.page ?? 1),
      pageSize: Number(request.params?.pageSize ?? 20),
      total: items.length,
    };
  }
  if (path === '/feedbacks' && method === 'POST') {
    const body = readDemoRequestBody(request.data);
    const created = {
      adminReply: null,
      attachmentCount: Array.isArray(body.attachmentFileIds)
        ? body.attachmentFileIds.length
        : 0,
      attachments: [],
      category: String(body.category ?? 'FEATURE'),
      clientIp: '127.0.0.1',
      content: String(body.content ?? ''),
      createdAt: now,
      deviceType: String(
        (body.diagnostics as Record<string, unknown> | undefined)?.deviceType ??
          'desktop',
      ),
      diagnostics: body.diagnostics ?? null,
      id: `demo-feedback-${demoFeedbacks.length + 1}`,
      pageUrl: String(
        (body.diagnostics as Record<string, unknown> | undefined)?.pageUrl ??
          '',
      ),
      processedAt: null,
      processedById: null,
      processedByName: null,
      status: 'PENDING',
      submittedById: 'demo-current-user',
      submittedByName: '当前演示用户',
      submittedByUsername: 'demo.user',
      title: String(body.title ?? ''),
      updatedAt: now,
      userAgent: navigator.userAgent,
    };
    demoFeedbacks.unshift(created);
    return created;
  }
  if (/^\/feedbacks\/[^/]+$/.test(path)) {
    const id = path.split('/').pop();
    const feedback = demoFeedbacks.find((item) => item.id === id);
    if (method === 'PUT' && feedback) {
      const body = readDemoRequestBody(request.data);
      Object.assign(feedback, {
        adminReply: String(body.adminReply ?? ''),
        processedAt: now,
        processedById: 'demo-admin',
        processedByName: '系统管理员',
        status: String(body.status ?? feedback.status),
        updatedAt: now,
      });
    }
    return feedback;
  }
  if (/^\/feedbacks\/[^/]+\/status$/.test(path) && method === 'PUT') {
    const id = path.split('/')[2];
    const feedback = demoFeedbacks.find((item) => item.id === id);
    if (!feedback) return undefined;
    const body = readDemoRequestBody(request.data);
    Object.assign(feedback, {
      adminReply: String(body.adminReply ?? ''),
      processedAt: now,
      processedById: 'demo-admin',
      processedByName: '系统管理员',
      status: String(body.status ?? feedback.status),
      updatedAt: now,
    });
    return feedback;
  }
  if (method !== 'GET') {
    if (path === '/files/upload') {
      const formData =
        typeof FormData !== 'undefined' && request.data instanceof FormData
          ? request.data
          : undefined;
      const file = formData?.get('file');
      return {
        id: `demo-feedback-file-${Date.now()}`,
        mimeType:
          file && typeof file === 'object' && 'type' in file
            ? String(file.type || 'application/octet-stream')
            : 'application/octet-stream',
        originalName:
          file && typeof file === 'object' && 'name' in file
            ? String(file.name)
            : 'feedback-file',
      };
    }
    if (path === '/material-orders/attachments') {
      return createDemoUploadTask(request.data);
    }
    if (/^\/material-orders\/[^/]+\/deliver$/.test(path)) {
      const orderId = path.split('/')[2] ?? '';
      const body = readDemoRequestBody(request.data);
      const materials = Array.isArray(body.materials) ? body.materials : [];
      const versionNo = (demoDeliveryVersions.get(orderId) ?? 0) + 1;
      demoDeliveryVersions.set(orderId, versionNo);
      const order = demoOrders.find((item) => item.id === orderId);
      if (order) {
        order.status = 'pending_accept';
        order.upload_done_count = materials.length;
        order.upload_total_count = Math.max(order.quantity, materials.length);
      }
      return {
        delivery_id: `demo-delivery-${orderId}-v${versionNo}`,
        status: 'pending_accept',
        version_no: versionNo,
      };
    }
    if (/^\/material-orders\/[^/]+\/accept$/.test(path)) {
      const orderId = path.split('/')[2] ?? '';
      const order = demoOrders.find((item) => item.id === orderId);
      if (!order) return { message: '素材订单不存在', status: 'not_found' };
      order.status = 'accepted';
      return { id: orderId, status: 'accepted', title: order.title };
    }
    if (/^\/material-orders\/[^/]+\/assign-materials$/.test(path)) {
      const orderId = path.split('/')[2] ?? '';
      const body = readDemoRequestBody(request.data);
      const folderId = typeof body.folder_id === 'string' ? body.folder_id : '';
      const ids = Array.isArray(body.ids)
        ? body.ids.filter(
            (id): id is string => typeof id === 'string' && id.length > 0,
          )
        : [];
      const availableIds = new Set(
        (demoOrderMaterials[orderId] ?? [])
          .map((material) => material.id)
          .filter((id): id is string => typeof id === 'string'),
      );
      if (
        !folderId ||
        ids.length === 0 ||
        ids.some((id) => !availableIds.has(id))
      ) {
        return { assigned_count: 0, message: '素材或目标目录无效' };
      }
      let assignedCount = 0;
      for (const materialId of ids) {
        const relationKey = `${orderId}:${folderId}:${materialId}`;
        if (demoMaterialFolderRelations.has(relationKey)) continue;
        demoMaterialFolderRelations.add(relationKey);
        assignedCount += 1;
      }
      return { assigned_count: assignedCount, folder_id: folderId, ids };
    }
    if (/^\/material-orders\/[^/]+\/comments$/.test(path)) {
      const orderId = path.split('/')[2] ?? '';
      const body = readDemoRequestBody(request.data);
      const comment = {
        author: '演示用户',
        author_role: '验收人',
        content: typeof body.content === 'string' ? body.content : '',
        created_at: now.replace(' ', 'T'),
        event: 'comment',
        id: `demo-comment-${Date.now()}`,
      };
      const comments = demoMaterialOrderComments.get(orderId) ?? [];
      comments.push(comment);
      demoMaterialOrderComments.set(orderId, comments);
      return comment;
    }
    if (/^\/material-orders\/[^/]+\/complete$/.test(path)) {
      const orderId = path.split('/')[2] ?? '';
      const order = demoOrders.find((item) => item.id === orderId);
      if (order) order.status = 'is_complete';
      return { id: orderId, status: 'is_complete' };
    }
    if (path === '/operations/subtask-personal-account-info') {
      let body = request.data ?? {};
      if (typeof body === 'string') {
        try {
          body = JSON.parse(body);
        } catch {
          body = {};
        }
      }
      const queries = Array.isArray(body.queries) ? body.queries : [];
      return queries.map((query: any, index: number) => ({
        accounts_total: 2,
        target_region: index % 2 === 0 ? ['ID'] : ['US'],
        公共主页ID: index % 2 === 0 ? 'page_1' : 'page_2',
        公共主页名称: index % 2 === 0 ? 'Starfall Quest' : 'Starfall Community',
        广告账户ID: index % 2 === 0 ? 'act_10001' : 'act_10002',
        所属BM: 'Starfall Global BM',
        项目名称: query.task_name || 'Starfall 全球增长',
        任务线名称: query.subtask_name || `Starfall-FB-${index + 1}`,
        任务线编号: `demo-line-${index + 1}`,
        投放地区: index % 2 === 0 ? '印尼' : '美国',
        投放链接:
          index % 2 === 0
            ? 'https://demo.example.com/id'
            : 'https://demo.example.com/us',
      }));
    }
    if (path.includes('batch-assign') || path.includes('batch-reject')) {
      return { count: request.data?.items?.length || 1 };
    }
    if (path.includes('/toggle')) return { enabled: true, id: 'demo-record' };
    if (path.includes('/config') && method === 'POST')
      return { request_ids: ['demo-request-1'] };
    return {
      _id: 'demo-created',
      id: 'demo-created',
      message: '演示操作已完成',
      status: 'success',
    };
  }

  if (path === '/users/info') {
    // Demo role selection is local only. Production continues to resolve the
    // authenticated user on the server through the unchanged /users/info API.
    return toDemoRoleUserInfo(
      readSelectedDemoRole() ?? getDemoRoleProfile('admin')!,
    );
  }
  if (path === '/users/' || path === '/users') return paginated(demoUsers);
  if (path.startsWith('/users/names')) {
    return demoNames.map((full_name) => ({ full_name, real_name: full_name }));
  }
  if (path.startsWith('/users/full_names')) return demoNames;
  if (path === '/users/department_options') return demoDepartments;
  if (path === '/users/department_scope') return demoUsers;
  if (/^\/users\/[^/]+\/apikeys$/.test(path))
    return [
      {
        _id: 'key-1',
        name: 'AdGen 调用密钥',
        created_at: now,
        remark: '演示环境',
      },
    ];

  if (path === '/roles/' || path === '/roles') return paginated(demoRoles);
  if (path === '/menus/all') return demoMenus;
  if (path === '/menus/name' || path === '/menus/path') return false;

  if (path === '/department/options/' || path === '/department/options')
    return demoDepartments;
  if (path === '/department/tree') {
    return {
      items: [
        {
          id: 'dept-growth',
          name: '增长一部',
          children: [
            { id: 'dept-id', name: '印尼增长组', parent_id: 'dept-growth' },
          ],
        },
        {
          id: 'dept-global',
          name: '全球发行部',
          children: [
            {
              id: 'dept-america',
              name: '美洲发行组',
              parent_id: 'dept-global',
            },
          ],
        },
        { id: 'dept-creative', name: '创意中心', children: [] },
      ],
    };
  }
  if (path === '/department/' || path === '/department')
    return demoDepartments.map((name, index) => ({
      id: `dept-${index}`,
      name,
    }));

  if (path === '/platform-config/' || path === '/platform-config')
    return paginated(demoPlatformConfigs);
  if (path === '/platform-config/plat_options/')
    return demoPlatformConfigs.map((item) => item.game_platform);
  if (path === '/platform-config/agent_options/')
    return demoPlatformConfigs.map((item) => ({
      _id: item.game_platform,
      agent_lines: item.agent_lines,
      game_platform: item.game_platform,
    }));
  if (path.startsWith('/platform-config/agent-line-kpi'))
    return paginated([
      {
        _id: 'kpi-1',
        agent_lines: ['Starfall-FB-ID'],
        event_name: 'purchase',
        game_platform: 'Starfall 全球增长',
        target_cost: 14,
        max_target_cost: 18,
        type: 'purchase',
      },
    ]);
  if (path.startsWith('/platform-config/agent-line'))
    return paginated([
      {
        _id: 'line-1',
        id: 'line-1',
        agent_line: 'Starfall-FB-ID',
        game_platform: 'Starfall 全球增长',
        enabled: true,
        auto_run: true,
        optimizer: '赵优化',
        package_name: 'com.demo.starfall',
      },
      {
        _id: 'line-2',
        id: 'line-2',
        agent_line: 'Orbit-TikTok-SEA',
        game_platform: 'Orbit 海外发行',
        enabled: true,
        auto_run: false,
        optimizer: '王投手',
        package_name: 'com.demo.orbit',
      },
    ]);

  if (path === '/material-orders/') {
    const status = queryValue(request, 'status');
    const view = queryValue(request, 'view');
    let items = [...demoOrders];
    if (status) items = items.filter((item) => item.status === status);
    if (view === 'assigned' && !status)
      items = items.filter((item) => item.designers.length > 0);
    return paginated(items, 10);
  }
  if (path === '/material-orders/stats')
    return {
      status_counts: { pending_assign: 4, in_production: 7, pending_accept: 3 },
      sla_warning: 2,
    };
  if (path === '/material-orders/my-stats')
    return {
      in_progress: { demands: 7, materials: 24, warning: 2 },
      delivered_week: { count: 18, wow: 12.5 },
    };
  if (path === '/material-orders/creators')
    return demoNames.map((full_name, index) => ({
      full_name,
      real_name: full_name,
      in_production_count: index < 2 ? 3 - index : 0,
    }));
  if (path.startsWith('/upload-tasks/')) {
    const taskId = path.split('/').pop() ?? '';
    const task = demoUploadTasks.get(taskId);
    return task
      ? { result: task.result, status: 'done' }
      : { error: '上传任务不存在', status: 'failed' };
  }
  if (/^\/material-orders\/[^/]+\/materials$/.test(path)) {
    const orderId = path.split('/')[2] ?? '';
    return demoOrderMaterialGroups(orderId);
  }
  if (/^\/material-orders\/[^/]+\/comments$/.test(path)) {
    const orderId = path.split('/')[2] ?? '';
    return { items: demoMaterialOrderComments.get(orderId) ?? [] };
  }
  if (/^\/material-orders\/[^/]+$/.test(path))
    return (
      demoOrders.find((item) => item.id === path.split('/').pop()) ||
      demoOrders[0]
    );

  if (path === '/tags/fact')
    return [
      {
        name: 'country',
        title: '投放国家',
        is_necessary: 'true',
        tags: ['ID', 'US', 'BR', 'TH'],
      },
      {
        name: 'theme',
        title: '创意主题',
        is_necessary: 'true',
        tags: ['奖励钩子', '真人口播', '高价值礼包', '限时活动'],
      },
      {
        name: 'gameplay',
        title: '玩法',
        is_necessary: 'false',
        tags: ['消除', '策略', '社交', '回流'],
      },
    ];
  if (path === '/tags/inference')
    return [
      {
        name: 'emotion',
        title: '情绪标签',
        is_necessary: 'false',
        tags: ['惊喜', '紧迫', '信任'],
      },
      {
        name: 'visual_style',
        title: '视觉风格',
        is_necessary: 'false',
        tags: ['UGC', '原生感', '高饱和'],
      },
    ];

  if (path === '/material-folders')
    return [
      {
        id: 'folder-1',
        name: 'Starfall 已审核素材',
        material_count: 18,
        children: [
          {
            id: 'folder-1-1',
            name: '印尼增长',
            parent_id: 'folder-1',
            material_count: 8,
            children: [],
          },
        ],
      },
      {
        id: 'folder-2',
        name: 'Orbit 本地化素材',
        material_count: 12,
        children: [],
      },
    ];
  if (/^\/material-folders\/[^/]+\/materials$/.test(path))
    return paginated(demoMaterials, 100);
  if (path === '/materials/' || path === '/materials')
    return paginated(demoMaterials, 100);
  if (path === '/materials/ad-creatives') return paginated(demoMaterials, 100);
  if (path === '/material-common/' || path === '/material-common')
    return paginated(demoMaterials, 100);
  if (path === '/materials/by_ids' || path === '/material-common/by_ids')
    return { items: demoMaterials };
  if (path.startsWith('/materials/url/')) return { url: '/mpower.jpg' };
  if (path.startsWith('/materials/img/')) return { img: tinyPng };

  if (path === '/material-dashboard/designer-spend')
    return {
      list: [
        {
          name: '陈素材',
          department: '创意中心',
          date: '2026-08-07',
          spend: 10_482.6,
          tokens: 1_284_000,
          last_date: '2026-08-07',
        },
        {
          name: '林策划',
          department: '全球发行部',
          date: '2026-08-07',
          spend: 7236.35,
          tokens: 936_000,
          last_date: '2026-08-07',
        },
        {
          name: '张设计',
          department: '创意中心',
          date: '2026-08-06',
          spend: 5918.2,
          tokens: 718_000,
          last_date: '2026-08-06',
        },
      ],
      spend_total: 23_637.15,
      tokens_total: 2_938_000,
      total: 3,
    };
  if (path === '/material-dashboard/materials')
    return {
      items: demoMaterials.map((item, index) => ({
        ...item,
        create_time: item.created_at,
        delivery_start: '2026-08-01',
        delivery_cutoff: '2026-08-07',
        designer: item.creative_editor,
        ads_count: 8 - index,
        spend: item.total_spent,
        cpm: 4.6 + index,
        cvr: 12.8 - index,
        ctr: 3.2 - index * 0.2,
        ir: 8.4 - index * 0.3,
        impressions: 150_000 - index * 21_000,
        clicks: 4800 - index * 620,
        registrations: 390 - index * 55,
        department: index === 2 ? '全球发行部' : '创意中心',
        creator: item.user,
        project: item.game_platform,
        product_info: index === 2 ? 'Orbit Social' : 'Starfall Quest',
      })),
      total: demoMaterials.length,
      spend_total: 12_711.45,
    };
  if (path === '/material-dashboard/materials/ads')
    return paginated(dashboardResult().data);

  if (path === '/creative/' || path === '/creative') {
    return {
      has_more: false,
      materials: demoMaterials.map((item, index) => ({
        ...item,
        _id: item.id,
        creative_count: [6, 12, 4][index],
        file_id: `demo-file-${index + 1}`,
        isNew: index === 0,
        original_filename: item.basename,
        prompt: [
          '奖励爆点前置，强化前三秒视觉钩子',
          '保持礼包主体，裂变背景与价格标签',
          '葡语真人口播，保留原生 UGC 质感',
        ][index],
        status: 'success',
        thumbnail: tinyPng,
        unique_filename: item.basename,
      })),
      total: demoMaterials.length,
    };
  }
  if (path === '/creative/running/' || path === '/creative/running')
    return { data: {}, remaining_time: 0, total: 0, wait_num: 0 };
  if (path.startsWith('/creative/url/') || path.startsWith('/creative/murl/'))
    return { url: '/mpower.jpg' };
  if (path.startsWith('/creative/thumbnail/')) return tinyPng;

  if (path === '/api/data/range') {
    const data = demoMaterials.map((item, index) => ({
      日期: `2026-08-0${7 - index}`,
      游戏平台: item.game_platform,
      广告平台: index === 1 ? 'Google' : 'Facebook',
      代理线: index === 2 ? 'Orbit-Kwai-BR' : 'Starfall-FB-ID',
      素材名称: item.basename,
      消耗: item.total_spent,
      展示: 186_000 - index * 24_000,
      点击: 5420 - index * 580,
      CTR: `${(3.1 - index * 0.2).toFixed(2)}%`,
      ROAS: (3.42 - index * 0.3).toFixed(2),
    }));
    return { columns: Object.keys(data[0]!), data, total: data.length };
  }
  if (path === '/api/materials/recommend') {
    const data = demoMaterials.map((item, index) => ({
      素材名称: item.basename,
      游戏平台: item.game_platform,
      文件类型: item.filetype === 'image' ? '图片' : '视频',
      成效等级: ['S', 'A', 'A'][index],
      聚类区域: ['顶级表现区', '稳定表现区', '顶级表现区'][index],
      素材状态: ['新', '已存在', '已存在'][index],
      消耗: item.total_spent,
      ROAS: [3.62, 2.91, 3.38][index],
    }));
    return { columns: Object.keys(data[0]!), data, total: data.length };
  }

  if (path === '/dashboard/filter_options')
    return {
      channels: [
        { label: 'Facebook', value: 'facebook' },
        { label: 'Google', value: 'google' },
        { label: 'TikTok', value: 'tiktok' },
      ],
      departments: demoDepartments,
      placers: [
        { label: '王投手', value: '王投手' },
        { label: '赵优化', value: '赵优化' },
      ],
      projects: demoPlatformConfigs.map((item) => item.game_platform),
      regions: ['ID', 'US', 'BR', 'TH'],
    };
  if (path === '/dashboard/filter_templates')
    return [
      {
        id: 'template-1',
        name: 'Starfall 日报',
        use_time: '2026-08-07 10:00:00',
      },
      {
        id: 'template-2',
        name: '美洲高消耗项目',
        use_time: '2026-08-06 18:30:00',
      },
    ];
  if (path.startsWith('/dashboard/filter_templates/'))
    return {
      id: 'template-1',
      name: 'Starfall 日报',
      use_time: now,
      filters: {
        game_platform: ['Starfall 全球增长'],
        placer: [],
        region: ['ID', 'US'],
      },
    };
  if (path.startsWith('/dashboard/detail/')) {
    return dashboardResult(path.split('/').findLast(Boolean));
  }
  if (path === '/dashboard/column-settings') return null;
  if (path === '/dashboard/spend_summary')
    return {
      今日总消耗: 18_620,
      昨日: 17_840,
      本月: 386_420,
      近7日平均: 17_230,
      环比昨日: '+4.37%',
      消耗趋势: [
        { date: '08-03', 消耗: 15_420 },
        { date: '08-04', 消耗: 16_980 },
        { date: '08-05', 消耗: 17_310 },
        { date: '08-06', 消耗: 17_840 },
        { date: '08-07', 消耗: 18_620, 进行中: true },
      ],
    };
  if (path === '/dashboard/intraday_trend')
    return {
      kpi_target: 18,
      data: [
        { 时间: '08:00', 消耗: 2210, 付费成本: 15.2 },
        { 时间: '12:00', 消耗: 6140, 付费成本: 14.6 },
        { 时间: '16:00', 消耗: 10_820, 付费成本: 13.9 },
      ],
    };
  if (
    /^\/dashboard\/(project_overview|placer_overview|placer_leaderboard|channel_overview)$/.test(
      path,
    )
  )
    return reportOverview(path);

  if (path === '/attribution/' || path === '/attribution')
    return [
      {
        id: 'attr-1',
        name: 'timezone',
        title: '报表时区',
        mode: 'single',
        default: 'Asia/Shanghai',
        options: ['Asia/Shanghai', 'UTC', 'America/Los_Angeles'],
        created_at: now,
        updated_at: now,
      },
      {
        id: 'attr-2',
        name: 'currency',
        title: '统一币种',
        mode: 'single',
        default: 'USD',
        options: ['USD', 'CNY', 'EUR'],
        created_at: now,
        updated_at: now,
      },
      {
        id: 'attr-3',
        name: 'window',
        title: '归因窗口',
        mode: 'single',
        default: '7天点击/1天浏览',
        options: ['1天点击', '7天点击/1天浏览', '28天点击/1天浏览'],
        created_at: now,
        updated_at: now,
      },
      {
        id: 'attr-4',
        name: 'metric',
        title: '核心指标',
        mode: 'multiple',
        default: ['CPP', 'CVR', 'ROAS'],
        options: ['CPP', 'CVR', 'ROAS'],
        created_at: now,
        updated_at: now,
      },
    ];

  if (path === '/developers/')
    return paginated([
      {
        _id: 'dev-1',
        ad_platform: 'facebook',
        app_name: 'Starfall Growth App',
        dev_id: 'fb-dev-001',
        placer_id: '王投手',
        agent_lines: ['Starfall-FB-ID'],
        department: ['增长一部'],
        status: 1,
        account_usage: {
          insights_pull: true,
          facebook_login: true,
          sync_personal: true,
          sync_bm: true,
          sync_pixels: true,
        },
      },
      {
        _id: 'dev-2',
        ad_platform: 'google',
        app_name: 'Orbit Google Ads',
        dev_id: 'google-dev-002',
        placer_id: '赵优化',
        agent_lines: ['Starfall-Google-US'],
        department: ['全球发行部'],
        status: 1,
      },
    ]);
  if (path === '/developers/ad_sync_history')
    return {
      items: [
        {
          _id: 'sync-1',
          dev_id: 'fb-dev-001',
          app_name: 'Starfall Growth App',
          ad_platform: 'facebook',
          run_status: 'success',
          synced_count: 128,
          day: '2026-08-07',
          hour: 16,
          updated_at: now,
        },
      ],
      page: 1,
      page_size: 20,
      pages: 1,
      total: 1,
    };

  if (path === '/fb_resource/personal_accounts')
    return paginated([
      {
        _id: 'personal-1',
        name: 'Facebook Personal · 王投手',
        app_id: '128840001',
        accounts: ['act_10001', 'act_10002'],
        business: ['bm_801'],
        pages: ['Starfall Quest'],
        updated_at: now,
        status: 1,
      },
      {
        _id: 'personal-2',
        name: 'Facebook Personal · 赵优化',
        app_id: '128840002',
        accounts: ['act_10003'],
        business: ['bm_802'],
        pages: ['Orbit Social'],
        updated_at: now,
        status: 1,
      },
    ]);
  if (path === '/fb_resource/system_accounts')
    return paginated([
      {
        _id: 'system-1',
        app_id: '128840001',
        accounts: ['act_10001', 'act_10002'],
        pages: ['Starfall Quest'],
        status: 1,
        update_time: now,
      },
    ]);
  if (path === '/fb_resource/ad_accounts')
    return {
      ...paginated([
        {
          _id: 'act_10001',
          name: 'Starfall ID Main',
          account_status: 1,
          amount_spent: '18620.50',
          balance: '38400.00',
          currency: 'USD',
          owner: 'bm_801',
          timezone_name: 'Asia/Jakarta',
          updated_at: now,
        },
      ]),
      matched_ids: [],
      missing_ids: [],
    };
  if (path === '/fb_resource/businesss')
    return paginated([
      {
        _id: 'bm_801',
        business_id: 'bm_801',
        business_name: 'Starfall Global BM',
        facebook_id: 'fb_801',
        accounts: ['act_10001'],
        pages: ['page_1'],
        pixels: ['pixel_1'],
        updated_at: now,
      },
    ]);
  if (path === '/fb_resource/pages')
    return paginated([
      {
        _id: 'page_1',
        name: 'Starfall Quest',
        username: 'starfallquest',
        fan_count: 128_400,
        followers_count: 136_800,
        is_published: true,
        verification_status: 'verified',
        updated_at: now,
      },
    ]);
  if (path === '/fb_resource/pixels')
    return paginated([
      {
        _id: 'pixel_1',
        name: 'Starfall Purchase Pixel',
        owner_business: 'bm_801',
        last_fired_time: now,
        is_unavailable: false,
        updated_at: now,
      },
    ]);

  if (path === '/tasks/' || path === '/tasks')
    return paginated([
      {
        id: 'task-1',
        task_type: '账户同步',
        game_platform: 'Starfall 全球增长',
        description: '同步 Facebook 广告账户与像素',
        related_users: ['王投手'],
        status: 'in_progress',
        create_time: '2026-08-07 15:00:00',
        deadline: '2026-08-07 18:00:00',
      },
      {
        id: 'task-2',
        task_type: '素材归档',
        game_platform: 'Orbit 海外发行',
        description: '归档本周已验收素材',
        related_users: ['陈素材', '林策划'],
        status: 'initiated',
        create_time: '2026-08-07 14:20:00',
        deadline: '2026-08-08 12:00:00',
      },
      {
        id: 'task-3',
        task_type: '日报生成',
        game_platform: 'Starfall 全球增长',
        description: '生成投放与归因日报',
        related_users: ['赵优化'],
        status: 'completed',
        create_time: '2026-08-07 09:00:00',
        deadline: null,
      },
    ]);

  if (path === '/ad-config/records')
    return {
      items: [
        {
          _id: 'config-1',
          account_id: 'act_10001',
          account_name: 'Starfall ID Main',
          ad_set_id: null,
          campaign_id: 'campaign-1001',
          created_at: now,
          date: null,
          error: null,
          include_related: true,
          level: 'campaign',
          object_id: 'campaign-1001',
          pull_type: 'config',
          real_name: '王投手',
          request_id: 'req-config-1',
          status: 'done',
        },
        {
          _id: 'config-2',
          account_id: 'act_10003',
          account_name: 'Orbit BR Main',
          ad_set_id: 'adset-2001',
          campaign_id: 'campaign-2001',
          created_at: now,
          date: null,
          error: null,
          include_related: false,
          level: 'adset',
          object_id: 'adset-2001',
          pull_type: 'config',
          real_name: '赵优化',
          request_id: 'req-config-2',
          status: 'pending',
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
    };

  if (path === '/platform-configs')
    return demoPlatformConfigs.map((item) => ({
      id: item._id,
      name: item.game_platform,
      value: item._id,
      platform: 'facebook',
      raw: item,
    }));
  if (path === '/media-buyers')
    return [
      {
        id: 'buyer-1',
        name: '王投手',
        real_name: '王敏',
        username: 'wang.pitcher',
        project_id: 'platform-starfall',
      },
      {
        id: 'buyer-2',
        name: '赵优化',
        real_name: '赵宁',
        username: 'zhao.optimizer',
        project_id: 'platform-orbit',
      },
    ];
  if (path === '/automation-rules/options') return automationOptions();
  if (path === '/automation-rules')
    return paginated([
      {
        id: 'rule-1',
        rule_name: 'ROAS 低于 2.2 自动降预算',
        project_ids: ['platform-starfall'],
        project_id: 'platform-starfall',
        platform: 'facebook',
        media_buyer: '王投手',
        account_id: 'act_10001',
        account_name: 'Starfall ID Main',
        agent_line: 'Starfall-FB-ID',
        campaign_id: 'campaign-1001',
        campaign_name: 'ID_RewardHook_AEO',
        levels: ['campaign'],
        enabled: true,
        auto_execute: true,
        condition_logic: 'AND',
        conditions: [
          {
            metric: 'purchase_roas',
            operator: 'lte',
            time_window: 'today',
            value: 2.2,
            value_min: null,
            value_max: null,
          },
        ],
        actions: [
          {
            action_type: 'daily_budget',
            direction: 'decrease',
            unit: 'percent',
            value: 20,
            limit_type: 'min',
            limit_value: 100,
          },
        ],
        notification: { channel: 'feishu', target: '增长告警群' },
        schedule: {
          frequency: 'hourly',
          timezone: 'Asia/Shanghai',
          custom_check_times: [],
          custom_cron: null,
          daily_check_times: [],
          effective_ranges: [],
          effective_type: 'long_term',
        },
        target_scope: {
          campaign_ids: ['campaign-1001'],
          adset_ids: [],
          ad_ids: [],
        },
        schedule_summary: '每小时',
        condition_summary: 'ROAS ≤ 2.2',
        action_summary: '预算降低 20%',
        target_summary: '1 个广告系列',
        created_at: '2026-07-28',
        updated_at: now,
        last_execution: {
          checked_at: now,
          status: 'success',
          message: '未触发',
        },
      },
      {
        id: 'rule-2',
        rule_name: '注册成本高于 18 暂停广告',
        project_ids: ['platform-orbit'],
        project_id: 'platform-orbit',
        platform: 'facebook',
        media_buyer: '赵优化',
        account_id: 'act_10003',
        account_name: 'Orbit BR Main',
        agent_line: 'Orbit-Kwai-BR',
        campaign_id: 'campaign-2001',
        campaign_name: 'BR_UGC_LocalVoice',
        levels: ['ad'],
        enabled: true,
        auto_execute: false,
        condition_logic: 'AND',
        conditions: [
          {
            metric: 'registration_cost',
            operator: 'gte',
            time_window: 'today',
            value: 18,
            value_min: null,
            value_max: null,
          },
        ],
        actions: [{ action_type: 'status', status: 'paused' }],
        notification: { channel: 'telegram', target: 'orbit-alerts' },
        schedule: {
          frequency: 'every_2_hours',
          timezone: 'Asia/Shanghai',
          custom_check_times: [],
          custom_cron: null,
          daily_check_times: [],
          effective_ranges: [],
          effective_type: 'long_term',
        },
        target_scope: { campaign_ids: [], adset_ids: [], ad_ids: ['ad-2001'] },
        schedule_summary: '每 2 小时',
        condition_summary: '注册成本 ≥ 18',
        action_summary: '暂停广告',
        target_summary: '1 个广告',
        created_at: '2026-08-01',
        updated_at: now,
      },
    ]);
  if (path === '/automation-rule-records/pending-summary')
    return {
      ai_suggestion_count: 2,
      rule_suggestion_count: 3,
      total_pending_count: 5,
    };
  if (path === '/kpi-baseline-rules/options')
    return {
      agent_targets: [
        {
          agent_line: 'Starfall-FB-ID',
          label: 'Starfall / Facebook / ID',
          placer_id: '王投手',
          platform: 'facebook',
          project_id: 'platform-starfall',
          project_name: 'Starfall 全球增长',
        },
        {
          agent_line: 'Orbit-Kwai-BR',
          label: 'Orbit / Kwai / BR',
          placer_id: '赵优化',
          platform: 'kwai',
          project_id: 'platform-orbit',
          project_name: 'Orbit 海外发行',
        },
      ],
      condition_logics: [
        { code: 'AND', name: '全部满足' },
        { code: 'OR', name: '任一满足' },
      ],
      delta_types: [
        { code: 'percent', name: '百分比', unit: '%' },
        { code: 'fixed', name: '固定值' },
      ],
      directions: [
        { code: 'above', name: '高于' },
        { code: 'below', name: '低于' },
      ],
      metrics: [
        { code: 'daily_spend', name: '日消耗', unit: 'USD' },
        { code: 'purchase_cost', name: '付费成本', unit: 'USD' },
        { code: 'subscription_cost', name: '订阅成本', unit: 'USD' },
      ],
      schedule: { frequency: 'hourly', name: '每小时检查' },
    };
  if (path === '/kpi-baseline-rules')
    return paginated([
      {
        id: 'kpi-rule-1',
        rule_name: 'Starfall 付费成本基线',
        agent_line: 'Starfall-FB-ID',
        platform: 'facebook',
        project_id: 'platform-starfall',
        project_name: 'Starfall 全球增长',
        condition_logic: 'AND',
        conditions: [
          {
            metric: 'purchase_cost',
            direction: 'above',
            delta_type: 'percent',
            threshold: 20,
          },
        ],
        enabled: true,
        notification: { channel: 'feishu', target: '增长告警群' },
        severity: 'warning',
        last_evaluated_at: now,
        last_snapshot_at: now,
      },
    ]);
  if (path === '/alert-rules/overview')
    return {
      enabled_rule_count: 8,
      total_rule_count: 10,
      last_updated_at: now,
      category_counts: [
        { category: 'cost', name: '成本', count: 4 },
        { category: 'conversion', name: '转化', count: 3 },
        { category: 'creative', name: '素材', count: 3 },
      ],
      trigger_stats: {
        days: 7,
        total: 18,
        by_severity: [
          { severity: 'critical', name: '严重', count: 3, daily_average: 0.43 },
          { severity: 'warning', name: '警告', count: 15, daily_average: 2.14 },
        ],
        top_rules: [
          { rule_id: 'rule-1', rule_name: 'ROAS 低于基线', count: 6 },
        ],
      },
      sync: { refresh_seconds: 60, data_source_status: 'normal' },
    };
  if (path === '/notification-channels')
    return {
      items: [
        {
          channel: 'feishu',
          name: '飞书',
          target_name: '增长告警群',
          status: 'connected',
          status_name: '已连接',
          last_checked_at: now,
        },
        {
          channel: 'telegram',
          name: 'Telegram',
          target_name: 'orbit-alerts',
          status: 'connected',
          status_name: '已连接',
          last_checked_at: now,
        },
      ],
    };
  if (path === '/alert-realtime/feed')
    return {
      generated_at: now,
      items: [
        {
          id: 'alert-1',
          rule_id: 'rule-1',
          severity: 'critical',
          severity_label: '严重',
          rule_type: 'cost',
          rule_type_label: '成本',
          tag: 'ROAS',
          title: 'Starfall 印尼系列 ROAS 低于基线',
          level: 'campaign',
          object_id: 'campaign-1001',
          object_name: 'ID_RewardHook_AEO',
          placer_id: '王投手',
          project_name: 'Starfall 全球增长',
          platform: 'Facebook',
          minutes_ago: 8,
          checked_at: now,
          metrics: [
            {
              code: 'purchase_roas',
              label: 'ROAS',
              value: 1.86,
              display: '1.86',
              target: 2.2,
              target_display: '2.20',
            },
          ],
          actions: [
            { type: 'pause', label: '暂停广告', style: 'danger' },
            { type: 'view', label: '查看详情', style: 'secondary' },
          ],
          status: 'action_pending',
          is_mock: true,
        },
        {
          id: 'alert-2',
          rule_id: 'rule-2',
          severity: 'warning',
          severity_label: '观察',
          rule_type: 'conversion',
          rule_type_label: '转化',
          tag: 'CPP',
          title: 'Orbit 巴西系列付费成本上升',
          level: 'adset',
          object_id: 'adset-2001',
          object_name: 'BR_UGC_LocalVoice',
          placer_id: '赵优化',
          project_name: 'Orbit 海外发行',
          platform: 'Facebook',
          minutes_ago: 16,
          checked_at: now,
          metrics: [
            {
              code: 'purchase_cost',
              label: '付费成本',
              value: 19.4,
              display: '$19.40',
              change_rate: 22.8,
              change_display: '+22.8%',
            },
          ],
          actions: [
            { type: 'snooze', label: '稍后提醒', style: 'secondary' },
            { type: 'view', label: '查看详情', style: 'secondary' },
          ],
          status: 'pending',
          is_mock: true,
        },
      ],
      minutes: 30,
      summary: { critical: 1, info: 0, total: 2, warning: 1 },
      total: 2,
    };

  if (path.startsWith('/superset/'))
    return path.includes('fetchGuestToken')
      ? { token: 'REDACTED_REFERENCE_SECRET' }
      : 'demo-dashboard';

  return undefined;
}

export function resolveDemoMock(request: DemoMockRequest): DemoMockResult {
  const path = normalizedPath(request);
  if (!isDemoMockEnabled) return { data: undefined, matched: false };
  const data = getMockData(path, request);
  return { data, matched: data !== undefined };
}
