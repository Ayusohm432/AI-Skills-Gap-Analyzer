import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { jwtDecode } from 'jwt-decode';
import { loginApi, registerApi, logoutApi, refreshTokenApi } from '../api/auth';
import { getAccessToken, clearAccessToken } from '../api/base';
import { getProfileApi } from '../api/user';

const AuthContext = createContext(null);

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
        
        try {
          const profile = await getProfileApi();
          setUser(profile);
          setIsAuthenticated(true);
        } catch (profileErr) {
          console.error("Failed to fetch profile after refresh", profileErr);
          throw profileErr;
        }
        return true;
      }
      return false;
    } catch (err) {
      console.warn("[Auth] Silent refresh failed, user logged out.", err);
      setUser(null);
      setIsAuthenticated(false);
      clearAccessToken();
      return false;
    }
  }, [scheduleTokenRefresh]);

  useEffect(() => {
    const initAuth = async () => {
      try {
        const success = await handleSilentRefresh();
        if (!success) {
          setIsAuthenticated(false);
          setUser(null);
        }
      } catch (err) {
        setIsAuthenticated(false);
        setUser(null);
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
    updateUserState: setUser,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout
  };

  console.log("[AuthContext] Provider initialized with value", {
    hasUser: !!value.user,
    hasUpdateFunc: typeof value.updateUserState === 'function',
    isAuthenticated: value.isAuthenticated
  });

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
