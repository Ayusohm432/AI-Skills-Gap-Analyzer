import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { Eye, EyeOff, Loader2, Mail, Lock, User, Github } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import PageTransition from '../components/PageTransition';

function validate(name, email, password, confirmPassword) {
  const errors = {};

  if (!name.trim()) {
    errors.name = 'Name is required.';
  }

  if (!email.trim()) {
    errors.email = 'Email is required.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = 'Please enter a valid email address.';
  }

  if (!password) {
    errors.password = 'Password is required.';
  } else if (password.length < 8) {
    errors.password = 'Password must be at least 8 characters.';
  }

  if (!confirmPassword) {
    errors.confirmPassword = 'Please confirm your password.';
  } else if (password && confirmPassword !== password) {
    errors.confirmPassword = 'Passwords do not match.';
  }

  return errors;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const { sendSignupOtp, verifySignupOtp } = useAuth();

  const [step, setStep] = useState(1);
  const [otp, setOtp] = useState('');
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
    if (name === 'password' && errors.confirmPassword) {
      setErrors((prev) => ({ ...prev, confirmPassword: '' }));
    }
    if (apiError) setApiError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const validationErrors = validate(form.name, form.email, form.password, form.confirmPassword);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsLoading(true);
    setApiError('');

    try {
      await sendSignupOtp(form.email);
      setStep(2);
    } catch (err) {
      if (err.message.includes('exists') || err.message.includes('Registration')) {
        setApiError('An account with this email already exists.');
      } else {
        setApiError(err.message || 'Something went wrong. Please try again later.');
      }
    } finally {
      setIsLoading(false);
    }
  }

  async function handleVerify(e) {
    e.preventDefault();
    if (!otp.trim() || otp.length < 6) {
      setApiError('Please enter a valid 6-digit code.');
      return;
    }

    setIsLoading(true);
    setApiError('');

    try {
      await verifySignupOtp(form.email, otp, form.name, form.password);
      navigate('/dashboard');
    } catch (err) {
      setApiError(err.message || 'Invalid or expired code. Please try again.');
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
              style={{ background: 'radial-gradient(circle, rgba(91,184,166,0.08) 0%, transparent 70%)' }}
            />

            <div className="relative z-10">
              <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1.5">
                {step === 1 ? 'Create your account' : 'Verify your email'}
              </h1>
              <p className="text-[var(--text-muted)] text-sm mb-8">
                {step === 1 
                  ? 'Start your skill gap analysis journey.' 
                  : `We've sent a 6-digit code to ${form.email}`
                }
              </p>

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

              {step === 1 ? (
                <>
                  {/* OAuth Buttons */}
                  <div className="space-y-3 mb-6">
                <button
                  type="button"
                  onClick={() => window.location.href = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/auth/google/login`}
                  className="w-full flex items-center justify-center px-4 py-2.5 rounded-xl bg-white text-gray-800 font-medium hover:bg-gray-50 transition-colors border border-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-200 focus:ring-offset-[var(--bg-deep)]"
                >
                  <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                  </svg>
                  Continue with Google
                </button>
                <button
                  type="button"
                  onClick={() => window.location.href = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/auth/github/login`}
                  className="w-full flex items-center justify-center px-4 py-2.5 rounded-xl bg-[#24292F] text-white font-medium hover:bg-[#24292F]/90 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#24292F] focus:ring-offset-[var(--bg-deep)]"
                >
                  <Github className="w-5 h-5 mr-3" />
                  Continue with GitHub
                </button>
              </div>

              <div className="flex items-center mb-6">
                <div className="flex-grow h-px bg-[var(--border-subtle)]"></div>
                <span className="px-3 text-xs text-[var(--text-muted)] uppercase tracking-wider font-medium">Or continue with email</span>
                <div className="flex-grow h-px bg-[var(--border-subtle)]"></div>
              </div>

              <form onSubmit={handleSubmit} noValidate className="space-y-5">
                {/* Full Name */}
                <div>
                  <label htmlFor="register-name" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Full name
                  </label>
                  <div className="relative">
                    <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="register-name"
                      name="name"
                      type="text"
                      autoComplete="name"
                      value={form.name}
                      onChange={handleChange}
                      placeholder="Jane Smith"
                      aria-invalid={!!errors.name}
                      className={inputClass(errors.name)}
                    />
                  </div>
                  {errors.name && (
                    <p className="mt-1.5 text-xs text-[var(--accent-coral)]">{errors.name}</p>
                  )}
                </div>

                {/* Email */}
                <div>
                  <label htmlFor="register-email" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="register-email"
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
                  <label htmlFor="register-password" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="register-password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={form.password}
                      onChange={handleChange}
                      placeholder="Min. 8 characters"
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

                {/* Confirm Password */}
                <div>
                  <label htmlFor="register-confirm-password" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                    Confirm password
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                      id="register-confirm-password"
                      name="confirmPassword"
                      type={showConfirm ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={form.confirmPassword}
                      onChange={handleChange}
                      placeholder="••••••••"
                      aria-invalid={!!errors.confirmPassword}
                      className={inputClass(errors.confirmPassword)}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirm((v) => !v)}
                      aria-label={showConfirm ? 'Hide confirm password' : 'Show confirm password'}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                    >
                      {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {errors.confirmPassword && (
                    <p className="mt-1.5 text-xs text-[var(--accent-coral)]">{errors.confirmPassword}</p>
                  )}
                </div>

                {/* Submit */}
                <motion.button
                  type="submit"
                  disabled={isLoading}
                  whileHover={!isLoading ? { scale: 1.01 } : {}}
                  whileTap={!isLoading ? { scale: 0.98 } : {}}
                  id="register-submit"
                  className="w-full btn-warm py-3 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isLoading && <Loader2 size={16} className="animate-spin" />}
                  {isLoading ? 'Sending verification code…' : 'Create account'}
                </motion.button>
              </form>
            </>
          ) : (
            <form onSubmit={handleVerify} className="space-y-5">
              <div>
                <label htmlFor="otp-input" className="block text-sm font-medium text-[var(--text-secondary)] mb-2 text-center">
                  6-Digit Verification Code
                </label>
                <input
                  id="otp-input"
                  type="text"
                  maxLength={6}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                  className="w-full text-center tracking-[0.5em] text-2xl px-4 py-3 rounded-xl bg-[var(--bg-deep)] border border-[var(--border-subtle)] text-[var(--text-primary)] focus:border-[var(--accent-teal)]"
                  placeholder="000000"
                  autoFocus
                />
              </div>
              
              <motion.button
                type="submit"
                disabled={isLoading || otp.length < 6}
                whileHover={!(isLoading || otp.length < 6) ? { scale: 1.01 } : {}}
                whileTap={!(isLoading || otp.length < 6) ? { scale: 0.98 } : {}}
                className="w-full btn-teal py-3 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isLoading && <Loader2 size={16} className="animate-spin" />}
                {isLoading ? 'Verifying…' : 'Verify & Create Account'}
              </motion.button>
              
              <button 
                type="button"
                onClick={() => setStep(1)}
                className="w-full text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] mt-4 transition-colors"
              >
                ← Back to edit details
              </button>
            </form>
          )}

              <p className="mt-8 text-center text-sm text-[var(--text-muted)]">
                Already have an account?{' '}
                <Link to="/login" className="text-[var(--accent-warm)] hover:text-[#f0b85a] font-medium transition-colors">
                  Sign in
                </Link>
              </p>
            </div>
          </motion.div>
        </main>
      </div>
    </PageTransition>
  );
}
