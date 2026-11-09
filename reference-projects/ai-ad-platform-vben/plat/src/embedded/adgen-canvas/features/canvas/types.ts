export type CanvasNodeKind =
  | 'text'
  | 'asset'
  | 'image'
  | 'video'
  | 'video_analysis'
  | 'music'
  | 'tts'
  | 'output';

export type CanvasNodeStatus = 'draft' | 'ready' | 'error';

export type ImageGenerationMode = 'text_to_image' | 'reference_image';

export type VideoGenerationMode =
  | 'text_to_video'
  | 'reference_image'
  | 'reference_video'
  | 'reference_assets'
  | 'first_frame'
  | 'first_last_frame';

export interface CanvasGenerationConfig {
  model?: string;
  count?: number;
  aspectRatio?: string;
  resolution?: string;
  duration?: number;
  extensionCount?: number;
  imageGenerationMode?: ImageGenerationMode;
  videoGenerationMode?: VideoGenerationMode;
}

export interface CanvasNodeResult {
  id: string;
  url: string;
  type: 'image' | 'video' | 'audio' | 'file' | 'link';
  /** 结果来自 MinIO 上传时保存的稳定对象键。 */
  storageKey?: string;
  createdAt: string;
}

export interface CanvasNodeData {
  id: string;
  kind: CanvasNodeKind;
  title: string;
  x: number;
  y: number;
  /** 可选的画布节点尺寸；未设置时使用节点类型的默认尺寸。 */
  width?: number;
  height?: number;
  prompt: string;
  model?: string;
  count?: number;
  aspectRatio?: string;
  resolution?: string;
  duration?: number;
  extensionCount?: number;
  imageGenerationMode?: ImageGenerationMode;
  videoGenerationMode?: VideoGenerationMode;
  textGenerationMode?: 'image' | 'video';
  textImageConfig?: CanvasGenerationConfig;
  textVideoConfig?: CanvasGenerationConfig;
  voiceName?: string;
  voiceStyle?: string;
  speechRate?: 'slow' | 'normal' | 'fast';
  assetType?: 'image' | 'video' | 'audio' | 'file' | 'link';
  assetName?: string;
  /** 素材在 MinIO 中的稳定对象键，文件名仅作为展示与下载名称。 */
  assetStorageKey?: string;
  assetSource?: 'local' | 'cloud';
  officialAssetEnabled?: boolean;
  officialAssetId?: string;
  officialAssetStatus?: 'idle' | 'uploading' | 'active' | 'failed';
  officialAssetError?: string;
  resultAssetType?: 'image' | 'video' | 'audio' | 'file' | 'link';
  resultUrl?: string;
  resultUrls?: string[];
  resultHistory?: CanvasNodeResult[];
  /** 视频分析节点由多模态模型返回的文本结果，可继续连接到生成节点。 */
  analysisResult?: string;
  /** 视频分析完成时冻结的分析提示词，仅用于结果节点下方展示。 */
  sourceGenerationPrompt?: string;
  mediaAspectRatio?: number;
  mediaDisplayScale?: number;
  /** 结果图含真实透明通道（如智能抠图 PNG），画布上用棋盘格展示。 */
  hasTransparentBackground?: boolean;
  /** 宫格切分来源节点。有值时参考图会同时带上自身切图和原图。 */
  gridSplitSourceNodeId?: string;
  /** 参考图 sourceNodeId 顺序。拖动缩略图后写入，生成时按此编号对应 @图片N。 */
  imageReferenceSourceOrder?: string[];
  /** 持久化分组。同一 groupId 的节点共用一个分组框，点击空白处不会解散。 */
  groupId?: string;
  status: CanvasNodeStatus;
}

export interface CanvasEdgeData {
  id: string;
  source: string;
  target: string;
}

export interface CanvasViewport {
  x: number;
  y: number;
  zoom: number;
}

export interface CanvasDraft {
  version: 1;
  title: string;
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
  viewport: CanvasViewport;
  updatedAt: string;
}
