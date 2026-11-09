-- 审批配置列表与资源申请首页使用同一套入口说明，避免历史 MPower 文案暴露给用户。
-- 仅修正展示描述；动态表单、审批节点和办理规则保持不变。
UPDATE media_approval_config
SET description = CASE asset_type
    WHEN 'BM' THEN '申请 BM 并登记区域、数量与用途说明'
    WHEN 'PIXEL' THEN '申请网站或应用转化像素、事件及使用权限'
    WHEN 'BUNDLE' THEN '申请账户绑包并提交绑定应用链接'
    WHEN 'PAGE' THEN '申请主页并填写地区、数量和授权 BM'
    WHEN 'MOBILE' THEN '申请业务手机、验证手机及移动设备资源'
    WHEN 'EMAIL' THEN '申请业务邮箱和对应使用用途'
    WHEN 'STATIC_IP' THEN '申请静态 IP，并指定地区与使用用途'
    WHEN 'PAYMENT' THEN '申请渠道打款并登记昨日消耗和收款信息'
    WHEN 'ACCOUNT_OPERATION' THEN '按操作类型填写广告账户的充值、扣款、清零、回收、解绑或换绑信息'
END
WHERE asset_type IN (
    'BM', 'PIXEL', 'BUNDLE', 'PAGE', 'MOBILE', 'EMAIL', 'STATIC_IP',
    'PAYMENT', 'ACCOUNT_OPERATION'
)
  AND deleted_at = 0;
