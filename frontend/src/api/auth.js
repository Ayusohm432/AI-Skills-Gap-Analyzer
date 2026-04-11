import { secureFetch, setAccessToken, clearAccessToken } from './base';

// ==========================================
// MOCK JWT HELPERS FOR FRONTEND TESTING
// ==========================================
// Generates a parseable JWT header.payload.signature
const createMockJwt = (expMinutes = 2) => {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({
    sub: 'user123',
    email: 'mock@example.com',
    role: 'user',
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + (expMinutes * 60)
  }));
  const signature = 'mock_signature_does_not_matter_on_frontend';
  return `${header}.${payload}.${signature}`;
};

// ==========================================
// REAL API ENDPOINTS WITH MOCK FALLBACKS
// ==========================================

export const loginApi = async (email, password) => {
  try {
    const res = await secureFetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    if (res.ok) {
      const data = await res.json();
      setAccessToken(data.access_token);
      return data; // { access_token, user }
    }
    
    // If endpoint doesn't exist yet, gracefully mock it to test UI
    if (res.status === 404) throw new Error("Mock");
    
    throw new Error('Invalid credentials');
  } catch (err) {
    if (err.message === "Mock" || err.message.includes("Failed to fetch")) {
      console.warn("Backend auth missing. Using Mock Login.");
      const mockToken = createMockJwt(2); // Expires in 2 minutes
      setAccessToken(mockToken);
      return { 
        access_token: mockToken, 
        user: { id: 'mock-1', email, name: email.split('@')[0] } 
      };
    }
    throw err;
  }
};

export const registerApi = async (name, email, password) => {
  try {
    const res = await secureFetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password })
    });
    
    if (res.ok) {
      const data = await res.json();
      setAccessToken(data.access_token);
      return data;
    }
    
    if (res.status === 404) throw new Error("Mock");
    throw new Error('Registration failed');
  } catch (err) {
    if (err.message === "Mock" || err.message.includes("Failed to fetch")) {
      console.warn("Backend auth missing. Using Mock Register.");
      const mockToken = createMockJwt(2);
      setAccessToken(mockToken);
      return { 
        access_token: mockToken, 
        user: { id: 'mock-2', email, name } 
      };
    }
    throw err;
  }
}

export const refreshTokenApi = async () => {
  try {
    // This endpoint should expect the httpOnly cookie sent automatically
    const res = await secureFetch('/api/v1/auth/refresh', { method: 'POST' });
    
    if (res.ok) {
      const data = await res.json();
      setAccessToken(data.access_token);
      return data.access_token;
    }
    
    if (res.status === 404) throw new Error("Mock");
    throw new Error('Session expired');
  } catch (err) {
    if (err.message === "Mock" || err.message.includes("Failed to fetch")) {
      console.log("Mock refreshing token...");
      const mockToken = createMockJwt(2);
      setAccessToken(mockToken);
      return mockToken;
    }
    throw err;
  }
};

export const logoutApi = async () => {
  try {
    await secureFetch('/api/v1/auth/logout', { method: 'POST' });
  } catch (err) {
    console.log("Mock logout"); // fallback
  } finally {
    clearAccessToken();
  }
};
