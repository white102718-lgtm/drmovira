# MFA认证流程

系统使用RFC 6238六位TOTP、Redis短期挑战和有状态JWT会话。启用MFA的账号必须完成MFA流程后才会创建Redis会话并签发JWT；停用MFA的账号在密码和IP策略校验通过后直接登录。

认证逻辑只读写 `mfa_status`。旧版 `mfa_enabled` 字段由 V4 手工升级脚本删除，数据库执行步骤见 `DATABASE_MANUAL_UPGRADE.md`。

## 用户状态

- `mfa_status=-1`：不启用MFA，密码和IP策略通过后直接登录。
- `mfa_status=0`：要求MFA但尚未绑定，进入绑定流程。
- `mfa_status=1`：已绑定MFA，进入动态码验证流程。

普通新建账号（包括首次初始化管理员）默认写入 `mfa_status=-1`，登录无需绑定或二次校验。飞书同步首次创建账号时写入 `mfa_status=0`，密码登录需要先绑定MFA；后续同步更新不覆盖已有账号的MFA状态、密钥、绑定时间和防重放计数器。管理员重置MFA仍会将账号设为待绑定状态。

## 第一步：密码登录

`POST /api/auth/login`

待绑定响应的 `loginStatus` 为 `MFA_BIND_REQUIRED`，同时返回5分钟有效的 `challengeToken`、仅展示一次的 `mfaSecret` 和 `otpAuthUri`。前端使用 `otpAuthUri` 生成二维码。

已绑定响应的 `loginStatus` 为 `MFA_VERIFY_REQUIRED`，只返回 `challengeToken`，不得返回已保存的MFA密钥。

不启用MFA时 `loginStatus` 为 `SUCCESS`，并返回正式JWT。

## 第二步：绑定或验证

- 首次绑定：`POST /api/auth/mfa/bind`
- 已绑定验证：`POST /api/auth/mfa/verify`

请求结构相同：

```json
{
  "challengeToken": "REDACTED_REFERENCE_SECRET",
  "totpCode": "123456"
}
```

绑定或验证成功后返回 `loginStatus=SUCCESS` 和正式JWT。挑战绑定发起登录的客户端IP、有效期为5分钟、最多允许5次错误尝试，成功后立即删除。

## 安全配置

生产环境必须配置独立的32字节AES密钥，其Base64文本放入：

```text
MFA_ENCRYPTION_KEY
```

可以使用 `openssl rand -base64 32` 生成。该密钥必须长期稳定并安全备份；丢失或更换后，已有MFA密钥将无法解密，需要管理员逐个重置MFA。

MFA密钥使用AES-256-GCM加密保存，成功使用的TOTP时间计数器写入数据库，防止同一个动态码被重复使用。管理员重置MFA后，用户状态回到待绑定并撤销全部现有会话。
