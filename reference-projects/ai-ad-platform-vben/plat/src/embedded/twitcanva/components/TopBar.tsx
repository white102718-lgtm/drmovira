/** @jsxImportSource react */
/**
 * TopBar.tsx
 *
 * Top navigation bar component with canvas title, save button, and other controls.
 */

import React, { useState } from 'react';
import { ArrowLeft, Plus, Save, Loader2 } from 'lucide-react';

interface TopBarProps {
  // Title
  canvasTitle: string;
  isEditingTitle: boolean;
  editingTitleValue: string;
  canvasTitleInputRef: React.RefObject<HTMLInputElement>;
  setCanvasTitle: (title: string) => void;
  setIsEditingTitle: (editing: boolean) => void;
  setEditingTitleValue: (value: string) => void;
  // Actions
  onSave: () => void | Promise<void>;
  onNew: () => void;
  onBack?: () => void;
  hasUnsavedChanges: boolean;
  lastAutoSaveTime?: number;
  // Layout
  isChatOpen?: boolean;
  // Theme
  canvasTheme: 'dark' | 'light';
  onToggleTheme: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  canvasTitle,
  isEditingTitle,
  editingTitleValue,
  canvasTitleInputRef,
  setCanvasTitle,
  setIsEditingTitle,
  setEditingTitleValue,
  onSave,
  onNew,
  onBack,
  hasUnsavedChanges,
  lastAutoSaveTime,
  isChatOpen = false,
  canvasTheme,
  onToggleTheme,
}) => {
  const [showNewConfirm, setShowNewConfirm] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const handleTitleBlur = () => {
    if (editingTitleValue.trim()) {
      setCanvasTitle(editingTitleValue.trim());
    } else {
      setEditingTitleValue(canvasTitle);
    }
    setIsEditingTitle(false);
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (editingTitleValue.trim()) {
        setCanvasTitle(editingTitleValue.trim());
      }
      setIsEditingTitle(false);
    } else if (e.key === 'Escape') {
      setEditingTitleValue(canvasTitle);
      setIsEditingTitle(false);
    }
  };

  const handleTitleDoubleClick = () => {
    setEditingTitleValue(canvasTitle);
    setIsEditingTitle(true);
  };

  const handleNewClick = () => {
    if (hasUnsavedChanges) {
      setShowNewConfirm(true);
    } else {
      onNew();
    }
  };

  const handleSaveAndNew = async () => {
    try {
      setIsSaving(true);
      await onSave();
      setShowNewConfirm(false);
      onNew();
    } catch (error) {
      console.error('Failed to save and new:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDiscardAndNew = () => {
    setShowNewConfirm(false);
    onNew();
  };

  return (
    <>
      <div
        className="pointer-events-none absolute left-0 top-0 z-50 flex h-14 items-center justify-between px-6 transition-all duration-300"
        style={{ width: isChatOpen ? 'calc(100% - 400px)' : '100%' }}
      >
        {/* Left: Logo & Title */}
        <div className="pointer-events-auto flex items-center gap-3">
          {onBack && (
            <button
              aria-label="返回画布列表"
              className={`flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
                canvasTheme === 'dark'
                  ? 'border-neutral-700 bg-neutral-900 text-neutral-300 hover:bg-neutral-800 hover:text-white'
                  : 'border-neutral-200 bg-white text-neutral-600 shadow-sm hover:bg-neutral-50 hover:text-neutral-900'
              }`}
              onClick={onBack}
              title="返回画布列表"
            >
              <ArrowLeft size={17} />
            </button>
          )}
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-600 text-sm font-bold text-white">
            AI
          </div>
          {isEditingTitle ? (
            <input
              ref={canvasTitleInputRef as React.RefObject<HTMLInputElement>}
              type="text"
              value={editingTitleValue}
              onChange={(e) => setEditingTitleValue(e.target.value)}
              onBlur={handleTitleBlur}
              onKeyDown={handleTitleKeyDown}
              className="min-w-[100px] border-b border-blue-500 bg-transparent font-semibold text-neutral-300 outline-none"
            />
          ) : (
            <span
              className={`cursor-pointer font-semibold transition-colors ${canvasTheme === 'dark' ? 'text-neutral-300 hover:text-white' : 'text-neutral-900 hover:text-neutral-600'}`}
              onDoubleClick={handleTitleDoubleClick}
              title="双击重命名"
            >
              {canvasTitle}
            </span>
          )}
        </div>

        {/* Right: Actions */}
        <div className="pointer-events-auto flex items-center gap-3">
          {/* Auto-save notification - before save button */}
          {lastAutoSaveTime && !hasUnsavedChanges && (
            <div
              className={`animate-in fade-in rounded border px-2 py-1 text-[10px] font-medium duration-500 ${
                canvasTheme === 'dark'
                  ? 'border-neutral-800 text-neutral-500'
                  : 'border-neutral-100 text-neutral-400'
              }`}
            >
              已自动保存{' '}
              {new Date(lastAutoSaveTime).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </div>
          )}
          <button
            onClick={() => onSave()}
            className={`flex items-center gap-2 rounded-full border px-5 py-2.5 text-sm font-medium transition-colors ${
              canvasTheme === 'dark'
                ? 'border-neutral-600 bg-neutral-800 text-white hover:bg-neutral-700'
                : 'border-neutral-300 bg-neutral-100 text-neutral-900 shadow-sm hover:bg-neutral-200'
            }`}
          >
            <Save size={16} />
            保存
          </button>
          <button
            onClick={handleNewClick}
            className={`flex items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium transition-colors ${
              canvasTheme === 'dark'
                ? 'border-neutral-600 bg-neutral-800 text-white hover:bg-neutral-700'
                : 'border-neutral-300 bg-neutral-200 text-neutral-900 hover:bg-neutral-300'
            }`}
          >
            <Plus size={16} />
            新建
          </button>
          <button
            onClick={onToggleTheme}
            className={`flex h-10 w-10 items-center justify-center rounded-full border transition-colors ${
              canvasTheme === 'dark'
                ? 'border-neutral-700 bg-neutral-900 text-yellow-400 hover:bg-neutral-800'
                : 'border-neutral-200 bg-white text-orange-500 shadow-sm hover:bg-neutral-50'
            }`}
            title={canvasTheme === 'dark' ? '切换为亮色画布' : '切换为深色画布'}
          >
            {canvasTheme === 'dark' ? (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Unsaved Changes Confirmation Modal */}
      {showNewConfirm && (
        <div className="app-modal-mask absolute inset-0 z-[100] flex items-center justify-center">
          <div className="w-[400px] rounded-2xl border border-neutral-700 bg-[#1a1a1a] p-6 shadow-2xl">
            <h3 className="mb-2 text-lg font-semibold text-white">尚未保存</h3>
            <p className="mb-6 text-sm text-neutral-400">
              当前画布有未保存内容，是否保存后再新建画布？
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowNewConfirm(false)}
                disabled={isSaving}
                className="rounded-lg bg-neutral-800 px-4 py-2 text-sm text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleDiscardAndNew}
                disabled={isSaving}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                放弃更改
              </button>
              <button
                onClick={handleSaveAndNew}
                disabled={isSaving}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    保存中...
                  </>
                ) : (
                  '保存并新建'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
