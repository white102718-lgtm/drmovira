/** @jsxImportSource react */
import { createRoot } from 'react-dom/client';
import CanvasReadonlyPage from './features/canvas/CanvasReadonlyPage';
import type { CanvasDraft } from './features/canvas/types';
import './adgen-canvas.css';

/** 独立挂载展示画布，不初始化编辑器运行时、任务或保存监听。 */
export function mountReadonlyCanvas(
  container: HTMLElement,
  draft: CanvasDraft,
  title: string,
  onBack: () => void,
  canvasId: string,
  getAccessToken: () => string | null | undefined,
) {
  container.classList.add('adgen-canvas-scope');
  const root = createRoot(container);
  root.render(
    <CanvasReadonlyPage
      draft={draft}
      canvasId={canvasId}
      getAccessToken={getAccessToken}
      title={title}
      onBack={onBack}
    />,
  );
  return () => {
    root.unmount();
    container.classList.remove('adgen-canvas-scope');
  };
}
