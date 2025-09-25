export const API_BASE_URL = '/api';

/**
 * 构造统一的后端接口地址，默认通过 Nginx/Vite 代理至后端服务。
 */
export const buildApiUrl = (path: string): string => {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
};

/**
 * 统一封装 fetch，便于后续扩展默认 headers 或错误处理。
 */
export const apiFetch = (path: string, init?: RequestInit) => {
  return fetch(buildApiUrl(path), init);
};
