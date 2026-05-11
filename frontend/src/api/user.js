import { secureFetch } from './base';

export const getProfileApi = async () => {
  const res = await secureFetch('/api/v1/user/profile');
  if (res.ok) {
    return await res.json();
  }
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to fetch profile');
};

export const updateProfileApi = async (profileData) => {
  const res = await secureFetch('/api/v1/user/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profileData)
  });
  
  if (res.ok) {
    return await res.json();
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to update profile');
};

export const getHistoryApi = async () => {
  const res = await secureFetch('/api/v1/user/history');
  if (res.ok) {
    return await res.json();
  }
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to fetch history');
};

export const disconnectGithubApi = async () => {
  const res = await secureFetch('/api/v1/user/me/github', {
    method: 'DELETE'
  });
  if (res.ok) {
    return await res.json();
  }
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to disconnect GitHub');
};
