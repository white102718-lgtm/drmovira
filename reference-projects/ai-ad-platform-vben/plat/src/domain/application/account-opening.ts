import type { DynamicFormField, HandlerActionConfig } from '#/api/asset-flow';

export const ACCOUNT_OPENING_APPLICATION_CODE = 'ACCOUNT_OPENING';
export const ACCOUNT_OPENING_ASSET_TYPE = 'ACCOUNT_OPENING';

const accountOpeningTimezoneOptions = [
  'UTC-8',
  'UTC-5',
  'UTC+0',
  'UTC+1',
  'UTC+7',
  'UTC+8',
  'UTC+9',
];

function createAccountOpeningChannelField(): DynamicFormField {
  return {
    key: 'channelId',
    label: '渠道',
    optionSource: 'channels',
    placeholder: '请选择渠道',
    required: true,
    type: 'select',
    width: 'half',
  };
}

/**
 * MPower 广告户申请表单字段。
 *
 * @remarks
 * 字段标识与 MPower 提交参数保持一致；币种在申请页与充值金额组合展示。
 */
export function createAccountOpeningFormSchema(): DynamicFormField[] {
  return [
    {
      key: 'sectionDetails',
      label: '广告户信息',
      required: false,
      type: 'section',
      width: 'full',
    },
    createAccountOpeningChannelField(),
    {
      key: 'accountName',
      label: '账户名称',
      maxLength: 50,
      placeholder: '请输入账户名称',
      required: false,
      type: 'text',
      width: 'half',
    },
    {
      key: 'quantity',
      label: '开户数量',
      minValue: 1,
      placeholder: '请输入开户数量，最少 1 个',
      required: true,
      type: 'number',
      width: 'half',
    },
    {
      defaultValue: '邮箱',
      key: 'authType',
      label: '授权类型',
      optionSource: 'custom',
      options: ['邮箱', 'BM', '邮箱和 BM'],
      placeholder: '请选择授权类型',
      required: true,
      type: 'select',
      width: 'half',
    },
    {
      key: 'authAccount',
      label: '授权邮箱/BM',
      placeholder: '请输入授权邮箱/BM',
      required: true,
      type: 'text',
      width: 'half',
    },
    {
      key: 'rechargeAmount',
      label: '充值金额',
      minValue: 200,
      placeholder: '请输入充值金额，最低 $200',
      required: false,
      type: 'number',
      validationRule: 'positive-money',
      width: 'half',
    },
    {
      defaultValue: 'USD',
      key: 'amountType',
      label: '币种',
      optionSource: 'custom',
      options: ['USD', 'EUR'],
      placeholder: '请选择币种',
      required: true,
      type: 'select',
      width: 'half',
    },
    {
      key: 'timezone',
      label: '时区',
      optionSource: 'custom',
      options: accountOpeningTimezoneOptions,
      placeholder: '请选择时区',
      required: true,
      type: 'select',
      width: 'half',
    },
    {
      key: 'remark',
      label: '备注',
      maxLength: 500,
      placeholder: '请输入备注',
      required: false,
      type: 'textarea',
      width: 'full',
    },
  ];
}

/**
 * 为迁移前保存的广告户申请配置补齐渠道字段。
 *
 * @remarks
 * 申请页面优先读取服务端审批配置；环境尚未执行数据库迁移时仍可能返回旧表单，
 * 因此仅在缺少 `channelId` 时插入必填渠道，并保留管理员配置的其他字段和顺序。
 */
export function normalizeAccountOpeningFormSchema(
  fields: DynamicFormField[],
): DynamicFormField[] {
  if (fields.some((field) => field.key === 'channelId')) return fields;

  const sectionIndex = fields.findIndex((field) => field.type === 'section');
  const insertionIndex = sectionIndex === -1 ? 0 : sectionIndex + 1;
  return [
    ...fields.slice(0, insertionIndex),
    createAccountOpeningChannelField(),
    ...fields.slice(insertionIndex),
  ];
}

/** MPower 开户审批通过后的办理结果字段。 */
export function createAccountOpeningHandlerAction(): HandlerActionConfig {
  return {
    formSchema: [
      {
        key: 'openedAccountIds',
        label: '已开户广告账户',
        maxLength: 1000,
        placeholder: '请输入广告账户 ID，每行一个或用分号分隔',
        required: true,
        type: 'textarea',
        validationRule: 'digit-list',
        width: 'full',
      },
      {
        key: 'bmLink',
        label: 'BM 链接',
        maxLength: 400,
        placeholder: '请输入 BM 链接（最多 400 字）',
        required: false,
        type: 'textarea',
        width: 'full',
      },
    ],
  };
}
