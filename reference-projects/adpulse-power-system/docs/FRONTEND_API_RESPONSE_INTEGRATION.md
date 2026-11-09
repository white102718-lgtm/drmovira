# 前端统一接口响应处理规范

本文档提供给前端开发人员或前端 AI，用于统一处理 AdPulse System Server 的成功响应、业务错误、登录失效、MFA 流程和网络异常。

## 1. 最重要的约定

1. 请求只要到达 Java 应用并由应用生成响应，HTTP 状态码始终为 `200`。
2. 不得使用 HTTP 状态码判断业务成功或失败，必须读取 JSON 响应体的 `code`。
3. `code === 200` 才是业务成功。
4. `code !== 200` 必须进入业务错误处理，即使 HTTP 状态为 200。
5. 网关错误、连接失败、超时、DNS 错误等没有标准 JSON 响应体的情况，仍按网络异常处理。

统一响应结构：

```ts
interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
}
```

成功示例：

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "1",
    "displayName": "系统管理员"
  }
}
```

业务失败示例。注意 HTTP 仍然是 200：

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "code": 504,
  "message": "角色仍有关联用户，不能删除",
  "data": null
}
```

## 2. 响应码分段规则

| 号段 | 含义 | 全局处理策略 |
| --- | --- | --- |
| `2xx` | 成功 | 返回 `data`，不显示错误 |
| `4xx` | 登录、会话、权限、MFA 等流程错误 | 全局不直接展示后端消息，交给指定流程处理 |
| `5xx` | 可以安全展示的业务错误 | 默认展示后端 `message` |
| `6xx` | 系统内部错误 | 禁止展示后端 `message`，展示固定兜底文案并上报日志 |

“全局静默”不代表完全忽略错误，而是禁止全局拦截器重复弹窗。登录页、MFA 页等业务页面可以根据具体 `code` 展示页面内提示。

## 3. 前端处理优先级

收到响应后必须按以下顺序处理：

1. 判断是否存在标准响应体 `{ code, message, data }`。
2. `code === 200`：返回 `data`。
3. `code === 401`：清除本地 token 和用户状态，只执行一次重新登录跳转。
4. 其他 `4xx`：禁止全局弹窗，抛给调用页面处理。
5. `5xx`：除非请求声明 `skipErrorMessage`，否则全局展示一次 `message`。
6. `6xx`：记录错误，上报监控，展示固定文案“系统繁忙，请稍后重试”。
7. 无标准响应体：按网络异常处理。

不要先按 HTTP 200 当作成功返回，否则业务错误会被误当成正常数据。

## 4. 当前具体响应码

| code | 场景 | 前端行为 |
| --- | --- | --- |
| `200` | 成功 | 返回 `data` |
| `400` | 账号密码错误、用户停用、锁定或 IP 受限 | 登录页展示 `message`，停留在密码步骤 |
| `401` | JWT 无效、Redis 会话不存在或登录已过期 | 清理认证状态，跳转登录页 |
| `403` | 当前用户没有接口权限 | 跳转 403 页面或显示无权限页面，不触发重新登录 |
| `410` | MFA 挑战不存在、无效或过期 | 清除 MFA 挑战，返回密码登录步骤 |
| `411` | MFA 挑战用途不匹配 | 清除 MFA 挑战，返回密码登录步骤 |
| `412` | MFA 状态在认证过程中发生变化 | 清除 MFA 挑战，重新登录 |
| `413` | MFA 动态码错误、过期或已使用 | 停留 MFA 步骤，清空动态码并允许重试 |
| `414` | MFA 尝试次数达到上限 | 清除 MFA 挑战，返回密码登录步骤 |
| `500` | 通用业务错误 | 展示 `message` |
| `501` | 参数或查询条件校验失败 | 表单内展示或全局展示 `message` |
| `502` | 数据与有效记录重复 | 展示 `message` |
| `503` | 查询或操作的资源不存在 | 展示 `message`，必要时刷新列表 |
| `504` | 当前业务状态不允许该操作 | 展示 `message` |
| `600` | 未预期的服务端异常 | 不展示后端消息；展示固定兜底文案并上报 |

## 5. 推荐的 TypeScript 类型

```ts
export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T | null;
}

export class ApiBusinessError extends Error {
  constructor(
    public readonly code: number,
    message: string,
    public readonly silent: boolean,
  ) {
    super(message);
    this.name = 'ApiBusinessError';
  }
}

export function isApiEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  if (!value || typeof value !== 'object') return false;
  const body = value as Record<string, unknown>;
  return (
    typeof body.code === 'number' &&
    typeof body.message === 'string' &&
    'data' in body
  );
}
```

## 6. 推荐的统一响应处理器

下面代码是框架无关的核心逻辑。`showError`、`reportError`、`clearSession` 和 `redirectToLoginOnce` 由前端项目实现。

```ts
interface HandleContext {
  skipErrorMessage?: boolean;
}

export function handleApiResponse<T>(
  body: ApiEnvelope<T>,
  context: HandleContext = {},
): T | null {
  const { code, data, message } = body;
  const family = Math.floor(code / 100);

  if (code === 200) return data;

  if (code === 401) {
    clearSession();
    redirectToLoginOnce();
    throw new ApiBusinessError(code, message, true);
  }

  if (family === 4) {
    throw new ApiBusinessError(code, message, true);
  }

  if (family === 5) {
    if (!context.skipErrorMessage) {
      showError(message || '操作失败');
    }
    throw new ApiBusinessError(code, message, false);
  }

  if (family === 6) {
    reportError({ code, message });
    if (!context.skipErrorMessage) {
      showError('系统繁忙，请稍后重试');
    }
    throw new ApiBusinessError(code, '系统繁忙，请稍后重试', false);
  }

  reportError({ code, message: `未知业务响应码: ${message}` });
  if (!context.skipErrorMessage) {
    showError('请求处理失败，请稍后重试');
  }
  throw new ApiBusinessError(code, message, false);
}
```

## 7. Axios 拦截器参考实现

```ts
import type { AxiosError, AxiosResponse } from 'axios';

axiosInstance.interceptors.response.use(
  (response: AxiosResponse<ApiEnvelope<unknown>>) => {
    const body = response.data;

    if (!isApiEnvelope(body)) {
      reportError({ message: '接口未返回标准响应结构' });
      throw new Error('接口响应格式错误');
    }

    return handleApiResponse(body, {
      skipErrorMessage: Boolean(
        (response.config as typeof response.config & {
          skipErrorMessage?: boolean;
        }).skipErrorMessage,
      ),
    });
  },
  (error: AxiosError) => {
    // 这里处理的是未进入标准应用响应流程的错误，例如超时、断网、网关错误。
    const body = error.response?.data;

    // 某些代理可能转发标准业务响应，即使 HTTP 非 200，也优先读取业务 code。
    if (isApiEnvelope(body)) {
      return handleApiResponse(body, {
        skipErrorMessage: Boolean(
          (error.config as typeof error.config & {
            skipErrorMessage?: boolean;
          })?.skipErrorMessage,
        ),
      });
    }

    reportError(error);
    showError('网络异常或服务不可用，请稍后重试');
    return Promise.reject(error);
  },
);
```

拦截器成功分支返回的是 `data`，因此业务 API 函数拿到的通常已经是数据本身，不要再次访问 `.data.data`。

## 8. 当前 Vben 项目的改造要点

当前前端 `src/api/request.ts` 使用 `defaultResponseInterceptor`。对接本服务时必须满足：

1. `successCode` 至少包含 `code === 200`。新系统接口不要再把 `code === 0` 当作本服务成功码。
2. 现有 `authenticateResponseInterceptor` 如果只检查 HTTP 401，将无法识别登录失效，因为后端返回 HTTP 200、业务码 401。
3. 必须在默认错误提示之前读取响应体业务码，并对 `code === 401` 调用已有的 `doReAuthenticate()`。
4. `400`、`410`～`414` 由登录或 MFA 页面自行处理，调用这些接口时建议传入 `skipErrorMessage: true`，避免页面提示和全局提示重复。
5. `5xx` 使用 Ant Design Vue 的 `message.error` 展示后端 `message`，建议使用固定 `key` 去重。
6. `600` 不允许把后端 `message` 直接展示给用户。
7. 多个并发请求同时返回 `401` 时，只允许触发一次退出和跳转。项目现有的 `reauthStarted` 可继续复用。

建议将业务码提取封装为：

```ts
function getBusinessResponse(error: any): ApiEnvelope<unknown> | undefined {
  const candidates = [
    error?.response?.data,
    error?.data,
    error?.cause?.response?.data,
  ];
  return candidates.find(isApiEnvelope);
}
```

具体字段路径可能受 `@vben/request` 版本影响。前端 AI 修改前应先确认 `defaultResponseInterceptor` 抛出的错误对象结构，再决定从 `error.response.data` 还是 `error.data` 读取。

## 9. 登录和 MFA 页面处理示例

```ts
try {
  const result = await loginApi(form);
  handleLoginResult(result);
} catch (error) {
  if (!(error instanceof ApiBusinessError)) throw error;

  switch (error.code) {
    case 400:
      setPasswordError(error.message);
      break;
    case 410:
    case 411:
    case 412:
    case 414:
      clearMfaChallenge();
      goToPasswordStep();
      showPageError(error.message);
      break;
    case 413:
      clearMfaCodeInput();
      showMfaError(error.message);
      break;
  }
}
```

登录和 MFA 完整状态流转以 [MFA 二次认证前端对接文档](FRONTEND_MFA_INTEGRATION.md) 为准。

## 10. 页面级提示责任

| 场景 | 全局拦截器 | 调用页面 |
| --- | --- | --- |
| `200` | 返回数据 | 正常渲染，可自行提示操作成功 |
| `400`、`410`～`414` | 静默抛出 | 登录/MFA 页面展示对应提示 |
| `401` | 清理认证并跳转 | 不重复提示 |
| `403` | 静默抛出或进入无权限路由 | 展示无权限页面 |
| `5xx` | 默认展示 `message` | 不再重复弹窗；表单可使用 `skipErrorMessage` 自行展示 |
| `6xx` | 展示固定兜底文案并上报 | 不展示后端详情 |
| 网络异常 | 展示网络异常文案 | 可提供重试按钮 |

## 11. 验收清单

前端完成改造后至少验证以下场景：

- 成功响应 `code=200` 能正确取得 `data`。
- HTTP 200、`code=504` 时不会进入成功逻辑，并且只显示一次后端消息。
- HTTP 200、`code=401` 时能清理 token，并且并发请求只跳转一次登录页。
- `code=413` 时停留在 MFA 页面，不触发全局弹窗或退出登录。
- `code=600` 时用户只能看到固定兜底文案，控制台或监控可记录业务码。
- 请求超时、断网、502 网关错误等无标准响应体的场景能显示网络异常提示。
- 使用 `skipErrorMessage: true` 时，全局不弹错误，由调用页面负责提示。
- API 函数已经返回 `data` 时，页面没有错误地继续读取 `.data.data`。

## 12. 禁止事项

- 禁止使用 `response.status === 200` 判断业务成功。
- 禁止把 `4xx` 业务码误认为 HTTP 状态码。
- 禁止对所有非 200 业务码统一弹出后端 `message`。
- 禁止向用户展示 `6xx` 返回的后端错误详情。
- 禁止在拦截器和页面中对同一个错误重复提示。
- 禁止自动刷新 JWT。本服务使用 Redis 有状态会话，`401` 应清理状态并重新登录。
