import type { FeedbackConsoleEntry, FeedbackDiagnostics } from '#/api/feedback';

const MAX_CONSOLE_ENTRIES = 100;
const MAX_CONSOLE_MESSAGE_LENGTH = 2000;
const SENSITIVE_KEY_PATTERN =
  /api[_-]?key|authorization|cookie|credential|password|passwd|secret|session|token/i;
const SENSITIVE_TEXT_PATTERNS = [
  { pattern: /Bearer\s+[\w.~+/=-]+/gi, replacement: 'Bearer [已脱敏]' },
  {
    pattern:
      /(["']?(?:access_?token|api[_-]?key|authorization|cookie|credential|password|passwd|refresh_?token|secret|session)["']?\s*[:=]\s*)[^,\s}"']+/gi,
    replacement: '$1[已脱敏]',
  },
];

const consoleEntries: FeedbackConsoleEntry[] = [];
let isInstalled = false;

function redactText(value: string) {
  let redacted = value;
  for (const { pattern, replacement } of SENSITIVE_TEXT_PATTERNS) {
    redacted = redacted.replace(pattern, replacement);
  }
  return redacted;
}

function serializeConsoleArgument(value: unknown) {
  if (value instanceof Error)
    return redactText(`${value.name}: ${value.message}`);
  if (typeof value === 'string') return redactText(value);
  try {
    const seen = new WeakSet<object>();
    return redactText(
      JSON.stringify(value, (key, nestedValue) => {
        if (SENSITIVE_KEY_PATTERN.test(key)) return '[已脱敏]';
        if (typeof nestedValue === 'object' && nestedValue !== null) {
          if (seen.has(nestedValue)) return '[循环引用]';
          seen.add(nestedValue);
        }
        return nestedValue;
      }),
    );
  } catch {
    return redactText(String(value));
  }
}

function currentPageUrl() {
  const url = new URL(window.location.href);
  for (const key of url.searchParams.keys()) {
    if (SENSITIVE_KEY_PATTERN.test(key)) {
      url.searchParams.set(key, '[已脱敏]');
    }
  }
  url.hash = redactText(url.hash);
  return url.toString().slice(0, 1000);
}

function recordConsoleEntry(
  level: FeedbackConsoleEntry['level'],
  values: unknown[],
) {
  const message = values
    .map((value) => serializeConsoleArgument(value))
    .join(' ')
    .slice(0, MAX_CONSOLE_MESSAGE_LENGTH);
  consoleEntries.push({
    level,
    message,
    timestamp: new Date().toISOString(),
  });
  if (consoleEntries.length > MAX_CONSOLE_ENTRIES) consoleEntries.shift();
}

/**
 * 安装内存诊断缓冲区。
 *
 * @remarks
 * 只保留本次页面会话中最近100条脱敏控制台信息，不读取Cookie、Token或本地存储，
 * 也不会把日志持久化；用户提交反馈时才会随反馈发送。
 */
export function installFeedbackDiagnostics() {
  if (isInstalled || typeof window === 'undefined') return;
  isInstalled = true;

  const browserConsole = globalThis.console;
  (['log', 'info', 'warn', 'error'] as const).forEach((level) => {
    const original = browserConsole[level].bind(browserConsole);
    browserConsole[level] = (...values: unknown[]) => {
      recordConsoleEntry(level, values);
      original(...values);
    };
  });

  window.addEventListener('error', (event) => {
    recordConsoleEntry('error', [
      `未捕获错误: ${event.message} (${event.filename}:${event.lineno}:${event.colno})`,
    ]);
  });
  window.addEventListener('unhandledrejection', (event) => {
    recordConsoleEntry('error', ['未处理 Promise 异常:', event.reason]);
  });
}

function detectDeviceType() {
  const userAgent = navigator.userAgent;
  if (/tablet|ipad/i.test(userAgent)) return 'tablet';
  if (/mobile|android|iphone/i.test(userAgent) || window.innerWidth < 768) {
    return 'mobile';
  }
  return 'desktop';
}

function detectBrowser() {
  const userAgent = navigator.userAgent;
  if (/Edg\//.test(userAgent)) return 'Microsoft Edge';
  if (/Chrome\//.test(userAgent)) return 'Google Chrome';
  if (/Firefox\//.test(userAgent)) return 'Mozilla Firefox';
  if (/Safari\//.test(userAgent) && !/Chrome\//.test(userAgent)) {
    return 'Apple Safari';
  }
  return '未知浏览器';
}

function detectOperatingSystem() {
  const userAgent = navigator.userAgent;
  if (/Windows NT/.test(userAgent)) return 'Windows';
  if (/Android/.test(userAgent)) return 'Android';
  if (/iPhone|iPad|iPod/.test(userAgent)) return 'iOS/iPadOS';
  if (/Mac OS X/.test(userAgent)) return 'macOS';
  if (/Linux/.test(userAgent)) return 'Linux';
  return navigator.platform || '未知系统';
}

/** 生成用户确认提交时的客户端运行环境快照。 */
export function collectFeedbackDiagnostics(routeName?: string) {
  const extendedNavigator = navigator as Navigator & {
    connection?: { effectiveType?: string; type?: string };
    deviceMemory?: number;
  };
  return {
    appVersion: import.meta.env.VITE_APP_VERSION || 'unknown',
    browser: detectBrowser(),
    consoleLogs: [...consoleEntries],
    deviceMemory: extendedNavigator.deviceMemory,
    devicePixelRatio: window.devicePixelRatio,
    deviceType: detectDeviceType(),
    hardwareConcurrency: navigator.hardwareConcurrency,
    language: navigator.language,
    networkType:
      extendedNavigator.connection?.effectiveType ||
      extendedNavigator.connection?.type,
    operatingSystem: detectOperatingSystem(),
    pageUrl: currentPageUrl(),
    routeName,
    screenResolution: `${window.screen.width}×${window.screen.height}`,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    viewportSize: `${window.innerWidth}×${window.innerHeight}`,
  } satisfies FeedbackDiagnostics;
}

/** 反馈提交成功后清空本次会话日志，避免下一条反馈重复携带旧记录。 */
export function clearFeedbackConsoleEntries() {
  consoleEntries.splice(0);
}
