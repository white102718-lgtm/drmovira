export interface AdgenCanvasRuntimeOptions {
  canvasId?: string;
  getAccessToken?: () => null | string;
  initialTitle?: string;
  mediaConfig?: any;
  onBack?: () => void;
}

let runtimeOptions: AdgenCanvasRuntimeOptions = {};

export function configureAdgenCanvasRuntime(
  options: AdgenCanvasRuntimeOptions,
) {
  runtimeOptions = options;
}

export function getAdgenCanvasAccessToken(): null | string {
  return runtimeOptions.getAccessToken?.() || null;
}

export function getAdgenCanvasRuntime(): AdgenCanvasRuntimeOptions {
  return runtimeOptions;
}
