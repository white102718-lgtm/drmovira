import { backendClient } from '#/api/request';

interface optionData {
  name: string;
  options: string[];
  title?: string;
}

async function getAllAttribution() {
  return backendClient.get('attribution/');
}

async function updateAttribution(option: optionData) {
  return backendClient.post('attribution/', option);
}

async function createAttribution(name: string, title: string) {
  const option: optionData = {
    name,
    options: [],
    title,
  };
  return backendClient.post('attribution/', option);
}

async function deleteAttribution(name: string) {
  return backendClient.delete(`attribution/${name}`);
}

async function uploadAttributionData(formData: FormData) {
  return backendClient.post('attribution/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300_000, // 5分钟超时 (单位: 毫秒)
  });
}

export {
  createAttribution,
  deleteAttribution,
  getAllAttribution,
  updateAttribution,
  uploadAttributionData,
};
