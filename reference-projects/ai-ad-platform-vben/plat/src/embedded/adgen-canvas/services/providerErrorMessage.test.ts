import { describe, expect, it } from 'vitest';

import {
  extractProviderErrorParts,
  formatProviderError,
  formatProviderErrorMessage,
  toUserFacingGenerationError,
} from './providerErrorMessage';

describe('formatProviderErrorMessage', () => {
  it('translates Seedance video-editing parameter errors', () => {
    const message = formatProviderErrorMessage(
      "Seedance identified your task as video editing based on your prompt. For this task type, the output ratio and duration follow the input video selected by the model for editing, and the video selected must satisfy the duration requirement of 4 to 30 seconds. Issues: [0] 'ratio' must be 'adaptive'. [1] 'duration' must be -1.",
    );

    expect(message).toContain('视频编辑');
    expect(message).toContain('自适应');
    expect(message).toContain('4–30');
  });

  it('translates copyright restriction errors and strips request ids', () => {
    const message = formatProviderErrorMessage(
      'Seedance任务失败cpt-20260909152008-77sw5：Seedance request failed - 20260909152008-77sw5: The request failed because the output video may be related to copyright restrictions. Request id: 0217889384101951',
    );

    expect(message).toContain('版权');
    expect(message).not.toContain('0217889384101951');
    expect(message).not.toContain('cpt-20260909152008');
  });

  it('translates BytePlus PolicyViolation codes as copyright', () => {
    const message = formatProviderErrorMessage(
      'The request failed because the input image may be related to copyright restrictions.',
      'InputImageSensitiveContentDetected.PolicyViolation',
    );
    expect(message).toContain('版权');
  });

  it('translates real-person reference image errors with a 1-based index', () => {
    const message = formatProviderErrorMessage(
      'The request failed because the input image [1] may contain a real person.',
      '',
      '生成失败，请根据提示调整后重试',
      { imageCount: 3 },
    );

    expect(message).toContain('第 2 张参考图');
    expect(message).toContain('真人肖像');
  });

  it('does not treat content[1] as the second reference image', () => {
    const message = formatProviderErrorMessage(
      'The request failed because content [1] may contain a real person.',
      '',
      '生成失败，请根据提示调整后重试',
      { imageCount: 1 },
    );

    expect(message).toContain('参考图可能包含真人肖像');
    expect(message).not.toContain('第 2');
  });

  it('omits the image ordinal when the user only attached one image', () => {
    const message = formatProviderErrorMessage(
      'The request failed because the input image [0] may contain a real person.',
      '',
      '生成失败，请根据提示调整后重试',
      { imageCount: 1 },
    );

    expect(message).toContain('参考图可能包含真人肖像');
    expect(message).not.toContain('第 1');
    expect(message).not.toContain('第 2');
  });

  it('translates BytePlus PrivacyInformation on videos', () => {
    const message = formatProviderErrorMessage(
      'The request failed because the input video may contain real person.',
      'InputVideoSensitiveContentDetected.PrivacyInformation',
    );
    expect(message).toContain('参考视频');
    expect(message).toContain('真人');
  });

  it('translates oversized reference image errors with dimensions', () => {
    const message = formatProviderErrorMessage(
      'image data [0] failed: Image exceeds the maximum allowed total pixels. Current dimensions: 15794x4168 = 65829992 pixels. Maximum allowed: 36000000 pixels.',
    );

    expect(message).toContain('15794×4168');
    expect(message).toContain('3600 万像素');
    expect(message).toContain('压缩或裁剪');
  });

  it('translates concurrent or polling timeout errors', () => {
    const message = formatProviderErrorMessage(
      '百炼任务轮询超时: 8d767753-d373-4e62-8a41-51379d9b6239',
    );

    expect(message).toContain('并发');
    expect(message).toContain('稍后再试');
  });

  it('translates BytePlus rate limit and overload codes', () => {
    expect(
      formatProviderErrorMessage(
        'RPM (Requests Per Minute) limit of the model is exceeded.',
      ),
    ).toContain('限流');
    expect(
      formatProviderErrorMessage(
        'The service is currently unable to handle additional requests due to server overload.',
      ),
    ).toContain('额度');
  });

  it('translates unreadable 400 bad request payloads', () => {
    const formatted = formatProviderError(
      '400 Bad Request: The browser (or proxy) sent a request that this server could not understand.',
    );

    expect(formatted.type).toBe('params');
    expect(formatted.message).toContain('请求参数');
  });

  it('translates input and output sensitive-content reviews', () => {
    expect(
      formatProviderErrorMessage(
        'The request failed because the input text may contain sensitive information.',
      ),
    ).toContain('提示词未通过内容安全审核');
    expect(
      formatProviderErrorMessage(
        'The request failed because the input image may contain sensitive information.',
      ),
    ).toContain('参考图未通过内容安全审核');
    expect(
      formatProviderErrorMessage(
        'The request failed because the output video may contain sensitive information.',
      ),
    ).toContain('生成结果未通过内容安全审核');
  });

  it('translates Bailian, Veo and Kling safety rejections', () => {
    expect(
      formatProviderErrorMessage(
        'DataInspectionFailed: 输入数据可能包含敏感内容',
      ),
    ).toContain('安全审核');
    expect(formatProviderErrorMessage('IPInfringementSuspect')).toContain(
      '版权',
    );
    expect(
      formatProviderErrorMessage(
        'Veo could not generate videos. Support codes: 15236754',
      ),
    ).toContain('公众人物');
    expect(
      formatProviderErrorMessage(
        'The content you uploaded appears to violate the community guidelines. (CM_EXT.POther)',
      ),
    ).toContain('安全审核');
  });

  it('translates media format, duration and download failures', () => {
    expect(formatProviderErrorMessage('Invalid base64 image url')).toContain(
      '格式',
    );
    expect(
      formatProviderErrorMessage('duration must be integer 3-15'),
    ).toContain('时长');
    expect(
      formatProviderErrorMessage('Failed to download the input file'),
    ).toContain('下载');
  });

  it('does not treat generic audio words as BGM restrictions', () => {
    const formatted = formatProviderError(
      'The request failed because the input audio may contain sensitive information.',
    );
    expect(formatted.type).toBe('sensitive');
    expect(formatted.message).toContain('参考音频');
  });

  it('keeps already readable Chinese messages when no official rule matches', () => {
    const message = formatProviderErrorMessage('当前节点没有可处理的图片');
    expect(message).toBe('当前节点没有可处理的图片');
  });
});

describe('extractProviderErrorParts', () => {
  it('prefers provider text over generic envelope messages', () => {
    const parts = extractProviderErrorParts({
      code: 600,
      message: '系统繁忙，请稍后重试',
      data: {
        status: 'failed',
        error:
          'The request failed because the input image [0] may contain a real person.',
      },
    });

    expect(parts.message).toContain('real person');
  });

  it('keeps official error codes from the payload', () => {
    const parts = extractProviderErrorParts({
      code: 'InputImageSensitiveContentDetected.PrivacyInformation',
      message:
        'The request failed because the input image may contain real person.',
    });
    expect(parts.code).toContain('PrivacyInformation');
  });

  it('ignores duplicated generic server messages', () => {
    const parts = extractProviderErrorParts({
      code: 600,
      message: '服务端处理异常',
      error: '服务端处理异常',
    });
    expect(parts.message).toBe('服务端处理异常');
    expect(parts.detail).toBe('');
  });
});

describe('toUserFacingGenerationError', () => {
  it('does not concatenate the same generic server message twice', () => {
    const message = toUserFacingGenerationError(
      {
        message: '服务端处理异常',
        originalReason: '服务端处理异常',
      },
      '视频生成失败，请稍后重试',
    );

    expect(message).toBe('视频生成失败，请稍后重试');
    expect(message).not.toContain('服务端处理异常服务端处理异常');
  });

  it('collapses a concatenated generic phrase before falling back', () => {
    const message = toUserFacingGenerationError(
      { message: '服务端处理异常服务端处理异常' },
      '视频生成失败，请稍后重试',
    );
    expect(message).toBe('视频生成失败，请稍后重试');
  });
});
