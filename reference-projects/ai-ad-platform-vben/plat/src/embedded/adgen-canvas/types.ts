export enum AssetType {
  IMAGE = 'IMAGE',
  VIDEO = 'VIDEO',
  AUDIO = 'AUDIO',
  TEXT = 'TEXT',
  FILE = 'FILE',
  LINK = 'LINK',
}

export interface UploadedAsset {
  id: string;
  type: AssetType;
  url: string;
  name: string;
  /** MinIO 对象键；与用户可见文件名分离，避免同名素材覆盖。 */
  storageKey?: string;
  file?: File;
  officialAssetUri?: string;
}

export interface TodoItem {
  id: string;
  task: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  description?: string;
}

export interface GenerationRequest {
  type: 'batch' | 'edit' | 'fission';
  assets: UploadedAsset[];
  prompt: string;
  batchCount: number;
  extensionCount?: number; // Veo 视频延长次数 (0-20)
  duration?: number; // 百炼视频目标时长（秒）
  aspectRatio?: string; // 画面比例 (16:9, 9:16, 1:1, etc.)
  imageSize?: string; // 图片画质 (1K, 2K, 4K)
  resolution?: string; // 视频画质 (720p, 1080p, 4k)
  imageModel?: string;
  imageGenerationMode?: 'text_to_image' | 'reference_image';
  videoModel?: string;
  videoGenerationMode?:
    | 'text_to_video'
    | 'reference_image'
    | 'reference_video'
    | 'reference_assets'
    | 'first_frame'
    | 'first_last_frame';
  /** 视频生成点击时由前端预先创建，用于提交阶段的取消请求。 */
  clientTaskId?: string;
  musicModel?: string;
  ttsModel?: string;
  parameters?: Record<string, any>;
}

export interface GeneratedResult {
  id: string;
  type: AssetType;
  /** 可跨页面生命周期恢复的 MinIO/后端流地址；url 可仅用于当前页面预览。 */
  persistentUrl?: string;
  url: string;
  prompt: string;
  createdAt: Date;
  videoData?: {
    operation?: any; // Veo operation object for extension
    extensionCount?: number; // 已延长次数
    videoId?: string; // 后端视频引用ID，用于延长
    aspectRatio?: string; // 视频宽高比，支持 16:9, 9:16 等
    modelName?: string;
    resolution?: string;
    provider?: string;
    providerModel?: string;
    providerVideoUrl?: string;
    duration?: number;
    extensionMode?: string;
    extensionMaxDuration?: number;
    capability?: string;
    /** 已由后端随 MinIO 落盘同步写入的生成历史记录。 */
    historyRecordId?: string;
  };
  audioData?: {
    mimeType?: string;
    modelName?: string;
    text?: string;
    speakerMode?: string;
    voiceName?: string;
    speakerConfigs?: Array<{
      speaker: string;
      voice_name: string;
      voice_style?: string;
    }>;
    voiceStyle?: string;
    speechRate?: string;
  };
}

export interface Clarification {
  id: string;
  question: string;
  options?: string[];
  type: 'text' | 'select' | 'boolean';
  answeredValue?: string;
  category?:
    | 'target'
    | 'platform'
    | 'audience'
    | 'content'
    | 'style'
    | 'reference'
    | 'constraints'; // 问题分类 - 新增 'platform'
}

export interface ClarificationSession {
  round: number; // 第几轮对话
  answers: Record<string, string>; // 所有历史答案
  isComplete: boolean; // 需求是否已经明确
  completenessScore: number; // 需求完整度评分 (0-100)
}

export interface QuickCommand {
  id: string;
  title: string;
  content: string;
  createdAt: Date;
  usageCount: number;
}

export interface Workspace {
  id: string;
  name: string;
  createdAt: Date;
  uploadedAssets: UploadedAsset[];
  generatedResults: GeneratedResult[];
  todos: TodoItem[];
  clarifications: Clarification[];
  userInput: string;
  isPlanning: boolean;
  isGenerating: boolean;
  batchCount: number;
  generationType: 'image' | 'video' | 'music' | 'tts';
  aspectRatio: string;
  videoExtensionCount: number;
  videoDurationSeconds: number;
  clarificationAnswers: Record<string, string>;
  clarificationSession: ClarificationSession;
  isAnalyzingVideo: boolean;
  videoAnalysisProgress: string;
}
