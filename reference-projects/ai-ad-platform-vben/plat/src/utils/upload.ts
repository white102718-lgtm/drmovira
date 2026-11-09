export const COMPRESSED_EXTS = ['zip', 'rar', '7z', 'tar', 'gz'];
export const COMPRESSED_MIMES = [
  'application/zip',
  'application/x-zip-compressed',
  'application/x-rar-compressed',
  'application/vnd.rar',
  'application/x-7z-compressed',
  'application/x-tar',
  'application/gzip',
];

export const UPLOAD_MAX_SIZE = 10 * 1024 * 1024 * 1024; // 10GB

export function isCompressedFile(file: {
  name: string;
  type: string;
}): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase();
  return (
    COMPRESSED_EXTS.includes(ext ?? '') || COMPRESSED_MIMES.includes(file.type)
  );
}

/**
 * 校验上传文件大小
 */
export function validateUploadFileSize(
  file: { size: number },
  onError: (msg: string) => void,
): boolean {
  if (file.size > UPLOAD_MAX_SIZE) {
    onError('文件大小不能超过 10GB');
    return false;
  }
  return true;
}

/** 工单附件 / 参考资料支持的扩展名 */
export const ORDER_ATTACHMENT_IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif'];
export const ORDER_ATTACHMENT_VIDEO_EXTS = ['mp4', 'mov'];
export const ORDER_ATTACHMENT_ARCHIVE_EXTS = ['zip', '7z'];
export const ORDER_ATTACHMENT_ALLOWED_EXTS = [
  ...ORDER_ATTACHMENT_IMAGE_EXTS,
  ...ORDER_ATTACHMENT_VIDEO_EXTS,
  ...ORDER_ATTACHMENT_ARCHIVE_EXTS,
];

/** 素材库支持的扩展名 */
export const MATERIAL_IMAGE_EXTS = [
  'jpg',
  'jpeg',
  'png',
  'gif',
  'bmp',
  'tiff',
  'webp',
  'svg',
  'ico',
  'avif',
  'heic',
];
export const MATERIAL_VIDEO_EXTS = ['mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv'];
export const MATERIAL_ARCHIVE_EXTS = ['zip', '7z'];
export const MATERIAL_ALLOWED_EXTS = [
  ...MATERIAL_IMAGE_EXTS,
  ...MATERIAL_VIDEO_EXTS,
  ...MATERIAL_ARCHIVE_EXTS,
];

/** 广告创意素材支持的扩展名 */
export const AD_CREATIVE_ALLOWED_EXTS = [
  ...MATERIAL_IMAGE_EXTS,
  ...MATERIAL_VIDEO_EXTS,
];

/** 将扩展名数组转为属性字符串，如 ".png,.jpg" */
function toAcceptAttr(exts: string[]) {
  return exts.map((e) => `.${e}`).join(',');
}

export const ORDER_ATTACHMENT_ACCEPT = toAcceptAttr(
  ORDER_ATTACHMENT_ALLOWED_EXTS,
);
export const MATERIAL_ACCEPT = toAcceptAttr(MATERIAL_ALLOWED_EXTS);
export const AD_CREATIVE_ACCEPT = toAcceptAttr(AD_CREATIVE_ALLOWED_EXTS);

/**
 * 通用文件类型校验：检查文件后缀
 */
export function validateFileType(
  file: { name: string },
  allowedExts: string[],
  onError: (msg: string) => void,
): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!allowedExts.includes(ext)) {
    onError(`不支持的文件类型 .${ext || '(无后缀)'}，请检查文件格式后重新上传`);
    return false;
  }
  return true;
}
