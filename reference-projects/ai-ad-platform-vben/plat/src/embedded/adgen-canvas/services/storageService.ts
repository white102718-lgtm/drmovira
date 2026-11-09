
import { AssetType } from '../types';
import type { UploadedAsset } from '../types';
import { uploadFileToMinioObject } from './minioService';

// 是否启用 MinIO 上传 (可通过环境变量控制)
const ENABLE_MINIO = import.meta.env.VITE_ENABLE_MINIO !== 'false'; // 默认启用

export const uploadToStorage = async (file: File, useMinIO: boolean = ENABLE_MINIO): Promise<UploadedAsset> => {
  const id = Math.random().toString(36).substring(7);
  let type = AssetType.FILE;

  if (file.type.startsWith('image/')) type = AssetType.IMAGE;
  else if (file.type.startsWith('video/')) type = AssetType.VIDEO;
  else if (file.type.startsWith('audio/') || /\.(mp3|wav)$/i.test(file.name))
    type = AssetType.AUDIO;
  else if (
    file.type.startsWith('text/') ||
    /\.(pdf|docx?|xlsx?|pptx?|md|key|pages|numbers)$/i.test(file.name)
  )
    type = file.type.startsWith('text/') ? AssetType.TEXT : AssetType.FILE;

  let url: string;
  let storageKey: string | undefined;

  if (useMinIO) {
    try {
      // 上传到 MinIO
      const uploaded = await uploadFileToMinioObject(file, 'uploads/');
      url = uploaded.url;
      storageKey = uploaded.object_name;
      console.log('File uploaded to MinIO:', url);
    } catch (error) {
      console.error('MinIO upload failed, falling back to local URL:', error);
      // 如果 MinIO 上传失败,回退到本地 URL
      url = URL.createObjectURL(file);
    }
  } else {
    // 创建本地对象 URL (用于即时 UI 反馈)
    url = URL.createObjectURL(file);
  }

  return {
    id,
    type,
    url,
    name: file.name,
    storageKey,
    file
  };
};

export const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const base64String = (reader.result as string).split(',')[1];
      resolve(base64String);
    };
    reader.onerror = error => reject(error);
  });
};
