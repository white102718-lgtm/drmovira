/**
 * 将服务商 / 后端返回的 AIGC 失败原文转成用户可读的中文原因。
 *
 * @remarks
 * 规则优先对齐 BytePlus ModelArk、阿里云百炼、Google Veo、可灵的官方错误码与原文。
 * 画布只展示短提示，因此去掉请求 ID，并说明用户下一步能改什么。
 */

export type ProviderErrorType =
  | 'audio'
  | 'celebrity'
  | 'copyright'
  | 'general'
  | 'media'
  | 'params'
  | 'pixels'
  | 'rate_limit'
  | 'real_person'
  | 'sensitive'
  | 'service';

export interface ProviderErrorParts {
  code: string;
  detail: string;
  message: string;
}

export interface FormattedProviderError {
  message: string;
  suggestions: string[];
  type: ProviderErrorType;
}

export interface ProviderErrorMediaCounts {
  imageCount?: number;
  videoCount?: number;
}

interface MatchContext {
  code: string;
  imageCount?: number;
  lower: string;
  raw: string;
  videoCount?: number;
}

const GENERIC_FALLBACKS = new Set([
  '后端处理失败',
  '操作失败',
  '请求处理失败',
  '请求处理失败，请稍后重试',
  '系统繁忙，请稍后重试',
  '网络异常或服务不可用，请稍后重试',
  '无法获取视频生成进度，请检查网络连接',
  '获取视频生成状态失败',
  '视频生成失败',
  '图片生成失败',
  '服务端处理异常',
]);

const INTERNAL_DUMP_RE =
  /traceback|exception in thread|sqlstate|java\.(lang|sql)|stack trace|at [\w.$]+\(/i;

const ERROR_CODE_RE =
  /\b(?:Input|Output)(?:Text|Image|Video|Audio)?SensitiveContentDetected(?:\.[A-Za-z]+)?\b|\b(?:IPInfringementSuspect|DataInspectionFailed|InvalidParameter(?:\.[A-Za-z]+)?|TaskTypeConstraint|TaskTypeMismatch|QuotaExceeded|Throttling(?:\.[A-Za-z]+)?|ServerOverloaded|RequestBurstTooFast|InflightBatchsizeExceeded|AccountOverdueError|AuthenticationError|OperationDenied(?:\.[A-Za-z]+)?|InternalServiceError|POLICY_VIOLATION|content_moderation)\b/gi;

function asRecord(value: unknown): null | Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function normalizeComparable(text: string): string {
  return text.replace(/\s+/g, '').trim();
}

/** 去掉「服务端处理异常服务端处理异常」这类首尾相接的重复句。 */
function collapseRepeatedPhrase(text: string): string {
  const trimmed = text.replace(/\s+/g, ' ').trim();
  const compact = normalizeComparable(trimmed);
  if (compact.length >= 8 && compact.length % 2 === 0) {
    const half = compact.slice(0, compact.length / 2);
    if (half && half === compact.slice(compact.length / 2)) {
      return half;
    }
  }
  return trimmed;
}

function pushUnique(target: string[], value: string) {
  const text = collapseRepeatedPhrase(value);
  if (!text || target.includes(text)) return;
  if (
    target.some(
      (existing) => normalizeComparable(existing) === normalizeComparable(text),
    )
  ) {
    return;
  }
  target.push(text);
}

function collectErrorTexts(
  value: unknown,
  texts: string[],
  codes: string[],
  depth = 0,
) {
  if (depth > 4 || value == null) return;

  if (typeof value === 'string') {
    pushUnique(texts, value);
    return;
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    pushUnique(codes, String(value));
    return;
  }

  if (value instanceof Error) {
    pushUnique(texts, value.message);
    const extra = value as Error & { detail?: string; rawMessage?: string };
    if (typeof extra.rawMessage === 'string')
      pushUnique(texts, extra.rawMessage);
    if (typeof extra.detail === 'string') pushUnique(texts, extra.detail);
    return;
  }

  const record = asRecord(value);
  if (!record) return;

  const keys = [
    'error',
    'message',
    'detail',
    'msg',
    'reason',
    'error_message',
    'errorMessage',
    'fail_reason',
    'failed_reason',
    'failReason',
  ];
  for (const key of keys) {
    const nested = record[key];
    if (typeof nested === 'string') {
      pushUnique(texts, nested);
      continue;
    }
    if (nested && typeof nested === 'object') {
      collectErrorTexts(nested, texts, codes, depth + 1);
    }
  }

  for (const key of ['code', 'error_code', 'errorCode']) {
    const nested = record[key];
    if (typeof nested === 'string' && /[A-Za-z]/.test(nested)) {
      pushUnique(codes, nested);
    }
  }

  if ('data' in record) collectErrorTexts(record.data, texts, codes, depth + 1);
}

/**
 * 从任务轮询结果、响应信封或 Error 中抽出最有用的原文。
 */
export function extractProviderErrorParts(
  ...payloads: unknown[]
): ProviderErrorParts {
  const texts: string[] = [];
  const codes: string[] = [];
  payloads.forEach((payload) => collectErrorTexts(payload, texts, codes));

  const useful = texts.filter(
    (text) => !GENERIC_FALLBACKS.has(text) && !INTERNAL_DUMP_RE.test(text),
  );
  const [message = texts[0] || '', ...rest] =
    useful.length > 0 ? useful : texts;
  return {
    code: codes[0] || '',
    message,
    detail: rest.join('\n'),
  };
}

function stripNoise(raw: string): string {
  return raw
    .replace(/--- 后端完整错误 ---/g, '\n')
    .replace(/request id[:：]\s*\S+/gi, ' ')
    .replace(/requestid[:：]\s*\S+/gi, ' ')
    .replace(/Seedance任务失败[^\s:：]*/gi, ' ')
    .replace(/Seedance request failed\s*[-—]?\s*[\w-]+[:：]?\s*/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function collectCodes(raw: string, explicitCode = ''): string {
  const found = raw.match(ERROR_CODE_RE) || [];
  return [explicitCode, ...found].filter(Boolean).join(' ');
}

function parseImageIndex(raw: string): number | null {
  // 只认图片/视频槽位。content[0] 通常是提示词，content[1] 才是第一张图，不能当成第 2 张参考图。
  const match = raw.match(
    /(?:input image|image data|input video)\s*\[(\d+)\]/i,
  );
  if (!match) return null;
  return Number(match[1]) + 1;
}

function describeReferenceMedia(
  raw: string,
  kind: 'image' | 'video',
  count?: number,
): string {
  const label = kind === 'video' ? '参考视频' : '参考图';
  const index = parseImageIndex(raw);
  if (!index) return label;
  if (count != null && count <= 1) return label;
  if (count != null && index > count) return label;
  if (count == null && index === 1) return label;
  return `第 ${index} ${kind === 'video' ? '个' : '张'}${label}`;
}

function parsePixelLimit(raw: string): {
  height?: string;
  maxPixels?: string;
  width?: string;
} {
  const current = raw.match(/Current dimensions:\s*(\d+)\s*[x×]\s*(\d+)/i);
  const maximum = raw.match(/Maximum allowed:\s*(\d+)/i);
  return {
    width: current?.[1],
    height: current?.[2],
    maxPixels: maximum?.[1]
      ? String(Math.round(Number(maximum[1]) / 10_000))
      : undefined,
  };
}

function buildMessage(
  summary: string,
  suggestion: string,
): FormattedProviderError['message'] {
  return `${summary}。${suggestion}`;
}

function result(
  type: ProviderErrorType,
  summary: string,
  suggestion: string,
  suggestions: string[] = [],
): FormattedProviderError {
  return {
    type,
    message: buildMessage(summary, suggestion),
    suggestions,
  };
}

function includesAny(
  haystack: string,
  patterns: Array<RegExp | string>,
): boolean {
  return patterns.some((pattern) =>
    typeof pattern === 'string'
      ? haystack.includes(pattern)
      : pattern.test(haystack),
  );
}

/**
 * 按服务商官方错误码和常见原文匹配。顺序即优先级，更具体的规则必须靠前。
 */
function matchOfficialError(ctx: MatchContext): FormattedProviderError | null {
  const { raw, lower, code } = ctx;
  const haystack = `${code} ${lower} ${raw}`;

  if (
    includesAny(haystack, [
      /privacyinformation/i,
      /real person/,
      /real human/,
      /not eligible/,
      '真人',
      '真实人脸',
      '真实人物',
    ])
  ) {
    const isVideo = /input video|参考视频|inputvideo/i.test(haystack);
    const target = describeReferenceMedia(
      raw,
      isVideo ? 'video' : 'image',
      isVideo ? ctx.videoCount : ctx.imageCount,
    );
    return result(
      'real_person',
      `${target}可能包含真人肖像，服务商已拒绝处理`,
      '请更换该素材，改用 AI 虚拟人物，或先把真人素材登记到官方素材库',
      [`更换${target}`, '可改用 AI 虚拟人物或无人物素材'],
    );
  }

  if (
    includesAny(haystack, [
      /policyviolation/i,
      /ipinfringementsuspect/i,
      /copyright/,
      '版权',
      '知识产权',
    ])
  ) {
    const isOutput = /output|生成结果|输出/.test(haystack);
    return result(
      'copyright',
      isOutput
        ? '生成结果可能涉及版权限制，服务商已拒绝输出'
        : '提示词或参考素材可能涉及版权限制，服务商已拒绝处理',
      '请去掉影视、品牌、游戏角色等受保护内容后重试',
      ['更换可能涉及版权的参考图、参考视频或提示词'],
    );
  }

  if (
    includesAny(haystack, [
      /celebrity|public figure|likenesses/,
      /29310472|15236754/,
      '名人',
      '公众人物',
      '明星',
    ])
  ) {
    return result(
      'celebrity',
      '参考素材或提示词被识别为明星、网红或公众人物',
      '请改用普通模特、AI 虚拟人物，或不含人物的产品/场景图',
      ['不要上传明星、网红、艺人或影视截图'],
    );
  }

  if (
    includesAny(haystack, [
      /58061214|17301594/,
      /\bchild\b|\bminor\b|underage/,
      '未成年人',
      '儿童',
    ])
  ) {
    return result(
      'sensitive',
      '内容涉及未成年人形象，服务商安全策略已拒绝生成',
      '请更换不含未成年人的提示词和参考素材',
    );
  }

  if (
    includesAny(haystack, [
      /deepfake/i,
      /counterfeit documents|credentials/,
      '伪造证件',
    ])
  ) {
    return result(
      'sensitive',
      '生成结果可能包含伪造证件或仿冒身份内容',
      '请去掉证件、证照或仿冒身份相关描述后重试',
    );
  }

  if (
    includesAny(haystack, [
      /inputtextsensitivecontentdetected/i,
      /input text may contain sensitive/,
      /prompt couldn't be submitted/,
      /violate our policies/,
    ])
  ) {
    return result(
      'sensitive',
      '提示词未通过内容安全审核',
      '请改写提示词，避免色情、暴力、政治或侵权描述',
    );
  }

  if (
    includesAny(haystack, [
      /inputimagesensitivecontentdetected/i,
      /input image may contain sensitive/,
    ])
  ) {
    const target = describeReferenceMedia(raw, 'image', ctx.imageCount);
    return result(
      'sensitive',
      `${target}未通过内容安全审核`,
      '请更换该图片后重试',
    );
  }

  if (
    includesAny(haystack, [
      /inputvideosensitivecontentdetected/i,
      /input video may contain sensitive/,
    ])
  ) {
    return result(
      'sensitive',
      '参考视频未通过内容安全审核',
      '请更换参考视频或裁剪敏感片段后重试',
    );
  }

  if (
    includesAny(haystack, [
      /inputaudiosensitivecontentdetected/i,
      /input audio may contain sensitive/,
    ])
  ) {
    return result(
      'sensitive',
      '参考音频未通过内容安全审核',
      '请更换音频，或去掉可能侵权的歌曲、人声后重试',
    );
  }

  if (
    includesAny(haystack, [
      /output(?:text|image|video|audio)?sensitivecontentdetected/i,
      /output (?:video|image|audio|text) may contain sensitive/,
      /generated (?:video|image|audio) may contain sensitive/,
    ])
  ) {
    return result(
      'sensitive',
      '生成结果未通过内容安全审核',
      '请调整提示词或参考素材后重试，相同内容再次提交仍会被拦截',
    );
  }

  if (
    includesAny(haystack, [
      /datainspectionfailed/i,
      /sensitivecontentdetected/i,
      /content_moderation|policy_violation|community guidelines|cm_ext/i,
      /rai|responsible ai|usage guidelines/,
      /90789179|43188360|61493863|56562880|62263041|57734940|22137204/,
      '100008',
      '100009',
      '100023',
      '绿网',
      '内容安全',
      '审核未通过',
      '敏感信息',
      '敏感内容',
      '违规内容',
    ])
  ) {
    return result(
      'sensitive',
      '内容未通过服务商安全审核',
      '请改写提示词或更换参考素材后重试，不要重复提交相同内容',
    );
  }

  if (
    includesAny(haystack, [
      /identified your task as video editing/,
      /classified your task as/,
      /tasktypeconstraint/i,
      /tasktypemismatch/i,
    ]) ||
    (/ratio/.test(lower) && /adaptive/.test(lower) && /duration/.test(lower))
  ) {
    return result(
      'params',
      '当前提示词被识别为「视频编辑」任务，或所选模式与提示词不一致',
      '该模式通常要求画幅为「自适应」、时长跟随原视频（需 4–30 秒）。请改画幅，或调整提示词/参考视频',
      ['将画幅改为自适应', '参考视频时长需在 4–30 秒'],
    );
  }

  if (
    includesAny(haystack, [
      /maximum allowed total pixels|exceeds the maximum allowed/,
      /invalidpixellimit/i,
      /image (?:size|resolution).*(?:too large|exceed)/,
      /resolution (?:too large|exceed)/,
    ])
  ) {
    const { width, height, maxPixels } = parsePixelLimit(raw);
    const sizeText =
      width && height ? `当前约 ${width}×${height}` : '当前分辨率过高';
    const limitText = maxPixels
      ? `超过上限约 ${maxPixels} 万像素`
      : '超过服务商像素或边长上限';
    return result(
      'pixels',
      `参考图尺寸过大（${sizeText}，${limitText}）`,
      '请压缩或裁剪后再试，常见要求是单边 300–6000 像素、宽高比 0.4–2.5',
    );
  }

  if (
    includesAny(haystack, [
      /too small|min(?:imum)? .*(?:width|height|resolution|pixels)/,
      /aspect ratio/,
      '尺寸过小',
      '长宽比',
      '宽高比',
    ])
  ) {
    return result(
      'pixels',
      '参考图尺寸或宽高比不符合模型要求',
      '请调整到模型支持的分辨率和宽高比后重试，常见要求是单边不少于 300 像素',
    );
  }

  if (
    includesAny(haystack, [
      /duration.+(?:invalid|must|between|range|exceed|too (?:long|short))/,
      /invalid_duration/,
      '时长不符合',
      '时长超过',
      '时长过',
    ])
  ) {
    return result(
      'media',
      '参考视频或音频时长不符合模型要求',
      '请裁剪到模型支持的时长后重试。Seedance 参考视频常见为 2–15 秒，视频编辑常见为 4–30 秒',
    );
  }

  if (
    includesAny(haystack, [
      /invalidimageurl|empty ?(?:base64 )?(?:image )?url|invalidformat|invalid (?:base64 )?image|corrupted/,
      /unsupported (?:file )?format|file format/,
      /unable to parse or process the image/,
      /payload too large|request (?:body )?too large|file (?:size )?(?:exceed|too large)/,
      '格式不支持',
      '文件损坏',
      '文件过大',
      '无法打开',
    ])
  ) {
    return result(
      'media',
      '参考素材格式、大小无效或文件已损坏',
      '请改用 jpg/png/webp 图片或 mp4/mov 视频，并确保单张图小于 30MB、视频小于 200MB',
    );
  }

  if (
    includesAny(haystack, [
      /download (?:failed|timeout)|failed to download|url.*(expired|not (?:found|accessible))/,
      '下载失败',
      '下载超时',
      '无法下载',
      '链接无法访问',
    ])
  ) {
    return result(
      'media',
      '服务商无法下载参考素材',
      '请确认图片或视频可正常打开后重新上传，不要使用已过期的临时链接',
    );
  }

  if (
    includesAny(haystack, [
      /quotaexceeded|ratelimit|too many requests|server ?overload|request ?burst|inflight ?batchsize/,
      /throttling|\brpm\b|\btpm\b|\bipm\b|\b429\b/,
      /concurrent (task )?limit/,
      '百炼任务轮询超时',
      '限流',
      '并发',
      '额度',
      '配额',
    ])
  ) {
    return result(
      'rate_limit',
      '当前并发生成任务过多，或服务商额度/限流已用尽',
      '请稍后再试，避免连续提交多个任务',
      ['等待进行中的任务完成后再提交'],
    );
  }

  if (
    includesAny(haystack, [
      /accountoverdue|servicenotopen|authenticationerror|accessdenied|operationdenied/,
      /overdue balance|account (?:balance )?is overdue/,
      /insufficient[_ ](?:credits|balance)|membership_required/,
      '欠费',
      '未开通',
      '余额不足',
    ])
  ) {
    return result(
      'service',
      '生成服务暂时不可用',
      '请稍后重试。若连续失败，请联系管理员检查模型开通或额度配置',
    );
  }

  if (
    includesAny(haystack, [
      /specific song|background music|\bbgm\b|copyrighted (?:music|song|audio)/,
      '指定配乐',
      '具体歌曲',
      '名人声音',
    ])
  ) {
    return result(
      'audio',
      '提示词包含受限的歌曲、名人声音或指定配乐',
      '请去掉具体曲名和音色要求，改用「轻快配乐」这类通用描述',
    );
  }

  if (
    includesAny(haystack, [
      /400 bad request|could not understand|invalidparameter|missingparameter/,
      /size is not match|not valid|invalid argument/,
      'sent a request that this server could not understand',
      '参数错误',
      '参数非法',
      '缺少参数',
    ])
  ) {
    return result(
      'params',
      '服务商无法接受本次请求参数',
      '请检查画幅、时长、分辨率、生成模式和参考素材数量是否与当前模型匹配后重试',
      ['核对模型支持的画幅、时长和参考素材数量'],
    );
  }

  if (
    includesAny(haystack, [
      /internalserviceerror|internal(?: server)? error|unexpected internal error/,
      /provider_(?:error|timeout|unavailable)|timed_out/,
      '系统异常',
      '内部错误',
    ])
  ) {
    return result(
      'service',
      '服务商内部异常，本次生成没有完成',
      '请稍后重试。这通常不是提示词问题，连续失败请联系管理员',
    );
  }

  return null;
}

function joinDistinctErrorTexts(...parts: Array<string | undefined>): string {
  const texts: string[] = [];
  parts.forEach((part) => {
    if (typeof part === 'string') pushUnique(texts, part);
  });
  return texts.join('\n');
}

/**
 * 把服务商原文转成可直接展示给用户的中文原因。
 */
export function formatProviderError(
  message: string,
  detail = '',
  fallback = '生成失败，请根据提示调整后重试',
  mediaCounts: ProviderErrorMediaCounts = {},
): FormattedProviderError {
  const raw = stripNoise(joinDistinctErrorTexts(message, detail));
  const lower = raw.toLowerCase();
  const code = collectCodes(`${message}\n${detail}`, '');

  if (!raw && !code) {
    return { type: 'general', message: fallback, suggestions: [] };
  }

  const matched = matchOfficialError({
    raw,
    lower,
    code,
    imageCount: mediaCounts.imageCount,
    videoCount: mediaCounts.videoCount,
  });
  if (matched) return matched;

  if (GENERIC_FALLBACKS.has(raw) || INTERNAL_DUMP_RE.test(raw)) {
    return { type: 'general', message: fallback, suggestions: [] };
  }

  // 原文已经是简短中文时直接展示；过长英文则收成一句可读摘要。
  if (/[\u4e00-\u9fff]/.test(raw) && raw.length <= 160) {
    return { type: 'general', message: raw, suggestions: [] };
  }

  const compact = raw.length > 180 ? `${raw.slice(0, 180).trim()}…` : raw;
  return {
    type: 'general',
    message: `生成失败：${compact}`,
    suggestions: [],
  };
}

export function formatProviderErrorMessage(
  message: string,
  detail = '',
  fallback = '生成失败，请根据提示调整后重试',
  mediaCounts: ProviderErrorMediaCounts = {},
): string {
  return formatProviderError(message, detail, fallback, mediaCounts).message;
}

export function toUserFacingGenerationError(
  error: unknown,
  fallback: string,
  mediaCounts: ProviderErrorMediaCounts = {},
): string {
  if (error && typeof error === 'object' && 'message' in error) {
    const typed = error as {
      detail?: string;
      message?: string;
      originalReason?: string;
    };
    const cleanedMessage = collapseRepeatedPhrase(typed.message || '');
    if (
      cleanedMessage &&
      /[\u4e00-\u9fff]/.test(cleanedMessage) &&
      cleanedMessage.length <= 160 &&
      !GENERIC_FALLBACKS.has(cleanedMessage)
    ) {
      const rematch = formatProviderError(
        cleanedMessage,
        joinDistinctErrorTexts(typed.detail, typed.originalReason),
        fallback,
        mediaCounts,
      );
      if (rematch.type !== 'general' || rematch.message !== cleanedMessage) {
        return rematch.message;
      }
      return cleanedMessage;
    }
    const parts = extractProviderErrorParts(error);
    return formatProviderErrorMessage(
      parts.message || cleanedMessage || typed.message || '',
      joinDistinctErrorTexts(
        parts.detail,
        typed.detail,
        typed.originalReason,
        parts.code,
      ),
      fallback,
      mediaCounts,
    );
  }

  return formatProviderErrorMessage(
    String(error || ''),
    '',
    fallback,
    mediaCounts,
  );
}
