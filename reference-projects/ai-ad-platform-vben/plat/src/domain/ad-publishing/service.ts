import type {
  AdPublishingAdapter,
  AdPublishingCheck,
  AdPublishingPreflight,
} from './types';

import type { AdDraftPayload, PublishJobResult } from '#/api';
import { assertAdPublishingPlatform } from './platform';

function cloneDraft(payload: AdDraftPayload): AdDraftPayload {
  return {
    ...payload,
    materialIds: [...payload.materialIds],
    targeting: {
      ...payload.targeting,
      countries: [...payload.targeting.countries],
      languages: payload.targeting.languages
        ? [...payload.targeting.languages]
        : undefined,
    },
  };
}

function required(value: string, label: string) {
  if (!value.trim()) throw new Error(`广告草稿缺少${label}`);
}

function cloneCheck(check: AdPublishingCheck): AdPublishingCheck {
  return { ...check };
}

/**
 * Application service for the current Fusion publishing contract. The legacy
 * page keeps owning its wizard-level account, asset and material checks; this
 * service owns only draft transport, proof lifetime and exact job lookup.
 */
export class AdPublishingService {
  constructor(private readonly adapter: AdPublishingAdapter) {}

  async getJob(jobId: string, projectId?: string) {
    return await this.adapter.getJob(jobId.trim(), projectId?.trim());
  }

  async preflight(payload: AdDraftPayload): Promise<AdPublishingPreflight> {
    const draft = this.validateDraft(payload);
    const result = await this.adapter.preflight(draft);
    return {
      checks: result.checks.map((check) => cloneCheck(check)),
      passed: result.passed,
      token: result.token,
      tokenExpiresAt: result.tokenExpiresAt,
    };
  }

  async publish(
    payload: AdDraftPayload,
    preflight: AdPublishingPreflight,
  ): Promise<PublishJobResult> {
    const draft = this.validateDraft(payload);
    if (!preflight.passed) throw new Error('发布前检查未通过');
    if (
      preflight.tokenExpiresAt &&
      Date.parse(preflight.tokenExpiresAt) <= Date.now()
    ) {
      throw new Error('发布前检查凭证已过期，请重新检查');
    }
    return await this.adapter.publish(draft, preflight.token);
  }

  withChecks(
    preflight: AdPublishingPreflight,
    additionalChecks: readonly AdPublishingCheck[],
  ): AdPublishingPreflight {
    const checks = [
      ...preflight.checks.map((check) => cloneCheck(check)),
      ...additionalChecks.map((check) => cloneCheck(check)),
    ];
    return {
      checks,
      passed: checks.every((check) => check.passed),
      token: preflight.token,
      tokenExpiresAt: preflight.tokenExpiresAt,
    };
  }

  private validateDraft(payload: AdDraftPayload): AdDraftPayload {
    assertAdPublishingPlatform(payload.platform);
    required(payload.projectId, '项目');
    required(payload.platform, '投放平台');
    required(payload.adAccountId, '广告账户');
    required(payload.agencyLineId ?? '', '代理线');
    if (!Array.isArray(payload.materialIds))
      throw new Error('广告草稿素材格式无效');
    return cloneDraft(payload);
  }
}
