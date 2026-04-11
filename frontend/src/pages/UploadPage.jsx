import React, { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import InteractiveBackground from "../components/InteractiveBackground";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [role, setRole] = useState("Auto Detect");
  const [customRole, setCustomRole] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
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
        // Automatically use localhost in dev mode, but use the environment variable in production (Vercel)
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a file to upload.");
      return;
    }

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append("resume", file);

    // If Custom Role is selected but empty, fallback to Auto Detect
    let finalRole = role;
    if (role === "Custom") {
      finalRole = customRole.trim() !== "" ? customRole.trim() : "Auto Detect";
    }
    formData.append("role", finalRole);

    try {
      // Automatically use localhost in dev mode, but use the environment variable in production
      const apiUrl = import.meta.env.DEV ? "http://127.0.0.1:8000" : (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000");
      const response = await fetch(`${apiUrl}/api/v1/analyze/resume`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server responded with status: ${response.status}`);
      }

      const data = await response.json();

      // Store data in localStorage specifically for the demo dashboard to pick up
      localStorage.setItem("analysisResult", JSON.stringify(data));

      navigate("/dashboard");

    } catch (err) {
      console.error(err);
      setError("Failed to connect to the analysis engine. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col font-sans text-zinc-300 relative">
      <InteractiveBackground />
      {/* Navigation */}
      <nav className="border-b border-zinc-800/50 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-10 px-6 py-4 flex justify-between items-center">
        <Link to="/" className="font-semibold tracking-wide text-zinc-100 flex items-center gap-2">
          <div className="w-4 h-4 bg-zinc-700 rounded-sm"></div>
          SkillGap<span className="text-zinc-500">Analyzer</span>
        </Link>
      </nav>

      <main className="flex-1 flex items-center justify-center p-6 relative z-10 animate-in fade-in zoom-in duration-700">
        <div className="w-full max-w-xl bg-zinc-900/60 backdrop-blur-xl border border-zinc-700/50 p-10 rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] relative overflow-hidden group">

          {/* Subtle Ambient Glow */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-32 bg-blue-500/10 blur-[60px] pointer-events-none rounded-full"></div>

          <div className="mb-10 text-center relative z-10">
            <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400 tracking-tight mb-2">Resume Engine Setup</h1>
            <p className="text-sm text-zinc-400 font-light">Configure analysis parameters and inject your document.</p>
          </div>

          {error && (
            <div className="mb-6 p-3 bg-red-950/30 border border-red-900/50 text-red-400 text-sm rounded-sm">
              [!] {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-8 relative z-10">
            <div className="group/input">
              <label className="block text-xs font-mono text-zinc-400 mb-3 uppercase tracking-widest flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                Target Role Vector (Optional)
              </label>
              <div className="relative">
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full appearance-none bg-zinc-950/80 border border-zinc-700/50 text-zinc-200 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 block p-4 outline-none rounded-xl transition-all shadow-inner hover:border-zinc-600 mb-3 cursor-pointer"
                  disabled={loading}
                >
                  {roleOptions.map(r => (
                    <option key={r} value={r}>{r === "Auto Detect" ? "Auto Detect Profile" : r}</option>
                  ))}
                  <option value="Custom">Other (Custom Role)</option>
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-zinc-400 top-0 h-[52px]">
                  <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z" /></svg>
                </div>
              </div>

              {role === "Custom" && (
                <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                  <input
                    type="text"
                    placeholder="e.g. Product Manager"
                    value={customRole}
                    onChange={(e) => setCustomRole(e.target.value)}
                    className="w-full bg-zinc-950/80 border border-blue-500/50 text-zinc-200 text-sm focus:border-blue-400 focus:ring-1 focus:ring-blue-400 block p-4 outline-none rounded-xl transition-all shadow-[0_0_15px_rgba(59,130,246,0.1)] placeholder:text-zinc-600"
                    disabled={loading}
                  />
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-mono text-zinc-400 mb-3 uppercase tracking-widest flex items-center gap-2">
                <svg className="w-4 h-4 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                Input Vector: Document
              </label>
              <div className={`border-2 border-dashed ${file ? 'border-purple-500/50 bg-purple-500/5' : 'border-zinc-700 bg-zinc-950/50 hover:bg-zinc-800/80 hover:border-blue-500/50'} transition-all duration-300 cursor-pointer relative rounded-2xl p-10 text-center flex flex-col items-center justify-center min-h-[180px] group/drop`}>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  onChange={handleFileChange}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                  disabled={loading}
                />

                {file ? (
                  <div className="text-center animate-in zoom-in duration-300">
                    <div className="w-16 h-16 bg-purple-500/20 text-purple-400 rounded-full flex items-center justify-center mx-auto mb-4 shadow-[0_0_15px_rgba(168,85,247,0.3)]">
                      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <p className="text-zinc-100 font-bold text-base truncate max-w-[250px] mx-auto">{file.name}</p>
                    <p className="text-purple-400 text-xs mt-2 font-mono tracking-widest uppercase">Target Locked</p>
                  </div>
                ) : (
                  <div className="text-center transform group-hover/drop:-translate-y-1 transition-transform duration-300">
                    <div className="w-16 h-16 bg-zinc-800 text-zinc-400 group-hover/drop:text-blue-400 rounded-full flex items-center justify-center mx-auto mb-4 transition-colors">
                      <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                    </div>
                    <p className="text-zinc-300 font-medium text-base mb-1">Drag & Drop Resume</p>
                    <p className="text-zinc-500 text-sm">Supported formats: PDF, DOCX</p>
                  </div>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className={`w-full py-4 text-sm font-bold tracking-widest uppercase transition-all duration-300 rounded-xl flex items-center justify-center gap-2 relative overflow-hidden group/btn ${loading
                ? 'bg-zinc-800 text-zinc-500 cursor-wait border border-zinc-700'
                : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-[0_0_20px_rgba(79,70,229,0.4)] hover:shadow-[0_0_30px_rgba(79,70,229,0.6)]'
                }`}
            >
              {loading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-zinc-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Processing Intelligence...
                </>
              ) : (
                <>
                  <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-[150%] group-hover/btn:animate-[shimmer_1.5s_ease-in-out_infinite]"></div>
                  Initiate Analysis Core
                </>
              )}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
