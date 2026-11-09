/** @jsxImportSource react */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  CalendarDays,
  Eye,
  Focus,
  Minus,
  Play,
  Plus,
  X,
} from 'lucide-react';
import { getCanvasHistoryApi } from '#/api/canvas';
import GenerationHistoryPage, {
  type GenerationHistoryData,
} from './components/GenerationHistoryPage';
import type { CanvasDraft, CanvasNodeData } from './types';

/** 原画布的展示版：草稿只作为输入，视口和预览状态均不持久化。 */
export default function CanvasReadonlyPage({
  draft,
  canvasId,
  getAccessToken,
  title,
  onBack,
}: {
  draft: CanvasDraft;
  canvasId: string;
  getAccessToken: () => string | null | undefined;
  title: string;
  onBack: () => void;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const loadHistory = useCallback(
    (params: URLSearchParams) =>
      getCanvasHistoryApi<GenerationHistoryData>(canvasId, params),
    [canvasId],
  );
  const surface = useRef<HTMLDivElement>(null);
  const pan = useRef<{
    x: number;
    y: number;
    vx: number;
    vy: number;
    blank: boolean;
    moved: boolean;
  } | null>(null);
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 });
  const [preview, setPreview] = useState<{
    url: string;
    type: string;
    title: string;
  } | null>(null);
  const [selected, setSelected] = useState<CanvasNodeData | null>(null);
  const [ratios, setRatios] = useState<Record<string, number>>({});
  const cards = useMemo(
    () =>
      draft.nodes.map((node) => {
        const source =
          node.kind === 'output'
            ? draft.edges
                .filter((edge) => edge.target === node.id)
                .map((edge) =>
                  draft.nodes.find((item) => item.id === edge.source),
                )
                .find((item) => item?.resultUrl || item?.resultUrls?.length) ||
              node
            : node;
        const urls = [
          ...new Set(
            [...(source.resultUrls || []), source.resultUrl].filter(
              (url): url is string =>
                Boolean(
                  url &&
                    /^(https?:\/\/|\/(?!\/)|blob:|data:image\/)/i.test(url),
                ),
            ),
          ),
        ];
        const primaryUrl = urls[0];
        const type =
          source.resultAssetType ||
          source.assetType ||
          (source.kind === 'text'
            ? source.textGenerationMode || 'image'
            : source.kind);
        const videoGeneration = node.kind === 'video';
        const media = urls.length > 0 && ['image', 'video'].includes(type);
        const [configuredWidth = 0, configuredHeight = 0] = (
          node.aspectRatio || ''
        )
          .split(':')
          .map(Number);
        const ratio =
          ratios[node.id] ||
          node.mediaAspectRatio ||
          (configuredHeight > 0 ? configuredWidth / configuredHeight : 0);
        const scale = Math.min(4, Math.max(0.25, node.mediaDisplayScale || 1));
        const width =
          (media || videoGeneration) && ratio > 0
            ? (ratio >= 1 ? 286 : 286 * ratio) * scale
            : node.width || 286;
        const height =
          (media || videoGeneration) && ratio > 0
            ? (ratio >= 1 ? 286 / ratio : 286) * scale
            : node.height || (node.kind === 'text' ? 150 : 182);
        return {
          node,
          urls,
          primaryUrl,
          type,
          media,
          videoGeneration,
          width,
          height,
        };
      }),
    [draft, ratios],
  );
  const fit = () => {
    const rect = surface.current?.getBoundingClientRect();
    if (!rect || !cards.length) return;
    const left = Math.min(...cards.map(({ node }) => node.x));
    const top = Math.min(...cards.map(({ node }) => node.y)) - 36;
    const right = Math.max(...cards.map(({ node, width }) => node.x + width));
    const bottom = Math.max(
      ...cards.map(({ node, height }) => node.y + height),
    );
    const zoom = Math.min(
      1,
      Math.max(
        0.15,
        Math.min(
          (rect.width - 100) / (right - left),
          (rect.height - 160) / (bottom - top),
        ),
      ),
    );
    setViewport({
      x: (rect.width - (right - left) * zoom) / 2 - left * zoom,
      y: 80 + (rect.height - 160 - (bottom - top) * zoom) / 2 - top * zoom,
      zoom,
    });
  };
  useEffect(() => {
    fit();
  }, [draft, ratios]);
  useEffect(() => {
    const element = surface.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      if ((event.target as HTMLElement).closest('[data-view-controls]')) return;
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      const x = event.clientX - rect.left,
        y = event.clientY - rect.top;
      setViewport((old) => {
        const zoom = Math.min(
          3,
          Math.max(0.15, old.zoom * Math.exp(-event.deltaY * 0.0015)),
        );
        return {
          zoom,
          x: x - ((x - old.x) * zoom) / old.zoom,
          y: y - ((y - old.y) * zoom) / old.zoom,
        };
      });
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, []);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreview(null);
        setSelected(null);
      }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, []);
  const groups = [
    ...new Set(draft.nodes.map((node) => node.groupId).filter(Boolean)),
  ].map((id) => {
    const members = cards.filter((card) => card.node.groupId === id);
    const left = Math.min(...members.map((card) => card.node.x)) - 24;
    const top = Math.min(...members.map((card) => card.node.y)) - 56;
    return {
      id,
      left,
      top,
      width:
        Math.max(...members.map((card) => card.node.x + card.width)) -
        left +
        24,
      height:
        Math.max(...members.map((card) => card.node.y + card.height)) -
        top +
        24,
    };
  });
  const selectedVideo =
    selected?.kind === 'video'
      ? cards.find((card) => card.node.id === selected.id)
      : undefined;
  const panelWidth = Math.min(
    760,
    Math.max(
      320,
      ((surface.current?.clientWidth || 1000) - 40) / viewport.zoom,
    ),
  );
  const panelLeft = selectedVideo
    ? selectedVideo.node.x + selectedVideo.width / 2 - panelWidth / 2
    : 0;
  const references = selectedVideo
    ? draft.edges
        .filter((edge) => edge.target === selectedVideo.node.id)
        .map((edge) => cards.find((card) => card.node.id === edge.source))
        .filter((card) => Boolean(card))
    : [];
  const videoModeLabels: Record<string, string> = {
    text_to_video: '文生视频',
    reference_image: '首帧',
    reference_video: '视频参考',
    reference_assets: '全能参考',
    first_frame: '首帧',
    first_last_frame: '首尾帧',
  };
  /** 只选中并把参数面板移入可见区域，不修改节点或草稿。 */
  const selectNode = (node: CanvasNodeData) => {
    setSelected((old) => (old?.id === node.id ? null : node));
    if (node.kind !== 'video') return;
    const card = cards.find((item) => item.node.id === node.id);
    const rect = surface.current?.getBoundingClientRect();
    if (!card || !rect) return;
    const left = node.x + card.width / 2 - panelWidth / 2;
    const bottom = node.y + card.height + 290;
    setViewport((v) => ({
      ...v,
      x:
        v.x +
        Math.max(20 - (v.x + left * v.zoom), 0) -
        Math.max(v.x + (left + panelWidth) * v.zoom - rect.width + 20, 0),
      y: v.y - Math.max(v.y + bottom * v.zoom - rect.height + 20, 0),
    }));
  };
  const button =
    'flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50';
  return (
    <div
      className="canvas-theme-shell relative h-full min-h-0 overflow-hidden bg-[#eef3fb] text-slate-900"
      data-canvas-theme="light"
    >
      {historyOpen && (
        <GenerationHistoryPage
          readOnly
          loadHistory={loadHistory}
          getAccessToken={getAccessToken}
          onBack={() => setHistoryOpen(false)}
        />
      )}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex h-[72px] items-center justify-between px-5">
        <div className="pointer-events-auto flex min-w-0 items-center gap-3">
          <button className={button} onClick={onBack} aria-label="返回画布列表">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="m-0 text-base font-semibold">{title}</h1>
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Eye size={12} />
              只读查看
            </span>
          </div>
        </div>
        <div className="pointer-events-auto flex items-center gap-2">
          <button
            className={button}
            onClick={() => setHistoryOpen(true)}
            aria-label="生成历史"
            title="生成历史"
          >
            <CalendarDays size={18} />
          </button>
          <button className={button} onClick={fit} aria-label="适应画布">
            <Focus size={18} />
          </button>
          <button
            className={button}
            onClick={() =>
              setViewport((v) => ({ ...v, zoom: Math.max(0.15, v.zoom / 1.2) }))
            }
            aria-label="缩小"
          >
            <Minus size={18} />
          </button>
          <span className="w-12 text-center text-xs">
            {Math.round(viewport.zoom * 100)}%
          </span>
          <button
            className={button}
            onClick={() =>
              setViewport((v) => ({ ...v, zoom: Math.min(3, v.zoom * 1.2) }))
            }
            aria-label="放大"
          >
            <Plus size={18} />
          </button>
        </div>
      </header>
      <div
        ref={surface}
        className="relative h-full w-full cursor-grab touch-none overflow-hidden active:cursor-grabbing"
        style={{
          backgroundImage:
            'radial-gradient(circle, rgba(100,116,139,0.34) 1px, transparent 1px)',
          backgroundSize: `${24 * viewport.zoom}px ${24 * viewport.zoom}px`,
          backgroundPosition: `${viewport.x}px ${viewport.y}px`,
        }}
        onPointerDown={(event) => {
          if (
            event.button !== 0 ||
            (event.target as HTMLElement).closest('[data-view-controls]')
          )
            return;
          pan.current = {
            x: event.clientX,
            y: event.clientY,
            vx: viewport.x,
            vy: viewport.y,
            blank: !(event.target as HTMLElement).closest('[data-view-node]'),
            moved: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const p = pan.current;
          if (!p) return;
          if (Math.hypot(event.clientX - p.x, event.clientY - p.y) > 4)
            p.moved = true;
          if (p.moved)
            setViewport((v) => ({
              ...v,
              x: p.vx + event.clientX - p.x,
              y: p.vy + event.clientY - p.y,
            }));
        }}
        onPointerUp={(event) => {
          const p = pan.current;
          // 空白点击取消选择；拖动平移不关闭节点参数。
          if (
            p?.blank &&
            !p.moved &&
            Math.hypot(event.clientX - p.x, event.clientY - p.y) <= 4
          )
            setSelected(null);
          pan.current = null;
        }}
        onPointerCancel={() => {
          pan.current = null;
        }}
      >
        <div
          className="absolute left-0 top-0 origin-top-left"
          style={{
            transform: `translate(${viewport.x}px,${viewport.y}px) scale(${viewport.zoom})`,
          }}
        >
          {groups.map((group) => (
            <div
              key={group.id}
              className="pointer-events-none absolute rounded-2xl border border-slate-300/70 bg-white/20"
              style={{
                left: group.left,
                top: group.top,
                width: group.width,
                height: group.height,
              }}
            />
          ))}
          <svg
            className="pointer-events-none absolute overflow-visible"
            width="1"
            height="1"
          >
            {draft.edges.map((edge) => {
              const source = cards.find((c) => c.node.id === edge.source),
                target = cards.find((c) => c.node.id === edge.target);
              if (!source || !target) return null;
              const x1 = source.node.x + source.width,
                y1 = source.node.y + source.height / 2;
              const x2 = target.node.x,
                y2 = target.node.y + target.height / 2,
                offset = Math.max(90, Math.abs(x2 - x1) * 0.42);
              return (
                <path
                  key={edge.id}
                  d={`M ${x1} ${y1} C ${x1 + offset} ${y1}, ${x2 - offset} ${y2}, ${x2} ${y2}`}
                  stroke="var(--canvas-drop-target)"
                  strokeWidth="2"
                  fill="none"
                />
              );
            })}
          </svg>
          {cards.map(
            ({
              node,
              urls,
              primaryUrl,
              type,
              media,
              videoGeneration,
              width,
              height,
            }) => (
              <article
                key={node.id}
                data-view-node
                className={`group absolute ${media || videoGeneration ? 'rounded-md bg-slate-950 shadow-sm' : 'rounded-[22px] border border-white/90 bg-white/95 p-3 shadow-[0_18px_48px_rgba(15,23,42,0.14)]'}`}
                style={{ left: node.x, top: node.y, width, height }}
              >
                <button
                  data-view-controls
                  className="absolute -top-7 left-0 max-w-full truncate rounded bg-white/90 px-2 py-1 text-xs text-slate-700"
                  onClick={() => selectNode(node)}
                >
                  {node.title || node.assetName || node.kind}
                </button>
                <span className="absolute -left-2 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-white bg-slate-300" />
                <span className="absolute -right-2 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-white bg-slate-300" />
                {videoGeneration ? (
                  <>
                    <button
                      data-view-controls
                      className={`relative h-full w-full overflow-hidden rounded-md bg-[#222] ${selected?.id === node.id ? 'ring-2 ring-blue-500' : ''}`}
                      aria-label={`查看${node.title}的生成参数`}
                      aria-expanded={selected?.id === node.id}
                      onClick={() => selectNode(node)}
                    >
                      {primaryUrl && (
                        <video
                          src={primaryUrl}
                          muted
                          playsInline
                          preload="metadata"
                          className="h-full w-full object-contain"
                          onLoadedMetadata={(e) => {
                            const video = e.currentTarget;
                            if (video.videoHeight)
                              setRatios((old) =>
                                old[node.id]
                                  ? old
                                  : {
                                      ...old,
                                      [node.id]:
                                        video.videoWidth / video.videoHeight,
                                    },
                              );
                          }}
                        />
                      )}
                      <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-white/40">
                        <Play size={30} fill="currentColor" />
                      </span>
                      <span className="absolute bottom-3 left-3 text-xs text-white/60">
                        {urls.length
                          ? '点击查看生成参数'
                          : node.status === 'error'
                            ? '生成失败'
                            : '等待生成'}
                      </span>
                    </button>
                    {primaryUrl && (
                      <button
                        data-view-controls
                        className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs text-slate-700"
                        onClick={() =>
                          setPreview({
                            url: primaryUrl,
                            type: 'video',
                            title: node.title,
                          })
                        }
                      >
                        播放视频
                      </button>
                    )}
                  </>
                ) : media ? (
                  <button
                    data-view-controls
                    className="h-full w-full overflow-hidden rounded-md"
                    style={
                      node.hasTransparentBackground
                        ? {
                            backgroundColor: '#fff',
                            backgroundImage:
                              'conic-gradient(#e2e8f0 25%, transparent 0 50%, #e2e8f0 0 75%, transparent 0)',
                            backgroundSize: '16px 16px',
                          }
                        : undefined
                    }
                    onClick={() =>
                      setPreview({ url: primaryUrl!, type, title: node.title })
                    }
                    aria-label={`预览${node.title}`}
                  >
                    {type === 'image' ? (
                      <img
                        src={primaryUrl}
                        alt={node.title}
                        draggable={false}
                        className="h-full w-full object-contain"
                        onLoad={(e) => {
                          const img = e.currentTarget;
                          if (img.naturalHeight)
                            setRatios((old) =>
                              old[node.id]
                                ? old
                                : {
                                    ...old,
                                    [node.id]:
                                      img.naturalWidth / img.naturalHeight,
                                  },
                            );
                        }}
                      />
                    ) : (
                      <video
                        src={primaryUrl}
                        muted
                        playsInline
                        preload="metadata"
                        className="h-full w-full object-contain"
                        onLoadedMetadata={(e) => {
                          const video = e.currentTarget;
                          if (video.videoHeight)
                            setRatios((old) =>
                              old[node.id]
                                ? old
                                : {
                                    ...old,
                                    [node.id]:
                                      video.videoWidth / video.videoHeight,
                                  },
                            );
                        }}
                      />
                    )}
                    {urls.length > 1 && (
                      <span className="absolute bottom-2 right-2 rounded bg-white px-2 py-1 text-xs">
                        {urls.length} 个产出
                      </span>
                    )}
                  </button>
                ) : (
                  <div
                    className="flex h-full flex-col gap-2 text-sm"
                    data-view-controls
                  >
                    <div className="truncate font-medium">{node.title}</div>
                    {node.model && (
                      <div className="truncate text-xs text-slate-500">
                        {node.model}
                      </div>
                    )}
                    <div className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-50 p-2 text-xs text-slate-600">
                      {node.analysisResult || node.prompt || '暂无内容'}
                    </div>
                    {urls.map((url) =>
                      type === 'audio' || ['music', 'tts'].includes(type) ? (
                        <audio
                          key={url}
                          src={url}
                          controls
                          className="w-full"
                        />
                      ) : (
                        <a
                          key={url}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          查看产出
                        </a>
                      ),
                    )}
                  </div>
                )}
              </article>
            ),
          )}
          {selectedVideo && (
            <section
              data-view-controls
              className="absolute z-40 rounded-[22px] border border-white/90 bg-white/95 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.14)]"
              style={{
                left: panelLeft,
                top: selectedVideo.node.y + selectedVideo.height + 12,
                width: panelWidth,
              }}
              aria-label="只读视频生成参数"
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2 text-xs text-slate-600">
                  <span className="shrink-0 rounded-full border border-slate-200 px-3 py-1">
                    生成参数 · 只读
                  </span>
                  <span>参考 {references.length}</span>
                </div>
                <button
                  aria-label="关闭生成参数"
                  onClick={() => setSelected(null)}
                  className="rounded p-1 text-slate-500 hover:bg-slate-100"
                >
                  <X size={16} />
                </button>
              </div>
              {references.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {references.map(
                    (card, index) =>
                      card && (
                        <button
                          key={card.node.id}
                          className="flex max-w-full items-center gap-2 rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-600"
                          onClick={() => {
                            if (card.urls[0])
                              setPreview({
                                url: card.urls[0],
                                type: card.type,
                                title: card.node.title,
                              });
                          }}
                          disabled={!card.urls[0]}
                        >
                          {card.type === 'image' && card.urls[0] && (
                            <img
                              src={card.urls[0]}
                              alt=""
                              className="h-5 w-5 rounded object-cover"
                            />
                          )}
                          <span className="truncate">
                            @参考{index + 1} · {card.node.title}
                          </span>
                        </button>
                      ),
                  )}
                </div>
              )}
              <div className="mb-4 max-h-32 min-h-20 overflow-auto whitespace-pre-wrap break-words text-sm text-slate-700">
                {selectedVideo.node.prompt || '未填写提示词'}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <div className="max-w-full break-all rounded-xl border border-slate-200 px-3 py-2">
                  模型：{selectedVideo.node.model || '未记录'}
                </div>
                <div className="rounded-xl border border-slate-200 px-3 py-2">
                  模式：
                  {videoModeLabels[
                    selectedVideo.node.videoGenerationMode || ''
                  ] ||
                    selectedVideo.node.videoGenerationMode ||
                    '未记录'}
                </div>
                <div className="rounded-xl border border-slate-200 px-3 py-2">
                  比例 {selectedVideo.node.aspectRatio || '未记录'} · 分辨率{' '}
                  {selectedVideo.node.resolution || '未记录'} · 时长{' '}
                  {selectedVideo.node.duration === undefined
                    ? '未记录'
                    : `${selectedVideo.node.duration} 秒`}{' '}
                  · 数量 {selectedVideo.node.count ?? '未记录'}
                </div>
              </div>
              {selectedVideo.urls.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedVideo.urls.map((url, index) => (
                    <button
                      key={url}
                      className="rounded-full border border-slate-200 px-3 py-1 text-xs"
                      onClick={() =>
                        setPreview({
                          url,
                          type: 'video',
                          title: selectedVideo.node.title,
                        })
                      }
                    >
                      播放产出 {index + 1}
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
      {!cards.length && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">
          此画布暂无节点
        </div>
      )}
      {selected && selected.kind !== 'video' && (
        <aside
          data-view-controls
          className="absolute bottom-5 right-5 top-20 z-40 w-80 overflow-auto rounded-2xl border border-slate-200 bg-white p-4 shadow-lg"
        >
          <button
            className="float-right"
            onClick={() => setSelected(null)}
            aria-label="关闭节点详情"
          >
            <X size={18} />
          </button>
          <h2 className="text-sm font-semibold">{selected.title}</h2>
          <p className="text-xs text-slate-500">{selected.model}</p>
          <p className="whitespace-pre-wrap break-words text-sm">
            {selected.prompt}
          </p>
          <p className="whitespace-pre-wrap break-words text-sm">
            {selected.analysisResult}
          </p>
          {cards
            .find((c) => c.node.id === selected.id)
            ?.urls.map((url, index) => (
              <button
                key={url}
                className="mb-2 block text-sm text-violet-600"
                onClick={() =>
                  setPreview({
                    url,
                    type: cards.find((c) => c.node.id === selected.id)!.type,
                    title: selected.title,
                  })
                }
              >
                查看产出 {index + 1}
              </button>
            ))}
        </aside>
      )}
      {preview && (
        <div
          className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 p-10"
          role="dialog"
          aria-modal="true"
          aria-label={preview.title}
          onClick={() => setPreview(null)}
        >
          <button
            className="absolute right-5 top-5 text-white"
            aria-label="关闭预览"
            onClick={() => setPreview(null)}
          >
            <X />
          </button>
          {preview.type === 'image' ? (
            <img
              src={preview.url}
              alt={preview.title}
              className="max-h-full max-w-full object-contain"
              onClick={(e) => e.stopPropagation()}
            />
          ) : preview.type === 'video' ? (
            <video
              src={preview.url}
              controls
              autoPlay
              className="max-h-full max-w-full"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <a
              href={preview.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-white"
              onClick={(e) => e.stopPropagation()}
            >
              打开产出文件
            </a>
          )}
        </div>
      )}
    </div>
  );
}
