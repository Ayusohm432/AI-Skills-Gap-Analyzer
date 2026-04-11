import { secureFetch, setAccessToken, clearAccessToken } from './base';

export const loginApi = async (email, password) => {
  const res = await secureFetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  
  if (res.ok) {
    const data = await res.json();
    setAccessToken(data.access_token);
    return data; // { access_token, token_type, user }
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Invalid credentials');
};

export const registerApi = async (name, email, password) => {
  const res = await secureFetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password })
  });
  
  if (res.ok) {
    // Phase 1 backend returns message/id, so we need to login after register 
    // or return login data. My backend returns message. 
    // Let's call login immediately after successful registration
    return loginApi(email, password);
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Registration failed');
};

export const refreshTokenApi = async () => {
  // This endpoint should expect the httpOnly cookie sent automatically
  const res = await secureFetch('/api/v1/auth/refresh', { method: 'POST' });
  
  if (res.ok) {
    const data = await res.json();
    setAccessToken(data.access_token);
    return data.access_token;
  }
  
  throw new Error('Session expired');
};

export const logoutApi = async () => {
  try {
    await secureFetch('/api/v1/auth/logout', { method: 'POST' });
  } catch (err) {
    console.error("Logout error", err);
  } finally {
    clearAccessToken();
  }
};
