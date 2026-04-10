import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import InteractiveBackground from '../components/InteractiveBackground';

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

  const [form, setForm] = useState({ email: '', password: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    // Clear field-level error on change
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
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: form.email, password: form.password }),
      });

      if (response.ok) {
        const data = await response.json();
        localStorage.setItem('authToken', data.token ?? '');
        navigate('/dashboard');
      } else if (response.status === 401) {
        setApiError('Invalid email or password. Please try again.');
      } else {
        setApiError('Something went wrong. Please try again later.');
      }
    } catch {
      // Backend not available in this phase – simulate a successful demo login
      navigate('/dashboard');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex flex-col font-sans overflow-hidden text-slate-200">
      <InteractiveBackground />

      {/* Navigation */}
      <nav className="relative z-10 px-8 py-6 flex justify-between items-center max-w-7xl mx-auto w-full">
        <Link to="/" className="font-bold tracking-tight text-xl text-white flex items-center gap-3">
          <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
            <div className="w-2 h-2 bg-white rounded-sm"></div>
          </div>
          SkillGap<span className="text-blue-400 font-normal">Analyzer</span>
        </Link>
        <div className="text-sm text-slate-400">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
            Sign up
          </Link>
        </div>
      </nav>

      {/* Form Card */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md bg-slate-900/70 backdrop-blur-xl border border-slate-700/60 rounded-2xl p-8 shadow-2xl">
          <h1 className="text-2xl font-bold text-white mb-1">Welcome back</h1>
          <p className="text-slate-400 text-sm mb-8">Sign in to your account to continue.</p>

          {/* API / server-level error */}
          {apiError && (
            <div role="alert" className="mb-6 px-4 py-3 rounded-lg bg-red-900/40 border border-red-700/60 text-red-300 text-sm">
              {apiError}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            {/* Email */}
            <div>
              <label htmlFor="login-email" className="block text-sm font-medium text-slate-300 mb-1.5">
                Email address
              </label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                value={form.email}
                onChange={handleChange}
                placeholder="you@example.com"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? 'login-email-error' : undefined}
                className={`w-full px-4 py-2.5 rounded-lg bg-slate-800/80 border text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 transition-colors ${
                  errors.email
                    ? 'border-red-500/70 focus:ring-red-500/40'
                    : 'border-slate-700 focus:ring-blue-500/40 focus:border-blue-500/70'
                }`}
              />
              {errors.email && (
                <p id="login-email-error" className="mt-1.5 text-xs text-red-400">
                  {errors.email}
                </p>
              )}
            </div>

            {/* Password */}
            <div>
              <label htmlFor="login-password" className="block text-sm font-medium text-slate-300 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="••••••••"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'login-password-error' : undefined}
                  className={`w-full px-4 py-2.5 pr-11 rounded-lg bg-slate-800/80 border text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 transition-colors ${
                    errors.password
                      ? 'border-red-500/70 focus:ring-red-500/40'
                      : 'border-slate-700 focus:ring-blue-500/40 focus:border-blue-500/70'
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-200 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && (
                <p id="login-password-error" className="mt-1.5 text-xs text-red-400">
                  {errors.password}
                </p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg text-sm transition-colors shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] flex items-center justify-center gap-2"
            >
              {isLoading && <Loader2 size={16} className="animate-spin" />}
              {isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Don&apos;t have an account?{' '}
            <Link to="/register" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
              Create one
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
