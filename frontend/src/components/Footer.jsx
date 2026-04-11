import React from 'react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="relative border-t border-[var(--border-subtle)] mt-auto">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[var(--accent-warm)] to-[var(--accent-coral)] flex items-center justify-center">
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2L14 6V10L8 14L2 10V6L8 2Z" stroke="white" strokeWidth="1.5" fill="none" />
                  <circle cx="8" cy="8" r="2" fill="white" />
                </svg>
              </div>
              <span className="text-[var(--text-primary)] font-semibold text-sm">
                Skill<span className="text-[var(--accent-warm)]">Gap</span>
              </span>
            </div>
            <p className="text-[var(--text-muted)] text-xs max-w-xs leading-relaxed">
              Bridging the distance between what you know and where you want to go. AI-powered career intelligence.
            </p>
          </div>

          {/* Links */}
          <div className="flex gap-8 text-xs text-[var(--text-muted)]">
            <div className="space-y-2">
              <p className="text-[var(--text-secondary)] font-medium uppercase tracking-wider text-[10px] mb-3">Platform</p>
              <Link to="/upload" className="block hover:text-[var(--text-primary)] transition-colors">Analyze</Link>
              <Link to="/dashboard" className="block hover:text-[var(--text-primary)] transition-colors">Dashboard</Link>
            </div>
            <div className="space-y-2">
              <p className="text-[var(--text-secondary)] font-medium uppercase tracking-wider text-[10px] mb-3">Account</p>
              <Link to="/login" className="block hover:text-[var(--text-primary)] transition-colors">Sign in</Link>
              <Link to="/register" className="block hover:text-[var(--text-primary)] transition-colors">Create account</Link>
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="mt-10 pt-6 border-t border-[var(--border-subtle)] flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-[var(--text-muted)] text-[11px]">
            © {new Date().getFullYear()} SkillGap Analyzer. Built with purpose.
          </p>
          <p className="text-[var(--text-muted)] text-[11px]">
            Powered by NLP & Machine Learning
          </p>
        </div>
      </div>
    </footer>
  );
}
