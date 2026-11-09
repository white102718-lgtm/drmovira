import type {
  AdDraftPayload,
  AsyncTaskStatus,
  PreflightResult,
  PublishJobResult,
} from '#/api';

export type AdPublishingCheck = PreflightResult['checks'][number];

/** Stable projection of an existing publish-job task. */
export interface AdPublishingJob {
  createdAt: string;
  id: string;
  message?: string;
  platform?: AdDraftPayload['platform'];
  progress: number;
  projectId: string;
  status: AsyncTaskStatus;
  title: string;
  updatedAt: string;
}

/**
 * Transport-neutral publishing boundary. It intentionally preserves the
 * established Fusion payload and the optional preflight proof shape.
 */
export interface AdPublishingAdapter {
  getJob(
    jobId: string,
    projectId?: string,
  ): Promise<AdPublishingJob | undefined>;
  preflight(payload: AdDraftPayload): Promise<PreflightResult>;
  publish(
    payload: AdDraftPayload,
    preflightToken?: string,
  ): Promise<PublishJobResult>;
}

export interface AdPublishingPreflight extends PreflightResult {
  checks: AdPublishingCheck[];
}
