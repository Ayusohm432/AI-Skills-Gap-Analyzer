import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowRight, Sparkles, Target, BookOpen, TrendingUp, Upload, Zap, GraduationCap } from 'lucide-react';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';
import PageTransition from '../components/PageTransition';

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.6, ease: [0.22, 1, 0.36, 1] }
  })
};

const stats = [
  { value: '10+', label: 'Tech Roles Covered' },
  { value: '50+', label: 'Skills Tracked' },
  { value: '8wk', label: 'Avg. Roadmap Length' },
];

const features = [
  {
    icon: Upload,
    title: 'Drop Your Resume',
    desc: 'Upload your CV and we parse it using advanced NLP — no templates, no forms, just your real document.',
    accent: 'var(--accent-warm)',
    accentDim: 'var(--accent-warm-dim)',
  },
  {
    icon: Target,
    title: 'See What\'s Missing',
    desc: 'We compare your skills against real job requirements and show you exactly which gaps are holding you back.',
    accent: 'var(--accent-coral)',
    accentDim: 'var(--accent-coral-dim)',
  },
  {
    icon: BookOpen,
    title: 'Get Your Roadmap',
    desc: 'Receive a structured, week-by-week learning plan built around your specific missing skills — not generic advice.',
    accent: 'var(--accent-teal)',
    accentDim: 'var(--accent-teal-dim)',
  },
];

// Static university/institution social-proof entries
const trustedBy = [
  'GCE Gaya', 'NCE Chandi', 'NIT Patna', 'IIIT Bhagalpur', 'BCE Patna', 'MIT Muzaffarpur',
];

export default function LandingPage() {
  return (
    <PageTransition>
      <div className="relative min-h-screen flex flex-col overflow-hidden">
        <InteractiveBackground />
        <Navbar />

        {/* ===== HERO ===== */}
        <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 pt-32 pb-20 lg:pt-40 lg:pb-28">
          <div className="max-w-5xl mx-auto w-full">
            {/* Badge */}
            <motion.div
              variants={fadeUp} initial="hidden" animate="visible" custom={0}
              className="flex justify-center mb-8"
            >
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)]/80">
                <Sparkles size={14} className="text-[var(--accent-warm)]" />
                <span className="text-xs font-medium text-[var(--text-muted)] tracking-wide">
                  Your career, intelligently mapped
                </span>
              </div>
            </motion.div>

            {/* Headline */}
            <motion.h1
              variants={fadeUp} initial="hidden" animate="visible" custom={1}
              className="text-center text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tight leading-[1.08] mb-7"
            >
              <span className="text-[var(--text-primary)] font-semibold">Find what's </span>
              <span className="font-serif italic text-[var(--accent-warm)]">missing</span>
              <br />
              <span className="text-[var(--text-primary)] font-semibold">between you &amp; your </span>
              <span className="font-serif italic text-[var(--accent-teal)]">dream role</span>
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              variants={fadeUp} initial="hidden" animate="visible" custom={2}
              className="text-center text-base md:text-lg text-[var(--text-secondary)] max-w-2xl mx-auto mb-12 font-light leading-relaxed"
            >
              Upload your resume, pick a target role, and our NLP engine will identify
              your skill gaps — then generate a personalized learning roadmap to close them.
            </motion.p>

            {/* CTAs */}
            <motion.div
              variants={fadeUp} initial="hidden" animate="visible" custom={3}
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
            >
              {/* Shimmer CTA Button */}
              <Link to="/upload" id="hero-cta-primary" className="relative group overflow-hidden btn-warm">
                <span className="relative z-10 flex items-center gap-2">
                  Start Your Analysis
                  <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
                </span>
                {/* Shimmer effect */}
                <span className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-in-out bg-gradient-to-r from-transparent via-white/25 to-transparent skew-x-12 pointer-events-none" />
              </Link>
              <Link to="/dashboard" className="btn-ghost" id="hero-cta-secondary">
                See Example Results
              </Link>
            </motion.div>

            {/* Stats Row */}
            <motion.div
              variants={fadeUp} initial="hidden" animate="visible" custom={4}
              className="flex items-center justify-center gap-10 mt-16"
            >
              {stats.map((stat, i) => (
                <div key={i} className="text-center">
                  <div className="text-2xl md:text-3xl font-bold text-[var(--text-primary)]">{stat.value}</div>
                  <div className="text-[11px] text-[var(--text-muted)] mt-1 uppercase tracking-wider">{stat.label}</div>
                </div>
              ))}
            </motion.div>
          </div>
        </main>

        {/* ===== TRUSTED BY STUDENTS ===== */}
        <section className="relative z-10 py-10 border-y border-[var(--border-subtle)]">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="max-w-5xl mx-auto px-6"
          >
            <div className="flex flex-col items-center gap-6">
              <div className="flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest">
                <GraduationCap size={14} className="text-[var(--accent-lavender)]" />
                Trusted by students from
              </div>
              <div className="flex flex-wrap items-center justify-center gap-3">
                {trustedBy.map((name, i) => (
                  <motion.div
                    key={name}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.07, duration: 0.4, type: 'spring' }}
                    className="px-4 py-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-surface)]/60 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent-lavender)]/40 hover:text-[var(--text-primary)] transition-all duration-300"
                  >
                    {name}
                  </motion.div>
                ))}
              </div>
            </div>
          </motion.div>
        </section>

        {/* ===== HOW IT WORKS ===== */}
        <section className="relative z-10 py-24 lg:py-32">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-100px' }}
              transition={{ duration: 0.6 }}
              className="text-center mb-16"
            >
              <p className="text-[var(--accent-warm)] uppercase tracking-[0.2em] text-xs font-semibold mb-4">How it works</p>
              <h2 className="text-3xl md:text-4xl font-semibold text-[var(--text-primary)] tracking-tight">
                Three steps to <span className="font-serif italic font-normal text-[var(--accent-teal)]">clarity</span>
              </h2>
            </motion.div>

            <div className="grid md:grid-cols-3 gap-6 lg:gap-8">
              {features.map((f, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 40 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: i * 0.15, duration: 0.55, type: 'spring', stiffness: 200, damping: 22 }}
                  whileHover={{ y: -6, transition: { duration: 0.2 } }}
                  className="group relative glass-card p-8 transition-all duration-500 noise-overlay overflow-hidden cursor-default"
                >
                  {/* Accent line top */}
                  <div
                    className="absolute top-0 left-8 right-8 h-[2px] rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                    style={{ background: f.accent }}
                  />
                  {/* Glow blob */}
                  <div
                    className="absolute -bottom-10 -right-10 w-32 h-32 rounded-full blur-3xl opacity-0 group-hover:opacity-20 transition-opacity duration-500"
                    style={{ backgroundColor: f.accent }}
                  />

                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-6">
                      <div
                        className="w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-300 group-hover:scale-110"
                        style={{ background: f.accentDim }}
                      >
                        <f.icon size={20} style={{ color: f.accent }} />
                      </div>
                      <span className="text-[var(--text-muted)] text-xs font-mono">0{i + 1}</span>
                    </div>

                    <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-3 tracking-tight">{f.title}</h3>
                    <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{f.desc}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ===== CTA BAND ===== */}
        <section className="relative z-10 py-20 lg:py-24">
          <div className="max-w-4xl mx-auto px-6 text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: '-100px' }}
              transition={{ duration: 0.6 }}
              className="glass-card p-12 lg:p-16 relative overflow-hidden noise-overlay glow-warm"
            >
              <div className="relative z-10">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-[var(--accent-warm-dim)] flex items-center justify-center mb-6">
                  <Zap size={24} className="text-[var(--accent-warm)]" />
                </div>
                <h2 className="text-2xl md:text-3xl font-semibold text-[var(--text-primary)] mb-4 tracking-tight">
                  Ready to see where you stand?
                </h2>
                <p className="text-[var(--text-secondary)] max-w-lg mx-auto mb-8 font-light">
                  It takes less than a minute. Upload your resume, choose a role, and get your personalized skill gap report instantly.
                </p>
                <Link to="/upload" id="cta-band-button" className="relative group overflow-hidden btn-warm inline-flex">
                  <span className="relative z-10 flex items-center gap-2">
                    Analyze My Resume
                    <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
                  </span>
                  <span className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-in-out bg-gradient-to-r from-transparent via-white/25 to-transparent skew-x-12 pointer-events-none" />
                </Link>
              </div>
            </motion.div>
          </div>
        </section>

        <Footer />
      </div>
    </PageTransition>
  );
}
