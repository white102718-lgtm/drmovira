/**
 * AdPulse System Server 统一响应处理。
 *
 * 该服务端约定：只要请求能到达 Java 应用并由应用生成响应，HTTP 状态码恒为 200，
 * 必须通过响应体中的业务码 `code` 判断成功或失败。详见
 * analysis-output/FRONTEND_API_RESPONSE_INTEGRATION.md。
 *
 * 业务码分段：
 * - `2xx`：业务成功，返回 `data`。
 * - `4xx`：登录、会话、权限、MFA 等流程错误，全局静默，交给页面处理。
 * - `5xx`：业务错误，默认全局展示后端 `message`。
 * - `6xx`：系统内部错误，禁止展示后端 `message`，统一展示兜底文案。
 */

/** 标准响应体结构。 */
export interface ApiEnvelope<T = unknown> {
  code: number;
  message: string;
  data: T | null;
}

/**
 * 业务错误。
 * - `silent=true`：全局拦截器不弹错误提示，由调用页面或认证流程自行处理。
 * - `silent=false`：允许全局拦截器统一展示 `message`（除非调用方传入 skipErrorMessage）。
 */
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

/** 判断给定的值是否为 AdPulse System Server 标准响应体。 */
export function isApiEnvelope(value: unknown): value is ApiEnvelope {
  if (!value || typeof value !== 'object') return false;
  const body = value as Record<string, unknown>;
  return (
    typeof body.code === 'number' &&
    typeof body.message === 'string' &&
    'data' in body
  );
}

interface ResolveContext {
  /**
   * 调用方声明自行处理错误提示时传入 `true`。
   * 当前实现仅用于语义占位，是否弹窗由上层拦截器统一控制。
   */
  skipErrorMessage?: boolean;
}

/**
 * 按业务码规则解析标准响应体。
 * - 成功（code === 200 / 0）：返回 `data`。
 * - 失败：抛出 `ApiBusinessError`，并依据号段决定 `silent` 与展示文案。
 *
 * 该函数为纯逻辑，不涉及任何副作用，便于单测。
 */
export function resolveBackendResponse<T>(
  body: ApiEnvelope<T>,
  _context: ResolveContext = {},
): T | null {
  const { code, data, message } = body;

  // Java 用 200 表示业务成功，广告数据服务(Python)用 0；失败号段两边一致
  if (code === 200 || code === 0) return data;

  const family = Math.floor(code / 100);

  if (code === 401) {
    // 登录失效：由认证流程或调用页面处理，全局静默
    throw new ApiBusinessError(code, message, true);
  }

  if (family === 4) {
    // 4xx 流程错误（权限/MFA 等）：交给页面处理
    throw new ApiBusinessError(code, message, true);
  }

  if (family === 5) {
    // 5xx 业务错误：默认全局展示后端 message
    throw new ApiBusinessError(code, message || '操作失败', false);
  }

  if (family === 6) {
    // 6xx 系统内部错误：禁止展示后端详情，使用兜底文案
    throw new ApiBusinessError(code, '系统繁忙，请稍后重试', false);
  }

  // 未知号段：使用兜底文案，并保留原始 message 便于排查
  throw new ApiBusinessError(code, '请求处理失败，请稍后重试', false);
}

interface HttpResponse<T = unknown> {
  config: {
    responseReturn?: string;
    responseType?: string;
    [key: string]: unknown;
  };
  data: T;
  headers?: unknown;
  status: number;
  [key: string]: unknown;
}

/** 兼容 AxiosResponseHeaders 与普通对象两种形态，安全读取 content-type。 */
function getContentType(response: HttpResponse): string {
  const headers = response.headers as
    | { get?: (name: string) => unknown; [key: string]: unknown }
    | undefined;
  if (!headers) return '';
  if (typeof headers.get === 'function') {
    return String(headers.get('content-type') ?? '');
  }
  return String(headers['content-type'] ?? '');
}

/**
 * 在 RequestClient 默认解包前校验 AdPulse System Server 业务码。
 *
 * - 成功（code=200）：原样返回 response，由后续 `defaultResponseInterceptor`
 *   根据 `responseReturn: 'data'` 解包 `data`。
 * - 业务失败：抛出 `ApiBusinessError`，并将 `config` 透传到错误对象上，
 *   使下游错误拦截器能读取 `skipErrorMessage` 等请求级标记。
 * - 非标准响应体、下载流、演示数据：原样返回，由下游拦截器处理。
 *
 * 注意：不在此处将业务 401 映射为 HTTP 401。业务 401 由错误拦截器
 * 直接调用 `doReAuthenticate()`（已认证客户端）或交由调用页面（匿名客户端）处理，
 * 避免与 `RequestClient.request()` 的 `error.response.data` 解包逻辑冲突。
 */
export function resolveBackendHttpResponse<
  T extends ApiEnvelope,
  R extends HttpResponse<T>,
>(response: R): R {
  const { config } = response;

  // 下载流和 raw 响应保持 Axios 原始形状
  if (
    config.responseReturn === 'raw' ||
    config.responseType === 'blob' ||
    config.responseType === 'arraybuffer'
  ) {
    return response;
  }

  // 演示数据（demo mock）使用 code=0，不走业务码校验，由 defaultResponseInterceptor 处理
  const contentType = getContentType(response);
  if (contentType.includes('application/x-demo-mock')) {
    return response;
  }

  const body = response.data;
  if (!isApiEnvelope(body)) {
    // 非标准响应体（如网关转发的 HTML 错误页），交给下游处理
    return response;
  }

  try {
    resolveBackendResponse(body);
    return response;
  } catch (error) {
    if (!(error instanceof ApiBusinessError)) throw error;
    // 把请求 config 透传到错误对象上，使错误拦截器能读取 skipErrorMessage
    (error as ApiBusinessError & { config: unknown }).config = config;
    throw error;
  }
}

/**
 * 从各种可能的错误对象位置提取业务响应体。
 * 用于在错误拦截器或调用方中识别"网关/代理在非 200 HTTP 中转发了业务响应"的场景。
 */
export function getBusinessResponse(error: unknown): ApiEnvelope | undefined {
  if (!error || typeof error !== 'object') return undefined;
  const candidates: unknown[] = [
    (error as any)?.response?.data,
    (error as any)?.data,
    (error as any)?.cause?.response?.data,
  ];
  return candidates.find(isApiEnvelope);
}
