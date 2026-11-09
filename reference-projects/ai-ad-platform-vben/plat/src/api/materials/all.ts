import { adpulseClient } from '#/api/request';
import { pollUploadTask } from '#/api/utils/poll-task';

interface TagData {
  name: string;
  tags: string[];
  title?: string;
}

async function addMaterialApi(
  formData: FormData,
  onUploadProgress?: (percent: number) => void,
) {
  const fileSize = (formData.get('file') as File)?.size ?? 0;
  const res: any = await adpulseClient.post('materials/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000,
    onUploadProgress: (e) => {
      if (e.total) onUploadProgress?.(Math.round((e.loaded * 100) / e.total));
    },
  });
  return pollUploadTask(res.task_id, fileSize);
}

async function addAdCreativeMaterialApi(formData: FormData) {
  const fileSize = (formData.get('file') as File)?.size ?? 0;
  const res: any = await adpulseClient.post(
    'materials/ad-creatives',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300_000,
    },
  );
  return pollUploadTask(res.task_id, fileSize);
}

async function listAdCreativesApi(params: Record<string, any>) {
  const urlParams = new URLSearchParams();
  urlParams.set('page', params.page.toString());
  urlParams.set('page_size', params.pageSize.toString());
  if (params.user) urlParams.set('user', params.user);
  if (params.filetype) urlParams.set('filetype', params.filetype);
  if (params.start_time) urlParams.set('start_time', params.start_time);
  if (params.end_time) urlParams.set('end_time', params.end_time);
  return adpulseClient.get(`materials/ad-creatives?${urlParams.toString()}`);
}

async function listMaterialApi(params: Record<string, any>) {
  const urlParams = new URLSearchParams();
  // 必需参数
  urlParams.set('page', params.page.toString());
  urlParams.set('page_size', params.pageSize.toString());
  // 字段映射
  const fieldMapping: Record<string, string> = {
    sortBy: 'sort',
    sortOrder: 'order',
    CreativeEditor: 'creative_editor',
  };
  // 处理普通参数
  Object.entries(params).forEach(([key, value]) => {
    if (
      [
        'basenames',
        'ids',
        'page',
        'pageSize',
        'tags',
        'tags_new',
        'tags_remove',
      ].includes(key)
    )
      return;
    if (value !== undefined && value !== null && value !== '') {
      const urlKey = fieldMapping[key] || key;
      urlParams.set(urlKey, value.toString());
    }
  });

  // 处理数组参数
  const arrayParams: Record<string, string[] | undefined> = {
    tags: params.tags,
    tags_new: params.tags_new,
    tags_remove: params.tags_remove,
    ids: params.ids,
    basenames: params.basenames,
    departments: params.departments,
    game_platform: params.game_platform,
  };

  Object.entries(arrayParams).forEach(([key, values]) => {
    if (values && Array.isArray(values)) {
      values.forEach((val) => urlParams.append(key, val));
    }
  });

  return adpulseClient.get(`materials/?${urlParams.toString()}`);
}

async function getMaterialUrlApi(filename: string, signal?: AbortSignal) {
  return adpulseClient.get(
    `materials/url/${filename}`,
    signal ? ({ signal, skipErrorMessage: true } as any) : undefined,
  );
}

async function getMaterialImgApi(basename: string) {
  return adpulseClient.get(`materials/img/${basename}`);
}

async function getBatchMaterialImgApi(
  basenames: string[],
  signal?: AbortSignal,
) {
  return adpulseClient.post(
    'materials/batch_img',
    { basenames },
    signal ? ({ signal, skipErrorMessage: true } as any) : undefined,
  );
}

async function downloadFilesAsZip(filenames: string[]) {
  const res: any = await adpulseClient.post('materials/zip', filenames, {
    timeout: 300_000,
  });
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

async function downloadFilesAsZipNamed(fileIds: string[]) {
  const res: any = await adpulseClient.post('materials/zip_named', fileIds, {
    timeout: 300_000,
  });
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

async function downloadCommonFilesAsZip(fileIds: string[]) {
  const res: any = await adpulseClient.post('material-common/zip', fileIds, {
    timeout: 300_000,
  });
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

interface BatchUpdateParams {
  basenames: string[];
  country?: string;
  ids: string[];
  operator?: string;
  tags?: string[];
  tags_new?: string[];
  tags_remove?: string[];
  user?: string;
}

async function batchUpdateMaterials(params: BatchUpdateParams) {
  return adpulseClient.put('materials/batch_update', params);
}

async function getMaterialsByIds({
  ids,
  basenames,
  fields,
}: {
  basenames?: string[];
  fields?: string[];
  ids?: string[];
}) {
  const params = new URLSearchParams();

  // 1️⃣ 优先使用 ids
  if (ids && ids.length > 0) {
    ids.forEach((id) => params.append('ids', id));
  }
  // 2️⃣ 否则使用 basenames
  else if (basenames && basenames.length > 0) {
    basenames.forEach((name) => params.append('basenames', name));
  }
  // 3️⃣ 如果有 fields，则用逗号拼接
  if (fields && fields.length > 0) {
    params.set('fields', fields.join(','));
  }
  // 4️⃣ 发起请求
  return adpulseClient.get(`materials/by_ids?${params.toString()}`);
}
async function listMaterialsWithTagTitles(params: Record<string, any>) {
  const urlParams = new URLSearchParams();
  urlParams.set('page', params.page.toString());
  urlParams.set('page_size', params.pageSize.toString());

  const fieldMapping: Record<string, string> = {
    sortBy: 'sort',
    sortOrder: 'order',
  };
  const arrayKeys = new Set(['departments', 'game_platform', 'tags']);

  Object.entries(params).forEach(([key, value]) => {
    if (key === 'page' || key === 'pageSize') return;
    if (arrayKeys.has(key)) return;
    if (value !== undefined && value !== null && value !== '') {
      urlParams.set(fieldMapping[key] || key, value.toString());
    }
  });

  for (const key of ['game_platform', 'departments', 'tags']) {
    const val = params[key];
    if (Array.isArray(val) && val.length > 0) {
      val.forEach((v: string) => urlParams.append(key, v));
    }
  }

  return adpulseClient.get(`materials/with_tag_titles?${urlParams.toString()}`);
}

async function batchDeleteMaterials(filenames: string[]) {
  return adpulseClient.post('materials/batch_delete', {
    filenames,
  });
}

async function getAllFactTags() {
  return adpulseClient.get('tags/fact');
}

async function getFactTagsByName(name: string) {
  return adpulseClient.get(`tags/fact?name=${encodeURIComponent(name)}`);
}

async function getCountryTags() {
  return getFactTagsByName('country');
}

async function getAllInferenceTags() {
  return adpulseClient.get('tags/inference');
}

async function updateFactTag(tagData: TagData) {
  return adpulseClient.post('tags/fact', tagData);
}

async function updateInferenceTag(tagData: TagData) {
  return adpulseClient.post('tags/inference', tagData);
}

async function createInferenceTag(name: string, title: string) {
  const tagData: TagData = {
    name,
    tags: [],
    title,
  };
  return adpulseClient.post('tags/inference', tagData);
}

async function deleteFactTag(name: string) {
  return adpulseClient.delete(`tags/fact/${name}`);
}

async function deleteInferenceTag(name: string) {
  return adpulseClient.delete(`tags/inference/${name}`);
}

async function analysisDescApi(filenames: string[]) {
  return adpulseClient.post('materials/analysis_desc', { filenames });
}

async function getAnalysisDescApi() {
  return adpulseClient.get<string[]>('materials/analysis_desc');
}

/** 文件夹归属的空间：个人空间 / 共享文件夹(部门文件夹) */
type FolderScope = 'department' | 'personal';
/** 查看权限：仅自己 / 本部门可见 / 全员可见 */
type FolderVisibility = 'department' | 'organization' | 'private';

interface FolderListParams {
  basename?: readonly string[];
  folder_id?: string;
  keyword?: string;
  owner?: string;
  parent_id?: string;
  scope?: FolderScope;
}

interface FolderPayload {
  color?: null | string;
  name: string;
  parent_id?: null | string;
  scope: FolderScope;
  visibility: FolderVisibility;
}

async function listFoldersApi(params?: FolderListParams) {
  // FastAPI 的列表查询参数使用重复键，不能序列化成 basename[] 或逗号串。
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (Array.isArray(value)) value.forEach((item) => query.append(key, item));
    else if (typeof value === 'string' && value) query.set(key, value);
  });
  return adpulseClient.get(`material-folders/?${query.toString()}`);
}

async function createFolderApi(payload: FolderPayload) {
  return adpulseClient.post('material-folders/', payload);
}

async function updateFolderApi(fid: string, payload: Partial<FolderPayload>) {
  return adpulseClient.put(`material-folders/${fid}`, payload);
}

async function deleteFolderApi(fid: string) {
  return adpulseClient.delete(`material-folders/${fid}`);
}

/** 记一次打开，用于首页「最近访问」 */
async function visitFolderApi(fid: string) {
  return adpulseClient.post(`material-folders/${fid}/visit`);
}

async function listFolderMaterialsApi(
  fid: string,
  page: number,
  pageSize: number,
  filters?: { filetype?: string; basename?: string | readonly string[] },
) {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const names =
    typeof filters?.basename === 'string'
      ? [filters.basename]
      : (filters?.basename ?? []);
  names.forEach((name) => query.append('basename', name));
  if (filters?.filetype) query.set('filetype', filters.filetype);
  return adpulseClient.get(
    `material-folders/${fid}/materials?${query.toString()}`,
  );
}

async function publishMaterialsApi(folder_id: string, materials: string[]) {
  return adpulseClient.post('material-folders/publish', {
    folder_id,
    materials,
  });
}

interface FbPushPayload {
  target_id: string;
  personal_id: string;
  basenames: string[];
  order_id?: string;
}

async function pushMaterialsToFbApi(payload: FbPushPayload) {
  const res: any = await adpulseClient.post('materials/fb_push', payload);
  const taskId = res.task_id;
  const pollInterval = Math.min(
    Math.max(payload.basenames.length * 3000, 3000),
    30_000,
  );
  return new Promise<any>((resolve, reject) => {
    const poll = async () => {
      try {
        const task: any = await adpulseClient.get(
          `materials/fb_push/${taskId}`,
          { skipErrorMessage: true } as any,
        );
        if (task.status === 'done') return resolve(task);
        if (task.status === 'failed')
          return reject(new Error(task.error || '上传失败'));
        setTimeout(poll, pollInterval);
      } catch (e: any) {
        const httpStatus = e?.response?.status;
        const bodyCode = e?.data?.code ?? e?.response?.data?.code;
        const is4xx =
          (httpStatus !== undefined && httpStatus >= 400 && httpStatus < 500) ||
          (bodyCode !== undefined && bodyCode >= 400 && bodyCode < 500);
        if (is4xx) {
          reject(
            new Error(
              e?.data?.message ??
                e?.response?.data?.message ??
                e?.message ??
                '上传失败',
            ),
          );
          return;
        }
        setTimeout(poll, pollInterval);
      }
    };
    poll();
  });
}

async function deleteFolderMaterialsApi(fid: string, ids: string[]) {
  return adpulseClient.post(`material-folders/${fid}/materials/batch_delete`, {
    ids,
  });
}

async function listCommonMaterialsApi(params: {
  page?: number;
  page_size?: number;
  filetype?: string;
  basename?: string;
}) {
  return adpulseClient.get('material-common/', { params });
}

async function getCommonMaterialsByIdsApi(ids: string[]) {
  const params = new URLSearchParams();
  ids.forEach((id) => params.append('ids', id));
  return adpulseClient.get(`material-common/by_ids?${params.toString()}`);
}

async function uploadCommonMaterialApi(
  formData: FormData,
  tagsNew?: (string | null)[] | string[],
  folderId?: string,
  onUploadProgress?: (percent: number) => void,
) {
  if (tagsNew && tagsNew.length > 0) {
    tagsNew.forEach((tag) => {
      if (tag !== null && tag !== undefined) {
        formData.append('tags_new', tag);
      }
    });
  }
  if (folderId) {
    formData.append('folder_id', folderId);
  }
  const fileSize = (formData.get('file') as File)?.size ?? 0;
  const res: any = await adpulseClient.post('material-common/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000,
    onUploadProgress: (e) => {
      if (e.total) onUploadProgress?.(Math.round((e.loaded * 100) / e.total));
    },
  });
  return pollUploadTask(res.task_id, fileSize);
}

async function batchDeleteCommonMaterialsApi(ids: string[]) {
  return adpulseClient.post('material-common/batch_delete', { ids });
}

async function getAdsByTag(params: Record<string, any>) {
  const urlParams = new URLSearchParams();
  const arrayKeys = new Set(['departments', 'game_platform']);

  Object.entries(params).forEach(([key, value]) => {
    if (arrayKeys.has(key)) return;
    if (value !== undefined && value !== null && value !== '') {
      urlParams.set(key, value.toString());
    }
  });

  for (const key of ['game_platform', 'departments']) {
    const val = params[key];
    if (Array.isArray(val) && val.length > 0) {
      val.forEach((v: string) => urlParams.append(key, v));
    }
  }

  return adpulseClient.get(`materials/ads_by_tag?${urlParams.toString()}`);
}

export type { FolderListParams, FolderPayload, FolderScope, FolderVisibility };

export {
  addAdCreativeMaterialApi,
  addMaterialApi,
  batchDeleteCommonMaterialsApi,
  createFolderApi,
  deleteFolderApi,
  deleteFolderMaterialsApi,
  getCommonMaterialsByIdsApi,
  listCommonMaterialsApi,
  listFolderMaterialsApi,
  listFoldersApi,
  publishMaterialsApi,
  updateFolderApi,
  uploadCommonMaterialApi,
  visitFolderApi,
  analysisDescApi,
  batchDeleteMaterials,
  batchUpdateMaterials,
  createInferenceTag,
  deleteFactTag,
  deleteInferenceTag,
  downloadCommonFilesAsZip,
  downloadFilesAsZip,
  downloadFilesAsZipNamed,
  getAdsByTag,
  getAllFactTags,
  getAllInferenceTags,
  getAnalysisDescApi,
  getBatchMaterialImgApi,
  getCountryTags,
  getFactTagsByName,
  getMaterialImgApi,
  getMaterialsByIds,
  getMaterialUrlApi,
  listAdCreativesApi,
  listMaterialApi,
  listMaterialsWithTagTitles,
  updateFactTag,
  updateInferenceTag,
  pushMaterialsToFbApi,
};
