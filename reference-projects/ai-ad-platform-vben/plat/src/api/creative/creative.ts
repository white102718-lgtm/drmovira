import { backendClient } from '#/api/request';

export async function uploadCreativeMaterial(formData: FormData) {
  return backendClient.post('/creative/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000, // 5分钟超时 (单位: 毫秒)
  });
}

export async function getCreativeMaterials(params?: any) {
  return backendClient.get('/creative/', { params });
}

export async function getVideoUrl(id: string): Promise<string> {
  return backendClient.get(`/creative/url/${id}`);
}

export async function getThumbnailByFileId(fileId: string): Promise<string> {
  return await backendClient.get(`/creative/thumbnail/${fileId}`);
}

export async function getThumbnailImgByFileIds(
  fileIds: string,
): Promise<Record<string, string>> {
  return await backendClient.get(`/creative/thumbnail_img/${fileIds}`);
}

export async function getOriginalVideoUrl(id: string): Promise<string> {
  return backendClient.get(`/creative/murl/${id}`);
}

export async function getRunningCreativeMaterials(params?: any) {
  return backendClient.get('/creative/running/', { params });
}

export async function checkCreativeTaskStatus(id: string) {
  return backendClient.get(`/creative/running/${id}`);
}

export async function uploadCreativeImages(formData: FormData) {
  return backendClient.post('/creative/img/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000, // 5分钟超时 (单位: 毫秒)
  });
}

export async function checkCreativeImagesTaskStatus(id: string) {
  return backendClient.get(`/creative/img-running/${id}`);
}
export async function getRunningCreativeImageTasks(params?: any) {
  return backendClient.get('/creative/img-running/', { params });
}

export async function getCreativeImageTasks(params?: any) {
  return backendClient.get('/creative/img/', { params });
}

export async function getImageUrl(uniqueFilename: string): Promise<string> {
  return backendClient.get(`/creative/url-img/${uniqueFilename}`);
}

export async function getOriginalImageUrl(id: string): Promise<string> {
  return backendClient.get(`/creative/murl-img/${id}`);
}

export async function bulkUploadCreativeImages(files: File[], bulkTasks: any[]) {
  // 创建一个特殊的请求，同时发送 JSON 和文件
  const formData = new FormData();
  
  // 添加文件
  files.forEach(file => {
    formData.append('files', file);
  });
  
  // 将 bulk_tasks 作为 JSON 字符串表单字段添加
  formData.append('bulk_tasks', JSON.stringify(bulkTasks));
  
  return backendClient.post('/creative/img/bulk', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000, // 5分钟超时 (单位: 毫秒)
  });
}

export async function bulkUploadCreativeVideos(files: File[], bulkTasks: any[]) {
  // 创建批量视频上传请求
  const formData = new FormData();
  
  // 添加文件
  files.forEach(file => {
    formData.append('files', file);
  });
  
  // 将 bulk_tasks 作为 JSON 字符串表单字段添加
  formData.append('bulk_tasks', JSON.stringify(bulkTasks));
  
  return backendClient.post('/creative/bulk', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000, // 5分钟超时 (单位: 毫秒)
  });
}
