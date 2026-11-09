import { backendClient } from '#/api/request';

export interface StoredFileView {
  extension: string;
  fileSize: number;
  id: string;
  mimeType: string;
  originalName: string;
}

/** 读取办理结果中的文件元数据，不暴露底层存储路径。 */
export function getStoredFileApi(fileId: string) {
  return backendClient.get<StoredFileView>(`/files/${fileId}`);
}

/** 通过带认证的请求读取文件，供水单等办理凭证预览。 */
export function downloadStoredFileApi(fileId: string) {
  return backendClient.get<Blob>(`/files/${fileId}/download`, {
    responseReturn: 'body',
    responseType: 'blob',
  });
}

/** 读取登录用户可直接访问的有效文件元数据。 */
export function getOpenStoredFileApi(fileId: string) {
  return backendClient.get<StoredFileView>(`/files/open/${fileId}`);
}

/** 读取登录用户可直接访问的有效文件内容。 */
export function downloadOpenStoredFileApi(fileId: string) {
  return backendClient.get<Blob>(`/files/open/${fileId}/download`, {
    responseReturn: 'body',
    responseType: 'blob',
  });
}
