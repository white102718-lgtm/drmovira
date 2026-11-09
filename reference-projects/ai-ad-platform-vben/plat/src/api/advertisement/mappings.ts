/**
 * 广告参数映射常量和工具函数
 */

// 系列类型(objective)映射
export const OBJECTIVE_MAP: Record<string, string> = {
  销量: 'OUTCOME_SALES',
  流量: 'OUTCOME_TRAFFIC',
  潜在客户: 'OUTCOME_LEADS',
  互动: 'OUTCOME_ENGAGEMENT',
  认知度: 'OUTCOME_AWARENESS',
  应用推广: 'OUTCOME_APP_PROMOTION',
};

// 优化目标映射
export const OPTIMIZATION_GOAL_MAP: Record<string, string> = {
  站外转化: 'OFFSITE_CONVERSIONS',
  价值优化: 'VALUE',
  应用安装量: 'APP_INSTALLS',
  链接点击: 'LINK_CLICKS',
};

// 投放平台映射
export const PUBLISHER_PLATFORMS_MAP: Record<string, string[]> = {
  网站: [''],
  Facebook: [''],
  Instagram: [''],
  全部: [''],
};

// 性别映射
export const GENDER_MAP: Record<string, number[]> = {
  男: [1],
  女: [2],
};

/**
 * 预算转换: USD -> 分
 * @param budget 美元金额
 * @returns 分
 */
export function convertBudgetToCents(budget: number): number {
  return Math.round(budget * 100);
}

/**
 * 映射系列类型
 */
export function mapObjective(seriesType: string): string {
  return OBJECTIVE_MAP[seriesType] || 'OUTCOME_SALES';
}

/**
 * 映射投放平台
 */
export function mapPublisherPlatforms(deliveryPosition: string): string[] {
  return PUBLISHER_PLATFORMS_MAP[deliveryPosition] ?? [];
}

/**
 * 映射性别
 */
export function mapGender(gender: string): number[] | undefined {
  return GENDER_MAP[gender];
}

export const CTA_TYPES = {
  // 通用选项
  COMMON: [
    'ORDER_NOW',      // 立即订购
    'SUBSCRIBE',      // 订阅
    'LEARN_MORE',     // 详细了解
    'DOWNLOAD',       // 下载
    'BOOK_NOW',       // 立即预定
    'SHOP_NOW',       // 去逛逛
    'MESSAGE_PAGE',   // 发消息
    'LISTEN_NOW',     // 立即收听
    'PLAY_GAME',      // 玩游戏
    'WATCH_MORE',     // 更多视频
    'SIGN_UP',        // 立即注册
  ] as const,

  // 仅图片支持的选项
  IMAGE_ONLY: [
    'BUY_NOW',        // 立即购买
    'USE_APP',        // 使用应用
    'INSTALL_APP',    // 立即安装
  ] as const,

  // 仅视频支持的选项
  VIDEO_ONLY: [
    'NO_BUTTON',      // 无按钮
    'APPLY_NOW',      // 立即申请
    'BUY_TICKETS',    // 购票
    'CONTACT_US',     // 联系我们
    'GET_OFFER',      // 领取优惠
    'GET_QUOTE',      // 立即询价
    'GET_SHOWTIMES',  // 查看场次信息
    'REQUEST_TIME',   // 预约时间
    'SEE_MENU',       // 查看菜单
  ] as const,
} as const;

/**
 * 验证 CTA 类型是否适用于指定素材类型
 */
export function validateCTAForMaterial(
  cta: string,
  filetype: 'image' | 'video'
): boolean {
  // 通用选项
  if (CTA_TYPES.COMMON.includes(cta as any)) {
    return true;
  }

  // 图片专用选项
  if (filetype === 'image' && CTA_TYPES.IMAGE_ONLY.includes(cta as any)) {
    return true;
  }

  // 视频专用选项
  if (filetype === 'video' && CTA_TYPES.VIDEO_ONLY.includes(cta as any)) {
    return true;
  }

  return false;
}
