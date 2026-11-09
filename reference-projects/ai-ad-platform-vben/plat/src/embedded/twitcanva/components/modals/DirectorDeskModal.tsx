/** @jsxImportSource react */
/**
 * Same-origin host for the standalone 3D director desk.
 *
 * The currently attached director desk already speaks the legacy
 * `storyai:director-desk-*` protocol. This host validates both `origin` and
 * `source`, scopes each editor instance with the canvas node project id, and
 * turns capture messages into normal canvas image nodes through its callback.
 */

import React from 'react';
import { AlertCircle, Loader2, RefreshCw, X } from 'lucide-react';

import type { NodeData } from '../../types';
import type { DirectorDeskContext } from '../../directorDeskContext';

export interface DirectorDeskCapture {
  dataUrl: string;
  fileName: string;
}

export interface DirectorDeskProjectUpdate {
  project: Record<string, unknown>;
  revision: number;
}

interface DirectorDeskModalProps {
  canvasTheme: 'dark' | 'light';
  directorDeskUrl?: string;
  node: NodeData;
  context: DirectorDeskContext;
  panoramaReference?: {
    fileName: string;
    sourceNodeId: string;
    url: string;
  };
  onCapture: (captures: DirectorDeskCapture[]) => Promise<void>;
  onClose: () => void;
  onProjectChange: (update: DirectorDeskProjectUpdate) => void;
  onStateChange: (updates: Partial<NodeData>) => void;
}

function resolveDeskUrl(configuredUrl: string | undefined, sessionId: string) {
  const source = configuredUrl?.trim() || '/director-desk/';
  const url = new URL(source, window.location.href);
  // The host application is a SPA and may have cached a previous 404 fallback
  // for `/director-desk/`. A session-scoped query guarantees that each editor
  // opening requests the standalone entry instead of reusing that navigation.
  url.searchParams.set('embed', '1');
  url.searchParams.set('session', sessionId);
  return url;
}

function isCaptureBatch(value: unknown): value is { captures: unknown[] } {
  return (
    typeof value === 'object' &&
    value !== null &&
    Array.isArray((value as { captures?: unknown[] }).captures)
  );
}

function normalizeCaptures(value: unknown): DirectorDeskCapture[] {
  if (!isCaptureBatch(value)) return [];

  return value.captures.flatMap((item, index) => {
    if (!item || typeof item !== 'object') return [];
    const capture = item as { dataUrl?: unknown; fileName?: unknown };
    if (
      typeof capture.dataUrl !== 'string' ||
      !capture.dataUrl.startsWith('data:image/')
    ) {
      return [];
    }

    return [
      {
        dataUrl: capture.dataUrl,
        fileName:
          typeof capture.fileName === 'string' && capture.fileName.trim()
            ? capture.fileName.trim()
            : `director-desk-capture-${index + 1}.png`,
      },
    ];
  });
}

function normalizeProjectUpdate(
  value: unknown,
  expectedProjectId: string,
  expectedSessionId: string,
): DirectorDeskProjectUpdate | null {
  if (!value || typeof value !== 'object') return null;
  const payload = value as {
    project?: unknown;
    projectId?: unknown;
    revision?: unknown;
    sessionId?: unknown;
  };
  if (
    payload.projectId !== expectedProjectId ||
    payload.sessionId !== expectedSessionId ||
    !payload.project ||
    typeof payload.project !== 'object' ||
    Array.isArray(payload.project) ||
    typeof payload.revision !== 'number' ||
    !Number.isInteger(payload.revision) ||
    payload.revision < 0
  ) {
    return null;
  }

  return {
    project: payload.project as Record<string, unknown>,
    revision: payload.revision,
  };
}

export const DirectorDeskModal: React.FC<DirectorDeskModalProps> = ({
  canvasTheme,
  directorDeskUrl,
  node,
  context,
  panoramaReference,
  onCapture,
  onClose,
  onProjectChange,
  onStateChange,
}) => {
  const iframeRef = React.useRef<HTMLIFrameElement>(null);
  const [frameKey, setFrameKey] = React.useState(0);
  const [phase, setPhase] = React.useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = React.useState<string>();
  const sessionId = React.useMemo(() => crypto.randomUUID(), []);
  const panoramaFileName = panoramaReference?.fileName;
  const panoramaSourceNodeId = panoramaReference?.sourceNodeId;
  const panoramaUrl = panoramaReference?.url;
  const deskUrl = React.useMemo(
    () => resolveDeskUrl(directorDeskUrl, sessionId),
    [directorDeskUrl, sessionId],
  );

  const postToDesk = React.useCallback(
    (type: string, payload: Record<string, unknown>) => {
      iframeRef.current?.contentWindow?.postMessage(
        { type, payload },
        deskUrl.origin,
      );
    },
    [deskUrl.origin],
  );

  const initialiseDesk = React.useCallback(() => {
    const instanceId = node.directorProjectId || node.id;
    postToDesk('storyai:director-desk-session', {
      instanceId,
      project: node.directorProject,
      projectId: instanceId,
      revision: node.directorRevision || 0,
      sessionId,
      theme: canvasTheme,
      context,
      hostOrigin: window.location.origin,
    });
    if (panoramaFileName && panoramaSourceNodeId && panoramaUrl) {
      postToDesk('storyai:director-desk-panorama', {
        edgeId: `${panoramaSourceNodeId}:${node.id}`,
        fileName: panoramaFileName,
        imageUrl: panoramaUrl,
        sourceNodeId: panoramaSourceNodeId,
      });
    }
    setPhase('ready');
    onStateChange({
      directorDeskState: 'local-draft',
      directorLastOpenedAt: new Date().toISOString(),
      directorSessionId: sessionId,
      errorMessage: undefined,
    });
  }, [
    canvasTheme,
    context,
    node.directorProject,
    node.directorProjectId,
    node.directorRevision,
    node.id,
    onStateChange,
    panoramaFileName,
    panoramaSourceNodeId,
    panoramaUrl,
    postToDesk,
    sessionId,
  ]);

  React.useEffect(() => {
    const timeout = window.setTimeout(() => {
      setPhase((current) => {
        if (current !== 'loading') return current;
        const message =
          '等待导演台握手超时，请检查导演台部署地址和页面加载状态。';
        setError(message);
        onStateChange({ directorDeskState: 'error', errorMessage: message });
        return 'error';
      });
    }, 10_000);

    const handleMessage = (event: MessageEvent) => {
      if (
        event.origin !== deskUrl.origin ||
        event.source !== iframeRef.current?.contentWindow ||
        !event.data ||
        typeof event.data !== 'object'
      ) {
        return;
      }

      const message = event.data as { type?: unknown; payload?: unknown };
      if (message.type === 'storyai:director-desk-ready') {
        initialiseDesk();
        return;
      }

      if (message.type === 'storyai:director-desk-close') {
        onClose();
        return;
      }

      if (
        message.type === 'storyai:director-desk-session-ready' ||
        message.type === 'storyai:director-desk-project-changed'
      ) {
        const projectUpdate = normalizeProjectUpdate(
          message.payload,
          node.directorProjectId || node.id,
          sessionId,
        );
        if (projectUpdate) onProjectChange(projectUpdate);
        return;
      }

      if (message.type === 'storyai:director-desk-captures-sent') {
        const captures = normalizeCaptures(message.payload);
        if (captures.length === 0) {
          setError('导演台返回的截图格式无效。');
          return;
        }

        void onCapture(captures).catch((captureError: unknown) => {
          const captureMessage =
            captureError instanceof Error
              ? captureError.message
              : '截图上传失败，请重试。';
          setError(captureMessage);
        });
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.clearTimeout(timeout);
      window.removeEventListener('message', handleMessage);
    };
  }, [
    deskUrl.origin,
    initialiseDesk,
    node.directorProjectId,
    node.id,
    onCapture,
    onClose,
    onProjectChange,
    onStateChange,
    sessionId,
  ]);

  React.useEffect(() => {
    if (phase !== 'ready') return;
    postToDesk('storyai:director-desk-context', {
      context,
      projectId: node.directorProjectId || node.id,
      sessionId,
    });
  }, [context, node.directorProjectId, node.id, phase, postToDesk, sessionId]);

  const retry = () => {
    setError(undefined);
    setPhase('loading');
    setFrameKey((value) => value + 1);
  };

  const isDark = canvasTheme === 'dark';
  const isBlockingError = phase === 'error';

  return (
    <div className="absolute inset-0 z-[500] flex flex-col bg-black/80 backdrop-blur-sm">
      <header
        className={`flex h-14 shrink-0 items-center justify-between border-b px-4 ${
          isDark
            ? 'border-neutral-800 bg-[#111] text-white'
            : 'border-neutral-200 bg-white text-neutral-900'
        }`}
      >
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">
            3D 导演台 · {node.title || '未命名工程'}
          </div>
          <div
            className={`mt-0.5 text-xs ${isDark ? 'text-neutral-500' : 'text-neutral-500'}`}
          >
            {phase === 'ready'
              ? '本地工程草稿已隔离；截图会上传并回传画布。'
              : '正在建立安全会话…'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={retry}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs transition-colors ${
              isDark
                ? 'text-neutral-300 hover:bg-neutral-800'
                : 'text-neutral-600 hover:bg-neutral-100'
            }`}
            title="重新加载导演台"
          >
            <RefreshCw size={14} /> 重载
          </button>
          <button
            type="button"
            onClick={onClose}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs transition-colors ${
              isDark
                ? 'text-neutral-300 hover:bg-neutral-800'
                : 'text-neutral-600 hover:bg-neutral-100'
            }`}
          >
            <X size={14} /> 关闭
          </button>
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        <iframe
          key={frameKey}
          ref={iframeRef}
          src={deskUrl.href}
          title="3D 导演台"
          className="h-full w-full border-0 bg-black"
          sandbox="allow-downloads allow-same-origin allow-scripts"
          onLoad={() => {
            // A cross-origin iframe can omit document.referrer before it has
            // sent its first message. Seed the scoped session on load as well
            // as on `ready`; the child validates the declared host origin.
            initialiseDesk();
          }}
        />

        {phase === 'loading' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 text-white">
            <Loader2 className="animate-spin text-blue-400" size={30} />
            <p className="text-sm">正在加载 3D 导演台…</p>
          </div>
        )}

        {(error || isBlockingError) && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/75 p-6">
            <div
              className={`w-full max-w-xl rounded-xl border p-5 shadow-2xl ${isDark ? 'border-neutral-700 bg-neutral-900 text-white' : 'border-neutral-200 bg-white text-neutral-900'}`}
            >
              <div className="flex gap-3">
                <AlertCircle
                  className="mt-0.5 shrink-0 text-amber-400"
                  size={20}
                />
                <div>
                  <h2 className="text-sm font-semibold">导演台暂时不可用</h2>
                  <p
                    className={`mt-2 text-sm leading-6 ${isDark ? 'text-neutral-400' : 'text-neutral-600'}`}
                  >
                    {error || '导演台初始化失败。'}
                  </p>
                </div>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md px-3 py-2 text-sm hover:bg-neutral-800/10"
                >
                  关闭
                </button>
                <button
                  type="button"
                  onClick={retry}
                  className="rounded-md bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-500"
                >
                  重新加载
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
