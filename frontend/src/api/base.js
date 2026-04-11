export const API_URL = import.meta.env.DEV 
  ? "http://127.0.0.1:8000" 
  : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000");

// In-memory access token storage (secure against XSS)
let inMemoryAccessToken = null;

export const setAccessToken = (token) => {
  inMemoryAccessToken = token;
};

export const getAccessToken = () => {
  return inMemoryAccessToken;
};

export const clearAccessToken = () => {
  inMemoryAccessToken = null;
};

/**
 * Secure fetch wrapper that automatically attaches the in-memory access token
 * and ensures cross-origin credentials (httpOnly cookies) are included.
 */
export const secureFetch = async (endpoint, options = {}) => {
  const token = getAccessToken();
  const headers = { ...options.headers };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include' // Ensures the refresh token cookie is sent
  });
};
