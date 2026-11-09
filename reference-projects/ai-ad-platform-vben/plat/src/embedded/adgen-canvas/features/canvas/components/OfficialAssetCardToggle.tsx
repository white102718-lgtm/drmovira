/** @jsxImportSource react */
import React from 'react';
import { Loader2 } from 'lucide-react';
import { OFFICIAL_ASSET_LIBRARY_ENABLED } from '../../../officialAssetLibrary';
import type { CanvasNodeData } from '../types';

interface OfficialAssetCardToggleProps {
  disabled?: boolean;
  node: CanvasNodeData;
  onToggle: (enabled: boolean) => void;
}

export const OfficialAssetCardToggle: React.FC<OfficialAssetCardToggleProps> = ({
  node,
  disabled,
  onToggle,
}) => {
  // AK/SK 未就绪时先不渲染入口，组件实现保留。
  if (!OFFICIAL_ASSET_LIBRARY_ENABLED) return null;

  const enabled = Boolean(node.officialAssetEnabled && node.officialAssetStatus === 'active');
  const uploading = node.officialAssetStatus === 'uploading';
  const failed = node.officialAssetStatus === 'failed';
  const label = uploading ? '入库中' : failed ? '入库失败' : enabled ? '已入库' : '官方素材库';

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label="将当前素材登记到 BytePlus 官方素材库"
      title={node.officialAssetError || '仅勾选需要过真人审核的参考图或视频'}
      disabled={disabled || uploading}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onToggle(!enabled);
      }}
      className={`absolute bottom-2 left-2 z-40 flex h-7 max-w-[calc(100%-1rem)] items-center gap-1 rounded-full px-2 text-[10px] font-semibold shadow-md backdrop-blur-md transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white ${
        enabled
          ? 'bg-emerald-600 text-white hover:bg-emerald-700'
          : failed
            ? 'bg-red-600 text-white hover:bg-red-700'
            : 'bg-slate-950/70 text-white hover:bg-slate-900'
      } disabled:cursor-wait disabled:opacity-70`}
    >
      {uploading ? <Loader2 size={11} className="animate-spin" /> : null}
      <span className="truncate">{label}</span>
    </button>
  );
};
