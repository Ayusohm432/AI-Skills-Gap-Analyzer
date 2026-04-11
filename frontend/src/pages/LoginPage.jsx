import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'motion/react';
import { Eye, EyeOff, Loader2, Mail, Lock } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import PageTransition from '../components/PageTransition';

function validate(email, password) {
  const errors = {};
  if (!email.trim()) {
    errors.email = 'Email is required.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Please enter a valid email address.';
  }
  if (!password) {
    errors.password = 'Password is required.';
  }
  return errors;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const from = location.state?.from?.pathname || '/dashboard';

  const [form, setForm] = useState({ email: '', password: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
    if (apiError) setApiError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const validationErrors = validate(form.email, form.password);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsLoading(true);
    setApiError('');

    try {
      await login(form.email, form.password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err.message.includes('credentials')) {
        setApiError('Invalid email or password. Please try again.');
      } else {
        setApiError('Something went wrong. Please try again later.');
      }
    } finally {
      setIsLoading(false);
    }
  }

  const inputClass = (hasError) =>
    `w-full px-4 py-3 pl-11 rounded-xl bg-[var(--bg-deep)] border text-[var(--text-primary)] placeholder-[var(--text-muted)] text-sm transition-all ${
      hasError
        ? 'border-[var(--accent-coral)]/50 focus:border-[var(--accent-coral)]'
        : 'border-[var(--border-subtle)] hover:border-[var(--border-hover)]'
    }`;

  return (
    <PageTransition>
      <div className="relative min-h-screen flex flex-col overflow-hidden">
        <InteractiveBackground />
        <Navbar />

        <main className="relative z-10 flex-1 flex items-center justify-center px-4 pt-24 pb-12">
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-md glass-card p-8 noise-overlay overflow-hidden relative"
          >
            {/* Ambient glow */}
            <div className="absolute -top-16 left-1/2 -translate-x-1/2 w-60 h-32 rounded-full blur-[70px] pointer-events-none z-0"
              style={{ background: 'radial-gradient(circle, rgba(232,168,73,0.08) 0%, transparent 70%)' }}
            />

            <div className="relative z-10">
              <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1.5">Welcome back</h1>
              <p className="text-[var(--text-muted)] text-sm mb-8">Sign in to your account to continue.</p>

              {/* API error */}
              {apiError && (
                <motion.div
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  role="alert"
                  className="mb-6 px-4 py-3 rounded-xl bg-[var(--accent-coral-dim)] border border-[var(--accent-coral)]/20 text-[var(--accent-coral)] text-sm"
                >
                  {apiError}
                </motion.div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-5">
                {/* Email */}
                <div>
                  <label htmlFor="login-email" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="login-email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      value={form.email}
                      onChange={handleChange}
                      placeholder="you@example.com"
                      aria-invalid={!!errors.email}
                      className={inputClass(errors.email)}
                    />
                  </div>
                  {errors.email && (
                    <p className="mt-1.5 text-xs text-[var(--accent-coral)]">{errors.email}</p>
                  )}
                </div>

                {/* Password */}
                <div>
                  <label htmlFor="login-password" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="login-password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={form.password}
                      onChange={handleChange}
                      placeholder="••••••••"
                      aria-invalid={!!errors.password}
                      className={inputClass(errors.password)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {errors.password && (
                    <p className="mt-1.5 text-xs text-[var(--accent-coral)]">{errors.password}</p>
                  )}
                </div>

                {/* Submit */}
                <motion.button
                  type="submit"
                  disabled={isLoading}
                  whileHover={!isLoading ? { scale: 1.01 } : {}}
                  whileTap={!isLoading ? { scale: 0.98 } : {}}
                  id="login-submit"
                  className="w-full btn-warm py-3 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isLoading && <Loader2 size={16} className="animate-spin" />}
                  {isLoading ? 'Signing in…' : 'Sign in'}
                </motion.button>
              </form>

              <p className="mt-8 text-center text-sm text-[var(--text-muted)]">
                Don&apos;t have an account?{' '}
                <Link to="/register" className="text-[var(--accent-warm)] hover:text-[#f0b85a] font-medium transition-colors">
                  Create one
                </Link>
              </p>
            </div>
          </motion.div>
        </main>
      </div>
    </PageTransition>
  );
}
