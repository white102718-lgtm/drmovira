/** @jsxImportSource react */
import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { Copy, FileText, Link2, Maximize2, Minimize2, Music2, Plus, X } from 'lucide-react';
import { useImageHoverPreview } from './ImageHoverPreview';

export interface PromptMentionReference {
  id: string;
  alias: string;
  url: string;
  sourceTitle: string;
  sourceNodeId?: string;
  mediaType?: 'image' | 'video' | 'audio' | 'file' | 'link';
}

interface PromptMentionEditorProps {
  value: string;
  references: PromptMentionReference[];
  placeholder: string;
  ariaLabel: string;
  onChange: (value: string) => void;
  /** 是否处于扩大编辑态，扩大后编辑区更高，按钮切成收起。 */
  expanded?: boolean;
  onToggleExpand?: () => void;
  /** 仅图片/视频节点展示：插入已连线参考素材，不新增参考来源。 */
  showReferenceTools?: boolean;
  /** 紧凑卡片：压缩提示词高度，工具条并入卡片顶栏。 */
  compact?: boolean;
  /** 插入到「+ 参考」前面，例如文本节点的图片/视频切换。 */
  toolbarExtra?: React.ReactNode;
  /** 拖动工具条缩略图换序后，由外部同步 @图片N / @视频N / @音频N。currentValue 是编辑器里的实时提示词。 */
  onReorderReferences?: (
    fromIndex: number,
    toIndex: number,
    currentValue: string,
  ) => void;
  /** 删除缩略图时断开对应连线，并同步提示词里的引用编号。 */
  onRemoveReference?: (
    reference: PromptMentionReference,
    currentValue: string,
  ) => void;
  /** 粘贴带顺序的提示词后，按复制时的参考图顺序对齐当前节点。 */
  onApplyCopiedImageOrder?: (imageUrls: string[]) => void;
  onCopiedPrompt?: () => void;
  tone?: 'light' | 'dark';
}

const PROMPT_CLIPBOARD_MARKER = 'adgen-canvas-prompt';

interface PromptClipboardPayload {
  v: 1;
  prompt: string;
  imageUrls: string[];
}

const encodePromptClipboardHtml = (prompt: string, imageUrls: string[]) => {
  const payload: PromptClipboardPayload = { v: 1, prompt, imageUrls };
  return `<!--${PROMPT_CLIPBOARD_MARKER}:${encodeURIComponent(JSON.stringify(payload))}-->`;
};

const readPromptClipboardPayload = (
  html: string,
): PromptClipboardPayload | null => {
  const match = html.match(
    new RegExp(`<!--${PROMPT_CLIPBOARD_MARKER}:([^>]+)-->`),
  );
  if (!match?.[1]) return null;
  try {
    const payload = JSON.parse(
      decodeURIComponent(match[1]),
    ) as PromptClipboardPayload;
    if (payload?.v !== 1 || typeof payload.prompt !== 'string') return null;
    return {
      v: 1,
      prompt: payload.prompt,
      imageUrls: Array.isArray(payload.imageUrls)
        ? payload.imageUrls.filter((url) => typeof url === 'string')
        : [],
    };
  } catch {
    return null;
  }
};

const writePromptClipboard = (
  clipboardData: DataTransfer,
  prompt: string,
  imageUrls: string[],
) => {
  clipboardData.setData('text/plain', prompt);
  clipboardData.setData(
    'text/html',
    `${encodePromptClipboardHtml(prompt, imageUrls)}${prompt}`,
  );
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const CANVAS_MENTION_SPLIT_PATTERN = /(@(?:图片|视频|音频|文档|网页)\d+)/g;

const isHoverableMentionMedia = (
  mediaType?: PromptMentionReference['mediaType'],
): mediaType is 'image' | 'video' =>
  mediaType === 'image' || mediaType === 'video' || mediaType == null;

const appendReferenceThumb = (
  parent: HTMLElement,
  reference: PromptMentionReference,
) => {
  if (reference.mediaType === 'video') {
    const video = document.createElement('video');
    video.src = reference.url;
    video.muted = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.className = 'max-h-full max-w-full object-contain';
    video.addEventListener('loadedmetadata', () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) return;
      video.currentTime = Math.min(0.5, Math.max(0, video.duration / 4));
    });
    parent.append(video);
    return;
  }
  if (
    reference.mediaType === 'audio' ||
    reference.mediaType === 'file' ||
    reference.mediaType === 'link'
  ) {
    const mark = document.createElement('span');
    mark.className = 'text-[10px] font-semibold text-violet-600';
    mark.textContent =
      reference.mediaType === 'audio'
        ? '音'
        : reference.mediaType === 'file'
          ? '文'
          : '链';
    parent.append(mark);
    return;
  }
  const image = document.createElement('img');
  image.src = reference.url;
  image.alt = '';
  image.className = 'max-h-full max-w-full object-contain';
  parent.append(image);
};

const ReferenceThumb: React.FC<{
  url: string;
  mediaType?: PromptMentionReference['mediaType'];
  className?: string;
}> = ({ url, mediaType = 'image', className }) => {
  if (mediaType === 'video') {
    return (
      <video
        src={url}
        muted
        playsInline
        preload="metadata"
        className={className}
      />
    );
  }
  if (mediaType === 'audio') {
    return <Music2 size={12} className="text-violet-600" />;
  }
  if (mediaType === 'file') {
    return <FileText size={12} className="text-violet-600" />;
  }
  if (mediaType === 'link') {
    return <Link2 size={12} className="text-violet-600" />;
  }
  return <img src={url} alt="" className={className} />;
};

/**
 * 支持图片和视频引用的提示词编辑器。
 * @图片N / @视频N 会显示为带缩略图的不可拆分标记，候选框跟随光标并支持方向键选择。
 * 右上角放大按钮对齐 LibTV：把窄输入框扩成大编辑区，方便写长提示词。
 * 「+ 参考」只列出当前节点已连线的参考素材，点击插入已有编号。
 * 缩略图右上角删除会断开对应连线，不必再去画布上剪线。
 */
const PromptMentionEditor: React.FC<PromptMentionEditorProps> = ({
  value,
  references,
  placeholder,
  ariaLabel,
  onChange,
  expanded = false,
  onToggleExpand,
  showReferenceTools = false,
  compact = false,
  toolbarExtra = null,
  onReorderReferences,
  onRemoveReference,
  onApplyCopiedImageOrder,
  onCopiedPrompt,
  tone = 'light',
}) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const referenceButtonRef = useRef<HTMLButtonElement>(null);
  const referenceMenuRef = useRef<HTMLDivElement>(null);
  const referenceMenuCloseTimerRef = useRef<number | null>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [popupPosition, setPopupPosition] = useState({ left: 12, top: 42 });
  const [referenceMenuOpen, setReferenceMenuOpen] = useState(false);
  const [referenceMenuPosition, setReferenceMenuPosition] = useState({
    left: 0,
    top: 0,
  });
  const { showPreview, hidePreview, previewNode } = useImageHoverPreview();
  const previewApiRef = useRef({ showPreview, hidePreview });
  previewApiRef.current = { showPreview, hidePreview };
  const referencesByAliasRef = useRef(new Map<string, PromptMentionReference>());
  referencesByAliasRef.current = new Map(
    references.map((reference) => [reference.alias, reference]),
  );
  const referenceDragRef = useRef<{
    fromIndex: number;
    pointerId: number;
    startX: number;
    dragging: boolean;
  } | null>(null);
  const [draggingReferenceIndex, setDraggingReferenceIndex] = useState<
    number | null
  >(null);
  const [dropReferenceIndex, setDropReferenceIndex] = useState<number | null>(
    null,
  );
  const dropReferenceIndexRef = useRef<number | null>(null);
  const lastEmittedValueRef = useRef(value);
  const canReorderReferences =
    Boolean(onReorderReferences) && references.length > 1;
  const filteredReferences =
    query === null
      ? []
      : references.filter((reference) => reference.alias.includes(query));

  const serializeEditor = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return '';
    const serializeNode = (node: Node): string => {
      if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
      if (!(node instanceof HTMLElement)) return '';
      if (node.dataset.canvasMention) return node.dataset.canvasMention;
      if (node.tagName === 'BR') return '\n';
      const content = Array.from(node.childNodes).map(serializeNode).join('');
      return node === editor || node.tagName === 'SPAN'
        ? content
        : `${content}\n`;
    };
    return serializeNode(editor)
      .replace(/\n{3,}/g, '\n\n')
      .replace(/\u00a0/g, ' ');
  }, []);

  const createMentionElement = useCallback(
    (reference: PromptMentionReference) => {
      const mention = document.createElement('span');
      mention.contentEditable = 'false';
      mention.dataset.canvasMention = `@${reference.alias}`;
      mention.className =
        'mx-0.5 inline-flex select-none items-center gap-1 rounded-md border border-violet-200 bg-violet-50 py-0.5 pl-0.5 pr-1 align-middle text-xs font-semibold text-violet-700';

      const thumb = document.createElement('span');
      thumb.className =
        'inline-flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded bg-white';
      appendReferenceThumb(thumb, reference);
      mention.append(thumb, document.createTextNode(`@${reference.alias}`));
      mention.addEventListener('mouseenter', () => {
        const currentReference =
          referencesByAliasRef.current.get(reference.alias) || reference;
        if (!isHoverableMentionMedia(currentReference.mediaType)) return;
        previewApiRef.current.showPreview(
          mention,
          currentReference.url,
          `@${currentReference.alias} · ${currentReference.sourceTitle}`,
          currentReference.mediaType === 'video' ? 'video' : 'image',
        );
      });
      mention.addEventListener('mouseleave', () => {
        previewApiRef.current.hidePreview();
      });
      return mention;
    },
    [],
  );

  const renderValue = useCallback(
    (nextValue: string) => {
      const editor = editorRef.current;
      if (!editor) return;
      editor.replaceChildren();
      const referenceByAlias = new Map(
        references.map((reference) => [`@${reference.alias}`, reference]),
      );
      nextValue.split(CANVAS_MENTION_SPLIT_PATTERN).forEach((part) => {
        const reference = referenceByAlias.get(part);
        if (reference) editor.append(createMentionElement(reference));
        else if (part) editor.append(document.createTextNode(part));
      });
    },
    [createMentionElement, references],
  );

  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const isExternalChange = value !== lastEmittedValueRef.current;
    // 保留聚焦编辑器的光标；图片换序后的 @图片N 缩略图由下方同步更新。
    if (!isExternalChange && document.activeElement === editor) return;
    if (serializeEditor() !== value) renderValue(value);
    lastEmittedValueRef.current = value;
  }, [renderValue, serializeEditor, value]);

  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.querySelectorAll<HTMLElement>('[data-canvas-mention]').forEach((mention) => {
      const alias = mention.dataset.canvasMention?.replace(/^@/, '');
      const reference = alias ? referencesByAliasRef.current.get(alias) : undefined;
      const image = mention.querySelector<HTMLImageElement>('img');
      if (reference?.mediaType === 'image' && image && image.src !== reference.url) {
        image.src = reference.url;
      }
    });
  }, [references]);

  useLayoutEffect(() => {
    if (!expanded) return;
    editorRef.current?.focus();
  }, [expanded]);

  const updateMentionQuery = useCallback(() => {
    const selection = window.getSelection();
    const editor = editorRef.current;
    const wrapper = wrapperRef.current;
    if (
      !selection?.rangeCount ||
      !editor ||
      !wrapper ||
      !editor.contains(selection.anchorNode)
    ) {
      setQuery(null);
      return;
    }
    const anchorNode = selection.anchorNode;
    const anchorOffset = selection.anchorOffset;
    if (anchorNode?.nodeType !== Node.TEXT_NODE) {
      setQuery(null);
      return;
    }
    const mentionMatch = (anchorNode.textContent || '')
      .slice(0, anchorOffset)
      .match(/@([^\s@]*)$/);
    if (!mentionMatch) {
      setQuery(null);
      return;
    }
    const caretRect = selection.getRangeAt(0).getBoundingClientRect();
    const wrapperRect = wrapper.getBoundingClientRect();
    setPopupPosition({
      left: clamp(
        caretRect.left - wrapperRect.left,
        8,
        Math.max(8, wrapperRect.width - 244),
      ),
      top: Math.max(38, caretRect.bottom - wrapperRect.top + 6),
    });
    setQuery(mentionMatch[1] || '');
    setActiveIndex(0);
  }, []);

  const commitEditorValue = useCallback(() => {
    const nextValue = serializeEditor();
    lastEmittedValueRef.current = nextValue;
    onChange(nextValue);
    updateMentionQuery();
  }, [onChange, serializeEditor, updateMentionQuery]);

  const placeMention = useCallback(
    (reference: PromptMentionReference, replaceQuery: boolean) => {
      const editor = editorRef.current;
      if (!editor) return;
      // 候选项会在点击后卸载，主动结束其悬停预览，避免残留。
      hidePreview();
      const mention = createMentionElement(reference);
      const trailingSpace = document.createTextNode('\u00a0');
      const selection = window.getSelection();
      const canUseCaret = Boolean(
        selection?.rangeCount &&
          selection.anchorNode &&
          editor.contains(selection.anchorNode),
      );

      if (canUseCaret && selection) {
        const range = selection.getRangeAt(0);
        if (replaceQuery) {
          const anchorNode = selection.anchorNode;
          const anchorOffset = selection.anchorOffset;
          if (anchorNode?.nodeType !== Node.TEXT_NODE) return;
          const mentionMatch = (anchorNode.textContent || '')
            .slice(0, anchorOffset)
            .match(/@([^\s@]*)$/);
          if (!mentionMatch) return;
          range.setStart(anchorNode, anchorOffset - mentionMatch[0].length);
          range.deleteContents();
        }
        range.insertNode(trailingSpace);
        range.insertNode(mention);
        range.setStartAfter(trailingSpace);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      } else {
        editor.append(mention, trailingSpace);
        const range = document.createRange();
        range.setStartAfter(trailingSpace);
        range.collapse(true);
        const nextSelection = window.getSelection();
        nextSelection?.removeAllRanges();
        nextSelection?.addRange(range);
      }

      setQuery(null);
      setReferenceMenuOpen(false);
      const nextValue = serializeEditor();
      lastEmittedValueRef.current = nextValue;
      onChange(nextValue);
      editor.focus();
    },
    [createMentionElement, hidePreview, onChange, serializeEditor],
  );

  const insertMention = useCallback(
    (reference: PromptMentionReference) => {
      placeMention(reference, true);
    },
    [placeMention],
  );

  const appendMention = useCallback(
    (reference: PromptMentionReference) => {
      placeMention(reference, false);
    },
    [placeMention],
  );

  const finishReferenceDrag = useCallback(
    (
      reference: PromptMentionReference,
      event: React.PointerEvent<HTMLButtonElement>,
    ) => {
      const drag = referenceDragRef.current;
      if (!drag || drag.pointerId !== event.pointerId) return;
      referenceDragRef.current = null;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // 捕获可能已在 pointercancel 时释放。
      }
      const insertAt = dropReferenceIndexRef.current;
      dropReferenceIndexRef.current = null;
      setDraggingReferenceIndex(null);
      setDropReferenceIndex(null);
      if (drag.dragging) {
        hidePreview();
        if (insertAt == null || !onReorderReferences) return;
        const toIndex = insertAt > drag.fromIndex ? insertAt - 1 : insertAt;
        if (toIndex !== drag.fromIndex) {
          onReorderReferences(drag.fromIndex, toIndex, serializeEditor());
        }
        return;
      }
      appendMention(reference);
    },
    [appendMention, hidePreview, onReorderReferences, serializeEditor],
  );

  const copyPromptWithImageOrder = useCallback(async () => {
    const prompt = serializeEditor() || value;
    const imageUrls = references.map((reference) => reference.url);
    try {
      if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItem({
            'text/plain': new Blob([prompt], { type: 'text/plain' }),
            'text/html': new Blob(
              [encodePromptClipboardHtml(prompt, imageUrls) + prompt],
              { type: 'text/html' },
            ),
          }),
        ]);
        return true;
      }
      await navigator.clipboard.writeText(prompt);
      return imageUrls.length === 0;
    } catch {
      return false;
    }
  }, [references, serializeEditor, value]);

  const clearReferenceMenuCloseTimer = useCallback(() => {
    if (referenceMenuCloseTimerRef.current !== null) {
      window.clearTimeout(referenceMenuCloseTimerRef.current);
      referenceMenuCloseTimerRef.current = null;
    }
  }, []);

  const closeReferenceMenu = useCallback(() => {
    clearReferenceMenuCloseTimer();
    hidePreview();
    setReferenceMenuOpen(false);
  }, [clearReferenceMenuCloseTimer, hidePreview]);

  const scheduleReferenceMenuClose = useCallback(() => {
    clearReferenceMenuCloseTimer();
    // 菜单通过 Portal 渲染，与触发按钮有少量间距，避免移动到菜单时立即收起。
    referenceMenuCloseTimerRef.current = window.setTimeout(() => {
      hidePreview();
      setReferenceMenuOpen(false);
      referenceMenuCloseTimerRef.current = null;
    }, 160);
  }, [clearReferenceMenuCloseTimer, hidePreview]);

  const openReferenceMenu = useCallback(() => {
    const button = referenceButtonRef.current;
    if (!button) return;
    clearReferenceMenuCloseTimer();
    const rect = button.getBoundingClientRect();
    setReferenceMenuPosition({
      left: Math.min(rect.left, window.innerWidth - 280),
      top: rect.bottom + 6,
    });
    setReferenceMenuOpen(true);
  }, [clearReferenceMenuCloseTimer]);

  useEffect(
    () => () => clearReferenceMenuCloseTimer(),
    [clearReferenceMenuCloseTimer],
  );

  useEffect(() => {
    if (!referenceMenuOpen) return;
    const closeOnPointer = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (
        referenceMenuRef.current?.contains(target) ||
        referenceButtonRef.current?.contains(target)
      ) {
        return;
      }
      closeReferenceMenu();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      closeReferenceMenu();
    };
    window.addEventListener('mousedown', closeOnPointer);
    window.addEventListener('keydown', closeOnEscape, true);
    return () => {
      window.removeEventListener('mousedown', closeOnPointer);
      window.removeEventListener('keydown', closeOnEscape, true);
    };
  }, [closeReferenceMenu, referenceMenuOpen]);

  return (
    <div
      ref={wrapperRef}
      className={`canvas-prompt-editor ${expanded ? 'canvas-prompt-editor--expanded' : ''} ${compact ? 'canvas-prompt-editor--compact' : ''} relative`}
    >
      {onToggleExpand && (
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={onToggleExpand}
          aria-label={expanded ? '收起提示词' : '扩大提示词'}
          title={expanded ? '收起提示词' : '扩大提示词'}
          className="canvas-prompt-expand-btn"
        >
          {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      )}
      {(showReferenceTools || toolbarExtra) && (
        <div className="canvas-prompt-toolbar">
          {toolbarExtra}
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              void copyPromptWithImageOrder().then((ok) => {
                if (ok) onCopiedPrompt?.();
              });
            }}
            title="复制提示词和参考顺序"
            className="canvas-prompt-chip-btn"
          >
            <Copy size={13} />
            复制
          </button>
          {showReferenceTools && (
            <>
              <button
                ref={referenceButtonRef}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={openReferenceMenu}
                onMouseLeave={scheduleReferenceMenuClose}
                onFocus={openReferenceMenu}
                onBlur={scheduleReferenceMenuClose}
                onClick={openReferenceMenu}
                aria-haspopup="listbox"
                aria-expanded={referenceMenuOpen}
                className={`canvas-prompt-chip-btn ${referenceMenuOpen ? 'is-open' : ''}`}
              >
                <Plus size={13} />
                参考
                {references.length > 0 && (
                  <span className="canvas-prompt-chip-btn__count">
                    {references.length}
                  </span>
                )}
              </button>
              {references.map((reference, index) => (
                <div
                  key={`toolbar-ref-${reference.id}`}
                  className={`canvas-prompt-ref-chip-wrap ${draggingReferenceIndex === index ? 'is-dragging' : ''}`}
                >
                  <button
                    type="button"
                    data-ref-index={index}
                    onMouseDown={(event) => event.preventDefault()}
                    onPointerDown={(event) => {
                      if (!canReorderReferences || event.button !== 0) return;
                      event.stopPropagation();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      referenceDragRef.current = {
                        fromIndex: index,
                        pointerId: event.pointerId,
                        startX: event.clientX,
                        dragging: false,
                      };
                    }}
                    onPointerMove={(event) => {
                      const drag = referenceDragRef.current;
                      if (!drag || drag.pointerId !== event.pointerId) return;
                      if (
                        !drag.dragging &&
                        Math.abs(event.clientX - drag.startX) < 6
                      )
                        return;
                      if (!drag.dragging) {
                        drag.dragging = true;
                        hidePreview();
                        setDraggingReferenceIndex(drag.fromIndex);
                      }
                      const target = document.elementFromPoint(
                        event.clientX,
                        event.clientY,
                      );
                      const chip =
                        target instanceof Element
                          ? target.closest('[data-ref-index]')
                          : null;
                      if (!(chip instanceof HTMLElement)) return;
                      const overIndex = Number(chip.dataset.refIndex);
                      if (Number.isNaN(overIndex)) return;
                      const rect = chip.getBoundingClientRect();
                      const insertAt =
                        event.clientX < rect.left + rect.width / 2
                          ? overIndex
                          : overIndex + 1;
                      dropReferenceIndexRef.current = insertAt;
                      setDropReferenceIndex(insertAt);
                    }}
                    onPointerUp={(event) =>
                      finishReferenceDrag(reference, event)
                    }
                    onPointerCancel={(event) =>
                      finishReferenceDrag(reference, event)
                    }
                    onMouseEnter={(event) => {
                      if (referenceDragRef.current?.dragging) return;
                      if (!isHoverableMentionMedia(reference.mediaType)) return;
                      showPreview(
                        event.currentTarget,
                        reference.url,
                        `@${reference.alias} · ${reference.sourceTitle}`,
                        reference.mediaType === 'video' ? 'video' : 'image',
                      );
                    }}
                    onMouseLeave={hidePreview}
                    onClick={(event) => {
                      if (canReorderReferences) event.preventDefault();
                      else appendMention(reference);
                    }}
                    title={
                      canReorderReferences
                        ? `拖动调整顺序，或点击插入 @${reference.alias} · 来源：${reference.sourceTitle}`
                        : `插入 @${reference.alias} · 来源：${reference.sourceTitle}`
                    }
                    className={`canvas-prompt-ref-chip ${canReorderReferences ? 'canvas-prompt-ref-chip--sortable' : ''} ${draggingReferenceIndex === index ? 'is-dragging' : ''} ${dropReferenceIndex === index ? 'is-drop-before' : ''} ${dropReferenceIndex === references.length && index === references.length - 1 ? 'is-drop-after' : ''}`}
                  >
                    <span className="canvas-prompt-ref-chip__thumb">
                      <ReferenceThumb
                        url={reference.url}
                        mediaType={reference.mediaType}
                      />
                    </span>
                    @{reference.alias}
                  </button>
                  {onRemoveReference && (
                    <button
                      type="button"
                      aria-label={`移除 @${reference.alias} 的参考连接`}
                      title={`移除 @${reference.alias}，并断开对应连线`}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                      }}
                      onPointerDown={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                      }}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        hidePreview();
                        onRemoveReference(reference, serializeEditor());
                      }}
                      className="canvas-prompt-ref-chip__remove"
                    >
                      <X size={9} strokeWidth={2.5} />
                    </button>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      )}
      <div
        ref={editorRef}
        contentEditable
        role="textbox"
        aria-label={ariaLabel}
        aria-multiline="true"
        aria-autocomplete="list"
        aria-expanded={query !== null && filteredReferences.length > 0}
        data-placeholder={placeholder}
        suppressContentEditableWarning
        onInput={commitEditorValue}
        onCopy={(event) => {
          const selection = window.getSelection()?.toString();
          const prompt =
            (selection && selection.length > 0
              ? selection
              : serializeEditor()) || value;
          event.preventDefault();
          if (event.clipboardData) {
            writePromptClipboard(
              event.clipboardData,
              prompt,
              references.map((reference) => reference.url),
            );
          }
        }}
        onPaste={(event) => {
          const html = event.clipboardData?.getData('text/html') || '';
          const payload = readPromptClipboardPayload(html);
          const text =
            payload?.prompt ?? event.clipboardData?.getData('text/plain') ?? '';
          if (!text && !payload) return;
          event.preventDefault();
          if (text) {
            const inserted = document.execCommand('insertText', false, text);
            if (!inserted) {
              const editor = editorRef.current;
              if (editor) {
                editor.focus();
                renderValue((serializeEditor() + text).trimStart());
              }
            }
          }
          commitEditorValue();
          if (payload?.imageUrls.length)
            onApplyCopiedImageOrder?.(payload.imageUrls);
        }}
        onClick={updateMentionQuery}
        onKeyUp={(event) => {
          if (
            ['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(
              event.key,
            )
          )
            return;
          updateMentionQuery();
        }}
        onBlur={() => window.setTimeout(() => setQuery(null), 120)}
        onKeyDown={(event) => {
          if (query === null || filteredReferences.length === 0) return;
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const offset = event.key === 'ArrowDown' ? 1 : -1;
            setActiveIndex(
              (current) =>
                (current + offset + filteredReferences.length) %
                filteredReferences.length,
            );
          } else if (event.key === 'Enter' || event.key === 'Tab') {
            event.preventDefault();
            const selectedReference =
              filteredReferences[activeIndex] || filteredReferences[0];
            if (selectedReference) insertMention(selectedReference);
          } else if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            setQuery(null);
          }
        }}
        className="canvas-prompt-mention-editor w-full overflow-y-auto whitespace-pre-wrap text-sm leading-6 outline-none empty:before:pointer-events-none empty:before:content-[attr(data-placeholder)]"
      />
      {query !== null && filteredReferences.length > 0 && (
        <div
          role="listbox"
          aria-label="可引用的参考素材"
          className="absolute z-[110] w-60 overflow-hidden rounded-xl border border-slate-200 bg-white p-1.5 shadow-[0_16px_44px_rgba(15,23,42,0.22)]"
          style={{ left: popupPosition.left, top: popupPosition.top }}
        >
          {filteredReferences.map((reference, index) => (
            <button
              key={`caret-mention-${reference.id}`}
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={(event) => {
                setActiveIndex(index);
                if (!isHoverableMentionMedia(reference.mediaType)) return;
                showPreview(
                  event.currentTarget,
                  reference.url,
                  `@${reference.alias} · ${reference.sourceTitle}`,
                  reference.mediaType === 'video' ? 'video' : 'image',
                );
              }}
              onMouseLeave={hidePreview}
              onClick={() => insertMention(reference)}
              className={`flex h-10 w-full cursor-pointer items-center gap-2 rounded-lg px-2 text-left text-xs outline-none ${index === activeIndex ? 'bg-violet-50 text-violet-800' : 'text-slate-700 hover:bg-slate-50'}`}
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-100 p-0.5">
                <ReferenceThumb
                  url={reference.url}
                  mediaType={reference.mediaType}
                  className="max-h-full max-w-full object-contain"
                />
              </span>
              <span className="font-semibold">@{reference.alias}</span>
              <span className="min-w-0 flex-1 truncate text-[10px] text-slate-400">
                {reference.sourceTitle}
              </span>
            </button>
          ))}
        </div>
      )}
      {referenceMenuOpen &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={referenceMenuRef}
            role="listbox"
            aria-label="已连线的参考素材"
            className={`canvas-prompt-ref-menu ${tone === 'dark' ? 'canvas-prompt-ref-menu--dark' : ''}`}
            style={{
              left: referenceMenuPosition.left,
              top: referenceMenuPosition.top,
            }}
            onMouseEnter={clearReferenceMenuCloseTimer}
            onMouseLeave={scheduleReferenceMenuClose}
          >
            {references.length === 0 ? (
              <p className="canvas-prompt-ref-menu__empty">
                把图片、视频、音频、文档、网页或素材节点连到当前节点后，即可在这里插入引用
              </p>
            ) : (
              references.map((reference) => (
                <button
                  key={`menu-ref-${reference.id}`}
                  type="button"
                  role="option"
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={(event) => {
                    if (!isHoverableMentionMedia(reference.mediaType)) return;
                    showPreview(
                      event.currentTarget,
                      reference.url,
                      `@${reference.alias} · ${reference.sourceTitle}`,
                      reference.mediaType === 'video' ? 'video' : 'image',
                    );
                  }}
                  onMouseLeave={hidePreview}
                  onClick={() => {
                    closeReferenceMenu();
                    appendMention(reference);
                  }}
                  className="canvas-prompt-ref-menu__item"
                >
                  <span className="canvas-prompt-ref-chip__thumb">
                    <ReferenceThumb
                      url={reference.url}
                      mediaType={reference.mediaType}
                    />
                  </span>
                  <span className="canvas-prompt-ref-menu__meta">
                    <strong>@{reference.alias}</strong>
                    <em>{reference.sourceTitle}</em>
                  </span>
                </button>
              ))
            )}
          </div>,
          document.body,
        )}
      {previewNode}
    </div>
  );
};

export default PromptMentionEditor;
