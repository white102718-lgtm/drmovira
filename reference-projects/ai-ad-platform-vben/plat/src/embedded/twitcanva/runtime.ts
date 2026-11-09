export type CanvasSaveState = 'clean' | 'dirty' | 'saving' | 'saved' | 'failed';

export interface TwitCanvaRuntimeOptions {
  apiBase?: string;
  assetBase?: string;
  /** Same-origin URL where the 3D director desk is deployed. */
  directorDeskUrl?: string;
  canvasId?: string;
  container: HTMLElement;
  initialTitle?: string;
  projectId?: string;
  requirementId?: string;
  taskId?: string;
  theme?: 'dark' | 'light';
  getAuthHeaders?: () => HeadersInit | Promise<HeadersInit>;
  onBack?: () => void;
  onSaveStateChange?: (state: CanvasSaveState) => void;
}

let runtime: TwitCanvaRuntimeOptions | undefined;

export function configureRuntime(options: TwitCanvaRuntimeOptions) {
  runtime = options;
}

export function getRuntime() {
  if (!runtime) throw new Error('TwitCanva runtime has not been configured');
  return runtime;
}

export function getRuntimeContainer() {
  return getRuntime().container;
}

export function hasRemoteApi() {
  return Boolean(runtime?.apiBase);
}

export function getHostRect(): DOMRect {
  return (
    runtime?.container.getBoundingClientRect() ??
    new DOMRect(0, 0, window.innerWidth, window.innerHeight)
  );
}

function trimEnd(value: string) {
  return value.replace(/\/+$/, '');
}

export function apiUrl(path: string) {
  const base = trimEnd(runtime?.apiBase ?? '/canvasApi');
  const suffix = path.replace(/^\/api(?=\/|$)/, '');
  return `${base}${suffix.startsWith('/') ? suffix : `/${suffix}`}`;
}

export function assetUrl(input: string) {
  if (!input || /^(blob:|data:)/.test(input)) return input;
  if (/^https?:\/\//.test(input)) return input;

  const base = trimEnd(runtime?.assetBase ?? '/library');
  const suffix = input.replace(/^\/library(?=\/|$)/, '');
  return `${base}${suffix.startsWith('/') ? suffix : `/${suffix}`}`;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(await runtime?.getAuthHeaders?.());
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));

  return fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
    headers,
  });
}

export function workflowStorageKey(id: string) {
  return `adpulse:creative-canvas:workflow:${id}`;
}

export function notifySaveState(state: CanvasSaveState) {
  runtime?.onSaveStateChange?.(state);
}
