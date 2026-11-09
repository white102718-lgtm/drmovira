function extension(name: string) {
  const match = name.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] ?? '';
}

/** 去掉路径字符，并保证有可用后缀。Chrome 丢了 download 名时至少还能打开。 */
export function safeDownloadName(name: string, fallback = 'download.bin') {
  const cleaned = (name || '')
    .replaceAll(/[/\\?%*:|"<>]/g, '_')
    .replaceAll(/\s+/g, ' ')
    .trim();
  const base = cleaned || fallback;
  const ext = extension(base) || extension(fallback);
  if (ext && !base.toLowerCase().endsWith(`.${ext}`)) return `${base}.${ext}`;
  return base;
}

/**
 * `<a download>` 遇到中文会被 Chrome / Android 直接丢掉。
 * 这个名字只当 ASCII 兜底，真实中文名走 Content-Disposition 的 filename*。
 */
export function asciiDownloadName(name: string, fallback = 'download.bin') {
  const original = safeDownloadName(name, fallback);
  const ext = extension(original) || extension(fallback) || 'bin';
  const stem = original.replace(/\.[^.]+$/, '');
  const ascii =
    stem.replaceAll(/[^\w.-]+/g, '_').replaceAll(/^_+|_+$/g, '') || 'download';
  return `${ascii}.${ext}`;
}

/** 对话附件必须走页面同源的 /agent/v1/blob/…，不能用 blob: 地址。 */
export function agentBlobHref(url: string, download = false, filename = '') {
  if (!url) return '';
  try {
    const parsed = url.startsWith('http')
      ? new URL(url)
      : new URL(url, 'http://127.0.0.1');
    const blobMatch = parsed.pathname.match(/\/v1\/blob\/([^/]+)/);
    if (blobMatch?.[1]) {
      let path = `/agent/v1/blob/${blobMatch[1]}`;
      if (download && filename) {
        path += `/${encodeURIComponent(safeDownloadName(filename))}`;
      }
      return download ? `${path}?download=1` : path;
    }
    const uploadMatch = parsed.pathname.match(/\/v1\/uploads\/([^/]+)/);
    if (uploadMatch?.[1]) {
      let path = `/agent/v1/uploads/${uploadMatch[1]}`;
      if (download && filename) {
        path += `/${encodeURIComponent(safeDownloadName(filename))}`;
      }
      return download ? `${path}?download=1` : path;
    }
  } catch {
    // ignore
  }
  if (!url.startsWith('/agent/')) return '';
  return download ? `${url}${url.includes('?') ? '&' : '?'}download=1` : url;
}

export function downloadFileByUrl(url: string, fileName: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.rel = 'noopener';
  link.style.display = 'none';
  document.body.append(link);
  link.click();
  window.setTimeout(() => link.remove(), 4000);
}

type SavePicker = (options: { suggestedName?: string }) => Promise<{
  createWritable: () => Promise<{
    close: () => Promise<void>;
    write: (data: Blob) => Promise<void>;
  }>;
}>;

export interface DownloadBlobOptions {
  /** browser 会进入浏览器下载记录；save-picker 保留现有的系统“另存为”行为。 */
  mode?: 'browser' | 'save-picker';
}

export type DownloadBlobResult = 'cancelled' | 'saved' | 'started';

/** 其它页面的程序化下载。对话附件不要走这条。 */
export async function downloadBlob(
  blob: Blob,
  fileName: string,
  options: DownloadBlobOptions = {},
): Promise<DownloadBlobResult> {
  const name = safeDownloadName(fileName);
  const picker = (window as unknown as { showSaveFilePicker?: SavePicker })
    .showSaveFilePicker;
  if (options.mode !== 'browser' && typeof picker === 'function') {
    try {
      const handle = await picker({ suggestedName: name });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return 'saved';
    } catch (error) {
      if ((error as { name?: string }).name === 'AbortError') {
        return 'cancelled';
      }
    }
  }
  const file = new File([blob], name, {
    type: blob.type || 'application/octet-stream',
  });
  const url = URL.createObjectURL(file);
  downloadFileByUrl(url, name);
  window.setTimeout(() => URL.revokeObjectURL(url), 4000);
  return 'started';
}
