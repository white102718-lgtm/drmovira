export const DEFAULT_MEDIA_GENERATION_CONFIG = {
  model_catalog: {
    'veo-3.1-generate-preview': {
      provider: 'gemini_proxy',
      provider_model: 'veo-3.1-generate-preview',
      category: 'video',
      label: 'Veo 3.1 标准',
      description: '质量优先',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
        'video_extension',
      ],
      supported_resolutions: ['720p', '1080p', '4k'],
      supports_extension: true,
      extension_mode: 'veo_iterations',
      duration_parameter_enabled: false,
      max_duration_seconds: null,
      pricing: {
        '720p': 0.4,
        '1080p': 0.4,
        '4k': 0.6,
      },
    },
    'veo-3.1-fast-generate-preview': {
      provider: 'gemini_proxy',
      provider_model: 'veo-3.1-fast-generate-preview',
      category: 'video',
      label: 'Veo 3.1 Fast',
      description: '默认，性价比最高',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
        'video_extension',
      ],
      supported_resolutions: ['720p', '1080p', '4k'],
      supports_extension: true,
      extension_mode: 'veo_iterations',
      duration_parameter_enabled: false,
      max_duration_seconds: null,
      pricing: {
        '720p': 0.15,
        '1080p': 0.15,
        '4k': 0.35,
      },
    },
    'veo-3.1-lite-generate-preview': {
      provider: 'gemini_proxy',
      provider_model: 'veo-3.1-lite-generate-preview',
      category: 'video',
      label: 'Veo 3.1 Lite',
      description: '最低成本，不支持延长',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
      ],
      supported_resolutions: ['720p', '1080p'],
      supports_extension: false,
      extension_mode: 'none',
      duration_parameter_enabled: false,
      max_duration_seconds: 8,
      pricing: {
        '720p': 0.05,
        '1080p': 0.08,
      },
    },
    'lyria-3-clip-preview': {
      category: 'music',
      label: 'Lyria 3 Clip',
      description: '固定 30 秒，适合短音乐片段、loop、预览',
      supports_extension: false,
      max_duration_seconds: 30,
      output_formats: ['mp3'],
      pricing: {},
    },
    'lyria-3-pro-preview': {
      category: 'music',
      label: 'Lyria 3 Pro',
      description: '适合完整歌曲，可通过提示词控制时长与结构',
      supports_extension: false,
      max_duration_seconds: null,
      output_formats: ['mp3', 'wav'],
      pricing: {},
    },
    'lyria-realtime-exp': {
      category: 'music_realtime',
      label: 'Lyria RealTime Experimental',
      description: '实时流式音乐生成，实验版',
      supports_extension: false,
      max_duration_seconds: null,
      output_formats: ['stream'],
      pricing: {},
    },
    'gemini-3.1-flash-image-preview': {
      provider: 'gemini_proxy',
      provider_model: 'gemini-3.1-flash-image-preview',
      category: 'image',
      label: 'Nano Banana 2',
      description: '高吞吐图片生成与编辑',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K', '4K'],
      pricing: {},
    },
    'gemini-3-pro-image-preview': {
      provider: 'gemini_proxy',
      provider_model: 'gemini-3-pro-image-preview',
      category: 'image',
      label: 'Nano Banana Pro',
      description: '高质量图片生成与编辑',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K', '4K'],
      pricing: {},
    },
    'gemini-2.5-flash-image': {
      provider: 'gemini_proxy',
      provider_model: 'gemini-2.5-flash-image',
      category: 'image',
      label: 'Nano Banana',
      description: '快速创意工作流图片模型',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K'],
      pricing: {},
    },
    'gpt-image-2': {
      provider: 'openai',
      provider_model: 'gpt-image-2',
      category: 'image',
      label: 'GPT Image 2',
      description: 'OpenAI 高质量图片生成与多参考图编辑',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K', '4K'],
      supported_aspect_ratios: ['1:1', '16:9', '9:16'],
      size_presets: {
        '1K': {
          '1:1': '1024x1024',
          '16:9': '1536x1024',
          '9:16': '1024x1536',
        },
        '2K': {
          '1:1': '2048x2048',
          '16:9': '2048x1152',
          '9:16': '1152x2048',
        },
        '4K': {
          '1:1': '2880x2880',
          '16:9': '3840x2160',
          '9:16': '2160x3840',
        },
      },
      pricing: {},
    },
    'gemini-3-flash-preview': {
      provider: 'gemini_proxy',
      provider_model: 'gemini-3-flash-preview',
      category: 'chat',
      label: 'Gemini 3 Flash',
      description: '快速画布对话与分析',
      capabilities: ['chat'],
      pricing: { input: 0.5, output: 3 },
    },
    'gemini-3.1-pro-preview': {
      provider: 'gemini_proxy',
      provider_model: 'gemini-3.1-pro-preview',
      category: 'chat',
      label: 'Gemini 3.1 Pro',
      description: '高质量画布对话与分析',
      capabilities: ['chat'],
      pricing: {},
    },
    'qwen-vl-plus': {
      provider: 'qwen',
      provider_model: 'qwen-vl-plus',
      category: 'chat',
      label: 'Qwen VL Plus',
      description: '支持画布截图理解的千问视觉模型',
      capabilities: ['chat', 'vision'],
      pricing: { currency: 'CNY', input: 0.8, output: 2 },
    },
    'qwen-vl-max': {
      provider: 'qwen',
      provider_model: 'qwen-vl-max',
      category: 'chat',
      label: 'Qwen VL Max',
      description: '高质量画布截图理解的千问视觉模型',
      capabilities: ['chat', 'vision'],
      pricing: { currency: 'CNY', input: 1.6, output: 4 },
    },
    'qwen-plus': {
      provider: 'qwen',
      provider_model: 'qwen-plus',
      category: 'chat',
      label: 'Qwen Plus',
      description: '通用千问对话模型',
      capabilities: ['chat'],
      pricing: { currency: 'CNY', input: 0.8, output: 2 },
    },
    'qwen-max': {
      provider: 'qwen',
      provider_model: 'qwen-max',
      category: 'chat',
      label: 'Qwen Max',
      description: '高质量千问对话模型',
      capabilities: ['chat'],
      pricing: { currency: 'CNY', input: 2.4, output: 9.6 },
    },
    'wan2.6-image': {
      provider: 'bailian',
      provider_model: 'wan2.6-image',
      category: 'image',
      label: '万相 2.6 图片',
      description: '阿里云百炼万相图片生成与编辑',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K'],
      pricing: {},
    },
    'wan2.7-image-pro': {
      provider: 'bailian',
      provider_model: 'wan2.7-image-pro',
      category: 'image',
      label: '万相 2.7 Image Pro',
      description: '阿里云百炼万相 2.7 图片生成与编辑',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K'],
      pricing: {},
    },
    'seedream-5-0-lite-260128': {
      provider: 'byteplus',
      provider_model: 'seedream-5-0-lite-260128',
      category: 'image',
      label: 'Seedream 5.0 Lite',
      description: 'BytePlus 新加坡区智能图片生成与编辑，支持 2K、3K 输出',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['2K', '3K'],
      supported_aspect_ratios: [
        '1:1',
        '16:9',
        '9:16',
        '4:3',
        '3:4',
        '3:2',
        '2:3',
        '21:9',
      ],
      pricing: {},
    },
    'seedream-4-5-251128': {
      provider: 'byteplus',
      provider_model: 'seedream-4-5-251128',
      category: 'image',
      label: 'Seedream 4.5',
      description: '高一致性专业视觉创作模型，支持最高 4K 输出',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['2K', '4K'],
      supported_aspect_ratios: [
        '1:1',
        '16:9',
        '9:16',
        '4:3',
        '3:4',
        '3:2',
        '2:3',
      ],
      pricing: {},
    },
    'seedream-4-0-250828': {
      provider: 'byteplus',
      provider_model: 'seedream-4-0-250828',
      category: 'image',
      label: 'Seedream 4.0',
      description: 'BytePlus 新加坡区多模态图片生成与编辑，支持最高 4K 输出',
      capabilities: ['image_generation', 'image_edit'],
      supported_resolutions: ['1K', '2K', '4K'],
      supported_aspect_ratios: [
        '1:1',
        '16:9',
        '9:16',
        '4:3',
        '3:4',
        '3:2',
        '2:3',
      ],
      pricing: {},
    },
    'dreamina-seedance-2-0-260128': {
      provider: 'byteplus',
      provider_model: 'dreamina-seedance-2-0-260128',
      category: 'video',
      label: 'Seedance 2.0',
      description:
        'BytePlus 新加坡区 Seedance 2.0 视频模型，支持文生视频与参考素材生成',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
      ],
      supported_resolutions: ['480p', '720p', '1080p', '4k'],
      supported_aspect_ratios: ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      duration_range_seconds: [4, 15],
      supports_extension: false,
      extension_mode: 'none',
      pricing: {},
    },
    'kling-v2-6': {
      provider: 'kling',
      provider_model: 'kling-v2-6',
      category: 'video',
      label: '可灵 2.6',
      description: '可灵官方开放平台文生视频 / 图生视频，支持原生音画生成',
      capabilities: ['video_generation', 'text_to_video', 'image_to_video'],
      supported_resolutions: ['720p', '1080p'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      duration_options_seconds: [5, 10],
      duration_range_seconds: [5, 10],
      supports_extension: false,
      extension_mode: 'none',
      pricing: {},
    },
    'kling-3.0': {
      provider: 'kling',
      provider_model: 'kling-3.0',
      category: 'video',
      label: '可灵 3.0',
      description:
        '可灵 3.0 标准版，支持 3-15 秒、原生音频、多镜头与最高 4K 输出',
      capabilities: ['video_generation', 'text_to_video', 'image_to_video'],
      supported_resolutions: ['720p', '1080p', '4k'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      duration_options_seconds: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
      duration_range_seconds: [3, 15],
      native_audio_modes: ['off', 'native'],
      default_audio_mode: 'off',
      multi_shot_parameter_enabled: true,
      default_multi_shot: true,
      supports_extension: false,
      extension_mode: 'none',
      pricing: { '720p': 0.084, '1080p': 0.112, '4k': 0.42 },
    },
    'kling-3.0-turbo': {
      provider: 'kling',
      provider_model: 'kling-3.0-turbo',
      category: 'video',
      label: '可灵 3.0 Turbo',
      description:
        '可灵 3.0 Turbo 图生视频，3-15 秒，固定生成原生音频，速度更快',
      capabilities: ['image_to_video'],
      supported_resolutions: ['720p', '1080p'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      duration_options_seconds: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
      duration_range_seconds: [3, 15],
      native_audio_modes: ['native'],
      default_audio_mode: 'native',
      multi_shot_parameter_enabled: false,
      supports_extension: false,
      extension_mode: 'none',
      pricing: { '720p': 0.112, '1080p': 0.14 },
    },
    'kling-3.0-omni': {
      provider: 'kling',
      provider_model: 'kling-3.0-omni',
      category: 'video',
      label: '可灵 3.0 Omni',
      description:
        '可灵 3.0 Omni 多模态视频生成，支持 3-15 秒、原生音频与最高 4K 输出',
      capabilities: ['video_generation', 'text_to_video', 'image_to_video'],
      supported_resolutions: ['720p', '1080p', '4k'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      duration_options_seconds: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
      duration_range_seconds: [3, 15],
      native_audio_modes: ['off', 'native'],
      default_audio_mode: 'off',
      multi_shot_parameter_enabled: true,
      default_multi_shot: true,
      supports_extension: false,
      extension_mode: 'none',
      pricing: { '720p': 0.084, '1080p': 0.112, '4k': 0.42 },
    },
    'happyhorse-1.0-t2v': {
      provider: 'bailian',
      provider_model: 'happyhorse-1.0-t2v',
      category: 'video',
      label: 'HappyHorse 文生视频',
      description: '阿里云百炼 HappyHorse 文生视频',
      capabilities: ['text_to_video'],
      supported_resolutions: ['720P', '1080P'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [3, 15],
      pricing: {},
    },
    'happyhorse-1.0-i2v': {
      provider: 'bailian',
      provider_model: 'happyhorse-1.0-i2v',
      category: 'video',
      label: 'HappyHorse 图生视频',
      description: '阿里云百炼 HappyHorse 图生视频',
      capabilities: ['image_to_video', 'reference_to_video'],
      supported_resolutions: ['720P', '1080P'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [3, 15],
      pricing: {},
    },
    'wan2.7-t2v': {
      provider: 'bailian',
      provider_model: 'wan2.7-t2v',
      category: 'video',
      label: '万相 2.7 文生视频',
      description: '阿里云百炼万相文生视频',
      capabilities: ['text_to_video'],
      supported_resolutions: ['720P', '1080P'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [2, 15],
      pricing: {},
    },
    'wan2.7-i2v-2026-04-25': {
      provider: 'bailian',
      provider_model: 'wan2.7-i2v-2026-04-25',
      category: 'video',
      label: '万相 2.7 图生视频',
      description: '阿里云百炼万相图生视频',
      capabilities: ['image_to_video'],
      supported_resolutions: ['720P', '1080P'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      supports_extension: true,
      extension_mode: 'bailian_continuation',
      extension_model: 'wan2.7-i2v-2026-04-25',
      extension_input_duration_range_seconds: [2, 10],
      extension_max_duration_seconds: 15,
      duration_range_seconds: [2, 15],
      pricing: {},
    },
    'wan3.0-video': {
      provider: 'bailian',
      provider_model: 'wan3.0-video',
      category: 'video',
      label: '万相 3.0',
      description: '阿里云百炼一体化视频模型，支持文生、首帧、首尾帧和全能参考',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
      ],
      supported_input_modes: [
        'text_to_video',
        'first_frame',
        'first_last_frame',
        'reference_assets',
      ],
      supported_resolutions: ['720P', '1080P', '480P'],
      supported_aspect_ratios: [
        '16:9',
        '9:16',
        '1:1',
        '4:3',
        '3:4',
        'adaptive',
      ],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      native_audio_modes: ['off', 'native'],
      default_audio_mode: 'native',
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [2, 30],
      pricing: {},
    },
    'wan3.0-video-prime': {
      provider: 'bailian',
      provider_model: 'wan3.0-video-prime',
      category: 'video',
      label: '万相 3.0 Prime',
      description: '阿里云百炼万相 3.0 优速版，能力与标准版对齐，支持全能参考',
      capabilities: [
        'video_generation',
        'text_to_video',
        'image_to_video',
        'reference_to_video',
      ],
      supported_input_modes: [
        'text_to_video',
        'first_frame',
        'first_last_frame',
        'reference_assets',
      ],
      supported_resolutions: ['720P', '1080P', '480P'],
      supported_aspect_ratios: [
        '16:9',
        '9:16',
        '1:1',
        '4:3',
        '3:4',
        'adaptive',
      ],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      native_audio_modes: ['off', 'native'],
      default_audio_mode: 'native',
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [2, 30],
      pricing: {},
    },
    'wan2.7-r2v': {
      provider: 'bailian',
      provider_model: 'wan2.7-r2v',
      category: 'video',
      label: '万相 2.7 参考生视频',
      description: '阿里云百炼万相参考生视频',
      capabilities: ['reference_to_video'],
      supported_resolutions: ['720P', '1080P'],
      supported_aspect_ratios: ['16:9', '9:16', '1:1', '4:3', '3:4'],
      duration_parameter_enabled: true,
      default_duration_seconds: 5,
      supports_extension: false,
      extension_mode: 'none',
      duration_range_seconds: [2, 10],
      pricing: {},
    },
    'happyhorse-1.0-video-edit': {
      provider: 'bailian',
      provider_model: 'happyhorse-1.0-video-edit',
      category: 'video_edit',
      label: 'HappyHorse 视频编辑',
      description: '阿里云百炼 HappyHorse 视频编辑',
      capabilities: ['video_edit'],
      supported_resolutions: ['720P', '1080P'],
      duration_parameter_enabled: false,
      extension_mode: 'none',
      duration_range_seconds: [3, 15],
      pricing: {},
    },
    'wan2.7-videoedit': {
      provider: 'bailian',
      provider_model: 'wan2.7-videoedit',
      category: 'video_edit',
      label: '万相 2.7 视频编辑',
      description: '阿里云百炼万相视频编辑',
      capabilities: [
        'video_edit',
        'effect_reference',
        'camera_motion_reference',
      ],
      supported_resolutions: ['720P', '1080P'],
      duration_parameter_enabled: false,
      extension_mode: 'none',
      duration_range_seconds: [2, 10],
      pricing: {},
    },
    'gemini-2.5-flash-preview-tts': {
      category: 'tts',
      label: 'Gemini 2.5 Flash TTS Preview',
      description: '低延迟可控文本转语音',
      output_formats: ['wav'],
      pricing: {},
    },
    'gemini-2.5-pro-preview-tts': {
      category: 'tts',
      label: 'Gemini 2.5 Pro TTS Preview',
      description: '高保真文本转语音',
      output_formats: ['wav'],
      pricing: {},
    },
    'gemini-3.1-flash-live-preview': {
      category: 'audio_live',
      label: 'Gemini 3.1 Flash Live Preview',
      description: '实时对话与语音优先场景',
      pricing: {},
    },
    'gemini-2.5-flash-native-audio-preview-12-2025': {
      category: 'audio_live',
      label: 'Gemini 2.5 Flash Live Preview',
      description: '低延迟双向原生音频模型',
      pricing: {},
    },
  },
  features: {
    workspace_image: {
      enabled_models: [
        'gemini-3.1-flash-image-preview',
        'gemini-3-pro-image-preview',
        'gemini-2.5-flash-image',
        'wan2.7-image-pro',
        'seedream-5-0-lite-260128',
        'seedream-4-5-251128',
        'seedream-4-0-250828',
      ],
      default_model: 'gemini-3.1-flash-image-preview',
      default_resolution: '1K',
      max_batch_count: 10,
    },
    workspace_video: {
      enabled_models: [
        'veo-3.1-generate-preview',
        'veo-3.1-fast-generate-preview',
        'veo-3.1-lite-generate-preview',
        'dreamina-seedance-2-0-260128',
        'kling-3.0',
        'kling-3.0-turbo',
        'kling-3.0-omni',
        'kling-v2-6',
        'happyhorse-1.0-t2v',
        'happyhorse-1.0-i2v',
        'wan3.0-video',
        'wan3.0-video-prime',
        'wan2.7-t2v',
        'wan2.7-i2v-2026-04-25',
        'wan2.7-r2v',
      ],
      default_model: 'veo-3.1-fast-generate-preview',
      default_resolution: '720p',
      max_extension_count: 20,
    },
    workspace_video_edit: {
      enabled_models: ['happyhorse-1.0-video-edit', 'wan2.7-videoedit'],
      default_model: 'wan2.7-videoedit',
      default_resolution: '720P',
      max_batch_count: 4,
    },
    workspace_chat: {
      enabled_models: [
        'gemini-3-flash-preview',
        'gemini-3.1-pro-preview',
        'qwen-vl-plus',
        'qwen-vl-max',
        'qwen-plus',
        'qwen-max',
      ],
      default_model: 'qwen-vl-plus',
      max_context_messages: 28,
    },
    workspace_music: {
      enabled_models: ['lyria-3-clip-preview', 'lyria-3-pro-preview'],
      default_model: 'lyria-3-clip-preview',
      max_batch_count: 10,
    },
    workspace_tts: {
      enabled_models: [
        'gemini-2.5-flash-preview-tts',
        'gemini-2.5-pro-preview-tts',
      ],
      default_model: 'gemini-2.5-flash-preview-tts',
      max_batch_count: 10,
      default_voice: 'Kore',
      default_multi_voices: ['Kore', 'Puck'],
    },
    video_replicate: {
      enabled_models: ['veo-3.1-fast-generate-preview'],
      default_model: 'veo-3.1-fast-generate-preview',
      default_resolution: '720p',
      max_extension_count: 20,
    },
  },
};

export const FEATURE_CONFIG_META = {
  workspace_image: { label: '工作区图片', category: 'image' },
  workspace_video: { label: '工作区视频', category: 'video' },
  workspace_music: { label: '工作区音乐', category: 'music' },
  workspace_tts: { label: '工作区 TTS', category: 'tts' },
  workspace_video_edit: { label: '工作区视频编辑', category: 'video_edit' },
  workspace_chat: { label: '工作区对话', category: 'chat' },
  video_replicate: { label: '视频复刻', category: 'video' },
};

export const CATEGORY_LABELS: Record<string, string> = {
  image: '图片',
  video: '视频',
  music: '音乐',
  music_realtime: '实时音乐',
  tts: 'TTS',
  audio_live: '实时音频',
  video_edit: '视频编辑',
  chat: '对话模型',
};

/** 万相 3.0 官方全能参考上限：图/视频/音频/文档/网页合计最多 20 个。 */
export const WAN3_VIDEO_MODELS = [
  'wan3.0-video',
  'wan3.0-video-prime',
] as const;
export const WAN3_MAX_REFERENCE_IMAGES = 10;
export const WAN3_MAX_REFERENCE_VIDEOS = 5;
export const WAN3_MAX_REFERENCE_AUDIOS = 5;
export const WAN3_MAX_REFERENCE_FILES = 1;
export const WAN3_MAX_REFERENCE_LINKS = 1;
export const WAN3_MAX_OMNI_MEDIA = 20;
export const WAN3_REFERENCE_VIDEO_MIN_SECONDS = 1;
export const WAN3_REFERENCE_VIDEO_MAX_SECONDS = 15;
export const WAN3_REFERENCE_VIDEO_TOTAL_MAX_SECONDS = 15;
export const WAN3_REFERENCE_VIDEO_MAX_BYTES = 100 * 1024 * 1024;
export const WAN3_REFERENCE_AUDIO_MIN_SECONDS = 1;
export const WAN3_REFERENCE_AUDIO_MAX_SECONDS = 15;
export const WAN3_REFERENCE_AUDIO_TOTAL_MAX_SECONDS = 15;
export const WAN3_REFERENCE_AUDIO_MAX_BYTES = 15 * 1024 * 1024;
export const WAN3_REFERENCE_FILE_MAX_BYTES = 100 * 1024 * 1024;
export const WAN3_REFERENCE_FILE_EXTENSIONS = [
  '.docx',
  '.doc',
  '.xlsx',
  '.xls',
  '.pptx',
  '.ppt',
  '.pdf',
  '.txt',
  '.md',
  '.key',
  '.pages',
  '.numbers',
] as const;

/** 当前接入的 Seedance 2.5 支持独立音频全能参考。 */
export const isSeedance25VideoModel = (model?: string | null): boolean =>
  model === 'dreamina-seedance-2-5-260628';

export const isWan3VideoModel = (model?: string | null): boolean =>
  Boolean(model && (WAN3_VIDEO_MODELS as readonly string[]).includes(model));

export const isWan3ReferenceAudioFile = (file: File): boolean => {
  const name = file.name.toLowerCase();
  return (
    file.type.startsWith('audio/') ||
    name.endsWith('.mp3') ||
    name.endsWith('.wav')
  );
};

export const isWan3ReferenceDocumentFile = (file: File): boolean => {
  const name = file.name.toLowerCase();
  return WAN3_REFERENCE_FILE_EXTENSIONS.some((extension) =>
    name.endsWith(extension),
  );
};

export const getDefaultMediaGenerationConfig = () =>
  JSON.parse(JSON.stringify(DEFAULT_MEDIA_GENERATION_CONFIG));

/** Empty runtime shape used while the database-backed catalog is loading. */
export const getEmptyMediaGenerationConfig = () => ({
  currency: {
    code: 'CNY',
    cnyToUsdRate: 0.14,
  },
  deleted_model_ids: [] as string[],
  features: {} as Record<string, any>,
  model_catalog: {} as Record<string, any>,
});

export const getMediaModelCatalog = (config: any) =>
  config?.model_catalog || {};

export const getMediaFeatureConfig = (config: any, featureKey: string) =>
  config?.features?.[featureKey] || {};

export const getEnabledModels = (config: any, featureKey: string): string[] => {
  const featureConfig = getMediaFeatureConfig(config, featureKey);
  const modelCatalog = getMediaModelCatalog(config);
  return (featureConfig.enabled_models || []).filter(
    (model: string) => modelCatalog[model],
  );
};

export const getVideoPricePerSecond = (
  model: string,
  resolution: string,
  config: any,
  hasVideoInput = false,
): number => {
  const modelConfig = getMediaModelCatalog(config)?.[model];
  const pricing = modelConfig?.pricing || {};
  const normalizedResolution = String(resolution || '').toLowerCase();
  const getResolutionValue = (rates: Record<string, unknown> | undefined) => {
    if (!rates) return 0;
    const normalizedRates = Object.fromEntries(
      Object.entries(rates).map(([key, value]) => [key.toLowerCase(), value]),
    );
    return Number(
      normalizedRates[normalizedResolution] ?? normalizedRates.default ?? 0,
    );
  };

  const directPrice = getResolutionValue(pricing);
  if (directPrice > 0) return directPrice;

  const flatPrice = Number(pricing.per_second || 0);
  if (flatPrice > 0) return flatPrice;

  // Seedance 按输出视频 Token 结算；生成前没有真实 Token，只能使用数据库维护的
  // 每秒预估 Token。实际用量统计仍以供应商成功响应里的 completion_tokens 为准。
  const outputRates = hasVideoInput
    ? pricing.output_with_video_per_million_tokens_by_resolution
    : pricing.output_per_million_tokens_by_resolution;
  const outputRate = getResolutionValue(outputRates);
  const estimatedTokensPerSecond = getResolutionValue(
    pricing.estimated_output_tokens_per_second_by_resolution,
  );
  if (outputRate <= 0 || estimatedTokensPerSecond <= 0) return 0;

  return (outputRate * estimatedTokensPerSecond) / 1_000_000;
};

/**
 * Read an image model's database-maintained official unit price. Supports a
 * model-wide per-image rate and a rate that varies by output resolution.
 */
export const getImagePricePerImage = (
  model: string,
  resolution: string,
  config: any,
): number => {
  const modelConfig = getMediaModelCatalog(config)?.[model];
  const pricing = modelConfig?.pricing || {};
  const normalizedResolution = String(resolution || '').toLowerCase();
  const getResolutionValue = (rates: Record<string, unknown> | undefined) => {
    if (!rates) return 0;
    const normalizedRates = Object.fromEntries(
      Object.entries(rates).map(([key, value]) => [key.toLowerCase(), value]),
    );
    return Number(
      normalizedRates[normalizedResolution] ?? normalizedRates.default ?? 0,
    );
  };

  const perResolutionPrice = getResolutionValue(
    pricing.per_image_by_resolution,
  );
  if (perResolutionPrice > 0) return perResolutionPrice;

  // Accept existing catalogs that place resolution prices directly in pricing.
  const directPrice = getResolutionValue(pricing);
  if (directPrice > 0) return directPrice;

  return Number(pricing.per_image || 0);
};

export const estimateVeoBillableDuration = (
  sourceDurationSeconds: number,
  modelConfig: any,
  maxExtensionCount: number = 20,
): number => {
  const baseDuration = Number(modelConfig?.max_duration_seconds || 8);
  if (!Number.isFinite(sourceDurationSeconds) || sourceDurationSeconds <= 0) {
    return baseDuration;
  }
  if (modelConfig?.supports_extension === false) {
    return Math.min(sourceDurationSeconds, baseDuration);
  }
  if (sourceDurationSeconds <= 8) {
    return 8;
  }
  const extensionCount = Math.min(
    Math.ceil((sourceDurationSeconds - 8) / 7),
    maxExtensionCount,
  );
  return 8 + extensionCount * 7;
};

export const TTS_VOICE_OPTIONS = [
  'Zephyr',
  'Puck',
  'Charon',
  'Kore',
  'Fenrir',
  'Leda',
  'Orus',
  'Aoede',
  'Callirrhoe',
  'Autonoe',
  'Enceladus',
  'Iapetus',
  'Umbriel',
  'Algieba',
  'Despina',
  'Erinome',
  'Algenib',
  'Rasalgethi',
  'Laomedeia',
  'Achernar',
  'Alnilam',
  'Schedar',
  'Gacrux',
  'Pulcherrima',
  'Achird',
  'Zubenelgenubi',
  'Vindemiatrix',
  'Sadachbia',
  'Sadaltager',
  'Sulafat',
];

// ── 音色预设 (Voice Timbre Presets) ──
// 通过提示词控制说话的音色特征，与声音(voice_name)搭配使用
export interface TtsTimbrePreset {
  id: string;
  label: string;
  description: string;
  prompt: string; // 发送给 Gemini 的音色指令
  recommendedVoices?: string[]; // 推荐搭配的 voice_name
}

export const TTS_TIMBRE_PRESETS: TtsTimbrePreset[] = [
  {
    id: 'default',
    label: '默认',
    description: '不添加音色指令，使用声音原始风格',
    prompt: '',
  },
  {
    id: 'warm_male',
    label: '温暖男声',
    description: '成熟稳重、温暖有磁性的男性声音',
    prompt:
      'Speak with a warm, deep, and resonant male voice. The tone should be mature, steady, and comforting, like a trusted narrator or mentor.',
    recommendedVoices: ['Charon', 'Orus', 'Fenrir', 'Gacrux'],
  },
  {
    id: 'gentle_female',
    label: '温柔女声',
    description: '柔和亲切、温婉动听的女性声音',
    prompt:
      'Speak with a gentle, soft, and soothing female voice. The tone should be warm, nurturing, and pleasant, like a caring friend.',
    recommendedVoices: ['Kore', 'Leda', 'Aoede', 'Achernar'],
  },
  {
    id: 'energetic_host',
    label: '活力主播',
    description: '充满活力、节奏明快的主持人风格',
    prompt:
      'Speak with high energy and enthusiasm, like a professional radio host. The pace should be upbeat and dynamic, with punchy consonants and a bright, engaging tone.',
    recommendedVoices: ['Puck', 'Fenrir', 'Sadachbia', 'Laomedeia'],
  },
  {
    id: 'professional_narrator',
    label: '专业旁白',
    description: '沉稳专业、清晰有力的解说风格',
    prompt:
      'Speak in a clear, authoritative, and professional narrator voice. The delivery should be measured and articulate, suitable for documentaries or corporate presentations.',
    recommendedVoices: ['Charon', 'Alnilam', 'Schedar', 'Iapetus'],
  },
  {
    id: 'sweet_girl',
    label: '甜美少女',
    description: '年轻甜美、活泼可爱的少女声音',
    prompt:
      'Speak with a young, sweet, and cute female voice. The tone should be cheerful, lively, and slightly playful, like a youthful girl sharing exciting news.',
    recommendedVoices: ['Leda', 'Aoede', 'Callirrhoe', 'Autonoe'],
  },
  {
    id: 'deep_bass',
    label: '低沉磁性',
    description: '低音浑厚、富有磁性的声音',
    prompt:
      'Speak with a deep, rich bass voice. The tone should be smooth and resonant with a magnetic quality, like a late-night jazz radio host.',
    recommendedVoices: ['Enceladus', 'Charon', 'Algenib', 'Gacrux'],
  },
  {
    id: 'news_anchor',
    label: '新闻主播',
    description: '端正规范、字正腔圆的新闻播报风格',
    prompt:
      'Speak like a professional news anchor. The delivery should be clear, measured, and authoritative with perfect diction and even pacing. Maintain a serious and trustworthy tone.',
    recommendedVoices: ['Kore', 'Alnilam', 'Schedar', 'Rasalgethi'],
  },
  {
    id: 'storyteller',
    label: '故事讲述',
    description: '引人入胜、富有感染力的讲故事风格',
    prompt:
      'Speak like an engaging storyteller. Vary the pace and emotion to match the narrative. Use dramatic pauses, build suspense, and convey wonder. The voice should be captivating and expressive.',
    recommendedVoices: ['Puck', 'Charon', 'Aoede', 'Sadachbia'],
  },
  {
    id: 'calm_meditation',
    label: '冥想舒缓',
    description: '平静舒缓、令人放松的引导风格',
    prompt:
      'Speak in a very calm, slow, and soothing voice suitable for meditation or relaxation guidance. The tone should be peaceful and tranquil, with gentle breathing pauses between phrases.',
    recommendedVoices: ['Achernar', 'Vindemiatrix', 'Enceladus', 'Despina'],
  },
  {
    id: 'commercial_ad',
    label: '广告配音',
    description: '富有感染力和号召力的广告风格',
    prompt:
      'Speak with an exciting and persuasive advertising voice. Be enthusiastic and compelling, emphasizing key words with energy. The tone should inspire action and create desire, like a premium brand commercial.',
    recommendedVoices: ['Puck', 'Fenrir', 'Zephyr', 'Autonoe'],
  },
  {
    id: 'whisper_asmr',
    label: '轻声耳语',
    description: '轻柔低语、ASMR 风格的声音',
    prompt:
      '[whispers] Speak in a soft, intimate whisper throughout. The voice should be very close and gentle, like sharing a secret. Keep the volume low and the tone breathy and calming.',
    recommendedVoices: ['Enceladus', 'Achernar', 'Aoede', 'Vindemiatrix'],
  },
  {
    id: 'elderly_wise',
    label: '智慧长者',
    description: '沉稳睿智、饱经沧桑的长者声音',
    prompt:
      'Speak with the voice of a wise elderly person. The tone should be slow, thoughtful, and full of wisdom. Convey warmth and life experience, with occasional reflective pauses.',
    recommendedVoices: ['Gacrux', 'Algenib', 'Sadaltager', 'Rasalgethi'],
  },
];

// 用户自定义音色的存储 key
export const TTS_CUSTOM_TIMBRES_STORAGE_KEY = 'tts_custom_timbres';
export const TTS_TIMBRE_PROMPT_OVERRIDES_STORAGE_KEY =
  'tts_timbre_prompt_overrides';
