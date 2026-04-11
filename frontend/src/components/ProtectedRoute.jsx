import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2 } from 'lucide-react';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-deep)]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 size={32} className="animate-spin text-[var(--accent-warm)]" />
          <p className="text-sm font-medium text-[var(--text-muted)] tracking-wide">
            Verifying secure session...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login, preserving the intended destination in react-router state
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}
