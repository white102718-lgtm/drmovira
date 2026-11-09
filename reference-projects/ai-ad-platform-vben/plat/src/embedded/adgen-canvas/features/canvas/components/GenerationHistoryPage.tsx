import type { HistoryAssetReference } from '../../../utils/historyAssetUtils';

import {
  AlertCircle,
  CalendarDays,
  Download,
  Film,
  ImageOff,
  Music2,
  RefreshCw,
  X,
} from 'lucide-react';
/** @jsxImportSource react */
import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { authService } from '../../../services/authService';
import { API_BASE_URL as API_ROOT } from '../../../services/runtimeConfig';
import {
  getHistoryAssetDownloadUrl,
  getHistoryAssetFilename,
  getHistoryAssetObjectName,
  getHistoryAssetPreviewUrl,
  isTransientHistoryAsset,
} from '../../../utils/historyAssetUtils';

type HistoryAsset = HistoryAssetReference;

interface GenerationRecord {
  _id?: string;
  created_at: string;
  error_message?: null | string;
  generated_assets: HistoryAsset[];
  generation_type: string;
  id?: string;
  input_assets: HistoryAsset[];
  metadata?: Record<string, any>;
  prompt: string;
  record_id?: string;
  session_id: string;
  status: string;
  updated_at?: string;
}

export interface HistoryRestoreData {
  generatedAssets: HistoryAsset[];
  generationType: string;
  inputAssets: HistoryAsset[];
  metadata: Record<string, any>;
  prompt: string;
  sessionId: string;
}

export interface HistoryUsePayload {
  asset: HistoryAsset;
  generationType: string;
  inputAssets: HistoryAsset[];
  metadata: Record<string, any>;
  prompt: string;
  sessionId: string;
}

export interface GenerationHistoryData {
  records: GenerationRecord[];
  count: number;
  media_counts: Record<HistoryMediaKind, number>;
  currency?: { cny_to_usd_rate: number };
}

interface GenerationHistoryPageProps {
  readOnly?: boolean;
  loadHistory?: (params: URLSearchParams) => Promise<GenerationHistoryData>;
  getAccessToken?: () => string | null | undefined;
  onBack: () => void;
  onRestore?: (data: HistoryRestoreData) => void;
  onUseAsset?: (payload: HistoryUsePayload) => void;
}

const API_BASE_URL = `${API_ROOT}/history`;
const HISTORY_PAGE_SIZE = 50;

const getAuthHeaders = (): Record<string, string> => {
  const token = authService.getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const isVideoAsset = (asset?: HistoryAsset | null) =>
  (asset?.type || '').toUpperCase() === 'VIDEO';
const isAudioAsset = (asset?: HistoryAsset | null) =>
  (asset?.type || '').toUpperCase() === 'AUDIO';

const getAssetMediaKind = (
  asset: HistoryAsset,
): 'audio' | 'image' | 'video' => {
  if (isVideoAsset(asset)) return 'video';
  if (isAudioAsset(asset)) return 'audio';
  return 'image';
};

const formatHistoryDate = (value?: string) => {
  if (!value) return '未知日期';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知日期';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

type HistoryMediaKind = 'audio' | 'image' | 'video';

const HISTORY_MEDIA_TABS: Array<{ key: HistoryMediaKind; label: string }> = [
  { key: 'image', label: '图片历史' },
  { key: 'video', label: '视频历史' },
  { key: 'audio', label: '音频历史' },
];

interface HistoryGridItem {
  asset: HistoryAsset;
  dateKey: string;
  index: number;
  key: string;
  kind: HistoryMediaKind;
  record: GenerationRecord;
}

const HistoryGridTile: React.FC<{
  item: HistoryGridItem;
  onDownload: (asset: HistoryAsset, index: number, prefix: string) => void;
  onPreview: (asset: HistoryAsset) => void;
  onUse: (item: HistoryGridItem) => void;
}> = ({ item, onDownload, onPreview, onUse }) => {
  const [loadFailed, setLoadFailed] = useState(false);
  const previewUrl = getHistoryAssetPreviewUrl(item.asset);
  const filename = getHistoryAssetFilename(item.asset, 'generated', item.index);
  const objectName = getHistoryAssetObjectName(item.asset);
  const canPreview = Boolean(previewUrl) && !loadFailed;
  const canDownload =
    Boolean(getHistoryAssetDownloadUrl(item.asset)) &&
    (!isTransientHistoryAsset(item.asset) || Boolean(objectName));

  useEffect(() => setLoadFailed(false), [previewUrl]);

  let mediaPreview: React.ReactNode;
  if (!canPreview) {
    mediaPreview = (
      <span className="flex h-full items-center justify-center text-slate-400">
        <ImageOff size={22} />
      </span>
    );
  } else if (item.kind === 'video') {
    mediaPreview = (
      <>
        <video
          className="h-full w-full object-cover"
          muted
          onError={() => setLoadFailed(true)}
          playsInline
          preload="metadata"
          src={previewUrl}
        />
        <span className="pointer-events-none absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-md bg-slate-950/55 text-white">
          <Film size={13} />
        </span>
      </>
    );
  } else if (item.kind === 'audio') {
    mediaPreview = (
      <span className="flex h-full flex-col items-center justify-center gap-1 bg-slate-100 text-[11px] font-medium text-slate-500">
        <Music2 size={22} />
        音频
      </span>
    );
  } else {
    mediaPreview = (
      <img
        alt={filename}
        className="h-full w-full object-cover"
        loading="lazy"
        onError={() => setLoadFailed(true)}
        src={previewUrl}
      />
    );
  }

  return (
    <article className="group relative aspect-square overflow-hidden rounded-lg bg-slate-100">
      {mediaPreview}
      <div className="canvas-history-tile-mask absolute inset-0 flex items-center justify-center gap-0.5 px-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          className="h-7 shrink-0 cursor-pointer rounded-md px-1.5 text-[11px] font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white disabled:cursor-not-allowed disabled:text-white/40"
          disabled={!canPreview}
          onClick={() => onPreview(item.asset)}
          type="button"
        >
          查看
        </button>
        <button
          className="h-7 shrink-0 cursor-pointer rounded-md px-1.5 text-[11px] font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white"
          onClick={() => onUse(item)}
          type="button"
        >
          使用
        </button>
        <button
          className="h-7 shrink-0 cursor-pointer rounded-md px-1.5 text-[11px] font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white disabled:cursor-not-allowed disabled:text-white/40"
          disabled={!canDownload}
          onClick={() => onDownload(item.asset, item.index, 'generated')}
          type="button"
        >
          下载
        </button>
      </div>
    </article>
  );
};

const formatHistoryDateTime = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
};

const historyModelAndConfig = (record: GenerationRecord) => {
  const metadata = record.metadata || {};
  const model = String(metadata.model_name || metadata.model || '未记录模型');
  const fields: Array<[string, unknown]> = [
    ['模式', metadata.image_generation_mode || metadata.video_generation_mode],
    ['规格', metadata.image_size || metadata.resolution],
    ['比例', metadata.aspect_ratio],
    ['时长', metadata.duration ? `${metadata.duration}s` : undefined],
    ['数量', metadata.batch_count ? `${metadata.batch_count}张` : undefined],
    ['音色', metadata.voice_name],
    ['语速', metadata.speech_rate],
  ];
  const configurations = fields
    .filter(
      ([, value]) => value !== undefined && value !== null && value !== '',
    )
    .map(([, value]) => String(value));
  return { configurations, model };
};

const historyAmount = (record: GenerationRecord, cnyToUsdRate: number) => {
  const metadata = record.metadata || {};
  const usage =
    metadata.usage && typeof metadata.usage === 'object' ? metadata.usage : {};
  const amount = usage.amount_usd ?? metadata.estimated_cost_usd;
  return amount === undefined || amount === null
    ? '—'
    : `¥ ${(
        Number(amount) / (cnyToUsdRate > 0 ? cnyToUsdRate : 0.14)
      ).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

const HistoryListRow: React.FC<{
  onDownload: (asset: HistoryAsset, index: number, prefix: string) => void;
  onPreview: (asset: HistoryAsset) => void;
  onUse: (record: GenerationRecord, asset: HistoryAsset) => void;
  record: GenerationRecord;
  cnyToUsdRate: number;
  readOnly?: boolean;
}> = ({ cnyToUsdRate, onDownload, onPreview, onUse, record, readOnly }) => {
  const [previewFailed, setPreviewFailed] = useState(false);
  const assets = Array.isArray(record.generated_assets)
    ? record.generated_assets
    : [];
  const primaryAsset = assets[0];
  const { configurations, model } = historyModelAndConfig(record);
  const previewUrl = primaryAsset
    ? getHistoryAssetPreviewUrl(primaryAsset)
    : '';
  const isVideo = isVideoAsset(primaryAsset);
  const isAudio = isAudioAsset(primaryAsset);
  const hasPreview = Boolean(previewUrl) && !previewFailed;
  const canDownload = Boolean(
    primaryAsset &&
      getHistoryAssetDownloadUrl(primaryAsset) &&
      (!isTransientHistoryAsset(primaryAsset) ||
        getHistoryAssetObjectName(primaryAsset)),
  );

  useEffect(() => setPreviewFailed(false), [previewUrl]);

  return (
    <article className="grid grid-cols-[128px_minmax(150px,1.2fr)_minmax(220px,1.8fr)_minmax(120px,.8fr)_minmax(150px,1fr)] items-center gap-3 border-b border-slate-100 px-3 py-3 last:border-b-0">
      <div className="group relative h-24 w-32 overflow-hidden rounded-lg bg-slate-100 focus-within:ring-2 focus-within:ring-violet-400">
        {!hasPreview ? (
          <span className="flex h-full items-center justify-center text-slate-400">
            <ImageOff size={22} />
          </span>
        ) : isVideo ? (
          <>
            <video
              className="h-full w-full object-cover"
              muted
              onError={() => setPreviewFailed(true)}
              playsInline
              preload="metadata"
              src={previewUrl}
            />
            <span className="pointer-events-none absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded bg-slate-950/55 text-white">
              <Film size={11} />
            </span>
          </>
        ) : isAudio ? (
          <span className="flex h-full flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-slate-500">
            <Music2 size={17} />
            音频
          </span>
        ) : (
          <img
            alt={getHistoryAssetFilename(primaryAsset!, 'generated', 0)}
            className="h-full w-full object-cover"
            loading="lazy"
            onError={() => setPreviewFailed(true)}
            src={previewUrl}
          />
        )}
        {primaryAsset && (
          <div className="absolute inset-0 flex items-center justify-center gap-1 bg-slate-950/45 px-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100">
            <button
              className="rounded px-1.5 py-1 text-xs font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-1 focus:ring-white disabled:cursor-not-allowed disabled:text-white/40"
              disabled={!hasPreview}
              onClick={() => onPreview(primaryAsset)}
              type="button"
            >
              查看
            </button>
            {!readOnly && (
              <button
                className="rounded px-1.5 py-1 text-xs font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-1 focus:ring-white"
                onClick={() => onUse(record, primaryAsset)}
                type="button"
              >
                使用
              </button>
            )}
            <button
              className="rounded px-1.5 py-1 text-xs font-medium text-white hover:bg-white/20 focus:outline-none focus:ring-1 focus:ring-white disabled:cursor-not-allowed disabled:text-white/40"
              disabled={!canDownload}
              onClick={() => onDownload(primaryAsset, 0, 'generated')}
              type="button"
            >
              下载
            </button>
          </div>
        )}
      </div>
      <div className="min-w-0">
        <div className="break-words text-sm font-semibold leading-5 text-slate-800">
          {model}
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap gap-1">
        {configurations.length ? (
          configurations.map((configuration) => (
            <span
              className="max-w-full truncate rounded-full bg-slate-100 px-2 py-0.5 text-xs leading-5 text-slate-600"
              key={configuration}
              title={configuration}
            >
              {configuration}
            </span>
          ))
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </div>
      <div className="text-sm tabular-nums text-slate-700">
        {historyAmount(record, cnyToUsdRate)}
      </div>
      <div className="text-xs tabular-nums text-slate-500">
        {formatHistoryDateTime(record.created_at)}
      </div>
    </article>
  );
};

const GenerationHistoryPage: React.FC<GenerationHistoryPageProps> = ({
  onBack,
  onRestore,
  onUseAsset,
  readOnly = false,
  loadHistory,
  getAccessToken,
}) => {
  const [records, setRecords] = useState<GenerationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<null | string>(null);
  const [mediaTab, setMediaTab] = useState<HistoryMediaKind>('image');
  const [historyCounts, setHistoryCounts] = useState<
    Record<HistoryMediaKind, number>
  >({
    image: 0,
    video: 0,
    audio: 0,
  });
  const [cnyToUsdRate, setCnyToUsdRate] = useState(0.14);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [previewAsset, setPreviewAsset] = useState<HistoryAsset | null>(null);
  const [notice, setNotice] = useState<null | {
    message: string;
    tone: 'error' | 'warning';
  }>(null);

  const fetchHistory = useCallback(
    async (page = 0) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          limit: String(HISTORY_PAGE_SIZE),
          media_kind: mediaTab,
          offset: String(page * HISTORY_PAGE_SIZE),
          status: 'success',
        });
        let data: {
          data: GenerationHistoryData;
          success?: boolean;
          message?: string;
        };
        if (loadHistory) {
          data = { data: await loadHistory(params) };
        } else {
          const response = await fetch(`${API_BASE_URL}/list?${params}`, {
            headers: getAuthHeaders(),
          });
          data = await response.json();
          if (!response.ok || !data.success)
            throw new Error(data.message || `HTTP ${response.status}`);
        }
        setRecords(Array.isArray(data.data?.records) ? data.data.records : []);
        setTotalCount(Number(data.data?.count || 0));
        setHistoryCounts({
          image: Number(data.data?.media_counts?.image || 0),
          video: Number(data.data?.media_counts?.video || 0),
          audio: Number(data.data?.media_counts?.audio || 0),
        });
        const returnedRate = Number(data.data?.currency?.cny_to_usd_rate);
        if (Number.isFinite(returnedRate) && returnedRate > 0) {
          setCnyToUsdRate(returnedRate);
        }
        setCurrentPage(page);
      } catch (fetchError) {
        setError(
          `获取历史记录失败：${fetchError instanceof Error ? fetchError.message : '未知错误'}`,
        );
      } finally {
        setLoading(false);
      }
    },
    [mediaTab, loadHistory],
  );

  useEffect(() => {
    void fetchHistory(0);
  }, [fetchHistory]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (previewAsset) {
        setPreviewAsset(null);
        return;
      }
      onBack();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onBack, previewAsset]);

  const downloadAsset = async (
    asset: HistoryAsset,
    index: number,
    prefix: string,
  ) => {
    const objectName = getHistoryAssetObjectName(asset);
    const url = getHistoryAssetDownloadUrl(asset);
    const filename = getHistoryAssetFilename(asset, prefix, index);
    if (!url || (isTransientHistoryAsset(asset) && !objectName)) {
      setNotice({
        message: '该历史素材使用的是已失效临时链接，无法下载',
        tone: 'warning',
      });
      return;
    }
    try {
      const token = getAccessToken?.();
      const response = await fetch(url, {
        headers: getAccessToken
          ? token
            ? { Authorization: `Bearer ${token}` }
            : {}
          : getAuthHeaders(),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      if (blob.size === 0) throw new Error('下载内容为空');
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (downloadError) {
      setNotice({
        message: `下载失败：${downloadError instanceof Error ? downloadError.message : '文件不可用'}`,
        tone: 'error',
      });
    }
  };

  const restoreRecord = (record: GenerationRecord, assets?: HistoryAsset[]) => {
    if (record.status !== 'success') return;
    onRestore?.({
      prompt: record.prompt || '',
      inputAssets: Array.isArray(record.input_assets)
        ? record.input_assets
        : [],
      generatedAssets: assets
        ? assets
        : Array.isArray(record.generated_assets)
          ? record.generated_assets
          : [],
      generationType: record.generation_type,
      sessionId: record.session_id,
      metadata: record.metadata || {},
    });
  };

  const gridItems = useMemo(() => {
    const items: HistoryGridItem[] = [];
    for (const record of records) {
      const assets = Array.isArray(record.generated_assets)
        ? record.generated_assets
        : [];
      assets.forEach((asset, index) => {
        if (!asset?.url && !asset?.object_name) return;
        items.push({
          asset,
          dateKey: formatHistoryDate(record.created_at),
          index,
          key: `${record.record_id || record._id || record.id || record.session_id}-${index}`,
          kind: getAssetMediaKind(asset),
          record,
        });
      });
    }
    return items;
  }, [records]);

  const mediaCounts = useMemo(
    () => ({
      image: gridItems.filter((item) => item.kind === 'image').length,
      video: gridItems.filter((item) => item.kind === 'video').length,
      audio: gridItems.filter((item) => item.kind === 'audio').length,
    }),
    [gridItems],
  );

  const groupedItems = useMemo(() => {
    const groups: { date: string; items: HistoryGridItem[] }[] = [];
    const indexByDate = new Map<string, number>();
    for (const item of gridItems) {
      if (item.kind !== mediaTab) continue;
      const existingIndex = indexByDate.get(item.dateKey);
      if (existingIndex === undefined) {
        indexByDate.set(item.dateKey, groups.length);
        groups.push({ date: item.dateKey, items: [item] });
        continue;
      }
      groups[existingIndex].items.push(item);
    }
    return groups;
  }, [gridItems, mediaTab]);

  useEffect(() => {
    setMediaTab((current) => {
      if (gridItems.some((item) => item.kind === current)) return current;
      return gridItems[0]?.kind || current;
    });
  }, [gridItems]);

  const handleUseItem = (item: HistoryGridItem) => {
    if (readOnly) return;
    const payload: HistoryUsePayload = {
      asset: item.asset,
      generationType: item.record.generation_type,
      inputAssets: Array.isArray(item.record.input_assets)
        ? item.record.input_assets
        : [],
      metadata: item.record.metadata || {},
      prompt: item.record.prompt || '',
      sessionId: item.record.session_id,
    };
    if (onUseAsset) {
      onUseAsset(payload);
      return;
    }
    restoreRecord(item.record, [item.asset]);
  };

  const handleUseHistoryRecord = (
    record: GenerationRecord,
    asset: HistoryAsset,
  ) => {
    if (readOnly) return;
    const payload: HistoryUsePayload = {
      asset,
      generationType: record.generation_type,
      inputAssets: Array.isArray(record.input_assets)
        ? record.input_assets
        : [],
      metadata: record.metadata || {},
      prompt: record.prompt || '',
      sessionId: record.session_id,
    };
    if (onUseAsset) {
      onUseAsset(payload);
      return;
    }
    restoreRecord(record, [asset]);
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / HISTORY_PAGE_SIZE));
  const previewUrl = previewAsset
    ? getHistoryAssetPreviewUrl(previewAsset)
    : '';
  const previewFilename = previewAsset
    ? getHistoryAssetFilename(previewAsset, 'preview', 0)
    : '';

  let historyContent: React.ReactNode;
  if (loading && records.length === 0) {
    historyContent = (
      <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
        <RefreshCw className="mb-3 animate-spin text-slate-400" size={28} />
        <p className="m-0 text-sm text-slate-500">历史记录加载中...</p>
      </div>
    );
  } else if (records.length === 0) {
    historyContent = (
      <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
        <CalendarDays className="mb-3 text-slate-300" size={40} />
        <h2 className="m-0 text-sm font-semibold text-slate-600">
          暂无
          {HISTORY_MEDIA_TABS.find((item) => item.key === mediaTab)?.label ||
            '生成'}
        </h2>
        <p className="mb-0 mt-1 text-xs text-slate-400">
          完成一次画布生成后，记录会显示在这里
        </p>
      </div>
    );
  } else {
    historyContent = (
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="grid grid-cols-[128px_minmax(150px,1.2fr)_minmax(220px,1.8fr)_minmax(120px,.8fr)_minmax(150px,1fr)] gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2 text-center text-xs font-medium text-slate-500">
          <span>生成结果</span>
          <span>模型</span>
          <span>配置</span>
          <span>金额（¥）</span>
          <span>生成时间</span>
        </div>
        {records.map((record) => (
          <HistoryListRow
            readOnly={readOnly}
            cnyToUsdRate={cnyToUsdRate}
            key={
              record.record_id || record._id || record.id || record.session_id
            }
            onDownload={downloadAsset}
            onPreview={setPreviewAsset}
            onUse={handleUseHistoryRecord}
            record={record}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      aria-label="生成历史"
      aria-modal="true"
      className="canvas-history-overlay absolute inset-0 z-[120] flex items-center justify-center bg-transparent p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !previewAsset) onBack();
      }}
      role="dialog"
    >
      <div className="flex h-[720px] w-[960px] max-w-[calc(100%-32px)] shrink-0 flex-col overflow-hidden rounded-[24px] border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800">生成历史</div>
            <div className="mt-0.5 text-xs text-slate-500">
              生成结果、模型、配置、金额与生成时间
            </div>
          </div>
          <button
            aria-label="关闭历史记录"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-400"
            onClick={onBack}
            type="button"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex items-center gap-1 border-b border-slate-100 px-5">
          {HISTORY_MEDIA_TABS.map((tab) => {
            const active = tab.key === mediaTab;
            return (
              <button
                aria-pressed={active}
                className={`relative px-3 py-3 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-violet-400 ${
                  active
                    ? 'text-violet-700'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
                disabled={loading}
                key={tab.key}
                onClick={() => {
                  if (active) return;
                  setCurrentPage(0);
                  setMediaTab(tab.key);
                }}
                type="button"
              >
                {tab.label}（{historyCounts[tab.key]}）
                {active && (
                  <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-violet-600" />
                )}
              </button>
            );
          })}
        </div>

        {(error || notice) && (
          <div className="space-y-2 px-5 pt-3">
            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                <AlertCircle className="mt-0.5 shrink-0" size={16} />
                {error}
              </div>
            )}
            {notice && (
              <div
                className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                  notice.tone === 'warning'
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-red-200 bg-red-50 text-red-700'
                }`}
              >
                <AlertCircle className="mt-0.5 shrink-0" size={16} />
                <span className="flex-1">{notice.message}</span>
                <button
                  aria-label="关闭提示"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md hover:bg-black/5"
                  onClick={() => setNotice(null)}
                  type="button"
                >
                  <X size={14} />
                </button>
              </div>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {historyContent}
        </div>

        {totalCount > HISTORY_PAGE_SIZE && (
          <div className="flex items-center justify-center gap-2 border-t border-slate-100 px-5 py-3">
            <button
              className="h-8 rounded-lg px-3 text-sm font-medium text-slate-600 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:opacity-40"
              disabled={currentPage === 0 || loading}
              onClick={() => void fetchHistory(currentPage - 1)}
              type="button"
            >
              上一页
            </button>
            <span className="text-sm text-slate-500">
              {currentPage + 1} / {totalPages}
            </span>
            <button
              className="h-8 rounded-lg px-3 text-sm font-medium text-slate-600 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:opacity-40"
              disabled={currentPage >= totalPages - 1 || loading}
              onClick={() => void fetchHistory(currentPage + 1)}
              type="button"
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {previewAsset && previewUrl && (
        <div
          aria-label={`预览 ${previewFilename}`}
          aria-modal="true"
          className="absolute inset-0 z-[140] flex items-center justify-center bg-slate-950/80 p-4"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setPreviewAsset(null)
          }
          role="dialog"
        >
          <div className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-white/15 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between gap-4 border-b border-white/10 px-5 py-3">
              <div className="min-w-0">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
                  素材预览
                </div>
                <div className="truncate text-sm font-bold text-white">
                  {previewFilename}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  className="flex h-10 items-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-bold text-white hover:bg-white/20"
                  onClick={() => void downloadAsset(previewAsset, 0, 'preview')}
                  type="button"
                >
                  <Download size={16} />
                  下载
                </button>
                <button
                  aria-label="关闭预览"
                  className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-white hover:bg-white/20"
                  onClick={() => setPreviewAsset(null)}
                  type="button"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-5">
              {(() => {
                if (isVideoAsset(previewAsset)) {
                  return (
                    <video
                      autoPlay
                      className="max-h-[78vh] max-w-full rounded-2xl bg-black object-contain"
                      controls
                      playsInline
                      src={previewUrl}
                    />
                  );
                }

                if (isAudioAsset(previewAsset)) {
                  return (
                    <div className="w-full max-w-2xl rounded-2xl bg-white/10 p-6">
                      <audio
                        autoPlay
                        className="w-full"
                        controls
                        src={previewUrl}
                      />
                    </div>
                  );
                }

                return (
                  <img
                    alt={previewFilename}
                    className="max-h-[78vh] max-w-full rounded-2xl bg-white object-contain"
                    src={previewUrl}
                  />
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GenerationHistoryPage;
