# 前端MFA二次认证对接文档

## 1. 对接范围

系统登录采用“账号密码 + 可选TOTP二次认证”流程。前端必须根据密码登录接口返回的 `loginStatus` 决定下一步操作。

只有 `loginStatus=SUCCESS` 时才表示完整登录成功，此时才能保存 `accessToken`、进入系统首页并请求受保护接口。`challengeToken` 只是短期MFA挑战令牌，不能放入 `Authorization` 请求头。

接口基础路径：

```text
/api
```

## 1.1 当前前端项目现状与必须修改项

前端项目位于 `adpluse-power/plat`，技术栈是 Vue 3、TypeScript、Pinia、Vben Request、Ant Design Vue。登录和MFA页面已经存在，但目前对接的是另一套旧协议，不能直接连接本后端。

前端AI必须检查并修改以下文件：

| 文件 | 当前问题 | 必须修改 |
| --- | --- | --- |
| `src/api/core/auth.ts` | 登录使用表单格式，字段为 `phone/username`；响应是snake_case | 改为JSON请求，字段为 `identifier/password`；响应改为本文camelCase结构 |
| `src/store/auth.ts` | 判断 `MFA_REQUIRED/MFA_ENROLL`，保存 `mfa_token/setup_token` | 判断 `MFA_VERIFY_REQUIRED/MFA_BIND_REQUIRED`，统一保存 `challengeToken` |
| `src/views/_core/authentication/login.vue` | 绑定时额外调用 `/auth/mfa/init` | 登录响应已直接返回二维码内容，不再调用初始化接口 |
| `src/api/core/user.ts` | 当前用户接口是 `/users/info` | 改为后端现有的 `GET /auth/me` 并映射为前端 `UserInfo` |
| `src/api/request.ts` | 所有请求都会附带旧JWT，401会触发全局重新认证 | 登录和两个MFA接口必须跳过JWT、刷新Token和全局401跳转 |
| `src/views/_core/authentication/mfa-rebind-modal.vue` | 使用 `/mfa/setup`、`enable` 等当前后端不存在的接口 | 本轮不要接入；暂时隐藏换绑入口，管理员重置后由用户下次登录重新绑定 |

禁止继续调用以下旧接口：

```text
POST /auth/mfa/init
POST /auth/mfa/activate
POST /auth/mfa/setup
POST /auth/mfa/enable
POST /auth/mfa/disable
POST /auth/refresh
GET  /auth/service-token
GET  /users/info
```

当前后端登录阶段实际使用的接口只有：

```text
POST /auth/login
POST /auth/mfa/bind
POST /auth/mfa/verify
GET  /auth/me
POST /auth/logout
```

统一成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

应用层响应的HTTP状态码固定为 `200`，前端必须检查响应体 `code`。业务成功码已由原来的 `0` 调整为 `200`。

注意：`backendClient` 已通过 `defaultResponseInterceptor` 提取响应体的 `data`，所以业务API函数通常直接拿到本文的 `LoginResult`，而不是完整 `ApiResponse<LoginResult>`。前端AI应先确认请求客户端的 `responseReturn`，避免再访问一次不存在的 `.data.data`。

## 2. MFA状态和页面流程

后端用户状态：

| `mfa_status` | 含义 | 密码正确后的行为 |
| --- | --- | --- |
| `-1` | 不启用MFA | 直接返回JWT |
| `0` | 要求MFA但尚未绑定 | 返回绑定密钥、二维码内容和临时挑战 |
| `1` | 已绑定MFA | 返回临时挑战，要求输入六位动态码 |

前端状态机：

```text
登录页提交账号密码
    ├── SUCCESS
    │   └── 保存JWT → 加载用户信息 → 进入系统
    ├── MFA_BIND_REQUIRED
    │   └── 展示二维码/密钥 → 输入6位动态码 → 绑定接口 → 保存JWT → 进入系统
    └── MFA_VERIFY_REQUIRED
        └── 展示动态码输入框 → 验证接口 → 保存JWT → 进入系统
```

完整返回结果矩阵：

| 调用接口 | 后端条件 | `loginStatus` | 必然返回 | 必然不返回 | 前端下一步 |
| --- | --- | --- | --- | --- | --- |
| `/auth/login` | `mfa_status=-1` | `SUCCESS` | `accessToken`、用户和权限 | 挑战及MFA密钥 | 保存JWT并进入系统 |
| `/auth/login` | `mfa_status=0` | `MFA_BIND_REQUIRED` | `challengeToken`、有效秒数、`mfaSecret`、`otpAuthUri` | `accessToken` | 展示二维码并调用 `/auth/mfa/bind` |
| `/auth/login` | `mfa_status=1` | `MFA_VERIFY_REQUIRED` | `challengeToken`、有效秒数 | `accessToken`、MFA密钥 | 展示动态码输入并调用 `/auth/mfa/verify` |
| `/auth/mfa/bind` | 动态码正确 | `SUCCESS` | `accessToken`、用户和权限 | 挑战及MFA密钥 | 保存JWT并进入系统 |
| `/auth/mfa/verify` | 动态码正确且未重放 | `SUCCESS` | `accessToken`、用户和权限 | 挑战及MFA密钥 | 保存JWT并进入系统 |

任何非 `SUCCESS` 响应都不能调用受保护接口。任何 `SUCCESS` 响应缺少 `accessToken` 都应视为协议异常，而不是继续进入系统。

建议前端页面至少维护以下状态：

```ts
type LoginStage =
  | "PASSWORD"
  | "MFA_BIND_REQUIRED"
  | "MFA_VERIFY_REQUIRED"
  | "SUCCESS";
```

刷新页面或挑战过期后，返回账号密码登录页重新开始，不能只重试MFA接口。

## 3. 第一步：账号密码登录

### 3.1 请求

```http
POST /api/auth/login
Content-Type: application/json
```

```json
{
  "identifier": "admin",
  "password": "REDACTED_REFERENCE_SECRET"
}
```

`identifier` 支持用户名或手机号。

### 3.2 不启用MFA：直接登录成功

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "loginStatus": "SUCCESS",
    "accessToken": "REDACTED_REFERENCE_SECRET",
    "tokenType": "Bearer",
    "expiresInSeconds": 43200,
    "userId": "1",
    "displayName": "系统管理员",
    "permissions": [
      "system:user:list",
      "system:user:create"
    ],
    "issuedAt": "2026-08-17T07:29:33.405Z"
  }
}
```

前端处理：

1. 保存 `accessToken`。
2. 后续请求添加 `Authorization: Bearer <accessToken>`。
3. 根据 `permissions` 初始化路由和按钮权限。
4. 进入系统首页。

### 3.3 尚未绑定MFA

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "loginStatus": "MFA_BIND_REQUIRED",
    "challengeToken": "REDACTED_REFERENCE_SECRET",
    "challengeExpiresInSeconds": 300,
    "mfaSecret": "REDACTED_REFERENCE_SECRET",
    "otpAuthUri": "otpauth://totp/AdPulse:admin?secret=...&issuer=AdPulse&algorithm=SHA1&digits=6&period=30"
  }
}
```

前端处理：

1. 切换到MFA绑定页面。
2. 使用 `otpAuthUri` 在浏览器端生成二维码。
3. 同时显示 `mfaSecret`，供无法扫码的用户手动输入。
4. 提示用户在Google Authenticator、Microsoft Authenticator等TOTP应用中完成添加。
5. 用户输入验证器生成的六位动态码后，调用绑定接口。
6. 使用 `challengeExpiresInSeconds` 展示倒计时；过期后要求重新输入账号密码。

安全要求：

- `mfaSecret` 只在首次绑定响应中展示。
- 不要将 `mfaSecret` 写入localStorage、日志、埋点、错误上报或URL。
- 不要把 `challengeToken` 当作JWT保存到全局登录状态。
- 离开绑定页时应清除内存中的 `mfaSecret` 和 `otpAuthUri`。

### 3.4 已绑定MFA

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "loginStatus": "MFA_VERIFY_REQUIRED",
    "challengeToken": "REDACTED_REFERENCE_SECRET",
    "challengeExpiresInSeconds": 300
  }
}
```

前端处理：

1. 切换到MFA验证页面。
2. 展示六位数字输入框。
3. 用户输入动态码后调用验证接口。
4. 不展示二维码，也不会收到已绑定用户的MFA密钥。

## 4. 第二步A：首次绑定MFA

### 4.1 请求

```http
POST /api/auth/mfa/bind
Content-Type: application/json
```

该接口不需要JWT：

```json
{
  "challengeToken": "REDACTED_REFERENCE_SECRET",
  "totpCode": "123456"
}
```

字段要求：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `challengeToken` | 是 | 密码登录返回的5分钟临时令牌 |
| `totpCode` | 是 | 验证器生成的六位数字 |

### 4.2 绑定成功

绑定成功后自动完成登录，不需要再次调用账号密码登录：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "loginStatus": "SUCCESS",
    "accessToken": "REDACTED_REFERENCE_SECRET",
    "tokenType": "Bearer",
    "expiresInSeconds": 43200,
    "userId": "1",
    "displayName": "系统管理员",
    "permissions": [
      "system:user:list"
    ],
    "issuedAt": "2026-08-17T08:00:00Z"
  }
}
```

前端收到后按正常登录成功流程保存JWT并进入系统。

## 5. 第二步B：验证已绑定MFA

### 5.1 请求

```http
POST /api/auth/mfa/verify
Content-Type: application/json
```

该接口不需要JWT：

```json
{
  "challengeToken": "REDACTED_REFERENCE_SECRET",
  "totpCode": "123456"
}
```

### 5.2 验证成功

成功响应与首次绑定成功一致，`loginStatus=SUCCESS` 并返回正式JWT。

同一个TOTP动态码不能重复使用。用户在同一个30秒窗口重复提交已经成功使用的动态码时，后端会拒绝请求。

## 6. 错误处理

常见业务错误：

| `code` | 含义 | 前端建议 |
| --- | --- | --- |
| `501` | 请求字段校验失败 | 展示字段错误 |
| `400` | 账号密码错误、账号停用、锁定或IP受限 | 停留在账号密码页并展示安全提示 |
| `410` | MFA挑战无效、过期或IP变化 | 清除挑战并返回账号密码页 |
| `411` | MFA挑战用途不匹配 | 清除挑战并返回账号密码页 |
| `413` | MFA动态码错误、过期或已使用 | 清空动态码输入框，允许重试 |
| `414` | MFA错误次数达到上限 | 清除挑战并返回账号密码页 |
| `412` | MFA状态在认证过程中发生变化 | 清除挑战并重新登录 |

失败响应示例：

```json
{
  "code": 413,
  "message": "MFA动态码错误或已过期",
  "data": null
}
```

MFA挑战最多允许5次错误尝试。前端不要自动重复提交，也不要在网络超时后无限重试。

## 7. 前端请求封装建议

### 7.1 精确TypeScript类型

后端使用Jackson的 `NON_NULL` 序列化策略，不属于当前阶段的字段会直接缺失，而不是固定返回 `null`。因此阶段字段必须声明为可选。

```ts
type LoginStatus =
  | 'SUCCESS'
  | 'MFA_BIND_REQUIRED'
  | 'MFA_VERIFY_REQUIRED';

interface PasswordLoginParams {
  identifier: string;
  password: string;
}

interface MfaCodeParams {
  challengeToken: string;
  totpCode: string;
}

interface LoginResult {
  loginStatus: LoginStatus;
  challengeToken?: string;
  challengeExpiresInSeconds?: number;
  mfaSecret?: string;
  otpAuthUri?: string;
  accessToken?: string;
  tokenType?: "Bearer";
  expiresInSeconds?: number;
  userId?: string;
  displayName?: string;
  permissions?: string[];
  issuedAt?: string;
}
```

不要保留当前旧类型中的以下字段：

```text
access_token
mfa_required
mfa_setup_required
mfa_token
setup_token
status=MFA_ENROLL
status=MFA_REQUIRED
```

### 7.2 `src/api/core/auth.ts`改造目标

API层应改造成以下等价结构：

```ts
import { publicBackendClient, backendClient } from '#/api/request';

export namespace AuthApi {
  export type LoginStatus =
    | 'SUCCESS'
    | 'MFA_BIND_REQUIRED'
    | 'MFA_VERIFY_REQUIRED';

  export interface LoginParams {
    identifier: string;
    password: string;
  }

  export interface MfaCodeParams {
    challengeToken: string;
    totpCode: string;
  }

  export interface LoginResult {
    loginStatus: LoginStatus;
    challengeToken?: string;
    challengeExpiresInSeconds?: number;
    mfaSecret?: string;
    otpAuthUri?: string;
    accessToken?: string;
    tokenType?: 'Bearer';
    expiresInSeconds?: number;
    userId?: string;
    displayName?: string;
    permissions?: string[];
    issuedAt?: string;
  }
}

export function loginApi(data: AuthApi.LoginParams) {
  return publicBackendClient.post<AuthApi.LoginResult>('/auth/login', data);
}

export function mfaBindApi(data: AuthApi.MfaCodeParams) {
  return publicBackendClient.post<AuthApi.LoginResult>('/auth/mfa/bind', data);
}

export function mfaVerifyApi(data: AuthApi.MfaCodeParams) {
  return publicBackendClient.post<AuthApi.LoginResult>('/auth/mfa/verify', data);
}

export function logoutApi() {
  return backendClient.post('/auth/logout');
}
```

登录请求必须直接发送JSON：

```json
{
  "identifier": "admin或手机号",
  "password": "REDACTED_REFERENCE_SECRET"
}
```

不得继续使用：

```text
URLSearchParams
application/x-www-form-urlencoded
username字段
```

### 7.3 公共认证请求客户端

`/auth/login`、`/auth/mfa/bind`、`/auth/mfa/verify` 是匿名认证接口，应使用独立的 `publicBackendClient`。该客户端应复用JSON解析、`code=200`数据提取和普通错误提示，但必须满足：

1. 不读取或附加 `accessStore.accessToken`。
2. 不执行Token刷新。
3. 收到401时不触发全局“登录已失效”倒计时跳转。
4. 将后端业务错误交给登录页面处理。

推荐在 `src/api/request.ts` 中让 `createRequestClient` 接受 `authenticated` 开关：

```ts
function createRequestClient(
  baseURL: string,
  options?: RequestClientOptions,
  authenticated = true,
) {
  // 公共逻辑：JSON解析、成功码提取、普通错误转换
  // authenticated=true：附加Bearer、注册刷新和重新认证拦截器
  // authenticated=false：完全不注册上述认证逻辑
}

export const publicBackendClient = createRequestClient(
  backendURL,
  { responseReturn: 'data' },
  false,
);
```

不要只在登录调用中设置 `Authorization=null`，因为现有全局401响应拦截器仍可能触发刷新Token或跳转；应从客户端层真正隔离。

### 7.4 `src/store/auth.ts`状态设计

Pinia Store建议维护：

```ts
const mfaStep = ref<'none' | 'setup' | 'verify'>('none');
const challengeToken = ref('');
const challengeExpiresInSeconds = ref(0);
const mfaSecret = ref('');
const otpAuthUri = ref('');
```

处理登录结果的核心函数：

```ts
async function consumeLoginResult(
  result: AuthApi.LoginResult,
  onSuccess?: () => Promise<void> | void,
) {
  switch (result.loginStatus) {
    case 'MFA_BIND_REQUIRED':
      if (
        !result.challengeToken ||
        !result.mfaSecret ||
        !result.otpAuthUri
      ) {
        throw new Error('MFA绑定响应字段不完整');
      }
      challengeToken.value = result.challengeToken;
      challengeExpiresInSeconds.value =
        result.challengeExpiresInSeconds ?? 300;
      mfaSecret.value = result.mfaSecret;
      otpAuthUri.value = result.otpAuthUri;
      mfaStep.value = 'setup';
      return;

    case 'MFA_VERIFY_REQUIRED':
      if (!result.challengeToken) {
        throw new Error('MFA验证响应缺少challengeToken');
      }
      challengeToken.value = result.challengeToken;
      challengeExpiresInSeconds.value =
        result.challengeExpiresInSeconds ?? 300;
      mfaSecret.value = '';
      otpAuthUri.value = '';
      mfaStep.value = 'verify';
      return;

    case 'SUCCESS':
      if (!result.accessToken) {
        throw new Error('登录成功响应缺少accessToken');
      }
      await handleLoginSuccess(result, onSuccess);
      resetMfaState();
      return;
  }
}
```

账号密码登录：

```ts
async function authLogin(params: { password: string; phone: string }) {
  const result = await loginApi({
    identifier: params.phone,
    password: params.password,
  });
  await consumeLoginResult(result);
}
```

首次绑定：

```ts
async function authMfaBind(totpCode: string) {
  const result = await mfaBindApi({
    challengeToken: challengeToken.value,
    totpCode,
  });
  await consumeLoginResult(result);
}
```

已绑定验证：

```ts
async function authMfaVerify(totpCode: string) {
  const result = await mfaVerifyApi({
    challengeToken: challengeToken.value,
    totpCode,
  });
  await consumeLoginResult(result);
}
```

`resetMfaState()` 必须清除全部敏感临时数据：

```ts
function resetMfaState() {
  mfaStep.value = 'none';
  challengeToken.value = '';
  challengeExpiresInSeconds.value = 0;
  mfaSecret.value = '';
  otpAuthUri.value = '';
}
```

这些值只保存在内存Pinia状态中，不启用持久化，不写入localStorage或sessionStorage。

### 7.5 登录成功处理

当前前端 `handleLoginSuccess` 只接收字符串Token，并通过 `getAccessCodesApi()` 得到空数组，这会丢失后端登录响应中的权限。应改为接收完整 `LoginResult`：

```ts
async function handleLoginSuccess(
  result: AuthApi.LoginResult,
  onSuccess?: () => Promise<void> | void,
) {
  accessStore.setAccessToken(result.accessToken!);
  accessStore.setAccessCodes(result.permissions ?? []);

  const userInfo = await fetchUserInfo();
  userStore.setUserInfo(userInfo);

  // 然后执行现有的路由跳转和登录成功提示
}
```

不要再用返回空数组的 `getAccessCodesApi()` 覆盖 `result.permissions`。

### 7.6 当前用户接口适配

后端当前用户接口：

```http
GET /api/auth/me
Authorization: Bearer <accessToken>
```

预期响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "userId": "1",
    "displayName": "系统管理员",
    "permissions": [
      "system:user:list"
    ]
  }
}
```

`src/api/core/user.ts` 应调用 `/auth/me`，再映射到Vben要求的 `UserInfo`。至少确保 `userId`、显示名称、默认首页和权限字段正确，不能继续请求不存在的 `/users/info`。

### 7.7 前端流程示例

通用流程示例：

```ts
async function handlePasswordLogin(identifier: string, password: string) {
  const result = await loginApi({
    identifier,
    password,
  });
  switch (result.loginStatus) {
    case 'SUCCESS':
      completeLogin(result);
      break;
    case 'MFA_BIND_REQUIRED':
      showMfaBinding(result);
      break;
    case 'MFA_VERIFY_REQUIRED':
      showMfaVerification(result);
      break;
  }
}
```

在调用 `/auth/login`、`/auth/mfa/bind` 和 `/auth/mfa/verify` 时，不要附带历史JWT。可以在请求拦截器中将这三个接口加入免Token列表，避免过期Token干扰登录流程。

## 8. 二维码生成

后端返回标准 `otpauthUri`，前端只负责将完整字符串编码成二维码，不需要解析或重新拼接其中参数。

二维码生成伪代码：

```ts
const qrDataUrl = await QRCode.toDataURL(loginResult.otpAuthUri);
```

当前项目已经使用：

```ts
import { useQRCode } from '@vueuse/integrations/useQRCode';
```

登录页不再调用 `mfaInitApi()`。直接将Store中的 `otpAuthUri` 赋给现有 `qrUri`，将 `mfaSecret` 赋给现有 `secretKey`：

```ts
watch(
  () => authStore.mfaStep,
  (step) => {
    if (step === 'setup') {
      qrUri.value = authStore.otpAuthUri;
      secretKey.value = authStore.mfaSecret;
      startSetupCountdown(authStore.challengeExpiresInSeconds);
    } else {
      qrUri.value = '';
      secretKey.value = '';
    }
  },
  { immediate: true },
);
```

绑定按钮应调用新的 `authMfaBind`，而不是旧的 `authMfaActivate`：

```vue
<button @click="handleMfaSubmit(authStore.authMfaBind)">
  验证并绑定
</button>
```

六位动态码输入框建议增加数字输入限制：

```vue
<Input
  v-model:value="mfaCode"
  :maxlength="6"
  inputmode="numeric"
  placeholder="请输入6位动态码"
/>
```

不要将二维码上传到第三方二维码生成服务，因为URI中包含MFA明文密钥。必须使用浏览器本地二维码库生成。

## 8.1 挑战倒计时

倒计时初值必须使用后端返回的 `challengeExpiresInSeconds`，不能永久硬编码300秒。倒计时到0后：

1. 清除 `challengeToken`、`mfaSecret` 和 `otpAuthUri`。
2. 清空动态码输入框。
3. 返回账号密码表单。
4. 提示“认证挑战已过期，请重新登录”。

前端倒计时只是用户体验，真正有效期以后端Redis为准。浏览器暂停、系统休眠或多个标签页可能导致前端倒计时不准确，后端返回 `410` 时仍必须强制重新登录。

## 9. 前端AI实施与测试要求

## 9.1 可直接交给前端AI的实施任务

将本节连同全文交给前端AI，并要求它在现有代码上直接实现和测试：

```text
目标：把 adpluse-power/plat 的登录流程对接到 AdPulse System Server。

必须先阅读：
1. docs/FRONTEND_MFA_INTEGRATION.md
2. plat/src/api/request.ts
3. plat/src/api/core/auth.ts
4. plat/src/store/auth.ts
5. plat/src/views/_core/authentication/login.vue

实施要求：
1. 登录改为 POST /auth/login 的JSON请求，字段 identifier/password。
2. 删除登录流程对旧 snake_case 字段和 MFA_ENROLL/MFA_REQUIRED 状态的依赖。
3. 新增独立 publicBackendClient，三个匿名认证接口不得携带旧JWT，也不得触发刷新Token和全局401跳转。
4. MFA_BIND_REQUIRED 直接使用登录响应中的 otpAuthUri/mfaSecret，不调用 /auth/mfa/init。
5. 绑定调用 POST /auth/mfa/bind，验证调用 POST /auth/mfa/verify，请求字段统一为 challengeToken/totpCode。
6. 只有 loginStatus=SUCCESS 且 accessToken存在时才能保存JWT和跳转。
7. 使用登录成功响应中的 permissions 设置 accessCodes，不得再被空数组覆盖。
8. 当前用户接口改为 GET /auth/me，并映射为现有UserInfo。
9. 暂时隐藏依赖 /auth/mfa/setup、enable、disable 的换绑功能，不要虚构后端接口。
10. MFA密钥和挑战只保存在内存，不写localStorage/sessionStorage/URL/日志/埋点。
11. 保留现有Demo模式，不影响Demo角色入口。
12. 增加API和Store单元测试，覆盖三种loginStatus、绑定成功、验证成功、挑战过期和错误动态码。
13. 完成后运行项目typecheck、相关单元测试和build:test。

验收标准：
- code=200 + SUCCESS：保存JWT并进入系统。
- code=200 + MFA_BIND_REQUIRED：二维码可扫描，正确动态码绑定后自动登录。
- code=200 + MFA_VERIFY_REQUIRED：正确动态码验证后登录。
- MFA阶段绝不提前保存JWT。
- 410/411/412/414：清除挑战并返回密码页。
- 413：停留MFA页并允许剩余次数内重试。
```

AI完成后必须列出实际修改文件、运行的命令和测试结果，不能只返回代码建议。

## 9.2 建议自动化测试用例

API层至少覆盖：

1. `loginApi` 发送JSON且字段名是 `identifier/password`。
2. `mfaBindApi` 使用 `/auth/mfa/bind` 和 `challengeToken/totpCode`。
3. `mfaVerifyApi` 使用 `/auth/mfa/verify` 和 `challengeToken/totpCode`。
4. 三个匿名接口不携带 `Authorization`。

Store层至少覆盖：

1. `MFA_BIND_REQUIRED` 保存挑战、密钥和URI，但不保存JWT。
2. `MFA_VERIFY_REQUIRED` 只保存挑战，不保留旧MFA密钥。
3. `SUCCESS` 保存JWT和权限并清除MFA临时数据。
4. `413` 保持当前MFA步骤。
5. 挑战失效类错误重置为密码登录步骤。
6. `resetMfaState` 清空全部临时敏感字段。

页面层至少覆盖：

1. 绑定状态显示二维码、密钥、倒计时和动态码输入。
2. 验证状态只显示动态码输入，不显示密钥。
3. 倒计时结束返回登录表单。
4. 输入非六位数字时不发送请求。

## 10. 人工联调检查清单

### MFA待绑定用户

1. 登录接口返回 `MFA_BIND_REQUIRED`。
2. 二维码可以被验证器识别。
3. 错误动态码不能绑定。
4. 正确动态码绑定成功并直接返回JWT。
5. 再次登录进入 `MFA_VERIFY_REQUIRED`，不再返回MFA密钥。

### 已绑定用户

1. 密码正确后不返回JWT，只返回MFA挑战。
2. 错误动态码提示明确。
3. 正确动态码返回JWT。
4. 同一个已成功使用的动态码不能重复登录。
5. 挑战超过5分钟后失效。

### 不启用MFA用户

1. `mfa_status=-1` 时密码正确后直接返回JWT。
2. 不展示MFA绑定或验证页面。

### 通用检查

1. 成功响应 `code=200`。
2. 只有 `SUCCESS` 状态才保存JWT。
3. 受保护接口正确携带 `Authorization: Bearer <token>`。
4. 管理员重置MFA后，用户已有JWT会话失效，下次登录重新绑定。
5. 页面刷新、退出登录或挑战过期时清除MFA临时数据。
