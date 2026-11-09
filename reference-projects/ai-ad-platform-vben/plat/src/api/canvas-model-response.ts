/**
 * 画布与模型管理接口的 fetch 响应解包。
 *
 * @remarks
 * 该适配器只供 AdGen 画布和模型管理使用，不接入项目全局请求层。
 * 页面已经拥有错误反馈入口，因此本层只抛出一次规范化错误，不主动弹窗。
 * AdGen 失败文案经常就是服务商原文，6xx 也必须保留可展示的 message，
 * 不能套用 Java 系统错误的「禁止展示后端详情」规则。
 */

import { isApiEnvelope } from './backend-response';

const NETWORK_ERROR_MESSAGE = '网络异常或服务不可用，请稍后重试';

const INTERNAL_DUMP_RE =
  /traceback|exception in thread|sqlstate|java\.(lang|sql)|stack trace|at [\w.$]+\(/i;

const GENERIC_FAILURE_MESSAGES = new Set([
  '后端处理失败',
  '操作失败',
  '请求处理失败',
  '请求处理失败，请稍后重试',
  '系统繁忙，请稍后重试',
  '服务端处理异常',
]);

export class CanvasApiError extends Error {
  readonly code?: number;
  readonly detail: string;
  readonly reason?: string;
  readonly rawMessage: string;

  constructor(
    message: string,
    options: {
      code?: number;
      detail?: string;
      rawMessage?: string;
      reason?: string;
    } = {},
  ) {
    super(message);
    this.name = 'CanvasApiError';
    this.code = options.code;
    this.detail = options.detail ?? '';
    this.reason = options.reason;
    this.rawMessage = options.rawMessage ?? message;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function pickFailureMessage(body: Record<string, unknown>): {
  detail: string;
  message: string;
} {
  const data = isRecord(body.data) ? body.data : {};
  const candidates = [
    readString(body.error),
    readString(body.message),
    readString(data.error),
    readString(data.message),
    readString(data.fail_reason),
    readString(data.error_message),
  ].filter(Boolean);
  const details = [
    readString(body.detail),
    readString(data.detail),
    readString(data.error_detail),
  ].filter(Boolean);

  const message =
    candidates.find(
      (text) =>
        !INTERNAL_DUMP_RE.test(text) && !GENERIC_FAILURE_MESSAGES.has(text),
    ) ||
    candidates.find((text) => !INTERNAL_DUMP_RE.test(text)) ||
    candidates[0] ||
    '后端处理失败';
  const detail = details.find((text) => text !== message) || '';
  return { message, detail };
}

function throwCanvasFailure(
  body: Record<string, unknown>,
  code?: number,
): never {
  const { message, detail } = pickFailureMessage(body);
  const data = isRecord(body.data) ? body.data : {};
  const reason =
    readString(data.error_code) ||
    readString(body.error_code) ||
    readString(body.code);
  throw new CanvasApiError(
    detail ? `${message}\n\n--- 后端完整错误 ---\n${detail}` : message,
    { code, detail, rawMessage: message, reason: reason || undefined },
  );
}

/**
 * 解析画布或模型管理接口的统一响应信封。
 *
 * 业务是否成功只由响应体 `code` 决定，不使用 HTTP 200 作为成功依据。
 */
export async function readCanvasModelApiResponse<T>(
  response: Response,
): Promise<T> {
  let bodyText = '';
  try {
    bodyText = await response.text();
  } catch (error) {
    console.error('[CanvasModelApi] 读取响应体失败', {
      status: response.status,
      url: response.url,
      error,
    });
    throw new Error(NETWORK_ERROR_MESSAGE);
  }

  const body: unknown = bodyText
    ? (() => {
        try {
          return JSON.parse(bodyText);
        } catch (error) {
          console.error('[CanvasModelApi] 响应体 JSON 解析失败', {
            status: response.status,
            url: response.url,
            raw: bodyText.slice(0, 200),
            error,
          });
          return undefined;
        }
      })()
    : undefined;

  if (!isApiEnvelope(body)) {
    if (isRecord(body) && 'success' in body) {
      if (body.success === false) {
        throwCanvasFailure(body);
      }

      return body as T;
    }

    if (!response.ok) {
      if (isRecord(body)) {
        throwCanvasFailure(body, response.status);
      }
      throw new CanvasApiError(
        `请求失败，HTTP ${response.status} ${response.statusText}`,
        { code: response.status },
      );
    }

    console.error('[CanvasModelApi] 接口未返回标准响应结构', {
      status: response.status,
      url: response.url,
      raw: bodyText ? bodyText.slice(0, 200) : undefined,
    });
    throw new Error(NETWORK_ERROR_MESSAGE);
  }

  if (body.code === 200 || body.code === 0) {
    return body.data as T;
  }

  throwCanvasFailure(body, body.code);
}
