import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import PageTransition from '../components/PageTransition';

export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { oauthLogin } = useAuth();
  const [error, setError] = useState(null);

  useEffect(() => {
    const processCallback = async () => {
      try {
        const searchParams = new URLSearchParams(location.search);
        const token = searchParams.get('token');
        const provider = searchParams.get('provider');
        
        if (!token) {
          throw new Error('No authentication token received.');
        }
        
        await oauthLogin(token);
        navigate('/dashboard', { replace: true });
      } catch (err) {
        console.error("OAuth callback processing error:", err);
        setError("Failed to complete social login. Please try again.");
        // Redirect back to login after a short delay
        setTimeout(() => navigate('/login', { replace: true }), 3000);
      }
    };

    processCallback();
  }, [location, navigate, oauthLogin]);

  return (
    <PageTransition>
      <div className="min-h-screen bg-[var(--bg-deep)] flex flex-col items-center justify-center p-4">
        {error ? (
          <div className="glass-card p-6 border border-[var(--accent-coral)]/30 text-center">
            <p className="text-[var(--accent-coral)] font-medium mb-2">{error}</p>
            <p className="text-sm text-[var(--text-muted)]">Redirecting to login...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <Loader2 size={48} className="animate-spin text-[var(--accent-lavender)]" />
            <h2 className="text-[var(--text-primary)] text-xl font-medium">
              Completing sign in...
            </h2>
            <p className="text-[var(--text-muted)] text-sm">
              Please wait while we securely log you in.
            </p>
          </div>
        )}
      </div>
    </PageTransition>
  );
}
