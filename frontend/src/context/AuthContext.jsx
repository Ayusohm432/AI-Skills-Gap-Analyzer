import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { jwtDecode } from 'jwt-decode';
import { loginApi, registerApi, logoutApi, refreshTokenApi } from '../api/auth';
import { getAccessToken, clearAccessToken } from '../api/base';

const AuthContext = createContext({});

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  
  const refreshTimeoutRef = useRef(null);

  const clearRefreshTimeout = () => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = null;
    }
  };

  const scheduleTokenRefresh = useCallback((token) => {
    clearRefreshTimeout();
    if (!token) return;

    try {
      const decoded = jwtDecode(token);
      const expMs = decoded.exp * 1000;
      const now = Date.now();
      
      // Refresh 1 minute before expiry. If expiry is < 1 min, refresh immediately.
      // E.g., if token lives for 2 mins, delay is 1 minute (60000ms).
      const delay = Math.max(0, expMs - now - 60000); 
      
      console.log(`[Auth] Token expires in ${Math.round((expMs - now)/1000)}s. Scheduling refresh in ${Math.round(delay/1000)}s.`);

      refreshTimeoutRef.current = setTimeout(() => {
        handleSilentRefresh();
      }, delay);
    } catch (e) {
      console.error("Failed to decode token for refresh scheduling", e);
    }
  }, []);

  const handleSilentRefresh = useCallback(async () => {
    console.log("[Auth] Attempting silent background refresh...");
    try {
      const newToken = await refreshTokenApi();
      if (newToken) {
        console.log("[Auth] Refresh successful.");
        scheduleTokenRefresh(newToken);
        // We assume token payload has user info, but real backend might have a /me route
        // For now, if we already have the user state, keep it. 
        setIsAuthenticated(true);
      } else {
        throw new Error("No token returned");
      }
    } catch (err) {
      console.warn("[Auth] Silent refresh failed, user logged out.", err);
      // Only clear state if refresh explicitly fails indicating expired refresh cookie
      setUser(null);
      setIsAuthenticated(false);
      clearAccessToken();
    }
  }, [scheduleTokenRefresh]);

  // Run once on mount to establish session from httpOnly cookie
  useEffect(() => {
    const initAuth = async () => {
      try {
        await handleSilentRefresh();
        // Here you would optimally fetch the User object from a /users/me endpoint
        // For our architecture, the mock assigns a dummy user if missing 
        setUser({ name: "Demo User", email: "demo@platform.com" });
        setIsAuthenticated(true);
      } catch (err) {
        // Not logged in initially, this is normal
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };
    initAuth();

    return () => clearRefreshTimeout();
  }, [handleSilentRefresh]);

  const login = async (email, password) => {
    const data = await loginApi(email, password);
    setUser(data.user);
    setIsAuthenticated(true);
    scheduleTokenRefresh(data.access_token);
  };

  const register = async (name, email, password) => {
    const data = await registerApi(name, email, password);
    setUser(data.user);
    setIsAuthenticated(true);
    scheduleTokenRefresh(data.access_token);
  };

  const logout = async () => {
    await logoutApi();
    clearRefreshTimeout();
    setUser(null);
    setIsAuthenticated(false);
  };

  const value = {
    user,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
