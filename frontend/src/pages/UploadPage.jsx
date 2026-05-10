import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { Upload, FileCheck, ChevronDown, Loader2, AlertCircle, Briefcase, CheckCircle2 } from "lucide-react";
import InteractiveBackground from "../components/InteractiveBackground";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";
import PageTransition from "../components/PageTransition";
import { secureFetch } from "../api/base";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [role, setRole] = useState("Auto Detect");
  const [customRole, setCustomRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState("");
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
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();
  const pollRef = useRef(null); // setInterval ID for cleanup

  // Pipeline steps mapped to backend status flow
  const PIPELINE_STEPS = [
    { key: 'upload',   label: 'Uploading' },
    { key: 'extract',  label: 'Extracting' },
    { key: 'analyze',  label: 'Analyzing' },
    { key: 'complete', label: 'Complete' },
  ];
  const [pipelineStep, setPipelineStep] = useState(-1); // -1 = not started

  // Cleanup polling on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  // Click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const res = await secureFetch('/api/v1/jobs/roles');
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

  const validateAndSetFile = (selectedFile) => {
    if (!selectedFile) return;
    
    // 1. Size Validation (5MB max)
    if (selectedFile.size > 5 * 1024 * 1024) {
      setError("File exceeds the 5MB size limit. Please choose a smaller file.");
      setFile(null);
      return;
    }

    // 2. Type Validation
    const ext = selectedFile.name.split('.').pop().toLowerCase();
    if (!['pdf', 'doc', 'docx', 'txt'].includes(ext)) {
      setError("Invalid file format. Please upload a PDF, DOCX, or TXT file.");
      setFile(null);
      return;
    }

    setError(null);
    setFile(selectedFile);
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
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
      validateAndSetFile(droppedFile);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a resume file to continue.");
      return;
    }

    setLoading(true);
    setUploadProgress(0);
    setUploadStatus("Preparing document...");
    setPipelineStep(0); // Uploading
    setError(null);

    const formData = new FormData();
    formData.append("resume", file);

    let finalRole = role;
    if (role === "Custom") {
      finalRole = customRole.trim() !== "" ? customRole.trim() : "Auto Detect";
    }
    formData.append("role", finalRole);
    localStorage.setItem("userSelectedRole", finalRole);

    try {
      // ── Step 1: Submit job (expect 202 + job_id) ──────────────────
      setUploadProgress(15);
      setUploadStatus("Uploading resume...");

      const submitRes = await secureFetch('/api/v1/analyze/resume', {
        method: "POST",
        body: formData,
      });

      if (!submitRes.ok) {
        const errData = await submitRes.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${submitRes.status}`);
      }

      const { job_id } = await submitRes.json();

      setPipelineStep(1); // Extracting
      setUploadProgress(30);
      setUploadStatus("Extracting text from resume...");

      // ── Step 2: Poll every 2s until completed / failed ────────────
      const result = await new Promise((resolve, reject) => {
        let pollProgress = 35;

        pollRef.current = setInterval(async () => {
          try {
            const pollRes = await secureFetch(`/api/v1/jobs/${job_id}`);
            if (!pollRes.ok) {
              clearInterval(pollRef.current);
              pollRef.current = null;
              reject(new Error(`Poll error: ${pollRes.status}`));
              return;
            }

            const jobData = await pollRes.json();

            // Map real backend step → 4-stage UI stepper
            if (jobData.status === "processing") {
              const backendStep = jobData.step || 1;
              const stepLabel = jobData.step_name || "Processing...";
              if (backendStep <= 2) {
                setPipelineStep(1); // Extracting
                setUploadStatus(stepLabel);
              } else if (backendStep <= 8) {
                setPipelineStep(2); // Analyzing
                setUploadStatus(stepLabel);
              } else {
                setPipelineStep(2); // Still analyzing (step 9 = storage)
                setUploadStatus("Saving results...");
              }
            }

            if (pollProgress < 90) {
              pollProgress += 8;
              setUploadProgress(Math.min(pollProgress, 92));
            }

            if (jobData.status === "completed") {
              clearInterval(pollRef.current);
              pollRef.current = null;
              setPipelineStep(3); // Complete
              resolve(jobData.result);
            } else if (jobData.status === "failed") {
              clearInterval(pollRef.current);
              pollRef.current = null;
              reject(new Error(jobData.error || "Analysis failed on the server."));
            }
            // "pending" / "processing" → keep polling
          } catch (pollErr) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            reject(pollErr);
          }
        }, 2000);
      });

      // ── Step 3: Save result + cache resume for role-swap ──────────
      setUploadProgress(100);
      setUploadStatus("Analysis Complete!");
      localStorage.setItem("analysisResult", JSON.stringify(result));

      // Cache resume in sessionStorage so DashboardPage can re-submit
      // for role swap without the user re-uploading (Issue #51)
      try {
        const reader = new FileReader();
        reader.onload = () => {
          sessionStorage.setItem("resumeFileBase64", reader.result);
          sessionStorage.setItem("resumeFileName", file.name);
          sessionStorage.setItem("resumeContentType", file.type);
        };
        reader.readAsDataURL(file);
      } catch (_) { /* non-critical — swap just won't be available */ }

      setTimeout(() => navigate("/dashboard"), 800);

    } catch (err) {
      console.error(err);
      setError(err.message || "Analysis failed. Please make sure the backend is running and the file is readable.");
      setLoading(false);
      setPipelineStep(-1);
    }
  };


  return (
    <PageTransition>
      <div className="min-h-screen flex flex-col relative">
        <InteractiveBackground />
        <Navbar />

        <main className="flex-1 flex items-center justify-center p-6 pt-28 pb-12 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: 'spring', stiffness: 260, damping: 22 }}
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
                  <div className="relative" ref={dropdownRef}>
                    <button
                      type="button"
                      onClick={() => !loading && setIsDropdownOpen(!isDropdownOpen)}
                      className={`w-full flex items-center justify-between bg-[var(--bg-deep)] border text-[var(--text-primary)] text-sm rounded-xl p-4 transition-all ${
                        isDropdownOpen ? 'border-[var(--accent-warm)] shadow-[0_0_15px_rgba(232,168,73,0.1)]' : 'border-[var(--border-subtle)] hover:border-[var(--border-hover)] cursor-pointer'
                      } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <span>{role === "Auto Detect" ? "Auto Detect (Best Match)" : role === "Custom" ? "Other (Type your own)" : role}</span>
                      <ChevronDown size={16} className={`text-[var(--text-muted)] transition-transform duration-300 ${isDropdownOpen ? 'rotate-180 text-[var(--accent-warm)]' : ''}`} />
                    </button>

                    <AnimatePresence>
                      {isDropdownOpen && (
                        <motion.div
                          initial={{ opacity: 0, y: -10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -10 }}
                          className="absolute z-50 w-full mt-2 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl shadow-2xl overflow-hidden"
                        >
                          <div className="max-h-60 overflow-y-auto scrollbar-custom py-2">
                            {roleOptions.map(r => (
                              <button
                                key={r}
                                type="button"
                                onClick={() => {
                                  setRole(r);
                                  setIsDropdownOpen(false);
                                  if (r !== "Custom") setCustomRole("");
                                }}
                                className={`w-full text-left px-4 py-3 text-sm transition-colors ${
                                  role === r 
                                    ? 'bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] font-medium' 
                                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]'
                                }`}
                              >
                                {r === "Auto Detect" ? "Auto Detect (Best Match)" : r}
                              </button>
                            ))}
                            <button
                              type="button"
                              onClick={() => {
                                setRole("Custom");
                                setIsDropdownOpen(false);
                              }}
                              className={`w-full text-left px-4 py-3 text-sm transition-colors border-t border-[var(--border-subtle)] mt-1 pt-3 ${
                                role === "Custom" 
                                  ? 'bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] font-medium' 
                                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)]'
                              }`}
                            >
                              Other (Type your own)
                            </button>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
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
                    className={`relative rounded-2xl p-8 text-center transition-all duration-300 cursor-pointer min-h-[180px] flex flex-col items-center justify-center ${
                      isDragging
                        ? 'bg-[var(--accent-warm-dim)]'
                        : file
                          ? 'border-2 border-dashed border-[var(--accent-teal)]/40 bg-[var(--accent-teal-dim)]'
                          : 'border-2 border-dashed border-[var(--border-subtle)] bg-[var(--bg-deep)]/50 hover:border-[var(--border-hover)] hover:bg-[var(--bg-elevated)]/30'
                    }`}
                    style={isDragging ? {
                      border: '2px dashed var(--accent-warm)',
                      animation: 'dash-pulse 1s linear infinite',
                    } : {}}
                    id="file-drop-zone"
                  >
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx,.txt"
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
                            PDF, DOCX, or TXT — up to 5MB
                          </p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>

                {/* Submit Button & Progress */}
                <div className="space-y-4">
                  <motion.button
                    type="submit"
                    disabled={loading || !file}
                    whileHover={!(loading || !file) ? { scale: 1.01 } : {}}
                    whileTap={!(loading || !file) ? { scale: 0.98 } : {}}
                    id="submit-analysis"
                    className={`w-full py-4 text-sm font-semibold tracking-wide rounded-xl flex items-center justify-center gap-2.5 transition-all duration-300 ${
                      loading || !file
                        ? 'bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-subtle)]'
                        : 'btn-warm w-full'
                    } ${loading ? 'cursor-wait' : !file ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
                  >
                    {loading ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        Processing...
                      </>
                    ) : (
                      'Begin Analysis'
                    )}
                  </motion.button>

                  <AnimatePresence>
                    {loading && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="pt-4 pb-1">
                          {/* Step-by-step pipeline tracker */}
                          <div className="flex items-center justify-between mb-5">
                            {PIPELINE_STEPS.map((step, idx) => {
                              const isCompleted = pipelineStep > idx;
                              const isActive = pipelineStep === idx;
                              return (
                                <React.Fragment key={step.key}>
                                  <div className="flex flex-col items-center gap-1.5 flex-1">
                                    {/* Step icon */}
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all duration-300 ${
                                      isCompleted
                                        ? 'bg-[var(--accent-teal)] text-[var(--bg-deep)]'
                                        : isActive
                                          ? 'bg-[var(--accent-warm-dim)] border-2 border-[var(--accent-warm)] text-[var(--accent-warm)]'
                                          : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-muted)]'
                                    }`}>
                                      {isCompleted ? (
                                        <CheckCircle2 size={16} />
                                      ) : isActive ? (
                                        <Loader2 size={14} className="animate-spin" />
                                      ) : (
                                        <span className="text-[10px] font-bold">{idx + 1}</span>
                                      )}
                                    </div>
                                    {/* Step label */}
                                    <span className={`text-[10px] font-medium transition-colors duration-200 ${
                                      isCompleted
                                        ? 'text-[var(--accent-teal)]'
                                        : isActive
                                          ? 'text-[var(--accent-warm)]'
                                          : 'text-[var(--text-muted)]'
                                    }`}>
                                      {step.label}
                                    </span>
                                  </div>
                                  {/* Connector line */}
                                  {idx < PIPELINE_STEPS.length - 1 && (
                                    <div className="flex-1 max-w-[40px] h-px mx-1 mt-[-18px] bg-[var(--border-subtle)] overflow-hidden relative">
                                      <div className={`absolute inset-0 h-full transition-all duration-500 ${
                                        pipelineStep > idx
                                          ? 'bg-[var(--accent-teal)] w-full'
                                          : pipelineStep === idx
                                            ? 'bg-[var(--accent-warm)] w-full animate-connector'
                                            : 'w-0'
                                      }`} />
                                    </div>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </div>

                          {/* Status text + percentage */}
                          <div className="flex justify-between text-xs font-medium text-[var(--text-secondary)] mb-2">
                            <span>{uploadStatus}</span>
                            <span>{Math.round(uploadProgress)}%</span>
                          </div>
                          {/* Progress bar */}
                          <div className="h-1.5 w-full bg-[var(--bg-deep)] rounded-full overflow-hidden border border-[var(--border-subtle)]">
                            <motion.div 
                              className={`h-full rounded-full transition-colors duration-300 ${
                                pipelineStep >= 3 ? 'bg-[var(--accent-teal)]' : 'bg-[var(--accent-warm)]'
                              }`}
                              initial={{ width: '0%' }}
                              animate={{ width: `${uploadProgress}%` }}
                              transition={{ duration: 0.4, ease: 'easeOut' }}
                            />
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </form>
            </div>
          </motion.div>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
}
