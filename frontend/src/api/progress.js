import { secureFetch } from './base';

export const getProgressApi = async () => {
  const response = await secureFetch('/api/v1/user/progress');
  if (!response.ok) {
    throw new Error('Failed to fetch progress');
  }
  return response.json();
};

export const getBadgesApi = async () => {
  const response = await secureFetch('/api/v1/user/badges');
  if (!response.ok) {
    throw new Error('Failed to fetch badges');
  }
  return response.json();
};

export const recordActionApi = async (action, metadata = {}) => {
  const response = await secureFetch('/api/v1/user/progress/complete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ action, metadata }),
  });
  if (!response.ok) {
    throw new Error('Failed to record action');
  }
  return response.json();
};

export const getActionsApi = async () => {
  const response = await secureFetch('/api/v1/user/progress/actions');
  if (!response.ok) {
    throw new Error('Failed to fetch valid actions');
  }
  return response.json();
};
