/** @jsxImportSource react */
/**
 * WorkflowPanel.tsx
 *
 * Panel for browsing and managing saved workflows.
 * Shows list of workflows with options to load, delete, or edit cover.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  Trash2,
  FileText,
  Loader2,
  Maximize2,
  Pencil,
  Check,
} from 'lucide-react';
import { apiFetch } from '../runtime';
import { LazyImage } from './LazyImage';

interface WorkflowSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  nodeCount: number;
  coverUrl?: string;
  description?: string; // For public workflows
}

interface AssetMetadata {
  id: string;
  url: string;
  prompt?: string;
  createdAt: string;
}

interface WorkflowPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadWorkflow: (workflowId: string) => void;
  currentWorkflowId?: string;
  panelY?: number;
  canvasTheme?: 'dark' | 'light';
}

export const WorkflowPanel: React.FC<WorkflowPanelProps> = ({
  isOpen,
  onClose,
  onLoadWorkflow,
  currentWorkflowId,
  panelY = 200,
  canvasTheme = 'dark',
}) => {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [publicWorkflows, setPublicWorkflows] = useState<WorkflowSummary[]>([]);
  const [activeTab, setActiveTab] = useState<'my' | 'public'>('my');
  const [loading, setLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Cover editing state
  const [editingCoverFor, setEditingCoverFor] = useState<string | null>(null);
  const [coverAssets, setCoverAssets] = useState<AssetMetadata[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);

  // Pagination state for cover image modal
  const COVERS_PER_PAGE = 9;
  const [visibleCoverCount, setVisibleCoverCount] = useState(COVERS_PER_PAGE);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Theme helper
  const isDark = canvasTheme === 'dark';

  // Fetch workflows on open
  useEffect(() => {
    if (isOpen) {
      fetchWorkflows();
      fetchPublicWorkflows();
    }
  }, [isOpen]);

  const fetchWorkflows = async () => {
    setLoading(true);
    try {
      const response = await apiFetch('/api/workflows');
      if (response.ok) {
        const data = await response.json();
        setWorkflows(data);
      }
    } catch (error) {
      console.error('Failed to fetch workflows:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPublicWorkflows = async () => {
    try {
      const response = await apiFetch('/api/public-workflows');
      if (response.ok) {
        const data = await response.json();
        setPublicWorkflows(data);
      }
    } catch (error) {
      console.error('Failed to fetch public workflows:', error);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const response = await apiFetch(`/api/workflows/${id}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        setWorkflows((prev) => prev.filter((w) => w.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete workflow:', error);
    }
    setDeleteConfirm(null);
  };

  // Load more covers callback for infinite scroll
  const loadMoreCovers = useCallback(() => {
    setVisibleCoverCount((prev) =>
      Math.min(prev + COVERS_PER_PAGE, coverAssets.length),
    );
  }, [coverAssets.length]);

  // Intersection Observer effect for infinite scroll
  useEffect(() => {
    if (!editingCoverFor || loadingAssets) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0].isIntersecting &&
          visibleCoverCount < coverAssets.length
        ) {
          loadMoreCovers();
        }
      },
      { threshold: 0.1, rootMargin: '100px' },
    );

    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }

    return () => observer.disconnect();
  }, [
    editingCoverFor,
    loadingAssets,
    visibleCoverCount,
    coverAssets.length,
    loadMoreCovers,
  ]);

  const openCoverEditor = async (workflowId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingCoverFor(workflowId);
    setLoadingAssets(true);
    setVisibleCoverCount(COVERS_PER_PAGE); // Reset pagination

    try {
      const response = await apiFetch('/api/assets/images');
      if (response.ok) {
        const data = await response.json();
        setCoverAssets(data);
      }
    } catch (error) {
      console.error('Failed to fetch assets:', error);
    } finally {
      setLoadingAssets(false);
    }
  };

  const selectCover = async (assetUrl: string) => {
    if (!editingCoverFor) return;

    try {
      const response = await apiFetch(
        `/api/workflows/${editingCoverFor}/cover`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ coverUrl: `/canvasApi${assetUrl}` }),
        },
      );

      if (response.ok) {
        // Update local state
        setWorkflows((prev) =>
          prev.map((w) =>
            w.id === editingCoverFor
              ? { ...w, coverUrl: `/canvasApi${assetUrl}` }
              : w,
          ),
        );
      }
    } catch (error) {
      console.error('Failed to update cover:', error);
    }

    setEditingCoverFor(null);
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Main Panel */}
      <div
        className={`absolute left-20 z-40 flex max-h-[500px] w-[700px] flex-col overflow-hidden rounded-2xl border shadow-2xl backdrop-blur-xl transition-colors duration-300 ${isDark ? 'border-neutral-800 bg-[#0a0a0a]/95' : 'border-neutral-200 bg-white/95'}`}
        style={{ top: panelY }}
      >
        {/* Header with Tabs */}
        <div
          className={`flex items-center justify-between border-b px-5 py-4 ${isDark ? 'border-neutral-800' : 'border-neutral-200'}`}
        >
          <div className="flex items-center gap-6">
            <button
              onClick={() => setActiveTab('my')}
              className={`pb-1 font-medium transition-colors ${activeTab === 'my' ? (isDark ? 'border-b-2 border-white text-white' : 'border-b-2 border-neutral-900 text-neutral-900') : isDark ? 'text-neutral-500 hover:text-neutral-300' : 'text-neutral-400 hover:text-neutral-600'}`}
            >
              My Workflows
            </button>
            <button
              onClick={() => setActiveTab('public')}
              className={`pb-1 font-medium transition-colors ${activeTab === 'public' ? (isDark ? 'border-b-2 border-white text-white' : 'border-b-2 border-neutral-900 text-neutral-900') : isDark ? 'text-neutral-500 hover:text-neutral-300' : 'text-neutral-400 hover:text-neutral-600'}`}
            >
              Public Workflows
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
          className="flex-1 overflow-y-auto p-4"
          style={{
            scrollbarWidth: 'thin',
            scrollbarColor: isDark ? '#525252 #171717' : '#d4d4d4 #fafafa',
          }}
        >
          {loading && activeTab === 'my' ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="animate-spin text-neutral-500" size={24} />
            </div>
          ) : activeTab === 'my' ? (
            /* My Workflows Tab */
            workflows.length === 0 ? (
              <div className="flex h-40 items-center justify-center text-neutral-500">
                No workflows found
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-4">
                {workflows.map((workflow) => (
                  <div
                    key={workflow.id}
                    onClick={() => onLoadWorkflow(workflow.id)}
                    className={`group cursor-pointer overflow-hidden rounded-xl transition-all ${
                      workflow.id === currentWorkflowId
                        ? 'ring-2 ring-blue-500'
                        : ''
                    }`}
                  >
                    {/* Thumbnail */}
                    <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden bg-gradient-to-br from-neutral-800 to-neutral-900">
                      {workflow.coverUrl ? (
                        <img
                          src={workflow.coverUrl}
                          alt={workflow.title}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-600/20">
                          <FileText size={28} className="text-neutral-500" />
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-all group-hover:opacity-100">
                        {/* Edit cover button */}
                        <button
                          onClick={(e) => openCoverEditor(workflow.id, e)}
                          className="rounded-lg bg-black/50 p-1.5 transition-all hover:bg-blue-500"
                          title="Edit cover"
                        >
                          <Pencil size={14} className="text-white" />
                        </button>
                        {/* Delete button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirm(workflow.id);
                          }}
                          className="rounded-lg bg-black/50 p-1.5 transition-all hover:bg-red-500"
                          title="Delete workflow"
                        >
                          <Trash2 size={14} className="text-white" />
                        </button>
                      </div>
                    </div>
                    {/* Info */}
                    <div
                      className={`p-3 ${isDark ? 'bg-neutral-900/50' : 'bg-neutral-100/90'}`}
                    >
                      <h3
                        className={`truncate text-sm font-medium ${isDark ? 'text-white' : 'text-neutral-900'}`}
                      >
                        {workflow.title || 'Untitled'}
                      </h3>
                      <p
                        className={`mt-0.5 text-xs ${isDark ? 'text-neutral-500' : 'text-neutral-600'}`}
                      >
                        {workflow.nodeCount} nodes
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : /* Public Workflows Tab */
          publicWorkflows.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center gap-2 text-neutral-500">
              <FileText size={32} className="opacity-50" />
              <p>No public workflows available</p>
              <p className="text-xs text-neutral-600">
                Add workflow JSONs to public/workflows/
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-4">
              {publicWorkflows.map((workflow) => (
                <div
                  key={workflow.id}
                  onClick={() => onLoadWorkflow(`public:${workflow.id}`)}
                  className="group cursor-pointer overflow-hidden rounded-xl transition-all"
                >
                  {/* Thumbnail */}
                  <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden bg-gradient-to-br from-green-800/30 to-emerald-900/30">
                    {workflow.coverUrl ? (
                      <img
                        src={workflow.coverUrl}
                        alt={workflow.title}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-gradient-to-br from-green-500/20 to-emerald-600/20">
                        <FileText size={28} className="text-neutral-500" />
                      </div>
                    )}
                    {/* Public badge */}
                    <div className="absolute left-2 top-2 rounded bg-green-600/80 px-2 py-0.5 text-[10px] font-medium text-white">
                      PUBLIC
                    </div>
                  </div>
                  {/* Info */}
                  <div
                    className={`p-3 ${isDark ? 'bg-neutral-900/50' : 'bg-neutral-100/90'}`}
                  >
                    <h3
                      className={`truncate text-sm font-medium ${isDark ? 'text-white' : 'text-neutral-900'}`}
                    >
                      {workflow.title || 'Untitled'}
                    </h3>
                    <p
                      className={`mt-0.5 text-xs ${isDark ? 'text-neutral-500' : 'text-neutral-600'}`}
                    >
                      {workflow.description || `${workflow.nodeCount} nodes`}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="app-modal-mask absolute inset-0 z-50 flex items-center justify-center">
          <div className="w-[340px] rounded-2xl border border-neutral-700 bg-[#1a1a1a] p-6 shadow-2xl">
            <h3 className="mb-2 text-lg font-semibold text-white">
              Delete Workflow
            </h3>
            <p className="mb-6 text-sm text-neutral-400">
              Are you sure you want to delete this workflow? This action cannot
              be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="rounded-lg bg-neutral-800 px-4 py-2 text-sm text-white transition-colors hover:bg-neutral-700"
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

      {/* Cover Selection Modal */}
      {editingCoverFor && (
        <div className="app-modal-mask absolute inset-0 z-50 flex items-center justify-center">
          <div className="flex max-h-[500px] w-[500px] flex-col rounded-2xl border border-neutral-700 bg-[#1a1a1a] p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">
                Select Cover Image
              </h3>
              <button
                onClick={() => setEditingCoverFor(null)}
                className="rounded-lg p-1.5 text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {loadingAssets ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 className="animate-spin text-neutral-500" size={24} />
              </div>
            ) : coverAssets.length === 0 ? (
              <div className="flex h-40 items-center justify-center text-neutral-500">
                No images available. Generate some images first!
              </div>
            ) : (
              <div className="grid flex-1 grid-cols-3 gap-3 overflow-y-auto">
                {coverAssets.slice(0, visibleCoverCount).map((asset) => (
                  <button
                    key={asset.id}
                    onClick={() => selectCover(asset.url)}
                    className="group relative h-32 w-full overflow-hidden rounded-lg bg-neutral-900 transition-all hover:ring-2 hover:ring-blue-500"
                  >
                    <LazyImage
                      src={`/canvasApi${asset.url}`}
                      alt="Cover option"
                      className="h-full w-full"
                      placeholderClassName="rounded-lg"
                      rootMargin="100px"
                    />
                    <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30">
                      <Check
                        size={24}
                        className="text-white opacity-0 transition-opacity group-hover:opacity-100"
                      />
                    </div>
                  </button>
                ))}

                {/* Load more sentinel - triggers infinite scroll */}
                {visibleCoverCount < coverAssets.length && (
                  <div
                    ref={loadMoreRef}
                    className="col-span-3 flex items-center justify-center py-4"
                  >
                    <Loader2
                      className="animate-spin text-neutral-500"
                      size={20}
                    />
                    <span className="ml-2 text-sm text-neutral-500">
                      Loading more...
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};
