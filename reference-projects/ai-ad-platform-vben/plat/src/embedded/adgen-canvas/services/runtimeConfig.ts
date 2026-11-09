const DEFAULT_BACKEND_URL = '/adgen-api';

const normalizeBackendUrl = (url: string) => {
  const trimmed = (url || '').trim().replace(/\/+$/, '');
  const apiIndex = trimmed.indexOf('/api/');
  if (apiIndex >= 0) {
    return trimmed.slice(0, apiIndex);
  }
  return trimmed.endsWith('/api') ? trimmed.slice(0, -4) : trimmed;
};

export const BACKEND_URL = normalizeBackendUrl(
  import.meta.env.VITE_ADGEN_BACKEND_URL || DEFAULT_BACKEND_URL,
);
export const API_BASE_URL =
  import.meta.env.VITE_ADGEN_API_BASE_URL || `${BACKEND_URL}/api`;
