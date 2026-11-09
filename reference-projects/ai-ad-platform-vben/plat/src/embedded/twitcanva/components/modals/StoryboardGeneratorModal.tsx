/** @jsxImportSource react */
/**
 * StoryboardGeneratorModal.tsx
 *
 * Modal overlay for creating AI-powered storyboard scenes.
 * Multi-step workflow: Character Selection → Story Input → Script Review → Generate
 */

import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
} from 'react';
import {
  X,
  ChevronRight,
  ChevronLeft,
  Loader2,
  Film,
  Users,
  PenTool,
  Sparkles,
  Check,
  Edit3,
  Wand2,
  Eye,
  ChevronDown,
} from 'lucide-react';
import type {
  CharacterAsset,
  SceneScript,
  StoryboardState,
} from '../../hooks/useStoryboardGenerator';
import { apiFetch } from '../../runtime';
import { StoryInput } from '../StoryInput';

// ============================================================================
// IMAGE MODELS (Copied from NodeControls.tsx for model selection)
// ============================================================================

const IMAGE_MODELS = [
  { id: 'gpt-image-1.5', name: 'GPT Image 1.5', provider: 'openai' },
  { id: 'gemini-pro', name: 'Nano Banana Pro', provider: 'google' },
  { id: 'kling-v1-5', name: 'Kling V1.5', provider: 'kling' },
  { id: 'kling-v2-1', name: 'Kling V2.1', provider: 'kling' },
];

// ============================================================================
// TYPES
// ============================================================================

interface StoryboardGeneratorModalProps {
  isOpen: boolean;
  onClose: () => void;
  state: StoryboardState;
  onSetStep: (step: StoryboardState['step']) => void;
  onToggleCharacter: (character: CharacterAsset) => void;
  onSetSceneCount: (count: number) => void;
  onSetStory: (story: string) => void;
  onUpdateScript: (index: number, updates: Partial<SceneScript>) => void;
  onGenerateScripts: () => Promise<void>;
  onBrainstormStory: () => Promise<void>;
  onOptimizeStory: () => Promise<void>;
  onGenerateComposite: () => Promise<void>;
  onRegenerateComposite: () => Promise<void>;
  onCreateNodes: () => void;
}

// ============================================================================
// COMPONENT
// ============================================================================

export const StoryboardGeneratorModal: React.FC<
  StoryboardGeneratorModalProps
> = ({
  isOpen,
  onClose,
  state,
  onSetStep,
  onToggleCharacter,
  onSetSceneCount,
  onSetStory,
  onUpdateScript,
  onGenerateScripts,
  onBrainstormStory,
  onOptimizeStory,
  onGenerateComposite,
  onRegenerateComposite,
  onCreateNodes,
}) => {
  const [characterAssets, setCharacterAssets] = useState<
    (CharacterAsset & { category: string })[]
  >([]);
  const [isLoadingAssets, setIsLoadingAssets] = useState(false);
  const [editingScriptIndex, setEditingScriptIndex] = useState<number | null>(
    null,
  );
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [isCategoryDropdownOpen, setIsCategoryDropdownOpen] = useState(false);

  // Mention picker state
  const [showMentionPicker, setShowMentionPicker] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);
  const [mentionStartPos, setMentionStartPos] = useState(0);
  const textareaRef = useRef<HTMLDivElement>(null);

  // Step definitions for progress bar
  const stepDefinitions = [
    { id: 'characters', label: 'Characters', icon: Users },
    { id: 'story', label: 'Story', icon: PenTool },
    { id: 'scripts', label: 'Scripts', icon: Film },
    { id: 'preview', label: 'Preview', icon: Eye },
    { id: 'generate', label: 'Generate', icon: Sparkles },
  ];

  const currentStepIndex = stepDefinitions.findIndex(
    (s) => s.id === state.step,
  );

  // Auto-generate preview when entering preview step
  useEffect(() => {
    if (
      state.step === 'preview' &&
      !state.compositeImageUrl &&
      !state.isGeneratingPreview
    ) {
      onGenerateComposite();
    }
  }, [
    state.step,
    state.compositeImageUrl,
    state.isGeneratingPreview,
    onGenerateComposite,
  ]);

  // Fetch character assets from library
  useEffect(() => {
    if (!isOpen) return;

    const fetchAssets = async () => {
      setIsLoadingAssets(true);
      try {
        const response = await apiFetch('/api/library');
        if (response.ok) {
          const assets = await response.json();
          // Filter to show all image assets and include category info
          const imageAssets = assets
            .filter((a: any) => a.type === 'image')
            .map((a: any) => ({
              id: a.id,
              name: a.name,
              url: a.url,
              description: a.description || '',
              category: a.category || 'Others',
            }));
          setCharacterAssets(imageAssets);
          setSelectedCategory('All');
        }
      } catch (error) {
        console.error('[StoryboardModal] Failed to fetch assets:', error);
      } finally {
        setIsLoadingAssets(false);
      }
    };

    fetchAssets();
  }, [isOpen]);

  // Get unique categories from loaded assets (exclude Sound Effect)
  const availableCategories = useMemo(() => {
    const categories = new Set(characterAssets.map((a) => a.category));
    categories.delete('Sound Effect'); // Audio files can't be used as image references
    return ['All', ...Array.from(categories).sort()];
  }, [characterAssets]);

  // Filter assets by selected category
  const filteredAssets = useMemo(() => {
    if (selectedCategory === 'All') return characterAssets;
    return characterAssets.filter((a) => a.category === selectedCategory);
  }, [characterAssets, selectedCategory]);

  // Filter mention suggestions based on current filter text
  const mentionSuggestions = useMemo(() => {
    if (!showMentionPicker || state.selectedCharacters.length === 0) return [];
    const filter = mentionFilter.toLowerCase();
    return state.selectedCharacters.filter((c) =>
      c.name.toLowerCase().includes(filter),
    );
  }, [showMentionPicker, mentionFilter, state.selectedCharacters]);

  // Handle story change with mention detection
  const handleStoryChange = useCallback(
    (value: string) => {
      // Calculate cursor position for mention detection
      let cursorPos = value.length;
      if (textareaRef.current) {
        const sel = window.getSelection();
        if (
          sel &&
          sel.rangeCount > 0 &&
          textareaRef.current.contains(sel.anchorNode)
        ) {
          try {
            const range = sel.getRangeAt(0);
            const preCaretRange = range.cloneRange();
            preCaretRange.selectNodeContents(textareaRef.current);
            preCaretRange.setEnd(range.endContainer, range.endOffset);
            cursorPos = preCaretRange.toString().length;
          } catch (e) {
            console.warn('Failed to calculate cursor position', e);
          }
        }
      }

      const textBeforeCursor = value.substring(0, cursorPos);
      const atIndex = textBeforeCursor.lastIndexOf('@');

      if (atIndex !== -1) {
        // Check if @ is at start or preceded by space/newline
        const charBefore = textBeforeCursor[atIndex - 1];
        if (atIndex === 0 || charBefore === ' ' || charBefore === '\n') {
          const filterText = textBeforeCursor.substring(atIndex + 1);
          // Only show if no space after @ (user is still typing the mention)
          if (!filterText.includes(' ')) {
            setShowMentionPicker(true);
            setMentionFilter(filterText);
            setMentionStartPos(atIndex);
            setMentionIndex(0);
          } else {
            setShowMentionPicker(false);
          }
        } else {
          setShowMentionPicker(false);
        }
      } else {
        setShowMentionPicker(false);
      }

      onSetStory(value);
    },
    [onSetStory],
  );

  // Insert a mention at the current position
  const insertMention = useCallback(
    (asset: CharacterAsset) => {
      const value = state.story;
      const beforeMention = value.substring(0, mentionStartPos);
      const afterMention = value.substring(
        mentionStartPos + mentionFilter.length + 1,
      ); // +1 for @
      const newValue = beforeMention + '@' + asset.name + ' ' + afterMention;
      onSetStory(newValue);
      setShowMentionPicker(false);
      setMentionFilter('');

      // Focus input after mention
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          // Move cursor to end logic handled by StoryInput fallback or browser default
        }
      }, 0);
    },
    [state.story, mentionStartPos, mentionFilter, onSetStory],
  );

  // Handle keyboard navigation for mention picker
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showMentionPicker || mentionSuggestions.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionIndex((prev) => (prev + 1) % mentionSuggestions.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionIndex(
          (prev) =>
            (prev - 1 + mentionSuggestions.length) % mentionSuggestions.length,
        );
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        insertMention(mentionSuggestions[mentionIndex]);
      } else if (e.key === 'Escape') {
        setShowMentionPicker(false);
      }
    },
    [showMentionPicker, mentionSuggestions, mentionIndex, insertMention],
  );

  if (!isOpen) return null;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="app-modal-mask absolute inset-0" />

      {/* Modal */}
      <div className="relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-neutral-800 bg-[#1a1a1a] shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-800/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-lg shadow-violet-500/25">
              <Film size={20} className="text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                Storyboard Generator
              </h2>
              <p className="text-xs text-neutral-500">Create scenes with AI</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="group rounded-lg p-2 transition-all duration-200 hover:bg-neutral-800/80"
          >
            <X
              size={18}
              className="text-neutral-500 transition-colors group-hover:text-neutral-300"
            />
          </button>
        </div>

        {/* Step Indicator - Redesigned with connected dots */}
        <div className="border-b border-neutral-800/50 px-6 py-4">
          <div className="relative flex items-center justify-between">
            {/* Progress line background */}
            <div className="absolute left-0 right-0 top-3 h-0.5 bg-neutral-800" />
            {/* Progress line filled */}
            <div
              className="absolute left-0 top-3 h-0.5 bg-gradient-to-r from-violet-500 to-purple-500 transition-all duration-500 ease-out"
              style={{
                width: `${(currentStepIndex / (stepDefinitions.length - 1)) * 100}%`,
              }}
            />

            {stepDefinitions.map((step, index) => {
              // Determine if step is accessible
              let isAccessible = false;
              if (index <= currentStepIndex) isAccessible = true;
              else if (step.id === 'scripts' && state.scripts.length > 0)
                isAccessible = true;
              else if (
                (step.id === 'preview' || step.id === 'generate') &&
                state.compositeImageUrl
              )
                isAccessible = true;

              const isCompleted = isAccessible && index < currentStepIndex;
              const isCurrent = index === currentStepIndex;

              return (
                <button
                  key={step.id}
                  onClick={() =>
                    isAccessible &&
                    onSetStep(step.id as StoryboardState['step'])
                  }
                  disabled={!isAccessible}
                  className="group relative z-10 flex flex-col items-center gap-1.5"
                >
                  {/* Step dot */}
                  <div
                    className={`flex h-6 w-6 items-center justify-center rounded-full transition-all duration-300 ${
                      isCurrent
                        ? 'scale-110 bg-violet-500 text-white shadow-lg shadow-violet-500/40'
                        : isCompleted
                          ? 'bg-emerald-500 text-white'
                          : isAccessible
                            ? 'cursor-pointer bg-neutral-700 text-neutral-300 hover:bg-neutral-600'
                            : 'bg-neutral-800 text-neutral-600'
                    }`}
                  >
                    {isCompleted ? (
                      <Check size={12} strokeWidth={3} />
                    ) : (
                      <step.icon size={12} />
                    )}
                  </div>
                  {/* Step label */}
                  <span
                    className={`text-[10px] font-medium transition-colors duration-200 ${
                      isCurrent
                        ? 'text-violet-400'
                        : isCompleted
                          ? 'text-emerald-400'
                          : isAccessible
                            ? 'text-neutral-400 group-hover:text-neutral-300'
                            : 'text-neutral-600'
                    }`}
                  >
                    {step.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Characters Step Header - Fixed outside scroll area */}
        {state.step === 'characters' && (
          <div className="border-b border-neutral-800/30 px-6 pb-4 pt-6">
            <h3 className="mb-2 font-medium text-white">
              Select Reference Images
            </h3>
            <p className="mb-4 text-sm text-neutral-400">
              Choose up to 3 reference images from your Asset Library to guide
              the AI.
            </p>

            {/* Category Dropdown */}
            {characterAssets.length > 0 && (
              <div className="relative">
                <button
                  onClick={() =>
                    setIsCategoryDropdownOpen(!isCategoryDropdownOpen)
                  }
                  className="flex w-full items-center justify-between rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-2.5 text-sm text-white transition-colors hover:border-neutral-600"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-neutral-400">Category:</span>
                    <span className="font-medium">{selectedCategory}</span>
                    <span className="text-xs text-neutral-500">
                      ({filteredAssets.length} items)
                    </span>
                  </span>
                  <ChevronDown
                    size={16}
                    className={`text-neutral-400 transition-transform duration-200 ${isCategoryDropdownOpen ? 'rotate-180' : ''}`}
                  />
                </button>

                {isCategoryDropdownOpen && (
                  <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 shadow-xl">
                    {availableCategories.map((category) => (
                      <button
                        key={category}
                        onClick={() => {
                          setSelectedCategory(category);
                          setIsCategoryDropdownOpen(false);
                        }}
                        className={`w-full px-4 py-2.5 text-left text-sm transition-colors ${
                          selectedCategory === category
                            ? 'bg-violet-600 text-white'
                            : 'text-neutral-300 hover:bg-neutral-800'
                        }`}
                      >
                        <span className="flex items-center justify-between">
                          <span>{category}</span>
                          <span className="text-xs opacity-60">
                            {category === 'All'
                              ? characterAssets.length
                              : characterAssets.filter(
                                  (a) => a.category === category,
                                ).length}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Error Message */}
          {state.error && (
            <div className="mb-4 rounded-lg border border-red-800 bg-red-900/20 p-3 text-sm text-red-400">
              {state.error}
            </div>
          )}

          {/* Step 1: Character Selection - Grid Only */}
          {state.step === 'characters' && (
            <div>
              {isLoadingAssets ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-purple-400" />
                </div>
              ) : characterAssets.length === 0 ? (
                <div className="py-12 text-center text-neutral-500">
                  <Users size={48} className="mx-auto mb-3 opacity-50" />
                  <p>No images found in Asset Library</p>
                  <p className="mt-1 text-xs">
                    Add image assets to your library to use them as character
                    references
                  </p>
                </div>
              ) : filteredAssets.length === 0 ? (
                <div className="py-12 text-center text-neutral-500">
                  <Users size={48} className="mx-auto mb-3 opacity-50" />
                  <p>No images in "{selectedCategory}" category</p>
                  <p className="mt-1 text-xs">
                    Try selecting a different category
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-4">
                  {filteredAssets.map((character) => {
                    const isSelected = state.selectedCharacters.some(
                      (c) => c.id === character.id,
                    );
                    return (
                      <button
                        key={character.id}
                        onClick={() => onToggleCharacter(character)}
                        className={`group relative aspect-square cursor-pointer overflow-hidden rounded-xl transition-all duration-300 ${
                          isSelected
                            ? 'scale-[1.02] ring-2 ring-violet-500 ring-offset-2 ring-offset-[#1a1a1a]'
                            : 'hover:-translate-y-0.5 hover:scale-[1.02]'
                        }`}
                      >
                        {/* Image */}
                        <img
                          src={character.url}
                          alt={character.name}
                          className={`h-full w-full object-cover transition-all duration-300 ${
                            isSelected
                              ? 'brightness-100'
                              : 'brightness-90 group-hover:brightness-100'
                          }`}
                        />

                        {/* Frosted glass name label */}
                        <div className="absolute inset-x-0 bottom-0 border-t border-white/10 bg-black/40 p-2.5 backdrop-blur-md">
                          <p className="truncate text-xs font-medium text-white">
                            {character.name}
                          </p>
                        </div>

                        {/* Selection indicator */}
                        <div
                          className={`absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full transition-all duration-300 ${
                            isSelected
                              ? 'scale-100 bg-violet-500 opacity-100'
                              : 'scale-90 border border-white/20 bg-black/40 opacity-0 backdrop-blur-sm group-hover:opacity-100'
                          }`}
                        >
                          <Check
                            size={12}
                            className="text-white"
                            strokeWidth={3}
                          />
                        </div>

                        {/* Hover overlay */}
                        <div
                          className={`pointer-events-none absolute inset-0 transition-opacity duration-300 ${
                            isSelected
                              ? 'bg-violet-500/10 opacity-100'
                              : 'bg-white/5 opacity-0 group-hover:opacity-100'
                          }`}
                        />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Story Input */}
          {state.step === 'story' && (
            <div>
              <h3 className="mb-2 font-medium text-white">Write Your Story</h3>
              <p className="mb-4 text-sm text-neutral-400">
                Describe the story you want to visualize. AI will break it into{' '}
                {state.sceneCount} scenes.
              </p>

              {/* Selected Reference Images - clickable to insert @ mention */}
              {state.selectedCharacters.length > 0 && (
                <div className="mb-4 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
                  <p className="mb-2 text-xs text-neutral-400">
                    Selected references — click to insert @mention in story:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {state.selectedCharacters.map((asset) => (
                      <button
                        key={asset.id}
                        onClick={() => {
                          const mention = `@${asset.name}`;
                          onSetStory(
                            state.story +
                              (state.story.endsWith(' ') || state.story === ''
                                ? ''
                                : ' ') +
                              mention +
                              ' ',
                          );
                        }}
                        className="group flex items-center gap-2 rounded-lg bg-neutral-800 px-2 py-1.5 transition-colors hover:bg-neutral-700"
                      >
                        <img
                          src={asset.url}
                          alt={asset.name}
                          className="h-6 w-6 rounded object-cover"
                        />
                        <span className="text-xs text-neutral-300 group-hover:text-white">
                          @{asset.name}
                        </span>
                        <span className="rounded bg-neutral-900 px-1.5 py-0.5 text-[10px] text-neutral-500">
                          {asset.category || 'Others'}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Scene Count Slider */}
              <div className="mb-4">
                <label className="mb-2 block text-sm text-neutral-300">
                  Number of Scenes:{' '}
                  <span className="font-medium text-purple-400">
                    {state.sceneCount}
                  </span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={state.sceneCount}
                  onChange={(e) => onSetSceneCount(parseInt(e.target.value))}
                  className="w-full accent-purple-500"
                />
                <div className="mt-1 flex justify-between text-xs text-neutral-500">
                  <span>1</span>
                  <span>10</span>
                </div>
              </div>

              {/* Brainstorm with AI Button */}
              <button
                onClick={onBrainstormStory}
                disabled={state.isBrainstorming}
                className="group mb-3 flex items-center gap-2 text-sm text-purple-400 transition-colors hover:text-purple-300"
              >
                {state.isBrainstorming ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Brainstorming...</span>
                  </>
                ) : (
                  <>
                    <Wand2
                      size={14}
                      className="transition-transform group-hover:rotate-12"
                    />
                    <span className="underline decoration-dashed underline-offset-2">
                      Brainstorm with AI
                    </span>
                    <span className="text-xs text-neutral-500">
                      (let AI write a story for you)
                    </span>
                  </>
                )}
              </button>

              {/* Story Textarea with Mention Picker */}
              <div className="relative">
                <StoryInput
                  inputRef={textareaRef}
                  value={state.story}
                  onChange={handleStoryChange}
                  onKeyDown={handleKeyDown}
                  onBlur={() => {
                    // Delay closing to allow click on mention
                    setTimeout(() => setShowMentionPicker(false), 150);
                  }}
                  placeholder={
                    state.selectedCharacters.length > 0
                      ? `Type @ to mention assets like @${state.selectedCharacters[0]?.name}...`
                      : 'Once upon a time, in a magical forest...'
                  }
                  assets={state.selectedCharacters}
                  className="min-h-[12rem]"
                />

                {/* Mention Picker Dropdown */}
                {showMentionPicker && mentionSuggestions.length > 0 && (
                  <div className="absolute left-4 top-10 z-50 w-64 overflow-hidden rounded-lg border border-neutral-700 bg-neutral-900 shadow-2xl">
                    <div className="border-b border-neutral-700/50 bg-neutral-900 px-3 py-1 text-[10px] text-neutral-500">
                      Select reference (↑↓ to navigate, Enter to select)
                    </div>
                    <div className="max-h-48 overflow-y-auto">
                      {mentionSuggestions.map((asset, index) => (
                        <button
                          key={asset.id}
                          onClick={() => insertMention(asset)}
                          onMouseEnter={() => setMentionIndex(index)}
                          className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                            index === mentionIndex
                              ? 'bg-purple-600 text-white'
                              : 'text-neutral-300 hover:bg-neutral-800'
                          }`}
                        >
                          <img
                            src={asset.url}
                            alt={asset.name}
                            className="h-7 w-7 flex-shrink-0 rounded object-cover"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium">
                              @{asset.name}
                            </div>
                            <div className="text-[10px] text-neutral-400">
                              {asset.category || 'Others'}
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="mt-2 flex items-start justify-between">
                <p className="text-xs text-neutral-500">
                  Tip: Be descriptive about scenes, actions, and emotions for
                  better results.
                </p>
                <button
                  onClick={onOptimizeStory}
                  disabled={state.isOptimizing || !state.story.trim()}
                  className={`flex items-center gap-1.5 text-xs transition-colors ${
                    state.story.trim()
                      ? 'text-purple-400 hover:text-purple-300'
                      : 'cursor-not-allowed text-neutral-600'
                  }`}
                >
                  {state.isOptimizing ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Wand2 size={12} />
                  )}
                  Optimize with AI
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Script Review */}
          {state.step === 'scripts' && (
            <div>
              <h3 className="mb-2 font-medium text-white">
                Review & Edit Scripts
              </h3>
              <p className="mb-4 text-sm text-neutral-400">
                AI generated {state.scripts.length} scene scripts. Click to
                edit.
              </p>

              <div className="space-y-3">
                {state.isGenerating
                  ? // SKELETON LOADERS
                    Array.from({ length: state.sceneCount }).map((_, i) => (
                      <div
                        key={i}
                        className="relative overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 p-4"
                      >
                        {/* Shimmer Effect */}
                        <div className="absolute inset-0 animate-[pulse_2s_infinite] bg-gradient-to-r from-transparent via-purple-500/5 to-transparent" />

                        <div className="mb-3 flex items-center justify-between">
                          <div className="h-4 w-20 animate-pulse rounded bg-neutral-800/50" />
                          <div className="flex gap-2">
                            <div className="h-4 w-16 animate-pulse rounded bg-neutral-800/50" />
                            <div className="h-4 w-16 animate-pulse rounded bg-neutral-800/50" />
                          </div>
                        </div>

                        <div className="mb-2 space-y-2">
                          <div className="h-3 w-full animate-pulse rounded bg-neutral-800/50" />
                          <div className="h-3 w-5/6 animate-pulse rounded bg-neutral-800/50" />
                          <div className="h-3 w-4/6 animate-pulse rounded bg-neutral-800/50" />
                        </div>

                        <div className="flex items-center justify-center gap-2 pt-2 text-xs font-medium text-purple-400/50">
                          <Loader2 size={12} className="animate-spin" />
                          Creating Scene {i + 1}...
                        </div>
                      </div>
                    ))
                  : // ACTUAL CONTENTS
                    state.scripts.map((script, index) => (
                      <div
                        key={index}
                        className="rounded-xl border border-neutral-700 bg-neutral-900 p-4"
                      >
                        <div className="mb-2 flex items-center justify-between">
                          <span className="text-sm font-medium text-purple-400">
                            Scene {script.sceneNumber}
                          </span>
                          <div className="flex items-center gap-2 text-xs text-neutral-500">
                            <span className="rounded bg-neutral-800 px-2 py-0.5">
                              {script.cameraAngle}
                            </span>
                            <span className="rounded bg-neutral-800 px-2 py-0.5">
                              {script.mood}
                            </span>
                          </div>
                        </div>

                        {editingScriptIndex === index ? (
                          <StoryInput
                            value={script.description}
                            onChange={(val) =>
                              onUpdateScript(index, { description: val })
                            }
                            onBlur={() => setEditingScriptIndex(null)}
                            assets={state.selectedCharacters}
                            className="min-h-[5rem] w-full rounded-lg border border-neutral-600 bg-neutral-800 p-2"
                            // autoFocus is trickier with contentEditable, handled by ref usually but let's test
                          />
                        ) : (
                          <div
                            onClick={() => setEditingScriptIndex(index)}
                            className="group relative -m-2 cursor-pointer rounded-lg p-2 transition-colors hover:bg-neutral-800"
                          >
                            <StoryInput
                              value={script.description}
                              onChange={() => {}}
                              assets={state.selectedCharacters}
                              readOnly
                              className="h-auto min-h-0 overflow-visible border-none bg-transparent p-0"
                            />
                            <Edit3
                              size={12}
                              className="absolute right-2 top-2 text-neutral-500 opacity-0 transition-opacity group-hover:opacity-100"
                            />
                          </div>
                        )}
                      </div>
                    ))}
              </div>
            </div>
          )}

          {/* STEP 4: PREVIEW COMPOSITE */}
          {state.step === 'preview' && (
            <div className="flex h-full flex-col">
              <h3 className="mb-2 font-medium text-white">
                Preview Storyboard
              </h3>
              <p className="mb-4 text-sm text-neutral-400">
                Review the composite storyboard. This image will be used as a
                reference to generate individual scenes with consistent
                characters and environments.
              </p>

              <div className="group relative flex flex-1 items-center justify-center overflow-hidden rounded-xl border border-neutral-700 bg-neutral-900 p-4">
                {state.isGeneratingPreview ? (
                  <div className="text-center">
                    <Loader2
                      size={48}
                      className="mx-auto mb-4 animate-spin text-purple-500"
                    />
                    <p className="font-medium text-white">
                      Generating Preview...
                    </p>
                    <p className="mt-2 text-sm text-neutral-400">
                      Creating a cohesive storyboard with Nano Banana Pro
                    </p>
                  </div>
                ) : state.compositeImageUrl ? (
                  <div className="relative flex h-full w-full items-center justify-center">
                    <img
                      src={state.compositeImageUrl}
                      alt="Storyboard Composite"
                      className="max-h-full max-w-full rounded object-contain shadow-lg"
                    />
                    <div className="absolute right-4 top-4 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={onRegenerateComposite}
                        className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/70 px-3 py-1.5 text-xs font-medium text-white backdrop-blur-sm hover:bg-black/90"
                      >
                        <Wand2 size={12} />
                        Regenerate
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-neutral-500">
                    <p>No preview available</p>
                    <button
                      onClick={onGenerateComposite}
                      className="mt-4 text-sm text-purple-400 underline hover:text-purple-300"
                    >
                      Generate Preview
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 5: GENERATE (Summary now, since model selection is removed) */}
          {state.step === 'generate' && (
            <div>
              <h3 className="mb-2 font-medium text-white">Ready to Generate</h3>
              <p className="mb-4 text-sm text-neutral-400">
                Determine the final output. The individual scenes will be
                extracted from your preview image.
              </p>

              <div className="rounded-xl border border-neutral-700 bg-neutral-900 p-4">
                <h4 className="mb-2 text-sm font-medium text-white">Summary</h4>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="text-neutral-400">Characters:</div>
                  <div className="text-white">
                    {state.selectedCharacters.length > 0
                      ? state.selectedCharacters.map((c) => c.name).join(', ')
                      : 'None selected'}
                  </div>
                  <div className="text-neutral-400">Scenes:</div>
                  <div className="text-white">{state.scripts.length}</div>
                  <div className="text-neutral-400">Model:</div>
                  <div className="text-white">Nano Banana Pro</div>
                  <div className="text-neutral-400">Preview:</div>
                  <div className="text-white">
                    {state.compositeImageUrl ? 'Generated' : 'Not available'}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-neutral-800 px-6 py-4">
          {/* Back Button */}
          <button
            onClick={() => {
              if (state.step === 'story') onSetStep('characters');
              else if (state.step === 'scripts') onSetStep('story');
              else if (state.step === 'preview') onSetStep('scripts');
              else if (state.step === 'generate') onSetStep('preview');
            }}
            disabled={state.step === 'characters'}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm transition-colors ${
              state.step === 'characters'
                ? 'cursor-not-allowed text-neutral-600'
                : 'text-neutral-300 hover:bg-neutral-800'
            }`}
          >
            <ChevronLeft size={16} />
            Back
          </button>

          {/* Selected Characters Count - shown in footer for characters step */}
          {state.step === 'characters' && (
            <p className="text-xs text-neutral-500">
              Selected: {state.selectedCharacters.length}/3 images (optional)
            </p>
          )}

          {/* Next/Generate Button */}
          {state.step === 'characters' && (
            <button
              onClick={() => onSetStep('story')}
              className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-violet-600/25 transition-all duration-200 hover:bg-violet-500 hover:shadow-violet-500/40"
            >
              Next
              <ChevronRight size={16} />
            </button>
          )}

          {state.step === 'story' && (
            <button
              onClick={onGenerateScripts}
              disabled={state.isGenerating || !state.story.trim()}
              className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all duration-200 ${
                state.isGenerating || !state.story.trim()
                  ? 'cursor-not-allowed bg-neutral-800 text-neutral-500'
                  : 'bg-violet-600 text-white shadow-lg shadow-violet-600/25 hover:bg-violet-500 hover:shadow-violet-500/40'
              }`}
            >
              {state.isGenerating ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Generating Scripts...
                </>
              ) : (
                <>
                  <Sparkles size={16} />
                  Generate Scripts
                </>
              )}
            </button>
          )}

          {state.step === 'scripts' && (
            <button
              onClick={() => {
                if (state.compositeImageUrl) {
                  onRegenerateComposite();
                } else {
                  onSetStep('preview');
                }
              }}
              disabled={state.isGeneratingPreview}
              className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all duration-200 ${
                state.isGeneratingPreview
                  ? 'cursor-not-allowed bg-neutral-800 text-neutral-500'
                  : 'bg-violet-600 text-white shadow-lg shadow-violet-600/25 hover:bg-violet-500 hover:shadow-violet-500/40'
              }`}
            >
              {state.isGeneratingPreview ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Generating...
                </>
              ) : state.compositeImageUrl ? (
                <>
                  <Sparkles size={16} />
                  Regenerate Preview
                </>
              ) : (
                <>
                  Next <ChevronRight size={16} />
                </>
              )}
            </button>
          )}

          {state.step === 'preview' && (
            <button
              onClick={() => onSetStep('generate')}
              disabled={!state.compositeImageUrl || state.isGeneratingPreview}
              className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all duration-200 ${
                !state.compositeImageUrl || state.isGeneratingPreview
                  ? 'cursor-not-allowed bg-neutral-800 text-neutral-500'
                  : 'bg-violet-600 text-white shadow-lg shadow-violet-600/25 hover:bg-violet-500 hover:shadow-violet-500/40'
              }`}
            >
              Next <ChevronRight size={16} />
            </button>
          )}

          {state.step === 'generate' && (
            <button
              onClick={onCreateNodes}
              className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-violet-600/25 transition-all duration-200 hover:bg-violet-500 hover:shadow-violet-500/40"
            >
              <Film size={16} />
              Create Storyboard
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
