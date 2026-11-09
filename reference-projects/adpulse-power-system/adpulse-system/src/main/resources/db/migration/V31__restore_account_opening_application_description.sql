-- 资源申请首页的全部已有入口沿用已确认的原型说明，表单字段与审批流程保持不变。
UPDATE media_application_definition
SET description = CASE application_code
    WHEN 'ACCOUNT_OPENING' THEN '申请广告户并补充授权方式、开户数量与时区'
    WHEN 'PIXEL' THEN '申请网站或应用转化像素、事件及使用权限'
    WHEN 'BM' THEN '申请 BM 并登记区域、数量与用途说明'
    WHEN 'BUNDLE' THEN '申请账户绑包并提交绑定应用链接'
    WHEN 'PAGE' THEN '申请主页并填写地区、数量和授权 BM'
    WHEN 'TG' THEN '申请 TG、Facebook、微信等社交资产'
    WHEN 'COMPUTER' THEN '申请办公电脑、剪辑工作站及配套设备'
    WHEN 'MOBILE' THEN '申请业务手机、验证手机及移动设备资源'
    WHEN 'EMAIL' THEN '申请业务邮箱和对应使用用途'
    WHEN 'STATIC_IP' THEN '申请静态 IP，并指定地区与使用用途'
    WHEN 'PAYMENT' THEN '申请渠道打款并登记昨日消耗和收款信息'
    WHEN 'ACCOUNT_RECHARGE' THEN '申请广告户充值，填写授权与开户信息'
    WHEN 'ACCOUNT_DEDUCTION' THEN '申请从指定广告账户扣款并填写扣款金额'
    WHEN 'ACCOUNT_ACTIVE_CLEAR' THEN '申请对广告账户执行活跃清零'
    WHEN 'ACCOUNT_ACTIVE_CLEAR_RECYCLE' THEN '确认回流消耗数据后回收活跃清零账户'
    WHEN 'ACCOUNT_RECYCLE' THEN '申请回收指定广告账户'
    WHEN 'ACCOUNT_UNBIND' THEN '申请解除广告账户与邮箱或 BM 的绑定'
    WHEN 'ACCOUNT_REBIND' THEN '申请将广告账户从原授权换绑到新授权'
    WHEN 'PROJECT_CLOSURE' THEN '申请项目结项并提交结算金额、周期与结项说明'
END
WHERE application_code IN (
    'ACCOUNT_OPENING', 'PIXEL', 'BM', 'BUNDLE', 'PAGE', 'TG', 'COMPUTER',
    'MOBILE', 'EMAIL', 'STATIC_IP', 'PAYMENT', 'ACCOUNT_RECHARGE',
    'ACCOUNT_DEDUCTION', 'ACCOUNT_ACTIVE_CLEAR', 'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
    'ACCOUNT_RECYCLE', 'ACCOUNT_UNBIND', 'ACCOUNT_REBIND', 'PROJECT_CLOSURE'
)
  AND deleted_at = 0;
