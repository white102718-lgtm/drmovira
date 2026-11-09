import { useDirectorStore } from '../store/directorStore';
import type { DirectorProject } from '../schema/directorProject';
import type {
  HostDirectorContext,
  HostDirectorContextItem,
  HostDirectorContextKind,
} from '../schema/hostContext';

interface HostPanoramaPayload {
  edgeId?: unknown;
  sourceNodeId?: unknown;
  imageUrl?: unknown;
  fileName?: unknown;
}

interface HostSessionPayload {
  instanceId?: unknown;
  project?: unknown;
  projectId?: unknown;
  revision?: unknown;
  sessionId?: unknown;
  theme?: unknown;
  context?: unknown;
  hostOrigin?: unknown;
}

interface HostContextUpdatePayload {
  projectId?: unknown;
  sessionId?: unknown;
  context?: unknown;
}

export interface HostCaptureItemPayload {
  dataUrl?: unknown;
  fileName?: unknown;
}

export interface HostCaptureBatchPayload {
  captures?: HostCaptureItemPayload[];
}

interface HostConnectedPanorama {
  edgeId: string;
  sourceNodeId: string;
}

interface ActiveHostSession {
  projectId: string;
  revision: number;
  sessionId: string;
}

let initialized = false;
let hostConnectedPanorama: HostConnectedPanorama | null = null;
let removeUnsubscribe: (() => void) | null = null;
let removeProjectUnsubscribe: (() => void) | null = null;
let suppressNextPanoramaRemovalNotice = false;
let suppressProjectChangeNotice = false;
let activeHostSession: ActiveHostSession | null = null;
let latestProjectDigest = '';
let projectChangeTimer: number | null = null;
let hasPendingProjectChange = false;
let trustedHostOrigin: string | null = null;

function normalizeString(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeOrigin(value: unknown) {
  if (typeof value !== 'string') return null;
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function getReferrerOrigin() {
  return normalizeOrigin(document.referrer);
}

function getHostOrigin() {
  return trustedHostOrigin ?? getReferrerOrigin() ?? window.location.origin;
}

function normalizeTheme(value: unknown): 'dark' | 'light' | null {
  return value === 'light' || value === 'dark' ? value : null;
}

function normalizeRevision(value: unknown) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : 0;
}

function isDirectorProject(value: unknown): value is DirectorProject {
  if (!value || typeof value !== 'object') return false;

  const project = value as Partial<DirectorProject>;
  return (
    project.version === 1 &&
    Array.isArray(project.assets) &&
    Array.isArray(project.objects) &&
    Array.isArray(project.cameras) &&
    Boolean(project.scene) &&
    typeof project.scene?.backgroundColor === 'string'
  );
}

const HOST_CONTEXT_KINDS: HostDirectorContextKind[] = [
  'brief',
  'storyboard',
  'character',
  'scene',
  'reference-image',
  'camera-direction',
];

function normalizeHostContextItem(value: unknown): HostDirectorContextItem | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as Record<string, unknown>;
  const id = normalizeString(item.id);
  const title = normalizeString(item.title);
  const kind = normalizeString(item.kind) as HostDirectorContextKind;
  if (!id || !title || !HOST_CONTEXT_KINDS.includes(kind)) return null;

  const fields = Array.isArray(item.fields)
    ? item.fields.flatMap((field) => {
        if (!field || typeof field !== 'object') return [];
        const candidate = field as Record<string, unknown>;
        const label = normalizeString(candidate.label);
        const value = normalizeString(candidate.value);
        return label && value ? [{ label, value }] : [];
      })
    : undefined;
  return {
    id,
    kind,
    title,
    description: normalizeString(item.description) || undefined,
    imageUrl: normalizeString(item.imageUrl) || undefined,
    fields: fields?.length ? fields : undefined,
  };
}

function normalizeHostContext(value: unknown): HostDirectorContext | null {
  if (!value || typeof value !== 'object') return null;
  const context = value as Record<string, unknown>;
  if (context.version !== 1) return null;
  const categories = [
    'briefs',
    'storyboards',
    'characters',
    'scenes',
    'referenceImages',
    'cameraDirections',
  ] as const;
  if (
    !Array.isArray(context.sourceNodeIds) ||
    categories.some((category) => !Array.isArray(context[category]))
  ) {
    return null;
  }

  const normalizeItems = (category: (typeof categories)[number]) =>
    (context[category] as unknown[])
      .map(normalizeHostContextItem)
      .filter((item): item is HostDirectorContextItem => Boolean(item));
  return {
    version: 1,
    generatedAt: normalizeString(context.generatedAt) || new Date().toISOString(),
    sourceNodeIds: (context.sourceNodeIds as unknown[])
      .map(normalizeString)
      .filter(Boolean),
    briefs: normalizeItems('briefs'),
    storyboards: normalizeItems('storyboards'),
    characters: normalizeItems('characters'),
    scenes: normalizeItems('scenes'),
    referenceImages: normalizeItems('referenceImages'),
    cameraDirections: normalizeItems('cameraDirections'),
  };
}

function cloneProject(project: DirectorProject) {
  return JSON.parse(JSON.stringify(project)) as DirectorProject;
}

function getProjectDigest(project: DirectorProject) {
  return JSON.stringify(project);
}

function applyDirectorDeskTheme(theme: 'dark' | 'light') {
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

function getInitialHostTheme() {
  try {
    return normalizeTheme(
      new URLSearchParams(window.location.search).get('theme'),
    );
  } catch {
    return null;
  }
}

function notifyPanoramaRemoved() {
  if (!hostConnectedPanorama) {
    return;
  }

  window.parent?.postMessage(
    {
      type: 'storyai:director-desk-panorama-removed',
      payload: hostConnectedPanorama,
    },
    getHostOrigin(),
  );
  hostConnectedPanorama = null;
}

function subscribeToPanoramaRemoval() {
  if (removeUnsubscribe) {
    return;
  }

  let previousPanoramaAssetId =
    useDirectorStore.getState().project.panoramaAssetId;
  removeUnsubscribe = useDirectorStore.subscribe((state) => {
    const nextPanoramaAssetId = state.project.panoramaAssetId;

    if (previousPanoramaAssetId && !nextPanoramaAssetId) {
      if (suppressNextPanoramaRemovalNotice) {
        suppressNextPanoramaRemovalNotice = false;
        hostConnectedPanorama = null;
      } else {
        notifyPanoramaRemoved();
      }
    }

    previousPanoramaAssetId = nextPanoramaAssetId;
  });
}

function postProjectSnapshot(
  type:
    | 'storyai:director-desk-project-changed'
    | 'storyai:director-desk-session-ready',
) {
  if (!activeHostSession) return;

  const project = useDirectorStore.getState().project;
  window.parent?.postMessage(
    {
      type,
      payload: {
        project: cloneProject(project),
        projectId: activeHostSession.projectId,
        revision: activeHostSession.revision,
        sessionId: activeHostSession.sessionId,
      },
    },
    getHostOrigin(),
  );
}

function scheduleProjectChangeNotice() {
  if (!activeHostSession || suppressProjectChangeNotice) return;

  hasPendingProjectChange = true;

  if (projectChangeTimer !== null) {
    window.clearTimeout(projectChangeTimer);
  }

  projectChangeTimer = window.setTimeout(() => {
    projectChangeTimer = null;
    if (!activeHostSession || suppressProjectChangeNotice) {
      hasPendingProjectChange = false;
      return;
    }

    activeHostSession.revision += 1;
    postProjectSnapshot('storyai:director-desk-project-changed');
    hasPendingProjectChange = false;
  }, 250);
}

export function flushDirectorDeskProjectToHost() {
  if (
    !activeHostSession ||
    suppressProjectChangeNotice ||
    !hasPendingProjectChange
  )
    return;

  if (projectChangeTimer !== null) {
    window.clearTimeout(projectChangeTimer);
    projectChangeTimer = null;
  }

  activeHostSession.revision += 1;
  postProjectSnapshot('storyai:director-desk-project-changed');
  hasPendingProjectChange = false;
}

function subscribeToProjectChanges() {
  if (removeProjectUnsubscribe) return;

  latestProjectDigest = getProjectDigest(useDirectorStore.getState().project);
  removeProjectUnsubscribe = useDirectorStore.subscribe((state) => {
    const nextDigest = getProjectDigest(state.project);
    if (nextDigest === latestProjectDigest) return;

    latestProjectDigest = nextDigest;
    scheduleProjectChangeNotice();
  });
}

function importHostPanorama(payload: HostPanoramaPayload) {
  const imageUrl = normalizeString(payload.imageUrl);
  if (!imageUrl) {
    return;
  }

  const fileName = normalizeString(payload.fileName) || '画布全景图.png';
  const edgeId = normalizeString(payload.edgeId);
  const sourceNodeId = normalizeString(payload.sourceNodeId);

  hostConnectedPanorama =
    edgeId && sourceNodeId ? { edgeId, sourceNodeId } : null;
  useDirectorStore.getState().addImportedAsset({
    kind: 'panorama',
    name: fileName,
    fileName,
    url: imageUrl,
    projectionMode: 'backdrop',
  });
}

function openHostSession(payload: HostSessionPayload, messageOrigin: string) {
  const instanceId = normalizeString(payload.instanceId);
  const projectId = normalizeString(payload.projectId) || instanceId;
  const sessionId = normalizeString(payload.sessionId);
  const payloadHostOrigin = normalizeOrigin(payload.hostOrigin);
  if (payloadHostOrigin && payloadHostOrigin !== messageOrigin) {
    return;
  }
  trustedHostOrigin = payloadHostOrigin ?? messageOrigin;
  const theme = normalizeTheme(payload.theme);
  if (theme) {
    applyDirectorDeskTheme(theme);
  }
  suppressProjectChangeNotice = true;
  suppressNextPanoramaRemovalNotice = Boolean(
    useDirectorStore.getState().project.panoramaAssetId,
  );
  if (isDirectorProject(payload.project)) {
    useDirectorStore.getState().openScopedScene(instanceId || null);
    useDirectorStore.getState().replaceProject(cloneProject(payload.project));
    useDirectorStore.getState().saveLatestSnapshot();
  } else {
    useDirectorStore.getState().openScopedScene(instanceId || null);
  }
  useDirectorStore.getState().setHostContext(normalizeHostContext(payload.context));
  suppressNextPanoramaRemovalNotice = false;
  activeHostSession =
    projectId && sessionId
      ? {
          projectId,
          revision: normalizeRevision(payload.revision),
          sessionId,
        }
      : null;
  latestProjectDigest = getProjectDigest(useDirectorStore.getState().project);
  hasPendingProjectChange = false;
  suppressProjectChangeNotice = false;
  hostConnectedPanorama = null;
  postProjectSnapshot('storyai:director-desk-session-ready');
}

function updateHostContext(payload: HostContextUpdatePayload) {
  if (
    !activeHostSession ||
    normalizeString(payload.projectId) !== activeHostSession.projectId ||
    normalizeString(payload.sessionId) !== activeHostSession.sessionId
  ) {
    return;
  }

  useDirectorStore.getState().setHostContext(normalizeHostContext(payload.context));
}

export function postDirectorDeskCapturesToHost(
  captures: Array<{
    dataUrl: string;
    fileName?: string;
  }>,
) {
  const normalizedCaptures = captures
    .map((capture, index) => {
      const dataUrl = normalizeString(capture.dataUrl);
      if (!dataUrl) {
        return null;
      }

      return {
        dataUrl,
        fileName:
          normalizeString(capture.fileName) ||
          `director-desk-capture-${index + 1}.png`,
      };
    })
    .filter((capture): capture is { dataUrl: string; fileName: string } =>
      Boolean(capture),
    );

  if (normalizedCaptures.length === 0) {
    return;
  }

  window.parent?.postMessage(
    {
      type: 'storyai:director-desk-captures-sent',
      payload: {
        captures: normalizedCaptures,
      },
    },
    getHostOrigin(),
  );
}

function handleHostMessage(event: MessageEvent) {
  if (event.data?.type === 'storyai:director-desk-session') {
    const payload = (event.data.payload || {}) as HostSessionPayload;
    const declaredHostOrigin = normalizeOrigin(payload.hostOrigin);
    const referrerOrigin = getReferrerOrigin();
    if (
      (declaredHostOrigin && declaredHostOrigin !== event.origin) ||
      (referrerOrigin && referrerOrigin !== event.origin) ||
      (!declaredHostOrigin &&
        !referrerOrigin &&
        event.origin !== window.location.origin)
    ) {
      return;
    }
    openHostSession(
      payload,
      event.origin,
    );
    return;
  }

  if (event.origin !== getHostOrigin()) {
    return;
  }

  if (event.data?.type === 'storyai:director-desk-panorama') {
    importHostPanorama((event.data.payload || {}) as HostPanoramaPayload);
    return;
  }

  if (event.data?.type === 'storyai:director-desk-context') {
    updateHostContext((event.data.payload || {}) as HostContextUpdatePayload);
  }
}

export function initDirectorDeskHostBridge() {
  if (initialized) {
    return;
  }

  initialized = true;
  applyDirectorDeskTheme(getInitialHostTheme() ?? 'dark');
  window.addEventListener('message', handleHostMessage);
  subscribeToPanoramaRemoval();
  subscribeToProjectChanges();
}

export function clearDirectorDeskHostBridge() {
  if (!initialized) {
    return;
  }

  initialized = false;
  hostConnectedPanorama = null;
  activeHostSession = null;
  trustedHostOrigin = null;
  suppressNextPanoramaRemovalNotice = false;
  suppressProjectChangeNotice = false;
  latestProjectDigest = '';
  hasPendingProjectChange = false;
  if (projectChangeTimer !== null) {
    window.clearTimeout(projectChangeTimer);
    projectChangeTimer = null;
  }
  window.removeEventListener('message', handleHostMessage);
  removeUnsubscribe?.();
  removeUnsubscribe = null;
  removeProjectUnsubscribe?.();
  removeProjectUnsubscribe = null;
}
