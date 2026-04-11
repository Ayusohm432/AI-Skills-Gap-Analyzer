import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { Upload, FileCheck, ChevronDown, Loader2, AlertCircle, Briefcase } from "lucide-react";
import InteractiveBackground from "../components/InteractiveBackground";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";
import PageTransition from "../components/PageTransition";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [role, setRole] = useState("Auto Detect");
  const [customRole, setCustomRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [roleOptions, setRoleOptions] = useState([
    "Auto Detect",
    "Machine Learning Engineer",
    "Data Scientist",
    "Backend Developer",
    "Frontend Developer",
    "Cyber Security Analyst"
  ]);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const apiUrl = import.meta.env.DEV ? "http://127.0.0.1:8000" : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000");
        const res = await fetch(`${apiUrl}/api/v1/jobs/roles`);
        if (res.ok) {
          const data = await res.json();
          if (data.roles && data.roles.length > 0) {
            setRoleOptions(data.roles);
          }
        }
      } catch (err) {
        console.error("Failed to fetch dynamic roles, using defaults", err);
      }
    };
    fetchRoles();
  }, []);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      setFile(droppedFile);
      setError(null);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a resume file to continue.");
      return;
    }

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("resume", file);

    let finalRole = role;
    if (role === "Custom") {
      finalRole = customRole.trim() !== "" ? customRole.trim() : "Auto Detect";
    }
    formData.append("role", finalRole);

    try {
      const apiUrl = import.meta.env.DEV ? "http://127.0.0.1:8000" : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000");
      const response = await fetch(`${apiUrl}/api/v1/analyze/resume`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server responded with status: ${response.status}`);
      }

      const data = await response.json();
      localStorage.setItem("analysisResult", JSON.stringify(data));
      navigate("/dashboard");

    } catch (err) {
      console.error(err);
      setError("Could not reach the analysis engine. Please make sure the backend is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageTransition>
      <div className="min-h-screen flex flex-col relative">
        <InteractiveBackground />
        <Navbar />

        <main className="flex-1 flex items-center justify-center p-6 pt-28 pb-12 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-xl glass-card p-8 md:p-10 relative overflow-hidden noise-overlay"
          >
            {/* Warm ambient glow */}
            <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-80 h-40 rounded-full blur-[80px] pointer-events-none z-0"
              style={{ background: 'radial-gradient(circle, rgba(232,168,73,0.1) 0%, transparent 70%)' }}
            />

            <div className="relative z-10">
              {/* Header */}
              <div className="mb-8 text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-[var(--accent-warm-dim)] flex items-center justify-center mb-4">
                  <Upload size={22} className="text-[var(--accent-warm)]" />
                </div>
                <h1 className="text-2xl md:text-3xl font-semibold text-[var(--text-primary)] tracking-tight mb-2">
                  Analyze Your Resume
                </h1>
                <p className="text-sm text-[var(--text-muted)]">
                  Upload your document and choose a target role to begin.
                </p>
              </div>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mb-6 overflow-hidden"
                  >
                    <div className="flex items-start gap-3 p-4 rounded-xl bg-[var(--accent-coral-dim)] border border-[var(--accent-coral)]/20 text-[var(--accent-coral)]">
                      <AlertCircle size={16} className="shrink-0 mt-0.5" />
                      <p className="text-sm">{error}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Role Selection */}
                <div>
                  <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)] mb-2.5" id="role-label">
                    <Briefcase size={15} className="text-[var(--accent-warm)]" />
                    Target Role
                  </label>
                  <div className="relative">
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      disabled={loading}
                      id="role-select"
                      className="w-full appearance-none bg-[var(--bg-deep)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-sm rounded-xl p-4 pr-10 transition-all cursor-pointer hover:border-[var(--border-hover)]"
                    >
                      {roleOptions.map(r => (
                        <option key={r} value={r}>{r === "Auto Detect" ? "Auto Detect (Best Match)" : r}</option>
                      ))}
                      <option value="Custom">Other (Type your own)</option>
                    </select>
                    <ChevronDown size={16} className="absolute right-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none" />
                  </div>

                  <AnimatePresence>
                    {role === "Custom" && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <input
                          type="text"
                          placeholder="e.g. Product Manager, DevOps Engineer..."
                          value={customRole}
                          onChange={(e) => setCustomRole(e.target.value)}
                          disabled={loading}
                          id="custom-role-input"
                          className="w-full mt-3 bg-[var(--bg-deep)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-sm rounded-xl p-4 transition-all placeholder:text-[var(--text-muted)]"
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* File Upload Zone */}
                <div>
                  <label className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)] mb-2.5" id="file-label">
                    <FileCheck size={15} className="text-[var(--accent-teal)]" />
                    Resume File
                  </label>
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all duration-300 cursor-pointer min-h-[180px] flex flex-col items-center justify-center ${
                      isDragging
                        ? 'border-[var(--accent-warm)] bg-[var(--accent-warm-dim)]'
                        : file
                          ? 'border-[var(--accent-teal)]/40 bg-[var(--accent-teal-dim)]'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-deep)]/50 hover:border-[var(--border-hover)] hover:bg-[var(--bg-elevated)]/30'
                    }`}
                    id="file-drop-zone"
                  >
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx"
                      onChange={handleFileChange}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                      disabled={loading}
                      id="file-input"
                    />

                    <AnimatePresence mode="wait">
                      {file ? (
                        <motion.div
                          key="uploaded"
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.9 }}
                          className="text-center"
                        >
                          <div className="w-14 h-14 rounded-xl bg-[var(--accent-teal-dim)] flex items-center justify-center mx-auto mb-4">
                            <FileCheck size={24} className="text-[var(--accent-teal)]" />
                          </div>
                          <p className="text-[var(--text-primary)] font-semibold text-sm truncate max-w-[250px] mx-auto">
                            {file.name}
                          </p>
                          <p className="text-[var(--accent-teal)] text-xs mt-2 font-medium">
                            Ready to analyze • Click to change
                          </p>
                        </motion.div>
                      ) : (
                        <motion.div
                          key="empty"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="text-center"
                        >
                          <div className="w-14 h-14 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center mx-auto mb-4 transition-colors">
                            <Upload size={24} className="text-[var(--text-muted)]" />
                          </div>
                          <p className="text-[var(--text-secondary)] text-sm font-medium mb-1">
                            Drop your resume here
                          </p>
                          <p className="text-[var(--text-muted)] text-xs">
                            PDF or DOCX — up to 5MB
                          </p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>

                {/* Submit Button */}
                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={!loading ? { scale: 1.01 } : {}}
                  whileTap={!loading ? { scale: 0.98 } : {}}
                  id="submit-analysis"
                  className={`w-full py-4 text-sm font-semibold tracking-wide rounded-xl flex items-center justify-center gap-2.5 transition-all duration-300 ${
                    loading
                      ? 'bg-[var(--bg-elevated)] text-[var(--text-muted)] cursor-wait border border-[var(--border-subtle)]'
                      : 'btn-warm w-full'
                  }`}
                >
                  {loading ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />
                      Analyzing your resume...
                    </>
                  ) : (
                    'Begin Analysis'
                  )}
                </motion.button>
              </form>
            </div>
          </motion.div>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
}
