// Advertiser Account Types
export interface PublicPageOption {
  id: string;
  label: string;
  name: string;
  personId?: string; // 所属个号ID
  personName?: string; // 所属个号名称
  picture?: string; // 主页头像
  value: string;
}

export interface PixelOption {
  id: string;
  label: string;
  name: string;
  value: string;
}

// 个号账户结构
export interface PersonAccount {
  id: string; // 主页ID
  name: string; // 主页名称
  person_id: string;
}

// 个号与主页的映射关系
export interface AccountAndPage {
  [personName: string]: PersonAccount[];
}

// 新API响应结构
export interface NewApiAccountData {
  ad_account_id: string;
  ad_account_name: string;
  balance?: number;
  person_and_page: AccountAndPage;
  pixels: Array<{ id: string; name: string }>;
  spend_cap?: number;
  status: string;
}

export interface Advertiser {
  accountId: string;
  accountName: string;
  bm: string;
  currency: string;
  id: string;
  pixelOptions: PixelOption[];
  publicPage: string;
  publicPageOptions: PublicPageOption[];
  selectedPixel?: string;
  selectedPublicPage?: string;
  status: string;
}

export interface AdvertiserItem {
  [key: string]: any; // 允许其他动态字段
  account: string;
  id: string;
  name: string;
  personAccountName?: string;

  personId?: string;
  pixel?: string;

  // 公共主页和像素
  publicPage?: string;
  status: string;
}

// 广告账户数据结构 (来自任务线 API 的完整记录)
export interface AdvertiserData {
  [key: string]: any;
  // 账户信息
  accountId: string; // 广告账户ID

  accountName: string; // 广告账户名称
  balance?: number; // 账户余额
  bmName?: string; // 所属BM

  dealerName?: string; // 投放师
  id: string;

  // 个号
  personAccountOptions?: Array<{ name: string; person_id: string }>;
  // 像素
  pixelOptions?: PixelOption[];

  projectName?: string; // 项目名称
  // 公共主页
  publicPageOptions?: PublicPageOption[];
  regionName?: string; // 投放地区
  selectedPersonAccount?: string; // 选中的个号名称
  selectedPersonId?: string; // 选中的个号ID
  selectedPixel?: string;

  selectedPublicPage?: string;
  spendCap?: number; // 账户限额
  status: string; // 状态
  taskCode?: string; // 任务线编号
  // 任务信息
  taskName?: string; // 任务线名称
  url?: string; // 投放链接
}

// Product Configuration Types
export interface SelectedProduct {
  [key: string]: any; // 允许其他动态字段
  advertisers?: AdvertiserItem[];
  projectName: string;
  regionName: string;
  taskCode: string;
  taskName: string;
  url: string;
  accounts_total?: number;
  accounts_page?: number;
  accounts_page_size?: number;
  // 接口返回的任务线信息字段
  任务线名称?: string;
  任务线编号?: string;
  公共主页ID?: null | string;
  公共主页名称?: null | string;
  广告账户ID?: null | string;
  所属BM?: null | string;
  投放地区?: string;
  投放链接?: string;
}

// Series and Region Group Types
export interface RegionGroup {
  ageRangeEnd: number;
  ageRangeStart: number;
  ageStart: number;
  applicationId?: string; // 应用ID (当转化发生位置为APP时)
  billingEvent: string; // 计费事件
  conversionGoal?: string; // 转化事件
  conversionLocation?: string; // 转化发生位置
  country?: string; // 国家代码
  deliveryPosition: string;
  // 设备平台
  device_platforms?: Array<'desktop' | 'mobile'>;
  gender: string;
  id: string;
  // 动态素材开关
  isDynamicCreative?: boolean;
  // 系统面板展开状态
  isExpanded?: boolean;
  // 进阶赋能型受众
  isNewModelEnabled?: boolean;
  language?: string[];
  name: string;
  objectStoreUrl?: string; // 应用商店链接 (当转化发生位置为APP时)
  optimizationTarget: string;
  // 发布平台
  publisher_platforms?: Array<
    | 'audience_network'
    | 'facebook'
    | 'instagram'
    | 'messenger'
    | 'threads'
    | 'whatsapp'
  >;
  // 包含的具体设备列表，如 ['Android_Smartphone', 'Android_Tablet']
  user_device?: string[];
  // 操作系统
  user_os?: Array<'Android' | 'iOS'>;
  // 操作系统版本（格式: '[系统]_ver_[版本]_and_above'）
  user_os_version?: string;
}

export interface SeriesSettings {
  autoRegulationIdentity?: boolean;
  contextualMultiAds?: boolean;
  // OFF=关闭, 不下发 brand_safety_content_filter_levels
  inventoryFilterLevel?: 'OFF' | 'RELAXED' | 'STANDARD' | 'STRICT';
  budget: number;
  budgetType: string;
  currency: string;
  flowOptimization: string;
  flowOptimizationAmount: number;
  objectiveType: string;
  specialAdCategories?: string[];
  specialAdCountries?: string[];
  optimizationMethod: string;
  purchaseType: string;
  seriesType: string;
  targetPrice: string;
  targetValue: string;
}

export interface SeriesData {
  id: string;
  name: string;
  regionGroups: RegionGroup[];
  seriesSettings: SeriesSettings;
}

// Material Types
export interface MaterialTreeItem {
  badge?: number;
  children?: MaterialTreeItem[];
  icon?: string;
  key: string;
  title: string;
}

export interface MaterialItem {
  // 允许其他动态字段
  [key: string]: any;
  callToAction?: string; // 行动号召
  displayLink?: string; // 广告中显示的链接
  cpi?: number;
  ctr?: number;
  description?: string;
  filename: string; // 原始文件名（含扩展名）
  filetype?: 'image' | 'video'; // 素材类型
  id: string;
  // 懒加载字段
  img?: string; // Base64缩略图
  installs?: number;
  isUsedToday?: boolean;

  materialId: string;
  name: string; // 素材显示名称
  purchaseCount?: number;
  purchaseValue?: number;
  registrations?: number;
  roas?: number;
  // 动态指标字段（从API返回）
  spend?: number;
  thumbnail?: string;
  title?: string;
  unique_name: string; // 用于图片加载的 basename

  uploadTime: string;

  usageCount?: number;
  isOriginalPost?: boolean;
  postId?: string;
  chatToolData?: {
    greeting: string;
    greetingType: string;
    questions: { autoReply: string; question: string }[];
    reengagementEnabled: boolean;
    reengagementText: string;
  };
  chatToolTemplateName?: string;
  enhancement?: CreativeEnhancement;
}

// 创意增强配置
export interface CreativeEnhancement {
  // 图片&视频共有必要功能
  show_summary: boolean;
  inline_comment: boolean;
  enhance_cta: boolean;
  reveal_details_over_time: boolean;
  show_destination_blurbs: boolean;
  // 图片必要
  image_brightness_and_contrast: boolean;
  // 图片优化
  image_templates: boolean;
  image_touchups: boolean;
  add_music: boolean;
  image_animation: boolean;
  // 视频必要
  video_filtering: boolean;
  // 视频优化
  detail_to_layout: boolean;
  video_auto_crop: boolean;
  // 共用优化
  text_optimizations: boolean;
  text_transformation_types: boolean;
  website_destination_optimization: boolean;
}

// 素材选择API响应类型
export interface MaterialSelectionResponse {
  columns: string[];
  data: MaterialItem[];
  total: number;
}

// 素材组绑定关系
export interface GroupBinding {
  type: 'random' | 'tag' | 'account' | 'regionGroup';
  accountId?: string;
  regionGroupPath?: [string, string];
}

// 素材组
export interface MaterialGroup {
  id: string;
  name: string;
  materials: MaterialItem[];
  selectedIds: string[];
  binding: GroupBinding;
}
