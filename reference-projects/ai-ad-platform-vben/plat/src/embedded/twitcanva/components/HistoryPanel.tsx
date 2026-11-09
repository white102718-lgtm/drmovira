/** @jsxImportSource react */
/**
 * HistoryPanel.tsx
 *
 * Panel for browsing generated image and video history.
 * Assets are grouped by date and displayed in a grid.
 * Clicking an asset applies it to the selected node.
 *
 * Uses infinite scroll with pagination for performance.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Loader2,
  Trash2,
  Maximize2,
  Image as ImageIcon,
  Video,
} from 'lucide-react';
import { apiFetch } from '../runtime';

// ============================================================================
// CONSTANTS
// ============================================================================

const PAGE_SIZE = 18; // 6 columns × 3 rows

// ============================================================================
// TYPES
// ============================================================================

interface AssetMetadata {
  id: string;
  filename: string;
  prompt: string;
  createdAt: string;
  type: string;
  url: string;
  model?: string;
}

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectAsset: (
    type: 'images' | 'videos',
    url: string,
    prompt: string,
    model?: string,
  ) => void;
  panelY?: number;
  canvasTheme?: 'dark' | 'light';
}

// ============================================================================
// COMPONENT
// ============================================================================

export const HistoryPanel: React.FC<HistoryPanelProps> = ({
  isOpen,
  onClose,
  onSelectAsset,
  panelY = 200,
  canvasTheme = 'dark',
}) => {
  // --- State ---
  const [activeTab, setActiveTab] = useState<'images' | 'videos'>('images');
  const [assets, setAssets] = useState<AssetMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [imageTotalCount, setImageTotalCount] = useState<number>(0);
  const [videoTotalCount, setVideoTotalCount] = useState<number>(0);

  // --- Refs ---
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const loadMoreTriggerRef = useRef<HTMLDivElement>(null);

  // Theme helper
  const isDark = canvasTheme === 'dark';

  // --- Fetch initial page and counts when panel opens ---
  useEffect(() => {
    if (isOpen) {
      // Reset pagination state for current tab
      setAssets([]);
      setOffset(0);
      setHasMore(true);
      fetchAssets(0, true);

      // Fetch total counts for both tabs
      fetchCounts();
    }
  }, [isOpen, activeTab]);

  /**
   * Fetch total counts for both images and videos
   */
  const fetchCounts = async () => {
    try {
      // Fetch counts in parallel
      const [imgRes, vidRes] = await Promise.all([
        apiFetch('/api/assets/images?limit=1'),
        apiFetch('/api/assets/videos?limit=1'),
      ]);

      if (imgRes.ok) {
        const imgData = await imgRes.json();
        setImageTotalCount(imgData.total);
      }

      if (vidRes.ok) {
        const vidData = await vidRes.json();
        setVideoTotalCount(vidData.total);
      }
    } catch (error) {
      console.error('Failed to fetch asset counts:', error);
    }
  };

  // --- Intersection Observer for infinite scroll ---
  useEffect(() => {
    if (!loadMoreTriggerRef.current || loading) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const target = entries[0];
        if (target.isIntersecting && hasMore && !loadingMore && !loading) {
          loadMoreAssets();
        }
      },
      { threshold: 0.1, root: scrollContainerRef.current },
    );

    observer.observe(loadMoreTriggerRef.current);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, loading, offset]);

  /**
   * Fetch assets with pagination
   * @param pageOffset - Offset to fetch from
   * @param isInitial - Whether this is the initial fetch (shows full loader)
   */
  const fetchAssets = async (
    pageOffset: number,
    isInitial: boolean = false,
  ) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }

    try {
      const response = await apiFetch(
        `/api/assets/${activeTab}?limit=${PAGE_SIZE}&offset=${pageOffset}`,
      );
      if (response.ok) {
        const data = await response.json();

        if (isInitial) {
          setAssets(data.assets);
        } else {
          setAssets((prev) => [...prev, ...data.assets]);
        }

        setHasMore(data.hasMore);
        setOffset(pageOffset + data.assets.length);

        // Update total counts
        if (activeTab === 'images') {
          setImageTotalCount(data.total);
        } else {
          setVideoTotalCount(data.total);
        }
      }
    } catch (error) {
      console.error('Failed to fetch assets:', error);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  /**
   * Load more assets when scrolling
   */
  const loadMoreAssets = useCallback(() => {
    if (!loadingMore && hasMore) {
      fetchAssets(offset, false);
    }
  }, [offset, loadingMore, hasMore, activeTab]);

  const handleDelete = async (id: string) => {
    try {
      const response = await apiFetch(`/api/assets/${activeTab}/${id}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        setAssets((prev) => prev.filter((a) => a.id !== id));
        // Update counts
        if (activeTab === 'images') {
          setImageTotalCount((prev) => prev - 1);
        } else {
          setVideoTotalCount((prev) => prev - 1);
        }
      }
    } catch (error) {
      console.error('Failed to delete asset:', error);
    }
    setDeleteConfirm(null);
  };

  const handleSelectAsset = (asset: AssetMetadata) => {
    // Construct full URL for the asset
    const fullUrl = `/canvasApi${asset.url}`;
    onSelectAsset(activeTab, fullUrl, asset.prompt || '', asset.model);
  };

  // Group assets by date
  const groupedAssets = assets.reduce(
    (groups, asset) => {
      const date = new Date(asset.createdAt).toLocaleDateString('en-CA'); // YYYY-MM-DD format
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(asset);
      return groups;
    },
    {} as Record<string, AssetMetadata[]>,
  );

  const sortedDates = Object.keys(groupedAssets).sort(
    (a, b) => new Date(b).getTime() - new Date(a).getTime(),
  );

  if (!isOpen) return null;

  return (
    <>
      {/* Main Panel */}
      <div
        className={`absolute left-20 z-40 flex max-h-[500px] w-[700px] flex-col overflow-hidden rounded-2xl border shadow-2xl backdrop-blur-xl transition-colors duration-300 ${isDark ? 'border-neutral-800 bg-[#0a0a0a]/95' : 'border-neutral-200 bg-white/95'}`}
        style={{ top: panelY }}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between border-b px-5 py-4 ${isDark ? 'border-neutral-800' : 'border-neutral-200'}`}
        >
          <div className="flex items-center gap-6">
            <button
              className={`flex items-center gap-2 pb-1 text-sm font-medium transition-colors ${
                activeTab === 'images'
                  ? isDark
                    ? 'border-b-2 border-white text-white'
                    : 'border-b-2 border-neutral-900 text-neutral-900'
                  : isDark
                    ? 'text-neutral-500 hover:text-white'
                    : 'text-neutral-400 hover:text-neutral-900'
              }`}
              onClick={() => setActiveTab('images')}
            >
              <ImageIcon size={16} />
              Image History ({imageTotalCount})
            </button>
            <button
              className={`flex items-center gap-2 pb-1 text-sm font-medium transition-colors ${
                activeTab === 'videos'
                  ? isDark
                    ? 'border-b-2 border-white text-white'
                    : 'border-b-2 border-neutral-900 text-neutral-900'
                  : isDark
                    ? 'text-neutral-500 hover:text-white'
                    : 'text-neutral-400 hover:text-neutral-900'
              }`}
              onClick={() => setActiveTab('videos')}
            >
              <Video size={16} />
              Video History ({videoTotalCount})
            </button>
          </div>
          <button
            onClick={onClose}
            className={`transition-colors ${isDark ? 'text-neutral-500 hover:text-white' : 'text-neutral-400 hover:text-neutral-900'}`}
          >
            <Maximize2 size={18} />
          </button>
        </div>

        {/* Content */}
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto p-4"
          style={{
            scrollbarWidth: 'thin',
            scrollbarColor: isDark ? '#525252 #171717' : '#d4d4d4 #fafafa',
          }}
        >
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="animate-spin text-neutral-500" size={24} />
            </div>
          ) : assets.length === 0 ? (
            <div
              className={`flex h-40 flex-col items-center justify-center ${isDark ? 'text-neutral-500' : 'text-neutral-400'}`}
            >
              <div
                className={`mb-3 flex h-16 w-16 items-center justify-center rounded-full ${isDark ? 'bg-neutral-800' : 'bg-neutral-100'}`}
              >
                {activeTab === 'images' ? (
                  <ImageIcon size={24} />
                ) : (
                  <Video size={24} />
                )}
              </div>
              <p>No {activeTab} found</p>
              <p className="mt-1 text-xs">
                Generated {activeTab} will appear here
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {sortedDates.map((date) => (
                <div key={date}>
                  <h3
                    className={`mb-3 text-sm ${isDark ? 'text-neutral-400' : 'text-neutral-500'}`}
                  >
                    {date}
                  </h3>
                  <div className="grid grid-cols-3 gap-3">
                    {groupedAssets[date].map((asset) => (
                      <div
                        key={asset.id}
                        onClick={() => handleSelectAsset(asset)}
                        className={`group relative aspect-square cursor-pointer overflow-hidden rounded-xl transition-all ${isDark ? 'bg-neutral-900' : 'bg-neutral-100'}`}
                      >
                        {activeTab === 'images' ? (
                          <img
                            src={`/canvasApi${asset.url}`}
                            alt={asset.prompt || 'Generated image'}
                            className="h-full w-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <video
                            src={`/canvasApi${asset.url}`}
                            className="h-full w-full object-cover"
                            muted
                            preload="metadata"
                            onMouseEnter={(e) => e.currentTarget.play()}
                            onMouseLeave={(e) => {
                              e.currentTarget.pause();
                              e.currentTarget.currentTime = 0;
                            }}
                          />
                        )}
                        {/* Delete button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(asset.id);
                          }}
                          className="absolute right-2 top-2 rounded-lg bg-black/50 p-1.5 opacity-0 transition-all hover:bg-red-500 group-hover:opacity-100"
                        >
                          <Trash2 size={14} className="text-white" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {/* Load more trigger for infinite scroll */}
              {hasMore && (
                <div
                  ref={loadMoreTriggerRef}
                  className="flex items-center justify-center py-4"
                >
                  {loadingMore && (
                    <Loader2
                      className="animate-spin text-neutral-500"
                      size={20}
                    />
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="app-modal-mask absolute inset-0 z-50 flex items-center justify-center">
          <div
            className={`w-[340px] rounded-2xl border p-6 shadow-2xl ${isDark ? 'border-neutral-700 bg-[#1a1a1a]' : 'border-neutral-200 bg-white'}`}
          >
            <h3
              className={`mb-2 text-lg font-semibold ${isDark ? 'text-white' : 'text-neutral-900'}`}
            >
              Delete Asset
            </h3>
            <p
              className={`mb-6 text-sm ${isDark ? 'text-neutral-400' : 'text-neutral-600'}`}
            >
              Are you sure you want to delete this{' '}
              {activeTab === 'images' ? 'image' : 'video'}? This action cannot
              be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className={`rounded-lg px-4 py-2 text-sm transition-colors ${isDark ? 'bg-neutral-800 text-white hover:bg-neutral-700' : 'bg-neutral-100 text-neutral-900 hover:bg-neutral-200'}`}
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white transition-colors hover:bg-red-500"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
