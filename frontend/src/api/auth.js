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

export const sendSignupOtpApi = async (email) => {
  const res = await secureFetch('/api/v1/auth/signup/send-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  
  if (res.ok) {
    return await res.json();
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to send verification code');
};

export const verifySignupOtpApi = async (email, otp, name, password) => {
  const res = await secureFetch('/api/v1/auth/signup/verify-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, otp, name, password })
  });
  
  if (res.ok) {
    const data = await res.json();
    setAccessToken(data.access_token);
    return data;
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Verification failed');
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

export const forgotPasswordApi = async (email) => {
  const res = await secureFetch('/api/v1/auth/password/forgot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  
  if (res.ok) {
    return await res.json();
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to request password reset');
};

export const resetPasswordApi = async (email, otp, newPassword) => {
  const res = await secureFetch('/api/v1/auth/password/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, otp, new_password: newPassword })
  });
  
  if (res.ok) {
    const data = await res.json();
    setAccessToken(data.access_token);
    return data;
  }
  
  const errorData = await res.json().catch(() => ({}));
  throw new Error(errorData.detail || 'Failed to reset password');
};
