import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Menu, X, LogOut, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const mobileMenuVars = {
  hidden: { x: '100%', opacity: 0 },
  visible: {
    x: 0, opacity: 1,
    transition: { type: 'spring', stiffness: 280, damping: 28, staggerChildren: 0.06, delayChildren: 0.1 }
  },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.25, ease: [0.4, 0, 1, 1] } }
};

const mobileLinkVars = {
  hidden: { opacity: 0, x: 20 },
  visible: { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
};

export default function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, user, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location]);

  const navLinks = [
    { to: '/upload', label: 'Analyze Resume' },
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/market', label: 'Market Insights' },
  ];

  if (isAuthenticated) {
    navLinks.push({ to: '/profile', label: 'Profile' });
  }

  const isActive = (path) => location.pathname === path;

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
        scrolled
          ? 'bg-[#0f0f0f]/95 border-b border-[#2a2a2a]/60 shadow-[0_4px_30px_rgba(0,0,0,0.4)]'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 lg:h-18">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2.5 group" id="nav-logo">
            <img 
              src={`${import.meta.env.BASE_URL}logo.svg`} 
              alt="SkillGap" 
              className="w-10 h-10 object-contain"
            />
            <span className="text-[var(--text-primary)] font-semibold text-lg tracking-tight">
              Skill<span className="text-[var(--accent-warm)]">Gap</span>
            </span>
          </Link>

          {/* Desktop Links */}
          <div className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                id={`nav-${link.label.toLowerCase().replace(' ', '-')}`}
                className={`relative px-4 py-2 text-sm font-medium rounded-lg transition-all duration-300 ${
                  isActive(link.to)
                    ? 'text-[var(--accent-warm)]'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]'
                }`}
              >
                {link.label}
                {isActive(link.to) && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="absolute bottom-0 left-4 right-4 h-0.5 bg-[var(--accent-warm)] rounded-full"
                    transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                  />
                )}
              </Link>
            ))}
          </div>

          {/* Desktop Auth */}
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated ? (
              <div className="flex items-center gap-4">
                <span className="text-sm text-[var(--text-muted)] flex items-center gap-2 border-r border-[var(--border-subtle)] pr-4">
                  {user?.picture ? (
                    <img src={user.picture} alt="Avatar" className="w-5 h-5 rounded-full object-cover border border-[var(--border-subtle)]" />
                  ) : (
                    <User size={14} className="text-[var(--accent-teal)]" />
                  )}
                  {user?.name || user?.email?.split('@')[0] || 'User'}
                </span>
                <button
                  onClick={async () => { await logout(); navigate('/login'); }}
                  className="text-sm font-medium px-4 py-2 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-all flex items-center gap-2 group"
                >
                  <LogOut size={14} className="group-hover:text-[var(--accent-coral)] transition-colors" />
                  Sign out
                </button>
              </div>
            ) : (
              <>
                <Link
                  to="/login"
                  id="nav-login"
                  className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors px-3 py-2"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  id="nav-register"
                  className="text-sm font-bold px-5 py-2 rounded-lg bg-[var(--accent-warm)] hover:bg-[#f0b85a] transition-all duration-300 hover:shadow-[0_4px_20px_rgba(232,168,73,0.3)] shadow-[0_2px_10px_rgba(232,168,73,0.25)]"
                  style={{ color: '#000000' }}
                >
                  Get Started
                </Link>
              </>
            )}
          </div>

          {/* Mobile Menu Toggle */}
          <motion.button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
            id="nav-mobile-toggle"
            whileTap={{ scale: 0.9 }}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={mobileOpen ? 'close' : 'open'}
                initial={{ rotate: -90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: 90, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                {mobileOpen ? <X size={20} /> : <Menu size={20} />}
              </motion.div>
            </AnimatePresence>
          </motion.button>
        </div>
      </div>

      {/* Mobile Overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
            className="md:hidden fixed inset-0 bg-black/50 z-40"
          />
        )}
      </AnimatePresence>

      {/* Mobile Menu — slide from right */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            variants={mobileMenuVars}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="md:hidden fixed top-0 right-0 h-full w-72 bg-[var(--bg-surface)] border-l border-[var(--border-subtle)] z-50 shadow-2xl flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-[var(--border-subtle)]">
              <span className="text-sm font-semibold text-[var(--text-primary)]">Menu</span>
              <motion.button
                onClick={() => setMobileOpen(false)}
                whileTap={{ scale: 0.9 }}
                className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
              >
                <X size={18} />
              </motion.button>
            </div>

            {/* Links */}
            <div className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
              {navLinks.map((link) => (
                <motion.div key={link.to} variants={mobileLinkVars}>
                  <Link
                    to={link.to}
                    className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                      isActive(link.to)
                        ? 'text-[var(--accent-warm)] bg-[var(--accent-warm-dim)] border border-[var(--accent-warm)]/20'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {isActive(link.to) && (
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-warm)] shrink-0" />
                    )}
                    {link.label}
                  </Link>
                </motion.div>
              ))}
            </div>

            {/* Auth footer */}
            <motion.div variants={mobileLinkVars} className="px-4 py-4 border-t border-[var(--border-subtle)] space-y-2">
              {isAuthenticated ? (
                <>
                  <div className="px-4 py-3 text-sm text-[var(--text-muted)] flex items-center gap-2 rounded-xl bg-[var(--bg-elevated)]">
                    {user?.picture ? (
                      <img src={user.picture} alt="Avatar" className="w-6 h-6 rounded-full object-cover border border-[var(--border-subtle)]" />
                    ) : (
                      <User size={14} className="text-[var(--accent-teal)]" />
                    )}
                    {user?.name || user?.email?.split('@')[0] || 'User'}
                  </div>
                  <button
                    onClick={async () => { await logout(); navigate('/login'); setMobileOpen(false); }}
                    className="w-full text-left px-4 py-3 rounded-xl text-sm font-medium text-[var(--accent-coral)] hover:bg-[var(--bg-elevated)] flex items-center gap-2 transition-colors"
                  >
                    <LogOut size={14} />
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link onClick={() => setMobileOpen(false)} to="/login" className="block px-4 py-3 rounded-xl text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] transition-colors">
                    Sign in
                  </Link>
                  <Link onClick={() => setMobileOpen(false)} to="/register" className="block px-4 py-3 rounded-xl text-sm font-semibold text-center bg-[var(--accent-warm)] text-black rounded-xl transition-all hover:opacity-90">
                    Get Started Free
                  </Link>
                </>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}
