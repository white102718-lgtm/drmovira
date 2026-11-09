import type { UserInfo } from '@vben/types';

export const DEMO_ROLE_STORAGE_KEY = 'fusion:demo-role-preview:v1';

export type DemoRoleId =
  | 'account-manager'
  | 'admin'
  | 'creative-lead'
  | 'creator'
  | 'finance'
  | 'media-lead'
  | 'operator'
  | 'operator-lead';

export type DemoRoleTodoLevel = 'high' | 'low' | 'medium';

export interface DemoRoleAction {
  icon: string;
  label: string;
  path: string;
}

export interface DemoRoleMetric {
  change: string;
  icon: string;
  label: string;
  value: number | string;
}

export interface DemoRoleTodo {
  description: string;
  id: string;
  level: DemoRoleTodoLevel;
  targetPath: string;
  title: string;
}

export interface DemoRoleProfile {
  avatar: string;
  department: string;
  description: string;
  homePath: string;
  id: DemoRoleId;
  label: string;
  metrics: readonly DemoRoleMetric[];
  quickActions: readonly DemoRoleAction[];
  realName: string;
  roles: readonly string[];
  summary: string;
  todos: readonly DemoRoleTodo[];
  userId: string;
  username: string;
}

export interface DemoRoleStorage {
  getItem(key: string): null | string;
  removeItem(key: string): void;
  setItem(key: string, value: string): void;
}

const defaultQuickActions: readonly DemoRoleAction[] = [
  {
    icon: 'lucide:list-todo',
    label: '查看任务中心',
    path: '/workbench/tasks',
  },
  {
    icon: 'lucide:briefcase-business',
    label: '查看项目',
    path: '/fusion/projects',
  },
];

/**
 * These profiles are a local Demo-only viewing aid.  They deliberately do not
 * represent production RBAC or server-side data scopes; the production source
 * remains the authenticated /users/info response and the server permission API.
 */
export const demoRoleProfiles: readonly DemoRoleProfile[] = [
  {
    avatar: '',
    department: '客户成功部',
    description: '维护客户项目资料、日报与交付状态。',
    homePath: '/home',
    id: 'account-manager',
    label: 'AM',
    metrics: [
      {
        change: '其中 5 个投放中',
        icon: 'lucide:briefcase-business',
        label: '负责项目',
        value: 6,
      },
      {
        change: '今日需要跟进',
        icon: 'lucide:clipboard-list',
        label: '项目待办',
        value: 4,
      },
      {
        change: '素材与资源状态正常',
        icon: 'lucide:circle-check-big',
        label: '健康项目',
        value: 5,
      },
      {
        change: '1 个客户待反馈',
        icon: 'lucide:message-circle-more',
        label: '客户反馈',
        value: 1,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:briefcase-business',
        label: '维护项目资料',
        path: '/fusion/projects',
      },
      {
        icon: 'lucide:clipboard-list',
        label: '查看项目待办',
        path: '/workbench/tasks',
      },
    ],
    realName: '顾明',
    roles: ['account_manager'],
    summary: '项目日报 · 客户反馈 · 项目健康度',
    todos: [
      {
        description: '补齐 Starfall 全球增长的产品资料与本周日报链接。',
        id: 'am-project-1',
        level: 'high',
        targetPath: '/fusion/projects',
        title: '补充项目资料：Starfall 全球增长',
      },
      {
        description: '确认 Pixel Quest 日本首发素材交付是否满足客户需求。',
        id: 'am-project-2',
        level: 'medium',
        targetPath: '/workbench/tasks',
        title: '确认客户反馈：Pixel Quest 日本',
      },
    ],
    userId: 'user-6',
    username: 'gu.account-manager',
  },
  {
    avatar: '',
    department: '全球发行部',
    description: '管理投放项目、分配投手并验收素材交付。',
    homePath: '/home',
    id: 'operator-lead',
    label: '投放负责人',
    metrics: [
      {
        change: '3 名投手协作',
        icon: 'lucide:users-round',
        label: '负责项目',
        value: 3,
      },
      {
        change: '等待分配投手',
        icon: 'lucide:user-round-plus',
        label: '待分配投放任务',
        value: 2,
      },
      {
        change: '需验收后才能发布',
        icon: 'lucide:package-check',
        label: '待验收素材',
        value: 3,
      },
      {
        change: '需要处理',
        icon: 'lucide:triangle-alert',
        label: '异常广告',
        value: 1,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:plus-square',
        label: '新建投放任务',
        path: '/workbench/tasks/create-delivery',
      },
      {
        icon: 'lucide:package-check',
        label: '验收素材交付',
        path: '/workbench/tasks',
      },
      {
        icon: 'lucide:rocket',
        label: '创建多平台广告',
        path: '/fusion/ads/create',
      },
    ],
    realName: '林悦',
    roles: ['operator_leader'],
    summary: '项目执行 · 任务分配 · 素材验收',
    todos: [
      {
        description: 'Starfall 美国暑期批量投放准备就绪，需要分配投手。',
        id: 'delivery-lead-task-1',
        level: 'high',
        targetPath: '/workbench/tasks',
        title: '分配投放任务：Starfall 美国暑期',
      },
      {
        description: '验收 Pixel Quest 日本首轮投放交付素材。',
        id: 'delivery-lead-task-2',
        level: 'medium',
        targetPath: '/workbench/tasks',
        title: '验收素材：Pixel Quest 日本',
      },
    ],
    userId: 'user-3',
    username: 'lin.operator-lead',
  },
  {
    avatar: '',
    department: '增长一部',
    description: '执行投放、优化广告效果并使用已分配资产。',
    homePath: '/home',
    id: 'operator',
    label: '投手',
    metrics: [
      {
        change: '当前负责项目',
        icon: 'lucide:briefcase-business',
        label: '我的项目',
        value: 2,
      },
      {
        change: '今日平台消耗',
        icon: 'lucide:wallet-cards',
        label: '今日消耗',
        value: 'US$18.2K',
      },
      {
        change: '目标 2.20',
        icon: 'lucide:chart-no-axes-combined',
        label: 'ROAS',
        value: '2.48',
      },
      {
        change: '账户、Pixel 与主页',
        icon: 'lucide:boxes',
        label: '我的资产',
        value: 7,
      },
    ],
    quickActions: [
      { icon: 'lucide:rocket', label: '创建广告', path: '/fusion/ads/create' },
      {
        icon: 'lucide:folder-open',
        label: '查看我的素材',
        path: '/materials/material-library',
      },
      {
        icon: 'lucide:list-todo',
        label: '处理投放任务',
        path: '/workbench/tasks',
      },
    ],
    realName: '王敏',
    roles: ['operator'],
    summary: '执行投放 · 效果优化 · 已分配资产',
    todos: [
      {
        description: '根据 ROAS 波动调整 Starfall SEA 广告组预算。',
        id: 'operator-task-1',
        level: 'high',
        targetPath: '/fusion/ads/create',
        title: '优化广告组：Starfall SEA',
      },
      {
        description: '选择已验收素材，为 Pixel Quest 新建日本首发广告。',
        id: 'operator-task-2',
        level: 'medium',
        targetPath: '/materials/material-library',
        title: '选择素材并创建广告',
      },
    ],
    userId: 'user-1',
    username: 'wang.pitcher',
  },
  {
    avatar: '',
    department: '创意中心',
    description: '接收创意需求、分配素材师并汇总交付。',
    homePath: '/home',
    id: 'creative-lead',
    label: '素材负责人',
    metrics: [
      {
        change: '等待分配素材师',
        icon: 'lucide:user-round-plus',
        label: '待分配创意任务',
        value: 3,
      },
      {
        change: '团队本周制作中',
        icon: 'lucide:palette',
        label: '制作中',
        value: 12,
      },
      {
        change: '等待投放验收',
        icon: 'lucide:package-check',
        label: '待验收',
        value: 4,
      },
      {
        change: '超过截止时间',
        icon: 'lucide:clock-3',
        label: '延期任务',
        value: 1,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:list-todo',
        label: '分配素材任务',
        path: '/workbench/tasks',
      },
      {
        icon: 'lucide:layout-dashboard',
        label: '查看素材看板',
        path: '/materials/material-board',
      },
      {
        icon: 'lucide:package-check',
        label: '汇总素材交付',
        path: '/requirement/pool',
      },
    ],
    realName: '许栩',
    roles: ['creative_lead'],
    summary: '创意任务池 · 素材师产能 · 交付汇总',
    todos: [
      {
        description: '为“巴西口播视频本地化”分配素材师并确认截止时间。',
        id: 'creative-lead-task-1',
        level: 'high',
        targetPath: '/workbench/tasks',
        title: '分配素材师：巴西口播视频本地化',
      },
      {
        description: '汇总 Starfall 竖版视频，并提交给投放负责人验收。',
        id: 'creative-lead-task-2',
        level: 'medium',
        targetPath: '/requirement/pool',
        title: '汇总待验收素材：Starfall',
      },
    ],
    userId: 'user-7',
    username: 'xu.creative-lead',
  },
  {
    avatar: '',
    department: '创意中心',
    description: '完成素材制作、上传版本并提交交付。',
    homePath: '/home',
    id: 'creator',
    label: '素材师',
    metrics: [
      {
        change: '今日需开始制作',
        icon: 'lucide:clapperboard',
        label: '待制作',
        value: 2,
      },
      {
        change: '视频与图片制作',
        icon: 'lucide:palette',
        label: '制作中',
        value: 4,
      },
      {
        change: '等待提交交付',
        icon: 'lucide:upload-cloud',
        label: '待提交',
        value: 1,
      },
      {
        change: '本周已交付',
        icon: 'lucide:circle-check-big',
        label: '已完成',
        value: 8,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:palette',
        label: '进入 AI 创意工作台',
        path: '/fusion/ai-studio',
      },
      {
        icon: 'lucide:upload-cloud',
        label: '上传制作素材',
        path: '/requirement/myTask',
      },
      {
        icon: 'lucide:list-todo',
        label: '查看我的制作任务',
        path: '/requirement/myTask',
      },
    ],
    realName: '陈晨',
    roles: ['creator'],
    summary: '制作任务 · AI 创作 · 上传与提交',
    todos: [
      {
        description: '完成 Pixel Quest 日本首发竖版视频的第二个版本。',
        id: 'creator-task-1',
        level: 'high',
        targetPath: '/requirement/myTask',
        title: '制作素材：Pixel Quest 竖版视频',
      },
      {
        description: '补传 Starfall UGC 素材的封面与字幕文件。',
        id: 'creator-task-2',
        level: 'medium',
        targetPath: '/requirement/myTask',
        title: '补齐交付素材附件',
      },
    ],
    userId: 'user-2',
    username: 'chen.creator',
  },
  {
    avatar: '',
    department: '媒介资源中心',
    description: '管理账号与资产生命周期，处理申请、分配和回收。',
    homePath: '/home',
    id: 'media-lead',
    label: '媒介负责人',
    metrics: [
      {
        change: '账户、Pixel 与主页资源',
        icon: 'lucide:boxes',
        label: '可用资产',
        value: 28,
      },
      {
        change: '申请等待审批',
        icon: 'lucide:clipboard-check',
        label: '待审批',
        value: 5,
      },
      {
        change: '异常、额度不足与即将回收',
        icon: 'lucide:triangle-alert',
        label: '资源风险',
        value: 3,
      },
      {
        change: '本周已完成',
        icon: 'lucide:rotate-ccw',
        label: '待回收',
        value: 2,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:clipboard-check',
        label: '处理资源审批',
        path: '/workbench/approvals',
      },
      {
        icon: 'lucide:boxes',
        label: '查看媒介资产',
        path: '/media-resources/accounts',
      },
    ],
    realName: '沈岚',
    roles: ['media_manager'],
    summary: '资源审批 · 资产库存 · 分配与回收',
    todos: [
      {
        description: '审批 Starfall Facebook 广告账户申请，并按项目分配。',
        id: 'media-lead-task-1',
        level: 'high',
        targetPath: '/workbench/approvals',
        title: '审批资源申请：Starfall Facebook 账户',
      },
      {
        description: '处理即将过期的 TikTok 日本账户授权。',
        id: 'media-lead-task-2',
        level: 'medium',
        targetPath: '/media-resources/account-management',
        title: '处理账户风险：TikTok 日本授权到期',
      },
    ],
    userId: 'user-8',
    username: 'shen.media-lead',
  },
  {
    avatar: '',
    department: '财务部',
    description: '维护项目收入、成本与利润核算。',
    homePath: '/home',
    id: 'finance',
    label: '财务',
    metrics: [
      {
        change: '本月已确认服务费',
        icon: 'lucide:wallet-cards',
        label: '项目收入',
        value: 'US$436K',
      },
      {
        change: '渠道、账户与素材成本',
        icon: 'lucide:receipt-text',
        label: '待核对成本',
        value: 'US$178K',
      },
      {
        change: '本月利润',
        icon: 'lucide:badge-dollar-sign',
        label: '项目利润',
        value: 'US$116K',
      },
      {
        change: '等待结算资料',
        icon: 'lucide:file-warning',
        label: '待结算项目',
        value: 2,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:chart-no-axes-combined',
        label: '查看成本与利润',
        path: '/data-report',
      },
      {
        icon: 'lucide:briefcase-business',
        label: '核对项目结算',
        path: '/fusion/projects',
      },
    ],
    realName: '唐玥',
    roles: ['finance'],
    summary: '收入与成本 · 项目利润 · 结算核对',
    todos: [
      {
        description: '核对 Starfall 全球增长 7 月账号成本与渠道账单。',
        id: 'finance-task-1',
        level: 'high',
        targetPath: '/data-report',
        title: '核对项目成本：Starfall 全球增长',
      },
      {
        description: '补齐 Pixel Quest 日本素材人工成本后再确认利润。',
        id: 'finance-task-2',
        level: 'medium',
        targetPath: '/fusion/projects',
        title: '补齐素材成本：Pixel Quest 日本',
      },
    ],
    userId: 'user-9',
    username: 'tang.finance',
  },
  {
    avatar: '',
    department: '数据增长部',
    description: '配置用户、角色、权限、流程和系统规则。',
    homePath: '/home',
    id: 'admin',
    label: '管理员',
    metrics: [
      {
        change: '当前已启用账户',
        icon: 'lucide:users-round',
        label: '系统用户',
        value: 48,
      },
      {
        change: '业务角色与系统角色',
        icon: 'lucide:shield-check',
        label: '角色权限',
        value: 9,
      },
      {
        change: '审批、验收与分配规则',
        icon: 'lucide:workflow',
        label: '流程规则',
        value: 12,
      },
      {
        change: '最近 24 小时',
        icon: 'lucide:activity',
        label: '系统告警',
        value: 1,
      },
    ],
    quickActions: [
      {
        icon: 'lucide:users-round',
        label: '管理用户',
        path: '/system-management/users',
      },
      {
        icon: 'lucide:shield-check',
        label: '管理角色权限',
        path: '/system-management/roles',
      },
      {
        icon: 'lucide:workflow',
        label: '查看流程与审批',
        path: '/workbench/approvals',
      },
    ],
    realName: '周宁',
    roles: ['admin'],
    summary: '用户与权限 · 流程配置 · 系统治理',
    todos: [
      {
        description: '为新媒介负责人配置资源审批与资产分配范围。',
        id: 'admin-task-1',
        level: 'high',
        targetPath: '/system-management/users',
        title: '配置用户权限：媒介负责人',
      },
      {
        description: '复核素材验收流程中的抄送与打回节点。',
        id: 'admin-task-2',
        level: 'medium',
        targetPath: '/workbench/approvals',
        title: '复核验收流程配置',
      },
    ],
    userId: 'user-4',
    username: 'zhou.admin',
  },
];

function getDefaultStorage(): DemoRoleStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function getDemoRoleProfile(
  roleId: null | string | undefined,
): DemoRoleProfile | undefined {
  return demoRoleProfiles.find((profile) => profile.id === roleId);
}

export function getDemoRoleAccessToken(profile: DemoRoleProfile): string {
  return `fusion-demo-role:${profile.id}`;
}

export function isDemoRoleAccessToken(token: null | string): boolean {
  return Boolean(token?.startsWith('fusion-demo-'));
}

export function toDemoRoleUserInfo(profile: DemoRoleProfile): UserInfo {
  return {
    avatar: profile.avatar,
    desc: `${profile.label} · ${profile.department}`,
    full_name: profile.realName,
    homePath: profile.homePath,
    realName: profile.realName,
    roles: [...profile.roles],
    token: getDemoRoleAccessToken(profile),
    userId: profile.userId,
    username: profile.username,
  };
}

export function readSelectedDemoRole(
  storage: DemoRoleStorage | null = getDefaultStorage(),
): DemoRoleProfile | undefined {
  const raw = storage?.getItem(DEMO_ROLE_STORAGE_KEY);
  if (!raw) return undefined;
  try {
    const parsed: unknown = JSON.parse(raw);
    let roleId: unknown;
    if (typeof parsed === 'string') {
      roleId = parsed;
    } else if (parsed && typeof parsed === 'object' && 'roleId' in parsed) {
      roleId = (parsed as { roleId?: unknown }).roleId;
    }
    return typeof roleId === 'string' ? getDemoRoleProfile(roleId) : undefined;
  } catch {
    return undefined;
  }
}

export function selectDemoRole(
  roleId: DemoRoleId,
  storage: DemoRoleStorage | null = getDefaultStorage(),
): DemoRoleProfile {
  const profile = getDemoRoleProfile(roleId);
  if (!profile) throw new Error(`Unknown demo role: ${roleId}`);
  storage?.setItem(
    DEMO_ROLE_STORAGE_KEY,
    JSON.stringify({ roleId: profile.id, version: 1 }),
  );
  return profile;
}

export function clearSelectedDemoRole(
  storage: DemoRoleStorage | null = getDefaultStorage(),
) {
  storage?.removeItem(DEMO_ROLE_STORAGE_KEY);
}

export function demoRoleProfilesAsUsers() {
  return demoRoleProfiles.map((profile) => ({
    _id: profile.userId,
    created_at: '2026-08-13',
    department: profile.department,
    full_name: profile.realName,
    name: profile.username,
    permissions: [],
    phone: '演示账号',
    real_name: profile.realName,
    roles: [...profile.roles],
    status: 1,
  }));
}

export { defaultQuickActions };
