import type {
  ApprovalConfig,
  ApprovalNodeConfig,
  DynamicFormField,
  HandlerActionConfig,
  HandlerSource,
} from '#/api/asset-flow';
import type { ApplicationApprovalRole } from '#/domain/application';

import { computed, ref } from 'vue';

import { defineStore } from 'pinia';

import { assetFlowApi } from '#/api/asset-flow';
import {
  createAccountOpeningFormSchema,
  createAccountOpeningHandlerAction,
  normalizeAccountOpeningFormSchema,
} from '#/domain/application/account-opening';
import { resolveDynamicFieldPlaceholder } from '#/domain/application/dynamic-form';
import { PROJECT_CLOSURE_APPLICATION_CODE } from '#/domain/project';
import { DELIVERY_DAILY_REPORT_APPLICATION_CODE } from '#/domain/daily-report-applications';
import { SOCIAL_ASSET_TYPE_OPTIONS } from '#/domain/application/social-assets';

/** 审批目录的内置业务类型；账户后处理动作通过表单中的操作类型区分。 */
/** 审批配置标识；内置配置使用可读编码，新建配置使用系统生成编码。 */
export type ApprovalApplicationType = string;

export const approvalApplicationTypeLabels: Record<string, string> = {
  ACCOUNT_OPENING: '广告户申请',
  ACCOUNT_OPERATION: '广告账户操作申请',
  BM: 'BM 申请',
  BUNDLE: '绑包申请',
  COMPUTER: '电脑申请',
  EMAIL: '邮箱申请',
  [DELIVERY_DAILY_REPORT_APPLICATION_CODE]: '投放日报申请',
  MOBILE: '手机申请',
  PAGE: '主页申请',
  PAYMENT: '打款申请',
  PERSONAL: '个号申请',
  PIXEL: '像素申请',
  [PROJECT_CLOSURE_APPLICATION_CODE]: '项目结项审批',
  STATIC_IP: '静态 IP 申请',
  TG: '社交资产申请',
};

export type ApprovalAssigneeMode = 'department' | 'member' | 'role';
export type ApprovalFlowNodeKind = 'approval' | 'copy' | 'handler';

export interface ApprovalFlowNode {
  approver?: string;
  approverId?: string;
  assigneeMode?: ApprovalAssigneeMode;
  departmentIds?: string[];
  departmentNames?: string[];
  handlerAction?: HandlerActionConfig;
  handlerApprovalNodeId?: string;
  handlerSource?: HandlerSource;
  id: string;
  kind: ApprovalFlowNodeKind;
  label: string;
  role?: ApplicationApprovalRole;
  roleIds?: string[];
  userNames?: string[];
  users?: string[];
}

export interface ApprovalConfigSettings {
  approvalType: 'auto-approve' | 'auto-reject' | 'manual';
  completionMode?: 'handler' | 'pixel-auto-assign';
  handlerAction?: HandlerActionConfig;
}

export interface MediaApprovalConfig {
  applicationDefinitionIds: string[];
  approver: string;
  approverId?: string;
  ccUsers: string[];
  description: string;
  enabled: boolean;
  formFields: DynamicFormField[];
  handlerApprovalNodeId?: string;
  handlerId?: string;
  handlerName?: string;
  handlerSource?: HandlerSource;
  icon: string;
  id: string;
  name: string;
  nodes: ApprovalFlowNode[];
  role: ApplicationApprovalRole;
  settings: ApprovalConfigSettings;
  sortOrder: number;
  status: 'published';
  types: ApprovalApplicationType[];
  updatedAt: string;
  visibility: 'admins' | 'all';
}

const regionOptions = [
  '新加坡',
  '马来西亚',
  '泰国',
  '越南',
  '印度尼西亚',
  '菲律宾',
  '印度',
  '美国',
  '日本',
  '香港',
];

const defaultSettings: ApprovalConfigSettings = {
  approvalType: 'manual',
};

const MAX_SORT_ORDER = 2_147_483_647;

/** 兼容曾使用毫秒时间戳生成的排序值，保证提交值落在后端 INT 字段范围内。 */
function normalizeSortOrder(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  const integer = Math.trunc(value);
  if (integer <= MAX_SORT_ORDER) return integer;
  return Math.min(Math.trunc(integer / 1000), MAX_SORT_ORDER);
}

function field(
  key: string,
  label: string,
  type: DynamicFormField['type'],
  options: Partial<DynamicFormField> = {},
): DynamicFormField {
  return {
    key,
    label,
    required: false,
    type,
    width: type === 'textarea' ? 'full' : 'half',
    ...options,
  };
}

/** 分组标题参与表单排序，但不产生申请数据。 */
function section(
  key: string,
  label: string,
  helpText?: string,
): DynamicFormField {
  return field(key, label, 'section', {
    helpText,
    required: false,
    width: 'full',
  });
}

function commonMaterialFields(): DynamicFormField[] {
  return [
    section('sectionDetails', '申请详情'),
    field('quantity', '数量', 'number', { minValue: 1, required: true }),
    field('region', '地区', 'select', {
      optionSource: 'custom',
      options: regionOptions,
      placeholder: '请选择地区',
    }),
    field('purpose', '说明', 'textarea', {
      maxLength: 200,
      placeholder: '请输入申请说明',
    }),
  ];
}

function officeFields(resourceName: string): DynamicFormField[] {
  return [
    section('sectionOwnership', '申请归属'),
    field('departmentId', '所属部门', 'select', {
      optionSource: 'departments',
      placeholder: '请选择系统部门',
      required: true,
    }),
    field('assigneeId', '使用人', 'select', {
      optionSource: 'users',
      placeholder: '请选择系统人员',
      required: true,
    }),
    field('projectId', '所属项目', 'select', {
      optionSource: 'projects',
      placeholder: '请选择系统项目',
    }),
    section('sectionDetails', `${resourceName}信息`),
    field('quantity', '数量', 'number', { minValue: 1, required: true }),
    field('purpose', '用途说明', 'textarea', {
      maxLength: 200,
      placeholder: `请说明${resourceName}用途及配置要求`,
      required: true,
    }),
  ];
}

/** MPower 办公物料申请字段；各资源类型在 MPower 中共用此表单。 */
function mpowerOfficeMaterialFields(
  resourceName: string,
  options: { email?: boolean; mobile?: boolean } = {},
): DynamicFormField[] {
  return [
    section('sectionDetails', `${resourceName}信息`),
    field('quantity', '数量', 'number', { minValue: 1, required: true }),
    ...(options.email
      ? []
      : [
          field('region', '地区', 'select', {
            optionSource: 'custom',
            options: regionOptions,
            placeholder: '请选择地区',
          }),
        ]),
    ...(options.mobile
      ? [
          field('purpose', '用途', 'select', {
            optionSource: 'custom',
            options: ['FB开发者验证', '谷歌验证', 'FB个号验证', '其它'],
            placeholder: '请选择用途',
            required: true,
          }),
        ]
      : [
          field('purpose', '说明', 'text', {
            maxLength: 200,
            placeholder: '请输入说明',
          }),
        ]),
  ];
}

function seed(
  type: ApprovalApplicationType,
  category: ApplicationApprovalRole,
  _legacyGroupName: string,
  icon: string,
  formFields: DynamicFormField[],
  sortOrder: number,
): MediaApprovalConfig {
  const handlerAction = defaultHandlerAction(type);
  return {
    applicationDefinitionIds: [],
    approver: '',
    ccUsers: [],
    description: `${approvalApplicationTypeLabels[type] ?? type}审批流程`,
    enabled: true,
    formFields,
    icon,
    id: type,
    name: approvalApplicationTypeLabels[type] ?? type,
    nodes: [
      {
        approver: '',
        assigneeMode: 'member',
        id: `${type}-approval`,
        kind: 'approval',
        label: '业务负责人审批',
        role: category,
      },
      {
        approver: '',
        assigneeMode: 'member',
        handlerAction,
        handlerSource: 'fixed-user',
        id: `${type}-handler`,
        kind: 'handler',
        label: '业务办理',
        role: category,
      },
    ],
    role: category,
    settings: { ...defaultSettings, handlerAction },
    sortOrder,
    status: 'published',
    types: [type],
    updatedAt: '',
    visibility: 'all',
  };
}

/** MPower 中审批通过后的业务动作统一由办理人执行。 */
function defaultHandlerAction(
  type: ApprovalApplicationType,
): HandlerActionConfig {
  if (type === 'ACCOUNT_OPENING') {
    return createAccountOpeningHandlerAction();
  }
  if (type === 'TG') {
    return {
      resourceAssignment: {
        assetTypeFieldKey: 'socialAssetType',
        assetTypeSource: 'application',
        channelFieldKey: '',
        enabled: true,
        quantityFieldKey: 'quantity',
      },
    };
  }
  if (
    [
      'BM',
      'COMPUTER',
      'EMAIL',
      'MOBILE',
      'PAGE',
      'PERSONAL',
      'PIXEL',
      'STATIC_IP',
    ].includes(type)
  ) {
    return {
      resourceAssignment: {
        assetTypeSource: 'application',
        channelFieldKey: ['BM', 'PERSONAL', 'PIXEL'].includes(type)
          ? 'channelId'
          : '',
        enabled: true,
        quantityFieldKey: type === 'PAGE' ? 'pageCount' : 'quantity',
      },
    };
  }
  if (type === 'PAYMENT') {
    return {
      formSchema: [
        field('actualAmount', '实际打款金额', 'number', {
          minValue: 0.01,
          required: true,
          validationRule: 'positive-money',
        }),
        field('receiptFileIds', '水单图片', 'image-upload', {
          accept: 'image/*',
          helpText: '支持 1 至 3 张图片，单张不超过 3MB',
          maxCount: 3,
          maxFileSizeMb: 3,
          required: true,
          width: 'full',
        }),
      ],
    };
  }
  const labels: Partial<Record<ApprovalApplicationType, string>> = {
    ACCOUNT_OPERATION: '账户操作结果',
    BUNDLE: '绑包结果',
    COMPUTER: '电脑交付结果',
    EMAIL: '邮箱交付结果',
    MOBILE: '手机交付结果',
    PAGE: '主页交付结果',
    STATIC_IP: '静态 IP 交付结果',
  };
  return {
    formSchema: [
      field('processingResult', labels[type] ?? '办理结果', 'textarea', {
        maxLength: 1000,
        placeholder: '请填写实际办理结果',
        required: true,
        width: 'full',
      }),
    ],
  };
}

const seedConfigs: MediaApprovalConfig[] = [
  seed(
    'ACCOUNT_OPENING',
    'media',
    '媒介与资源',
    'lucide:badge-plus',
    createAccountOpeningFormSchema(),
    5,
  ),
  seed(
    'PERSONAL',
    'media',
    '媒介与资源',
    'lucide:user-round',
    commonMaterialFields(),
    10,
  ),
  seed(
    'BM',
    'media',
    '媒介与资源',
    'lucide:briefcase-business',
    commonMaterialFields(),
    20,
  ),
  seed(
    'PIXEL',
    'media',
    '媒介与资源',
    'lucide:scan-line',
    [
      section('sectionDetails', '像素信息'),
      field('pixelNames', '像素', 'textarea', {
        placeholder: '请输入“像素名称:像素ID”，多个像素以“;”分隔',
        required: true,
        validationRule: 'pixel-list',
      }),
      field('bms', 'BM ID', 'text', {
        placeholder: '请输入 BM ID，多个以“;”分隔',
        required: true,
        validationRule: 'digit-list',
      }),
      field('channel', '渠道', 'text', {
        maxLength: 50,
        placeholder: '请输入渠道名称',
        required: true,
      }),
      field('accountIds', '授权账户 ID', 'textarea', {
        placeholder: '请输入授权账户 ID，多个以“;”分隔',
        required: true,
        validationRule: 'digit-list',
      }),
    ],
    30,
  ),
  seed(
    'TG',
    'media',
    '媒介与资源',
    'lucide:messages-square',
    [
      section('sectionDetails', '社交资产信息'),
      field('socialAssetType', '社交资产类型', 'select', {
        optionSource: 'custom',
        options: [...SOCIAL_ASSET_TYPE_OPTIONS],
        placeholder: '请选择社交资产类型',
        required: true,
      }),
      field('quantity', '数量', 'number', {
        minValue: 1,
        required: true,
      }),
      field('region', '地区', 'select', {
        optionSource: 'custom',
        options: regionOptions,
        placeholder: '请选择地区',
      }),
      field('purpose', '说明', 'textarea', {
        maxLength: 200,
        placeholder: '请输入使用说明',
      }),
    ],
    40,
  ),
  seed(
    'BUNDLE',
    'media',
    '媒介与资源',
    'lucide:package-check',
    [
      section('sectionDetails', '绑包信息'),
      field('accountIds', '账户 ID', 'textarea', {
        placeholder: '请输入账户 ID，多个以“;”分隔',
        required: true,
        validationRule: 'digit-list',
      }),
      field('bindAppLink', '绑定应用链接', 'text', {
        placeholder: '请输入绑定应用链接',
        required: true,
        validationRule: 'url',
      }),
    ],
    50,
  ),
  seed(
    'PAGE',
    'media',
    '媒介与资源',
    'lucide:panels-top-left',
    [
      section('sectionDetails', '主页信息'),
      field('region', '地区', 'select', {
        optionSource: 'custom',
        options: regionOptions,
        placeholder: '请选择地区',
        required: true,
      }),
      field('pageCount', '主页数量', 'number', {
        minValue: 1,
        required: true,
      }),
      field('authBm', '授权 BM', 'text', {
        placeholder: '请输入授权 BM',
        required: true,
        validationRule: 'digit-list',
      }),
    ],
    60,
  ),
  seed(
    'COMPUTER',
    'office',
    '行政与资产',
    'lucide:laptop',
    officeFields('电脑'),
    70,
  ),
  seed(
    'MOBILE',
    'office',
    '行政与资产',
    'lucide:smartphone',
    mpowerOfficeMaterialFields('手机', { mobile: true }),
    80,
  ),
  seed(
    'STATIC_IP',
    'office',
    '行政与资产',
    'lucide:network',
    mpowerOfficeMaterialFields('静态 IP'),
    90,
  ),
  seed(
    'EMAIL',
    'office',
    '行政与资产',
    'lucide:mail',
    mpowerOfficeMaterialFields('邮箱', { email: true }),
    100,
  ),
  seed(
    'PAYMENT',
    'finance',
    '财务管理',
    'lucide:badge-dollar-sign',
    [
      section('sectionOwnership', '申请归属'),
      field('channelId', '渠道', 'select', {
        optionSource: 'channels',
        placeholder: '请选择渠道',
        required: true,
      }),
      section('sectionPayment', '付款信息'),
      field('amount', '备款金额', 'number', {
        minValue: 1,
        required: true,
        validationRule: 'positive-money',
      }),
      field('channelYesterdayCost', '渠道昨日消耗', 'number', {
        autoFill: {
          resultKey: 'channelYesterdayCost',
          source: 'channel-payment-context',
          triggerFieldKey: 'channelId',
        },
        minValue: 0,
        required: true,
        readOnly: true,
      }),
      field('paymentAddress', '收款地址', 'text', {
        autoFill: {
          resultKey: 'paymentAddress',
          source: 'channel-payment-context',
          triggerFieldKey: 'channelId',
        },
        required: true,
        readOnly: true,
      }),
      field('remark', '备注', 'textarea', {
        placeholder: '请输入备注',
      }),
    ],
    110,
  ),
  seed(
    'ACCOUNT_OPERATION',
    'finance',
    '财务管理',
    'lucide:wallet-cards',
    [
      section('sectionOperation', '操作信息'),
      field('accountIds', '广告账户', 'multi-select', {
        optionSource: 'ad-accounts',
        placeholder: '请选择系统账户管理中的广告账户',
        required: true,
      }),
      field('amount', '金额', 'number', {
        applicableApplicationCodes: ['ACCOUNT_RECHARGE', 'ACCOUNT_DEDUCTION'],
        minValue: 0.01,
        required: true,
        validationRule: 'positive-money',
      }),
      field('applyReason', '申请原因', 'select', {
        applicableApplicationCodes: [
          'ACCOUNT_ACTIVE_CLEAR',
          'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
        ],
        optionSource: 'custom',
        options: [
          '项目暂停',
          '账户问题暂停',
          '项目停止',
          '账户不花钱',
          '拒审严重',
          '其它',
        ],
        required: true,
      }),
      field('originalAuthAccount', '原解绑邮箱/BM', 'text', {
        applicableApplicationCodes: ['ACCOUNT_REBIND'],
        placeholder: '请输入原解绑邮箱/BM',
        required: true,
      }),
      field('authAccount', '解绑/换绑邮箱或 BM', 'text', {
        applicableApplicationCodes: ['ACCOUNT_UNBIND', 'ACCOUNT_REBIND'],
        placeholder: '请输入邮箱或 BM',
        required: true,
      }),
      field('remark', '备注', 'textarea', {
        applicableApplicationCodes: [
          'ACCOUNT_ACTIVE_CLEAR',
          'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
          'ACCOUNT_RECYCLE',
        ],
        maxLength: 100,
        placeholder: '请输入备注',
      }),
    ],
    120,
  ),
  seed(
    PROJECT_CLOSURE_APPLICATION_CODE,
    'media',
    '业务与项目',
    'lucide:circle-check-big',
    [
      section('sectionProject', '结项项目信息'),
      field('projectId', '项目', 'select', {
        optionSource: 'projects',
        placeholder: '请选择需要结项的项目',
        required: true,
      }),
      field('settlementAmount', '结算金额', 'number', {
        minValue: 0.01,
        placeholder: '请输入付款金额',
        required: true,
        validationRule: 'positive-money',
      }),
      field('settlementCurrency', '币种', 'select', {
        defaultValue: 'USD - 美元',
        optionSource: 'custom',
        options: ['USD - 美元', 'CNY - 人民币', 'JPY - 日元'],
        required: true,
      }),
      section(
        'sectionApplication',
        '申请信息',
        '请按当前审批类型补充必要字段，提交后将随审批单一并留痕。',
      ),
      field('settlementPeriod', '结算周期', 'date-range', {
        placeholder: '请选择结算周期',
        required: true,
      }),
      field('closureDescription', '结项说明', 'textarea', {
        maxLength: 300,
        placeholder: '请填写项目交付完成情况、结算依据及备注',
        required: true,
        width: 'full',
      }),
    ],
    130,
  ),
  // 固定日报只开放审批流、可见范围和通知配置，禁止通过低代码变更业务字段。
  seed(
    DELIVERY_DAILY_REPORT_APPLICATION_CODE,
    'media',
    '业务与项目',
    'lucide:chart-no-axes-combined',
    [],
    140,
  ),
];

/** 创建审批配置时复用内置业务模板，避免新配置缺少必要的表单和办理节点。 */
export function createApprovalConfigDraft(): MediaApprovalConfig {
  const type = `FLOW_${Date.now().toString(36)}_${Math.random()
    .toString(36)
    .slice(2, 7)}`.toUpperCase();
  return {
    applicationDefinitionIds: [],
    approver: '',
    ccUsers: [],
    description: '',
    enabled: true,
    formFields: [],
    icon: 'lucide:workflow',
    id: type,
    name: '',
    nodes: [
      {
        approver: '',
        assigneeMode: 'member',
        id: `${type}-approval`,
        kind: 'approval',
        label: '审批人',
        role: 'media',
      },
      {
        approver: '',
        assigneeMode: 'member',
        handlerAction: defaultHandlerAction(type),
        handlerSource: 'fixed-user',
        id: `${type}-handler`,
        kind: 'handler',
        label: '业务办理',
        role: 'media',
      },
    ],
    role: 'media',
    settings: {
      approvalType: 'manual',
      handlerAction: defaultHandlerAction(type),
    },
    // 后端排序字段为 INT，打开编辑器前由调用方根据现有配置确定位置。
    sortOrder: 0,
    status: 'published',
    types: [type],
    updatedAt: '',
    visibility: 'all',
  };
}

function cloneField(input: DynamicFormField): DynamicFormField {
  const cloneCondition = (condition: DynamicFormField['visibleWhen']) =>
    condition
      ? {
          ...condition,
          value: Array.isArray(condition.value)
            ? [...condition.value]
            : condition.value,
        }
      : undefined;
  return {
    ...input,
    applicableApplicationCodes: input.applicableApplicationCodes
      ? [...input.applicableApplicationCodes]
      : undefined,
    options: input.options ? [...input.options] : undefined,
    placeholder: resolveDynamicFieldPlaceholder(input),
    requiredWhen: cloneCondition(input.requiredWhen),
    visibleWhen: cloneCondition(input.visibleWhen),
  };
}

const legacyAccountFieldApplications: Record<string, string[]> = {
  amount: ['ACCOUNT_RECHARGE', 'ACCOUNT_DEDUCTION'],
  applyReason: ['ACCOUNT_ACTIVE_CLEAR', 'ACCOUNT_ACTIVE_CLEAR_RECYCLE'],
  authAccount: ['ACCOUNT_UNBIND', 'ACCOUNT_REBIND'],
  originalAuthAccount: ['ACCOUNT_REBIND'],
  remark: [
    'ACCOUNT_ACTIVE_CLEAR',
    'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
    'ACCOUNT_RECYCLE',
  ],
};

/** 将存量“操作类型联动”转换为按申请编码控制，发布后即保存为新结构。 */
function normalizeAccountOperationField(
  input: DynamicFormField,
): DynamicFormField | undefined {
  if (input.key === 'operationType') return;
  const field = cloneField(input);
  const usesLegacyOperationCondition =
    field.visibleWhen?.fieldKey === 'operationType' ||
    field.requiredWhen?.fieldKey === 'operationType';
  if (!usesLegacyOperationCondition) return field;
  field.applicableApplicationCodes = legacyAccountFieldApplications[field.key];
  field.visibleWhen = undefined;
  field.requiredWhen = undefined;
  if (field.key !== 'remark') field.required = true;
  return field;
}

function normalizeConfigFormFields(input: ApprovalConfig): DynamicFormField[] {
  if (input.assetType === 'ACCOUNT_OPERATION') {
    return input.formSchema.flatMap((item) => {
      const normalized = normalizeAccountOperationField(item);
      return normalized ? [normalized] : [];
    });
  }

  const fields = input.formSchema.map((item) => cloneField(item));
  return input.assetType === 'ACCOUNT_OPENING'
    ? normalizeAccountOpeningFormSchema(fields)
    : fields;
}

function cloneHandlerAction(
  input?: HandlerActionConfig,
): HandlerActionConfig | undefined {
  if (!input) return;
  return {
    formSchema: input.formSchema?.map((item) => cloneField(item)),
    resourceAssignment: input.resourceAssignment
      ? { ...input.resourceAssignment }
      : undefined,
  };
}

export function cloneApprovalConfig(
  input: MediaApprovalConfig,
): MediaApprovalConfig {
  return {
    ...input,
    applicationDefinitionIds: [...(input.applicationDefinitionIds ?? [])],
    ccUsers: [...input.ccUsers],
    formFields: input.formFields.map((item) => cloneField(item)),
    nodes: input.nodes.map((node) => ({
      ...node,
      departmentIds: [...(node.departmentIds ?? [])],
      departmentNames: [...(node.departmentNames ?? [])],
      handlerAction: cloneHandlerAction(node.handlerAction),
      roleIds: [...(node.roleIds ?? [])],
      users: [...(node.users ?? [])],
      userNames: [...(node.userNames ?? [])],
    })),
    settings: {
      ...input.settings,
      handlerAction: cloneHandlerAction(input.settings.handlerAction),
    },
    types: [...input.types],
  };
}

function roleForCategory(
  category: ApprovalConfig['category'],
): ApplicationApprovalRole {
  if (category === 'finance') return 'finance';
  if (category === 'office') return 'office';
  return 'media';
}

function categoryForRole(
  role: ApplicationApprovalRole,
): ApprovalConfig['category'] {
  if (role === 'finance') return 'finance';
  if (role === 'office') return 'office';
  return 'advertising';
}

function categoryForConfig(
  input: MediaApprovalConfig,
): ApprovalConfig['category'] {
  if (input.types.includes('TG')) return 'social';
  return categoryForRole(input.role);
}

function fromApi(input: ApprovalConfig): MediaApprovalConfig | undefined {
  const role = roleForCategory(input.category);
  const base =
    seedConfigs.find((item) => item.types[0] === input.assetType) ??
    createApprovalConfigDraft();
  base.id = input.assetType;
  base.types = [input.assetType];
  base.role = role;
  const approvalNodes: ApprovalFlowNode[] = input.nodes.map((node, index) => ({
    approver: node.approverName,
    approverId: node.approverId,
    assigneeMode:
      node.assigneeMode ??
      (node.approverType === 'DEPARTMENTS'
        ? 'department'
        : node.approverType === 'ROLES'
          ? 'role'
          : 'member'),
    departmentIds: [...(node.departmentIds ?? [])],
    departmentNames: [...(node.departmentNames ?? [])],
    id: node.id ?? `${input.assetType}-approval-${index}`,
    kind: 'approval',
    label: node.name,
    role,
    roleIds: [...(node.roleIds ?? [])],
  }));
  if (input.ccUserIds) {
    approvalNodes.push({
      id: `${input.assetType}-copy`,
      kind: 'copy',
      label: '抄送',
      users: input.ccUserIds.split(',').filter(Boolean),
    });
  }
  const configuredHandlerAction = cloneHandlerAction(
    input.settings.handlerAction,
  );
  const completionMode =
    input.settings.completionMode === 'pixel-auto-assign'
      ? 'pixel-auto-assign'
      : 'handler';
  if (completionMode === 'handler') {
    approvalNodes.push({
      approver: input.handlerName,
      approverId: input.handlerId,
      assigneeMode: 'member',
      handlerApprovalNodeId: input.handlerApprovalNodeId,
      id: `${input.assetType}-handler`,
      kind: 'handler',
      label: '业务办理',
      role,
      handlerSource: input.handlerSource ?? 'fixed-user',
      handlerAction:
        configuredHandlerAction ??
        cloneHandlerAction(
          base.nodes.find((node) => node.kind === 'handler')?.handlerAction,
        ),
    });
  }
  const configuredApprovalType = (
    input.settings as Partial<ApprovalConfigSettings>
  ).approvalType;
  const settings: ApprovalConfigSettings = {
    approvalType:
      configuredApprovalType === 'auto-approve' ||
      configuredApprovalType === 'auto-reject' ||
      configuredApprovalType === 'manual'
        ? configuredApprovalType
        : 'manual',
    completionMode,
    handlerAction:
      completionMode === 'handler'
        ? (configuredHandlerAction ??
          cloneHandlerAction(
            base.nodes.find((node) => node.kind === 'handler')?.handlerAction,
          ))
        : undefined,
  };
  return {
    ...cloneApprovalConfig(base),
    applicationDefinitionIds: [...(input.applicationDefinitionIds ?? [])],
    approver:
      approvalNodes.find((node) => node.kind === 'approval')?.approver ?? '',
    approverId: approvalNodes.find((node) => node.kind === 'approval')
      ?.approverId,
    ccUsers: input.ccUserIds?.split(',').filter(Boolean) ?? [],
    description: input.description || base.description,
    enabled: input.enabled,
    formFields: normalizeConfigFormFields(input),
    handlerApprovalNodeId: input.handlerApprovalNodeId,
    handlerId: input.handlerId,
    handlerName: input.handlerName,
    handlerSource: input.handlerSource ?? 'fixed-user',
    icon: input.icon || base.icon,
    id: input.id,
    name: input.name,
    nodes: approvalNodes,
    role,
    settings,
    sortOrder: normalizeSortOrder(input.sortOrder),
    updatedAt: input.updatedAt,
    visibility: input.visibility,
  };
}

export function toApprovalConfigPayload(
  input: MediaApprovalConfig,
): Omit<ApprovalConfig, 'id' | 'updatedAt' | 'usageCount'> {
  const type = input.types[0];
  if (!type) throw new Error('审批配置缺少申请类型');
  const approvalNodes = input.nodes.filter((node) => node.kind === 'approval');
  const handler = input.nodes.find((node) => node.kind === 'handler');
  if (input.settings.approvalType === 'manual' && approvalNodes.length === 0) {
    throw new Error('人工审批至少需要一个审批节点');
  }
  const pixelAutoAssignment =
    input.settings.completionMode === 'pixel-auto-assign';
  if (!pixelAutoAssignment && !handler) throw new Error('请配置业务办理节点');
  const handlerSource = handler?.handlerSource ?? 'fixed-user';
  const sourceApprovalNode = approvalNodes.find(
    (node) => node.id === handler?.handlerApprovalNodeId,
  );
  if (!pixelAutoAssignment && handlerSource === 'approval-node') {
    if (!handler?.handlerApprovalNodeId || !sourceApprovalNode) {
      throw new Error('请选择办理人关联的审批节点');
    }
    if (sourceApprovalNode.assigneeMode === 'role') {
      if (!sourceApprovalNode.roleIds?.length) {
        throw new Error('关联审批节点必须配置审批角色');
      }
    } else if (sourceApprovalNode.assigneeMode === 'department') {
      if (!sourceApprovalNode.departmentIds?.length) {
        throw new Error('关联审批节点必须配置审批部门');
      }
    } else if (
      !sourceApprovalNode.approverId ||
      sourceApprovalNode.approverId === '0' ||
      !sourceApprovalNode.approver
    ) {
      throw new Error('关联审批节点必须配置具体审批人');
    }
  } else if (
    !pixelAutoAssignment &&
    (!handler?.approverId || !handler?.approver)
  ) {
    throw new Error('请选择业务办理人');
  }
  const handlerId = pixelAutoAssignment
    ? ''
    : handlerSource === 'approval-node'
      ? sourceApprovalNode?.assigneeMode === 'member'
        ? (sourceApprovalNode.approverId ?? '')
        : ''
      : (handler?.approverId ?? '');
  const handlerName = pixelAutoAssignment
    ? ''
    : handlerSource === 'approval-node'
      ? sourceApprovalNode?.assigneeMode === 'member'
        ? (sourceApprovalNode.approver ?? '')
        : ''
      : (handler?.approver ?? '');
  const nodes: ApprovalNodeConfig[] = approvalNodes.map((node) => ({
    approverId: node.approverId ?? '',
    approverIds: node.users,
    approverName: node.approver ?? '',
    approverNames: node.userNames,
    approverType:
      node.assigneeMode === 'department'
        ? 'DEPARTMENTS'
        : node.assigneeMode === 'role'
          ? 'ROLES'
          : 'USERS',
    assigneeMode: node.assigneeMode ?? 'member',
    departmentIds: node.departmentIds,
    departmentNames: node.departmentNames,
    id: node.id,
    kind: 'approval',
    name: node.label,
    roleIds: node.roleIds,
  }));
  return {
    applicationDefinitionIds: [...input.applicationDefinitionIds],
    assetType: type,
    category: categoryForConfig(input),
    ccUserIds: input.nodes
      .filter((node) => node.kind === 'copy')
      .flatMap((node) => node.users ?? [])
      .join(','),
    description: input.description,
    enabled: input.enabled,
    formSchema: input.formFields.map((item) => cloneField(item)),
    handlerApprovalNodeId:
      !pixelAutoAssignment && handlerSource === 'approval-node'
        ? handler?.handlerApprovalNodeId
        : undefined,
    handlerId,
    handlerName,
    handlerSource,
    icon: input.icon,
    name: input.name,
    nodes,
    settings: {
      approvalType: input.settings.approvalType,
      completionMode: pixelAutoAssignment ? 'pixel-auto-assign' : 'handler',
      handlerAction: pixelAutoAssignment
        ? undefined
        : cloneHandlerAction(handler?.handlerAction),
    },
    sortOrder: normalizeSortOrder(input.sortOrder),
    status: 'published',
    visibility: input.visibility,
  };
}

export const useMediaApprovalConfigStore = defineStore(
  'media-approval-config',
  () => {
    const state = ref(seedConfigs.map((item) => cloneApprovalConfig(item)));
    const loading = ref(false);
    const loaded = ref(false);
    const configs = computed(() =>
      [...state.value].sort((left, right) => left.sortOrder - right.sortOrder),
    );

    async function load() {
      if (loading.value) return;
      loading.value = true;
      try {
        const remote = await assetFlowApi.managedConfigs();
        const mapped = remote
          .map((item) => fromApi(item))
          .filter((item): item is MediaApprovalConfig => item !== undefined);
        state.value =
          mapped.length > 0
            ? mapped
            : seedConfigs.map((item) => cloneApprovalConfig(item));
        loaded.value = true;
      } finally {
        loading.value = false;
      }
    }

    async function update(input: MediaApprovalConfig) {
      const saved = fromApi(
        await assetFlowApi.saveConfig(toApprovalConfigPayload(input)),
      );
      if (!saved) throw new Error('后端返回了不支持的申请类型');
      // 保存接口的旧版本响应未返回关联申请，提交值才是本次更新后的权威状态。
      saved.applicationDefinitionIds = [...input.applicationDefinitionIds];
      const exists = state.value.some(
        (item) => item.types[0] === saved.types[0],
      );
      state.value = exists
        ? state.value.map((item) =>
            item.types[0] === saved.types[0] ? saved : item,
          )
        : [...state.value, saved];
      return cloneApprovalConfig(saved);
    }

    async function toggleEnabled(id: string) {
      const target = state.value.find((item) => item.id === id);
      if (!target) return;
      return update({
        ...cloneApprovalConfig(target),
        enabled: !target.enabled,
      });
    }

    async function remove(id: string) {
      await assetFlowApi.deleteConfig(id);
      state.value = state.value.filter((item) => item.id !== id);
    }

    function resolveForType(type: ApprovalApplicationType) {
      return configs.value.find(
        (item) => item.enabled && item.types.includes(type),
      );
    }

    return {
      configs,
      load,
      loaded,
      loading,
      remove,
      resolveForType,
      toggleEnabled,
      update,
    };
  },
);
