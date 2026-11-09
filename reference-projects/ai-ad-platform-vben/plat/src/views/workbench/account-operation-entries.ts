/** 账户操作的独立申请入口；提交时仍共用 ACCOUNT_OPERATION 审批配置。 */
export const accountOperationEntries = [
  {
    applicationCode: 'ACCOUNT_RECHARGE',
    description: '为指定广告账户申请充值并填写充值金额',
    icon: 'lucide:circle-dollar-sign',
    iconClass: 'application-icon application-icon--emerald',
    key: 'recharge',
    label: '广告账户充值申请',
    operationType: '充值',
    recommended: true,
  },
  {
    applicationCode: 'ACCOUNT_DEDUCTION',
    description: '从指定广告账户扣款并填写扣款金额',
    icon: 'lucide:circle-minus',
    iconClass: 'application-icon application-icon--orange',
    key: 'deduction',
    label: '广告账户扣款申请',
    operationType: '扣款',
    recommended: false,
  },
  {
    applicationCode: 'ACCOUNT_ACTIVE_CLEAR',
    description: '对指定广告账户执行活跃清零',
    icon: 'lucide:activity',
    iconClass: 'application-icon application-icon--amber',
    key: 'active-reset',
    label: '活跃清零申请',
    operationType: '活跃清零',
    recommended: false,
  },
  {
    applicationCode: 'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
    description: '清零账户活跃数据后同步发起回收',
    icon: 'lucide:rotate-ccw',
    iconClass: 'application-icon application-icon--amber',
    key: 'active-reset-reclaim',
    label: '活跃清零回收申请',
    operationType: '活跃清零回收',
    recommended: false,
  },
  {
    applicationCode: 'ACCOUNT_RECYCLE',
    description: '申请回收指定广告账户并记录回收备注',
    icon: 'lucide:archive-restore',
    iconClass: 'application-icon application-icon--cyan',
    key: 'reclaim',
    label: '广告账户回收申请',
    operationType: '回收',
    recommended: false,
  },
  {
    applicationCode: 'ACCOUNT_UNBIND',
    description: '解除广告账户与指定邮箱或 BM 的绑定',
    icon: 'lucide:unlink',
    iconClass: 'application-icon application-icon--rose',
    key: 'unbind',
    label: '广告账户解绑申请',
    operationType: '解绑',
    recommended: false,
  },
  {
    applicationCode: 'ACCOUNT_REBIND',
    description: '将广告账户从原授权邮箱或 BM 换绑到新授权',
    icon: 'lucide:repeat-2',
    iconClass: 'application-icon application-icon--violet',
    key: 'rebind',
    label: '广告账户换绑申请',
    operationType: '换绑',
    recommended: false,
  },
] as const;

export type AccountOperationEntry = (typeof accountOperationEntries)[number];
export type AccountOperationType = AccountOperationEntry['operationType'];

/** 根据已保存的操作类型恢复独立申请上下文。 */
export function findAccountOperationEntry(value: unknown) {
  return accountOperationEntries.find((entry) => entry.operationType === value);
}

/** 根据稳定申请编码恢复账户操作入口的展示元数据。 */
export function findAccountOperationEntryByCode(value: unknown) {
  return accountOperationEntries.find(
    (entry) => entry.applicationCode === value,
  );
}
