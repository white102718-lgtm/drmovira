/** @jsxImportSource react */
import React, { useState, useEffect } from 'react';
import { X, Search, Filter, Trash2 } from 'lucide-react';
import { apiFetch, getHostRect } from '../runtime';

interface LibraryAsset {
  id: string;
  name: string;
  category: string;
  url: string;
  type: 'image' | 'video';
}

interface AssetLibraryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectAsset: (url: string, type: 'image' | 'video') => void;
  panelY?: number;
  variant?: 'panel' | 'modal';
  canvasTheme?: 'dark' | 'light';
}

const CATEGORIES = [
  'All',
  'Character',
  'Scene',
  'Item',
  'Style',
  'Sound Effect',
  'Others',
];

export const AssetLibraryPanel: React.FC<AssetLibraryPanelProps> = ({
  isOpen,
  onClose,
  onSelectAsset,
  panelY = 100,
  variant = 'panel',
  canvasTheme = 'dark',
}) => {
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchLibrary();
    }
  }, [isOpen]);

  const fetchLibrary = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/library');
      if (res.ok) {
        setAssets(await res.json());
      }
    } catch (error) {
      console.error('Failed to load library:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAsset = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent selection
    // Confirmation is now handled in the UI before this is called

    try {
      const res = await apiFetch(`/api/library/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setAssets((prev) => prev.filter((a) => a.id !== id));
      } else {
        console.error('Failed to delete asset');
      }
    } catch (error) {
      console.error('Delete error:', error);
    }
  };

  if (!isOpen) return null;

  // Theme helper
  const isDark = canvasTheme === 'dark';

  if (variant === 'modal') {
    return (
      <div className="app-modal-mask animate-in fade-in absolute inset-0 z-50 flex items-center justify-center duration-200">
        <div
          className={`flex h-[600px] w-[800px] flex-col overflow-hidden rounded-2xl border shadow-2xl transition-colors duration-300 ${isDark ? 'border-neutral-800 bg-[#0a0a0a]' : 'border-neutral-200 bg-white'}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div
            className={`flex items-center justify-between border-b p-4 ${isDark ? 'border-neutral-800' : 'border-neutral-200'}`}
          >
            <h2
              className={`pl-2 text-lg font-medium ${isDark ? 'text-white' : 'text-neutral-900'}`}
            >
              Asset Library
            </h2>
            <button
              onClick={onClose}
              className={`rounded-lg p-2 transition-colors ${isDark ? 'text-neutral-400 hover:bg-neutral-800 hover:text-white' : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900'}`}
            >
              <X size={20} />
            </button>
          </div>
          {/* Reuse internal content logic */}
          <AssetLibraryContent
            selectedCategory={selectedCategory}
            setSelectedCategory={setSelectedCategory}
            assets={assets}
            loading={loading}
            onSelectAsset={onSelectAsset}
            onDeleteAsset={handleDeleteAsset}
            variant={variant}
            canvasTheme={canvasTheme}
          />
        </div>
        {/* Click outside to close */}
        <div className="absolute inset-0 -z-10" onClick={onClose} />
      </div>
    );
  }

  return (
    <div
      className={`animate-in slide-in-from-left-4 absolute left-20 z-40 flex max-h-[500px] w-[700px] flex-col overflow-hidden rounded-2xl border shadow-2xl backdrop-blur-xl transition-colors duration-200 ${isDark ? 'border-neutral-800 bg-[#0a0a0a]/95' : 'border-neutral-200 bg-white/95'}`}
      style={{
        top: Math.min(getHostRect().height - 510, Math.max(20, panelY)),
      }}
    >
      <AssetLibraryContent
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
        assets={assets}
        loading={loading}
        onSelectAsset={onSelectAsset}
        onDeleteAsset={handleDeleteAsset}
        variant={variant}
        canvasTheme={canvasTheme}
      />
    </div>
  );
};

// Extracted Internal Component for reuse
const AssetLibraryContent = ({
  selectedCategory,
  setSelectedCategory,
  assets,
  loading,
  onSelectAsset,
  onDeleteAsset,
  variant,
  canvasTheme = 'dark',
}: any) => {
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const isDark = canvasTheme === 'dark';

  const filteredAssets = assets.filter(
    (asset: any) =>
      selectedCategory === 'All' || asset.category === selectedCategory,
  );

  const handleDeleteClick = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setDeleteConfirmId(id);
  };

  const handleConfirmDelete = (e: React.MouseEvent, id: string) => {
    onDeleteAsset(id, e);
    setDeleteConfirmId(null);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteConfirmId(null);
  };

  return (
    <>
      <div className="flex h-full flex-col gap-4 overflow-hidden p-4">
        {/* Filters */}
        <div className="scrollbar-hide flex shrink-0 gap-2 overflow-x-auto pb-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                selectedCategory === cat
                  ? isDark
                    ? 'border-white bg-neutral-100 text-black'
                    : 'border-neutral-900 bg-neutral-900 text-white'
                  : isDark
                    ? 'border-neutral-800 bg-neutral-900 text-neutral-400 hover:border-neutral-600'
                    : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Content */}
        <div
          className="grid flex-1 grid-cols-4 content-start gap-3 overflow-y-auto pb-4 pr-2"
          style={{
            scrollbarWidth: 'thin',
            scrollbarColor: isDark ? '#525252 #171717' : '#d4d4d4 #fafafa',
          }}
        >
          {loading ? (
            <div className="col-span-full py-10 text-center text-neutral-500">
              Loading...
            </div>
          ) : filteredAssets.length === 0 ? (
            <div className="col-span-full py-10 text-center text-sm text-neutral-500">
              No assets found in this category.
            </div>
          ) : (
            filteredAssets.map((asset: any) => (
              <div
                key={asset.id}
                className="group relative aspect-square cursor-pointer overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900 hover:border-neutral-600"
                onClick={() => onSelectAsset(asset.url, asset.type)}
              >
                <img
                  src={asset.url}
                  alt={asset.name}
                  className="h-full w-full object-cover"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    target.onerror = null; // Prevent infinite loop
                    target.src =
                      'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiMzMzMiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cmVjdCB4PSIzIiB5PSIzIiB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHJ4PSIyIiByeT0iMiI+PC9yZWN0PjxjaXJjbGUgY3g9IjguNSIgY3k9IjguNSIgcj0iMS41Ij48L2NpcmNsZT48cG9seWxpbmUgcG9pbnRzPSIyMSAxNSAxNiAxMCA1IDIxIj48LcG9lyxpbmU+PC9zdmc+';
                    target.classList.add('p-8', 'opacity-50');
                  }}
                />
                <div className="pointer-events-none absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/80 to-transparent p-2 opacity-0 transition-opacity group-hover:opacity-100">
                  <span className="truncate text-xs font-medium text-white">
                    {asset.name}
                  </span>
                </div>

                {/* Delete Button or Confirmation */}
                {deleteConfirmId === asset.id ? (
                  <div
                    className="animate-in fade-in absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 bg-black/80 duration-200"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="text-xs font-medium text-white">
                      Delete?
                    </span>
                    <div className="flex gap-2">
                      <button
                        className="rounded bg-red-500 px-2 py-1 text-xs text-white transition-colors hover:bg-red-600"
                        onClick={(e) => handleConfirmDelete(e, asset.id)}
                      >
                        Yes
                      </button>
                      <button
                        className="rounded bg-neutral-700 px-2 py-1 text-xs text-white transition-colors hover:bg-neutral-600"
                        onClick={handleCancelDelete}
                      >
                        No
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="absolute right-1 top-1 z-10 rounded-md bg-black/60 p-1.5 text-white opacity-0 transition-opacity hover:bg-red-500/80 group-hover:opacity-100"
                    onClick={(e) => handleDeleteClick(e, asset.id)}
                    title="Delete Asset"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
};
