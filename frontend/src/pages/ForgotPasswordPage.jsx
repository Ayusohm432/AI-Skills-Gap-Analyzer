import React, { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Mail, Lock, Eye, EyeOff, Loader2, ArrowLeft, CheckCircle2, ShieldCheck, Hash } from 'lucide-react';
import { forgotPasswordApi, resetPasswordApi } from '../api/auth';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import PageTransition from '../components/PageTransition';

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: Request, 2: Reset
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const inputRef = useRef(null);

  useEffect(() => {
    if (step === 2 && inputRef.current) {
      inputRef.current.focus();
    }
  }, [step]);

  const handleRequestReset = async (e) => {
    e.preventDefault();
    if (!email) {
      setError('Email is required.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Please enter a valid email address.');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      await forgotPasswordApi(email);
      setStep(2);
      setSuccess('Verification code sent to your email.');
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (!otp || otp.length < 6) {
      setError('Please enter the 6-digit verification code.');
      return;
    }
    if (!newPassword || newPassword.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      await resetPasswordApi(email, otp, newPassword);
      setSuccess('Password reset successful! Redirecting to dashboard...');
      setTimeout(() => {
        navigate('/dashboard');
      }, 2000);
    } catch (err) {
      setError(err.message || 'Invalid code or something went wrong.');
    } finally {
      setIsLoading(false);
    }
  };

  const inputClass = (hasError) =>
    `w-full px-4 py-3 pl-11 rounded-xl bg-[var(--bg-deep)] border text-[var(--text-primary)] placeholder-[var(--text-muted)] text-sm transition-all ${
      hasError
        ? 'border-[var(--accent-coral)]/50 focus:border-[var(--accent-coral)]'
        : 'border-[var(--border-subtle)] hover:border-[var(--border-hover)]'
    }`;

  const containerVariants = {
    hidden: { opacity: 0, y: 20, scale: 0.98 },
    visible: { 
      opacity: 1, 
      y: 0, 
      scale: 1,
      transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] }
    },
    exit: { 
      opacity: 0, 
      y: -20, 
      scale: 0.98,
      transition: { duration: 0.3, ease: 'easeInOut' }
    }
  };

  return (
    <PageTransition>
      <div className="relative min-h-screen flex flex-col overflow-hidden">
        <InteractiveBackground />
        <Navbar />

        <main className="relative z-10 flex-1 flex items-center justify-center px-4 pt-24 pb-12">
          <AnimatePresence mode="wait">
            {step === 1 ? (
              <motion.div
                key="step1"
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                className="w-full max-w-md glass-card p-8 noise-overlay overflow-hidden relative"
              >
                <div className="absolute -top-16 left-1/2 -translate-x-1/2 w-60 h-32 rounded-full blur-[70px] pointer-events-none z-0"
                  style={{ background: 'radial-gradient(circle, rgba(232,168,73,0.08) 0%, transparent 70%)' }}
                />

                <div className="relative z-10">
                  <Link to="/login" className="inline-flex items-center text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors mb-6 group">
                    <ArrowLeft size={14} className="mr-1 group-hover:-translate-x-1 transition-transform" />
                    Back to login
                  </Link>

                  <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1.5 flex items-center gap-2">
                    <ShieldCheck className="text-[var(--accent-warm)]" />
                    Forgot password?
                  </h1>
                  <p className="text-[var(--text-muted)] text-sm mb-8">Enter your email and we'll send you a 6-digit code to reset your password.</p>

                  {error && (
                    <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} className="mb-6 px-4 py-3 rounded-xl bg-[var(--accent-coral-dim)] border border-[var(--accent-coral)]/20 text-[var(--accent-coral)] text-sm">
                      {error}
                    </motion.div>
                  )}

                  <form onSubmit={handleRequestReset} className="space-y-5">
                    <div>
                      <label htmlFor="email" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">Email address</label>
                      <div className="relative">
                        <Mail size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                        <input
                          id="email"
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="you@example.com"
                          className={inputClass(!!error)}
                          disabled={isLoading}
                        />
                      </div>
                    </div>

                    <motion.button
                      type="submit"
                      disabled={isLoading}
                      whileHover={!isLoading ? { scale: 1.01 } : {}}
                      whileTap={!isLoading ? { scale: 0.98 } : {}}
                      className="w-full btn-warm py-3 disabled:opacity-60 flex items-center justify-center gap-2"
                    >
                      {isLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                      {isLoading ? 'Sending code...' : 'Send reset code'}
                    </motion.button>
                  </form>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="step2"
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
                className="w-full max-w-md glass-card p-8 noise-overlay overflow-hidden relative"
              >
                <div className="absolute -top-16 left-1/2 -translate-x-1/2 w-60 h-32 rounded-full blur-[70px] pointer-events-none z-0"
                  style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 70%)' }}
                />

                <div className="relative z-10">
                  <button onClick={() => setStep(1)} className="inline-flex items-center text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors mb-6 group">
                    <ArrowLeft size={14} className="mr-1 group-hover:-translate-x-1 transition-transform" />
                    Change email
                  </button>

                  <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1.5 flex items-center gap-2">
                    <Lock className="text-[var(--accent-teal)]" />
                    Reset password
                  </h1>
                  <p className="text-[var(--text-muted)] text-sm mb-8">We sent a 6-digit code to <span className="text-[var(--text-primary)] font-medium">{email}</span>. Please enter it below along with your new password.</p>

                  {success && !isLoading && (
                    <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} className="mb-6 px-4 py-3 rounded-xl bg-[var(--accent-teal-dim)] border border-[var(--accent-teal)]/20 text-[var(--accent-teal)] text-sm flex items-center gap-2">
                      <CheckCircle2 size={16} />
                      {success}
                    </motion.div>
                  )}

                  {error && (
                    <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} className="mb-6 px-4 py-3 rounded-xl bg-[var(--accent-coral-dim)] border border-[var(--accent-coral)]/20 text-[var(--accent-coral)] text-sm">
                      {error}
                    </motion.div>
                  )}

                  <form onSubmit={handleResetPassword} className="space-y-5">
                    <div>
                      <label htmlFor="otp" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">Verification Code</label>
                      <div className="relative">
                        <Hash size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                        <input
                          ref={inputRef}
                          id="otp"
                          type="text"
                          maxLength={6}
                          value={otp}
                          onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                          placeholder="123456"
                          className={inputClass(!!error && !otp)}
                          disabled={isLoading}
                        />
                      </div>
                    </div>

                    <div>
                      <label htmlFor="new-password" className="block text-sm font-medium text-[var(--text-secondary)] mb-2">New Password</label>
                      <div className="relative">
                        <Lock size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                        <input
                          id="new-password"
                          type={showPassword ? 'text' : 'password'}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="at least 8 characters"
                          className={inputClass(!!error && !newPassword)}
                          disabled={isLoading}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((v) => !v)}
                          className="absolute inset-y-0 right-0 flex items-center px-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                        >
                          {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>

                    <motion.button
                      type="submit"
                      disabled={isLoading}
                      whileHover={!isLoading ? { scale: 1.01 } : {}}
                      whileTap={!isLoading ? { scale: 0.98 } : {}}
                      className="w-full btn-warm py-3 disabled:opacity-60 flex items-center justify-center gap-2"
                    >
                      {isLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                      {isLoading ? 'Resetting password...' : 'Reset password'}
                    </motion.button>
                  </form>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </PageTransition>
  );
}
