/** @jsxImportSource react */
import { createRoot, type Root } from 'react-dom/client';

import App from './App';
import { configureRuntime, type TwitCanvaRuntimeOptions } from './runtime';
import './twitcanva.css';

export type MountTwitCanvaOptions = Omit<TwitCanvaRuntimeOptions, 'container'>;

const mountedRoots = new WeakMap<HTMLElement, Root>();

export function mountTwitCanva(
  container: HTMLElement,
  options: MountTwitCanvaOptions = {},
) {
  mountedRoots.get(container)?.unmount();
  configureRuntime({ ...options, container });
  container.classList.add('twitcanva-scope');

  const root = createRoot(container);
  mountedRoots.set(container, root);
  root.render(
    <App
      canvasId={options.canvasId}
      initialTitle={options.initialTitle}
      initialTheme={options.theme}
    />,
  );

  return () => {
    if (mountedRoots.get(container) === root) {
      root.unmount();
      mountedRoots.delete(container);
      container.classList.remove('twitcanva-scope');
    }
  };
}
