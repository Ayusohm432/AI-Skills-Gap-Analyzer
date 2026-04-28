import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { jsPDF } from 'jspdf';
import {
  CheckCircle2, XCircle, Zap, Download, MessageSquare,
  ChevronRight, ArrowLeft, BookOpen, Loader2, Target
} from "lucide-react";
import InteractiveBackground from "../components/InteractiveBackground";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";
import PageTransition from "../components/PageTransition";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }
});

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  const [userSelectedRole, setUserSelectedRole] = useState("Auto Detect");

  useEffect(() => {
    const savedRole = localStorage.getItem("userSelectedRole");
    if (savedRole) setUserSelectedRole(savedRole);

    const saved = localStorage.getItem("analysisResult");
    if (saved) {
      setData(JSON.parse(saved));
    } else {
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
        ]
      });
    }
  }, []);

  if (!data) return (
    <div className="min-h-screen bg-[var(--bg-deep)] flex flex-col items-center justify-center text-[var(--text-muted)]">
      <Loader2 size={24} className="animate-spin mb-3 text-[var(--accent-warm)]" />
      <p className="text-sm">Loading your results...</p>
    </div>
  );

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
            </motion.header>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

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
                            className="px-3.5 py-1.5 bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal)]/15 text-sm rounded-lg font-medium"
                          >
                            {skill}
                          </motion.span>
                        ))}
                      </div>
                    </div>

                    {/* Missing Skills */}
                    <div>
                      <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
                        Skills to learn ({data.missing_skills?.length || 0})
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {data.missing_skills?.length === 0 && (
                          <span className="text-sm text-[var(--accent-teal)] font-medium">You're fully qualified for this role!</span>
                        )}
                        {data.missing_skills?.map((skill, i) => (
                          <motion.span
                            key={skill}
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: i * 0.05 }}
                            className="flex items-center gap-2 px-3.5 py-1.5 bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border border-[var(--accent-coral)]/15 text-sm rounded-lg font-medium"
                          >
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-coral)] animate-pulse-soft" />
                            {skill}
                          </motion.span>
                        ))}
                      </div>
                    </div>
                  </div>
                </motion.div>

                {/* Roadmap */}
                <motion.div {...fadeUp(0.2)} className="glass-card p-8 noise-overlay overflow-hidden relative">
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-8">
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

                    {/* Timeline */}
                    <div className="relative ml-4 space-y-6">
                      {/* Vertical line */}
                      <div className="absolute left-0 top-3 bottom-3 w-px bg-[var(--border-subtle)]" />

                      {data.roadmap?.length === 0 && (
                        <p className="pl-8 text-[var(--text-muted)] text-sm">No roadmap needed — you're already there!</p>
                      )}

                      {data.roadmap?.map((step, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.3 + idx * 0.1 }}
                          className="relative pl-8 group"
                        >
                          {/* Dot */}
                          <div className="absolute w-3 h-3 rounded-full -left-[6px] top-[18px] border-2 border-[var(--border-subtle)] bg-[var(--bg-surface)] group-hover:border-[var(--accent-warm)] group-hover:bg-[var(--accent-warm)] transition-all duration-300 group-hover:shadow-[0_0_12px_rgba(232,168,73,0.4)]" />

                          <div className="bg-[var(--bg-deep)]/60 border border-[var(--border-subtle)] rounded-xl p-6 hover:border-[var(--border-hover)] transition-all duration-300 group-hover:-translate-y-0.5">
                            <div className="flex items-center gap-3 mb-3">
                              <span className="px-2.5 py-1 bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] text-xs font-semibold rounded-md">
                                Phase {idx + 1}
                              </span>
                              <span className="text-xs text-[var(--text-muted)]">{step.week}</span>
                            </div>
                            <h4 className="text-base font-semibold text-[var(--text-primary)] mb-3">{step.focus}</h4>
                            <ul className="space-y-2">
                              {step.resources?.map((res, rIdx) => (
                                <li key={rIdx} className="flex items-start gap-2.5 text-sm text-[var(--text-secondary)] group/item">
                                  <ChevronRight size={14} className="shrink-0 mt-0.5 text-[var(--text-muted)] group-hover/item:text-[var(--accent-warm)] transition-colors" />
                                  <span className="group-hover/item:text-[var(--text-primary)] transition-colors">{res}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </motion.div>
                      ))}
                    </div>
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
                          <span className={`text-lg font-bold ${
                            trueMlConfidence >= 80 ? 'text-[var(--accent-teal)]' : 
                            trueMlConfidence >= 60 ? 'text-[var(--accent-warm)]' : 
                            'text-[var(--accent-coral)]'
                          }`}>
                            {Math.round(trueMlConfidence)}%
                          </span>
                        </div>

                        {/* Confidence Bar */}
                        <div className="h-1.5 w-full bg-[var(--bg-deep)] rounded-full overflow-hidden border border-[var(--border-subtle)] mb-6">
                          <motion.div 
                            className={`h-full rounded-full ${
                              trueMlConfidence >= 80 ? 'bg-[var(--accent-teal)]' : 
                              trueMlConfidence >= 60 ? 'bg-[var(--accent-warm)]' : 
                              'bg-[var(--accent-coral)]'
                            }`}
                            initial={{ width: '0%' }}
                            animate={{ width: `${trueMlConfidence}%` }}
                            transition={{ duration: 1, ease: "easeOut", delay: 0.2 }}
                          />
                        </div>

                        {/* Alternative Roles */}
                        {trueMlAlternatives && trueMlAlternatives.length > 0 && (
                           <div>
                             <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mb-3">Alternative Matches</p>
                             <div className="flex flex-wrap gap-2">
                               {trueMlAlternatives.map((alt, i) => {
                                 const roleName = typeof alt === 'string' ? alt : alt.role;
                                 return (
                                   <span key={i} className="px-2.5 py-1 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-xs rounded-md font-medium hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-colors cursor-default">
                                     {roleName}
                                   </span>
                                 );
                               })}
                             </div>
                           </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-4">
                        <span className="text-sm text-[var(--text-muted)]">No prediction available</span>
                        <h3 className="text-lg font-semibold text-[var(--text-primary)] mt-1">{displayTargetRole}</h3>
                      </div>
                    )}
                  </div>
                </motion.div>

                {/* Readiness Score */}
                <motion.div {...fadeUp(0.15)} className="glass-card p-8 noise-overlay overflow-hidden relative group">
                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-8">
                      <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Readiness Score</p>
                      <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                        <span className="w-2 h-2 rounded-full bg-[var(--accent-teal)] animate-pulse-soft" />
                        Live
                      </div>
                    </div>

                    {/* Circular Progress */}
                    <div className="relative w-44 h-44 mx-auto flex items-center justify-center mb-8 group-hover:scale-105 transition-transform duration-500">
                      <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--bg-elevated)" strokeWidth="5" />
                        <circle
                          cx="50" cy="50" r="42" fill="none"
                          stroke={scoreColor}
                          strokeWidth="6"
                          strokeLinecap="round"
                          strokeDasharray={`${(data.readiness_score || 0) * 2.64} 264`}
                          className="transition-all duration-1000 ease-out"
                          style={{ filter: `drop-shadow(0 0 8px ${scoreColor}40)` }}
                        />
                      </svg>
                      <div className="absolute flex flex-col items-center">
                        <span className="text-4xl font-bold text-[var(--text-primary)]">
                          {Math.round(data.readiness_score || 0)}
                          <span className="text-lg text-[var(--text-muted)] ml-0.5">%</span>
                        </span>
                        <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mt-1">Match</span>
                      </div>
                    </div>

                    {/* Bar Chart */}
                    <div className="h-28 w-full opacity-80 group-hover:opacity-100 transition-opacity">
                      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                        <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                          <XAxis dataKey="name" stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} />
                          <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                          <Tooltip
                            cursor={{ fill: 'var(--bg-elevated)' }}
                            contentStyle={{
                              backgroundColor: 'var(--bg-surface)',
                              borderColor: 'var(--border-subtle)',
                              color: 'var(--text-primary)',
                              borderRadius: '10px',
                              fontSize: '12px',
                              boxShadow: '0 8px 30px rgba(0,0,0,0.3)'
                            }}
                          />
                          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                            {chartData.map((entry, index) => (
                              <Cell key={index} fill={chartColors[index]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </motion.div>

                {/* Interview Prep */}
                <motion.div {...fadeUp(0.25)} className="glass-card p-8 noise-overlay overflow-hidden relative">
                  <div className="relative z-10">
                    <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-3 mb-8">
                      <div className="w-9 h-9 rounded-xl bg-[var(--accent-lavender-dim)] flex items-center justify-center">
                        <MessageSquare size={18} className="text-[var(--accent-lavender)]" />
                      </div>
                      Interview Prep
                    </h2>

                    <div className="space-y-3">
                      {data.interview_questions?.length === 0 && (
                        <p className="text-sm text-[var(--text-muted)]">No interview questions generated.</p>
                      )}
                      {data.interview_questions?.map((q, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: 10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.4 + idx * 0.08 }}
                          className="group bg-[var(--bg-deep)]/60 border border-[var(--border-subtle)] p-4 rounded-xl hover:border-[var(--accent-lavender)]/30 transition-all duration-300 cursor-pointer flex gap-3 items-start hover:bg-[var(--accent-lavender-dim)]"
                        >
                          <div className="w-7 h-7 rounded-lg bg-[var(--accent-lavender-dim)] flex items-center justify-center text-[var(--accent-lavender)] text-xs font-bold shrink-0 group-hover:bg-[var(--accent-lavender)]/20 transition-colors">
                            {idx + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-[var(--text-secondary)] leading-relaxed group-hover:text-[var(--text-primary)] transition-colors">
                              {typeof q === 'string' ? q : q.question}
                            </p>
                            {typeof q === 'object' && q.category && (
                              <div className="flex gap-2 mt-2">
                                <span className="text-[10px] px-2 py-0.5 rounded-md bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-muted)] font-medium">
                                  {q.category}
                                </span>
                                {q.difficulty && (
                                  <span className={`text-[10px] px-2 py-0.5 rounded-md font-medium ${
                                    q.difficulty.toLowerCase() === 'hard' ? 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)]' :
                                    q.difficulty.toLowerCase() === 'medium' ? 'bg-[var(--accent-warm-dim)] text-[var(--accent-warm)]' :
                                    'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]'
                                  }`}>
                                    {q.difficulty}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                </motion.div>

              </div>
            </div>
          </div>
        </div>

        <Footer />
      </div>
    </PageTransition>
  );
}
