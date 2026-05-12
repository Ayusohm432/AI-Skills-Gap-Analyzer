import React, { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, PieChart, Pie } from "recharts";
import { jsPDF } from 'jspdf';
import { toPng } from 'html-to-image';
import {
  CheckCircle2, XCircle, Zap, Download, MessageSquare,
  ChevronRight, ArrowLeft, BookOpen, Loader2, Target, BarChart2, Activity, Filter, RefreshCw,
  Check, ExternalLink, Clock, Trophy, Bot, Share2, Sparkles, Play
} from "lucide-react";
import InteractiveBackground from "../components/InteractiveBackground";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";
import PageTransition from "../components/PageTransition";
import InterviewPanel from "../components/InterviewPanel";
import { secureFetch } from "../api/base";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { delay, type: 'spring', stiffness: 260, damping: 20 }
});

// Respect prefers-reduced-motion (ui-ux-pro-max: Severity High)
function useReducedMotion() {
  const [reduced, setReduced] = React.useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e) => setReduced(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return reduced;
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  const [userSelectedRole, setUserSelectedRole] = useState("Auto Detect");
  const [chartView, setChartView] = useState("radar"); // "radar" | "bar"
  const [selectedCategory, setSelectedCategory] = useState(null); // donut filter
  const [activeDonutIndex, setActiveDonutIndex] = useState(null); // interactive ring chart
  const [isSwapping, setIsSwapping] = useState(false); // role swap loading
  const [swapError, setSwapError] = useState(null);
  
  // Issue #53: Interview Panel State
  const [isInterviewActive, setIsInterviewActive] = useState(false);
  const swapPollRef = useRef(null);
  const prefersReducedMotion = useReducedMotion();

  // Readiness Levels state (Issue #135)
  const [readinessLevels, setReadinessLevels] = useState(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const readinessFetchedFor = useRef(null);
  const [selectedLevel, setSelectedLevel] = useState(null); // null | 'beginner' | 'intermediate' | 'advanced'
  const [readinessView, setReadinessView] = useState('overall'); // 'overall' | 'beginner' | 'intermediate' | 'advanced'
  const [isSharing, setIsSharing] = useState(false);
  const shareRef = useRef(null);

  // Cleanup swap polling on unmount
  useEffect(() => {
    return () => {
      if (swapPollRef.current) {
        clearInterval(swapPollRef.current);
        swapPollRef.current = null;
      }
    };
  }, []);

  // Disable motion for users who prefer it
  const safeMotion = (delay = 0) => prefersReducedMotion
    ? { initial: false, animate: {}, transition: {} }
    : fadeUp(delay);

  useEffect(() => {
    const saved = localStorage.getItem("analysisResult");
    if (saved) {
      const parsed = JSON.parse(saved);
      setData(parsed);

      // When viewing a historical report the analysis already knows its own role.
      // Always prefer the role stored IN the analysis over the stale
      // "userSelectedRole" key (which reflects the most recent upload session,
      // not the historical one being viewed).
      const roleFromAnalysis = parsed.predicted_role || parsed.target_role;
      if (roleFromAnalysis) {
        setUserSelectedRole(roleFromAnalysis);
      } else {
        // Fallback: restore from localStorage for the original upload flow
        const savedRole = localStorage.getItem("userSelectedRole");
        if (savedRole) setUserSelectedRole(savedRole);
      }
    } else {
      // Restore role preference for the upload flow (no stored analysis)
      const savedRole = localStorage.getItem("userSelectedRole");
      if (savedRole) setUserSelectedRole(savedRole);

      // Mock data if accessed directly
      setData({
        job_id: "DEMO-123",
        target_role: "Data Scientist",
        predicted_role: "Machine Learning Engineer",
        role_confidence: 84.5,
        role_alternatives: ["Data Scientist", "Backend Developer"],
        skills_detected: ['Python', 'NumPy', 'Pandas', 'Statistics', 'SQL', 'Git'],
        missing_skills: ['TensorFlow', 'Docker', 'MLOps', 'AWS', 'PyTorch'],
        readiness_score: 58,
        roadmap: [
          { week: "Week 1-2", focus: "Deep Learning Foundations with TensorFlow", resources: ["TensorFlow Official Tutorials", "Stanford CS231n Lecture Notes"] },
          { week: "Week 3-4", focus: "Container Orchestration with Docker", resources: ["Docker Getting Started Guide", "Play with Docker Labs"] },
          { week: "Week 5-6", focus: "Cloud Infrastructure on AWS", resources: ["AWS Free Tier Hands-On", "AWS Certified Cloud Practitioner Prep"] },
          { week: "Week 7-8", focus: "MLOps Pipeline Design", resources: ["MLflow Documentation", "Made With ML - MLOps Course"] }
        ],
        interview_questions: [
          "Explain the difference between overfitting and underfitting. How would you detect each?",
          "How would you deploy a deep learning model to production using Docker?",
          "Walk me through designing an end-to-end ML pipeline with monitoring.",
          "What are the trade-offs between TensorFlow and PyTorch for production systems?"
        ],
        skill_categories: {
          languages: ["Python"],
          data: ["NumPy", "Pandas", "Statistics", "SQL"],
          frontend: [],
          backend: [],
          cloud_devops: ["Git"],
          ml_ai: [],
        },
        missing_skills_ranked: [
          { skill: "TensorFlow", likelihood: 0.91, category: "ml_ai", priority: "high" },
          { skill: "Docker", likelihood: 0.87, category: "cloud_devops", priority: "high" },
          { skill: "MLOps", likelihood: 0.78, category: "mlops", priority: "high" },
          { skill: "AWS", likelihood: 0.65, category: "cloud_devops", priority: "medium" },
          { skill: "PyTorch", likelihood: 0.61, category: "ml_ai", priority: "medium" },
        ],
      });
    }
  }, []);

  // ── Roadmap completion tracking (Issue #52) ──────────────────────────
  const [completedWeeks, setCompletedWeeks] = useState(() => {
    try {
      const saved = localStorage.getItem("roadmapCompletedWeeks");
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch { return new Set(); }
  });

  // Reset completed weeks when data changes (e.g. after role swap)
  const prevAnalysisId = useRef(null);
  useEffect(() => {
    const currentId = data?.analysis_id;
    if (currentId && currentId !== prevAnalysisId.current) {
      prevAnalysisId.current = currentId;
      // Try to load from localStorage for this analysis
      try {
        const saved = localStorage.getItem(`roadmapCompleted_${currentId}`);
        setCompletedWeeks(saved ? new Set(JSON.parse(saved)) : new Set());
      } catch { setCompletedWeeks(new Set()); }
    }
  }, [data?.analysis_id]);

  const toggleWeekComplete = useCallback((weekIdx) => {
    setCompletedWeeks(prev => {
      const next = new Set(prev);
      if (next.has(weekIdx)) {
        next.delete(weekIdx);
      } else {
        next.add(weekIdx);
      }

      // Persist to localStorage
      const arr = [...next];
      localStorage.setItem("roadmapCompletedWeeks", JSON.stringify(arr));
      if (data?.analysis_id) {
        localStorage.setItem(`roadmapCompleted_${data.analysis_id}`, JSON.stringify(arr));
      }

      // Persist to backend (fire-and-forget)
      if (data?.analysis_id) {
        secureFetch('/api/v1/user/roadmap-progress', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            analysis_id: data.analysis_id,
            completed_weeks: arr,
          }),
        }).catch(() => {}); // silent fail — localStorage is primary
      }

      return next;
    });
  }, [data?.analysis_id]);

  // Fetch readiness levels when we have a role and data
  useEffect(() => {
    const role = data?.predicted_role || data?.target_role;
    if (!role || readinessFetchedFor.current === role) return;
    readinessFetchedFor.current = role;
    setReadinessLoading(true);
    setReadinessLevels(null);
    secureFetch(`/api/v1/readiness/levels?role=${encodeURIComponent(role)}`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => setReadinessLevels(d))
      .catch(() => setReadinessLevels(null))
      .finally(() => setReadinessLoading(false));
  }, [data?.predicted_role, data?.target_role]);

  if (!data) {
    return (
      <PageTransition>
        <div className="min-h-screen flex items-center justify-center bg-[var(--bg-deep)]">
          <Loader2 className="animate-spin text-[var(--accent-warm)]" size={40} />
        </div>
      </PageTransition>
    );
  }

  // ── Role swap handler (Issue #51) ──────────────────────────────────
  const handleRoleSwap = async (newRole) => {
    // Retrieve cached resume from sessionStorage
    const base64 = sessionStorage.getItem("resumeFileBase64");
    const fileName = sessionStorage.getItem("resumeFileName") || "resume.pdf";
    const contentType = sessionStorage.getItem("resumeContentType") || "application/pdf";

    if (!base64) {
      setSwapError("Resume not cached. Please re-upload from the Upload page.");
      return;
    }

    setIsSwapping(true);
    setSwapError(null);

    try {
      // Convert base64 back to File
      const res = await fetch(base64);
      const blob = await res.blob();
      const file = new File([blob], fileName, { type: contentType });

      // Submit with the new role
      const formData = new FormData();
      formData.append("resume", file);
      formData.append("role", newRole);

      const submitRes = await secureFetch('/api/v1/analyze/resume', {
        method: "POST",
        body: formData,
      });

      if (!submitRes.ok) {
        const errData = await submitRes.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${submitRes.status}`);
      }

      const { job_id } = await submitRes.json();

      // Poll until completed
      const result = await new Promise((resolve, reject) => {
        swapPollRef.current = setInterval(async () => {
          try {
            const pollRes = await secureFetch(`/api/v1/jobs/${job_id}`);
            if (!pollRes.ok) {
              clearInterval(swapPollRef.current);
              swapPollRef.current = null;
              reject(new Error(`Poll error: ${pollRes.status}`));
              return;
            }
            const jobData = await pollRes.json();
            if (jobData.status === "completed") {
              clearInterval(swapPollRef.current);
              swapPollRef.current = null;
              resolve(jobData.result);
            } else if (jobData.status === "failed") {
              clearInterval(swapPollRef.current);
              swapPollRef.current = null;
              reject(new Error(jobData.error || "Re-analysis failed."));
            }
          } catch (err) {
            clearInterval(swapPollRef.current);
            swapPollRef.current = null;
            reject(err);
          }
        }, 2000);
      });

      // Update dashboard data
      setData(result);
      setUserSelectedRole(newRole);
      localStorage.setItem("analysisResult", JSON.stringify(result));
      localStorage.setItem("userSelectedRole", newRole);
      setSelectedCategory(null); // reset donut filter
    } catch (err) {
      console.error("Role swap failed:", err);
      setSwapError(err.message || "Role swap failed. Try again.");
    } finally {
      setIsSwapping(false);
    }
  };

  const handleExportPDF = () => {
    if (!data) return;
    setIsExporting(true);

    setTimeout(() => {
      try {
        const doc = new jsPDF();
        doc.setFont("helvetica", "bold");
        doc.setFontSize(22);
        doc.setTextColor(232, 168, 73);
        doc.text("Your Personalized Roadmap", 105, 20, { align: "center" });

        doc.setFontSize(14);
        doc.setTextColor(60, 60, 60);
        doc.text(`Target Role: ${data.target_role || 'Unknown'}`, 20, 35);
        doc.text(`Readiness Score: ${Math.round(data.readiness_score || 0)}%`, 20, 42);

        doc.setLineWidth(0.5);
        doc.setDrawColor(200, 200, 200);
        doc.line(20, 48, 190, 48);

        let yPos = 60;

        if (!data.roadmap || data.roadmap.length === 0) {
          doc.setFont("helvetica", "normal");
          doc.setFontSize(12);
          doc.text("No roadmap needed — you're ready for this role!", 20, yPos);
        } else {
          data.roadmap.forEach((step, idx) => {
            if (yPos > 260) { doc.addPage(); yPos = 20; }

            doc.setFont("helvetica", "bold");
            doc.setFontSize(12);
            doc.setTextColor(232, 168, 73);
            doc.text(`PHASE ${idx + 1}: ${step.week}`, 20, yPos);
            yPos += 7;

            doc.setFont("helvetica", "bold");
            doc.setTextColor(30, 30, 30);
            const focusLines = doc.splitTextToSize(step.focus, 170);
            doc.text(focusLines, 20, yPos);
            yPos += (focusLines.length * 6) + 2;

            doc.setFont("helvetica", "normal");
            doc.setFontSize(11);
            doc.setTextColor(100, 100, 100);

            if (step.resources && step.resources.length > 0) {
              step.resources.forEach(res => {
                const resLines = doc.splitTextToSize(`• ${res}`, 160);
                doc.text(resLines, 25, yPos);
                yPos += (resLines.length * 6);
              });
            }
            yPos += 10;
          });
        }

        doc.save(`SkillGap_Roadmap_${data.target_role?.replace(/\s+/g, '_') || 'Export'}.pdf`);
      } catch (error) {
        console.error("Error generating PDF:", error);
        alert("Failed to generate PDF document.");
      } finally {
        setIsExporting(false);
      }
    }, 100);
  };

  const handleShareResults = async () => {
    if (!shareRef.current) return;
    setIsSharing(true);
    try {
      const dataUrl = await toPng(shareRef.current, {
        backgroundColor: '#0f0f0f',
        pixelRatio: 2,
      });
      const link = document.createElement('a');
      link.download = `SkillGap_Results_${data.target_role?.replace(/\s+/g, '_') || 'Report'}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error('Share screenshot failed:', err);
    } finally {
      setIsSharing(false);
    }
  };

  const chartData = [
    { name: "Matched", count: data.skills_detected?.length || 0 },
    { name: "Missing", count: data.missing_skills?.length || 0 }
  ];

  const chartColors = ['#5bb8a6', '#d96b5d']; // teal, coral

  const scoreColor = data.readiness_score >= 70
    ? 'var(--accent-teal)'
    : data.readiness_score >= 40
      ? 'var(--accent-warm)'
      : 'var(--accent-coral)';

  const scoreColorDim = data.readiness_score >= 70
    ? 'var(--accent-teal-dim)'
    : data.readiness_score >= 40
      ? 'var(--accent-warm-dim)'
      : 'var(--accent-coral-dim)';

  // Determine what to display in the header
  const displayTargetRole = userSelectedRole !== "Auto Detect" ? userSelectedRole : (data.predicted_role || "Unknown");

  // Determine the true ML prediction (even if overridden by user)
  let trueMlPrediction = null;
  let trueMlConfidence = 0;
  let trueMlAlternatives = [];
  const isLowConfidence = data.ml_role_source === "low_confidence";

  const normalizeConfidence = (val) => {
    if (!val) return 0;
    return (val <= 1 && val > 0) ? val * 100 : val;
  };

  if (userSelectedRole !== "Auto Detect") {
    // User forced a role. The ML's prediction is buried in role_alternatives.
    if (data.role_alternatives && data.role_alternatives.length > 0) {
      const sortedAlts = [...data.role_alternatives].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
      trueMlPrediction = typeof sortedAlts[0] === 'string' ? sortedAlts[0] : sortedAlts[0].role;
      trueMlConfidence = normalizeConfidence(sortedAlts[0].confidence);
      trueMlAlternatives = sortedAlts.slice(1);
    }
  } else {
    // Auto Detect was used. ML prediction is predicted_role.
    trueMlPrediction = data.predicted_role;
    trueMlConfidence = normalizeConfidence(data.role_confidence);
    trueMlAlternatives = data.role_alternatives || [];
  }

  return (
    <PageTransition>
      <div className="min-h-screen relative flex flex-col">
        <InteractiveBackground />
        <Navbar />

        <div className="flex-1 relative z-10 pt-24 pb-12">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">

            {/* Header */}
            <motion.header {...fadeUp(0)} className="mb-10 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
              <div>
                <Link to="/upload" className="inline-flex items-center gap-1.5 text-[var(--text-muted)] text-xs hover:text-[var(--text-primary)] transition-colors mb-4 group">
                  <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
                  Back to upload
                </Link>
                <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight">
                  Your Analysis
                </h1>
                <p className="text-sm text-[var(--text-muted)] mt-1.5">
                  Target: <span className="text-[var(--text-secondary)] font-medium">{displayTargetRole}</span>
                </p>
              </div>
              {/* Action buttons */}
              <div className="flex items-center gap-2">
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={handleShareResults}
                  disabled={isSharing}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--accent-lavender)] hover:border-[var(--accent-lavender-dim)] transition-all"
                >
                  {isSharing ? <Loader2 size={14} className="animate-spin" /> : <Share2 size={14} />}
                  {isSharing ? 'Capturing…' : 'Share Results'}
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={handleExportPDF}
                  disabled={isExporting}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[var(--accent-warm-dim)] border border-[var(--accent-warm-dim)] text-[var(--accent-warm)] text-sm font-medium hover:bg-[var(--accent-warm-dim)] transition-all"
                >
                  {isExporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  {isExporting ? 'Exporting…' : 'Export PDF'}
                </motion.button>
              </div>
            </motion.header>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" ref={shareRef}>

              {/* ===== MAIN COLUMN ===== */}
              <div className="lg:col-span-2 space-y-6">

                {/* Skills Intelligence */}
                <motion.div {...fadeUp(0.1)} className="glass-card p-8 noise-overlay overflow-hidden relative">
                  <div className="relative z-10">
                    <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-3 mb-8">
                      <div className="w-9 h-9 rounded-xl bg-[var(--accent-teal-dim)] flex items-center justify-center">
                        <CheckCircle2 size={18} className="text-[var(--accent-teal)]" />
                      </div>
                      Skill Breakdown
                    </h2>

                    {/* Matched Skills */}
                    <div className="mb-8">
                      <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
                        Skills you have ({data.skills_detected?.length || 0})
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {data.skills_detected?.length === 0 && (
                          <span className="text-sm text-[var(--text-muted)]">No skills detected from your resume.</span>
                        )}
                        {data.skills_detected?.map((skill, i) => (
                          <motion.span
                            key={skill}
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: i * 0.03 }}
                            className="px-3.5 py-1.5 bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal-dim)] text-sm rounded-lg font-medium"
                          >
                            {skill}
                          </motion.span>
                        ))}
                      </div>

                      {/* Level Toggle Pills */}
                      {readinessLevels && !readinessLevels.no_analysis && (
                        <div className="mt-5 flex flex-wrap items-center gap-2">
                          <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-widest mr-1">View by level:</span>
                          {[
                            { key: null, label: 'All', icon: '◈', color: 'var(--text-secondary)', dim: 'var(--bg-elevated)', border: 'var(--border-subtle)' },
                            { key: 'beginner', label: 'Fresher', icon: '●', color: 'var(--accent-teal)', dim: 'var(--accent-teal-dim)', border: 'rgba(91,184,166,0.3)' },
                            { key: 'intermediate', label: 'Experienced', icon: '●', color: 'var(--accent-lavender)', dim: 'var(--accent-lavender-dim)', border: 'rgba(143,111,246,0.3)' },
                            { key: 'advanced', label: 'Professional', icon: '●', color: 'var(--accent-warm)', dim: 'var(--accent-warm-dim)', border: 'rgba(232,168,73,0.3)' },
                          ].map(lvl => (
                            <motion.button
                              key={String(lvl.key)}
                              whileHover={{ scale: 1.04 }}
                              whileTap={{ scale: 0.96 }}
                              onClick={() => setSelectedLevel(lvl.key)}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all duration-200 cursor-pointer ${
                                selectedLevel === lvl.key
                                  ? 'shadow-sm'
                                  : 'opacity-60 hover:opacity-100'
                              }`}
                              style={{
                                backgroundColor: selectedLevel === lvl.key ? lvl.dim : 'transparent',
                                borderColor: selectedLevel === lvl.key ? lvl.border : 'var(--border-subtle)',
                                color: selectedLevel === lvl.key ? lvl.color : 'var(--text-muted)',
                              }}
                            >
                              <span style={{ color: lvl.color, fontSize: '6px' }}>{lvl.icon}</span>
                              {lvl.label}
                              {lvl.key && readinessLevels[lvl.key] && (
                                <span className="ml-0.5 text-[10px] font-bold" style={{ color: lvl.color }}>
                                  {Math.round(readinessLevels[lvl.key].score)}%
                                </span>
                              )}
                            </motion.button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Missing Skills — ranked list (issue #48) */}
                    <div>
                      {/* Level-aware missing skills header */}
                      {selectedLevel && readinessLevels?.[selectedLevel] ? (() => {
                        const lvlData = readinessLevels[selectedLevel];
                        const lvlMeta = {
                          beginner:     { label: 'Fresher',       color: 'var(--accent-teal)',     dim: 'var(--accent-teal-dim)' },
                          intermediate: { label: 'Experienced',   color: 'var(--accent-lavender)', dim: 'var(--accent-lavender-dim)' },
                          advanced:     { label: 'Professional',  color: 'var(--accent-warm)',     dim: 'var(--accent-warm-dim)' },
                        }[selectedLevel];
                        const missing = lvlData.missing_skills || [];
                        const matched = lvlData.matched_skills || [];

                        return (
                          <>
                            <div className="flex items-center justify-between mb-3">
                              <p className="text-xs font-medium uppercase tracking-wider" style={{ color: lvlMeta.color }}>
                                Missing for {lvlMeta.label} Level ({missing.length})
                              </p>
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-md border" style={{ backgroundColor: lvlMeta.dim, color: lvlMeta.color, borderColor: `${lvlMeta.color}30` }}>
                                {Math.round(lvlData.score)}% ready
                              </span>
                            </div>

                            {missing.length === 0 ? (
                              <span className="text-sm font-medium" style={{ color: lvlMeta.color }}>You're fully qualified at this level! ✓</span>
                            ) : (
                              <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1 scrollbar-thin">
                                {missing.map((skill, i) => (
                                  <motion.div
                                    key={`${selectedLevel}-${skill}`}
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.04 }}
                                    className="group flex items-center gap-3 bg-[rgba(15,15,15,0.5)] border border-[var(--border-subtle)] rounded-xl px-4 py-3 hover:border-[var(--border-hover)] transition-colors duration-200"
                                  >
                                    <span className="text-[10px] font-bold text-[var(--text-muted)] w-4 shrink-0 text-center">{i + 1}</span>
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors truncate">{skill}</p>
                                    </div>
                                    <span className="w-1.5 h-1.5 rounded-full animate-pulse-soft" style={{ backgroundColor: lvlMeta.color }} />
                                  </motion.div>
                                ))}
                              </div>
                            )}

                            {/* Also show matched skills at this level */}
                            {matched.length > 0 && (
                              <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
                                <p className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                                  Matched at this level ({matched.length})
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {matched.map(s => (
                                    <span key={s} className="px-2.5 py-1 text-xs rounded-md font-medium border" style={{ backgroundColor: lvlMeta.dim, color: lvlMeta.color, borderColor: `${lvlMeta.color}15` }}>
                                      {s}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </>
                        );
                      })() : (
                        /* Default: original analysis missing skills */
                        <>
                          <div className="flex items-center justify-between mb-3">
                            <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
                              Skills you need to learn ({data.missing_skills?.length || 0})
                            </p>
                            {data.missing_skills_ranked?.length > 0 && (
                              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest">
                                Ranked by LSTM likelihood
                              </span>
                            )}
                          </div>

                          {data.missing_skills?.length === 0 && (
                            <span className="text-sm text-[var(--accent-teal)] font-medium">You're fully qualified for this role!</span>
                          )}

                          {data.missing_skills_ranked?.length > 0 ? (() => {
                            const priorityOrder = { high: 0, medium: 1, low: 2 };
                            const sorted = [...data.missing_skills_ranked]
                              .sort((a, b) => (priorityOrder[a.priority] ?? 1) - (priorityOrder[b.priority] ?? 1));
                            const filtered = selectedCategory
                              ? sorted.filter(s => (s.category || 'general') === selectedCategory)
                              : sorted;
                            return (
                              <>
                                {selectedCategory && (
                                  <div className="flex items-center gap-2 mb-3">
                                    <Filter size={12} className="text-[var(--accent-lavender)]" />
                                    <span className="text-xs text-[var(--text-muted)]">Filtered by: <span className="text-[var(--accent-lavender)] font-medium capitalize">{selectedCategory.replace(/_/g, ' ')}</span></span>
                                    <button onClick={() => setSelectedCategory(null)} className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)] ml-auto underline cursor-pointer transition-colors">Clear</button>
                                  </div>
                                )}
                                <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1 scrollbar-thin">
                                  {filtered.slice(0, 20).map((item, i) => {
                                    const skill = typeof item === 'string' ? item : item.skill;
                                    const likelihood = item.likelihood != null
                                      ? Math.round((item.likelihood <= 1 ? item.likelihood * 100 : item.likelihood))
                                      : null;
                                    const priority = item.priority || 'medium';
                                    const category = item.category ? item.category.replace(/_/g, ' ') : null;
                                    const priorityConfig = {
                                      high: { label: 'HIGH', bar: 'bg-[var(--accent-coral)]', badge: 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border-[var(--accent-coral-dim)]' },
                                      medium: { label: 'MED', bar: 'bg-[var(--accent-warm)]', badge: 'bg-[var(--accent-warm-dim)]  text-[var(--accent-warm)]  border-[var(--accent-warm-dim)]' },
                                      low: { label: 'LOW', bar: 'bg-[var(--accent-teal)]', badge: 'bg-[var(--accent-teal-dim)]  text-[var(--accent-teal)]  border-[var(--accent-teal-dim)]' },
                                    };
                                    const cfg = priorityConfig[priority] || priorityConfig.medium;
                                    return (
                                      <motion.div
                                        key={skill}
                                        initial={prefersReducedMotion ? false : { opacity: 0, x: -8 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: i * 0.04 }}
                                        className="group flex items-center gap-3 bg-[rgba(15,15,15,0.5)] border border-[var(--border-subtle)] rounded-xl px-4 py-3 hover:border-[var(--border-hover)] transition-colors duration-200"
                                      >
                                        <span className="text-[10px] font-bold text-[var(--text-muted)] w-4 shrink-0 text-center">{i + 1}</span>
                                        <div className="flex-1 min-w-0">
                                          <p className="text-sm font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors truncate">{skill}</p>
                                          {category && (<span className="text-[10px] text-[var(--text-muted)] capitalize">{category}</span>)}
                                        </div>
                                        {likelihood != null && (
                                          <div className="flex items-center gap-2 shrink-0">
                                            <div className="w-16 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                                              <motion.div className={`h-full rounded-full ${cfg.bar}`} initial={{ width: 0 }} animate={{ width: `${likelihood}%` }} transition={{ duration: 0.7, ease: 'easeOut', delay: 0.1 + i * 0.04 }} />
                                            </div>
                                            <span className="text-[10px] font-medium text-[var(--text-muted)] w-7 text-right">{likelihood}%</span>
                                          </div>
                                        )}
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${cfg.badge} shrink-0`}>{cfg.label}</span>
                                      </motion.div>
                                    );
                                  })}
                                </div>
                              </>
                            );
                          })() : (
                            <div className="flex flex-wrap gap-2">
                              {data.missing_skills?.map((skill, i) => (
                                <motion.span
                                  key={skill}
                                  initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.8 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ delay: i * 0.05 }}
                                  className="flex items-center gap-2 px-3.5 py-1.5 bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border border-[var(--accent-coral-dim)] text-sm rounded-lg font-medium"
                                >
                                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-coral)] animate-pulse-soft" />
                                  {skill}
                                </motion.span>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>

                  </div>
                </motion.div>

                {/* ===== SKILL GAP VISUALIZATION ===== */}
                {((data.skill_categories && Object.keys(data.skill_categories).length > 0) ||
                  (data.missing_skills_ranked && data.missing_skills_ranked.length > 0)) && (
                    <motion.div {...fadeUp(0.15)} className="glass-card p-8 noise-overlay overflow-hidden relative">
                      <div className="relative z-10">
                        {/* Header + Toggle */}
                        <div className="flex items-center justify-between mb-8">
                          <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-3">
                            <div className="w-9 h-9 rounded-xl bg-[var(--accent-lavender-dim)] flex items-center justify-center">
                              <Activity size={18} className="text-[var(--accent-lavender)]" />
                            </div>
                            Skill Gap Analysis
                          </h2>
                          {/* Chart type toggle */}
                          <div className="flex items-center gap-1 p-1 bg-[var(--bg-deep)] border border-[var(--border-subtle)] rounded-lg">
                            <button
                              onClick={() => setChartView("radar")}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors duration-200 cursor-pointer ${chartView === "radar"
                                  ? "bg-[var(--accent-lavender-dim)] text-[var(--accent-lavender)] border border-[var(--accent-lavender-dim)]"
                                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                                }`}
                            >
                              <Activity size={12} />
                              Radar
                            </button>
                            <button
                              onClick={() => setChartView("bar")}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors duration-200 cursor-pointer ${chartView === "bar"
                                  ? "bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] border border-[var(--accent-warm-dim)]"
                                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                                }`}
                            >
                              <BarChart2 size={12} />
                              Bar
                            </button>
                          </div>
                        </div>

                        {/* ── Radar Chart: skill coverage per category ── */}
                        {chartView === "radar" && (() => {
                          const cats = data.skill_categories || {};
                          const radarData = Object.entries(cats).map(([cat, skills]) => ({
                            category: cat.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
                            count: Array.isArray(skills) ? skills.length : 0,
                            fullMark: Math.max(6, ...Object.values(cats).map(s => Array.isArray(s) ? s.length : 0)),
                          }));
                          if (radarData.length === 0) return (
                            <p className="text-center text-sm text-[var(--text-muted)] py-12">No skill categories available yet.</p>
                          );
                          return (
                            <>
                              <p className="text-xs text-[var(--text-muted)] mb-6">Coverage of detected skills across tech domains</p>
                              <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                                  <RadarChart data={radarData} margin={{ top: 10, right: 30, left: 30, bottom: 10 }}>
                                    <PolarGrid stroke="var(--border-subtle)" />
                                    <PolarAngleAxis
                                      dataKey="category"
                                      tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                                    />
                                    <PolarRadiusAxis
                                      angle={30}
                                      domain={[0, "auto"]}
                                      tick={{ fill: "var(--text-muted)", fontSize: 10 }}
                                      tickCount={4}
                                    />
                                    <Radar
                                      name="Skills"
                                      dataKey="count"
                                      stroke="var(--accent-lavender)"
                                      fill="var(--accent-lavender)"
                                      fillOpacity={0.25}
                                      strokeWidth={2}
                                    />
                                    <Tooltip
                                      contentStyle={{
                                        backgroundColor: "var(--bg-surface)",
                                        borderColor: "var(--border-subtle)",
                                        color: "var(--text-primary)",
                                        borderRadius: "10px",
                                        fontSize: "12px",
                                        boxShadow: "0 8px 30px rgba(0,0,0,0.3)",
                                      }}
                                      itemStyle={{ color: "var(--text-primary)" }}
                                      labelStyle={{ color: "var(--text-muted)" }}
                                      formatter={(value, name, props) => [
                                        `${value} skill${value !== 1 ? "s" : ""}`,
                                        props.payload.category,
                                      ]}
                                    />
                                  </RadarChart>
                                </ResponsiveContainer>
                              </div>
                              {/* Category chips */}
                              <div className="flex flex-wrap gap-2 mt-6">
                                {Object.entries(cats).filter(([, s]) => Array.isArray(s) && s.length > 0).map(([cat, skills]) => (
                                  <span key={cat} className="flex items-center gap-1.5 px-2.5 py-1 bg-[var(--accent-lavender-dim)] border border-[var(--accent-lavender-dim)] text-[var(--accent-lavender)] text-xs rounded-md font-medium">
                                    {cat.replace(/_/g, " ")}
                                    <span className="text-[var(--accent-lavender-dim)]">·</span>
                                    {skills.length}
                                  </span>
                                ))}
                              </div>
                            </>
                          );
                        })()}

                        {/* ── Bar Chart: top missing skills by likelihood ── */}
                        {chartView === "bar" && (() => {
                          const ranked = (data.missing_skills_ranked || []).slice(0, 10);
                          if (ranked.length === 0) return (
                            <p className="text-center text-sm text-[var(--text-muted)] py-12">No ranked missing skills yet.</p>
                          );
                          const barData = ranked.map(s => ({
                            name: s.skill,
                            likelihood: Math.round((s.likelihood <= 1 ? s.likelihood * 100 : s.likelihood)),
                            priority: s.priority,
                            category: s.category,
                          }));
                          const barColor = (priority) =>
                            priority === "high" ? "var(--accent-teal)" :
                              priority === "medium" ? "var(--accent-warm)" :
                                "var(--accent-coral)";
                          return (
                            <>
                              <p className="text-xs text-[var(--text-muted)] mb-6">Top missing skills ranked by LSTM likelihood score</p>
                              <div className="h-72 w-full">
                                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                                  <BarChart data={barData} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                                    <XAxis
                                      type="number"
                                      domain={[0, 100]}
                                      tickFormatter={v => `${v}%`}
                                      stroke="var(--text-muted)"
                                      fontSize={11}
                                      tickLine={false}
                                      axisLine={false}
                                    />
                                    <YAxis
                                      type="category"
                                      dataKey="name"
                                      width={90}
                                      stroke="var(--text-muted)"
                                      fontSize={11}
                                      tickLine={false}
                                      axisLine={false}
                                    />
                                    <Tooltip
                                      cursor={{ fill: "var(--bg-elevated)" }}
                                      contentStyle={{
                                        backgroundColor: "var(--bg-surface)",
                                        borderColor: "var(--border-subtle)",
                                        color: "var(--text-primary)",
                                        borderRadius: "10px",
                                        fontSize: "12px",
                                        boxShadow: "0 8px 30px rgba(0,0,0,0.3)",
                                      }}
                                      itemStyle={{ color: "var(--text-primary)" }}
                                      labelStyle={{ color: "var(--text-muted)" }}
                                      formatter={(value, name, props) => [
                                        `${value}% likelihood`,
                                        `${props.payload.category} · ${props.payload.priority} priority`,
                                      ]}
                                    />
                                    <Bar dataKey="likelihood" radius={[0, 6, 6, 0]} maxBarSize={18}>
                                      {barData.map((entry, i) => (
                                        <Cell key={i} fill={barColor(entry.priority)} />
                                      ))}
                                    </Bar>
                                  </BarChart>
                                </ResponsiveContainer>
                              </div>
                              {/* Priority legend */}
                              <div className="flex items-center gap-4 mt-6">
                                {[["high", "var(--accent-teal)"], ["medium", "var(--accent-warm)"], ["low", "var(--accent-coral)"]].map(([p, c]) => (
                                  <div key={p} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                                    <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: c }} />
                                    {p.charAt(0).toUpperCase() + p.slice(1)} priority
                                  </div>
                                ))}
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    </motion.div>
                  )}

                {/* Roadmap — Interactive Timeline */}
                <motion.div {...fadeUp(0.2)} className="glass-card p-8 noise-overlay overflow-hidden relative">
                  <div className="relative z-10">
                    {/* Header row */}
                    <div className="flex items-center justify-between mb-6">
                      <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-[var(--accent-warm-dim)] flex items-center justify-center">
                          <Zap size={18} className="text-[var(--accent-warm)]" />
                        </div>
                        Your Learning Roadmap
                      </h2>
                      <button
                        onClick={handleExportPDF}
                        disabled={isExporting}
                        id="export-pdf"
                        className="flex items-center gap-2 text-xs font-medium px-4 py-2 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-all disabled:opacity-50"
                      >
                        {isExporting ? (
                          <><Loader2 size={14} className="animate-spin" /> Exporting...</>
                        ) : (
                          <><Download size={14} /> Export PDF</>
                        )}
                      </button>
                    </div>

                    {/* Progress summary bar */}
                    {data.roadmap?.length > 0 && (() => {
                      const total = data.roadmap.length;
                      const done = completedWeeks.size;
                      const pct = Math.round((done / total) * 100);
                      return (
                        <div className="mb-8">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              {done === total ? (
                                <Trophy size={14} className="text-[var(--accent-warm)]" />
                              ) : (
                                <Clock size={14} className="text-[var(--text-muted)]" />
                              )}
                              <span className="text-xs font-medium text-[var(--text-secondary)]">
                                {done === total
                                  ? "Roadmap Complete! 🎉"
                                  : `${done} of ${total} phases completed`}
                              </span>
                            </div>
                            <span className={`text-xs font-bold ${
                              pct === 100 ? 'text-[var(--accent-warm)]' :
                              pct >= 50  ? 'text-[var(--accent-teal)]' :
                                           'text-[var(--text-muted)]'
                            }`}>{pct}%</span>
                          </div>
                          <div className="roadmap-progress-bar">
                            <div className="roadmap-progress-fill" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })()}

                    {/* Empty state */}
                    {data.roadmap?.length === 0 && (
                      <div className="flex flex-col items-center justify-center py-12 text-center">
                        <Trophy size={32} className="text-[var(--accent-teal)] mb-3" />
                        <p className="text-sm font-medium text-[var(--accent-teal)]">No roadmap needed — you're already there!</p>
                        <p className="text-xs text-[var(--text-muted)] mt-1">Your skills fully cover this role's requirements.</p>
                      </div>
                    )}

                    {/* Timeline */}
                    {data.roadmap?.length > 0 && (
                      <div className="relative" style={{ paddingLeft: '16px' }}>
                        {/* Vertical connector line */}
                        <div className="timeline-connector" />
                        {/* Animated fill based on completion */}
                        <div
                          className="timeline-connector-fill"
                          style={{
                            height: data.roadmap.length > 0
                              ? `${(completedWeeks.size / data.roadmap.length) * 100}%`
                              : '0%'
                          }}
                        />

                        <div className="space-y-5">
                          {data.roadmap.map((step, idx) => {
                            const isDone = completedWeeks.has(idx);
                            // Parse resource strings: "Platform: https://..." → { platform, url }
                            const parsedResources = (step.resources || []).map(raw => {
                              const colonIdx = raw.indexOf(': http');
                              if (colonIdx > -1) {
                                const platform = raw.substring(0, colonIdx).trim();
                                const url = raw.substring(colonIdx + 2).trim();
                                return { platform, url };
                              }
                              // Try to detect bare URLs
                              const urlMatch = raw.match(/(https?:\/\/[^\s]+)/);
                              if (urlMatch) {
                                return { platform: 'Link', url: urlMatch[1] };
                              }
                              return { platform: raw, url: null };
                            });

                            const platformClass = (p) => {
                              const lower = p.toLowerCase();
                              if (lower.includes('coursera')) return 'resource-link-coursera';
                              if (lower.includes('youtube'))  return 'resource-link-youtube';
                              return 'resource-link-generic';
                            };

                            return (
                              <motion.div
                                key={`roadmap-${idx}`}
                                initial={prefersReducedMotion ? false : { opacity: 0, x: -12 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.2 + idx * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                                className="flex gap-4 items-start"
                              >
                                {/* Timeline node (click to toggle) */}
                                <button
                                  onClick={() => toggleWeekComplete(idx)}
                                  className={`timeline-node ${isDone ? 'completed' : ''}`}
                                  title={isDone ? 'Mark as incomplete' : 'Mark as complete'}
                                  aria-label={isDone ? `Unmark phase ${idx + 1}` : `Mark phase ${idx + 1} complete`}
                                >
                                  {isDone ? (
                                    <Check size={16} className="text-white timeline-check-icon" strokeWidth={3} />
                                  ) : (
                                    <span className="text-[10px] font-bold text-[var(--text-muted)]">{idx + 1}</span>
                                  )}
                                </button>

                                {/* Card */}
                                <div className={`flex-1 min-w-0 bg-[rgba(15,15,15,0.6)] border border-[var(--border-subtle)] rounded-xl p-5 transition-all duration-300 hover:border-[var(--border-hover)] hover:-translate-y-0.5 ${isDone ? 'timeline-card-complete' : ''}`}>
                                  {/* Phase badge + week label */}
                                  <div className="flex items-center gap-3 mb-3">
                                    <span className={`px-2.5 py-1 text-xs font-semibold rounded-md ${
                                      isDone
                                        ? 'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]'
                                        : 'bg-[var(--accent-warm-dim)] text-[var(--accent-warm)]'
                                    }`}>
                                      Phase {idx + 1}
                                    </span>
                                    <span className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                                      <Clock size={10} />
                                      {step.week}
                                    </span>
                                    {isDone && (
                                      <span className="ml-auto text-[10px] font-medium text-[var(--accent-teal)] bg-[var(--accent-teal-dim)] px-2 py-0.5 rounded-md">
                                        ✓ Completed
                                      </span>
                                    )}
                                  </div>

                                  {/* Focus title */}
                                  <h4 className={`text-base font-semibold text-[var(--text-primary)] mb-4 timeline-focus`}>
                                    {step.focus}
                                  </h4>

                                  {/* Resource links */}
                                  <div className="flex flex-wrap gap-2">
                                    {parsedResources.map((res, rIdx) => (
                                      res.url ? (
                                        <a
                                          key={rIdx}
                                          href={res.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className={`resource-link ${platformClass(res.platform)}`}
                                        >
                                          {res.platform}
                                          <ExternalLink size={10} />
                                        </a>
                                      ) : (
                                        <span key={rIdx} className="resource-link resource-link-generic">
                                          {res.platform}
                                        </span>
                                      )
                                    ))}
                                  </div>
                                </div>
                              </motion.div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              </div>

              {/* ===== SIDEBAR ===== */}
              <div className="space-y-6">

                {/* Role Prediction */}
                <motion.div {...fadeUp(0.12)} className="glass-card p-8 noise-overlay overflow-hidden relative group">
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-6">
                      <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">AI Role Prediction</p>
                      <Target size={14} className="text-[var(--text-muted)]" />
                    </div>

                    {isLowConfidence && userSelectedRole === "Auto Detect" ? (
                      <div className="text-center py-4">
                        <span className="text-sm text-[var(--accent-coral)] font-medium">Low Confidence Match</span>
                        <p className="text-xs text-[var(--text-muted)] mt-2 leading-relaxed">The AI could not strongly match this resume to a specific technical role.</p>
                      </div>
                    ) : trueMlPrediction ? (
                      <>
                        <div className="flex items-end justify-between mb-2">
                          <h3 className="text-xl font-bold text-[var(--text-primary)] tracking-tight leading-tight w-2/3">
                            {trueMlPrediction}
                          </h3>
                          <span className={`text-lg font-bold ${trueMlConfidence >= 80 ? 'text-[var(--accent-teal)]' :
                              trueMlConfidence >= 60 ? 'text-[var(--accent-warm)]' :
                                'text-[var(--accent-coral)]'
                            }`}>
                            {Math.round(trueMlConfidence)}%
                          </span>
                        </div>

                        {/* Confidence Bar */}
                        <div className="h-1.5 w-full bg-[var(--bg-deep)] rounded-full overflow-hidden border border-[var(--border-subtle)] mb-6">
                          <motion.div
                            className={`h-full rounded-full ${trueMlConfidence >= 80 ? 'bg-[var(--accent-teal)]' :
                                trueMlConfidence >= 60 ? 'bg-[var(--accent-warm)]' :
                                  'bg-[var(--accent-coral)]'
                              }`}
                            initial={{ width: '0%' }}
                            animate={{ width: `${trueMlConfidence}%` }}
                            transition={{ duration: 1, ease: "easeOut", delay: 0.2 }}
                          />
                        </div>

                        {/* Top Predictive Skills — "Why this role?" */}
                        {data.top_predictive_skills?.length > 0 && (
                          <div className="mb-6">
                            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mb-2.5">Why this role?</p>
                            <div className="flex flex-wrap gap-1.5">
                              {data.top_predictive_skills.map((skill, i) => (
                                <motion.span
                                  key={skill}
                                  initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.8 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ delay: 0.3 + i * 0.05 }}
                                  className="flex items-center gap-1 px-2 py-0.5 bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal-dim)] text-[10px] rounded-md font-medium"
                                >
                                  <span className="w-1 h-1 rounded-full bg-[var(--accent-teal)]" />
                                  {skill}
                                </motion.span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Alternative Roles with probability bars — clickable for swap */}
                        {trueMlAlternatives && trueMlAlternatives.length > 0 && (
                          <div>
                            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mb-3">
                              Click to switch role
                            </p>
                            <div className="space-y-2">
                              {trueMlAlternatives.slice(0, 3).map((alt, i) => {
                                const roleName = typeof alt === 'string' ? alt : alt.role;
                                const altConf = typeof alt === 'string' ? null : normalizeConfidence(alt.confidence);
                                const probConf = data.role_probabilities?.[roleName]
                                  ? normalizeConfidence(data.role_probabilities[roleName])
                                  : altConf;
                                return (
                                  <motion.button
                                    key={i}
                                    initial={prefersReducedMotion ? false : { opacity: 0, x: -6 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: 0.4 + i * 0.08 }}
                                    whileHover={{ scale: 1.02 }}
                                    whileTap={{ scale: 0.97 }}
                                    disabled={isSwapping}
                                    onClick={() => handleRoleSwap(roleName)}
                                    className="flex items-center gap-2.5 w-full text-left px-3 py-2 bg-[rgba(15,15,15,0.5)] border border-[var(--border-subtle)] rounded-lg hover:border-[var(--accent-warm-dim)] hover:bg-[var(--accent-warm-dim)] transition-all duration-200 cursor-pointer group disabled:opacity-50 disabled:cursor-wait"
                                  >
                                    <RefreshCw size={10} className="text-[var(--text-muted)] group-hover:text-[var(--accent-warm)] transition-colors shrink-0" />
                                    <span className="text-xs text-[var(--text-secondary)] font-medium flex-1 truncate group-hover:text-[var(--text-primary)] transition-colors">
                                      {roleName}
                                    </span>
                                    {probConf != null && (
                                      <div className="flex items-center gap-1.5 shrink-0">
                                        <div className="w-12 h-1 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                                          <motion.div
                                            className="h-full rounded-full bg-[var(--text-muted)] group-hover:bg-[var(--accent-warm)] transition-colors"
                                            initial={{ width: 0 }}
                                            animate={{ width: `${probConf}%` }}
                                            transition={{ duration: 0.6, ease: 'easeOut', delay: 0.5 + i * 0.08 }}
                                          />
                                        </div>
                                        <span className="text-[10px] text-[var(--text-muted)] font-medium w-6 text-right">
                                          {Math.round(probConf)}%
                                        </span>
                                      </div>
                                    )}
                                  </motion.button>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Swap error */}
                        <AnimatePresence>
                          {swapError && (
                            <motion.p
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              className="text-xs text-[var(--accent-coral)] mt-3"
                            >
                              {swapError}
                            </motion.p>
                          )}
                        </AnimatePresence>
                      </>
                    ) : (
                      <div className="text-center py-4">
                        <span className="text-sm text-[var(--text-muted)]">No prediction available</span>
                        <h3 className="text-lg font-semibold text-[var(--text-primary)] mt-1">{displayTargetRole}</h3>
                      </div>
                    )}
                  </div>

                  {/* Swap loading overlay */}
                  <AnimatePresence>
                    {isSwapping && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[rgba(15,15,15,0.8)] backdrop-blur-sm rounded-2xl"
                      >
                        <Loader2 size={28} className="animate-spin text-[var(--accent-warm)] mb-3" />
                        <p className="text-sm font-medium text-[var(--text-primary)]">Switching role...</p>
                        <p className="text-xs text-[var(--text-muted)] mt-1">Re-analyzing with new target</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>

                {/* Readiness Score + Job Readiness by Level */}
                <motion.div {...fadeUp(0.15)} className="glass-card p-8 noise-overlay overflow-hidden relative group">
                  <div className="relative z-10">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-6">
                      <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Readiness Score</p>
                      <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                        <span className="w-2 h-2 rounded-full bg-[var(--accent-teal)] animate-pulse-soft" />
                        Live
                      </div>
                    </div>

                    {/* Overall Card */}
                    {(() => {
                      const overallScore = data.readiness_score || 0;
                      const circumference = 2 * Math.PI * 26;
                      const filled = (overallScore / 100) * circumference;
                      const matchedCount = data.skills_detected?.length || 0;
                      const missingCount = data.missing_skills?.length || 0;
                      
                      return (
                        <motion.div
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="flex items-center gap-3 p-4 rounded-xl border mb-6 transition-all duration-200"
                          style={{ 
                            borderColor: scoreColorDim, 
                            background: scoreColorDim 
                          }}
                        >
                          {/* Mini ring */}
                          <div className="relative w-12 h-12 shrink-0">
                            <svg className="w-full h-full -rotate-90" viewBox="0 0 60 60">
                              <circle cx="30" cy="30" r="26" fill="none" stroke="var(--bg-elevated)" strokeWidth="6" />
                              <circle cx="30" cy="30" r="26" fill="none" stroke={scoreColor} strokeWidth="6" strokeLinecap="round"
                                strokeDasharray={`${filled} ${circumference}`}
                                className="transition-all duration-1000 ease-out"
                                style={{ filter: `drop-shadow(0 0 4px ${scoreColor}70)` }}
                              />
                            </svg>
                            <div className="absolute inset-0 flex items-center justify-center">
                              <span className="text-[11px] font-bold" style={{ color: scoreColor }}>{Math.round(overallScore)}</span>
                            </div>
                          </div>

                          {/* Info + bar */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-1">
                              <div>
                                <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: scoreColor }}>Overall Match</p>
                                <p className="text-xs font-semibold text-[var(--text-secondary)]">Readiness Score</p>
                              </div>
                              <span className="text-xs font-bold shrink-0" style={{ color: scoreColor }}>{Math.round(overallScore)}%</span>
                            </div>
                            <div className="h-1.5 w-full bg-[var(--bg-deep)] rounded-full overflow-hidden">
                              <motion.div
                                className="h-full rounded-full"
                                initial={{ width: 0 }}
                                animate={{ width: `${overallScore}%` }}
                                transition={{ duration: 1.1, ease: 'easeOut' }}
                                style={{ background: scoreColor, boxShadow: `0 0 6px ${scoreColor}40` }}
                              />
                            </div>
                            <div className="flex gap-1.5 mt-2 text-[10px] font-semibold">
                              <span className="px-1.5 py-0.5 rounded bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal-dim)]">✓ {matchedCount} matched</span>
                              <span className="px-1.5 py-0.5 rounded bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border border-[var(--accent-coral-dim)]">✗ {missingCount} missing</span>
                            </div>
                          </div>
                        </motion.div>
                      );
                    })()}

                    {/* Job Readiness by Level — 3 mini cards */}
                    {readinessLevels && !readinessLevels.no_analysis && (() => {
                      const levels = [
                        { key: 'beginner', label: 'Fresher', title: 'Beginner', description: '0–2 yrs', color: 'var(--accent-teal)', borderColor: 'rgba(91,184,166,0.25)', glowColor: 'rgba(91,184,166,0.15)', gradient: 'from-[#5bb8a6] to-[#38a892]' },
                        { key: 'intermediate', label: 'Experienced', title: 'Intermediate', description: '2–4 yrs', color: 'var(--accent-lavender)', borderColor: 'rgba(143,111,246,0.25)', glowColor: 'rgba(143,111,246,0.12)', gradient: 'from-[#8f6ff6] to-[#7054d4]' },
                        { key: 'advanced', label: 'Professional', title: 'Advanced', description: 'Senior+', color: 'var(--accent-warm)', borderColor: 'rgba(232,168,73,0.25)', glowColor: 'rgba(232,168,73,0.12)', gradient: 'from-[#e8a849] to-[#cf8f2e]' },
                      ];
                      return (
                        <>
                          <div className="flex items-center gap-2 mb-4 pt-4 border-t border-[var(--border-subtle)]">
                            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[var(--accent-teal-dim)] to-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--border-subtle)]">
                              <BarChart2 size={14} className="text-[var(--accent-teal)]" />
                            </div>
                            <p className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">By Experience Level</p>
                          </div>
                          <div className="space-y-3">
                            {levels.map((lvl, idx) => {
                              const d = readinessLevels[lvl.key];
                              const score = d?.score ?? 0;
                              const circumference = 2 * Math.PI * 26;
                              const filled = (score / 100) * circumference;
                              return (
                                <motion.div
                                  key={lvl.key}
                                  initial={{ opacity: 0, x: 12 }}
                                  animate={{ opacity: 1, x: 0 }}
                                  transition={{ delay: 0.2 + idx * 0.08, duration: 0.4 }}
                                  className="flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 hover:border-opacity-60"
                                  style={{ borderColor: lvl.borderColor, background: `${lvl.glowColor}` }}
                                >
                                  {/* Mini ring */}
                                  <div className="relative w-11 h-11 shrink-0">
                                    <svg className="w-full h-full -rotate-90" viewBox="0 0 60 60">
                                      <circle cx="30" cy="30" r="26" fill="none" stroke="var(--bg-elevated)" strokeWidth="6" />
                                      <circle cx="30" cy="30" r="26" fill="none" stroke={lvl.color} strokeWidth="6" strokeLinecap="round"
                                        strokeDasharray={`${filled} ${circumference}`}
                                        className="transition-all duration-1000 ease-out"
                                        style={{ filter: `drop-shadow(0 0 4px ${lvl.color}70)` }}
                                      />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                      <span className="text-[10px] font-bold" style={{ color: lvl.color }}>{Math.round(score)}</span>
                                    </div>
                                  </div>

                                  {/* Info + bar */}
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between mb-1">
                                      <div>
                                        <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: lvl.color }}>{lvl.label}</p>
                                        <p className="text-xs font-semibold text-[var(--text-secondary)]">{lvl.title}</p>
                                      </div>
                                      <span className="text-xs font-bold shrink-0" style={{ color: lvl.color }}>{Math.round(score)}%</span>
                                    </div>
                                    <div className="h-1 w-full bg-[var(--bg-deep)] rounded-full overflow-hidden">
                                      <motion.div
                                        className={`h-full rounded-full bg-gradient-to-r ${lvl.gradient}`}
                                        initial={{ width: 0 }}
                                        animate={{ width: `${score}%` }}
                                        transition={{ duration: 1.1, ease: 'easeOut', delay: 0.3 + idx * 0.08 }}
                                        style={{ boxShadow: `0 0 6px ${lvl.color}40` }}
                                      />
                                    </div>
                                    {d && (
                                      <div className="flex gap-1.5 mt-1.5 text-[9px] font-semibold">
                                        <span className="px-1.5 py-0.5 rounded bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal-dim)]">✓ {d.matched_skills?.length ?? 0}</span>
                                        <span className="px-1.5 py-0.5 rounded bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border border-[var(--accent-coral-dim)]">✗ {d.missing_skills?.length ?? 0}</span>
                                      </div>
                                    )}
                                  </div>
                                </motion.div>
                              );
                            })}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </motion.div>

                {/* Skill Categories Donut (Issue #49) */}
                {data.skill_categories && Object.keys(data.skill_categories).length > 0 && (() => {
                  const cats = data.skill_categories;
                  const CATEGORY_COLORS = {
                    languages: 'var(--accent-teal)',
                    frontend: 'var(--accent-warm)',
                    backend: 'var(--accent-coral)',
                    databases: 'var(--accent-lavender)',
                    cloud_devops: '#6bb5e0',
                    ml_ai: '#e06bb5',
                    data: '#b5e06b',
                    mlops: '#e0b56b',
                    security: '#6be0b5',
                    general: 'var(--text-muted)',
                  };
                  const donutData = Object.entries(cats)
                    .filter(([, skills]) => Array.isArray(skills) && skills.length > 0)
                    .map(([cat, skills]) => ({
                      name: cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
                      value: skills.length,
                      rawCat: cat,
                      fill: CATEGORY_COLORS[cat] || 'var(--text-muted)',
                    }))
                    .sort((a, b) => b.value - a.value);
                  const totalSkills = donutData.reduce((sum, d) => sum + d.value, 0);
                  if (donutData.length === 0) return null;
                  return (
                    <motion.div {...fadeUp(0.18)} className="glass-card p-8 noise-overlay overflow-hidden relative group">
                      <div className="relative z-10">
                        <div className="flex items-center justify-between mb-6">
                          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Skill Distribution</p>
                          {selectedCategory && (
                            <button onClick={() => setSelectedCategory(null)} className="text-[10px] text-[var(--accent-lavender)] hover:text-[var(--text-primary)] cursor-pointer underline transition-colors">Reset filter</button>
                          )}
                        </div>

                        {/* Improved Interactive Ring Chart */}
                        <div className="relative h-48 w-full">
                          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                            <PieChart>
                              <Pie
                                activeIndex={activeDonutIndex}
                                activeShape={(props) => {
                                  const { cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill } = props;
                                  return (
                                    <g>
                                      <path d={`M ${cx + (outerRadius + 8) * Math.cos(-startAngle * Math.PI / 180)},${cy + (outerRadius + 8) * Math.sin(-startAngle * Math.PI / 180)} A ${outerRadius + 8},${outerRadius + 8} 0 0,0 ${cx + (outerRadius + 8) * Math.cos(-endAngle * Math.PI / 180)},${cy + (outerRadius + 8) * Math.sin(-endAngle * Math.PI / 180)} L ${cx + (innerRadius - 4) * Math.cos(-endAngle * Math.PI / 180)},${cy + (innerRadius - 4) * Math.sin(-endAngle * Math.PI / 180)} A ${innerRadius - 4},${innerRadius - 4} 0 0,1 ${cx + (innerRadius - 4) * Math.cos(-startAngle * Math.PI / 180)},${cy + (innerRadius - 4) * Math.sin(-startAngle * Math.PI / 180)} Z`} fill={fill} style={{ filter: `drop-shadow(0px 0px 8px ${fill}60)` }} className="transition-all duration-300" />
                                    </g>
                                  );
                                }}
                                data={donutData}
                                cx="50%"
                                cy="50%"
                                innerRadius={54}
                                outerRadius={70}
                                paddingAngle={4}
                                dataKey="value"
                                stroke="none"
                                onMouseEnter={(_, index) => setActiveDonutIndex(index)}
                                onMouseLeave={() => setActiveDonutIndex(null)}
                                onClick={(entry) => {
                                  setSelectedCategory(prev => prev === entry.rawCat ? null : entry.rawCat);
                                }}
                                className="cursor-pointer outline-none"
                              >
                                {donutData.map((entry, idx) => (
                                  <Cell
                                    key={idx}
                                    fill={entry.fill}
                                    opacity={selectedCategory && selectedCategory !== entry.rawCat ? 0.2 : 1}
                                    className="transition-opacity duration-300 outline-none"
                                  />
                                ))}
                              </Pie>
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: 'var(--bg-deep)',
                                  borderColor: 'var(--border-subtle)',
                                  color: 'var(--text-primary)',
                                  borderRadius: '12px',
                                  fontSize: '12px',
                                  padding: '8px 12px',
                                  boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
                                }}
                                itemStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
                                labelStyle={{ display: 'none' }}
                                formatter={(value, name) => [`${value} skill${value !== 1 ? 's' : ''}`, name]}
                              />
                            </PieChart>
                          </ResponsiveContainer>
                          {/* Center label */}
                          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span className="text-3xl font-black text-[var(--text-primary)] tracking-tight">{totalSkills}</span>
                            <span className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mt-0.5">Skills</span>
                          </div>
                        </div>

                        {/* Legend */}
                        <div className="space-y-1.5 mt-4">
                          {donutData.map((d) => (
                            <button
                              key={d.rawCat}
                              onClick={() => setSelectedCategory(prev => prev === d.rawCat ? null : d.rawCat)}
                              className={`flex items-center gap-2 w-full text-left px-2 py-1 rounded-md text-xs transition-colors duration-200 cursor-pointer ${selectedCategory === d.rawCat
                                  ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)]'
                                  : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                                }`}
                            >
                              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.fill, opacity: selectedCategory && selectedCategory !== d.rawCat ? 0.3 : 1 }} />
                              <span className="flex-1 truncate">{d.name}</span>
                              <span className="font-medium">{d.value}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  );
                })()}

                {/* Interview Prep — Premium Preview Card */}
                <motion.div {...fadeUp(0.25)} className="glass-card noise-overlay overflow-hidden relative">
                  {/* Lavender ambient glow */}
                  <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full opacity-20 blur-3xl pointer-events-none" style={{ background: 'var(--accent-lavender)' }} />

                  <div className="relative z-10">
                    {/* Header */}
                    <div className="flex items-start justify-between p-8 pb-5">
                      <div className="flex items-center gap-3">
                        <div className="relative">
                          <div className="w-10 h-10 rounded-xl bg-[var(--accent-lavender-dim)] flex items-center justify-center">
                            <Bot size={20} className="text-[var(--accent-lavender)]" />
                          </div>
                          <motion.div
                            className="absolute inset-0 rounded-xl border border-[var(--accent-lavender)]"
                            animate={{ scale: [1, 1.3, 1], opacity: [0.5, 0, 0.5] }}
                            transition={{ duration: 2.5, repeat: Infinity }}
                          />
                        </div>
                        <div>
                          <h2 className="text-base font-bold text-[var(--text-primary)]">Mock Interview</h2>
                          <p className="text-xs text-[var(--text-muted)]">AI-powered practice session</p>
                        </div>
                      </div>

                      {/* Stats chips */}
                      {data.interview_questions?.length > 0 && (
                        <div className="flex items-center gap-2">
                          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)]">
                            <MessageSquare size={10} className="text-[var(--accent-lavender)]" />
                            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">{data.interview_questions.length} Q</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Empty state */}
                    {(!data.interview_questions || data.interview_questions.length === 0) && (
                      <div className="flex flex-col items-center justify-center py-10 text-center px-8">
                        <MessageSquare size={28} className="text-[var(--text-muted)] mb-3" />
                        <p className="text-sm font-medium text-[var(--text-secondary)] mb-1">No questions generated</p>
                        <p className="text-xs text-[var(--text-muted)]">Re-analyze your resume to get mock interview questions.</p>
                      </div>
                    )}

                    {/* Question preview list */}
                    {data.interview_questions?.length > 0 && (
                      <div className="px-6 pb-5 space-y-2">
                        {data.interview_questions.slice(0, 4).map((q, idx) => {
                          const qText = typeof q === 'string' ? q : q.question;
                          const diff  = typeof q === 'object' ? q.difficulty?.toLowerCase() : null;
                          const cat   = typeof q === 'object' ? q.category : null;
                          const diffConfig = {
                            hard:   { cls: 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)]',   dot: 'bg-[var(--accent-coral)]' },
                            medium: { cls: 'bg-[var(--accent-warm-dim)] text-[var(--accent-warm)]',     dot: 'bg-[var(--accent-warm)]' },
                            easy:   { cls: 'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]',     dot: 'bg-[var(--accent-teal)]' },
                          };
                          const dc = diffConfig[diff] || diffConfig.medium;

                          return (
                            <motion.div
                              key={idx}
                              initial={{ opacity: 0, x: 12 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: 0.35 + idx * 0.07, type: 'spring', stiffness: 280, damping: 24 }}
                              onClick={() => setIsInterviewActive(true)}
                              className="group flex items-start gap-3 px-4 py-3 rounded-xl bg-[rgba(15,15,15,0.5)] border border-[var(--border-subtle)] hover:border-[var(--accent-lavender-dim)] hover:bg-[var(--accent-lavender-dim)] transition-all duration-200 cursor-pointer"
                            >
                              {/* Number */}
                              <span className="w-5 h-5 rounded-md bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center justify-center text-[10px] font-bold text-[var(--text-muted)] shrink-0 mt-0.5 group-hover:border-[var(--accent-lavender-dim)] group-hover:text-[var(--accent-lavender)] transition-colors">
                                {idx + 1}
                              </span>

                              {/* Question text */}
                              <p className="flex-1 text-xs text-[var(--text-secondary)] leading-relaxed group-hover:text-[var(--text-primary)] transition-colors line-clamp-2">
                                {qText}
                              </p>

                              {/* Badges */}
                              <div className="flex flex-col items-end gap-1 shrink-0">
                                {diff && (
                                  <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md font-semibold ${dc.cls}`}>
                                    <span className={`w-1 h-1 rounded-full ${dc.dot}`} />
                                    {diff.charAt(0).toUpperCase() + diff.slice(1)}
                                  </span>
                                )}
                                {cat && (
                                  <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-muted)] font-medium">
                                    {cat}
                                  </span>
                                )}
                              </div>

                              <ChevronRight size={13} className="text-[var(--text-muted)] group-hover:text-[var(--accent-lavender)] shrink-0 mt-0.5 transition-colors" />
                            </motion.div>
                          );
                        })}

                        {data.interview_questions.length > 4 && (
                          <p className="text-[10px] text-[var(--text-muted)] text-center pt-1">
                            +{data.interview_questions.length - 4} more questions in the session
                          </p>
                        )}
                      </div>
                    )}

                    {/* CTA Footer */}
                    {data.interview_questions?.length > 0 && (
                      <div className="px-6 pb-6">
                        <motion.button
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.97 }}
                          onClick={() => setIsInterviewActive(true)}
                          className="w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl text-sm font-bold text-white transition-all relative overflow-hidden"
                          style={{
                            background: 'linear-gradient(135deg, var(--accent-lavender) 0%, #7b6bb0 100%)',
                            boxShadow: '0 4px 20px rgba(155,142,196,0.30)'
                          }}
                        >
                          {/* Shimmer sweep */}
                          <motion.div
                            className="absolute inset-0 pointer-events-none"
                            style={{ background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%)' }}
                            initial={{ x: '-100%' }}
                            whileHover={{ x: '100%' }}
                            transition={{ duration: 0.55 }}
                          />
                          <Play size={15} className="fill-white" />
                          Begin Mock Interview
                          <Sparkles size={13} className="opacity-80" />
                        </motion.button>

                        <p className="text-[10px] text-[var(--text-muted)] text-center mt-2.5">
                          Adaptive AI questions · Real-time feedback · Restart anytime
                        </p>
                      </div>
                    )}
                  </div>
                </motion.div>

              </div>
            </div>
          </div>
        </div>



        <Footer />
        
        {/* Mock Interview Panel */}
        <AnimatePresence>
          {isInterviewActive && data.interview_questions && (
            <InterviewPanel
              isOpen={isInterviewActive}
              onClose={() => setIsInterviewActive(false)}
              analysisId={data.analysis_id}
              role={data.predicted_role}
            />
          )}
        </AnimatePresence>
      </div>
    </PageTransition>
  );
}
