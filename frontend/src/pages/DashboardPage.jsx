import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import InteractiveBackground from "../components/InteractiveBackground";
import { jsPDF } from 'jspdf';

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    // Attempt to load real data from local storage uploaded from fastapi
    const saved = localStorage.getItem("analysisResult");
    if (saved) {
      setData(JSON.parse(saved));
    } else {
      // Mock data if accessed directly
      setData({
        job_id: "DEMO-123",
        target_role: "Demo Data Scientist",
        skills_detected: ['Python', 'NumPy', 'Pandas', 'Statistics'],
        missing_skills: ['TensorFlow', 'Docker', 'MLOps', 'AWS', 'PyTorch'],
        readiness_score: 58,
        roadmap: [
          { week: "Week 1-2", focus: "Core Concepts", resources: ["Docs"] },
          { week: "Week 3-4", focus: "Advanced Integration", resources: ["Tutorial"] }
        ],
        interview_questions: [
          "Explain the difference between overfitting and underfitting.",
          "How would you deploy a deep learning model to production using Docker?"
        ]
      });
    }
  }, []);

  if (!data) return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center text-zinc-500 font-mono text-sm">
      <div className="w-4 h-4 border-2 border-zinc-500 border-t-transparent rounded-full animate-spin mb-4"></div>
      Loading telemetry...
    </div>
  );

  const handleExportPDF = () => {
    if (!data) return;
    setIsExporting(true);

    // Use setTimeout to allow UI to update to "Generating..." state
    setTimeout(() => {
      try {
        const doc = new jsPDF();

        // Document Title
        doc.setFont("helvetica", "bold");
        doc.setFontSize(22);
        doc.setTextColor(37, 99, 235); // Blue-600
        doc.text("Personalized Execution Roadmap", 105, 20, { align: "center" });

        // Subtitles
        doc.setFontSize(14);
        doc.setTextColor(30, 41, 59); // Slate-800
        doc.text(`Target Role: ${data.target_role || 'Unknown'}`, 20, 35);
        doc.text(`Readiness Score: ${Math.round(data.readiness_score || 0)}%`, 20, 42);

        // Separator line
        doc.setLineWidth(0.5);
        doc.setDrawColor(203, 213, 225); // Slate-300
        doc.line(20, 48, 190, 48);

        let yPos = 60;

        if (!data.roadmap || data.roadmap.length === 0) {
          doc.setFont("helvetica", "normal");
          doc.setFontSize(12);
          doc.text("No roadmap required! You are ready for this role.", 20, yPos);
        } else {
          data.roadmap.forEach((step, idx) => {
            // Add new page if content exceeds A4 height
            if (yPos > 260) {
              doc.addPage();
              yPos = 20;
            }

            // Phase Header
            doc.setFont("helvetica", "bold");
            doc.setFontSize(12);
            doc.setTextColor(59, 130, 246); // Blue-500
            doc.text(`PHASE ${idx + 1}: ${step.week}`, 20, yPos);
            yPos += 7;

            // Focus Text
            doc.setFont("helvetica", "bold");
            doc.setTextColor(15, 23, 42); // Slate-900
            const focusLines = doc.splitTextToSize(step.focus, 170);
            doc.text(focusLines, 20, yPos);
            yPos += (focusLines.length * 6) + 2;

            // Resources List
            doc.setFont("helvetica", "normal");
            doc.setFontSize(11);
            doc.setTextColor(71, 85, 105); // Slate-500

            if (step.resources && step.resources.length > 0) {
              step.resources.forEach(res => {
                const resLines = doc.splitTextToSize(`• ${res}`, 160);
                doc.text(resLines, 25, yPos);
                yPos += (resLines.length * 6);
              });
            }
            yPos += 10; // Extra spacing between phases
          });
        }

        doc.save(`SkillGap_Roadmap_${data.target_role?.replace(/\s+/g, '_') || 'Export'}.pdf`);
      } catch (error) {
        console.error("Error generating native PDF:", error);
        alert("Failed to generate PDF document.");
      } finally {
        setIsExporting(false);
      }
    }, 100);
  };

  // Prepare chart data
  const chartData = [
    { name: "Matched", count: data.skills_detected?.length || 0, fill: "#3b82f6" },
    { name: "Missing", count: data.missing_skills?.length || 0, fill: "#ef4444" }
  ];

  return (
    <div className="min-h-screen text-zinc-300 font-sans pb-12 relative">
      <InteractiveBackground />
      {/* Navigation */}
      <nav className="border-b border-zinc-800/50 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-10 px-6 py-4 flex justify-between items-center mb-8">
        <Link to="/" className="font-semibold tracking-wide text-zinc-100 flex items-center gap-2">
          <div className="w-4 h-4 bg-zinc-700 rounded-sm"></div>
          SkillGap<span className="text-zinc-500">Analyzer</span>
        </Link>
        <Link to="/upload" className="text-xs font-mono text-zinc-400 hover:text-zinc-100 transition-colors uppercase tracking-wider">
          &larr; Return to Input
        </Link>
      </nav>

      <div className="max-w-6xl mx-auto px-6">

        <header className="mb-10 pl-2 border-l-2 border-blue-500">
          <h1 className="text-3xl font-bold text-zinc-100 tracking-tight">Analysis Output</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono">
            TARGET_ROLE: <span className="text-zinc-300 ml-2">{data.target_role || "Unknown"}</span> |
            JOB_ID: <span className="text-zinc-600 ml-2">{data.job_id || "N/A"}</span>
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Main Content Area */}
          <div className="lg:col-span-2 space-y-6">

            {/* Skills Section */}
            <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 p-8 rounded-xl shadow-2xl">
              <h2 className="text-xl font-bold text-zinc-100 mb-6 flex items-center gap-3 border-b border-zinc-800/50 pb-6">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </div>
                Skill Intelligence Inventory
              </h2>

              <div className="mb-10">
                <h3 className="text-xs font-mono text-zinc-500 mb-4 uppercase tracking-widest">Detected Capabilities</h3>
                <div className="flex flex-wrap gap-2">
                  {data.skills_detected?.length === 0 && <span className="text-sm text-zinc-600 font-mono">No valid entities found.</span>}
                  {data.skills_detected?.map(skill => (
                    <span key={skill} className="px-4 py-1.5 bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 border border-zinc-700/50 text-sm rounded-full font-medium transition-colors cursor-default">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-mono text-zinc-500 mb-4 uppercase tracking-widest">Missing Requirements [Priority]</h3>
                <div className="flex flex-wrap gap-3">
                  {data.missing_skills?.length === 0 && <span className="text-sm text-emerald-500 font-mono">Inventory matches role criteria.</span>}
                  {data.missing_skills?.map(skill => (
                    <span key={skill} className="px-4 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 text-sm rounded-full font-medium flex items-center gap-2 transition-colors cursor-default">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Roadmap Section */}
            <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 p-8 rounded-xl shadow-2xl relative">
              <div className="flex items-center justify-between border-b border-zinc-800/50 pb-6 mb-8">
                <h2 className="text-xl font-bold flex items-center gap-3 text-zinc-100">
                  <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center text-blue-400">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  </div>
                  Personalized Execution Roadmap
                </h2>
                <button
                  onClick={handleExportPDF}
                  disabled={isExporting}
                  className="text-xs font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-4 py-2 rounded-md transition-colors border border-zinc-700 cursor-pointer shadow-sm disabled:opacity-50 flex items-center gap-2"
                >
                  {isExporting ? (
                    <>
                      <div className="w-3 h-3 border-2 border-zinc-400 border-t-zinc-100 rounded-full animate-spin"></div>
                      Generating...
                    </>
                  ) : "Export PDF"}
                </button>
              </div>

              <div className="relative border-l-2 border-zinc-800 ml-4 space-y-8 pb-4">
                {data.roadmap?.length === 0 && (
                  <p className="pl-6 text-zinc-500 text-sm">No roadmap required! You are ready for this role.</p>
                )}
                {data.roadmap?.map((step, idx) => (
                  <div key={idx} className="relative pl-8 group">
                    <div className="absolute w-5 h-5 bg-zinc-900 border-[3px] border-zinc-700 rounded-full -left-[11px] top-2 group-hover:border-blue-500 group-hover:bg-blue-500 shadow-[0_0_0_rgba(59,130,246,0)] group-hover:shadow-[0_0_15px_rgba(59,130,246,0.6)] transition-all duration-300"></div>
                    <div className="bg-zinc-950/50 border border-zinc-800/50 rounded-xl p-6 hover:bg-zinc-800/50 hover:border-zinc-700 transition-all duration-300 transform group-hover:-translate-y-1">
                      <span className="inline-block px-3 py-1 bg-blue-500/10 text-blue-400 text-xs font-bold font-mono tracking-widest rounded-full mb-3">{"PHASE " + (idx + 1) + ": " + step.week}</span>
                      <h4 className="text-lg font-bold text-zinc-200 mb-4">{step.focus}</h4>
                      <ul className="space-y-3">
                        {step.resources?.map((res, rIdx) => (
                          <li key={rIdx} className="flex items-start gap-3 text-zinc-400 text-sm group/item">
                            <span className="text-zinc-600 mt-0.5 group-hover/item:text-blue-400 transition-colors">
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                            </span>
                            <span className="group-hover/item:text-zinc-200 transition-colors">{res}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Sidebar */}
          <div className="space-y-6">

            {/* Score Card & Chart */}
            <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 p-8 rounded-xl shadow-2xl relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none"></div>
              <h2 className="text-xs font-mono text-zinc-500 uppercase tracking-widest mb-8 border-b border-zinc-800/50 pb-4 flex items-center justify-between">
                <span>Readiness Metric</span>
                <span className="flex items-center gap-2 text-zinc-400">
                  LIVE
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-[pulse_2s_ease-in-out_infinite]"></span>
                </span>
              </h2>

              <div className="relative w-48 h-48 mx-auto flex items-center justify-center mb-10 transition-transform duration-500 group-hover:scale-105">
                <svg className="w-full h-full transform -rotate-90 drop-shadow-[0_0_15px_rgba(59,130,246,0.3)]" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="45" fill="none" stroke="#18181b" strokeWidth="6" />
                  <circle
                    cx="50" cy="50" r="45" fill="none"
                    stroke="url(#score-gradient)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${(data.readiness_score || 0) * 2.83} 283`}
                    className="transition-all duration-1500 ease-out"
                    strokeDashoffset="0"
                  />
                  <defs>
                    <linearGradient id="score-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#3b82f6" />
                      <stop offset="100%" stopColor="#a855f7" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute flex flex-col items-center">
                  <span className="text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-br from-white to-zinc-400">
                    {Math.round(data.readiness_score || 0)}<span className="text-2xl ml-1 text-zinc-500">%</span>
                  </span>
                  <span className="text-xs text-zinc-500 mt-1 font-mono tracking-widest">MATCH</span>
                </div>
              </div>

              <div className="h-32 w-full mt-4 opacity-80 group-hover:opacity-100 transition-opacity">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                    <XAxis dataKey="name" stroke="#52525b" fontSize={11} tickLine={false} axisLine={false} />
                    <YAxis stroke="#52525b" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip cursor={{ fill: '#27272a' }} contentStyle={{ backgroundColor: '#09090b', borderColor: '#27272a', color: '#f4f4f5', borderRadius: '8px' }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* AI Interview Prep */}
            <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 p-8 rounded-xl shadow-2xl relative">
              <h2 className="text-xl font-bold flex items-center gap-3 text-zinc-100 mb-8 border-b border-zinc-800/50 pb-6">
                <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
                </div>
                AI Interview Simulator
              </h2>

              <div className="grid gap-4">
                {data.interview_questions?.length === 0 && <p className="text-zinc-500 text-sm">No questions generated.</p>}
                {data.interview_questions?.map((q, idx) => (
                  <div key={idx} className="bg-zinc-950/50 border border-zinc-800/60 p-5 rounded-xl hover:border-purple-500/50 transition-all duration-300 flex gap-4 items-start cursor-pointer group hover:bg-purple-500/5">
                    <div className="w-8 h-8 rounded-full bg-purple-500/10 flex items-center justify-center text-purple-400 font-bold shrink-0 shadow-[0_0_10px_rgba(168,85,247,0)] group-hover:shadow-[0_0_15px_rgba(168,85,247,0.3)] group-hover:bg-purple-500/20 transition-all">
                      {idx + 1}
                    </div>
                    <p className="text-zinc-300 text-sm leading-relaxed group-hover:text-zinc-100 transition-colors mt-0.5">{q}</p>
                  </div>
                ))}
              </div>
            </div>

          </div>

        </div>
      </div>
    </div>
  );
}
