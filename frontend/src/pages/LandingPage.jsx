import React from 'react';
import { Link } from 'react-router-dom';
import InteractiveBackground from '../components/InteractiveBackground';

export default function LandingPage() {
  return (
    <div className="relative min-h-screen flex flex-col font-sans overflow-hidden text-slate-200">

      <InteractiveBackground />

      {/* Navigation */}
      <nav className="relative z-10 px-8 py-6 flex justify-between items-center max-w-7xl mx-auto w-full">
        <div className="font-bold tracking-tight text-xl text-white flex items-center gap-3">
          <div className="w-6 h-6 rounded bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
            <div className="w-2 h-2 bg-white rounded-sm"></div>
          </div>
          SkillGap<span className="text-blue-400 font-normal">Analyzer</span>
        </div>
        <div className="flex gap-8 items-center text-sm font-medium tracking-wide">
          <Link to="/upload" className="text-slate-300 hover:text-white transition-colors duration-300">Upload Resume</Link>
          <Link to="/dashboard" className="text-slate-300 hover:text-white transition-colors duration-300">Sample Results</Link>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 py-24 text-center max-w-4xl mx-auto mt-10">

        <div className="inline-block border border-blue-500/30 bg-blue-900/10 px-4 py-1.5 text-xs font-semibold tracking-widest text-blue-300 rounded-full mb-8 uppercase backdrop-blur-sm shadow-[0_0_15px_rgba(59,130,246,0.15)]">
          Empowering University Students
        </div>

        <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-white mb-8 leading-[1.1] drop-shadow-2xl">
          Bridge the gap between <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-300 italic font-medium">education</span> and <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-300 to-purple-400 italic font-medium">industry</span>.
        </h1>

        <p className="text-lg md:text-xl text-slate-300 max-w-3xl mb-12 leading-relaxed font-light">
          A definitive career roadmap platform.
          Upload your resume, select your target tech role, and let our NLP engine
          uncover your missing skills to generate a personalized week-by-week learning syllabus.
        </p>

        <div className="flex flex-col sm:flex-row gap-5 w-full justify-center">
          <Link
            to="/upload"
            className="group relative px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white font-medium transition-all text-center rounded shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)] overflow-hidden"
          >
            <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-[150%] group-hover:animate-shimmer"></div>
            Start Your Analysis
          </Link>
          <Link
            to="/dashboard"
            className="px-8 py-4 bg-slate-900/50 hover:bg-slate-800 backdrop-blur-md border border-slate-700 text-slate-200 font-medium transition-all text-center rounded"
          >
            View Example Roadmap
          </Link>
        </div>
      </main>

      {/* Philosophy / Features Grid */}
      <section className="relative z-10 bg-slate-950/50 backdrop-blur-xl border-t border-slate-800/50 py-20 mt-auto">
        <div className="max-w-7xl mx-auto px-6 grid md:grid-cols-3 gap-12 text-left">

          <div className="flex flex-col group p-6 rounded-lg hover:bg-slate-900/50 transition-colors border border-transparent hover:border-slate-800">
            <div className="text-blue-500 text-3xl mb-4 font-light font-mono group-hover:scale-110 transition-transform origin-left">01.</div>
            <h3 className="text-white text-lg font-semibold mb-3 tracking-wide">Intelligent Extraction</h3>
            <p className="text-slate-400 leading-relaxed font-light text-sm">
              We process your CV using Natural Language Processing to accurately identify the tools, frameworks, and methodologies you already possess.
            </p>
          </div>

          <div className="flex flex-col group p-6 rounded-lg hover:bg-slate-900/50 transition-colors border border-transparent hover:border-slate-800">
            <div className="text-cyan-400 text-3xl mb-4 font-light font-mono group-hover:scale-110 transition-transform origin-left">02.</div>
            <h3 className="text-white text-lg font-semibold mb-3 tracking-wide">Market Alignment</h3>
            <p className="text-slate-400 leading-relaxed font-light text-sm">
              Your profile is cross-referenced against thousands of real-world job descriptions, pinpointing the exact technical requirements you are missing.
            </p>
          </div>

          <div className="flex flex-col group p-6 rounded-lg hover:bg-slate-900/50 transition-colors border border-transparent hover:border-slate-800">
            <div className="text-indigo-400 text-3xl mb-4 font-light font-mono group-hover:scale-110 transition-transform origin-left">03.</div>
            <h3 className="text-white text-lg font-semibold mb-3 tracking-wide">Structured Syllabus</h3>
            <p className="text-slate-400 leading-relaxed font-light text-sm">
              Receive a concrete, chronological learning roadmap. We map out what you need to study, week by week, to reach the market standard.
            </p>
          </div>

        </div>
      </section>
    </div>
  );
}
