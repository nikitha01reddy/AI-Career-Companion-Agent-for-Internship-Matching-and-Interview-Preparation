import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_URL,
  // Auth is cookie-based (HTTP-only access/refresh tokens set by the backend).
  withCredentials: true,
});

apiClient.interceptors.request.use((config) => {
  // Required for ngrok free tier when the API is called from a browser (e.g. Vercel).
  config.headers['ngrok-skip-browser-warning'] = 'true';

  const method = config.method?.toLowerCase();
  const isFormData = typeof FormData !== 'undefined' && config.data instanceof FormData;

  // Avoid Content-Type on GET/HEAD — it triggers a CORS preflight that ngrok can block.
  if (method === 'get' || method === 'head') {
    delete config.headers['Content-Type'];
  } else if (!isFormData) {
    config.headers['Content-Type'] = 'application/json';
  }

  return config;
});

// Response interceptor to surface auth failures consistently.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    return Promise.reject(error);
  }
);