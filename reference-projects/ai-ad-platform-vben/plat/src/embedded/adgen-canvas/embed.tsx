/** @jsxImportSource react */
import { createRoot, type Root } from 'react-dom/client';

import CanvasCreationPage from './features/canvas/CanvasCreationPage';
import {
  configureAdgenCanvasRuntime,
  type AdgenCanvasRuntimeOptions,
} from './runtime';
import './adgen-canvas.css';

export type MountAdgenCanvasOptions = AdgenCanvasRuntimeOptions;

export interface AdgenCanvasMountHandle {
  dispose: () => void;
  updateOptions: (options: Partial<MountAdgenCanvasOptions>) => void;
}

const mountedRoots = new WeakMap<HTMLElement, Root>();

export function mountAdgenCanvas(
  container: HTMLElement,
  options: MountAdgenCanvasOptions = {},
): AdgenCanvasMountHandle {
  mountedRoots.get(container)?.unmount();
  container.classList.add('adgen-canvas-scope');

  const root = createRoot(container);
  mountedRoots.set(container, root);
  let currentOptions = { ...options };
  let mediaConfigRevision = 0;
  let mediaConfigSignature = JSON.stringify(currentOptions.mediaConfig ?? null);

  const render = () => {
    configureAdgenCanvasRuntime(currentOptions);
    root.render(
      <CanvasCreationPage
        key={`${currentOptions.canvasId || 'adpulse-default'}:${mediaConfigRevision}`}
        canvasId={currentOptions.canvasId}
        initialTitle={currentOptions.initialTitle}
        mediaConfig={currentOptions.mediaConfig}
        onBack={currentOptions.onBack}
      />,
    );
  };

  render();

  return {
    dispose: () => {
      if (mountedRoots.get(container) === root) {
        root.unmount();
        mountedRoots.delete(container);
        container.classList.remove('adgen-canvas-scope');
      }
    },
    updateOptions: (nextOptions) => {
      if (mountedRoots.get(container) !== root) return;
      const nextResolvedOptions = { ...currentOptions, ...nextOptions };
      const nextMediaConfigSignature = JSON.stringify(nextResolvedOptions.mediaConfig ?? null);
      if (nextMediaConfigSignature !== mediaConfigSignature) {
        mediaConfigRevision += 1;
        mediaConfigSignature = nextMediaConfigSignature;
      }
      currentOptions = nextResolvedOptions;
      render();
    },
  };
}
