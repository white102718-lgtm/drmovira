import { adpulseClient } from '#/api/request';
import { pollUploadTask } from '#/api/utils/poll-task';
import { ORDER_ATTACHMENT_ALLOWED_EXTS } from '#/utils/upload';

export interface RequirementTemplateAttachment {
  attachment_id: string;
  object_key: string;
  name: string;
  basename: string;
  size: number;
  content_type: string;
  filetype: 'archive' | 'image' | 'video';
  url?: string;
  download_url?: string;
}

export interface RequirementTemplateItem {
  description: string;
  duration: string;
  quantity: number;
  link: string;
  remark: string;
  compliance: string;
  attachments: RequirementTemplateAttachment[];
}

export interface RequirementTemplateSummary {
  id: string;
  name: string;
  description: string;
  requirement_count: number;
  version: number;
  updated_at: string;
  updated_by_name?: string;
}

export interface RequirementTemplate extends RequirementTemplateSummary {
  requirements: RequirementTemplateItem[];
}

export interface RequirementTemplatePayload {
  name: string;
  description: string;
  requirements: Array<
    Omit<RequirementTemplateItem, 'attachments'> & {
      attachments: Array<{ attachment_id: string }>;
    }
  >;
}

const path = '/material-requirement-templates';

/** 仅取摘要；游标分页不加载全库明细，也不依赖浏览器本地模板。 */
export function listRequirementTemplates(
  params: {
    keyword?: string;
    cursor?: string;
    page_size?: number;
  },
  signal?: AbortSignal,
) {
  return adpulseClient.get<{
    items: RequirementTemplateSummary[];
    next_cursor: string | null;
    can_manage: boolean;
  }>(path, { params, signal });
}

export function getRequirementTemplate(id: string) {
  return adpulseClient.get<RequirementTemplate>(`${path}/${id}`);
}

export function createRequirementTemplate(data: RequirementTemplatePayload) {
  return adpulseClient.post<RequirementTemplate>(path, data);
}

export function updateRequirementTemplate(
  id: string,
  data: RequirementTemplatePayload & { version: number },
) {
  return adpulseClient.put<RequirementTemplate>(`${path}/${id}`, data);
}

export function deleteRequirementTemplate(id: string, version: number) {
  return adpulseClient.delete(`${path}/${id}`, { params: { version } });
}

export const REQUIREMENT_TEMPLATE_ATTACHMENT_EXTS =
  ORDER_ATTACHMENT_ALLOWED_EXTS;

/** 接收完成后轮询后台入桶结果，调用方始终拿到已登记的附件。 */
export async function uploadRequirementTemplateAttachment(
  file: File,
  signal?: AbortSignal,
): Promise<RequirementTemplateAttachment> {
  const data = new FormData();
  data.append('file', file);
  const response = await adpulseClient.post<
    RequirementTemplateAttachment | { task_id: string }
  >(`${path}/attachments`, data, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // 浏览器超时包含文件传输；后台入桶由后续轮询等待。
    timeout: 60 * 60 * 1000,
    signal,
  });
  // 兼容先发布前端时仍返回附件对象的旧后端。
  if (!('task_id' in response)) return response;
  return pollUploadTask(
    response.task_id,
    file.size,
    signal,
    undefined,
    true,
    true,
  );
}

export function getRequirementTemplateAttachmentUrl(id: string) {
  return adpulseClient.get<{ url: string; name: string }>(
    `${path}/attachments/${id}/url`,
  );
}
